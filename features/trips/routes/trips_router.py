from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends, Request, Response
from fastapi.responses import JSONResponse
from shared.db.db_config import get_db
from psqlmodel import Select, Count, Delete, AsyncSession, With, RawExpression, NotExists
from psqlmodel.utils import unnest, Array
from shared.db.schemas import Trip as TripDB, Location, Airport, Organization, Hotel
from features.trips.utils.trip_importer import load_trips_from_bytes
from features.trips.models import TripUpdate, CreateTrip, LocationZoneUpdate, HotelPointUpdate
from features.trips.models.qr_models import CreateQRCode, UpdateQRCode, QRCodeResponse
from shared.middlewares.user_context import get_user_time_format
from shared.utils.serialization import model_dump_with_time_format
from datetime import date, time, datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from uuid import UUID
from features.auth.utils import verify_role
from features.trips.utils import get_locations_by_org_id, tz_from_latlon
from features.trips.utils.trip_classifier import classify_trip_type
from shared.db.schemas import TripType, TripStatus
from shared.redis.redis_client import redis_client as redis
from shared.redis.redis_safe import safe_redis_call
import json



router = APIRouter(tags=["Trips"])

@router.post("/v1/trips/upload-trips")
async def upload_trips(
    airport: str,
    provider: str,
    airline: str,
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> dict:
    """
    Sube un archivo Excel con el schedule de trips y los guarda en la base de datos.
    """
    # Validar extensión del archivo
    if not file.filename or not (file.filename.endswith(".xlsx") or file.filename.endswith(".xlsm") or file.filename.endswith(".xls")):
        raise HTTPException(
            status_code=400,
            detail="Debe subir un archivo Excel (.xlsx / .xlsm / .xls).",
        )

    user_data = request.state.user_data
    org_id = user_data.get("organization_id")

    print(f"ORGANIZATION: {org_id}")
    
    organization = await session.exec(
        Select(Organization)
        .Where(Organization.id == org_id)
        ).first()

    # Validar que la organización existe
    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organización no encontrada. Verifique que su cuenta esté correctamente configurada."
        )

    # Leer el contenido del archivo
    content = await file.read()

    # Cargar viajes desde el Excel (función asíncrona)
    try:
        trips_import = await load_trips_from_bytes(content, location=airport, plan=organization.plan, airlinex=airline)
    except ValueError as e:
        # Errores de validación (código de aeropuerto incorrecto, múltiples aerolíneas, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # Errores de formato del Excel (hoja no encontrada, encabezados incorrectos, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Cualquier otro error inesperado
        raise HTTPException(
            status_code=400,
            detail=f"Error al procesar el archivo Excel: {str(e)}"
        )

    if not trips_import:
        raise HTTPException(
            status_code=400,
            detail="No se pudieron extraer viajes del archivo. Verifica que sea una hoja tipo 'Schedule'.",
        )

    # Buscar el aeropuerto en la base de datos
    stmt = Select(Airport).Where(Airport.code == airport.upper())
    airportdb = await session.exec(stmt).first()

    if not airportdb:
        raise HTTPException(
            status_code=404,
            detail=f"Aeropuerto con código '{airport}' no encontrado.",
        )

    location = await session.exec(
        Select(Location)
        .Where((Location.name == airport) & (Location.organization_id == org_id))
    ).first()

    radio = 0.0

    if not location:
        # Crear Location con timezone basado en coordenadas del aeropuerto
        location = Location(
            organization_id=organization.id,
            name=airport,
            point={
                "type": "Point",
                "coordinates": [
                    airportdb.longitude, 
                    airportdb.latitude
                ]
            },
            radio_zone = radio,
            provider=provider,
            timezone=tz_from_latlon(airportdb.latitude, airportdb.longitude)
        )
    
    session.add(location)
    await session.flush()
    await session.refresh(location)

    # Check for duplicate trips using CTE
    trip_hashes = [str(t.trip_hash) for t in trips_import]
    total_trips = len(trip_hashes)

    if total_trips > 0:
        # CTE query to count how many trips from the uploaded file don't exist in the database
        cte_query = (
            With(
                "file_trips",
                Select(unnest(Array(trip_hashes)).As("trip_hash"))
            )
            .Then(
                Select(Count(RawExpression("*")))
                .From("file_trips")
                .Where(
                    NotExists(
                        Select(RawExpression("1"))
                        .From(TripDB)
                        .Where(TripDB.trip_hash == RawExpression("file_trips.trip_hash"))
                        .And(TripDB.location_id == location.id)
                    )
                )
            )
        )

        result = await session.exec(cte_query).first()

        # Extraer el valor del COUNT - psqlmodel devuelve un Row con la clave 'count'
        if hasattr(result, 'count') and not callable(result.count):
            new_trips_count = int(result.count)
        elif isinstance(result, dict):
            new_trips_count = int(result.get('count', 0))
        elif hasattr(result, '__getitem__'):
            try:
                new_trips_count = int(result['count'])
            except (KeyError, TypeError):
                new_trips_count = int(list(result.values())[0]) if hasattr(result, 'values') else 0
        else:
            new_trips_count = int(result) if result else 0

        # If less than 90% of trips are new, the file was likely already uploaded
        new_trips_percentage = (new_trips_count / total_trips) * 100

        if new_trips_percentage < 90:
            raise HTTPException(
                status_code=409,
                detail="This file has already been uploaded. Most trips in this file already exist in the database."
            )

    # Crear los trips

    created = 0
    trips_to_create = []
    trips = []
    hotels_set = set()
    hotels_result = []

    # ===================================================================
    # DETECTAR DÍAS EXISTENTES (para auto-apply preset)
    # ===================================================================
    existing_dates_for_airline = set()
    if airline:
        existing_dates_query = (
            Select(TripDB.pick_up_date)
            .Where(TripDB.location_id == location.id)
            .Where(TripDB.airline == airline)
            .Distinct()
        )
        existing_dates_rows = await session.exec(existing_dates_query).all()
        existing_dates_for_airline = set(existing_dates_rows)
        print(f"[AUTO_PRESET] Existing dates for {location.id}/{airline}: {len(existing_dates_for_airline)} days")

    try:
        # Obtener el timezone de la location para asignar correctamente a los tiempos
        # Validar que el timezone sea válido, usar default si no
        try:
            if location.timezone:
                location_tz = ZoneInfo(location.timezone)
            else:
                location_tz = ZoneInfo("America/New_York")  # Default timezone
        except Exception:
            location_tz = ZoneInfo("America/New_York")  # Fallback si timezone es inválido
        
        # 1. Construir la lista de objetos en memoria (rápido)
        for t in trips_import:
            # El pick_up_time del Excel viene como hora local, reemplazar tzinfo con el tz correcto
            pick_up_time_local = t.pick_up_time.replace(tzinfo=location_tz)

            # trip_type ya viene calculado desde el importer
            trip_type = t.trip_type if hasattr(t, 'trip_type') and t.trip_type else None

            db_trip = TripDB(
                location_id=location.id,
                pick_up_date=t.pick_up_date,
                pick_up_time=pick_up_time_local,
                pick_up_location=t.pick_up_location,
                drop_off_location=t.drop_off_location,
                airline=t.airline,
                flight_number=t.flight_number,
                riders=t.riders,
                trip_type=trip_type,
                trip_hash=str(t.trip_hash),
                status=TripStatus.SCHEDULED
            )
            trips_to_create.append(db_trip)
            
            # Guardar nombres de hoteles únicos (strings, no objetos)
            if db_trip.pick_up_location.upper() != location.name.upper():
                hotels_set.add(db_trip.pick_up_location.strip())
            if db_trip.drop_off_location.upper() != location.name.upper():
                hotels_set.add(db_trip.drop_off_location.strip())

            created += 1

        # 2. Insertar todo el lote de una sola vez (optimizado)
        if trips_to_create:
            # ACTIVAR BATCH MODE: Los triggers NO enviarán eventos individuales
            # Ejecutar raw SQL directamente con exec() usando string plano
            try:
                await session.exec("SET LOCAL app.batch_insert_mode = 'true'")
            except Exception as e:
                print(f"[WARNING] Could not set batch_insert_mode: {e}")
                # Continuar de todas formas, los triggers enviarán eventos individuales

            # Procesar en chunks si son miles (ej. 5000) para no saturar la consulta
            chunk_size = 5000
            for i in range(0, len(trips_to_create), chunk_size):
                batch = trips_to_create[i : i + chunk_size]

                # [FIXED] BulkInsert sin .Returning() para evitar el bug de psqlmodel
                # El .Returning() junto con .OrderBy() y .all() causa TypeError en psqlmodel
                await session.BulkInsert(batch)

            # Obtener los primeros 50 trips insertados para la respuesta
            trips_stmt = (
                Select(TripDB)
                .Where(TripDB.location_id == location.id)
                .OrderBy(
                    TripDB.pick_up_date.Asc(),
                    TripDB.pick_up_time.Asc()
                )
                .Limit(50)
            )
            trips_objs = await session.exec(trips_stmt).all()
            # Serializar trips a JSON (convierte UUIDs a strings) con formato de hora
            time_format = await get_user_time_format(request, session)
            trips = [model_dump_with_time_format(t, time_format) for t in trips_objs]

            # Convertir nombres de hoteles a objetos Hotel y hacer bulk insert
            if hotels_set:
                # Consultar hoteles existentes para esta location
                existing_hotels_stmt = Select(Hotel.name).Where(Hotel.location_id == location.id)
                existing_hotels_rows = await session.exec(existing_hotels_stmt).all()
                # Extraer nombres (siempre intentar acceder al índice 0)
                existing_hotel_names = set()
                for row in existing_hotels_rows:
                    try:
                        # Row objects y tuplas soportan indexación
                        existing_hotel_names.add(row[0])
                    except (TypeError, IndexError, KeyError):
                        # Si falla, es un string directo
                        existing_hotel_names.add(row)
                
                print(f"[HOTELS] hotels_set: {hotels_set}")
                print(f"[HOTELS] existing: {existing_hotel_names}")
                
                # Filtrar solo los hoteles nuevos
                new_hotels = {h for h in hotels_set if h not in existing_hotel_names}
                
                print(f"[HOTELS] new_hotels: {new_hotels}")
                
                if new_hotels:
                    hotel_objects = [Hotel(name=name, location_id=location.id) for name in new_hotels]
                    # [FIXED] BulkInsert sin .Returning() para evitar el bug de psqlmodel
                    await session.BulkInsert(hotel_objects)

                    # Obtener los hoteles insertados para la respuesta
                    hotels_stmt = Select(Hotel).Where(Hotel.location_id == location.id)
                    hotels_objs = await session.exec(hotels_stmt).all()
                    # Serializar hoteles a JSON (convierte UUIDs a strings)
                    hotels_result = [h.model_dump(mode="json") for h in hotels_objs]

        # Confirmar la transacción solo si todo salió bien
        await session.commit()

        # ===================================================================
        # AUTO-APPLY PRESET (V2)
        # ===================================================================
        if trips_to_create and airline:
            from features.trips.services.filter_preset_service import FilterPresetService

            # Get unique dates from imported trips
            unique_dates_imported = {t.pick_up_date for t in trips_to_create}

            # CRITICAL: Filter to ONLY new dates (not pre-existing)
            # A date is "new" if it didn't exist before in trips.trips for this location+airline
            new_dates = [d for d in unique_dates_imported if d not in existing_dates_for_airline]

            if not new_dates:
                print(
                    f"[AUTO_PRESET] No new dates to process "
                    f"(all {len(unique_dates_imported)} dates already existed)"
                )
            else:
                print(
                    f"[AUTO_PRESET] Detected {len(new_dates)} new dates "
                    f"(out of {len(unique_dates_imported)} total)"
                )

                # Auto-apply preset ONLY to new dates
                preset_service = FilterPresetService(session)
                try:
                    auto_apply_result = await preset_service.auto_apply_preset(
                        location_id=location.id,
                        airline=airline,
                        pick_up_dates=new_dates
                    )

                    if auto_apply_result.applied:
                        print(
                            f"[AUTO_PRESET] ✅ Applied preset to {auto_apply_result.days_processed} days, "
                            f"affected {auto_apply_result.trips_affected} trips"
                        )
                        if auto_apply_result.days_skipped > 0:
                            print(
                                f"[AUTO_PRESET] Skipped {auto_apply_result.days_skipped} days "
                                "(already have stack)"
                            )
                    else:
                        print(f"[AUTO_PRESET] Not applied: {auto_apply_result.reason}")

                except Exception as e:
                    # Don't fail the import if auto-apply fails
                    print(f"[AUTO_PRESET] ⚠️ Auto-apply failed: {e}")

        # DESPUÉS del commit, enviar UN evento batch (batch_insert_mode se resetea automáticamente con COMMIT)
        if trips_to_create:
            # Calcular meses afectados
            months_affected = {}
            for trip in trips_to_create:
                year = trip.pick_up_date.year
                month = trip.pick_up_date.month - 1  # JavaScript format (0-11)
                key = f"{year}-{month}"
                if key not in months_affected:
                    months_affected[key] = {"year": year, "month": month, "count": 0}
                months_affected[key]["count"] += 1

            # Construir evento batch
            batch_event = {
                "type": "batch_insert",
                "location_id": str(location.id),
                "location_name": location.name,
                "airline": airline if airline else None,
                "trips_count": created,
                "months_affected": list(months_affected.values()),
                "message": f"{created} trips uploaded successfully"
            }

            # Publicar evento a Redis
            # Canal loc:{location_id} para usuarios conectados a /ws/trips
            loc_channel = f"loc:{location.id}"
            await safe_redis_call(
                redis.publish,
                loc_channel,
                json.dumps(batch_event),
                context=f"publish {loc_channel}",
            )

            # También publicar al canal org para usuarios conectados a /ws/org
            if hasattr(location, 'organization_id') and location.organization_id:
                org_channel = f"org:{location.organization_id}"
                await safe_redis_call(
                    redis.publish,
                    org_channel,
                    json.dumps(batch_event),
                    context=f"publish {org_channel}",
                )

            print(f"[BATCH WS] Sent batch_insert event: {created} trips, {len(months_affected)} months affected")

    except Exception as e:
        # Rollback en caso de error
        try:
            await session.rollback()
        except Exception:
            pass
        
        msg = str(e)
        print(e)
        if "DETAIL:" in msg:
            msg = msg.split("DETAIL:", 1)[1].strip()
        raise HTTPException(
            status_code=422,
            detail=f"We couldn't validate the schedule: {msg}"
        )

    return JSONResponse(
            content={
                "status": "ok",
                "uploaded_rows": created,
                "location_id": str(location.id),
                "airport_code": airport,
                "trips": trips,
                "hotels": hotels_result
            }, 
            status_code=201
    )

