from __future__ import annotations

import asyncio
import logging
import re
from io import BytesIO
from datetime import date, datetime, timezone
from typing import List, Optional

import fitz  # pymupdf

from features.trips.models import Trip
from features.trips.utils.trip_importer import (
    _normalize_str,
    _parse_service_date,
    _find_flight_text,
    _extract_flight_day,
    _parse_flight_and_time,
    _parse_department_riders,
    _split_airline_and_number,
)
from features.trips.utils.trip_classifier import classify_trip_type_sync

logger = logging.getLogger(__name__)


# ---------- PDF-specific helpers ----------

def _find_city_code_pdf(doc: fitz.Document) -> Optional[str]:
    """
    Extract city/airport code from PDF page 1 metadata.
    Looks for pattern like 'Air Crew Transport Inc (MEM)' in the first page.
    """
    text = doc[0].get_text()

    # Pattern: "Company Name (CODE)" — 3-letter airport code in parentheses
    m = re.search(r"\(([A-Z]{3})\)", text)
    if m:
        return m.group(1)

    # Fallback: look for "CITY:" label like in Excel
    for line in text.split("\n"):
        upper = line.strip().upper()
        if "CITY:" in upper or upper.startswith("CITY"):
            parts = upper.replace("CITY:", "").replace("CITY", "").split()
            for part in parts:
                clean = part.strip()
                if len(clean) == 3 and clean.isalpha():
                    return clean

    return None


def _extract_all_rows(doc: fitz.Document) -> list[list[str]]:
    """
    Extract all data rows from every page of the PDF, skipping repeated
    header/subheader rows (rows 0 and 1 of each page's table).
    """
    all_rows: list[list[str]] = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        tables = page.find_tables()

        if not tables.tables:
            continue

        data = tables.tables[0].extract()

        # Skip header rows (row 0: DATE/DEPARTMENT/..., row 1: Location/From/To)
        # Data starts at row 2
        for row in data[2:]:
            # Normalize None to empty string
            normalized = [cell if cell is not None else "" for cell in row]
            all_rows.append(normalized)

    return all_rows


# ---------- Column indices (fixed from PDF table structure) ----------
# PDF table columns are always:
#   [0] DATE
#   [1] DEPARTMENT
#   [2] #RIDERS
#   [3] PICK UP - Location
#   [4] PICK UP - From
#   [5] Pickup Date/Time (always empty)
#   [6] DROP OFF - Location
#   [7] DROP OFF - To

COL_DATE = 0
COL_DEPARTMENT = 1
COL_RIDERS = 2
COL_PU_LOCATION = 3
COL_PU_FROM = 4
COL_DO_LOCATION = 6
COL_DO_TO = 7


# ---------- Main sync processing ----------

