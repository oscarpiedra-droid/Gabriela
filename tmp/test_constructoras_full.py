import sys, os
sys.path.insert(0, 'app')
import db.commercial_rules as rules
rules.load_from_json()
from db.services.commercial_conditions_service import DiscountProposalService

svc = DiscountProposalService()
data = svc.get_proposal_data()

# Segmentos únicos en el Excel
segs = sorted({str(r.get('Segmento','')).strip() for r in data if r.get('Segmento')})
print("SEGMENTOS en Excel:")
for s in segs:
    print(f"  {s!r}")

# Familias únicas de Empresas Constructoras
print("\nFAMILIAS de 'Empresas Constructoras':")
fams = sorted({str(r.get('Familia','')).strip() for r in data if str(r.get('Segmento','')).strip() == 'Empresas Constructoras'})
for f in fams:
    print(f"  {f!r}")

# Test validate_range para el caso del pedido SO50189
# AIR-BUR Reticulado → family_logic_base del SKU 20.003
print("\n=== TEST SO50189 ===")
print("SKU 20.003 SKU_MASTER:", rules.SKU_MASTER.get('20.003', {}).get('family_logic_base', 'NOT FOUND'))

# Simulamos validate_range para Empresas Constructoras + AIR-BUR + 1552.50€ + 64% dto
res = svc.validate_range(
    segmento='Empresas Constructoras',
    familia=rules.SKU_MASTER.get('20.003', {}).get('family_logic_base', 'REFLECTIVOS_EXCL_CM_XPS_SYC'),
    base_imponible=1552.50,
    territorio='PENINSULA',
    dto_solicitado=64.0,
    familias_en_pedido=None
)
print("validate_range result:", res)

# Mostrar la familia que resuelve
fam_int = rules.SKU_MASTER.get('20.003', {}).get('family_logic_base', '')
fam_excel = svc.resolve_familia_excel(fam_int, 'Empresas Constructoras')
print("Familia Excel resuelta:", fam_excel)
tramos = svc._get_tramo_rules('Empresas Constructoras', fam_excel)
print("Tramos encontrados:", len(tramos))
for t in tramos:
    print(f"  {t}")
