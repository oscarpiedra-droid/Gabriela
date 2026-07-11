"""
compare_excel_vs_json.py
Compara EXHAUSTIVAMENTE las tarifas del Excel oficial 
"Nueva Politica de Portes 2026.xlsx" contra los SHIPPING_GROUPS en el JSON.
Detecta errores de importación, valores incorrectos y regiones mal clasificadas.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import db.commercial_rules as rules

rules.load_from_json()

# ═══════════════════════════════════════════════════════════════════════════════
# FUENTE DE VERDAD: Excel "Nueva Política de Portes 2026.xlsx" (hoja "Portes")
# Extraído manualmente celda a celda, incluyendo texto completo de cada gama.
# ═══════════════════════════════════════════════════════════════════════════════

EXCEL_TRUTH = {
    # Gama 1: Air-Bur Termic / Termoreflex / Acusticos / Impermeabilizantes
    # Franco desde: 1.500 €
    # < 500€: Bucket-A = 50€,  Bucket-B = 90€
    # 500-1499€: Bucket-A = 90€, Bucket-B = 120€
    # >= 1500€: 0€
    # NOTA: Baleares clasifica en Bucket-A (junto a Cataluña, Aragón, Levante...)
    "G1_GENERAL": [
        {"min": 0.0,    "max": 500.0,    "bucket": "A", "price": 50.0},
        {"min": 0.0,    "max": 500.0,    "bucket": "B", "price": 90.0},
        {"min": 500.0,  "max": 1500.0,   "bucket": "A", "price": 90.0},
        {"min": 500.0,  "max": 1500.0,   "bucket": "B", "price": 120.0},
        {"min": 1500.0, "max": 999999.0, "bucket": "A", "price": 0.0},
        {"min": 1500.0, "max": 999999.0, "bucket": "B", "price": 0.0},
    ],

    # Gama 2: Air-Bur Termic CM XPS
    # Franco desde: 3.000 €
    # < 3000€: Bucket-A = 90€, Bucket-B = 120€
    # NOTA: Baleares en Bucket-A (misma tarifa que Cataluña, Levante...)
    "G2_CM_XPS": [
        {"min": 0.0,    "max": 3000.0,   "bucket": "A", "price": 90.0},
        {"min": 0.0,    "max": 3000.0,   "bucket": "B", "price": 120.0},
        {"min": 3000.0, "max": 999999.0, "bucket": "A", "price": 0.0},
        {"min": 3000.0, "max": 999999.0, "bucket": "B", "price": 0.0},
    ],

    # Gama 3: Acustica (AGLO)
    # Franco desde: 3.000 €
    # < 3000€: Bucket-A = 90€, Bucket-B = 120€
    "G3_ACUSTICA_AGLO": [
        {"min": 0.0,    "max": 3000.0,   "bucket": "A", "price": 90.0},
        {"min": 0.0,    "max": 3000.0,   "bucket": "B", "price": 120.0},
        {"min": 3000.0, "max": 999999.0, "bucket": "A", "price": 0.0},
        {"min": 3000.0, "max": 999999.0, "bucket": "B", "price": 0.0},
    ],

    # Gama 4: Anti Impacto (NO SOUND)
    # Franco desde: 3.000 €
    # ATENCIÓN: 3 sub-grupos de región, NO solo A/B
    # < 500€ (Grado 1):
    #   "Bucket-C" (Cataluña, Levante, Com.Madrid): 90€
    #   "Bucket-D" (Aragón-La Rioja, Baleares, PV-Nav-Cant, Asturias-Galicia, 
    #               Castilla y León, Extremadura, Castilla-La Mancha, And.Este, And.Oeste): 150€
    # 500-2999€ (Grado 2):
    #   "Bucket-C": 120€
    #   "Bucket-D": 180€
    # >= 3000€: franco (0€)
    # EN EL JSON ACTUAL: se usa solo A/B → BUG: Baleares, Aragón, PV-Nav-Cant
    # deberían ser 150€ (Grado 1) y 180€ (Grado 2), NO 90 y 120.
    # FIX NECESARIO: crear Bucket-C y Bucket-D para G4, o un tercer bucket.
    "G4_ANTIIMPACTO_NO_SOUND": [
        # Bucket-C (Cataluña, Levante, Madrid)
        {"min": 0.0,    "max": 500.0,    "bucket": "C", "price": 90.0},
        {"min": 500.0,  "max": 3000.0,   "bucket": "C", "price": 120.0},
        {"min": 3000.0, "max": 999999.0, "bucket": "C", "price": 0.0},
        # Bucket-D (Resto: Aragón, Baleares, PV-Nav-Cant, Galicia, CyL, Ext, CLM, And.Este, And.Oeste)
        {"min": 0.0,    "max": 500.0,    "bucket": "D", "price": 150.0},
        {"min": 500.0,  "max": 3000.0,   "bucket": "D", "price": 180.0},
        {"min": 3000.0, "max": 999999.0, "bucket": "D", "price": 0.0},
    ],

    # Gama 5: Anti Impacto (SOUND / PARQUET)
    # Franco desde: 1.500 €
    # < 1500€:
    #   "Bucket-A" (Cataluña, Aragón-La Rioja, Levante, PV-Nav-Cant, Madrid, CLM, And.Este): 50€
    #   "Bucket-B" (BALEARES + Asturias-Galicia, Castilla y León, Extremadura, And.Oeste): 90€
    # >= 1500€: 0€
    # ATENCIÓN: Baleares está en Bucket-B (tarifa alta) para SOUND,
    #           a diferencia de G1 y G2 donde Baleares está en Bucket-A.
    "G5_SOUND": [
        {"min": 0.0,    "max": 1500.0,   "bucket": "A", "price": 50.0},
        {"min": 0.0,    "max": 1500.0,   "bucket": "B", "price": 90.0},
        {"min": 1500.0, "max": 999999.0, "bucket": "A", "price": 0.0},
        {"min": 1500.0, "max": 999999.0, "bucket": "B", "price": 0.0},
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
# Mapeado de regiones a bucket según el Excel
# ═══════════════════════════════════════════════════════════════════════════════

REGION_TO_BUCKET = {
    # G1, G2, G3: Baleares en A
    "G1_GENERAL": {
        "CATALUNA": "A", "ARAGON-RIOJA": "A", "LEVANTE": "A", "BALEARES": "A",
        "NORTE (PV-NAV-CAN)": "A", "MADRID": "A", "CASTILLA LA MANCHA": "A",
        "ANDALUCIA ESTE": "A", "ASTURIAS-GALICIA": "B", "CASTILLA Y LEON": "B",
        "EXTREMADURA": "B", "ANDALUCIA OESTE": "B",
    },
    "G2_CM_XPS": {  # mismo que G1
        "CATALUNA": "A", "ARAGON-RIOJA": "A", "LEVANTE": "A", "BALEARES": "A",
        "NORTE (PV-NAV-CAN)": "A", "MADRID": "A", "CASTILLA LA MANCHA": "A",
        "ANDALUCIA ESTE": "A", "ASTURIAS-GALICIA": "B", "CASTILLA Y LEON": "B",
        "EXTREMADURA": "B", "ANDALUCIA OESTE": "B",
    },
    "G3_ACUSTICA_AGLO": {  # mismo que G1
        "CATALUNA": "A", "ARAGON-RIOJA": "A", "LEVANTE": "A", "BALEARES": "A",
        "NORTE (PV-NAV-CAN)": "A", "MADRID": "A", "CASTILLA LA MANCHA": "A",
        "ANDALUCIA ESTE": "A", "ASTURIAS-GALICIA": "B", "CASTILLA Y LEON": "B",
        "EXTREMADURA": "B", "ANDALUCIA OESTE": "B",
    },
    # G4: 3 grupos distintos
    "G4_ANTIIMPACTO_NO_SOUND": {
        "CATALUNA": "C", "LEVANTE": "C", "MADRID": "C",
        "ARAGON-RIOJA": "D", "BALEARES": "D", "NORTE (PV-NAV-CAN)": "D",
        "ASTURIAS-GALICIA": "D", "CASTILLA Y LEON": "D", "EXTREMADURA": "D",
        "CASTILLA LA MANCHA": "D", "ANDALUCIA ESTE": "D", "ANDALUCIA OESTE": "D",
    },
    # G5 (SOUND): Baleares en B (tarifa alta), al contrario que G1/G2
    "G5_SOUND": {
        "CATALUNA": "A", "ARAGON-RIOJA": "A", "LEVANTE": "A",
        "NORTE (PV-NAV-CAN)": "A", "MADRID": "A", "CASTILLA LA MANCHA": "A",
        "ANDALUCIA ESTE": "A",
        "BALEARES": "B",  # ← DIFERENCIA respecto a G1/G2
        "ASTURIAS-GALICIA": "B", "CASTILLA Y LEON": "B",
        "EXTREMADURA": "B", "ANDALUCIA OESTE": "B",
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# COMPARACIÓN JSON actual vs Excel
# ═══════════════════════════════════════════════════════════════════════════════

print("="*70)
print("COMPARACION SHIPPING_GROUPS: JSON actual vs Excel oficial")
print("="*70)

ERRORS = []
WARNINGS = []

for group_name, expected_rules in EXCEL_TRUTH.items():
    json_rules = rules.SHIPPING_GROUPS.get(group_name, [])
    print(f"\n--- {group_name} ---")

    for er in expected_rules:
        # Buscar regla equivalente en JSON
        match = None
        for jr in json_rules:
            if (jr['region_bucket_key'] == er['bucket'] and
                abs(jr['min_order_eur'] - er['min']) < 0.01 and
                abs(jr['max_order_eur'] - er['max']) < 0.01):
                match = jr
                break

        label = f"bucket={er['bucket']} [{er['min']}-{er['max']}]"
        if match is None:
            print(f"  [MISS] {label} → no existe en JSON (esperado: {er['price']}EUR)")
            ERRORS.append((group_name, f"Regla MISSING: {label}", er['price'], "N/A"))
        elif abs(match['price_eur'] - er['price']) > 0.01:
            print(f"  [ERR]  {label} → JSON={match['price_eur']}EUR / EXCEL={er['price']}EUR")
            ERRORS.append((group_name, label, er['price'], match['price_eur']))
        else:
            print(f"  [OK]   {label} = {er['price']}EUR")

    # Detectar reglas EXTRA en JSON que no están en Excel
    for jr in json_rules:
        found = any(
            abs(er['min'] - jr['min_order_eur']) < 0.01 and
            abs(er['max'] - jr['max_order_eur']) < 0.01 and
            er['bucket'] == jr['region_bucket_key']
            for er in expected_rules
        )
        if not found:
            print(f"  [XTRA] bucket={jr['region_bucket_key']} [{jr['min_order_eur']}-{jr['max_order_eur']}] "
                  f"= {jr['price_eur']}EUR → en JSON pero NO en Excel")
            WARNINGS.append((group_name, f"Regla EXTRA bucket={jr['region_bucket_key']}",
                             jr['min_order_eur'], jr['price_eur']))

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICACIÓN ESPECIAL: asignación de Baleares al bucket correcto
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("VERIFICACION CRITICA: Baleares en bucket correcto por grupo")
print("="*70)

from app.db.commercial_rules import get_region_by_cp, get_region_bucket

# CP de Baleares: 07001
region_baleares = get_region_by_cp("07001")
bucket_baleares = get_region_bucket(region_baleares)

print(f"  CP 07001 → region='{region_baleares}' → bucket='{bucket_baleares}'")
print(f"  Segun Excel:")
print(f"    G1/G2/G3: Baleares debe ser Bucket A (50/90/90EUR bajo umbral)")
print(f"    G4: Baleares debe ser Bucket D (150/180EUR bajo umbral)")
print(f"    G5(Sound): Baleares debe ser Bucket B (90EUR bajo umbral)")
print()

if bucket_baleares == "A":
    print("  [OK] G1/G2/G3: Baleares → Bucket A — CORRECTO para esas gamas")
    print("  [WARN] G4: Baleares se asigna A, pero Excel dice tarifa alta (Bucket D). BUG si hay G4 en Baleares.")
    print("  [WARN] G5(SOUND): Baleares se asigna A (50EUR), pero Excel dice Bucket B (90EUR). BUG para SOUND.")
    WARNINGS.append(("G4", "Baleares asignada a Bucket A pero debe ser D (tarifa alta)", "D", bucket_baleares))
    WARNINGS.append(("G5_SOUND", "Baleares asignada a Bucket A (50EUR) pero Excel dice B (90EUR)", "B", bucket_baleares))
elif bucket_baleares == "B":
    print("  [OK] G5/G4: correcto para esos grupos")
    print("  [ERR] G1/G2/G3: Baleares → Bucket B, pero Excel dice A (50EUR). Cobro excesivo.")
    ERRORS.append(("G1/G2/G3", "Baleares en Bucket B cuando debería ser A", "A", bucket_baleares))

# ═══════════════════════════════════════════════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("RESUMEN DE DISCREPANCIAS")
print("="*70)

if ERRORS:
    print(f"\nERRORES CRITICOS ({len(ERRORS)}):")
    for group, desc, expected, actual in ERRORS:
        print(f"  [{group}] {desc}")
        print(f"    EXCEL={expected} | JSON={actual}")
else:
    print("\n  Sin errores criticos.")

if WARNINGS:
    print(f"\nWARNINGS ({len(WARNINGS)}):")
    for group, desc, expected, actual in WARNINGS:
        print(f"  [{group}] {desc}")
        print(f"    ESPERADO={expected} | ACTUAL={actual}")
else:
    print("  Sin warnings.")

total = len(ERRORS) + len(WARNINGS)
print(f"\nTotal discrepancias: {total}")
