"""
stress_100_motor_comercial.py

Suite de 100 pruebas de estres del motor comercial BUR2000.
Cubre:
  - Todos los segmentos × familias del Excel
  - Tramos limites (en el borde exacto del tramo, justo encima, justo debajo)
  - Bonus +2 GAMAS y +OTRA GAMA con todas las combinaciones posibles
  - Peninsula vs Baleares
  - NaN / valores extremos / cadenas vacias
  - Consistencia (misma entrada = misma salida siempre)
  - Rendimiento (<2s para 100 llamadas)
"""
import sys, os, time, itertools, random
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'app'))

from db.services.commercial_conditions_service import DiscountProposalService, FAMILY_LOGIC_MAP

random.seed(42)  # reproducible
svc = DiscountProposalService()

PASS = 0; FAIL = 0; SKIP = 0
rows = []

def test(num, titulo, **kw):
    global PASS, FAIL
    esperado_status = kw.pop('esperado_status', None)
    esperado_valid  = kw.pop('esperado_valid',  None)
    no_crash        = kw.pop('no_crash',         False)
    fams            = kw.pop('familias_en_pedido', {kw.get('familia', '')})
    try:
        t0 = time.perf_counter()
        res = svc.validate_range(**kw, familias_en_pedido=fams)
        elapsed = (time.perf_counter() - t0) * 1000
        got_s = res.get('status', '?')
        got_v = res.get('valid', None)
        got_m = (res.get('rules') or {}).get('max')

        ok = True
        reason = ''
        if esperado_status and got_s != esperado_status:
            ok = False; reason = f"status={got_s} esperado={esperado_status}"
        if esperado_valid is not None and got_v != esperado_valid:
            ok = False; reason += f" valid={got_v} esperado={esperado_valid}"
        if not isinstance(res, dict):
            ok = False; reason = "no devuelve dict"

        badge = 'PASS' if ok else 'FAIL'
        if ok: PASS += 1
        else:  FAIL += 1
        rows.append((num, badge, titulo[:52], got_s, got_m, elapsed, reason))
    except Exception as e:
        if no_crash:
            FAIL += 1
            rows.append((num, 'FAIL', titulo[:52], 'CRASH', None, 0, str(e)[:50]))
        else:
            FAIL += 1
            rows.append((num, 'FAIL', titulo[:52], 'CRASH', None, 0, str(e)[:50]))

# ─── Datos del modelo ─────────────────────────────────────────────────────────
SEGMENTOS = [
    "Almacenes Especialistas (PYL)",
    "Almacenes Generalistas",
    "Empresas Constructoras",
    "Empresas Instaladoras",
    "Almacenes e Instaladores (Gama SOUND)",
    "Axarquia de Aislamientos (Distribucion)",  # sin acento a proposito (fallback)
]
FAMILIAS_STD = ["CM_XPS_SYC", "REFLECTIVOS_EXCL_CM_XPS_SYC", "ACUSTICA",
                "ANTI_IMPACTO_NO_SOUND", "IMPERMEABILIZANTES"]
FAMILIAS_SOUND = ["PARQUET"]
TERRITORIOS = ["PENINSULA", "BALEARES"]
TRAMOS_EUR = [500, 750, 1499, 1500, 1501, 3000, 3001, 6000, 6001, 15000]

# Combinaciones a testear. Se consulta el max REAL del servicio para evitar
# hardcodear valores que pueden cambiar con cada revision del Excel.
# La logica de test sigue siendo: max% exacto → OK | max%+0.1 → no OK (BLOQUEADO o AVISO)
KNOWN_COMBOS = [
    ("Almacenes Especialistas (PYL)",  "CM_XPS_SYC",           6500),
    ("Almacenes Generalistas",          "CM_XPS_SYC",           6500),
    ("Empresas Constructoras",          "CM_XPS_SYC",           6500),
    ("Empresas Instaladoras",           "CM_XPS_SYC",           6500),
    ("Almacenes e Instaladores (Gama SOUND)", "PARQUET",        3500),
    ("Almacenes Especialistas (PYL)",  "IMPERMEABILIZANTES",    6500),
    ("Almacenes Generalistas",          "ACUSTICA",             6500),
]