@router.post("/v1/locations/{location_id}/trips")
async def create_trip(
    location_id: str,
    request: Request,
    trip_data: CreateTrip,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
    ):

    
    try:
        from uuid import UUID
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")
    
    # Obtener la location para acceder a su timezone
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")
    
    try:
        # preparar payload y convertir strings a date/time si vienen como texto
        trip_payload = trip_data.model_dump(exclude_unset=True)
        if "pick_up_date" in trip_payload and isinstance(trip_payload.get("pick_up_date"), str):
            trip_payload["pick_up_date"] = date.fromisoformat(trip_payload["pick_up_date"])
        if "pick_up_time" in trip_payload and isinstance(trip_payload.get("pick_up_time"), str):
            trip_payload["pick_up_time"] = time.fromisoformat(trip_payload["pick_up_time"])
        # Asignar el timezone correcto de la location
        if "pick_up_time" in trip_payload and isinstance(trip_payload.get("pick_up_time"), time) and trip_payload["pick_up_time"].tzinfo is None:
            location_tz = ZoneInfo(location.timezone)
            trip_payload["pick_up_time"] = trip_payload["pick_up_time"].replace(tzinfo=location_tz)

        # Calcular trip_type si no fue proporcionado
        if "trip_type" not in trip_payload or not trip_payload["trip_type"]:
            trip_payload["trip_type"] = await classify_trip_type(
                pick_up_location=trip_payload["pick_up_location"],
                drop_off_location=trip_payload["drop_off_location"],
                location_airport_code=location.name  # location.name contiene el código
            )

        # Calcular trip_hash con los mismos campos que trip_importer
        trip_hash = hash((
            trip_payload["pick_up_date"],
            trip_payload["pick_up_time"],
            trip_payload["pick_up_location"],
            trip_payload["drop_off_location"],
            trip_payload["airline"],
            trip_payload["flight_number"],
            tuple(sorted(trip_payload["riders"].items())),
            trip_payload["trip_type"]
        ))
        trip_payload["trip_hash"] = str(trip_hash)

        trip = TripDB(location_id=location_uuid, **trip_payload)
        session.add(trip)
        # flush para obtener ids y validar DB antes del commit
        await session.flush()

        # commit dentro del try: si algo falla después (p. ej. serialización), entra en except
        await session.commit()
        await session.refresh(trip)

        time_format = await get_user_time_format(request, session)
        trip_json = model_dump_with_time_format(trip, time_format)
        return JSONResponse(status_code=200, content={"data": trip_json})

    except Exception as e:
        # intentar rollback, ignorando errores del rollback mismo
        try:
            await session.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get("/v1/locations/{location_id}/trips")
