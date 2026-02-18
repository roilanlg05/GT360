#!/bin/bash

# Script para aplicar el fix de Expand automáticamente
# Fecha: 2026-02-11
# Modificaciones en: features/trips/services/step_filter_service.py

set -e  # Exit on error

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  FIX EXPAND - Respetar min_gap"
echo "=========================================="
echo ""

# Archivo a modificar
TARGET_FILE="features/trips/services/step_filter_service.py"

# Verificar que existe el archivo
if [ ! -f "$TARGET_FILE" ]; then
    echo -e "${RED}❌ ERROR: No se encontró el archivo $TARGET_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Archivo encontrado: $TARGET_FILE${NC}"
echo ""

# Crear backup
BACKUP_FILE="$TARGET_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo -e "${YELLOW}📦 Creando backup...${NC}"
cp "$TARGET_FILE" "$BACKUP_FILE"
echo -e "${GREEN}✅ Backup creado: $BACKUP_FILE${NC}"
echo ""

# Verificar que el archivo tiene las líneas esperadas
echo -e "${YELLOW}🔍 Verificando contenido del archivo...${NC}"

if ! grep -q "def _identify_expand_chains" "$TARGET_FILE"; then
    echo -e "${RED}❌ ERROR: No se encontró la función _identify_expand_chains${NC}"
    echo "   El archivo puede haber sido modificado previamente."
    exit 1
fi

if ! grep -q "max_gap=window.max_gap" "$TARGET_FILE"; then
    echo -e "${YELLOW}⚠️  ADVERTENCIA: No se encontró 'max_gap=window.max_gap' en la llamada${NC}"
    echo "   Puede que el fix ya esté aplicado o el código haya cambiado."
    echo ""
    read -p "¿Continuar de todos modos? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        echo "Operación cancelada"
        exit 1
    fi
fi

echo -e "${GREEN}✅ Archivo verificado${NC}"
echo ""

# Mostrar resumen de cambios
echo "=========================================="
echo "  CAMBIOS QUE SE APLICARÁN"
echo "=========================================="
echo ""
echo "1. CAMBIO en llamada a _identify_expand_chains (~línea 845):"
echo "   ANTES: chains = self._identify_expand_chains(group_trips, max_gap=..., max_shift=...)"
echo "   DESPUÉS: chains = self._identify_expand_chains(group_trips, min_gap=..., max_gap=..., max_shift=...)"
echo ""
echo "2. CAMBIO en firma de función _identify_expand_chains (~línea 884):"
echo "   ANTES: def _identify_expand_chains(self, trips, max_gap, max_shift)"
echo "   DESPUÉS: def _identify_expand_chains(self, trips, min_gap, max_gap, max_shift)"
echo ""
echo "3. CAMBIO en lógica de identificación de cadenas (~línea 912):"
echo "   ANTES: if gap <= threshold:"
echo "   DESPUÉS: if min_gap <= gap <= max_gap:"
echo ""
echo "=========================================="
echo ""

read -p "¿Aplicar los cambios? (s/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "Operación cancelada"
    rm -f "$BACKUP_FILE"
    exit 0
fi

echo ""
echo -e "${YELLOW}🔧 Aplicando cambios...${NC}"
echo ""

# CAMBIO #1: Agregar min_gap en la llamada
echo "  [1/3] Agregando parámetro min_gap en llamada..."
sed -i 's/chains = self\._identify_expand_chains(\s*$/chains = self._identify_expand_chains(/g' "$TARGET_FILE"
sed -i '/chains = self\._identify_expand_chains(/,/\)$/ {
    /max_gap=window\.max_gap,/i\                    min_gap=window.min_gap,     # ← FIX: Agregar min_gap
}' "$TARGET_FILE"

# CAMBIO #2: Modificar firma de la función
echo "  [2/3] Actualizando firma de función _identify_expand_chains..."
sed -i '/def _identify_expand_chains(/,/\) -> list\[list\[Trip\]\]:/ {
    s/max_gap: int,/min_gap: int,          # ← FIX: Agregar parámetro min_gap\n        max_gap: int,/
}' "$TARGET_FILE"

# CAMBIO #3: Modificar lógica de identificación (línea del threshold y del if)
echo "  [3/3] Actualizando lógica de identificación de cadenas..."

# Eliminar la línea "threshold = max_gap"
sed -i '/threshold = max_gap/d' "$TARGET_FILE"

# Cambiar "if gap <= threshold:" por "if min_gap <= gap <= max_gap:"
sed -i 's/if gap <= threshold:  # Gap pequeño → misma cadena (consistente con Combine)/if min_gap <= gap <= max_gap:  # ✅ FIX: Gap en rango → misma cadena/' "$TARGET_FILE"

# Cambiar comentarios
sed -i 's/# Gap pequeño → misma cadena (consistente con Combine)/# ✅ FIX: Gap dentro del rango → misma cadena/' "$TARGET_FILE"
sed -i 's/# Gap grande → nueva cadena/# Gap fuera del rango → nueva cadena/' "$TARGET_FILE"

# Actualizar docstring de la función
sed -i '/def _identify_expand_chains(/,/"""$/c\
    def _identify_expand_chains(\
        self,\
        trips: list[Trip],\
        min_gap: int,          # ← FIX: Nuevo parámetro\
        max_gap: int,\
        max_shift: int\
    ) -> list[list[Trip]]:\
        """\
        Identifica cadenas de trips con gaps EN EL RANGO [min_gap, max_gap].\
\
        Solo agrupa trips consecutivos si su gap está dentro del rango configurado.\
        Trips con gap < min_gap: ya están muy juntos, NO expandir\
        Trips con gap > max_gap: ya están suficientemente separados, NO expandir\
\
        Args:\
            trips: Lista de trips ordenados por pickup time\
            min_gap: Gap mínimo para considerar trips en la misma cadena\
            max_gap: Gap máximo para considerar trips en la misma cadena\
            max_shift: Máximo desplazamiento permitido por trip\
\
        Returns:\
            Lista de cadenas (cada cadena es una lista de trips con gaps en rango)\
        """
' "$TARGET_FILE"

echo ""
echo -e "${GREEN}✅ Cambios aplicados correctamente${NC}"
echo ""

# Verificar sintaxis Python
echo -e "${YELLOW}🔍 Verificando sintaxis Python...${NC}"
if python3 -m py_compile "$TARGET_FILE" 2>&1; then
    echo -e "${GREEN}✅ Sintaxis correcta${NC}"
else
    echo -e "${RED}❌ ERROR: Sintaxis incorrecta. Restaurando backup...${NC}"
    cp "$BACKUP_FILE" "$TARGET_FILE"
    echo -e "${YELLOW}⚠️  Backup restaurado. Cambios revertidos.${NC}"
    exit 1
fi

echo ""
echo "=========================================="
echo "  ✅ FIX APLICADO EXITOSAMENTE"
echo "=========================================="
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Reiniciar el backend:"
echo "   sudo systemctl restart backend"
echo ""
echo "2. Verificar logs:"
echo "   tail -f /var/log/backend.log | grep EXPAND_CHAIN"
echo ""
echo "3. Probar con casos de prueba manuales"
echo ""
echo "4. Si hay problemas, restaurar backup:"
echo "   cp $BACKUP_FILE $TARGET_FILE"
echo "   sudo systemctl restart backend"
echo ""
echo "=========================================="
echo ""
