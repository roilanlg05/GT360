#!/usr/bin/env python3
"""
Script para eliminar la location SDF del usuario carlitoleo10@gmail.com
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from psqlmodel import Select, Delete, AsyncSession
from shared.db.schemas import User, Manager, Location, Trip, Hotel
from shared.db.db_config import get_db


async def delete_sdf_location():
    """Elimina la location SDF para el usuario carlitoleo10@gmail.com"""

    email = "carlitoleo10@gmail.com"

    print("=" * 80)
    print("ELIMINACIÓN DE LOCATION SDF")
    print("=" * 80)
    print(f"\nUsuario: {email}\n")

    # Obtener sesión de DB
    async for session in get_db():
        try:
            # 1. Buscar el usuario
            print("1. Buscando usuario...")
            user = await session.exec(
                Select(User).Where(User.email == email.lower())
            ).first()

            if not user:
                print(f"❌ Usuario no encontrado: {email}")
                return

            print(f"✓ Usuario encontrado: {user.id}")
            print(f"  - Role: {user.role}")

            # 2. Verificar que sea manager y obtener su organización
            if user.role != "manager":
                print(f"❌ El usuario no es un manager (role: {user.role})")
                return

            print("\n2. Obteniendo organización...")
            manager = await session.exec(
                Select(Manager).Where(Manager.id == user.id)
            ).first()

            if not manager or not manager.organization_id:
                print("❌ Manager sin organización asociada")
                return

            print(f"✓ Organización encontrada: {manager.organization_id}")

            # 3. Buscar la location SDF
            print("\n3. Buscando location SDF...")
            location = await session.exec(
                Select(Location).Where(
                    (Location.name == "SDF") &
                    (Location.organization_id == manager.organization_id)
                )
            ).first()

            if not location:
                print("❌ Location SDF no encontrada para esta organización")
                print("   Es posible que ya haya sido eliminada")
                return

            print(f"✓ Location SDF encontrada: {location.id}")
            print(f"  - Provider: {location.provider}")
            print(f"  - Timezone: {location.timezone}")

            # 4. Contar trips y hotels asociados
            print("\n4. Contando elementos asociados...")

            trips_count = len(await session.exec(
                Select(Trip).Where(Trip.location_id == location.id)
            ).all())

            hotels_count = len(await session.exec(
                Select(Hotel).Where(Hotel.location_id == location.id)
            ).all())

            print(f"  - Trips: {trips_count}")
            print(f"  - Hotels: {hotels_count}")

            # 5. Confirmar eliminación
            print("\n5. ADVERTENCIA:")
            print(f"   Se eliminarán:")
            print(f"   - 1 Location (SDF)")
            print(f"   - {trips_count} Trips")
            print(f"   - {hotels_count} Hotels")
            print()

            respuesta = input("¿Continuar con la eliminación? (escribe 'SI' para confirmar): ")

            if respuesta.strip().upper() != "SI":
                print("\n❌ Eliminación cancelada por el usuario")
                return

            # 6. Eliminar hoteles primero
            print("\n6. Eliminando hoteles...")
            await session.exec(
                Delete(Hotel).Where(Hotel.location_id == location.id)
            )
            print(f"✓ {hotels_count} hoteles eliminados")

            # 7. Eliminar la location (trips se eliminan por CASCADE)
            print("\n7. Eliminando location y trips (CASCADE)...")
            await session.exec(
                Delete(Location).Where(Location.id == location.id)
            )

            # 8. Commit
            await session.commit()

            print(f"\n✓ ÉXITO: Location SDF eliminada correctamente")
            print(f"  - Location ID: {location.id}")
            print(f"  - Trips eliminados: {trips_count}")
            print(f"  - Hotels eliminados: {hotels_count}")
            print()

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            await session.rollback()
            import traceback
            traceback.print_exc()
        finally:
            break  # Solo queremos una sesión


if __name__ == "__main__":
    asyncio.run(delete_sdf_location())