async def get_trips(
    location_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    pick_up_date: Optional[str] = None,
    pick_up_date_from: Optional[str] = None,
    pick_up_date_to: Optional[str] = None,
    pick_up_time: Optional[str] = None,
    pick_up_time_from: Optional[str] = None,
    pick_up_time_to: Optional[str] = None,
    pick_up_location: Optional[str] = None,
    drop_off_location: Optional[str] = None,
    airline: Optional[str] = None,
    flight_number: Optional[str] = None,
    trip_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),  # Optimizado para infinite scroll
    _role=Depends(verify_role(["manager", "driver", "crew"]))
):

    """
    Obtiene una lista paginada de trips.
    """
    from uuid import UUID

    # Validar UUID de location
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    # Convertir strings a date/time objects
    try:
        pick_up_date_obj = date.fromisoformat(pick_up_date) if pick_up_date else None
        pick_up_date_from_obj = date.fromisoformat(pick_up_date_from) if pick_up_date_from else None
        pick_up_date_to_obj = date.fromisoformat(pick_up_date_to) if pick_up_date_to else None
        pick_up_time_obj = time.fromisoformat(pick_up_time) if pick_up_time else None
        pick_up_time_from_obj = time.fromisoformat(pick_up_time_from) if pick_up_time_from else None
        pick_up_time_to_obj = time.fromisoformat(pick_up_time_to) if pick_up_time_to else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Formato de fecha/hora inválido: {e}")

    # Construir condiciones dinámicas según parámetros opcionales
    filters = [TripDB.location_id == location_uuid]
    # filtros exactos
    if pick_up_date_obj:
        filters.append(TripDB.pick_up_date == pick_up_date_obj)
    if pick_up_time_obj:
        filters.append(TripDB.pick_up_time == pick_up_time_obj)
    # filtros rango
    if pick_up_date_from_obj:
        filters.append(TripDB.pick_up_date >= pick_up_date_from_obj)
    if pick_up_date_to_obj:
        filters.append(TripDB.pick_up_date <= pick_up_date_to_obj)
    if pick_up_time_from_obj:
        filters.append(TripDB.pick_up_time >= pick_up_time_from_obj)
    if pick_up_time_to_obj:
        filters.append(TripDB.pick_up_time <= pick_up_time_to_obj)
    # filtros texto
    if pick_up_location:
        filters.append(TripDB.pick_up_location.ilike(f"%{pick_up_location}%"))
    if drop_off_location:
        filters.append(TripDB.drop_off_location.ilike(f"%{drop_off_location}%"))
    if airline:
        filters.append(TripDB.airline.ilike(f"%{airline}%"))
    if flight_number:
        filters.append(TripDB.flight_number == flight_number)
    if trip_type:
        filters.append(TripDB.trip_type == trip_type)
    # ✅ Usar reduce para combinar con &
    from functools import reduce
    combined_filter = reduce(lambda a, b: a & b, filters)

    # Contar total con los mismos filtros
    """count_stmt = Select(Count(TripDB.id)).From(TripDB).Where(combined_filter)
    total = await session.exec(count_stmt).first()

    # Obtener trips paginados aplicando filtros
    trips_stmt = (
        Select(TripDB, )
        .Where(combined_filter)
        .OrderBy(
            TripDB.pick_up_date,
            TripDB.pick_up_time,
            TripDB.id,
        )
        .Asc()
        .Offset(skip)
        .Limit(limit)
    )"""

    total_count_col = Count(TripDB.id).Over().As("total_count")
    trips_stmt = (
        Select(TripDB, total_count_col)  # Seleccionas el modelo Y el total
        .Where(combined_filter)
        .OrderBy(
            TripDB.pick_up_date.Asc(),
            TripDB.pick_up_time.Asc(),
            TripDB.id.Asc(),
        )
        .Offset(skip)
        .Limit(limit)
    )

    rows = await session.exec(trips_stmt).all()

    # Retornar lista vacía si no hay trips (en lugar de 404)
    if not rows:
        return {
            "data": [],
            "skip": skip,
            "limit": limit,
            "total": 0
        }

    trips = []
    time_format = await get_user_time_format(request, session)

    for row in rows:
        trips.append(model_dump_with_time_format(row[0], time_format))

    total = rows[0][1] if rows else 0

    return {
        "data": trips,
        "skip": skip,
        "limit": limit,
        "total": total
    }

