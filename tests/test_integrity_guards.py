"""
test_integrity_guards.py
Valida las 3 guardas de integridad del motor comercial BUR2000.
"""
import sys, os
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'app'))
from db.services.commercial_conditions_service import DiscountProposalService

svc = DiscountProposalService()
PASS = 0; FAIL = 0

def check(label, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [OK ] {label}")
    else:
        FAIL += 1; print(f"  [ERR] {label}" + (f" — {detail}" if detail else ''))

print("=" * 65)
print("GUARDA 1 — Hash del Excel vs JSON (_meta.excel_hash_sha256)")
print("=" * 65)
r = svc.check_excel_integrity()
check("check_excel_integrity() devuelve dict", isinstance(r, dict))
check("Campo 'ok' presente",  'ok' in r)
check("Campo 'msg' presente", 'msg' in r)
check("Hash actual calculado (64 hex chars)", len(r.get('current_hash','')) == 64, r.get('current_hash','?'))
check("Hash esperado leído del JSON",         len(r.get('expected_hash','')) == 64, r.get('expected_hash','?'))
check("Hash coincide → ok=True", r.get('ok') is True, r.get('msg',''))
print(f"\n  Mensaje: {r['msg']}")

print()
print("=" * 65)
print("GUARDA 2 — Cobertura bidireccional FAMILY_LOGIC_MAP")
print("=" * 65)
r2 = svc.check_family_map_coverage()
check("check_family_map_coverage() devuelve dict", isinstance(r2, dict))
check("ok=True (sin familias sin mapear)", r2.get('ok') is True, r2.get('msg',''))
check("missing_in_map vacío",  len(r2.get('missing_in_map',  ['?'])) == 0, str(r2.get('missing_in_map',[])))
# missing_in_excel puede tener entradas normales por alias (Axarquia)
# pero no debe tener entradas que existen literalmente en el Excel
check("excel_families no vacío", len(r2.get('excel_families', [])) > 0)
print(f"\n  Familias Excel cubiertas: {len(r2.get('excel_families', []))}")
print(f"  Mensaje: {r2['msg']}")
if r2.get('missing_in_excel'):
    print(f"  [INFO] missing_in_excel (aliases normales): {r2['missing_in_excel']}")

print()
print("=" * 65)
print("GUARDA 3 — validate_range devuelve UNCHECKED (no OK silencioso)")
print("=" * 65)
# Familia inexistente en el Excel → debe ser UNCHECKED, no OK
r3 = svc.validate_range("Almacenes Generalistas", "FAMILIA_QUE_NO_EXISTE", 5000.0, "PENINSULA", 30.0)
check("status='UNCHECKED' para familia inexistente", r3.get('status') == 'UNCHECKED', str(r3))
check("valid=True (no bloquea)", r3.get('valid') is True)

# Segmento inexistente → también UNCHECKED
r4 = svc.validate_range("Segmento Inventado", "CM_XPS_SYC", 5000.0, "PENINSULA", 30.0)
check("status='UNCHECKED' para segmento inexistente", r4.get('status') == 'UNCHECKED', str(r4))

# Familia real + segmento real → debe encontrar regla (OK o BLOQUEADO, nunca UNCHECKED)
r5 = svc.validate_range("Almacenes Generalistas", "CM_XPS_SYC", 5000.0, "PENINSULA", 30.0)
check("CM_XPS_SYC real → NO es UNCHECKED", r5.get('status') != 'UNCHECKED', str(r5))

print()
print("=" * 65)
print("GUARDA integrada — run_integrity_checks()")
print("=" * 65)
all_ok = svc.run_integrity_checks()
check("run_integrity_checks() = True", all_ok is True)

print()
print("=" * 65)
print(f"RESULTADO: {PASS} PASS / {FAIL} FAIL")
if FAIL == 0:
    print("Todas las guardas de integridad funcionan correctamente.")
print("=" * 65)
