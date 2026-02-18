"""
PATCH para Fix de Expand - Respetar min_gap al Identificar Cadenas

Este archivo contiene las funciones modificadas listas para reemplazar
en features/trips/services/step_filter_service.py

INSTRUCCIONES:
1. Hacer backup del archivo original
2. Aplicar los cambios en las líneas indicadas
3. Probar con casos de prueba manual
"""

# =============================================================================
# CAMBIO #1: Actualizar llamada en _apply_expand (línea ~845)
# =============================================================================

"""
ANTES (líneas 844-849):
                # Identify chains within this location group
                chains = self._identify_expand_chains(
                    group_trips,
                    max_gap=window.max_gap,
                    max_shift=window.max_shift
                )

DESPUÉS (líneas 844-850):

                # Identify chains within this location group
                chains = self._identify_expand_chains(
                    group_trips,
                    min_gap=window.min_gap,     # ← AGREGADO
                    max_gap=window.max_gap,
                    max_shift=window.max_shift
                )
"""


# =============================================================================
# CAMBIO #2: Reemplazar función completa _identify_expand_chains (líneas 884-924)
# =============================================================================

"""
UBICACIÓN: step_filter_service.py líneas 884-924

REEMPLAZAR LA FUNCIÓN COMPLETA CON EL CÓDIGO QUE ESTÁ EN LA FUNCIÓN test_identify_chains_fix
ABAJO (ver _identify_expand_chains_NEW)
"""

# =============================================================================
# OPCIONAL: Validación adicional en _apply_expand (línea ~769)
# =============================================================================

"""
AGREGAR después de la línea 771 (después del continue de validación):

            # Validación adicional: min_gap debe ser <= max_gap
            if window.min_gap > window.max_gap:
                logger.error(
                    f"[EXPAND_CONFIG_ERROR] Invalid config: min_gap ({window.min_gap}) "
                    f"> max_gap ({window.max_gap}). Skipping this window."
                )
                continue
"""


# =============================================================================
# TESTING CODE - Para verificar el fix manualmente
# =============================================================================