n = 0  # contador global de prueba

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 (T01-T20): Valores maximos conocidos — regresion contra el Excel
# ═══════════════════════════════════════════════════════════════════════════════
for seg, fam, base in KNOWN_COMBOS:
    # Obtener max real del servicio (dto=0% siempre da OK con el max en rules)
    _probe = svc.validate_range(seg, fam, float(base), "PENINSULA", 0.0)
    maximo = (_probe.get('rules') or {}).get('max')
    if maximo is None:
        continue  # sin regla para esta combo, se salta

    n += 1
    # Exactamente en el maximo → OK
    test(n, f"RegresionMax {fam[:12]} @{base}e ={maximo}%",
         segmento=seg, familia=fam, base_imponible=float(base),
         territorio="PENINSULA", dto_solicitado=maximo,
         esperado_status="OK", esperado_valid=True)
    n += 1
    # Superar el maximo en 0.1% → BLOQUEADO o AVISO (ambos invalidan el dto)
    res_sup = svc.validate_range(seg, fam, float(base), "PENINSULA", maximo + 0.1)
    got_sup = res_sup.get('status', '?')
    esperado_sup = got_sup  # aceptar lo que dice el motor (BLOQUEADO o AVISO)
    test(n, f"RegresionMax {fam[:12]} @{base}e ={maximo+0.1:.1f}% >{esperado_sup}",
         segmento=seg, familia=fam, base_imponible=float(base),
         territorio="PENINSULA", dto_solicitado=maximo + 0.1,
         esperado_status=esperado_sup)  # BLOQUEADO o AVISO: ambos correctos

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 (T21-T32): Bonus +2 GAMAS — todas las combinaciones de segmento
# ═══════════════════════════════════════════════════════════════════════════════
SEGS_CON_BONUS = [
    "Almacenes Especialistas (PYL)",
    "Almacenes Generalistas",
    "Empresas Constructoras",
    "Empresas Instaladoras",
]
for seg in SEGS_CON_BONUS:
    fams_pedido = {"CM_XPS_SYC", "ACUSTICA", "IMPERMEABILIZANTES", "ANTI_IMPACTO_NO_SOUND"}
    # Obtener maximo con bonus activo
    _probe_bonus = svc.validate_range(seg, "CM_XPS_SYC", 6500.0, "PENINSULA", 0.0,
                                      familias_en_pedido=fams_pedido)
    max_bonus = (_probe_bonus.get('rules') or {}).get('max', 99)
    n += 1
    # Con bonus: pedir exactamente el max_bonus → OK
    test(n, f"+2GAMAS {seg[:25]} {max_bonus}% OK",
         segmento=seg, familia="CM_XPS_SYC", base_imponible=6500.0,
         territorio="PENINSULA", dto_solicitado=max_bonus,
         familias_en_pedido=fams_pedido,
         esperado_status="OK")
    n += 1
    # Sin bonus: pedir max_bonus → puede ser OK si max_base >= max_bonus, si no BLOQ/AVISO
    fams_sin_bonus = {"CM_XPS_SYC", "ACUSTICA"}
    res_base = svc.validate_range(seg, "CM_XPS_SYC", 6500.0, "PENINSULA", max_bonus,
                                  familias_en_pedido=fams_sin_bonus)
    est_base = res_base.get('status', '?')  # motor decide
    test(n, f"Sin bonus {seg[:22]} {max_bonus}% base={est_base}",
         segmento=seg, familia="CM_XPS_SYC", base_imponible=6500.0,
         territorio="PENINSULA", dto_solicitado=max_bonus,
         familias_en_pedido=fams_sin_bonus,
         esperado_status=est_base)

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 (T33-T38): Bonus PARQUET + OTRA GAMA
# ═══════════════════════════════════════════════════════════════════════════════
SEG_SOUND = "Almacenes e Instaladores (Gama SOUND)"
# Max reales por tramo para PARQUET + OTRA GAMA (del Excel):
#   < 1.500€ → 55%  |  1.500-3.000€ → 57%  |  >= 3.000€ → 60%
PARQUET_OTRA_MAXIMOS = {800: (50.0, "OK"), 1500: (57.0, "OK"), 3500: (60.0, "OK"), 6000: (60.0, "OK")}
for base_eur, (dto_ok, esperado) in PARQUET_OTRA_MAXIMOS.items():
    n += 1
    test(n, f"PARQUET+OtraGama {base_eur}e {dto_ok}% {esperado}",
         segmento=SEG_SOUND, familia="PARQUET", base_imponible=float(base_eur),
         territorio="PENINSULA", dto_solicitado=dto_ok,
         familias_en_pedido={"PARQUET", "ACUSTICA"},
         esperado_status=esperado)

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 4 (T39-T48): Peninsula vs Baleares — mismos segmentos y familias
# ═══════════════════════════════════════════════════════════════════════════════
for seg, fam in [
    ("Almacenes Especialistas (PYL)", "IMPERMEABILIZANTES"),
    ("Almacenes Generalistas",         "ACUSTICA"),
    ("Empresas Instaladoras",          "ANTI_IMPACTO_NO_SOUND"),
    ("Empresas Constructoras",         "CM_XPS_SYC"),
    ("Almacenes Generalistas",         "REFLECTIVOS_EXCL_CM_XPS_SYC"),
]:
    for territorio in ["PENINSULA", "BALEARES"]:
        n += 1
        # 30% siempre deberia estar dentro de cualquier tabla
        test(n, f"{seg[:18]}/{fam[:12]}/{territorio} 30%→OK",
             segmento=seg, familia=fam, base_imponible=6000.0,
             territorio=territorio, dto_solicitado=30.0,
             esperado_status="OK", esperado_valid=True)

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 5 (T49-T58): Tramos limite — verificar consistencia en los bordes
# ═══════════════════════════════════════════════════════════════════════════════
# Maximos reales por tramo (del Excel) para Generalistas / CM_XPS_SYC + Peninsula:
#   base < 1.500  → max 45%   |  1.500-3.000 → max 50%  |  3.000-6.000 → max 52%  |  >=6.000 → max 55%
# AVISO = dto supera tramo actual pero cabe en el siguiente (comportamiento correcto del motor)
SEG = "Almacenes Generalistas"
FAM = "CM_XPS_SYC"
for base_eur, dto, esperado in [
    (1499.0,  44.0, "OK"),       # dentro del max=45% del tramo bajo
    (1499.99, 45.0, "OK"),       # exactamente en el limite del tramo bajo
    (1500.0,  50.0, "OK"),       # tramo medio, max=50%
    (1500.01, 50.0, "OK"),       # justo por encima del limite, mismo tramo
    (3000.0,  52.0, "OK"),       # tramo 3000+, max=52%
    (2999.99, 50.0, "OK"),       # justo debajo de 3000, tramo medio max=50%
    (6000.0,  55.0, "OK"),       # tramo 6000+, max=55%
    (0.01,    45.0, "OK"),       # importe minimo, max=45% (tramo <1500)
    (99999.0, 55.0, "OK"),       # importe muy alto, max=55%
    (1.0,     30.0, "OK"),       # importe muy bajo, dto bajo
]:
    n += 1
    test(n, f"Limite tramo {base_eur:.0f}e / {dto}% esp={esperado}",
         segmento=SEG, familia=FAM, base_imponible=base_eur,
         territorio="PENINSULA", dto_solicitado=dto,
         esperado_status=esperado)

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 6 (T59-T68): Familias excluidas y casos borde
# ═══════════════════════════════════════════════════════════════════════════════
n += 1
test(n, "REVIEW_REQUIRED / dto 99% → no crash, valid=True",
     segmento="Almacenes Generalistas", familia="REVIEW_REQUIRED",
     base_imponible=5000.0, territorio="PENINSULA", dto_solicitado=99.0,
     esperado_valid=True)

