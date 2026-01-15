#!/usr/bin/env python3
"""
Simula el proceso completo de upload del archivo SDF December.xls
para identificar exactamente dónde falla
"""
import sys
import asyncio
from pathlib import Path
from datetime import timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))

from psqlmodel import Select, AsyncSession
from shared.db.schemas import User, Manager, Organization, Location, Airport, Trip as TripDB, Hotel
from shared.db.db_config import engine
from features.trips.utils.trip_importer import load_trips_from_bytes
from features.trips.utils import tz_from_latlon


async def simulate_upload():
    """Simula el proceso completo de upload"""

    print("=" * 80)
    print("SIMULACIÓN DE UPLOAD DE SDF DECEMBER.XLS")
    print("=" * 80)
    print()

    # Parámetros
    email = "carlitoleo10@gmail.com"
    airport_code = "SDF"
    airline = "WN"
    provider = "api"
    file_path = "docs/Docs_From_Frontend/Sdf December .xls"

    print(f"Usuario: {email}")
    print(f"Airport: {airport_code}")
    print(f"Airline: {airline}")
    print(f"Provider: {provider}")
    print(f"File: {file_path}")
    print()

    # Leer archivo
    print("1. Leyendo archivo...")
    with open(file_path, "rb") as f:
        content = f.read()
    print(f"   ✓ Archivo leído: {len(content)} bytes")
    print()

    # Crear sesión
    async with AsyncSession(engine) as session:
        try:
            # Obtener usuario y organización
            print("2. Buscando usuario y organización...")
            user = await session.exec(
                Select(User).Where(User.email == email.lower())
            ).first()

            if not user:
                print(f"   ❌ Usuario no encontrado")
                return

            manager = await session.exec(
                Select(Manager).Where(Manager.id == user.id)
            ).first()

            if not manager:
                print(f"   ❌ Manager no encontrado")
                return

            organization = await session.exec(
                Select(Organization).Where(Organization.id == manager.organization_id)
            ).first()

            if not organization:
                print(f"   ❌ Organización no encontrada")
                return

            print(f"   ✓ Usuario: {user.id}")
            print(f"   ✓ Organización: {organization.id}")
            print(f"   ✓ Plan: {organization.plan}")
            print()

            # Procesar Excel
            print("3. Procesando Excel...")
            try:
                trips_import = await load_trips_from_bytes(
                    content,
                    location=airport_code,
                    plan=organization.plan,
                    airlinex=airline
                )
                print(f"   ✓ Trips procesados: {len(trips_import)}")
            except Exception as e:
                print(f"   ❌ Error al procesar Excel: {e}")
                import traceback
                traceback.print_exc()
                return
            print()

            # Buscar aeropuerto
            print("4. Buscando aeropuerto...")
            airport_db = await session.exec(
                Select(Airport).Where(Airport.code == airport_code.upper())
            ).first()

            if not airport_db:
                print(f"   ❌ Aeropuerto no encontrado: {airport_code}")
                return

            print(f"   ✓ Aeropuerto: {airport_db.name}")
            print(f"   ✓ Coordenadas: ({airport_db.latitude}, {airport_db.longitude})")
            print()

            # Buscar o crear location
            print("5. Buscando/creando location...")
            location = await session.exec(
                Select(Location).Where(
                    (Location.name == airport_code) &
                    (Location.organization_id == organization.id)
                )
            ).first()

            if not location:
                print(f"   → Location no existe, creando...")
                location = Location(
                    organization_id=organization.id,
                    name=airport_code,
                    point={
                        "type": "Point",
                        "coordinates": [
                            float(airport_db.longitude),
                            float(airport_db.latitude)
                        ]
                    },
                    radio_zone=0.0,
                    provider=provider,
                    timezone=tz_from_latlon(float(airport_db.latitude), float(airport_db.longitude))
                )
                session.add(location)
                await session.flush()
                await session.refresh(location)
                print(f"   ✓ Location creada: {location.id}")
            else:
                print(f"   ✓ Location existente: {location.id}")

            print(f"   ✓ Timezone: {location.timezone}")
            print()

            # Preparar trips para insertar
            print("6. Preparando trips para insertar...")
            location_tz = ZoneInfo(location.timezone) if location.timezone else ZoneInfo("America/New_York")

            trips_to_create = []
            hotels_set = set()

            for t in trips_import:
                pick_up_time_local = t.pick_up_time.replace(tzinfo=location_tz)
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
                )
                trips_to_create.append(db_trip)

                # Guardar nombres de hoteles únicos
                if db_trip.pick_up_location.upper() != location.name.upper():
                    hotels_set.add(db_trip.pick_up_location.strip())
                if db_trip.drop_off_location.upper() != location.name.upper():
                    hotels_set.add(db_trip.drop_off_location.strip())

            print(f"   ✓ Trips preparados: {len(trips_to_create)}")
            print(f"   ✓ Hoteles únicos: {len(hotels_set)}")
            print()

            # AQUÍ ESTÁ EL PUNTO CRÍTICO - Insertar en DB
            print("7. Insertando en base de datos...")
            print("   → Ejecutando BulkInsert...")

            try:
                # Procesar en chunks
                chunk_size = 5000
                for i in range(0, len(trips_to_create), chunk_size):
                    batch = trips_to_create[i : i + chunk_size]
                    print(f"   → Insertando batch {i//chunk_size + 1} ({len(batch)} trips)...")

                    # [FIXED] BulkInsert sin .Returning() para evitar el bug de psqlmodel
                    await session.BulkInsert(batch)
                    print(f"   ✓ Batch insertado correctamente")

                print()
                print(f"   ✓ TODOS LOS TRIPS INSERTADOS CORRECTAMENTE")
                print()

                # Obtener los primeros 50 trips para verificar
                print("   → Obteniendo los primeros 50 trips para verificar...")
                trips_stmt = (
                    Select(TripDB)
                    .Where(TripDB.location_id == location.id)
                    .OrderBy(TripDB.pick_up_date.Asc(), TripDB.pick_up_time.Asc())
                    .Limit(50)
                )
                trips_objs = await session.exec(trips_stmt).all()
                print(f"   ✓ Verificación exitosa: {len(trips_objs)} trips retornados")
                print()

                # Insertar hoteles
                print("8. Insertando hoteles...")
                if hotels_set:
                    # Consultar hoteles existentes
                    existing_hotels_stmt = Select(Hotel.name).Where(Hotel.location_id == location.id)
                    existing_hotels_rows = await session.exec(existing_hotels_stmt).all()
                    existing_hotel_names = set()
                    for row in existing_hotels_rows:
                        try:
                            existing_hotel_names.add(row[0])
                        except (TypeError, IndexError, KeyError):
                            existing_hotel_names.add(row)

                    new_hotels = {h for h in hotels_set if h not in existing_hotel_names}

                    if new_hotels:
                        print(f"   → Insertando {len(new_hotels)} hoteles nuevos...")
                        hotel_objects = [Hotel(name=name, location_id=location.id) for name in new_hotels]
                        # [FIXED] BulkInsert sin .Returning()
                        await session.BulkInsert(hotel_objects)
                        print(f"   ✓ Hoteles insertados: {len(new_hotels)}")
                    else:
                        print(f"   → Todos los hoteles ya existen")
                else:
                    print(f"   → No hay hoteles para insertar")
                print()

                # Commit
                print("9. Commiteando transacción...")
                await session.commit()
                print("   ✓ COMMIT EXITOSO")
                print()

                print("=" * 80)
                print("✓ ¡SIMULACIÓN EXITOSA!")
                print("=" * 80)

            except Exception as e:
                print(f"\n❌ ERROR AL INSERTAR EN BASE DE DATOS:")
                print(f"   Tipo: {type(e).__name__}")
                print(f"   Mensaje: {str(e)}")
                print()
                import traceback
                traceback.print_exc()
                await session.rollback()

        except Exception as e:
            print(f"\n❌ ERROR GENERAL:")
            print(f"   Tipo: {type(e).__name__}")
            print(f"   Mensaje: {str(e)}")
            print()
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(simulate_upload())
