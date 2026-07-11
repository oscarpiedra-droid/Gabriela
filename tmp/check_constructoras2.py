import sys
sys.path.insert(0, 'app')
import db.commercial_rules as rules
rules.load_from_json()

print("SEGMENTOS registrados en SKU_DISCOUNTS:")
# DiscountProposalService guarda un dict segmento→familia→tramos
from db.services.commercial_conditions_service import DiscountProposalService
svc = DiscountProposalService()

# Introspect the internal discount table
if hasattr(svc, '_table'):
    segs = set()
    for key in svc._table:
        seg = key[0]
        segs.add(seg)
    print("Segmentos en tabla:")
    for s in sorted(segs):
        print(f"  {s!r}")

    print("\n--- Buscar 'Empresas Constructoras' ---")
    const_keys = [k for k in svc._table if 'constructora' in str(k[0]).lower()]
    if const_keys:
        print(f"Encontradas {len(const_keys)} filas:")
        for k in const_keys[:10]:
            print(f"  {k} → {svc._table[k]}")
    else:
        print("NO ENCONTRADO — el segmento 'Empresas Constructoras' no tiene entradas en el motor de descuentos")
else:
    print("Atributo _table no existe, buscando otro...")
    print(dir(svc))
