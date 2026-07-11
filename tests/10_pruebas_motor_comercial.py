"""
10_pruebas_motor_comercial.py

10 escenarios de validacion comercial reales que cubren:
  - Segmentos distintos
  - Familias con y sin bonus
  - Territorios Peninsula y Baleares  
  - Tramos de facturacion altos y bajos
  - Casos limite y casos de error esperados
"""
import sys, os
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'app'))

from db.services.commercial_conditions_service import DiscountProposalService, FAMILY_LOGIC_MAP

svc = DiscountProposalService()

PASS = 0; FAIL = 0; results = []

def prueba(num, titulo, segmento, familia, base_eur, territorio, dto_pct,
           familias_pedido=None, esperado_status=None, esperado_max=None,
           nota=''):
    global PASS, FAIL
    fams = familias_pedido or {familia}
    res  = svc.validate_range(segmento, familia, base_eur, territorio, dto_pct,
                              familias_en_pedido=fams)
    got_status = res.get('status', '?')
    got_max    = res.get('rules', {}).get('max') if res.get('rules') else None
    got_fam    = res.get('checked_familia', familia)  # familia efectiva usada

    status_ok = (esperado_status is None) or (got_status == esperado_status)
    max_ok    = (esperado_max is None)    or (got_max is not None and abs(got_max - esperado_max) < 0.05)

    ok = status_ok and max_ok
    if ok: PASS += 1; badge = 'PASS'
    else:  FAIL += 1; badge = 'FAIL'

    results.append((num, badge, titulo, got_status, got_max, res.get('msg','')[:60]))

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 1: Especialista PYL / CM XPS / 7.500€ / 55% Peninsula → debe pasar
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    1, "Especialista / CM XPS / 55% / 7.500€ PENINSULA / OK esperado",
    segmento   = "Almacenes Especialistas (PYL)",
    familia    = "CM_XPS_SYC",
    base_eur   = 7500.0,
    territorio = "PENINSULA",
    dto_pct    = 55.0,
    esperado_status = "OK",
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 2: Especialista PYL / CM XPS / 7.500€ / 60% Peninsula → BLOQUEADO (máx 55%)
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    2, "Especialista / CM XPS / 60%>55% / 7.500€ PENINSULA / BLOQUEADO esperado",
    segmento   = "Almacenes Especialistas (PYL)",
    familia    = "CM_XPS_SYC",
    base_eur   = 7500.0,
    territorio = "PENINSULA",
    dto_pct    = 60.0,
    esperado_status = "BLOQUEADO",
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 3: CM XPS + 2 familias → bonus +2 GAMAS activo → 57% debe pasar
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    3, "Especialista / CM XPS +2 GAMAS / 57% / 7.500€ / OK (bonus activo)",
    segmento         = "Almacenes Especialistas (PYL)",
    familia          = "CM_XPS_SYC",
    base_eur         = 7500.0,
    territorio       = "PENINSULA",
    dto_pct          = 57.0,
    familias_pedido  = {"CM_XPS_SYC", "ACUSTICA", "IMPERMEABILIZANTES", "ANTI_IMPACTO_NO_SOUND"},
    esperado_status  = "OK",
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 4: CM XPS + solo 1 otra familia → NO hay bonus → 57% BLOQUEADO
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    4, "Especialista / CM XPS + 1 otra (sin bonus) / 57% / BLOQUEADO esperado",
    segmento         = "Almacenes Especialistas (PYL)",
    familia          = "CM_XPS_SYC",
    base_eur         = 7500.0,
    territorio       = "PENINSULA",
    dto_pct          = 57.0,
    familias_pedido  = {"CM_XPS_SYC", "ACUSTICA"},  # solo 1 otra → sin bonus
    esperado_status  = "BLOQUEADO",
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 5: SOUND / PARQUET / 3.500€ / 58% → OK
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    5, "SOUND / PARQUET solo / 58% / 3.500€ / OK esperado",
    segmento   = "Almacenes e Instaladores (Gama SOUND)",
    familia    = "PARQUET",
    base_eur   = 3500.0,
    territorio = "PENINSULA",
    dto_pct    = 58.0,
    esperado_status = "OK",
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 6: SOUND / PARQUET + OTRA GAMA → 60% OK con bonus
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    6, "SOUND / PARQUET +OTRA GAMA / 60% / 3.500€ / OK (bonus activo)",
    segmento        = "Almacenes e Instaladores (Gama SOUND)",
    familia         = "PARQUET",
    base_eur        = 3500.0,
    territorio      = "PENINSULA",
    dto_pct         = 60.0,
    familias_pedido = {"PARQUET", "ACUSTICA"},
    esperado_status = "OK",
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 7: Generalistas / ACUSTICA / tramo bajo (<1.500€) / Baleares
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    7, "Generalistas / ACUSTICA / tramo bajo / BALEARES / verificar limite",
    segmento   = "Almacenes Generalistas",
    familia    = "ACUSTICA",
    base_eur   = 800.0,
    territorio = "BALEARES",
    dto_pct    = 10.0,   # dtos bajos en tramo bajo → siempre OK
    esperado_status = "OK",
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 8: Constructoras / REFLECTIVOS (alias especifico) / 5.000€ / 45%
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    8, "Constructoras / REFLECTIVOS (alias EXCL.) / 5.000€ / 45% / verificar",
    segmento   = "Empresas Constructoras",
    familia    = "REFLECTIVOS_EXCL_CM_XPS_SYC",
    base_eur   = 5000.0,
    territorio = "PENINSULA",
    dto_pct    = 45.0,
    esperado_status = "OK",  # 45% deberia estar dentro del máximo
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 9: Familia REVIEW_REQUIRED → siempre UNCHECKED (excluida de validacion)
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    9, "Familia REVIEW_REQUIRED → UNCHECKED (excluida, valid=True)",
    segmento   = "Almacenes Generalistas",
    familia    = "REVIEW_REQUIRED",
    base_eur   = 5000.0,
    territorio = "PENINSULA",
    dto_pct    = 99.0,   # descuento absurdo, pero no debe bloquearse
    esperado_status = "OK",  # resolve_familia_excel devuelve None → return OK inmediato
)

# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA 10: Instaladoras / IMPERMEABILIZANTES / tramo alto / 40% → OK
# ─────────────────────────────────────────────────────────────────────────────
prueba(
    10, "Instaladoras / IMPERMEABILIZANTES / 6.000€ / 40% / OK esperado",
    segmento   = "Empresas Instaladoras",
    familia    = "IMPERMEABILIZANTES",
    base_eur   = 6000.0,
    territorio = "PENINSULA",
    dto_pct    = 40.0,
    esperado_status = "OK",
)

# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 85)
print(f"{'#':<3} {'RESULTADO':<6} {'Titulo':<46} {'Status':<12} {'Max%':<7} {'Detalle'}")
print("=" * 85)
for num, badge, titulo, got_status, got_max, msg in results:
    max_str = f"{got_max:.1f}%" if got_max is not None else "—"
    print(f"{num:<3} {'[OK] ' if badge=='PASS' else '[ERR]':<6} {titulo[:46]:<46} {got_status:<12} {max_str:<7} {msg}")
print("=" * 85)
print(f"\nRESULTADO FINAL: {PASS} PASS / {FAIL} FAIL de 10 pruebas")
if FAIL == 0:
    print("Motor comercial respondiendo correctamente en todos los escenarios.")
else:
    print(f"ATENCION: {FAIL} prueba(s) fallida(s). Revisar arriba.")