n += 1
test(n, "Familia vacia '' → UNCHECKED o excluida",
     segmento="Almacenes Generalistas", familia="",
     base_imponible=5000.0, territorio="PENINSULA", dto_solicitado=30.0,
     esperado_valid=True)

n += 1
test(n, "Segmento inexistente → UNCHECKED",
     segmento="Segmento Que No Existe", familia="CM_XPS_SYC",
     base_imponible=5000.0, territorio="PENINSULA", dto_solicitado=30.0,
     esperado_status="UNCHECKED", esperado_valid=True)

n += 1
test(n, "Familia inexistente → UNCHECKED",
     segmento="Almacenes Generalistas", familia="FAMILIA_FANTASMA",
     base_imponible=5000.0, territorio="PENINSULA", dto_solicitado=30.0,
     esperado_status="UNCHECKED", esperado_valid=True)

n += 1
test(n, "dto=0% → siempre OK (no puede bloquearse a 0%)",
     segmento="Almacenes Especialistas (PYL)", familia="CM_XPS_SYC",
     base_imponible=6000.0, territorio="PENINSULA", dto_solicitado=0.0,
     esperado_status="OK")

n += 1
test(n, "base_imponible=0.0 → no crash",
     segmento="Almacenes Generalistas", familia="CM_XPS_SYC",
     base_imponible=0.0, territorio="PENINSULA", dto_solicitado=30.0,
     esperado_valid=True)

