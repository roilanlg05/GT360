# import_airports.py

#Ejecutar con: python -m features.trips.utils.airport_upload

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional
import os

from psqlmodel import Session, create_engine, Select

# 🔁 Ajusta este import al módulo donde tengas definido tu modelo Airport
from ..schemas import Airport  # por ejemplo

# 📌 Ruta al CSV (ajusta según dónde lo tengas)
CSV_PATH = Path("features/trips/utils/files/AIRPORTS.csv")

# 📌 URL de tu base de datos (cámbiala por la real)
# Soporta override por variable de entorno DATABASE_URL



engine = create_engine(
    username="hashdown",
    password="Rlg*020305",
    database="gt360",
    ensure_database=False,
    ensure_tables=False,
    auto_startup=False,
    check_schema_drift=False,
    debug=True,
    models_path=[
        "features/auth/schemas/auth_schemas.py", 
        "features/trips/schemas/trip_schemas.py"
    ],
    ignore_duplicates=True
)

if __name__ == "__main__":
    print(f"Connecting to database")


def normalize_zone_code(value: Optional[str]) -> str:
    """
    Tu schema exige zone_code NOT NULL.
    Si viene vacío/NaN en el CSV, le ponemos 'NA' por defecto.
    Cámbialo si quieres otro valor por defecto.
    """
    if value is None:
        return "NA"
    text = str(value).strip().upper()
    if not text or text == "NAN":
        return "NA"
    return text[:4]


def import_airports_from_csv(csv_path: Path) -> None:
    """
    Lee el CSV UPPLY-AIRPORTS y:
    - Si el code ya existe => actualiza el registro.
    - Si no existe => lo crea.
    Respeta el UniqueConstraint("code").
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {csv_path}")

    with Session(engine) as session, csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")

        count = 0
        for row in reader:
            code = (row.get("code") or "").strip().upper()
            if not code:
                # fila inválida o vacía
                continue

            name = (row.get("name") or "").strip()
            if not name:
                continue

            # Convertimos lat/lon a float
            try:
                latitude = float(row.get("latitude"))
                longitude = float(row.get("longitude"))
            except (TypeError, ValueError):
                print(f"⚠️  Saltando {code}: lat/lon inválidos -> {row.get('latitude')}, {row.get('longitude')}")
                continue

            country_code = (row.get("country_code") or "").strip().upper()
            if not country_code:
                print(f"⚠️  Saltando {code}: country_code vacío")
                continue

            zone_code = normalize_zone_code(row.get("zone_code"))

            # 🔎 ¿Ya existe este aeropuerto?
            existing = session.exec(
                Select(Airport).Where(Airport.code == code)
            ).first()

            if existing:
                # Update
                existing.name = name
                existing.latitude = latitude
                existing.longitude = longitude
                existing.country_code = country_code
                existing.zone_code = zone_code
            else:
                # Insert
                airport = Airport(
                    code=code,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    country_code=country_code,
                    zone_code=zone_code,
                )
                session.add(airport)

            count += 1
            # Commit por lotes para no acumular demasiado en memoria
            if count % 50 == 0:
                session.commit()
                print(f"💾 Commit intermedio, procesados {count} aeropuertos...")

        session.commit()
        print(f"✅ Importación terminada: {count} aeropuertos procesados.")


if __name__ == "__main__":
    import_airports_from_csv(CSV_PATH)
