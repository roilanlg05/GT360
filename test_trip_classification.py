"""
Script de prueba para la clasificación de trips.
Ejecutar: python test_trip_classification.py
"""

from features.trips.utils.trip_classifier import classify_trip_type_sync

def test_classification():
    """Prueba la lógica de clasificación de trips."""

    tests = [
        {
            "name": "Inbound (SDF -> Hotel)",
            "pickup": "SDF",
            "dropoff": "Marriott Hotel",
            "airport": "SDF",
            "expected": "inbound"
        },
        {
            "name": "Outbound (Hotel -> SDF)",
            "pickup": "Holiday Inn",
            "dropoff": "SDF",
            "airport": "SDF",
            "expected": "outbound"
        },
        {
            "name": "Ground (Hotel -> Hotel)",
            "pickup": "Marriott",
            "dropoff": "Holiday Inn",
            "airport": "SDF",
            "expected": "ground"
        },
        {
            "name": "Case insensitive (sdf -> Hotel)",
            "pickup": "sdf",
            "dropoff": "Hotel",
            "airport": "SDF",
            "expected": "inbound"
        },
        {
            "name": "Whitespace handling (  SDF   -> Hotel)",
            "pickup": "  SDF  ",
            "dropoff": "Hotel",
            "airport": "SDF",
            "expected": "inbound"
        },
    ]

    passed = 0
    failed = 0

    for test in tests:
        result = classify_trip_type_sync(
            test["pickup"],
            test["dropoff"],
            test["airport"]
        )

        if result == test["expected"]:
            print(f"✅ PASS: {test['name']}")
            print(f"   Resultado: {result}")
            passed += 1
        else:
            print(f"❌ FAIL: {test['name']}")
            print(f"   Esperado: {test['expected']}, Obtenido: {result}")
            failed += 1
        print()

    print(f"\n{'='*50}")
    print(f"Resultados: {passed} pasaron, {failed} fallaron")
    print(f"{'='*50}")

    return failed == 0

if __name__ == "__main__":
    success = test_classification()
    exit(0 if success else 1)
