#!/usr/bin/env python3
"""
Script para verificar el estado de un driver y sus trips.
"""
import asyncio
from psqlmodel import AsyncSession, Select
from shared.db.db_config import engine
from shared.db.schemas import User, Driver, Trip as TripDB


async def check_driver_status(driver_email: str):
    """Verifica el estado del driver y sus trips."""
    async with AsyncSession(engine) as session:
        print(f"\n{'='*70}")
        print(f"VERIFICANDO DRIVER: {driver_email}")
        print(f"{'='*70}\n")

        # Buscar usuario
        user = await session.exec(
            Select(User).Where(User.email == driver_email)
        ).first()

        if not user:
            print(f"❌ Usuario no encontrado")
            return

        print(f"✅ Usuario encontrado:")
        print(f"   ID: {user.id}")
        print(f"   Nombre: {user.first_name} {user.last_name}")
        print(f"   Email: {user.email}")
        print(f"   Role: {user.role}\n")

        # Buscar driver
        driver = await session.exec(
            Select(Driver).Where(Driver.id == user.id)
        ).first()

        if not driver:
            print(f"❌ No es un driver")
            return

        print(f"Driver info:")
        print(f"   is_active: {driver.is_active}")
        print(f"   location_id: {driver.location_id}")
        print(f"   organization_id: {driver.organization_id}\n")

        # Buscar todos los trips
        trips = await session.exec(
            Select(TripDB).Where(TripDB.assigned_driver == driver.id)
        ).all()

        print(f"{'='*70}")
        print(f"TRIPS ASIGNADOS: {len(trips)}")
        print(f"{'='*70}\n")

        if not trips:
            print("ℹ️  No hay trips asignados\n")
            return

        # Clasificar por estado
        by_status = {}
        for trip in trips:
            status = trip.status
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(trip)

        # Mostrar resumen
        for status, trip_list in by_status.items():
            print(f"\n📊 {status.upper()}: {len(trip_list)} trip(s)")
            print(f"{'-'*70}")

            for trip in trip_list:
                print(f"\n  Trip ID: {trip.id}")
                print(f"    Pick up: {trip.pick_up_date} {trip.pick_up_time}")
                print(f"    From: {trip.pick_up_location}")
                print(f"    To: {trip.drop_off_location}")
                print(f"    Airline: {trip.airline} {trip.flight_number}")
                print(f"    Type: {trip.trip_type}")
                print(f"    Started at: {trip.started_at}")
                print(f"    Picked up at: {trip.picked_up_at}")
                print(f"    Dropped off at: {trip.dropped_off_at}")

        print(f"\n{'='*70}\n")


async def main():
    await check_driver_status("lg.deals.ky@gmail.com")


if __name__ == "__main__":
    asyncio.run(main())