def _process_pdf_sync(
    data: bytes,
    location: str,
    airlinex: str,
    plan: str,
) -> list[Trip]:
    """
    Synchronous function that processes a PDF schedule file.
    Reuses all parsing logic from the Excel trip importer.
    """
    doc = fitz.open(stream=data, filetype="pdf")

    # --- Validate city code ---
    city_code = _find_city_code_pdf(doc)

    if not city_code:
        raise ValueError(
            "No se encontró el código de aeropuerto en el archivo PDF. "
            "Por favor verifica que el archivo contenga el código del aeropuerto."
        )

    if city_code.upper() != location.upper():
        raise ValueError(
            f"El código de aeropuerto en el PDF ({city_code}) no coincide "
            f"con el seleccionado ({location}). "
            f"Por favor verifica que el archivo PDF sea del aeropuerto correcto."
        )

    # --- Extract all data rows across pages ---
    rows = _extract_all_rows(doc)
    doc.close()

    if not rows:
        raise RuntimeError("No se encontraron datos de trips en el archivo PDF.")

    airlinex = _normalize_str(airlinex)
    trips: List[Trip] = []
    current_service_date: Optional[date] = None

    for row_idx, row in enumerate(rows):
        date_raw = _normalize_str(row[COL_DATE])
        department_val = _normalize_str(row[COL_DEPARTMENT])
        pickup_loc_val = _normalize_str(row[COL_PU_LOCATION])
        pickup_raw = _normalize_str(row[COL_PU_FROM])
        dropoff_loc_val = _normalize_str(row[COL_DO_LOCATION])
        dropoff_raw = _normalize_str(row[COL_DO_TO])

        # --- Stop marker ---
        upper_date = date_raw.upper()
        if upper_date and (
            "END OF TRANSPORTATION SCHEDULE" in upper_date
            or "THIS SCHEDULE REPRESENTS" in upper_date
        ):
            break

        # --- DATE with carry-forward ---
        if date_raw:
            try:
                base_service_date = _parse_service_date(date_raw)
                current_service_date = base_service_date
            except Exception as exc:
                logger.error("Error parseando fecha en fila PDF %s: %s", row_idx, exc)
                continue
        else:
            if current_service_date is None:
                continue
            base_service_date = current_service_date

        # --- Skip empty rows ---
        if not any([pickup_raw, dropoff_raw, pickup_loc_val, dropoff_loc_val]):
            continue

        try:
            # --- Flight detection ---
            pickup_flight_text, flight_from_pickup = _find_flight_text(pickup_raw, pickup_loc_val)
            dropoff_flight_text, flight_from_dropoff = _find_flight_text(dropoff_raw, dropoff_loc_val)

            # --- Day from flight suffix ---
            flight_day = _extract_flight_day(pickup_flight_text) or _extract_flight_day(dropoff_flight_text)
            if flight_day is None:
                raise ValueError(
                    "No se encontró el día en el número de vuelo (-DD) en la fila."
                )
            try:
                service_date = base_service_date.replace(day=flight_day)
            except ValueError:
                raise ValueError(
                    f"Día inválido {flight_day} para {base_service_date.strftime('%Y-%m')}"
                )

            # --- Airport code ---
            airport_code: Optional[str] = None
            for v in (pickup_loc_val, dropoff_loc_val):
                s = _normalize_str(v).upper()
                if len(s) == 3 and s.isalpha():
                    airport_code = s
                    break

            # --- Riders from department ---
            riders = _parse_department_riders(department_val)

            if flight_from_pickup:
                # ----- PICK UP AT AIRPORT -----
                airline, flight_number = _split_airline_and_number(flight_from_pickup)

                if airline and airline.upper() != airlinex.upper():
                    raise ValueError(
                        "Se ha detectado mas de una aerolinea en el archivo, "
                        "necesitas una subscripcion para cargar mas de una aerolinea"
                    )

                pick_up_location = airport_code or "AIRPORT"

                if flight_from_dropoff and airport_code:
                    drop_off_location = airport_code
                else:
                    drop_off_location = dropoff_raw or (airport_code or "AIRPORT")

                dropoff_time_source = dropoff_flight_text or dropoff_raw
                _, dropoff_dt = _parse_flight_and_time(dropoff_time_source, service_date)
                if dropoff_dt is None:
                    pickup_time_source = pickup_flight_text or pickup_raw
                    _, pickup_dt = _parse_flight_and_time(pickup_time_source, service_date)
                else:
                    pickup_dt = dropoff_dt

                if pickup_dt is None:
                    pickup_dt = datetime(
                        year=service_date.year,
                        month=service_date.month,
                        day=service_date.day,
                        hour=0,
                        minute=0,
                    )

                pick_up_date = pickup_dt.date()
                pick_up_time = pickup_dt.time().replace(tzinfo=timezone.utc)

            else:
                # ----- PICK UP AT HOTEL -----
                pick_up_location = pickup_raw

                dropoff_time_source = dropoff_flight_text or dropoff_raw
                flight_from_dropoff, dropoff_dt = _parse_flight_and_time(dropoff_time_source, service_date)
                if not flight_from_dropoff or not dropoff_dt:
                    raise ValueError(f"Formato inválido de vuelo en Drop Off: {dropoff_time_source!r}")

                airline, flight_number = _split_airline_and_number(flight_from_dropoff)

                if airline and airline.upper() != airlinex.upper():
                    raise ValueError(
                        "Se ha detectado mas de una aerolinea en el archivo, "
                        "necesitas una subscripcion para cargar mas de una aerolinea"
                    )

                pickup_dt = dropoff_dt
                pick_up_date = pickup_dt.date()
                pick_up_time = pickup_dt.time().replace(tzinfo=timezone.utc)

                drop_off_location = airport_code or "AIRPORT"

            # --- Classify trip type ---
            trip_type = classify_trip_type_sync(
                pick_up_location=pick_up_location,
                drop_off_location=drop_off_location,
                location_airport_code=location,
            )

            # --- Trip hash ---
            trip_hash = hash((
                pick_up_date,
                pick_up_time,
                pick_up_location,
                drop_off_location,
                airline,
                flight_number,
                tuple(sorted(riders.items())),
                trip_type,
            ))

            trips.append(
                Trip(
                    pick_up_date=pick_up_date,
                    pick_up_time=pick_up_time,
                    pick_up_location=pick_up_location,
                    drop_off_location=drop_off_location,
                    airline=airline,
                    flight_number=flight_number,
                    riders=riders,
                    trip_type=trip_type,
                    trip_hash=str(trip_hash),
                )
            )

        except Exception as exc:
            logger.error("Error parseando fila PDF %s: %s", row_idx, exc)
            continue

    return trips


# ---------- Public async API ----------

async def load_trips_from_pdf_bytes(
    data: bytes,
    location: str,
    plan: str,
    airlinex: str,
) -> list[Trip]:
    """
    Reads a PDF schedule file and returns a list of Trip objects.
    Runs the PDF processing in a thread pool to avoid blocking the event loop.
    """
    return await asyncio.to_thread(
        _process_pdf_sync, data, location=location, airlinex=airlinex, plan=plan
    )
