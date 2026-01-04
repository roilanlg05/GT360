from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends, Request, Response
from fastapi.responses import JSONResponse
from shared.db.db_config import get_db
from psqlmodel import Select, Count, Delete, AsyncSession
from shared.db.schemas import Trip as TripDB, Location, Airport, Organization, Hotel
from features.trips.utils.trip_importer import load_trips_from_bytes
from features.trips.models import TripUpdate, CreateTrip, LocationZoneUpdate, HotelPointUpdate
from datetime import date, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from features.auth.utils import verify_role
from features.trips.utils import get_locations_by_org_id, tz_from_latlon



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

    # Leer el contenido del archivo
    content = await file.read()

    # Cargar viajes desde el Excel (función asíncrona)
    try:
        trips_import = await load_trips_from_bytes(content, location=airport, plan=organization.plan, airlinex=airline)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
        location_tz = ZoneInfo(location.timezone)
        
        # 1. Construir la lista de objetos en memoria (rápido)
        for t in trips_import:
            # El pick_up_time del Excel viene como hora local, reemplazar tzinfo con el tz correcto
            pick_up_time_local = t.pick_up_time.replace(tzinfo=location_tz)
            
            db_trip = TripDB(
                location_id=location.id,
                pick_up_date=t.pick_up_date,
                pick_up_time=pick_up_time_local,
                pick_up_location=t.pick_up_location,
                drop_off_location=t.drop_off_location,
                airline=t.airline,
                flight_number=t.flight_number,
                riders=t.riders,
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
            # Procesar en chunks si son miles (ej. 5000) para no saturar la consulta
            chunk_size = 5000
            for i in range(0, len(trips_to_create), chunk_size):
                batch = trips_to_create[i : i + chunk_size]
                
                # [NUEVO] Usar BulkInsert (PascalCase) para máxima velocidad.
                trips_objs = (
                    await session.BulkInsert(batch)
                        .Returning(TripDB)
                        .OrderBy(
                            TripDB.pick_up_date,
                            TripDB.pick_up_time
                        )
                        .Asc()
                        .Limit(50)
                        .all()
                )
                # Serializar trips a JSON (convierte UUIDs a strings)
                trips = [t.model_dump(mode="json") for t in trips_objs]

            # Convertir nombres de hoteles a objetos Hotel y hacer bulk insert
            if hotels_set:
                hotel_objects = [Hotel(name=name, location_id=location.id) for name in hotels_set]
                hotels_objs = await session.BulkInsert(hotel_objects).Returning(Hotel).all()
                # Serializar hoteles a JSON (convierte UUIDs a strings)
                hotels_result = [h.model_dump(mode="json") for h in hotels_objs]

        # Confirmar la transacción solo si todo salió bien
        await session.commit()

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
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    _role=Depends(verify_role(["manager"]))
):

    """
    Obtiene una lista paginada de trips.
    """

    # Construir condiciones dinámicas según parámetros opcionales
    filters = [TripDB.location_id == location_id]
    # filtros exactos
    if pick_up_date:
        filters.append(TripDB.pick_up_date == pick_up_date)
    if pick_up_time:
        filters.append(TripDB.pick_up_time == pick_up_time)
    # filtros rango
    if pick_up_date_from:
        filters.append(TripDB.pick_up_date >= pick_up_date_from)
    if pick_up_date_to:
        filters.append(TripDB.pick_up_date <= pick_up_date_to)
    if pick_up_time_from:
        filters.append(TripDB.pick_up_time >= pick_up_time_from)
    if pick_up_time_to:
        filters.append(TripDB.pick_up_time <= pick_up_time_to)
    # filtros texto
    if pick_up_location:
        filters.append(TripDB.pick_up_location.ilike(f"%{pick_up_location}%"))
    if drop_off_location:
        filters.append(TripDB.drop_off_location.ilike(f"%{drop_off_location}%"))
    if airline:
        filters.append(TripDB.airline.ilike(f"%{airline}%"))
    if flight_number:
        filters.append(TripDB.flight_number == flight_number)
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

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No trips matching your filters or search criteria."
        )
    
    trips=[]
    
    for row in rows:
        trips.append(row[0].model_dump(mode="json"))
    
    total = rows[0][1] if rows else 0

    return {
        "data": trips,
        "skip": skip,
        "limit": limit,
        "total": total
    }

@router.delete("/v1/locations/{location_id}/trips")
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


@router.delete("/v1/locations/{location_id}/trips/{trip_id}")
async def delete_trip(
    location_id: str,
    trip_id: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Elimina un trip por su ID y location_id.
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
    
    # Comprobar existencia del trip
    sel_stmt = Select(TripDB).Where((TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id))
    trip = await session.exec(sel_stmt).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip no encontrado")

    # Eliminar y commitear
    del_stmt = Delete(TripDB).Where((TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id))
    await session.exec(del_stmt)
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
        .Join(Location, TripDB.location_id == Location.id)
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

    for key, value in update_data.items():
        setattr(trip, key, value)

    session.add(trip)

    await session.commit()
    trip = trip.model_dump(mode="json")

    print("TRIP UPDATED: ", trip)
    
    return JSONResponse(content={"status": "ok", "trip": trip})

@router.get("/v1/locations")
async def get_locations(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    metadata = request.state.user_data
    org_id = metadata.get("organization_id")
    
    locations = await get_locations_by_org_id(session, org_id)

    return JSONResponse(status_code=200, content={"data": locations})

@router.delete("/v1/locations/{location_id}")
async def delete_location(
    location_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    await session.exec(
        Delete(Location)
        .Where(Location.id == location_id)
    )

    await session.commit()

    return JSONResponse(status_code=200, content={"data": f"Location {location_id} deleted successfully"})


@router.patch("/v1/locations/{location_id}")
async def edit_location(
    location_id: str,
    location_data: LocationZoneUpdate,
    session: AsyncSession = Depends(get_db),
    _role = Depends(verify_role(["manager", "driver"]))
    ):

    location = await session.get(Location, location_id)

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    if location_data.point is not None:
        location.point = location_data.point
    if location_data.radio_zone is not None:
        location.radio_zone = location_data.radio_zone

    session.add(location)
    await session.commit()

    return JSONResponse(content={"status": "ok", "location": location.model_dump(mode="json")})

@router.patch("/v1/hotels/{hotel_id}")
async def edit_hotel(
    hotel_id: str,
    hotel_data: HotelPointUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Actualiza el point y/o radio_zone de un hotel.
    """
    from uuid import UUID

    try:
        uuid_hotel_id = UUID(hotel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de hotel inválido")

    hotel = await session.get(Hotel, uuid_hotel_id)

    if not hotel:
        raise HTTPException(status_code=404, detail="Hotel no encontrado")

    if hotel_data.point is not None:
        hotel.point = hotel_data.point
    if hotel_data.radio_zone is not None:
        hotel.radio_zone = hotel_data.radio_zone
    if hotel_data.address is not None:
        hotel.address = hotel_data.address

    session.add(hotel)
    await session.commit()
    await session.refresh(hotel)

    return JSONResponse(content={"status": "ok", "hotel": hotel.model_dump(mode="json")})


