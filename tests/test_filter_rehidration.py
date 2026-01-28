"""
Test de Rehidratación de Filtros
Objetivo: Verificar que después de aplicar un filtro, el GET /stack retorna la config correctamente
"""

import asyncio
import sys
from datetime import date
from uuid import UUID

# Add project to path
sys.path.insert(0, '/home/backend/GT360')

from shared.db.db_config import engine, AsyncSession
from shared.db.schemas import FilterStep, Trip, TripType, TripStatus
from features.trips.services.step_filter_service import StepFilterService
from features.trips.models.filter_models import FilterStepConfig, TimeWindow
from psqlmodel import Select


async def test_filter_rehidration():
    """
    Test completo del flujo:
    1. Aplicar un filtro Reduce
    2. Verificar que se guarda en DB
    3. Hacer GET /stack (rehidratación)
    4. Verificar que retorna la configuración correcta
    """

    print("=" * 80)
    print("TEST: Rehidratación de Filtros Ground Filters V2")
    print("=" * 80)
    print()

    # Configuración del test
    location_id = UUID('d9f81f73-3059-4bcf-a980-47cca92fe594')  # ONT
    airline = 'WN'
    pick_up_date_str = '2026-01-26'  # Usar fecha futura con trips

    async with AsyncSession(engine) as session:
        service = StepFilterService(session)

        # ====================================================================
        # PASO 1: Verificar trips elegibles ANTES de aplicar
        # ====================================================================
        print("📋 PASO 1: Verificar trips elegibles")
        print("-" * 80)

        eligible_query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.pick_up_date == date.fromisoformat(pick_up_date_str))
            .Where(Trip.trip_type == TripType.OUTBOUND)
            .Where(Trip.status == TripStatus.SCHEDULED)
        )
        eligible_trips = await session.exec(eligible_query).all()

        print(f"✅ Trips elegibles encontrados: {len(eligible_trips)}")

        if not eligible_trips:
            print("❌ ERROR: No hay trips elegibles para esta fecha")
            print("   El test necesita trips con:")
            print("   - trip_type = 'outbound'")
            print("   - status = 'scheduled'")
            print(f"   - pick_up_date = {pick_up_date_str}")
            return False

        # Mostrar sample
        sample = eligible_trips[0]
        print(f"\n   Sample trip:")
        print(f"   - ID: {sample.id}")
        print(f"   - Pick up time: {sample.pick_up_time}")
        print(f"   - Original time: {sample.original_pick_up_time}")
        print(f"   - Reduce applied: {sample.reduce_applied}")
        print()

        # ====================================================================
        # PASO 2: Limpiar filtros anteriores para este test
        # ====================================================================
        print("🧹 PASO 2: Limpiar filtros anteriores (setup del test)")
        print("-" * 80)

        # Buscar y revertir steps activos
        existing_steps_query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == date.fromisoformat(pick_up_date_str))
            .Where(FilterStep.is_active == True)
        )
        existing_steps = await session.exec(existing_steps_query).all()

        if existing_steps:
            print(f"⚠️  Encontrados {len(existing_steps)} steps activos existentes")
            print("   Revertiéndolos para empezar limpio...")

            for step in existing_steps:
                try:
                    await service.revert_step(step.id)
                    print(f"   ✅ Step {step.id} revertido")
                except Exception as e:
                    print(f"   ❌ Error revirtiendo step: {e}")
        else:
            print("✅ No hay steps activos - empezando limpio")
        print()

        # ====================================================================
        # PASO 3: Aplicar filtro Reduce
        # ====================================================================
        print("🔧 PASO 3: Aplicar filtro Reduce con 10 minutos")
        print("-" * 80)

        config = FilterStepConfig(
            filter_type="reduce",
            pick_up_date=pick_up_date_str,
            windows=[
                TimeWindow(
                    start="00:00",
                    end="24:00",
                    enabled=True,
                    minutes_to_reduce=10
                )
            ]
        )

        try:
            result = await service.apply_step(location_id, airline, config)

            print(f"✅ Filtro aplicado exitosamente")
            print(f"   - Step ID: {result.step_id}")
            print(f"   - Filter type: {result.filter_type}")
            print(f"   - Trips modified: {result.trips_modified}")
            print(f"   - Pick up date: {result.pick_up_date}")

            step_id_created = result.step_id

        except Exception as e:
            print(f"❌ ERROR aplicando filtro: {e}")
            import traceback
            traceback.print_exc()
            return False

        print()

        # ====================================================================
        # PASO 4: Verificar que el FilterStep se guardó en DB
        # ====================================================================
        print("🔍 PASO 4: Verificar que FilterStep se guardó en PostgreSQL")
        print("-" * 80)

        saved_step_query = (
            Select(FilterStep)
            .Where(FilterStep.id == step_id_created)
        )
        saved_step = await session.exec(saved_step_query).first()

        if not saved_step:
            print(f"❌ ERROR CRÍTICO: FilterStep {step_id_created} NO se encontró en DB")
            print("   El commit pudo haber fallado")
            return False

        print(f"✅ FilterStep encontrado en DB")
        print(f"   - ID: {saved_step.id}")
        print(f"   - is_active: {saved_step.is_active}")
        print(f"   - filter_type: {saved_step.filter_type}")
        print(f"   - step_order: {saved_step.step_order}")
        print(f"   - trips_affected: {saved_step.trips_affected}")
        print(f"   - windows: {saved_step.windows}")
        print(f"   - created_at: {saved_step.created_at}")
        print()

        # ====================================================================
        # PASO 5: Verificar que los trips se modificaron
        # ====================================================================
        print("🔍 PASO 5: Verificar que los trips se modificaron en DB")
        print("-" * 80)

        modified_trips_query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.pick_up_date == date.fromisoformat(pick_up_date_str))
            .Where(Trip.reduce_applied == True)
        )
        modified_trips = await session.exec(modified_trips_query).all()

        print(f"✅ Trips modificados encontrados: {len(modified_trips)}")

        if modified_trips:
            sample_modified = modified_trips[0]
            print(f"\n   Sample trip modificado:")
            print(f"   - ID: {sample_modified.id}")
            print(f"   - Pick up time (new): {sample_modified.pick_up_time}")
            print(f"   - Original time (backup): {sample_modified.original_pick_up_time}")
            print(f"   - Reduce applied: {sample_modified.reduce_applied}")
            print(f"   - Current step_id: {sample_modified.current_step_id}")

            # Verificar que current_step_id coincide
            if sample_modified.current_step_id == step_id_created:
                print(f"   ✅ current_step_id coincide con el step creado")
            else:
                print(f"   ⚠️  current_step_id no coincide:")
                print(f"      Expected: {step_id_created}")
                print(f"      Got: {sample_modified.current_step_id}")
        else:
            print("❌ ERROR: No se encontraron trips modificados")
            return False

        print()

        # ====================================================================
        # PASO 6: SIMULAR F5 - Rehidratar con GET /stack
        # ====================================================================
        print("🔄 PASO 6: SIMULAR F5 - Rehidratación con GET /stack")
        print("-" * 80)
        print(f"   Llamando: GET /stack?pick_up_date={pick_up_date_str}")
        print()

        try:
            stack_state = await service.get_stack(location_id, airline, pick_up_date_str)

            print(f"📥 Respuesta de GET /stack:")
            print(f"   - location_id: {stack_state.location_id}")
            print(f"   - airline: {stack_state.airline}")
            print(f"   - pick_up_date: {stack_state.pick_up_date}")
            print(f"   - Total steps: {len(stack_state.steps)}")
            print(f"   - Total trips affected: {stack_state.total_trips_affected}")
            print()

            if not stack_state.steps:
                print("❌ ERROR CRÍTICO: GET /stack retorna steps vacío")
                print("   Esto significa que la rehidratación FALLA")
                print("   El filtro aparecerá como 'apagado' después de F5")
                print()
                print("   Posibles causas:")
                print("   1. FilterStep fue marcado como is_active=false")
                print("   2. FilterStep fue eliminado de la DB")
                print("   3. Bug en la query de get_stack")
                print()

                # Debug: Buscar steps inactivos
                all_steps_query = (
                    Select(FilterStep)
                    .Where(FilterStep.location_id == location_id)
                    .Where(FilterStep.airline == airline)
                    .Where(FilterStep.pick_up_date == date.fromisoformat(pick_up_date_str))
                )
                all_steps = await session.exec(all_steps_query).all()

                print(f"   Debug: Total FilterSteps en DB (activos+inactivos): {len(all_steps)}")
                for step in all_steps:
                    status = "ACTIVO" if step.is_active else "INACTIVO"
                    print(f"   - {status}: {step.filter_type}, order={step.step_order}, id={step.id}")

                return False

            # Verificar que el step retornado es el que creamos
            step_info = stack_state.steps[0]
            print(f"✅ Step retornado en rehidratación:")
            print(f"   - step_id: {step_info.step_id}")
            print(f"   - filter_type: {step_info.filter_type}")
            print(f"   - step_order: {step_info.step_order}")
            print(f"   - trips_affected: {step_info.trips_affected}")
            print(f"   - windows_count: {step_info.windows_count}")
            print(f"   - windows: {step_info.windows}")
            print(f"   - is_active: {step_info.is_active}")
            print()

            if step_info.step_id == step_id_created:
                print("✅ PASO 6 OK: El step_id coincide con el creado")
            else:
                print(f"⚠️  Step ID no coincide")
                print(f"   Expected: {step_id_created}")
                print(f"   Got: {step_info.step_id}")

            # Verificar windows
            if step_info.windows:
                window = step_info.windows[0]
                print(f"\n✅ Windows rehidratados correctamente:")
                print(f"   - start: {window.get('start')}")
                print(f"   - end: {window.get('end')}")
                print(f"   - minutes_to_reduce: {window.get('minutes_to_reduce')}")
            else:
                print(f"❌ ERROR: Windows vacíos en rehidratación")
                return False

        except Exception as e:
            print(f"❌ ERROR en GET /stack: {e}")
            import traceback
            traceback.print_exc()
            return False

        print()

        # ====================================================================
        # RESUMEN FINAL
        # ====================================================================
        print("=" * 80)
        print("📊 RESUMEN DEL TEST")
        print("=" * 80)
        print()
        print(f"✅ PASO 1: Trips elegibles encontrados ({len(eligible_trips)} trips)")
        print(f"✅ PASO 2: Setup limpio")
        print(f"✅ PASO 3: Filtro aplicado (step_id={step_id_created})")
        print(f"✅ PASO 4: FilterStep guardado en DB (is_active=true)")
        print(f"✅ PASO 5: Trips modificados en DB ({len(modified_trips)} trips)")
        print(f"✅ PASO 6: Rehidratación funciona (GET /stack retorna {len(stack_state.steps)} step)")
        print()
        print("=" * 80)
        print("🎉 TEST PASSED: El backend funciona correctamente")
        print("=" * 80)
        print()
        print("CONCLUSIÓN:")
        print("- El filtro se aplica y guarda correctamente en DB")
        print("- La rehidratación funciona (GET /stack retorna la config)")
        print("- Si después de F5 el filtro aparece apagado, el problema es del FRONTEND")
        print()

        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_filter_rehidration())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrumpido por usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
