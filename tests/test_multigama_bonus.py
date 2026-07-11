"""Test +2 GAMAS / +OTRA GAMA bonus feature."""
import sys, os
# Usar miniconda local del proyecto donde está pandas instalado
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'app'))
from db.services.commercial_conditions_service import DiscountProposalService, FAMILY_LOGIC_MAP

svc = DiscountProposalService()

PASS = 0; FAIL = 0

def check(label, got, expected_contains=None, expected_exact=None):
    global PASS, FAIL
    ok = True
    if expected_exact is not None and got != expected_exact:
        ok = False
    if expected_contains is not None and (got is None or expected_contains not in got):
        ok = False
    status = 'OK' if ok else 'FAIL'
    if ok: PASS += 1
    else:  FAIL += 1
    print(f"  [{status}] {label}: {got!r}")

print("=== Test 1: Traduccion basica ===")
check("CM_XPS_SYC",            svc.resolve_familia_excel('CM_XPS_SYC', 'Almacenes Generalistas'),            expected_contains="CM XPS")
check("PARQUET base",           svc.resolve_familia_excel('PARQUET', 'Almacenes e Instaladores (Gama SOUND)'), expected_exact="PARQUET")
check("ACUSTICA",               svc.resolve_familia_excel('ACUSTICA', 'Almacenes Generalistas'),               expected_contains="ST")
check("ANTI_IMPACTO_NO_SOUND",  svc.resolve_familia_excel('ANTI_IMPACTO_NO_SOUND', 'Almacenes Generalistas'), expected_contains="ANTI")
check("IMPERMEABILIZANTES",     svc.resolve_familia_excel('IMPERMEABILIZANTES', 'Almacenes Generalistas'),     expected_exact="IMPERMEABILIZANTES")
check("REFLECTIVOS std",        svc.resolve_familia_excel('REFLECTIVOS_EXCL_CM_XPS_SYC', 'Almacenes Generalistas'), expected_contains="TERMOREFLEX")
check("REFLECTIVOS constru",    svc.resolve_familia_excel('REFLECTIVOS_EXCL_CM_XPS_SYC', 'Empresas Constructoras'), expected_contains="EXCL.")
check("REVIEW_REQUIRED = None", svc.resolve_familia_excel('REVIEW_REQUIRED', 'Almacenes Generalistas'),        expected_exact=None)

print("\n=== Test 2: Alias Axarquia ===")
check("CM XPS Axarquia",       svc.resolve_familia_excel('CM_XPS_SYC', 'Axarquia de Aislamientos (Distribucion)'), expected_contains="CM")
check("REFLECTIVOS Axarquia",  svc.resolve_familia_excel('REFLECTIVOS_EXCL_CM_XPS_SYC', 'Axarquia de Aislamientos (Distribucion)'), expected_contains="EXCL.")

print("\n=== Test 3: Bonus +2 GAMAS (CM XPS) ===")
tres_fams = {'CM_XPS_SYC', 'ACUSTICA', 'IMPERMEABILIZANTES', 'ANTI_IMPACTO_NO_SOUND'}
check("+2 GAMAS activo",       svc.resolve_familia_excel('CM_XPS_SYC', 'Almacenes Especialistas (PYL)', tres_fams), expected_contains="+2 GAMAS")
check("+2 GAMAS Generalistas", svc.resolve_familia_excel('CM_XPS_SYC', 'Almacenes Generalistas', tres_fams), expected_contains="+2 GAMAS")
check("+2 GAMAS Constructoras",svc.resolve_familia_excel('CM_XPS_SYC', 'Empresas Constructoras', tres_fams), expected_contains="+2 GAMAS")
check("+2 GAMAS Instaladoras", svc.resolve_familia_excel('CM_XPS_SYC', 'Empresas Instaladoras', tres_fams), expected_contains="+2 GAMAS")

una_fam = {'CM_XPS_SYC', 'ACUSTICA'}  # solo 1 otra
check("NO bonus con 1 otra",   svc.resolve_familia_excel('CM_XPS_SYC', 'Almacenes Especialistas (PYL)', una_fam), expected_exact="AIR BUR TERMIC (CM XPS / S-YC)")
check("NO bonus solo",         svc.resolve_familia_excel('CM_XPS_SYC', 'Almacenes Especialistas (PYL)', {'CM_XPS_SYC'}), expected_exact="AIR BUR TERMIC (CM XPS / S-YC)")

# No aplica en Axarquia
check("NO bonus Axarquia",     svc.resolve_familia_excel('CM_XPS_SYC', 'Axarquia de Aislamientos (Distribucion)', tres_fams), expected_contains="CM")

print("\n=== Test 4: Bonus +OTRA GAMA (PARQUET) ===")
parquet_dos = {'PARQUET', 'ACUSTICA'}
check("+OTRA GAMA activo",     svc.resolve_familia_excel('PARQUET', 'Almacenes e Instaladores (Gama SOUND)', parquet_dos), expected_contains="OTRA GAMA")
check("NO bonus PARQUET solo", svc.resolve_familia_excel('PARQUET', 'Almacenes e Instaladores (Gama SOUND)', {'PARQUET'}), expected_exact="PARQUET")

print(f"\n{'='*50}")
print(f"RESULTADO: {PASS} PASS / {FAIL} FAIL")
if FAIL == 0:
    print("TODAS las pruebas pasan. Feature +2 GAMAS implementada correctamente.")
