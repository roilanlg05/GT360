#!/usr/bin/env python3
"""
Script para aplicar el fix de Expand automáticamente
Fecha: 2026-02-11
Modificaciones en: features/trips/services/step_filter_service.py
"""

import os
import sys
import shutil
from datetime import datetime

# Colores para output
class Colors:
    YELLOW = '\033[1;33m'
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.NC}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.NC}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.NC}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.NC}")


def main():
    print_header("FIX EXPAND - Respetar min_gap")

    # Archivo a modificar
    target_file = "features/trips/services/step_filter_service.py"

    # Verificar que existe
    if not os.path.exists(target_file):
        print_error(f"No se encontró el archivo {target_file}")
        return 1

    print_success(f"Archivo encontrado: {target_file}")

    # Crear backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{target_file}.backup.{timestamp}"

    print(f"\n{Colors.YELLOW}📦 Creando backup...{Colors.NC}")
    shutil.copy2(target_file, backup_file)
    print_success(f"Backup creado: {backup_file}")

    # Leer archivo
    with open(target_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Verificar contenido
    print(f"\n{Colors.YELLOW}🔍 Verificando contenido...{Colors.NC}")

    if "def _identify_expand_chains" not in content:
        print_error("No se encontró la función _identify_expand_chains")
        return 1

    if "max_gap=window.max_gap" not in content:
        print_warning("No se encontró 'max_gap=window.max_gap' en la llamada")
        response = input("¿Continuar de todos modos? (s/n): ")
        if response.lower() != 's':
            print("Operación cancelada")
            os.remove(backup_file)
            return 0

    print_success("Archivo verificado")

    # Mostrar resumen
    print_header("CAMBIOS QUE SE APLICARÁN")
    print("1. CAMBIO en llamada a _identify_expand_chains (~línea 845):")
    print("   AGREGAR: min_gap=window.min_gap,")
    print("")
    print("2. CAMBIO en firma de función (~línea 884):")
    print("   AGREGAR: min_gap: int  (nuevo parámetro)")
    print("")
    print("3. CAMBIO en lógica de identificación (~línea 912):")
    print("   CAMBIAR: if gap <= threshold:")
    print("   POR:     if min_gap <= gap <= max_gap:")
    print("")

    response = input("¿Aplicar los cambios? (s/n): ")
    if response.lower() != 's':
        print("Operación cancelada")
        os.remove(backup_file)
        return 0

    print(f"\n{Colors.YELLOW}🔧 Aplicando cambios...{Colors.NC}\n")

    # =========================================================================
    # CAMBIO #1: Agregar min_gap en la llamada (~línea 845)
    # =========================================================================
    print("  [1/3] Agregando parámetro min_gap en llamada...")

    old_call = """                chains = self._identify_expand_chains(
                    group_trips,
                    max_gap=window.max_gap,
                    max_shift=window.max_shift
                )"""

    new_call = """                chains = self._identify_expand_chains(
                    group_trips,
                    min_gap=window.min_gap,
                    max_gap=window.max_gap,
                    max_shift=window.max_shift
                )"""

    if old_call in content:
        content = content.replace(old_call, new_call)
        print_success("Llamada actualizada")
    else:
        print_warning("No se encontró el patrón exacto de llamada, intentando alternativa...")
        # Intentar con variaciones de espaciado
        import re
        pattern = r'chains\s*=\s*self\._identify_expand_chains\(\s*group_trips,\s*max_gap=window\.max_gap,\s*max_shift=window\.max_shift\s*\)'
        if re.search(pattern, content):
            content = re.sub(
                pattern,
                'chains = self._identify_expand_chains(\n                    group_trips,\n                    min_gap=window.min_gap,\n                    max_gap=window.max_gap,\n                    max_shift=window.max_shift\n                )',
                content
            )
            print_success("Llamada actualizada (patrón alternativo)")
        else:
            print_error("No se pudo aplicar CAMBIO #1 automáticamente")
            print_info("Deberás aplicarlo manualmente según EXPAND_FIX_FINAL.md")

    # =========================================================================
    # CAMBIO #2: Modificar firma y cuerpo de la función (~líneas 884-924)
    # =========================================================================
    print("  [2/3] Actualizando función _identify_expand_chains completa...")

    # Función VIEJA (para encontrar y reemplazar)
    old_function_start = '    def _identify_expand_chains(\n        self,\n        trips: list[Trip],\n        max_gap: int,\n        max_shift: int\n    ) -> list[list[Trip]]:'

    # Buscar la función vieja
    if old_function_start in content:
        # Encontrar el inicio de la función
        start_idx = content.find(old_function_start)

        # Encontrar el final de la función (siguiente def o final de archivo)
        # Buscar desde después de la firma hasta el siguiente "    def " o final de archivo
        search_from = start_idx + len(old_function_start)
        next_def_match = content.find('\n    def ', search_from)

        if next_def_match == -1:
            # No hay siguiente función, tomar hasta el final
            end_idx = len(content)
        else:
            end_idx = next_def_match

        # Extraer la función completa (incluyendo docstring y código)
        old_function_full = content[start_idx:end_idx]

        # Nueva función
        new_function = '''    def _identify_expand_chains(
        self,
        trips: list[Trip],
        min_gap: int,          # ← FIX: Nuevo parámetro
        max_gap: int,
        max_shift: int
    ) -> list[list[Trip]]:
        """
        Identifica cadenas de trips con gaps EN EL RANGO [min_gap, max_gap].

        Solo agrupa trips consecutivos si su gap está dentro del rango configurado.
        Trips con gap < min_gap: ya están muy juntos, NO expandir
        Trips con gap > max_gap: ya están suficientemente separados, NO expandir

        Args:
            trips: Lista de trips ordenados por pickup time
            min_gap: Gap mínimo para considerar trips en la misma cadena
            max_gap: Gap máximo para considerar trips en la misma cadena
            max_shift: Máximo desplazamiento permitido por trip

        Returns:
            Lista de cadenas (cada cadena es una lista de trips con gaps en rango)
        """
        if not trips:
            return []

        chains = []
        current_chain = [trips[0]]

        for i in range(1, len(trips)):
            prev_time = self._get_effective_time(trips[i-1])
            curr_time = self._get_effective_time(trips[i])
            gap = self._minutes_between(prev_time, curr_time)

            # ✅ FIX: Verificar que gap esté EN EL RANGO [min_gap, max_gap]
            if min_gap <= gap <= max_gap:
                # Gap dentro del rango → misma cadena
                current_chain.append(trips[i])
            else:
                # Gap fuera del rango → nueva cadena
                if len(current_chain) >= 2:
                    chains.append(current_chain)
                current_chain = [trips[i]]

        # Agregar última cadena si tiene al menos 2 trips
        if len(current_chain) >= 2:
            chains.append(current_chain)

        return chains
'''

        # Reemplazar
        content = content[:start_idx] + new_function + content[end_idx:]
        print_success("Función _identify_expand_chains reemplazada")

    else:
        print_error("No se encontró la firma exacta de la función")
        print_info("Deberás aplicar CAMBIO #2 manualmente según EXPAND_FIX_FINAL.md")

    print("  [3/3] Cambios aplicados al contenido")

    # Escribir archivo modificado
    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print_success("Archivo guardado")

    # Verificar sintaxis
    print(f"\n{Colors.YELLOW}🔍 Verificando sintaxis Python...{Colors.NC}")
    import py_compile
    try:
        py_compile.compile(target_file, doraise=True)
        print_success("Sintaxis correcta")
    except py_compile.PyCompileError as e:
        print_error(f"Error de sintaxis: {e}")
        print_warning("Restaurando backup...")
        shutil.copy2(backup_file, target_file)
        print_warning("Backup restaurado. Cambios revertidos.")
        return 1

    # Resumen final
    print_header("✅ FIX APLICADO EXITOSAMENTE")
    print("NEXT STEPS:\n")
    print("1. Reiniciar el backend:")
    print("   sudo systemctl restart backend\n")
    print("2. Verificar logs:")
    print("   tail -f /var/log/backend.log | grep EXPAND_CHAIN\n")
    print("3. Probar con casos de prueba manuales\n")
    print("4. Si hay problemas, restaurar backup:")
    print(f"   cp {backup_file} {target_file}")
    print("   sudo systemctl restart backend\n")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nOperación cancelada por usuario")
        sys.exit(1)
    except Exception as e:
        print_error(f"Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
