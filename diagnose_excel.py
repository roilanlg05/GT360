#!/usr/bin/env python3
"""
Script de diagnóstico para el archivo 'Sdf December .xls'
"""
import sys
import traceback
from pathlib import Path
from io import BytesIO

# Agregar el directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

from features.trips.utils.trip_importer import load_trips_from_bytes


async def main():
    """Función principal de diagnóstico"""
    file_path = "docs/Docs_From_Frontend/Sdf December .xls"

    print("=" * 80)
    print("DIAGNÓSTICO DEL ARCHIVO EXCEL")
    print("=" * 80)
    print(f"\nArchivo: {file_path}\n")

    # Leer el archivo
    with open(file_path, "rb") as f:
        content = f.read()

    print(f"✓ Archivo leído correctamente ({len(content)} bytes)\n")

    # Parámetros de prueba
    location = "SDF"
    airline = "WN"
    plan = "freemium"

    print(f"Parámetros:")
    print(f"  - Location (airport): {location}")
    print(f"  - Airline: {airline}")
    print(f"  - Plan: {plan}")
    print()

    # Intentar procesar el archivo
    print("Procesando archivo...\n")
    try:
        result = await load_trips_from_bytes(
            content,
            location=location,
            plan=plan,
            airlinex=airline,
            sheet_name="Schedule"
        )

        print(f"Tipo de resultado: {type(result)}")
        print(f"Número de elementos: {len(result) if hasattr(result, '__len__') else 'N/A'}")

        # El resultado es solo una lista de trips
        trips = result

        print(f"\n✓ ÉXITO: Se procesaron {len(trips)} trips")
        print()

        # Mostrar algunos trips de ejemplo
        if trips:
            print("Primeros 5 trips:")
            for i, trip in enumerate(trips[:5], 1):
                print(f"\n  Trip {i}:")
                print(f"    - Fecha: {trip.pick_up_date}")
                print(f"    - Hora: {trip.pick_up_time}")
                print(f"    - Pick up: {trip.pick_up_location}")
                print(f"    - Drop off: {trip.drop_off_location}")
                print(f"    - Vuelo: {trip.airline} {trip.flight_number}")
                print(f"    - Riders: {trip.riders}")
                print(f"    - Trip type: {trip.trip_type}")

    except ValueError as e:
        print(f"\n❌ ERROR DE VALIDACIÓN:")
        print(f"   {str(e)}")
        print()
        traceback.print_exc()

    except RuntimeError as e:
        print(f"\n❌ ERROR DE FORMATO:")
        print(f"   {str(e)}")
        print()
        traceback.print_exc()

    except Exception as e:
        print(f"\n❌ ERROR INESPERADO ({type(e).__name__}):")
        print(f"   {str(e)}")
        print()
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
