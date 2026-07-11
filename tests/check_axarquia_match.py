import sys, json
sys.path.insert(0, 'app')
with open('app/db/services/homologacion_clientes.json', encoding='utf-8') as f:
    cat = json.load(f)
print("Segmentos con 'axarq' o 'sound':")
for entry in cat.get('homologacion', []):
    seg = entry.get('segmento_aplicacion', '')
    if 'axarq' in seg.lower() or 'sound' in seg.lower():
        print(f"  {repr(seg)}  uso={entry.get('uso','')}")

# Verificar que el segmento Axarquia en homologacion coincide exactamente
# con el _AXARQUIA_SEGMENT de commercial_conditions_service.py
from db.services.commercial_conditions_service import _AXARQUIA_SEGMENT, FAMILY_LOGIC_MAP_OVERRIDES
print(f"\n_AXARQUIA_SEGMENT = {repr(_AXARQUIA_SEGMENT)}")
print("OVERRIDES keys:", list(FAMILY_LOGIC_MAP_OVERRIDES.keys()))
print()
# Verificar match exacto con lo que devuelve homologacion
segs_en_catalogo = {e.get('segmento_aplicacion','') for e in cat.get('homologacion',[])}
if _AXARQUIA_SEGMENT in segs_en_catalogo:
    print("OK: _AXARQUIA_SEGMENT coincide con los valores del catalogo de homologacion")
else:
    print("ATENCION: No se encontro _AXARQUIA_SEGMENT en el catalogo")
    print("Segmentos disponibles:")
    for s in sorted(segs_en_catalogo):
        if s:
            print(f"  {repr(s)}")