def test_identify_chains_fix():
    """
    Test manual para verificar que el fix funciona correctamente.

    Simula el comportamiento de _identify_expand_chains con datos de ejemplo.
    """
    from datetime import time

    # Mock de Trip
    class MockTrip:
        def __init__(self, trip_id, pick_up_time):
            self.id = trip_id
            self.pick_up_time = pick_up_time

    # Mock de service
    class MockService:
        def _get_effective_time(self, trip):
            return trip.pick_up_time

        def _time_to_minutes(self, t: time) -> int:
            return t.hour * 60 + t.minute

        def _minutes_between(self, t1: time, t2: time) -> int:
            m1 = self._time_to_minutes(t1)
            m2 = self._time_to_minutes(t2)
            return abs(m2 - m1)

        # Función ANTES del fix (para comparar)
        def _identify_expand_chains_OLD(self, trips, max_gap, max_shift):
            if not trips:
                return []

            threshold = max_gap  # Solo usa max_gap
            chains = []
            current_chain = [trips[0]]

            for i in range(1, len(trips)):
                prev_time = self._get_effective_time(trips[i-1])
                curr_time = self._get_effective_time(trips[i])
                gap = self._minutes_between(prev_time, curr_time)

                if gap <= threshold:  # BUG: No verifica min_gap
                    current_chain.append(trips[i])
                else:
                    if len(current_chain) >= 2:
                        chains.append(current_chain)
                    current_chain = [trips[i]]

            if len(current_chain) >= 2:
                chains.append(current_chain)

            return chains

        # Función DESPUÉS del fix (NUEVA)
        def _identify_expand_chains_NEW(self, trips, min_gap, max_gap, max_shift):
            if not trips:
                return []

            chains = []
            current_chain = [trips[0]]

            for i in range(1, len(trips)):
                prev_time = self._get_effective_time(trips[i-1])
                curr_time = self._get_effective_time(trips[i])
                gap = self._minutes_between(prev_time, curr_time)

                # FIX: Verificar ambos límites
                if min_gap <= gap <= max_gap:
                    current_chain.append(trips[i])
                else:
                    if len(current_chain) >= 2:
                        chains.append(current_chain)
                    current_chain = [trips[i]]

            if len(current_chain) >= 2:
                chains.append(current_chain)

            return chains

    # Setup
    service = MockService()

    # Test Case 1: Caso reportado por usuario
    print("=" * 80)
    print("TEST CASE 1: Caso reportado (gap=0 no debería agruparse)")
    print("=" * 80)

    trips_case1 = [
        MockTrip("A", time(8, 0)),   # 08:00
        MockTrip("B", time(8, 0)),   # 08:00 (gap=0)
        MockTrip("C", time(8, 22)),  # 08:22 (gap=22)
        MockTrip("D", time(8, 45)),  # 08:45 (gap=23)
    ]

    min_gap, max_gap, max_shift = 20, 25, 10

    chains_old = service._identify_expand_chains_OLD(trips_case1, max_gap, max_shift)
    chains_new = service._identify_expand_chains_NEW(trips_case1, min_gap, max_gap, max_shift)

    print(f"\nConfig: min_gap={min_gap}, max_gap={max_gap}")
    print("\nTrips:")
    for trip in trips_case1:
        print(f"  {trip.id}: {trip.pick_up_time}")

    print(f"\n❌ ANTES (CON BUG):")
    print(f"   Cadenas: {[[t.id for t in chain] for chain in chains_old]}")
    print(f"   Total cadenas: {len(chains_old)}")

    print(f"\n✅ DESPUÉS (FIX APLICADO):")
    print(f"   Cadenas: {[[t.id for t in chain] for chain in chains_new]}")
    print(f"   Total cadenas: {len(chains_new)}")

    # Análisis detallado
    print("\nAnálisis de gaps:")
    print("  A→B: gap=0 min (< 20) ❌ Fuera de rango")
    print("  B→C: gap=22 min (en [20,25]) ✅ En rango")
    print("  C→D: gap=23 min (en [20,25]) ✅ En rango")

    print("\nInterpretación correcta:")
    print("  - A queda solo (gap A→B fuera de rango)")
    print("  - B inicia nueva cadena")
    print("  - B, C, D forman cadena (gaps internos en rango)")

    # Validación
    assert len(chains_old) == 1, "ANTES: debería haber 1 cadena [A,B,C,D]"
    assert len(chains_old[0]) == 4, "ANTES: cadena debería tener 4 trips"

    assert len(chains_new) == 1, "DESPUÉS: debería haber 1 cadena [B,C,D]"
    assert len(chains_new[0]) == 3, "DESPUÉS: cadena debería tener 3 trips"
    assert chains_new[0][0].id == "B", "DESPUÉS: primer trip debería ser B"
    assert chains_new[0][1].id == "C", "DESPUÉS: segundo trip debería ser C"
    assert chains_new[0][2].id == "D", "DESPUÉS: tercer trip debería ser D"

    print("\nPatrón que se aplicaría a [B,C,D]:")
    print("  Cadena de 3: [-10, 0, +10]")
    print("  B: 08:00 → 07:50")
    print("  C: 08:22 → 08:22 (sin cambio)")
    print("  D: 08:45 → 08:55")
    print("  Gap B-C final: 32 min ✅")
    print("  Gap C-D final: 33 min ✅")

    print("\n✅ TEST CASE 1 PASSED\n")

    # Test Case 2: Gaps mixtos
    print("=" * 80)
    print("TEST CASE 2: Gaps mixtos (algunos en rango, otros no)")
    print("=" * 80)

    trips_case2 = [
        MockTrip("A", time(4, 0)),   # 04:00
        MockTrip("B", time(4, 10)),  # 04:10 (gap=10, fuera)
        MockTrip("C", time(4, 35)),  # 04:35 (gap=25, en rango)
        MockTrip("D", time(5, 0)),   # 05:00 (gap=25, en rango)
        MockTrip("E", time(5, 40)),  # 05:40 (gap=40, fuera)
    ]

    chains_old2 = service._identify_expand_chains_OLD(trips_case2, max_gap, max_shift)
    chains_new2 = service._identify_expand_chains_NEW(trips_case2, min_gap, max_gap, max_shift)

    print(f"\nConfig: min_gap={min_gap}, max_gap={max_gap}")
    print("\nTrips:")
    for i, trip in enumerate(trips_case2):
        if i > 0:
            prev = trips_case2[i-1]
            gap = service._minutes_between(prev.pick_up_time, trip.pick_up_time)
            in_range = "✅ EN RANGO" if min_gap <= gap <= max_gap else "❌ FUERA"
            print(f"  {trip.id}: {trip.pick_up_time} (gap={gap} {in_range})")
        else:
            print(f"  {trip.id}: {trip.pick_up_time}")

    print(f"\n❌ ANTES (CON BUG):")
    print(f"   Cadenas: {[[t.id for t in chain] for chain in chains_old2]}")

    print(f"\n✅ DESPUÉS (FIX APLICADO):")
    print(f"   Cadenas: {[[t.id for t in chain] for chain in chains_new2]}")

    print("\nAnálisis de formación de cadenas:")
    print("  A→B: gap=10 < 20 → B inicia nueva cadena")
    print("  B→C: gap=25 en [20,25] → [B, C]")
    print("  C→D: gap=25 en [20,25] → [B, C, D]")
    print("  D→E: gap=40 > 25 → cadena se cierra")

    assert len(chains_new2) == 1, "DESPUÉS: debería haber 1 cadena [B,C,D]"
    assert chains_new2[0][0].id == "B", "DESPUÉS: primer trip debería ser B"
    assert chains_new2[0][1].id == "C", "DESPUÉS: segundo trip debería ser C"
    assert chains_new2[0][2].id == "D", "DESPUÉS: tercer trip debería ser D"

    print("\n✅ TEST CASE 2 PASSED\n")

    # Test Case 3: Todos fuera de rango
    print("=" * 80)
    print("TEST CASE 3: Todos los gaps fuera de rango")
    print("=" * 80)

    trips_case3 = [
        MockTrip("A", time(8, 0)),   # 08:00
        MockTrip("B", time(8, 5)),   # 08:05 (gap=5)
        MockTrip("C", time(8, 10)),  # 08:10 (gap=5)
        MockTrip("D", time(8, 15)),  # 08:15 (gap=5)
    ]

    chains_new3 = service._identify_expand_chains_NEW(trips_case3, min_gap, max_gap, max_shift)

    print(f"\nConfig: min_gap={min_gap}, max_gap={max_gap}")
    print("\nTrips:")
    for i, trip in enumerate(trips_case3):
        if i > 0:
            prev = trips_case3[i-1]
            gap = service._minutes_between(prev.pick_up_time, trip.pick_up_time)
            print(f"  {trip.id}: {trip.pick_up_time} (gap={gap} < min_gap)")
        else:
            print(f"  {trip.id}: {trip.pick_up_time}")

    print(f"\n✅ DESPUÉS (FIX APLICADO):")
    print(f"   Cadenas: {[[t.id for t in chain] for chain in chains_new3]}")
    print(f"   Total cadenas: {len(chains_new3)}")

    assert len(chains_new3) == 0, "DESPUÉS: no debería haber cadenas (todos gaps < min_gap)"

    print("\n✅ TEST CASE 3 PASSED\n")

    print("=" * 80)
    print("🎉 TODOS LOS TESTS PASSED")
    print("=" * 80)
    print("\nEl fix funciona correctamente:")
    print("✅ Respeta min_gap al identificar cadenas")
    print("✅ No agrupa trips con gap < min_gap")
    print("✅ No agrupa trips con gap > max_gap")
    print("✅ Solo agrupa trips con gap en [min_gap, max_gap]")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("TESTING FIX DE EXPAND - Respetar min_gap")
    print("=" * 80 + "\n")

    test_identify_chains_fix()

    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Aplicar los cambios en step_filter_service.py")
    print("2. Reiniciar el backend")
    print("3. Probar con casos reales en la interfaz")
    print("4. Verificar logs de exclusiones")
    print("=" * 80 + "\n")
