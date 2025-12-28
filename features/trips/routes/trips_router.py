from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends, Request, Response
from fastapi.responses import JSONResponse
from shared.db import get_db
from psqlmodel import Select, Count, Delete, AsyncSession
from features.trips.schemas import Trip as TripDB, Location, Airport, Organization
from features.trips.utils.trip_importer import load_trips_from_bytes
from features.trips.models import TripUpdate, CreateTrip
from datetime import date, time, timezone
from typing import Optional
from features.auth.utils import verify_role
from features.trips.utils import get_locations_by_org_id



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

    if not location:
        # Crear Location
        location = Location(
            organization_id=organization.id,
            name=airport,
            point=
            {
            "type": "Point", 
            "coordinates": [
                airportdb.longitude, 
                airportdb.latitude
                ]
            }
        )
    
    session.add(location)
    await session.flush()
    await session.refresh(location)

    # Crear los trips
    created = 0
    try:
        for t in trips_import:
            db_trip = TripDB(
                location_id=location.id,
                pick_up_date=t.pick_up_date,
                pick_up_time=t.pick_up_time,
                pick_up_location=t.pick_up_location,
                drop_off_location=t.drop_off_location,
                airline=t.airline,
                flight_number=t.flight_number,
                riders=t.riders,
            )
            session.add(db_trip)
            created += 1

        await session.commit()

    except Exception as e:
        msg = str(e)
        if "DETAIL:" in msg:
            msg = msg.split("DETAIL:", 1)[1].strip()
        raise HTTPException(
            status_code=422,
            detail=f"We couldn't validate the schedule: {msg}"
        )
    
    trips_stmt = (
        Select(TripDB)
        .OrderBy(
            TripDB.pick_up_date,
            TripDB.pick_up_time
        )
        .Asc()
        .Limit(10)
    )
    trips = await session.exec(trips_stmt).to_dicts()

    return {
        "status": "ok",
        "uploaded_rows": created,
        "location_id": str(location.id),
        "airport_code": airport,
        "trips": trips
    }

@router.post("/v1/locations/{location_id}/trips")
async def create_trip(
    location_id: str,
    trip_data: CreateTrip,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
    ):

    
    try:
        from uuid import UUID
        location_id = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")
    
    try:
        # Ensure pick_up_date/time are proper Python date/time objects before saving.
        # If they arrive as ISO strings, parse them; otherwise keep as-is.
        trip_payload = trip_data.model_dump(exclude_unset=True)
        # parse ISO date string -> date
        if "pick_up_date" in trip_payload and isinstance(trip_payload.get("pick_up_date"), str):
            trip_payload["pick_up_date"] = date.fromisoformat(trip_payload["pick_up_date"])
        # parse ISO time string -> time
        if "pick_up_time" in trip_payload and isinstance(trip_payload.get("pick_up_time"), str):
            trip_payload["pick_up_time"] = time.fromisoformat(trip_payload["pick_up_time"])
        # Ensure timezone-aware time for DB (column is TIME WITH TIME ZONE)
        if "pick_up_time" in trip_payload and isinstance(trip_payload.get("pick_up_time"), time) and trip_payload["pick_up_time"].tzinfo is None:
            trip_payload["pick_up_time"] = trip_payload["pick_up_time"].replace(tzinfo=timezone.utc)
        
        trip = TripDB(
            location_id=location_id, 
            **trip_payload
        )

        session.add(trip)
        
        await session.commit()

        trip.model_dump(mode="json")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return JSONResponse(status_code=200, content={"data": trip})
    

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

    # Comprobar existencia del trip
    sel_stmt = Select(TripDB).Where((TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id))
    trip = await session.exec(sel_stmt).first()
    if trip:
        print("Psqlmodel:", trip) #[0].model_dump(mode="json")
    else:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Actualizar datos del trip: parsear strings ISO a date/time si es necesario
    update_data = trip_update.model_dump(exclude_unset=True)
    if "pick_up_date" in update_data and isinstance(update_data.get("pick_up_date"), str):
        update_data["pick_up_date"] = date.fromisoformat(update_data["pick_up_date"])
    if "pick_up_time" in update_data and isinstance(update_data.get("pick_up_time"), str):
        update_data["pick_up_time"] = time.fromisoformat(update_data["pick_up_time"])
    # Ensure timezone-aware time for DB (column is TIME WITH TIME ZONE)
    if "pick_up_time" in update_data and isinstance(update_data.get("pick_up_time"), time) and update_data["pick_up_time"].tzinfo is None:
        update_data["pick_up_time"] = update_data["pick_up_time"].replace(tzinfo=timezone.utc)

    for key, value in update_data.items():
        setattr(trip, key, value)

    await session.commit()
    trip = trip.model_dump(mode="json")
    
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

    return JSONResponse(status_code=200, content={"data": f"Location {location_id} deleted successfully"})

