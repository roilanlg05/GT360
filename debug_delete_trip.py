"""
Script de diagnóstico para el error DELETE /trips/{trip_id}

Ejecuta este script para diagnosticar el problema:
  python debug_delete_trip.py
"""
import asyncio
from uuid import UUID
from shared.db.db_config import get_db
from psqlmodel import Select, Delete
from shared.db.schemas import Trip as TripDB

async def debug_delete_trip():
    """Diagnóstico del error en DELETE trip"""

    trip_id = "b76d6021-77a7-4b58-a9e7-a50c4ba12f03"
    location_id = "f44b67e9-95ce-4c02-a3e2-bd1ffcfc8747"

    try:
        uuid_id = UUID(trip_id)
        uuid_location_id = UUID(location_id)
        print(f"✓ UUIDs válidos:")
        print(f"  trip_id: {uuid_id}")
        print(f"  location_id: {uuid_location_id}\n")
    except ValueError as e:
        print(f"✗ Error parseando UUIDs: {e}")
        return

    # Obtener sesión de DB
    async for session in get_db():
        try:
            # 1. Verificar si el trip existe
            print("1. Verificando si el trip existe...")
            sel_stmt = Select(TripDB).Where(
                (TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id)
            )
            trip = await session.exec(sel_stmt).first()

            if not trip:
                print(f"✗ Trip {trip_id} NO encontrado")
                return

            print(f"✓ Trip encontrado:")
            print(f"  ID: {trip.id}")
            print(f"  Pick-up: {trip.pick_up_location} → {trip.drop_off_location}")
            print(f"  Fecha: {trip.pick_up_date} {trip.pick_up_time}")
            print(f"  Vuelo: {trip.airline} {trip.flight_number}\n")

            # 2. Intentar DELETE
            print("2. Intentando DELETE...")
            del_stmt = Delete(TripDB).Where(
                (TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id)
            )

            result = await session.exec(del_stmt)
            print(f"✓ DELETE ejecutado (result: {result})")

            # 3. Commit
            print("3. Haciendo COMMIT...")
            await session.commit()
            print("✓ COMMIT exitoso")

            # 4. Verificar que se eliminó
            print("\n4. Verificando eliminación...")
            check = await session.exec(sel_stmt).first()
            if check is None:
                print("✓ Trip eliminado correctamente")
            else:
                print("✗ Trip todavía existe después del DELETE")

        except Exception as e:
            print(f"\n✗ ERROR durante DELETE:")
            print(f"  Tipo: {type(e).__name__}")
            print(f"  Mensaje: {str(e)}")

            import traceback
            print(f"\n  Traceback completo:")
            traceback.print_exc()

            # Rollback
            try:
                await session.rollback()
                print("\n✓ Rollback ejecutado")
            except Exception as rb_error:
                print(f"✗ Error en rollback: {rb_error}")

        break  # Solo usar la primera sesión

if __name__ == "__main__":
    asyncio.run(debug_delete_trip())