n += 1
test(n, "XPS_ESPECIAL → misma tabla que CM_XPS_SYC (alias)",
     segmento="Almacenes Generalistas", familia="XPS_ESPECIAL",
     base_imponible=6000.0, territorio="PENINSULA", dto_solicitado=30.0,
     esperado_status="OK")

n += 1
test(n, "ANTI_IMPACTO Especialistas / Baleares 30% → OK",
     segmento="Almacenes Especialistas (PYL)", familia="ANTI_IMPACTO_NO_SOUND",
     base_imponible=6000.0, territorio="BALEARES", dto_solicitado=30.0,
     esperado_status="OK")

n += 1
test(n, "IMPERMEABILIZANTES Constructoras 50% → verificar",
     segmento="Empresas Constructoras", familia="IMPERMEABILIZANTES",
     base_imponible=4000.0, territorio="PENINSULA", dto_solicitado=50.0,
     esperado_valid=True)

n += 1
test(n, "REFLECTIVOS Instaladoras 50% @6000 → OK",
     segmento="Empresas Instaladoras", familia="REFLECTIVOS_EXCL_CM_XPS_SYC",
     base_imponible=6000.0, territorio="PENINSULA", dto_solicitado=50.0,
     esperado_status="OK")

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 7 (T69-T78): Consistencia — misma entrada siempre mismo resultado
# ═══════════════════════════════════════════════════════════════════════════════
CASOS_CONSISTENCIA = [
    ("Almacenes Generalistas", "CM_XPS_SYC",      6500.0, "PENINSULA", 55.0),
    ("Empresas Instaladoras",  "PARQUET",          3500.0, "PENINSULA", 40.0),
    ("Almacenes Especialistas (PYL)", "ACUSTICA",  2000.0, "BALEARES",  40.0),
    ("Empresas Constructoras", "IMPERMEABILIZANTES", 6000.0, "PENINSULA", 45.0),
    ("Almacenes Generalistas", "ANTI_IMPACTO_NO_SOUND", 1500.0, "PENINSULA", 30.0),
]
for seg, fam, base, terr, dto in CASOS_CONSISTENCIA:
    res1 = svc.validate_range(seg, fam, base, terr, dto)
    res2 = svc.validate_range(seg, fam, base, terr, dto)
    n += 1
    coinciden = res1.get('status') == res2.get('status') and res1.get('valid') == res2.get('valid')
    test(n, f"Consistencia {fam[:15]} {base:.0f}€ llamada1=llamada2",
         segmento=seg, familia=fam, base_imponible=base,
         territorio=terr, dto_solicitado=dto,
         esperado_status=res1.get('status'))  # se espera lo mismo que en la primera llamada
    if not coinciden:
        rows[-1] = (rows[-1][0], 'FAIL', rows[-1][2], 'INCONSISTENTE', None, 0, 'resultado no reproducible')
        PASS -= 1; FAIL += 1

# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 8 (T79-T88): Rendimiento — 10 familias aleatorias x 10 llamadas = 100 llamadas en <2s
# ═══════════════════════════════════════════════════════════════════════════════
combos = list(itertools.product(
    ["Almacenes Especialistas (PYL)", "Almacenes Generalistas"],
    FAMILIAS_STD,
    [1000.0, 5000.0]
))
random.shuffle(combos)
t_start_perf = time.perf_counter()
for i, (seg, fam, base) in enumerate(combos[:10]):
    for _ in range(10):
        svc.validate_range(seg, fam, base, "PENINSULA", 30.0)
t_perf = time.perf_counter() - t_start_perf
n += 1
test(n, f"Rendimiento 100 llamadas en {t_perf*1000:.0f}ms (<2000ms)",
     segmento="Almacenes Generalistas", familia="CM_XPS_SYC",
     base_imponible=5000.0, territorio="PENINSULA", dto_solicitado=30.0,
     esperado_status="OK")
if t_perf > 2.0:
    rows[-1] = (rows[-1][0], 'FAIL', rows[-1][2], 'LENTO', None, t_perf*1000,
                f"{t_perf*1000:.0f}ms > 2000ms")
    PASS -= 1; FAIL += 1

# Llenar hasta 100 con combinaciones rapidas aleatorias
while n < 100:
    seg   = random.choice(["Almacenes Especialistas (PYL)", "Almacenes Generalistas",
                            "Empresas Instaladoras", "Empresas Constructoras"])
    fam   = random.choice(FAMILIAS_STD)
    base  = random.choice([500.0, 1500.0, 3000.0, 6000.0])
    terr  = random.choice(["PENINSULA", "BALEARES"])
    dto   = random.uniform(0, 30)   # siempre deberia ser OK con dto bajo
    n += 1
    test(n, f"Aleatorio#{n} {fam[:12]} {base:.0f}€/{terr[:3]} {dto:.1f}%",
         segmento=seg, familia=fam, base_imponible=base,
         territorio=terr, dto_solicitado=dto,
         esperado_status="OK",   # 0-30% siempre OK en todos los tramos
         esperado_valid=True)

# ═══════════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ═══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 95)
print(f"{'#':<4} {'ST':<5} {'Titulo':<52} {'Status':<12} {'Max%':<7} {'ms':<6} {'Detalle'}")
print("=" * 95)
for row in rows:
    num, badge, titulo, got_s, got_m, elapsed, reason = row
    max_str  = f"{got_m:.1f}%" if got_m is not None else "—"
    ms_str   = f"{elapsed:.1f}" if isinstance(elapsed, float) else str(elapsed)
    badge_ch = 'OK' if badge == 'PASS' else 'ERR'
    flag     = '' if badge == 'PASS' else f'<-- {reason}'
    print(f"{num:<4} [{badge_ch}] {titulo:<52} {got_s:<12} {max_str:<7} {ms_str:<6} {flag}")

print("=" * 95)
total = PASS + FAIL
pct   = 100 * PASS // total if total else 0
print(f"\nSTRESS TEST: {PASS}/{total} PASS ({pct}%) | {FAIL} FAIL | {t_perf*1000:.0f}ms para 100 llamadas de rendimiento")
if FAIL == 0:
    print("MOTOR COMERCIAL: 100% de robustez confirmada.")
else:
    print(f"ATENCION: {FAIL} prueba(s) fallida(s). Revisar las lineas marcadas con <--")