@router.delete("/v1/locations/{location_id}/trips/all")
async def delete_all_trips(    
    location_id: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Elimina todos los trips de una location específica.
    """
    from uuid import UUID

    try:
        uuid_location_id = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Comprobar existencia de la location
    sel_stmt = Select(Location).Where(Location.id == uuid_location_id)
    location = await session.exec(sel_stmt).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Eliminar todos los trips de la location y commitear
    del_stmt = Delete(TripDB).Where(TripDB.location_id == uuid_location_id)
    await session.exec(del_stmt)
    await session.commit()

    return Response(status_code=204)


@router.delete("/v1/locations/{location_id}/trips")
async def delete_trips(
    location_id: str,
    trip_ids: list[str] = Query(..., description="Lista de IDs de trips a eliminar"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Elimina múltiples trips por sus IDs y location_id.
    """
    from uuid import UUID

    # Validar location_id
    try:
        uuid_location_id = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar y convertir todos los trip_ids
    uuid_trip_ids = []
    invalid_ids = []
    
    for trip_id in trip_ids:
        try:
            uuid_trip_ids.append(UUID(trip_id))
        except ValueError:
            invalid_ids.append(trip_id)
    
    if invalid_ids:
        raise HTTPException(
            status_code=400, 
            detail=f"IDs de trip inválidos: {', '.join(invalid_ids)}"
        )
    
    # Aquí tienes la lista de UUIDs validados para tu lógica de borrado
    # uuid_trip_ids contiene todos los UUIDs válidos
    # uuid_location_id contiene el UUID de la location

    trips_ids = await session.exec(
        Select(TripDB.id)
        .Where(
            (TripDB.id.In(uuid_trip_ids)) & 
            (TripDB.location_id == uuid_location_id)
        )
    ).all()

    if not trips_ids:
        raise HTTPException(
            status_code=404, 
            detail="No se encontraron trips para eliminar con los IDs proporcionados en la location especificada."
        )
    
    await session.BulkDelete(TripDB, uuid_trip_ids).Where(TripDB.location_id == uuid_location_id)
    await session.commit()
    
    return Response(status_code=204)

@router.patch("/v1/locations/{location_id}/trips/{trip_id}")
async def edit_trip(
    location_id: str,
    request: Request,
    trip_id: str,
    trip_update: TripUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Actualiza un trip por su ID y location_id.
    """
    from uuid import UUID

    try:
        uuid_id = UUID(trip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de trip inválido")
    
    try:
        uuid_location_id = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Comprobar existencia del trip y obtener la location para el timezone
    sel_stmt = (
        Select(TripDB, Location)
        .Join(Location).On(TripDB.location_id == Location.id)
        .Where((TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id))
    )
    result = await session.exec(sel_stmt).first()
    if not result:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    trip, location = result

    # Actualizar datos del trip: parsear strings ISO a date/time si es necesario
    update_data = trip_update.model_dump(exclude_unset=True)
    if "pick_up_date" in update_data and isinstance(update_data.get("pick_up_date"), str):
        update_data["pick_up_date"] = date.fromisoformat(update_data["pick_up_date"])
    if "pick_up_time" in update_data and isinstance(update_data.get("pick_up_time"), str):
        update_data["pick_up_time"] = time.fromisoformat(update_data["pick_up_time"])
    # Asignar el timezone correcto de la location
    if "pick_up_time" in update_data and isinstance(update_data.get("pick_up_time"), time) and update_data["pick_up_time"].tzinfo is None:
        location_tz = ZoneInfo(location.timezone)
        update_data["pick_up_time"] = update_data["pick_up_time"].replace(tzinfo=location_tz)

    # Recalcular trip_type si cambiaron las locations
    if "pick_up_location" in update_data or "drop_off_location" in update_data:
        # Obtener valores actuales (usar updated si está, sino mantener existente)
        pick_up = update_data.get("pick_up_location", trip.pick_up_location)
        drop_off = update_data.get("drop_off_location", trip.drop_off_location)

        update_data["trip_type"] = await classify_trip_type(
            pick_up_location=pick_up,
            drop_off_location=drop_off,
            location_airport_code=location.name
        )

    for key, value in update_data.items():
        setattr(trip, key, value)

    session.add(trip)

    await session.commit()
    await session.refresh(trip)  # Asegurar datos actualizados (updated_at, etc.)

    time_format = await get_user_time_format(request, session)
    trip = model_dump_with_time_format(trip, time_format)

    print("TRIP UPDATED: ", trip)

    return JSONResponse(content={"status": "ok", "trip": trip})



@router.get("/v1/locations")
async def get_locations(
    request: Request,
    session: AsyncSession = Depends(get_db),
    location_id: str | None = None,
    _role=Depends(verify_role(["manager", "driver"]))
):
    metadata = request.state.user_data
    org_id = metadata.get("organization_id")

    if location_id:
        location = await session.exec(
            Select(Location)
            .Where((Location.id == location_id) & (Location.organization_id == org_id))
        ).first()

        if not location:
            raise HTTPException(status_code=404, detail="Location not found")

        return JSONResponse(status_code=200, content={"data": location.model_dump(mode="json")})

    locations = await get_locations_by_org_id(session, org_id)

    return JSONResponse(status_code=200, content={"data": locations})

@router.patch("/v1/locations/{location_id}")
async def edit_location(
    location_id: str,
    location_data: LocationZoneUpdate,
    session: AsyncSession = Depends(get_db),
    _role = Depends(verify_role(["manager", "driver"]))
    ):
    """
    Actualiza el point y/o radio_zone de una location.
    """
    from uuid import UUID

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    location = await session.get(Location, location_uuid)

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    if location_data.point is not None:
        location.point = location_data.point
    if location_data.radio_zone is not None:
        location.radio_zone = location_data.radio_zone
    if location_data.address is not None:
        location.address = location_data.address
    if location_data.validation_status is not None:
        location.validation_status = location_data.validation_status

    session.add(location)
    await session.commit()
    await session.refresh(location)

    return JSONResponse(content={"status": "ok", "location": location.model_dump(mode="json")})

@router.delete("/v1/locations/{location_id}")
async def delete_location(
    location_id: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    from uuid import UUID

    # Validar UUID de location
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    # Guardar datos antes de eliminar para el mensaje WebSocket
    location_name = location.name
    org_id = str(location.organization_id)

    # Contar trips y hotels antes de eliminar
    trips_count_result = await session.exec(
        Select(Count(TripDB.id)).From(TripDB).Where(TripDB.location_id == location_uuid)
    ).first()
    trips_count = trips_count_result[0] if trips_count_result else 0

    hotels_count_result = await session.exec(
        Select(Count(Hotel.id)).From(Hotel).Where(Hotel.location_id == location_uuid)
    ).first()
    hotels_count = hotels_count_result[0] if hotels_count_result else 0

    # 1. Publicar evento "location_delete_started" para que el frontend ignore los batches del streaming
    #    Publicamos a AMBOS canales para que llegue a usuarios conectados a /ws/trips y /ws/org
    start_event = {
        "type": "location_delete_started",
        "location_id": location_id,
        "location_name": location_name,
        "trips_count": trips_count,
        "hotels_count": hotels_count
    }
    start_event_json = json.dumps(start_event)
    await safe_redis_call(
        redis.publish,
        f"org:{org_id}",
        start_event_json,
        context=f"publish org:{org_id}",
    )
    await safe_redis_call(
        redis.publish,
        f"loc:{location_id}",
        start_event_json,
        context=f"publish loc:{location_id}",
    )

    # 2. Eliminar trips manualmente primero
    if trips_count > 0:
        await session.exec(
            Delete(TripDB).Where(TripDB.location_id == location_uuid)
        )

    # 3. Eliminar hotels asociados
    if hotels_count > 0:
        await session.exec(
            Delete(Hotel).Where(Hotel.location_id == location_uuid)
        )

    # 4. Eliminar la location
    await session.exec(
        Delete(Location).Where(Location.id == location_uuid)
    )

    await session.commit()

    # 5. Publicar evento "location_deleted" con resumen final consolidado
    #    Publicamos a AMBOS canales para que llegue a usuarios conectados a /ws/trips y /ws/org
    deleted_event = {
        "type": "location_deleted",
        "location_id": location_id,
        "location_name": location_name,
        "trips_deleted": trips_count,
        "hotels_deleted": hotels_count,
        "message": f"Location {location_name} deleted",
        "detail": f"{trips_count} trips and {hotels_count} hotels also deleted"
    }
    deleted_event_json = json.dumps(deleted_event)
    await safe_redis_call(
        redis.publish,
        f"org:{org_id}",
        deleted_event_json,
        context=f"publish org:{org_id}",
    )
    await safe_redis_call(
        redis.publish,
        f"loc:{location_id}",
        deleted_event_json,
        context=f"publish loc:{location_id}",
    )

    return JSONResponse(status_code=200, content={
        "status": "ok",
        "data": {
            "location_id": location_id,
            "location_name": location_name,
            "trips_deleted": trips_count,
            "hotels_deleted": hotels_count,
            "message": f"Location {location_name} deleted successfully"
        }
    })

@router.get("/v1/locations/{location_id}/hotels")
async def get_hotels(
    location_id: str,
    session: AsyncSession = Depends(get_db),
    name: Optional[str] = None,
    exact: bool = Query(False, description="If true, match exact name; otherwise partial match"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Obtiene una lista paginada de hoteles para una location.
    Permite buscar por nombre exacto o parcial.
    """
    from uuid import UUID

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    # Construir filtros
    filters = [Hotel.location_id == location_uuid]
    
    if name:
        if exact:
            filters.append(Hotel.name == name)
        else:
            filters.append(Hotel.name.ilike(f"%{name}%"))

    from functools import reduce
    combined_filter = reduce(lambda a, b: a & b, filters)

    # Query con conteo total usando window function
    total_count_col = Count(Hotel.id).Over().As("total_count")
    hotels_stmt = (
        Select(Hotel, total_count_col)
        .Where(combined_filter)
        .OrderBy(Hotel.name.Asc())
        .Offset(skip)
        .Limit(limit)
    )

    rows = await session.exec(hotels_stmt).all()

    if not rows:
        return {
            "data": [],
            "skip": skip,
            "limit": limit,
            "total": 0
        }

    hotels = [row[0].model_dump(mode="json") for row in rows]
    total = rows[0][1] if rows else 0

    return {
        "data": hotels,
        "skip": skip,
        "limit": limit,
        "total": total
    }

@router.get("/v1/locations/{location_id}/airlines")
async def get_airlines(
    location_id: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Retorna todas las airlines únicas disponibles para una location específica.
    Útil para poblar dropdowns y navegación entre airlines sin cargar todos los trips.
    """
    from uuid import UUID

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    # Obtener airlines únicas ordenadas alfabéticamente
    airlines_stmt = (
        Select(TripDB.airline)
        .Where(TripDB.location_id == location_uuid)
        .Distinct()
        .OrderBy(TripDB.airline.Asc())
    )

    rows = await session.exec(airlines_stmt).all()

    # Extraer el string de cada row (psqlmodel retorna Row objects, no strings directos)
    airlines = []
    for row in rows:
        if row is None:
            continue
        # Si row es un string, usarlo directamente
        if isinstance(row, str):
            airlines.append(row)
        # Si row es una tupla o tiene índice, extraer el primer elemento
        elif hasattr(row, '__getitem__'):
            val = row[0] if len(row) > 0 else None
            if val and isinstance(val, str):
                airlines.append(val)
        # Si row tiene atributo airline
        elif hasattr(row, 'airline'):
            if row.airline:
                airlines.append(str(row.airline))
        else:
            # Último recurso: convertir a string
            airlines.append(str(row))

    return {
        "location_id": location_id,
        "location_name": location.name,
        "airlines": airlines,
        "total": len(airlines)
    }

@router.get("/v1/locations/{location_id}/months")
async def get_available_months(
    location_id: str,
    airline: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Retorna meses disponibles para location/airline.
    SOURCE OF TRUTH - no depende de WebSocket snapshot.

    Este endpoint resuelve el problema de calcular availableMonths client-side,
    que es ineficiente y depende de un snapshot incompleto de WebSocket.

    Args:
        location_id: UUID de la location
        airline: Opcional - filtrar por airline específica

    Returns:
        {
            "location_id": "uuid",
            "location_name": "SDF",
            "airline": "WN" | null,
            "months": [
                {"year": 2026, "month": 0, "count": 1341},
                {"year": 2026, "month": 1, "count": 890}
            ],
            "total_months": 2
        }
    """
    from uuid import UUID

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar location existe
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    # Query SQL optimizada con GROUP BY
    # psqlmodel usa positional params ($1, $2) no named params (:name)
    query = """
        SELECT
            EXTRACT(YEAR FROM pick_up_date)::int AS year,
            EXTRACT(MONTH FROM pick_up_date)::int AS month,
            COUNT(*)::int AS trips_count
        FROM trips.trips
        WHERE location_id = $1
    """

    params = [location_uuid]

    if airline:
        query += " AND airline ILIKE $2"
        params.append(f"%{airline}%")

    query += """
        GROUP BY year, month
        ORDER BY year DESC, month DESC
    """

    # Ejecutar query raw SQL usando la engine de psqlmodel directamente
    from shared.db.db_config import engine

    # psqlmodel engine usa execute_raw_async() con positional params como lista
    result = await engine.execute_raw_async(query, params)
    rows = result

    months = [
        {
            "year": row[0],
            "month": row[1] - 1,  # JavaScript usa 0-11, SQL usa 1-12
            "count": row[2]
        }
        for row in rows
    ]

    return {
        "location_id": location_id,
        "location_name": location.name,
        "airline": airline,
        "months": months,
        "total_months": len(months)
    }


# =============================================================================
# TIMELINE ENDPOINTS (Live/History with Anchor and Cursor Pagination)
# =============================================================================

@router.get("/v1/locations/{location_id}/days")
async def get_available_days(
    location_id: str,
    year: int = Query(..., description="Year (e.g., 2026)"),
    month: int = Query(..., ge=0, le=11, description="Month (0-11 JavaScript format)"),
    airline: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Returns available days for a specific month with live/history trip counts.

    The month parameter uses JavaScript format (0-11) for frontend consistency.
    Returns current_day based on the location's timezone.
    """
    from features.trips.utils import (
        get_current_date_in_timezone,
        get_current_time_in_timezone
    )
    from shared.db.db_config import engine

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    # Validate location exists
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Convert JavaScript month (0-11) to SQL month (1-12)
    sql_month = month + 1

    # Get current date/time in location timezone
    current_date = get_current_date_in_timezone(location.timezone)
    current_time = get_current_time_in_timezone(location.timezone)

    # Build SQL query for day counts with live/history breakdown
    query = """
        SELECT
            EXTRACT(DAY FROM pick_up_date)::int AS day,
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE
                status = 'en_route'
                OR (
                    status = 'scheduled'
                    AND (
                        pick_up_date > $4::date
                        OR (pick_up_date = $4::date AND pick_up_time > $5::time)
                    )
                )
            ) AS live_count
        FROM trips.trips
        WHERE location_id = $1
          AND EXTRACT(YEAR FROM pick_up_date) = $2
          AND EXTRACT(MONTH FROM pick_up_date) = $3
    """

    params = [location_uuid, year, sql_month, current_date, current_time]

    if airline:
        query += " AND airline ILIKE $6"
        params.append(f"%{airline}%")

    query += """
        GROUP BY day
        ORDER BY day ASC
    """

    result = await engine.execute_raw_async(query, params)

    days = [
        {
            "day": row[0],
            "count": row[1],
            "live_count": row[2],
            "history_count": row[1] - row[2]
        }
        for row in result
    ]

    # Determine current_day only if viewing current month
    current_day = None
    if current_date.year == year and current_date.month == sql_month:
        current_day = current_date.day

    return {
        "location_id": location_id,
        "year": year,
        "month": month,
        "timezone": location.timezone,
        "current_day": current_day,
        "days": days
    }


@router.get("/v1/locations/{location_id}/timeline/anchor")
async def get_timeline_anchor(
    location_id: str,
    airline: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Get anchor information for the timeline to "jump to now".

    Returns:
    - Current date/time in location timezone
    - First live trip (if any) with cursor for pagination
    - Summary of today's trips (live vs history counts)

    This allows the frontend to anchor the scroll position directly
    at the current point in time without loading the entire month.
    """
    from features.trips.utils import (
        get_current_datetime_in_timezone,
        get_current_date_in_timezone,
        get_current_time_in_timezone,
        build_cursor
    )
    from shared.db.db_config import engine

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    # Validate location exists
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Get current datetime in location timezone
    current_dt = get_current_datetime_in_timezone(location.timezone)
    current_date = current_dt.date()
    current_time = current_dt.time()

    # Find first LIVE trip (en_route or scheduled with future pickup)
    first_live_query = """
        SELECT id, pick_up_date, pick_up_time
        FROM trips.trips
        WHERE location_id = $1
          AND (
            status = 'en_route'
            OR (
              status = 'scheduled'
              AND (
                pick_up_date > $2::date
                OR (pick_up_date = $2::date AND pick_up_time > $3::time)
              )
            )
          )
    """

    params = [location_uuid, current_date, current_time]

    if airline:
        first_live_query += " AND airline ILIKE $4"
        params.append(f"%{airline}%")

    first_live_query += """
        ORDER BY pick_up_date ASC, pick_up_time ASC
        LIMIT 1
    """

    first_live_result = await engine.execute_raw_async(first_live_query, params)
    first_live_trip = None

    if first_live_result:
        row = first_live_result[0]
        trip_id = str(row[0])
        trip_date = row[1]
        trip_time = row[2]
        first_live_trip = {
            "id": trip_id,
            "pick_up_date": trip_date.isoformat(),
            "pick_up_time": trip_time.isoformat(),
            "cursor": build_cursor(trip_date, trip_time, trip_id)
        }

    # Get summary for today
    summary_query = """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE
                status = 'en_route'
                OR (
                    status = 'scheduled'
                    AND (
                        pick_up_date > $2::date
                        OR (pick_up_date = $2::date AND pick_up_time > $3::time)
                    )
                )
            ) AS live_count,
            COUNT(*) FILTER (WHERE status = 'scheduled') AS scheduled_count,
            COUNT(*) FILTER (WHERE status = 'en_route') AS en_route_count,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
            COUNT(*) FILTER (WHERE status = 'canceled') AS canceled_count
        FROM trips.trips
        WHERE location_id = $1
          AND pick_up_date = $2::date
    """

    summary_params = [location_uuid, current_date, current_time]

    if airline:
        summary_query += " AND airline ILIKE $4"
        summary_params.append(f"%{airline}%")

    summary_result = await engine.execute_raw_async(summary_query, summary_params)

    today_summary = {
        "total": 0,
        "live": 0,
        "history": 0,
        "by_status": {
            "scheduled": 0,
            "en_route": 0,
            "completed": 0,
            "canceled": 0
        }
    }

    if summary_result:
        row = summary_result[0]
        total = row[0] or 0
        live = row[1] or 0
        today_summary = {
            "total": total,
            "live": live,
            "history": total - live,
            "by_status": {
                "scheduled": row[2] or 0,
                "en_route": row[3] or 0,
                "completed": row[4] or 0,
                "canceled": row[5] or 0
            }
        }

    return {
        "location_id": location_id,
        "timezone": location.timezone,
        "current_datetime": current_dt.isoformat(),
        "current_date": current_date.isoformat(),
        "current_year": current_date.year,
        "current_month": current_date.month - 1,  # JavaScript format (0-11)
        "current_day": current_date.day,
        "first_live_trip": first_live_trip,
        "today_summary": today_summary
    }


@router.get("/v1/locations/{location_id}/timeline")
async def get_timeline(
    location_id: str,
    request: Request,
    airline: Optional[str] = None,
    cursor: Optional[str] = None,
    direction: str = Query("forward", pattern="^(forward|backward)$"),
    date: Optional[str] = None,
    category: str = Query("all", pattern="^(all|live|history)$"),
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Get trips organized as a timeline with bidirectional cursor pagination.

    Parameters:
    - cursor: Pagination cursor (format: "date_time_tripId")
    - direction: "forward" (future/later) or "backward" (past/earlier)
    - date: Specific date to load (alternative to cursor)
    - category: Filter by "all", "live", or "history"
    - status: Filter by specific status (scheduled, en_route, completed, canceled)
    - limit: Number of trips to return (max 100)

    The response includes:
    - Trips with computed is_live field
    - Pagination cursors for forward/backward navigation
    - Summary with live/history counts
    """
    from features.trips.utils import (
        get_current_datetime_in_timezone,
        compute_is_live,
        build_cursor,
        parse_cursor,
        format_time_for_display
    )

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    # Validate location exists
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Get current datetime in location timezone
    current_dt = get_current_datetime_in_timezone(location.timezone)
    current_date = current_dt.date()
    current_time = current_dt.time()

    # Get user's time format preference
    time_format = await get_user_time_format(request, session)
    use_24h = time_format == "24h"

    # Build base filters
    filters = [TripDB.location_id == location_uuid]

    if airline:
        filters.append(TripDB.airline.ilike(f"%{airline}%"))

    if status:
        filters.append(TripDB.status == status)

    # Handle date filter (if provided instead of cursor)
    if date and not cursor:
        try:
            target_date = datetime.fromisoformat(date).date()
            filters.append(TripDB.pick_up_date == target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Handle category filter (live vs history)
    if category == "live":
        # LIVE: en_route OR (scheduled AND future pickup time)
        filters.append(
            (TripDB.status == TripStatus.EN_ROUTE) |
            (
                (TripDB.status == TripStatus.SCHEDULED) &
                (
                    (TripDB.pick_up_date > current_date) |
                    ((TripDB.pick_up_date == current_date) & (TripDB.pick_up_time > current_time))
                )
            )
        )
    elif category == "history":
        # HISTORY: completed, canceled, OR (scheduled with past pickup time)
        filters.append(
            (TripDB.status == TripStatus.COMPLETED) |
            (TripDB.status == TripStatus.CANCELED) |
            (
                (TripDB.status == TripStatus.SCHEDULED) &
                (
                    (TripDB.pick_up_date < current_date) |
                    ((TripDB.pick_up_date == current_date) & (TripDB.pick_up_time <= current_time))
                )
            )
        )

    # Handle cursor-based pagination
    if cursor:
        try:
            cursor_date, cursor_time, cursor_id = parse_cursor(cursor)
            cursor_uuid = UUID(cursor_id)

            if direction == "forward":
                # Get trips AFTER the cursor (future/later)
                filters.append(
                    (TripDB.pick_up_date > cursor_date) |
                    ((TripDB.pick_up_date == cursor_date) & (TripDB.pick_up_time > cursor_time)) |
                    ((TripDB.pick_up_date == cursor_date) & (TripDB.pick_up_time == cursor_time) & (TripDB.id > cursor_uuid))
                )
            else:
                # Get trips BEFORE the cursor (past/earlier)
                filters.append(
                    (TripDB.pick_up_date < cursor_date) |
                    ((TripDB.pick_up_date == cursor_date) & (TripDB.pick_up_time < cursor_time)) |
                    ((TripDB.pick_up_date == cursor_date) & (TripDB.pick_up_time == cursor_time) & (TripDB.id < cursor_uuid))
                )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid cursor format: {str(e)}")

    # Combine filters
    from functools import reduce
    combined_filter = reduce(lambda a, b: a & b, filters)

    # Build query with ordering
    if direction == "backward":
        query = (
            Select(TripDB)
            .Where(combined_filter)
            .OrderBy(
                TripDB.pick_up_date.Desc(),
                TripDB.pick_up_time.Desc(),
                TripDB.id.Desc()
            )
            .Limit(limit + 1)  # Fetch one extra to check if there's more
        )
    else:
        query = (
            Select(TripDB)
            .Where(combined_filter)
            .OrderBy(
                TripDB.pick_up_date.Asc(),
                TripDB.pick_up_time.Asc(),
                TripDB.id.Asc()
            )
            .Limit(limit + 1)
        )

    trips = await session.exec(query).all()

    # Check if there are more results
    has_more = len(trips) > limit
    if has_more:
        trips = trips[:limit]

    # Reverse backward results to maintain chronological order
    if direction == "backward":
        trips = list(reversed(trips))

    # Build response data with is_live computation
    data = []
    for trip in trips:
        trip_dict = model_dump_with_time_format(trip, time_format)
        trip_dict["is_live"] = compute_is_live(
            trip.status,
            trip.pick_up_date,
            trip.pick_up_time,
            location.timezone
        )
        trip_dict["pick_up_time_formatted"] = format_time_for_display(
            trip.pick_up_time,
            use_24h
        )
        data.append(trip_dict)

    # Build pagination info
    pagination = {
        "has_more_forward": has_more if direction == "forward" else True,
        "has_more_backward": has_more if direction == "backward" else True,
        "next_cursor": None,
        "prev_cursor": None
    }

    if data:
        # Next cursor is from the last item (for forward pagination)
        last_trip = trips[-1]
        pagination["next_cursor"] = build_cursor(
            last_trip.pick_up_date,
            last_trip.pick_up_time,
            str(last_trip.id)
        )

        # Prev cursor is from the first item (for backward pagination)
        first_trip = trips[0]
        pagination["prev_cursor"] = build_cursor(
            first_trip.pick_up_date,
            first_trip.pick_up_time,
            str(first_trip.id)
        )

    # Build summary (count live vs history in returned data)
    live_count = sum(1 for d in data if d.get("is_live"))
    history_count = len(data) - live_count

    status_counts = {}
    for d in data:
        s = d.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "location_id": location_id,
        "timezone": location.timezone,
        "current_datetime": current_dt.isoformat(),
        "data": data,
        "pagination": pagination,
        "summary": {
            "live": live_count,
            "history": history_count,
            "by_status": status_counts
        }
    }


@router.patch("/v1/locations/{location_id}/hotels/{hotel_id}")
async def edit_hotel(
    hotel_id: str,
    location_id: str,
    hotel_data: HotelPointUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Actualiza el point y/o radio_zone de un hotel.
    """
    try:
        uuid_hotel_id = UUID(hotel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de hotel inválido")

    try:
        uuid_location_id = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    hotel = await session.get(Hotel, uuid_hotel_id)

    if not hotel:
        raise HTTPException(status_code=404, detail="Hotel no encontrado")

    if hotel.location_id != uuid_location_id:
        raise HTTPException(status_code=404, detail="Hotel no pertenece a esta location")

    if hotel_data.point is not None:
        hotel.point = hotel_data.point
    if hotel_data.radio_zone is not None:
        hotel.radio_zone = hotel_data.radio_zone
    if hotel_data.address is not None:
        hotel.address = hotel_data.address
    if hotel_data.validation_status is not None:
        hotel.validation_status = hotel_data.validation_status

    session.add(hotel)
    await session.commit()
    await session.refresh(hotel)

    return JSONResponse(content={"status": "ok", "hotel": hotel.model_dump(mode="json")})


# =============================================================================
# TRIP DRIVER ASSIGNMENT ENDPOINT
# =============================================================================

@router.patch("/v1/organizations/{organization_id}/locations/{location_id}/trips/{trip_id}/assign")
async def assign_driver_to_trip(
    organization_id: str,
    location_id: str,
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    driver_id: Optional[str] = Query(None, description="ID del driver a asignar (requerido para manager)"),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Asigna un driver a un trip.

    - Manager: Debe pasar driver_id en query param para asignar un driver específico
    - Driver: Se auto-asigna (driver_id se ignora) y marca started_at

    Ejemplo Manager: PATCH /v1/organizations/{org}/locations/{loc}/trips/{trip}/assign?driver_id=uuid
    Ejemplo Driver: PATCH /v1/organizations/{org}/locations/{loc}/trips/{trip}/assign
    """
    from datetime import datetime
    from shared.db.schemas import Driver

    # Validar UUIDs
    try:
        org_uuid = UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de organización inválido")

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    try:
        trip_uuid = UUID(trip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de trip inválido")

    # Obtener datos del usuario autenticado
    user_data = request.state.user_data
    user_id = user_data.get("id")
    user_role = user_data.get("role")
    user_org_id = user_data.get("organization_id")

    # Verificar que el usuario pertenece a la organización
    if str(user_org_id) != organization_id:
        raise HTTPException(status_code=403, detail="No tiene acceso a esta organización")

    # Validar existencia de location y que pertenece a la organización
    location = await session.exec(
        Select(Location).Where(
            (Location.id == location_uuid) &
            (Location.organization_id == org_uuid)
        )
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada en esta organización")

    # Buscar el trip
    trip = await session.exec(
        Select(TripDB).Where(
            (TripDB.id == trip_uuid) &
            (TripDB.location_id == location_uuid)
        )
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip no encontrado")

    # Lógica según rol
    if user_role == "driver":
        # Driver se auto-asigna
        target_driver_id = UUID(user_id)

        # Verificar que el driver existe y pertenece a la organización
        driver = await session.exec(
            Select(Driver).Where(
                (Driver.id == target_driver_id) &
                (Driver.organization_id == org_uuid)
            )
        ).first()

        if not driver:
            raise HTTPException(status_code=404, detail="Driver no encontrado en esta organización")

        # Asignar driver y marcar started_at
        trip.assigned_driver = target_driver_id
        trip.started_at = datetime.now(timezone.utc)
        trip.status = TripStatus.EN_ROUTE

    else:
        # Manager asigna driver específico
        if not driver_id:
            raise HTTPException(status_code=400, detail="driver_id es requerido para managers")

        try:
            target_driver_uuid = UUID(driver_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="ID de driver inválido")

        # Verificar que el driver existe y pertenece a la organización
        driver = await session.exec(
            Select(Driver).Where(
                (Driver.id == target_driver_uuid) &
                (Driver.organization_id == org_uuid)
            )
        ).first()

        if not driver:
            raise HTTPException(status_code=404, detail="Driver no encontrado en esta organización")

        # Solo asignar driver (no marca started_at)
        trip.assigned_driver = target_driver_uuid

    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    time_format = await get_user_time_format(request, session)

    return {
        "status": "ok",
        "data": model_dump_with_time_format(trip, time_format),
        "message": "Driver asignado correctamente" if user_role == "manager" else "Trip iniciado correctamente"
    }


# =============================================================================
# TRIP SEARCH ENDPOINT
# =============================================================================

@router.get("/v1/organizations/{organization_id}/locations/{location_id}/trips/search")
async def search_trips(
    organization_id: str,
    location_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    airline: str = Query(..., description="Código de aerolínea (ej: WN, AA)"),
    date: str = Query(..., description="Fecha de pick up (YYYY-MM-DD)"),
    flight: str = Query(..., description="Número de vuelo"),
    type: str = Query(..., description="Tipo de viaje: inbound o outbound"),
    _role=Depends(verify_role(["manager", "driver", "crew"]))
):
    """
    Busca un viaje específico por aerolínea, fecha, número de vuelo y tipo.

    Ejemplo: /v1/organizations/{org_id}/locations/{loc_id}/trips/search?airline=wn&date=2026-01-01&flight=5468&type=inbound
    """
    from functools import reduce

    # Validar organization_id
    try:
        org_uuid = UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de organización inválido")

    # Validar location_id
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Verificar que el usuario pertenece a la organización
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != organization_id:
        raise HTTPException(status_code=403, detail="No tiene acceso a esta organización")

    # Validar existencia de location y que pertenece a la organización
    location = await session.exec(
        Select(Location).Where(
            (Location.id == location_uuid) &
            (Location.organization_id == org_uuid)
        )
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada en esta organización")

    # Validar tipo de viaje
    if type.lower() not in [TripType.INBOUND, TripType.OUTBOUND, TripType.GROUND]:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de viaje inválido. Valores permitidos: {TripType.INBOUND}, {TripType.OUTBOUND}, {TripType.GROUND}"
        )

    # Convertir fecha
    try:
        from datetime import date as date_type
        pick_up_date_obj = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")

    # Construir filtros
    filters = [
        TripDB.location_id == location_uuid,
        TripDB.airline.ilike(airline.strip()),
        TripDB.pick_up_date == pick_up_date_obj,
        TripDB.flight_number == flight.strip(),
        TripDB.trip_type == type.lower()
    ]

    combined_filter = reduce(lambda a, b: a & b, filters)

    # Buscar el viaje
    trip = await session.exec(
        Select(TripDB).Where(combined_filter)
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    time_format = await get_user_time_format(request, session)

    return {
        "data": model_dump_with_time_format(trip, time_format),
        "location": {
            "id": str(location.id),
            "name": location.name
        }
    }


# ============================================================================
# QR CODE ENDPOINTS (Public - No authentication required)
# ============================================================================

@router.get("/v1/crew-lookup/health")
async def qr_health_check(
    session: AsyncSession = Depends(get_db)
):
    """
    Health check for QR code system.
    Returns table status and count of QR codes.
    Public endpoint for debugging.
    """
    from shared.db.schemas import QRCode

    try:
        # Try to count QR codes to verify table exists and is accessible
        qr_codes = await session.exec(Select(QRCode))

        # Convert to list if it's not already
        if not isinstance(qr_codes, list):
            qr_codes = list(qr_codes) if qr_codes else []

        return {
            "status": "healthy",
            "table_exists": True,
            "qr_codes_count": len(qr_codes),
            "qr_codes": [
                {
                    "id": str(qr.id),
                    "name": qr.name,
                    "status": qr.status,
                    "location_id": str(qr.location_id)
                }
                for qr in qr_codes[:10]  # Limit to 10 for safety
            ]
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "table_exists": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "hint": "The entities.qr_codes table may not exist. Run migrations or create table manually."
        }


@router.get("/v1/crew-lookup/config")
async def get_qr_config(
    qr_id: str = Query(..., description="QR code ID"),
    session: AsyncSession = Depends(get_db)
):
    """
    Get configuration for QR code crew lookup.

    Public endpoint (no authentication required).
    Returns the airlines, location info, and settings for the given QR code.

    Example: /v1/crew-lookup/config?qr_id=123e4567-e89b-12d3-a456-426614174000
    """
    from shared.db.schemas import QRCode, QRCodeStatus

    # Validate QR ID format
    try:
        qr_uuid = UUID(qr_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid QR code ID format")

    # Log the request for debugging
    print(f"[QR-LOOKUP] Searching for QR code: {qr_id}")

    # Get QR code from database
    qr_code = await session.exec(
        Select(QRCode).Where(QRCode.id == qr_uuid)
    ).first()

    if not qr_code:
        # Log for debugging
        print(f"[QR-LOOKUP] QR code NOT FOUND: {qr_id}")

        # Try to get count of all QR codes for debugging
        try:
            all_qrs = await session.exec(Select(QRCode))
            qr_list = all_qrs.all()
            print(f"[QR-LOOKUP] Total QR codes in database: {len(qr_list)}")
            if qr_list:
                print(f"[QR-LOOKUP] Available QR IDs: {[str(qr.id) for qr in qr_list[:5]]}")
        except Exception as e:
            print(f"[QR-LOOKUP] Error counting QR codes: {e}")

        raise HTTPException(
            status_code=404,
            detail="QR code not found. The QR needs to be activated by a manager opening the dashboard first."
        )

    print(f"[QR-LOOKUP] QR code FOUND: {qr_id}, location: {qr_code.location_id}")

    # Check if QR code is disabled
    if qr_code.status == QRCodeStatus.DISABLED:
        raise HTTPException(status_code=403, detail="QR code is disabled")

    # Get location information
    location = await session.exec(
        Select(Location).Where(Location.id == qr_code.location_id)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Get airlines from QR code or derive from location's trips
    airlines = qr_code.airlines
    if not airlines:
        # If QR doesn't have specific airlines, get all airlines from trips at this location
        airlines_stmt = (
            Select(TripDB.airline)
            .Where(TripDB.location_id == qr_code.location_id)
            .Distinct()
        )
        rows = await session.exec(airlines_stmt).all()

        # Extract airline strings from rows (psqlmodel returns Row objects)
        airlines = []
        for row in rows:
            if row is None:
                continue
            # If row is a string, use directly
            if isinstance(row, str):
                airlines.append(row)
            # If row is tuple or has index, extract first element
            elif hasattr(row, '__getitem__'):
                val = row[0] if len(row) > 0 else None
                if val and isinstance(val, str):
                    airlines.append(val)
            # If row has airline attribute
            elif hasattr(row, 'airline'):
                if row.airline:
                    airlines.append(str(row.airline))

    # Update scan count and last scanned time (fire and forget)
    try:
        qr_code.scan_count += 1
        qr_code.last_scanned_at = datetime.now(timezone.utc)
        session.add(qr_code)
        await session.commit()
    except Exception as e:
        # Don't fail the request if analytics update fails
        print(f"Failed to update QR scan analytics: {e}")
        await session.rollback()

    return {
        "qr_id": str(qr_code.id),
        "organization_id": str(qr_code.organization_id),
        "location_id": str(qr_code.location_id),
        "location_name": location.name,
        "airlines": airlines or [],
        "default_trip_type": "outbound",
        "timezone": location.timezone,
        "status": qr_code.status
    }


@router.get("/v1/trips/search/qr")
async def search_trip_qr(
    qr_id: str = Query(..., description="QR code ID"),
    airline: str = Query(..., description="Airline code (e.g., WN, AA)"),
    date: str = Query(..., description="Pickup date (YYYY-MM-DD) in location's timezone"),
    flight: str = Query(..., description="Flight number"),
    type: Optional[str] = Query(None, description="Trip type: inbound, outbound, or ground (optional filter)"),
    session: AsyncSession = Depends(get_db)
):
    """
    Search for a trip using QR code authentication.

    Public endpoint (no authentication required).
    Validates the QR code and searches for the trip within its scope.

    REQUIRED INPUTS (minimum to find a trip):
    - qr_id: The QR code UUID
    - airline: Airline code (WN, AA, DL, etc.)
    - date: Pickup date in YYYY-MM-DD format (interpreted in location's timezone)
    - flight: Flight number

    OPTIONAL:
    - type: Filter by trip type (inbound/outbound/ground)

    BEHAVIOR:
    - If exactly 1 trip matches → returns trip data
    - If multiple trips match → returns list for user to select
    - If no trips match → returns 404

    Example: /v1/trips/search/qr?qr_id=123&airline=WN&date=2026-01-15&flight=5468
    """
    from shared.db.schemas import QRCode, QRCodeStatus

    # Validate QR ID format
    try:
        qr_uuid = UUID(qr_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid QR code ID format")

    # Get and validate QR code
    qr_code = await session.exec(
        Select(QRCode).Where(QRCode.id == qr_uuid)
    ).first()

    if not qr_code:
        raise HTTPException(status_code=404, detail="QR code not found")

    if qr_code.status == QRCodeStatus.DISABLED:
        raise HTTPException(status_code=403, detail="QR code is disabled")

    # Validate that airline is allowed for this QR code
    if qr_code.airlines and airline.upper() not in [a.upper() for a in qr_code.airlines]:
        raise HTTPException(
            status_code=403,
            detail=f"Airline {airline} is not allowed for this QR code"
        )

    # Validate trip type if provided
    if type and type.lower() not in [TripType.INBOUND, TripType.OUTBOUND, TripType.GROUND]:
        raise HTTPException(
            status_code=400,
            detail="Invalid trip type. Must be inbound, outbound, or ground"
        )

    # Validate date format
    try:
        pickup_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    # Normalize airline and flight number
    airline_normalized = airline.strip().upper()
    flight_normalized = flight.strip()

    # Get location info first (needed for timezone)
    location = await session.exec(
        Select(Location).Where(Location.id == qr_code.location_id)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Build query for trips - combine conditions with &
    base_condition = (
        (TripDB.location_id == qr_code.location_id) &
        (TripDB.airline == airline_normalized) &
        (TripDB.flight_number == flight_normalized) &
        (TripDB.pick_up_date == pickup_date)
    )

    # Add type filter if provided
    if type:
        base_condition = base_condition & (TripDB.trip_type == type.lower())

    # Search for trips matching criteria
    trips = await session.exec(
        Select(TripDB).Where(base_condition).OrderBy(TripDB.pick_up_time)
    ).all()

    if not trips:
        raise HTTPException(status_code=404, detail="No trips found matching criteria")

    def format_trip_response(trip):
        """Format a single trip for response."""
        # Normalize riders data (handle old typo format and new format)
        riders_data = {"pilots": 0, "flight_attendants": 0}
        if trip.riders:
            if "pilots" in trip.riders and "flight_attendants" in trip.riders:
                riders_data = trip.riders
            elif "fligth" in trip.riders or "in_fligth" in trip.riders:
                riders_data = {
                    "pilots": trip.riders.get("fligth", 0),
                    "flight_attendants": trip.riders.get("in_fligth", 0)
                }

        return {
            "id": str(trip.id),
            "pick_up_time": trip.pick_up_time.strftime("%H:%M"),
            "pick_up_location": trip.pick_up_location,
            "drop_off_location": trip.drop_off_location,
            "airline": trip.airline,
            "flight_number": trip.flight_number,
            "trip_type": trip.trip_type,
            "status": trip.status,
            "riders": riders_data
        }

    # Update scan count for analytics
    qr_code.scan_count = (qr_code.scan_count or 0) + 1
    qr_code.last_scanned_at = datetime.utcnow()
    session.add(qr_code)
    await session.commit()

    # Build response with location context
    response_base = {
        "location": {
            "id": str(location.id),
            "name": location.name,
            "timezone": location.timezone  # Document timezone for date interpretation
        },
        "query": {
            "airline": airline_normalized,
            "flight_number": flight_normalized,
            "date": date,
            "type_filter": type
        }
    }

    # If exactly 1 trip, return it directly
    if len(trips) == 1:
        return {
            **response_base,
            "data": format_trip_response(trips[0]),
            "multiple_results": False
        }

    # If multiple trips, return list for user selection
    return {
        **response_base,
        "data": [format_trip_response(t) for t in trips],
        "multiple_results": True,
        "message": f"Found {len(trips)} trips. Please select one or add type filter (inbound/outbound/ground)."
    }


# ============================================================================
# QR CODE MANAGEMENT ENDPOINTS (Authentication required)
# ============================================================================

@router.get("/v1/organizations/{organization_id}/qr-codes")
async def list_organization_qr_codes(
    organization_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    List all QR codes for an organization with their associated locations.

    Returns all QR codes (one per location) that belong to this organization.
    Includes location information for each QR code.

    Response includes:
    - QR codes that already exist
    - Location info (name, id) for each QR
    - QR URL ready for display
    """
    from shared.db.schemas import QRCode

    # Validate UUID
    try:
        org_uuid = UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format")

    # Verify user has access to this organization
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != organization_id:
        raise HTTPException(status_code=403, detail="No access to this organization")

    # Get all locations for this organization
    locations = await session.exec(
        Select(Location).Where(Location.organization_id == org_uuid)
    ).all()

    # Get all QR codes for this organization
    qr_codes = await session.exec(
        Select(QRCode).Where(QRCode.organization_id == org_uuid)
    ).all()

    # Create a map of location_id -> qr_code for easy lookup
    qr_by_location = {str(qr.location_id): qr for qr in qr_codes}

    # Build response with locations and their QR codes
    result = []
    for location in locations:
        loc_id_str = str(location.id)
        qr = qr_by_location.get(loc_id_str)

        location_data = {
            "location_id": loc_id_str,
            "location_name": location.name,
            "qr_code": None
        }

        if qr:
            location_data["qr_code"] = {
                "id": str(qr.id),
                "name": qr.name,
                "airlines": qr.airlines,
                "status": qr.status,
                "qr_url": f"https://web.gt360.app/crew-lookup?qr={qr.id}",
                "scan_count": qr.scan_count,
                "last_scanned_at": qr.last_scanned_at.isoformat() if qr.last_scanned_at else None,
                "created_at": qr.created_at.isoformat(),
                "updated_at": qr.updated_at.isoformat()
            }

        result.append(location_data)

    return {
        "organization_id": organization_id,
        "total_locations": len(locations),
        "total_qr_codes": len(qr_codes),
        "locations": result
    }


@router.get("/v1/organizations/{organization_id}/locations/{location_id}/qr-code")
async def get_qr_code(
    organization_id: str,
    location_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Get the QR code for a specific location.

    Each location has exactly ONE QR code (1:1 relationship).
    Returns 404 if no QR code exists for this location yet.
    Use POST to create the QR code if it doesn't exist.
    """
    from shared.db.schemas import QRCode

    # Validate UUIDs
    try:
        org_uuid = UUID(organization_id)
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Verify user has access to this organization
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != organization_id:
        raise HTTPException(status_code=403, detail="No access to this organization")

    # Verify location belongs to organization
    location = await session.exec(
        Select(Location).Where(
            (Location.id == loc_uuid) &
            (Location.organization_id == org_uuid)
        )
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found in this organization")

    # Get the QR code for this location (exactly 1 per location)
    qr_code = await session.exec(
        Select(QRCode).Where(QRCode.location_id == loc_uuid)
    ).first()

    if not qr_code:
        raise HTTPException(
            status_code=404,
            detail="No QR code exists for this location. Use POST to create one."
        )

    return {
        "id": str(qr_code.id),
        "organization_id": str(qr_code.organization_id),
        "location_id": str(qr_code.location_id),
        "name": qr_code.name,
        "airlines": qr_code.airlines,
        "status": qr_code.status,
        "qr_url": f"https://web.gt360.app/crew-lookup?qr={qr_code.id}",
        "scan_count": qr_code.scan_count,
        "last_scanned_at": qr_code.last_scanned_at.isoformat() if qr_code.last_scanned_at else None,
        "created_at": qr_code.created_at.isoformat(),
        "updated_at": qr_code.updated_at.isoformat()
    }


@router.post("/v1/organizations/{organization_id}/locations/{location_id}/qr-code")
async def get_or_create_qr_code(
    organization_id: str,
    location_id: str,
    qr_data: CreateQRCode,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Get or create the QR code for a location (idempotent).

    LOGIC:
    - If QR already exists for this location → returns existing QR (status 200)
    - If no QR exists → creates new QR with frontend-provided UUID (status 201)

    Each location has exactly ONE QR code (1:1 relationship).
    The QR URL is stable and never changes once created.

    IMPORTANT: The UUID comes from the frontend (crypto.randomUUID()).
    This allows the QR code to be displayed immediately in the UI.
    """
    from shared.db.schemas import QRCode, QRCodeStatus

    # Validate UUIDs
    try:
        org_uuid = UUID(organization_id)
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Verify user has access to this organization
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != organization_id:
        raise HTTPException(status_code=403, detail="No access to this organization")

    # Verify location belongs to organization
    location = await session.exec(
        Select(Location).Where(
            (Location.id == loc_uuid) &
            (Location.organization_id == org_uuid)
        )
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found in this organization")

    # Check if QR already exists for this location (1:1 relationship)
    existing_qr = await session.exec(
        Select(QRCode).Where(QRCode.location_id == loc_uuid)
    ).first()

    if existing_qr:
        # Return existing QR (idempotent) with 200 status
        response.status_code = 200
        return {
            "id": str(existing_qr.id),
            "organization_id": str(existing_qr.organization_id),
            "location_id": str(existing_qr.location_id),
            "name": existing_qr.name,
            "airlines": existing_qr.airlines,
            "status": existing_qr.status,
            "qr_url": f"https://web.gt360.app/crew-lookup?qr={existing_qr.id}",
            "scan_count": existing_qr.scan_count,
            "last_scanned_at": existing_qr.last_scanned_at.isoformat() if existing_qr.last_scanned_at else None,
            "created_at": existing_qr.created_at.isoformat(),
            "updated_at": existing_qr.updated_at.isoformat(),
            "created": False  # Indicates this was already existing
        }

    # Create new QR code with frontend-provided UUID
    qr_code = QRCode(
        id=qr_data.id,  # UUID from frontend
        organization_id=org_uuid,
        location_id=loc_uuid,
        name=qr_data.name or f"QR - {location.name}",
        airlines=qr_data.airlines,
        status=QRCodeStatus.ACTIVE,
        metadata=qr_data.metadata,
        scan_count=0
    )

    session.add(qr_code)

    try:
        await session.commit()
        await session.refresh(qr_code)
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to create QR code: {str(e)}")

    # Return new QR code with 201 status
    response.status_code = 201
    return {
        "id": str(qr_code.id),
        "organization_id": str(qr_code.organization_id),
        "location_id": str(qr_code.location_id),
        "name": qr_code.name,
        "airlines": qr_code.airlines,
        "status": qr_code.status,
        "qr_url": f"https://web.gt360.app/crew-lookup?qr={qr_code.id}",
        "scan_count": qr_code.scan_count,
        "last_scanned_at": qr_code.last_scanned_at.isoformat() if qr_code.last_scanned_at else None,
        "created_at": qr_code.created_at.isoformat(),
        "updated_at": qr_code.updated_at.isoformat(),
        "created": True  # Indicates this was newly created
    }
