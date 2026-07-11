"""
Simulación offline del cálculo de portes con la lógica nueva (total_products_base).
Verifica el fix para el caso SO50168:
  - SKU 07.046A (CM XPS 28mm, G2_CM_XPS): subtotal 3031.20€
  - MANIPULACION (no en SKU_MASTER → G1_GENERAL): subtotal 50€
  - Total factura producto: 3081.20€  → debe ser franco en ambos grupos.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

import db.commercial_rules as rules

rules.load_from_json()

PASS = 0
FAIL = 0

def check(desc, actual, expected):
    global PASS, FAIL
    ok = abs(actual - expected) < 0.01
    symbol = "OK" if ok else "FAIL"
    print(f"  [{symbol}] {desc}: esperado={expected}€, obtenido={actual}€")
    if ok:
        PASS += 1
    else:
        FAIL += 1


def calcular_portes(lines, region_bucket):
    """Replica exacta de la logica post-fix en commercial_service.py (Paso 7)."""
    sg_subtotals = {}
    total_products_base = 0.0
    any_all_franco = False

    for line in lines:
        lname = line.get('name', '').lower()
        if line.get('qty', 0) <= 0 or 'portes' in lname or 'entrega' in lname:
            continue
        sku = line.get('code', '')
        sku_info = rules.SKU_MASTER.get(sku, {})
        if sku_info.get('all_franco'):
            any_all_franco = True
        item_sg = sku_info.get('shipping_group_key', 'G1_GENERAL')
        line_total = line.get('subtotal', 0)
        sg_subtotals[item_sg] = sg_subtotals.get(item_sg, 0) + line_total
        total_products_base += line_total

    if any_all_franco:
        return 0.0, "all_franco", sg_subtotals, total_products_base

    total_shipping = 0.0
    applied = []
    for sg in sg_subtotals:
        sg_rules = rules.SHIPPING_GROUPS.get(sg, [])
        cost = 0.0
        for r in sg_rules:
            if r['region_bucket_key'] == region_bucket and \
               r['min_order_eur'] <= total_products_base <= r['max_order_eur']:
                cost = float(r['price_eur'])
                break
        if cost > 0:
            applied.append(f"{sg}({cost}e)")
        total_shipping += cost

    label = "Franco" if not applied else " + ".join(applied)
    return total_shipping, label, sg_subtotals, total_products_base


# ─────────────────────────────────────────────────────────────────────────────
print("\n===== CASO 1: SO50168 (CM XPS + MANIPULACION) =====")
lines_so50168 = [
    {'code': '07.046A', 'subtotal': 3031.20, 'qty': 300, 'name': 'Air-bur CM XPS 28'},
    {'code': 'MANIPULACION', 'subtotal': 50.0,   'qty': 1,   'name': 'MANIPULACION'},
]
cost, label, sgs, base = calcular_portes(lines_so50168, 'A')
print(f"  sg_subtotals     : {sgs}")
print(f"  total_products_base: {base:.2f}€")
print(f"  Etiqueta         : {label}")
check("SO50168 - Portes (debe ser 0.00)", cost, 0.0)

# ─────────────────────────────────────────────────────────────────────────────
print("\n===== CASO 2: Pedido G1 pequeño (500€ en G1) → 50€ portes =====")
lines_g1_500 = [
    {'code': '01.001', 'subtotal': 499.0, 'qty': 1, 'name': 'Air-bur Termic'},
]
cost2, label2, sgs2, base2 = calcular_portes(lines_g1_500, 'A')
print(f"  total_products_base: {base2:.2f}€")
print(f"  Etiqueta         : {label2}")
check("G1 Small 499€ - Portes (debe ser 50.00)", cost2, 50.0)

# ─────────────────────────────────────────────────────────────────────────────
print("\n===== CASO 3: G1 sobre umbral (1600€) → Franco =====")
lines_g1_over = [
    {'code': '01.001', 'subtotal': 1600.0, 'qty': 1, 'name': 'Air-bur Termic'},
]
cost3, label3, sgs3, base3 = calcular_portes(lines_g1_over, 'A')
print(f"  total_products_base: {base3:.2f}€")
print(f"  Etiqueta         : {label3}")
check("G1 Large 1600€ - Portes (debe ser 0.00)", cost3, 0.0)

# ─────────────────────────────────────────────────────────────────────────────
print("\n===== CASO 4: G2 bajo umbral (2000€) → 90€ portes =====")
lines_g2_low = [
    {'code': '07.046A', 'subtotal': 2000.0, 'qty': 1, 'name': 'CM XPS 28'},
]
cost4, label4, sgs4, base4 = calcular_portes(lines_g2_low, 'A')
print(f"  total_products_base: {base4:.2f}€")
print(f"  Etiqueta         : {label4}")
check("G2 Small 2000€ - Portes (debe ser 90.00)", cost4, 90.0)

# ─────────────────────────────────────────────────────────────────────────────
print("\n===== CASO 5: G2 sobre umbral (3100€) → Franco =====")
lines_g2_over = [
    {'code': '07.046A', 'subtotal': 3100.0, 'qty': 1, 'name': 'CM XPS 28'},
]
cost5, label5, sgs5, base5 = calcular_portes(lines_g2_over, 'A')
print(f"  total_products_base: {base5:.2f}€")
print(f"  Etiqueta         : {label5}")
check("G2 Large 3100€ - Portes (debe ser 0.00)", cost5, 0.0)

# ─────────────────────────────────────────────────────────────────────────────
print("\n===== CASO 6: Mixto G1+G2, total 3200€ (ambos grupos → franco) =====")
lines_mixed = [
    {'code': '01.001',  'subtotal': 1000.0, 'qty': 1, 'name': 'Reflectivo'},
    {'code': '07.046A', 'subtotal': 2200.0, 'qty': 1, 'name': 'CM XPS 28'},
]
cost6, label6, sgs6, base6 = calcular_portes(lines_mixed, 'A')
print(f"  sg_subtotals     : {sgs6}")
print(f"  total_products_base: {base6:.2f}€")
print(f"  Etiqueta         : {label6}")
check("Mixto G1+G2 3200€ - Portes (debe ser 0.00)", cost6, 0.0)

# ─────────────────────────────────────────────────────────────────────────────
print("\n===== CASO 7: Mixto G1+G2, total 1000€ (G1 franco, G2 no) =====")
# G1: umbral 1500€ → con 1000€ total, G1 no es franco (600€ > 500€ → tramo medio 90€)
# G2: umbral 3000€ → con 1000€ total, G2 cobra 90€
# Total esperado: 90 (G1 bucket A medio=90) + 90 (G2) = 180€
# G1_GENERAL reglas: 0<=x<=500 → 50€, 500<=x<=1500 → 90€, >=1500 → 0€
# con 1000€ total: G1 = 90€, G2 = 90€ → total 180€
lines_mixed_low = [
    {'code': '01.001',  'subtotal': 600.0, 'qty': 1, 'name': 'Reflectivo'},
    {'code': '07.046A', 'subtotal': 400.0, 'qty': 1, 'name': 'CM XPS 28'},
]
cost7, label7, sgs7, base7 = calcular_portes(lines_mixed_low, 'A')
print(f"  sg_subtotals     : {sgs7}")
print(f"  total_products_base: {base7:.2f}€")
print(f"  Etiqueta         : {label7}")
check("Mixto G1+G2 1000€ - Portes (debe ser 180.00)", cost7, 180.0)

# ─────────────────────────────────────────────────────────────────────────────
print(f"\n===== RESUMEN: {PASS} OK / {FAIL} FAIL =====\n")
sys.exit(0 if FAIL == 0 else 1)
