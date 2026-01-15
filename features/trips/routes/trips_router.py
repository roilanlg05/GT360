from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends, Request, Response
from fastapi.responses import JSONResponse
from shared.db.db_config import get_db
from psqlmodel import Select, Count, Delete, AsyncSession
from sqlalchemy import func, text
from shared.db.schemas import Trip as TripDB, Location, Airport, Organization, Hotel
from features.trips.utils.trip_importer import load_trips_from_bytes
from features.trips.models import TripUpdate, CreateTrip, LocationZoneUpdate, HotelPointUpdate
from features.trips.models.filter_models import (
    FilterRequest,
    FilterPreviewResult,
    FilterApplyResult,
    FilterRevertResult,
)
from features.trips.services.trip_filter_service import TripFilterService
from datetime import date, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from uuid import UUID
from features.auth.utils import verify_role
from features.trips.utils import get_locations_by_org_id, tz_from_latlon
from features.trips.utils.trip_classifier import classify_trip_type
from shared.db.schemas import TripType, TripStatus
from shared.redis.redis_client import redis_client as redis
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

    # Crear los trips
   
    created = 0
    trips_to_create = []
    trips = []
    hotels_set = set()
    hotels_result = []

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
            await session.execute(text("SET LOCAL app.batch_insert_mode = 'true'"))

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
            # Serializar trips a JSON (convierte UUIDs a strings)
            trips = [t.model_dump(mode="json") for t in trips_objs]

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
            await redis.publish(
                f"loc:{location.id}",
                json.dumps(batch_event)
            )

            # También publicar al canal org para usuarios conectados a /ws/org
            if hasattr(location, 'organization_id') and location.organization_id:
                await redis.publish(
                    f"org:{location.organization_id}",
                    json.dumps(batch_event)
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

        trip = TripDB(location_id=location_uuid, **trip_payload)
        session.add(trip)
        # flush para obtener ids y validar DB antes del commit
        await session.flush()

        # commit dentro del try: si algo falla después (p. ej. serialización), entra en except
        await session.commit()
        await session.refresh(trip)

        trip_json = trip.model_dump(mode="json")
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
    limit: int = Query(20, ge=1, le=50),
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

    for row in rows:
        trips.append(row[0].model_dump(mode="json"))

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
    trip = trip.model_dump(mode="json")

    print("TRIP UPDATED: ", trip)
    
    return JSONResponse(content={"status": "ok", "trip": trip})



@router.get("/v1/locations")
async def get_locations(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    metadata = request.state.user_data
    org_id = metadata.get("organization_id")
    
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
    await redis.publish(f"org:{org_id}", start_event_json)
    await redis.publish(f"loc:{location_id}", start_event_json)

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
    await redis.publish(f"org:{org_id}", deleted_event_json)
    await redis.publish(f"loc:{location_id}", deleted_event_json)

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
    query = """
        SELECT
            EXTRACT(YEAR FROM pick_up_date)::int AS year,
            EXTRACT(MONTH FROM pick_up_date)::int AS month,
            COUNT(*)::int AS trips_count
        FROM trips.trips
        WHERE location_id = :location_id
    """

    params = {"location_id": location_uuid}

    if airline:
        query += " AND airline ILIKE :airline"
        params["airline"] = f"%{airline}%"

    query += """
        GROUP BY year, month
        ORDER BY year DESC, month DESC
    """

    # Ejecutar query raw SQL usando la engine directamente
    from shared.db.db_config import engine

    async with engine.begin() as conn:
        result = await conn.execute(text(query), params)
        rows = result.fetchall()

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
# TRIP FILTERS ENDPOINTS (Reduce, Combine, Expand)
# =============================================================================

@router.post("/v1/locations/{location_id}/airlines/{airline}/trips/filters/preview")
async def preview_filters(
    location_id: str,
    airline: str,
    filters: FilterRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterPreviewResult:
    """
    Simula los filtros y retorna los cambios propuestos sin aplicarlos.

    Solo aplica a trips:
    - trip_type = OUTBOUND
    - status = SCHEDULED
    - Con el airline especificado

    Filtros disponibles:
    - reduce: Resta minutos fijos al pickup_time
    - combine: Mueve pares de trips a su punto medio
    - expand: Separa pares de trips respetando No-Collision Rule

    Todos los resultados se redondean a múltiplos de 5 minutos.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar airline
    airline = airline.strip().upper()
    if not airline or len(airline) < 2:
        raise HTTPException(status_code=400, detail="Airline inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    service = TripFilterService(session)
    result = await service.preview(location_uuid, airline, filters)

    return result


@router.post("/v1/locations/{location_id}/airlines/{airline}/trips/filters/apply")
async def apply_filters(
    location_id: str,
    airline: str,
    filters: FilterRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterApplyResult:
    """
    Aplica los filtros a los trips Outbound con status SCHEDULED y persiste los cambios.

    Solo aplica a trips:
    - trip_type = OUTBOUND
    - status = SCHEDULED
    - Con el airline especificado

    Solo modifica el campo pickup_time. Guarda el valor original para permitir
    revertir los cambios posteriormente.

    Reglas aplicadas:
    - Regla A: Un trip modificado no se vuelve a modificar en la misma corrida
    - Regla B: No-Collision Rule - Expand no crea gaps que caigan en rango de Combine
    - Todos los resultados se redondean a múltiplos de 5 minutos

    Returns:
        FilterApplyResult con batch_id para revertir, conteo de cambios y log detallado
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar airline
    airline = airline.strip().upper()
    if not airline or len(airline) < 2:
        raise HTTPException(status_code=400, detail="Airline inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    service = TripFilterService(session)
    result = await service.apply(location_uuid, airline, filters)

    return result


@router.post("/v1/locations/{location_id}/airlines/{airline}/trips/filters/revert")
async def revert_filters(
    location_id: str,
    airline: str,
    batch_id: Optional[str] = Query(None, description="ID del batch a revertir. Si es None, revierte todos."),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterRevertResult:
    """
    Revierte filtros aplicados, restaurando el pickup_time original.

    Args:
        location_id: ID de la location
        airline: Código de aerolínea (ej: WN, AA)
        batch_id: Si se proporciona, solo revierte trips de ese batch.
                  Si es None, revierte todos los trips filtrados de la location+airline.

    Returns:
        FilterRevertResult con conteo de trips revertidos
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar airline
    airline = airline.strip().upper()
    if not airline or len(airline) < 2:
        raise HTTPException(status_code=400, detail="Airline inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    batch_uuid = None
    if batch_id:
        try:
            batch_uuid = UUID(batch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="ID de batch inválido")

    service = TripFilterService(session)
    result = await service.revert(location_uuid, airline, batch_uuid)

    return result


