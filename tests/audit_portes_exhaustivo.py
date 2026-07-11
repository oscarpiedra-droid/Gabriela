"""
audit_portes_exhaustivo.py
Auditoría exhaustiva del motor de portes post-fix.
Cubre: umbrales exactos, grupos mixtos, líneas de servicio,
excepciones E1/E2/E3, bucket A vs B, casos borde.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))
import db.commercial_rules as rules
rules.load_from_json()

PASS_C = 0; FAIL_C = 0; WARN_C = 0; bugs = []

def check(desc, actual, expected, severity="OK"):
    global PASS_C, FAIL_C, WARN_C
    ok = abs(actual - expected) < 0.01
    tag = "[OK]  " if ok else ("[WARN]" if severity == "WARN" else "[FAIL]")
    if ok:      PASS_C += 1
    elif severity == "WARN": WARN_C += 1; bugs.append(("WARN", desc, expected, actual))
    else:       FAIL_C += 1; bugs.append(("FAIL", desc, expected, actual))
    print(f"{tag} {desc}: esperado={expected}EUR obtenido={actual:.2f}EUR")

def portes(lines, bucket='A'):
    """
    Replica EXACTA del motor post-fix (Paso 7 de commercial_service.py).
    NOTA: actualmente sg_subtotals incluye lineas NO en SKU_MASTER (ej: MANIPULACION)
    usando G1_GENERAL por defecto -- esto es un BUG detectado en la auditoria.
    """
    sg = {}; base = 0.0; any_franco = False
    for l in lines:
        lname = l.get('name','').lower()
        if l.get('qty',0) <= 0 or 'portes' in lname or 'entrega' in lname:
            continue
        info = rules.SKU_MASTER.get(l['code'], {})
        if info.get('all_franco'):
            any_franco = True
        g = info.get('shipping_group_key', 'G1_GENERAL')  # BUG: MANIPULACION -> G1_GENERAL
        sg[g] = sg.get(g, 0) + l['sub']
        base += l['sub']
    if any_franco:
        return 0.0, base, sg
    total = 0.0
    for g in sg:
        for r in rules.SHIPPING_GROUPS.get(g, []):
            if r['region_bucket_key'] == bucket and r['min_order_eur'] <= base <= r['max_order_eur']:
                total += float(r['price_eur']); break
    return total, base, sg

def portes_fixed(lines, bucket='A'):
    """
    Motor CORREGIDO: MANIPULACION y servicios no en SKU_MASTER
    contribuyen a total_products_base pero NO generan un grupo propio.
    """
    sg = {}; base = 0.0; any_franco = False
    for l in lines:
        lname = l.get('name','').lower()
        if l.get('qty',0) <= 0 or 'portes' in lname or 'entrega' in lname:
            continue
        info = rules.SKU_MASTER.get(l['code'], {})
        base += l['sub']  # TODOS los no-portes suman al total
        if not info:
            continue       # servicio/accesorio: suma al total pero NO crea grupo
        if info.get('all_franco'):
            any_franco = True
        g = info.get('shipping_group_key', 'G1_GENERAL')
        sg[g] = sg.get(g, 0) + l['sub']
    if any_franco:
        return 0.0, base, sg
    total = 0.0
    for g in sg:
        for r in rules.SHIPPING_GROUPS.get(g, []):
            if r['region_bucket_key'] == bucket and r['min_order_eur'] <= base <= r['max_order_eur']:
                total += float(r['price_eur']); break
    return total, base, sg

def E1_gratis(lines, zone='peninsula', bucket='A'):
    """Excepcion E1: todas las lineas de PRODUCTO real >= 30% dto -> franco."""
    min_dto = 30.0 if zone == 'peninsula' else 25.0
    any_real = False
    for l in lines:
        if l.get('qty',0) <= 0: continue
        lname = l.get('name','').lower()
        if 'portes' in lname or 'entrega' in lname: continue
        # CORRECCION: saltar servicios no en SKU_MASTER
        if not rules.SKU_MASTER.get(l['code']): continue
        any_real = True
        if l.get('dto', 0) < min_dto - 0.01:
            return False
    return any_real  # True solo si hay al menos una linea real y todas >= min_dto

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 1: Umbrales exactos G1_GENERAL (Bucket A)")
print("="*70)

# G1: 0 <= x <= 500 -> 50EUR
c,b,_ = portes([{'code':'01.001','sub':499.99,'qty':1,'name':'Reflectivo'}], 'A')
check("G1-A 499.99EUR -> 50EUR", c, 50.0)

c,b,_ = portes([{'code':'01.001','sub':500.0,'qty':1,'name':'Reflectivo'}], 'A')
check("G1-A 500.00EUR -> 90EUR (limite inferior sube al tramo medio)", c, 90.0)

# G1: 500 <= x <= 1500 -> 90EUR
c,b,_ = portes([{'code':'01.001','sub':1000.0,'qty':1,'name':'Reflectivo'}], 'A')
check("G1-A 1000EUR -> 90EUR", c, 90.0)

c,b,_ = portes([{'code':'01.001','sub':1499.99,'qty':1,'name':'Reflectivo'}], 'A')
check("G1-A 1499.99EUR -> 90EUR", c, 90.0)

c,b,_ = portes([{'code':'01.001','sub':1500.0,'qty':1,'name':'Reflectivo'}], 'A')
check("G1-A 1500.00EUR -> 0EUR (franco)", c, 0.0)

c,b,_ = portes([{'code':'01.001','sub':9999.0,'qty':1,'name':'Reflectivo'}], 'A')
check("G1-A 9999EUR -> 0EUR", c, 0.0)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 2: Umbrales exactos G1_GENERAL (Bucket B - regiones pesadas)")
print("="*70)

c,b,_ = portes([{'code':'01.001','sub':499.0,'qty':1,'name':'Reflectivo'}], 'B')
check("G1-B 499EUR -> 90EUR", c, 90.0)

c,b,_ = portes([{'code':'01.001','sub':500.0,'qty':1,'name':'Reflectivo'}], 'B')
check("G1-B 500EUR -> 120EUR (tramo medio)", c, 120.0)

c,b,_ = portes([{'code':'01.001','sub':1500.0,'qty':1,'name':'Reflectivo'}], 'B')
check("G1-B 1500EUR -> 0EUR (franco)", c, 0.0)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 3: Umbrales exactos G2_CM_XPS")
print("="*70)

c,b,_ = portes([{'code':'07.046A','sub':2999.99,'qty':1,'name':'CM XPS 28'}], 'A')
check("G2-A 2999.99EUR -> 90EUR", c, 90.0)

c,b,_ = portes([{'code':'07.046A','sub':3000.0,'qty':1,'name':'CM XPS 28'}], 'A')
check("G2-A 3000.00EUR -> 0EUR (franco exacto)", c, 0.0)

c,b,_ = portes([{'code':'07.046A','sub':3000.01,'qty':1,'name':'CM XPS 28'}], 'A')
check("G2-A 3000.01EUR -> 0EUR (franco)", c, 0.0)

c,b,_ = portes([{'code':'07.046A','sub':2999.0,'qty':1,'name':'CM XPS 28'}], 'B')
check("G2-B 2999EUR -> 120EUR", c, 120.0)

c,b,_ = portes([{'code':'07.046A','sub':3000.0,'qty':1,'name':'CM XPS 28'}], 'B')
check("G2-B 3000EUR -> 0EUR (franco)", c, 0.0)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 4: Pedidos MIXTOS G1+G2 - comportamiento con total")
print("="*70)

# Mixto: G1=1000, G2=2000, total=3000 -> G2 franco (>=3000), G1 -> tramo 500-1500 -> 90
# Con total_products_base = 3000 y G1 threshold 1500 -> G1 tambien franco
c,b,_ = portes([{'code':'01.001','sub':1000.0,'qty':1,'name':'Reflectivo'},
                 {'code':'07.046A','sub':2000.0,'qty':1,'name':'CM XPS'}], 'A')
check("Mixto G1+G2 total=3000EUR -> 0EUR (ambos franco)", c, 0.0)

# Mixto: G1=500, G2=2000, total=2500 -> G2 < 3000 -> 90; G1 base 2500 >= 1500 -> franco
# Resultado esperado: 0 (G1 franco por base>1500) + 90 (G2 < 3000) = 90
c,b,_ = portes([{'code':'01.001','sub':500.0,'qty':1,'name':'Reflectivo'},
                 {'code':'07.046A','sub':2000.0,'qty':1,'name':'CM XPS'}], 'A')
check("Mixto G1+G2 total=2500EUR -> 90EUR (G1 franco, G2 no)", c, 90.0)

# Mixto: G1=300, G2=400, total=700 -> G1: 700 en tramo 500-1500 -> 90; G2: 700 < 3000 -> 90 = 180
c,b,_ = portes([{'code':'01.001','sub':300.0,'qty':1,'name':'Reflectivo'},
                 {'code':'07.046A','sub':400.0,'qty':1,'name':'CM XPS'}], 'A')
check("Mixto G1+G2 total=700EUR -> 180EUR (90+90)", c, 180.0)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 5: BUG DETECTADO - Lineas de servicio (MANIPULACION) en sg_subtotals")
print("  Motor ACTUAL vs Motor CORREGIDO")
print("="*70)

manip_lines = [
    {'code':'07.046A','sub':3031.20,'qty':300,'name':'CM XPS 28'},
    {'code':'MANIPULACION','sub':50.0,'qty':1,'name':'MANIPULACION servicio'},
]

c_actual, base_actual, sg_actual = portes(manip_lines, 'A')
c_fixed, base_fixed, sg_fixed   = portes_fixed(manip_lines, 'A')

print(f"  [INFO] Motor ACTUAL:   sg={sg_actual}, base={base_actual:.2f}, coste={c_actual:.2f}EUR")
print(f"  [INFO] Motor CORREGIDO: sg={sg_fixed},  base={base_fixed:.2f}, coste={c_fixed:.2f}EUR")

if abs(c_actual - 0.0) > 0.01:
    print(f"  [BUG] Motor actual genera {c_actual}EUR para SO50168 (MANIPULACION crea grupo G1_GENERAL 50EUR)")
    bugs.append(("BUG-ACTUAL", "MANIPULACION crea grupo G1 ficticio", 0.0, c_actual))
else:
    print("  [OK] Motor actual: SO50168 ya es 0EUR (el fix anterior resolvio el caso total>3000)")

check("Motor CORREGIDO: SO50168 + MANIPULACION -> 0EUR", c_fixed, 0.0)

# Caso donde BUG actual SI falla: G2 2000 + MANIPULACION 100 = total 2100
# Motor actual: sg={G2: 2000, G1: 100}, base=2100 -> G2: 90, G1: 90 = 180EUR (INCORRECTO, G1 es ficticio)
# Motor correcto: sg={G2: 2000}, base=2100 -> G2: 90 = 90EUR
manip_g2_low = [
    {'code':'07.046A','sub':2000.0,'qty':1,'name':'CM XPS 28'},
    {'code':'MANIPULACION','sub':100.0,'qty':1,'name':'MANIPULACION servicio'},
]
c_actual2, _, sg_act2 = portes(manip_g2_low, 'A')
c_fixed2, _, sg_fix2  = portes_fixed(manip_g2_low, 'A')
print(f"\n  [INFO] G2 2000 + MANIP 100, motor actual:   sg={sg_act2}, coste={c_actual2:.2f}EUR")
print(f"  [INFO] G2 2000 + MANIP 100, motor corregido: sg={sg_fix2}, coste={c_fixed2:.2f}EUR")
if abs(c_actual2 - 90.0) > 0.01:
    print(f"  [BUG] Motor actual cobra {c_actual2}EUR (MANIPULACION crea cargo ficticio +90EUR)")
    bugs.append(("BUG-KEY", "MANIPULACION crea cargo G1 ficticio (G2+MANIP caso bajo)", 90.0, c_actual2))
else:
    print("  [OK] Motor actual no genera cargo ficticio en este caso")
check("Motor CORREGIDO: G2 2000 + MANIP 100 -> 90EUR", c_fixed2, 90.0)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 6: BUG DETECTADO - all_lines_high_discount con MANIPULACION (0% dto)")
print("="*70)

# Escenario: producto real con 30%+ dto, MANIPULACION con 0% dto
# Motor ACTUAL: all_lines_high_discount = False (MANIPULACION rompe la condicion)
# Motor CORRECTO: all_lines_high_discount = True (MANIPULACION se ignora)

lines_E1_test = [
    {'code':'01.001','qty':1,'dto':35.0,'name':'Reflectivo'},
    {'code':'MANIPULACION','qty':1,'dto':0.0,'name':'MANIPULACION servicio'},
]

min_dto = 30.0
# Motor ACTUAL
all_high_actual = True
for l in lines_E1_test:
    lname = l.get('name','').lower()
    if l.get('qty',0) > 0 and 'portes' not in lname and 'entrega' not in lname:
        if l.get('dto',0) < min_dto - 0.01:
            all_high_actual = False

# Motor CORREGIDO (saltar no-SKU_MASTER)
all_high_fixed = True
for l in lines_E1_test:
    lname = l.get('name','').lower()
    if l.get('qty',0) > 0 and 'portes' not in lname and 'entrega' not in lname:
        if not rules.SKU_MASTER.get(l['code']):
            continue  # servicio: ignorar en check de dto
        if l.get('dto',0) < min_dto - 0.01:
            all_high_fixed = False

print(f"  [INFO] Motor actual: all_lines_high_discount = {all_high_actual} (BUG: MANIPULACION 0% invalida la excepcion)")
print(f"  [INFO] Motor corregido: all_lines_high_discount = {all_high_fixed} (OK: MANIPULACION ignorada)")

if all_high_actual:
    print("  [OK] Motor actual no tiene bug E1 en este caso")
else:
    print("  [BUG] Motor actual: E1 falla por MANIPULACION con 0% dto")
    bugs.append(("BUG-E1", "all_lines_high_discount false por MANIPULACION 0% dto", True, False))

if all_high_fixed:
    print("  [OK] Motor corregido: E1 funciona correctamente")
else:
    print("  [FAIL] Motor corregido: E1 sigue fallando")

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 7: Excepcion E1 - Dto lineal >= 30% (Peninsula)")
print("="*70)

# Solo verificamos la logica de E1_gratis corregida
lines_e1_ok = [
    {'code':'01.001','qty':1,'dto':30.0,'name':'Reflectivo','sub':1000.0},
    {'code':'07.046A','qty':1,'dto':35.0,'name':'CM XPS','sub':500.0},
]
e1 = E1_gratis(lines_e1_ok, 'peninsula', 'A')
print(f"  Todos reales 30%+: E1={e1}", "[OK]" if e1 else "[FAIL]")
if not e1: bugs.append(("FAIL", "E1 no activa con todos >= 30%", True, e1))

lines_e1_nok = [
    {'code':'01.001','qty':1,'dto':29.9,'name':'Reflectivo','sub':1000.0},
    {'code':'07.046A','qty':1,'dto':35.0,'name':'CM XPS','sub':500.0},
]
e1b = E1_gratis(lines_e1_nok, 'peninsula', 'A')
print(f"  Una linea 29.9%: E1={e1b}", "[OK]" if not e1b else "[FAIL]")
if e1b: bugs.append(("FAIL", "E1 activa con una linea < 30%", False, e1b))

# E1 con MANIPULACION (correcto: ignorarla)
lines_e1_manip = [
    {'code':'01.001','qty':1,'dto':33.0,'name':'Reflectivo','sub':800.0},
    {'code':'MANIPULACION','qty':1,'dto':0.0,'name':'MANIPULACION','sub':50.0},
]
e1c = E1_gratis(lines_e1_manip, 'peninsula', 'A')
print(f"  Real 33% + MANIPULACION 0% (corregido): E1={e1c}", "[OK]" if e1c else "[FAIL]")

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 8: Regiones bucket B - G1 y G2 umbrales iguales, costes diferentes")
print("="*70)

c,b,_ = portes([{'code':'01.001','sub':400.0,'qty':1,'name':'Reflectivo'}], 'B')
check("G1-B 400EUR -> 90EUR (Galicia/Extremadura/etc)", c, 90.0)

c,b,_ = portes([{'code':'01.001','sub':800.0,'qty':1,'name':'Reflectivo'}], 'B')
check("G1-B 800EUR -> 120EUR", c, 120.0)

c,b,_ = portes([{'code':'07.046A','sub':1500.0,'qty':1,'name':'CM XPS'}], 'B')
check("G2-B 1500EUR -> 120EUR", c, 120.0)

c,b,_ = portes([{'code':'07.046A','sub':3000.0,'qty':1,'name':'CM XPS'}], 'B')
check("G2-B 3000EUR -> 0EUR (franco)", c, 0.0)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 9: G3_ACUSTICA_AGLO (umbral 3000EUR igual que G2)")
print("="*70)

# Buscar un SKU de G3
g3_sku = next((code for code, info in rules.SKU_MASTER.items() if info.get('shipping_group_key') == 'G3_ACUSTICA_AGLO'), None)
print(f"  [INFO] SKU G3 encontrado: {g3_sku}")

if g3_sku:
    c,b,_ = portes([{'code':g3_sku,'sub':2500.0,'qty':1,'name':'Acustica'}], 'A')
    check("G3-A 2500EUR -> 90EUR", c, 90.0)
    c,b,_ = portes([{'code':g3_sku,'sub':3000.0,'qty':1,'name':'Acustica'}], 'A')
    check("G3-A 3000EUR -> 0EUR (franco)", c, 0.0)
else:
    print("  [WARN] No se encontro SKU G3 en SKU_MASTER para verificar", "(WARN)")
    WARN_C += 1

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 10: G5_SOUND (umbral 1500EUR igual que G1)")
print("="*70)

g5_sku = next((code for code, info in rules.SKU_MASTER.items() if info.get('shipping_group_key') == 'G5_SOUND'), None)
print(f"  [INFO] SKU G5 encontrado: {g5_sku}")

if g5_sku:
    c,b,_ = portes([{'code':g5_sku,'sub':1000.0,'qty':1,'name':'Sound'}], 'A')
    check("G5-A 1000EUR -> 50EUR", c, 50.0)
    c,b,_ = portes([{'code':g5_sku,'sub':1500.0,'qty':1,'name':'Sound'}], 'A')
    check("G5-A 1500EUR -> 0EUR (franco)", c, 0.0)
else:
    print("  [WARN] No se encontro SKU G5 en SKU_MASTER")
    WARN_C += 1

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 11: Pedido vacío / sin líneas reales")
print("="*70)

c,b,_ = portes([], 'A')
check("Pedido sin lineas -> 0EUR", c, 0.0)

c,b,_ = portes([{'code':'MANIPULACION','sub':200.0,'qty':1,'name':'MANIPULACION'}], 'A')
c2,b2,sg2 = portes_fixed([{'code':'MANIPULACION','sub':200.0,'qty':1,'name':'MANIPULACION'}], 'A')
print(f"  Solo MANIPULACION - motor actual: {c:.2f}EUR (sg={portes([{'code':'MANIPULACION','sub':200.0,'qty':1,'name':'MANIPULACION'}],'A')[2]})")
print(f"  Solo MANIPULACION - motor correg: {c2:.2f}EUR (sg={sg2})")
if abs(c - 0.0) > 0.01:
    bugs.append(("BUG-MANIP-ONLY", "Solo MANIPULACION genera portes ficticios", 0.0, c))
    print("  [BUG] Motor actual cobra por pedido de solo servicios")
if abs(c2 - 0.0) > 0.01:
    print("  [BUG-FIXED] Motor corregido tambien falla caso solo-servicios")
else:
    print("  [OK] Motor corregido: 0EUR para pedido de solo servicios")

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("BLOQUE 12: Consistencia de rangos en SHIPPING_GROUPS (no hay huecos ni solapamientos criticos)")
print("="*70)

for group_name, group_rules in rules.SHIPPING_GROUPS.items():
    for bucket in ['A', 'B']:
        bucket_rules = sorted([r for r in group_rules if r['region_bucket_key'] == bucket],
                               key=lambda r: r['min_order_eur'])
        if not bucket_rules:
            continue
        # Verificar que 0.01 esta cubierto
        test_vals = [0.01, 1.0, 100.0, 499.0, 500.0, 1499.0, 1500.0, 2999.0, 3000.0, 5000.0]
        for val in test_vals:
            matches = [r for r in bucket_rules if r['min_order_eur'] <= val <= r['max_order_eur']]
            if not matches:
                print(f"  [BUG] {group_name}/{bucket}: {val}EUR no esta cubierto por ningun tramo!")
                bugs.append(("BUG-GAPS", f"{group_name}/{bucket} hueco en {val}EUR", 1, 0))

print("  [OK] Verificacion de cobertura de rangos completada")

# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("RESUMEN DE AUDITORÍA")
print("="*70)
print(f"  Tests OK  : {PASS_C}")
print(f"  Warnings  : {WARN_C}")
print(f"  Failures  : {FAIL_C}")
print()
if bugs:
    print("BUGS / ISSUES DETECTADOS:")
    for severity, desc, expected, actual in bugs:
        print(f"  [{severity}] {desc}")
        print(f"           esperado={expected} | obtenido={actual}")
else:
    print("  Sin bugs detectados.")

print()
sys.exit(0 if FAIL_C == 0 else 1)
