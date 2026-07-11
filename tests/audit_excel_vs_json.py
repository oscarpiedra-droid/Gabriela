# -*- coding: utf-8 -*-
"""
audit_excel_vs_json.py
Comparación EXHAUSTIVA: Excel oficial de portes vs SHIPPING_GROUPS del JSON.
Identifica errores en tarifas G4 y G5, y la clasificación de regiones por bucket.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import db.commercial_rules as rules

rules.load_from_json()

ERRORS = []

def sg_price(group, bucket, min_val):
    """Obtiene precio del JSON para un grupo/bucket/tramo."""
    for r in rules.SHIPPING_GROUPS.get(group, []):
        if r['region_bucket_key'] == bucket and abs(r['min_order_eur'] - min_val) < 0.01:
            return r['price_eur']
    return None

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("BLOQUE A: G1/G2/G3 — Verificacion de tarifas (ya validadas, resumen)")
print("="*70)

checks_abc = [
    ("G1_GENERAL",   "A", 0.0,    50.0,  "G1 Bucket-A Grado-1 (< 500EUR)"),
    ("G1_GENERAL",   "B", 0.0,    90.0,  "G1 Bucket-B Grado-1 (< 500EUR)"),
    ("G1_GENERAL",   "A", 500.0,  90.0,  "G1 Bucket-A Grado-2 (500-1500EUR)"),
    ("G1_GENERAL",   "B", 500.0,  120.0, "G1 Bucket-B Grado-2 (500-1500EUR)"),
    ("G1_GENERAL",   "A", 1500.0, 0.0,   "G1 franco (>= 1500EUR)"),
    ("G2_CM_XPS",    "A", 0.0,    90.0,  "G2 Bucket-A (< 3000EUR)"),
    ("G2_CM_XPS",    "B", 0.0,    120.0, "G2 Bucket-B (< 3000EUR)"),
    ("G2_CM_XPS",    "A", 3000.0, 0.0,   "G2 franco (>= 3000EUR)"),
    ("G3_ACUSTICA_AGLO", "A", 0.0,    90.0, "G3 Bucket-A (< 3000EUR)"),
    ("G3_ACUSTICA_AGLO", "B", 0.0,    120.0,"G3 Bucket-B (< 3000EUR)"),
    ("G3_ACUSTICA_AGLO", "A", 3000.0, 0.0,  "G3 franco (>= 3000EUR)"),
]
for group, bucket, min_v, expected, desc in checks_abc:
    actual = sg_price(group, bucket, min_v)
    ok = actual is not None and abs(actual - expected) < 0.01
    print(f"  {'[OK]  ' if ok else '[FAIL]'} {desc}: esperado={expected}EUR obtenido={actual}EUR")
    if not ok:
        ERRORS.append((group, desc, expected, actual))

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("BLOQUE B: G4_ANTIIMPACTO_NO_SOUND — Analisis completo")
print("="*70)
print("""
Excel dice (hoja 'Portes'):
  4. Anti Impacto (NO SOUND) — Franco desde 3.000 EUR
  
  Grado 1 (< 500EUR):
    - 90EUR : Cataluna, Levante, Com.Madrid
    - 150EUR: Aragon-La Rioja, Baleares, Pais Vasco-Nav-Cant,
              Asturias-Galicia, Castilla y Leon, Extremadura,
              Castilla-La Mancha, Andalucia Este, Andalucia Oeste
  
  Grado 2 (500 - 2.999EUR):
    - 120EUR: Cataluna, Levante, Com.Madrid
    - 180EUR: Resto (mismos que Grado 1 en 150EUR)
  
  El JSON actual solo tiene buckets A y B.
  La funcion get_region_bucket(region) clasifica:
    Bucket A: Cataluna, Aragon, Levante, BALEARES, PV-Nav-Can, Madrid, CLM, And.Este
    Bucket B: Asturias-Galicia, CyL, Extremadura, And.Oeste
""")

json_g4 = rules.SHIPPING_GROUPS.get("G4_ANTIIMPACTO_NO_SOUND", [])
print("JSON actual G4:")
for r in json_g4:
    print(f"  bucket={r['region_bucket_key']} [{r['min_order_eur']}-{r['max_order_eur']}] = {r['price_eur']}EUR")

g4_A_g1 = sg_price("G4_ANTIIMPACTO_NO_SOUND", "A", 0.0)
g4_A_g2 = sg_price("G4_ANTIIMPACTO_NO_SOUND", "A", 500.0)
g4_B_g1 = sg_price("G4_ANTIIMPACTO_NO_SOUND", "B", 0.0)
g4_B_g2 = sg_price("G4_ANTIIMPACTO_NO_SOUND", "B", 500.0)

print(f"\nJSON: G4-A Grado1={g4_A_g1}EUR (Cataluna+Aragon+Levante+BALEARES+PV+Madrid+CLM+And.Este)")
print(f"JSON: G4-A Grado2={g4_A_g2}EUR")
print(f"JSON: G4-B Grado1={g4_B_g1}EUR (Asturias-Galicia+CyL+Extremadura+And.Oeste)")
print(f"JSON: G4-B Grado2={g4_B_g2}EUR")
print()
print("Excel separa en 2 grupos distintos a G4, NO en A/B del sistema general:")
print("  Grupo bajo (90/120EUR): solo Cataluna + Levante + Madrid")
print("  Grupo alto (150/180EUR): TODOS los demas (incluyendo Aragon, BALEARES, PV-Nav-Cant, CLM, And.Este...)")
print()

# Regiones mal clasificadas para G4:
mal_g4 = {
    "ARAGON-RIOJA":       ("A", "debia ser D", 90.0, 150.0, 120.0, 180.0),
    "BALEARES":           ("A", "debia ser D", 90.0, 150.0, 120.0, 180.0),
    "NORTE (PV-NAV-CAN)": ("A", "debia ser D", 90.0, 150.0, 120.0, 180.0),
    "CASTILLA LA MANCHA": ("A", "debia ser D", 90.0, 150.0, 120.0, 180.0),
    "ANDALUCIA ESTE":     ("A", "debia ser D", 90.0, 150.0, 120.0, 180.0),
    # Bucket B son correctos para G4 (solo 90/120) pero B no cubre Aragon etc.
    # Y ademas B paga 90/120 cuando deberia pagar 150/180:
    "ASTURIAS-GALICIA":   ("B", "debia ser D", g4_B_g1, 150.0, g4_B_g2, 180.0),
    "CASTILLA Y LEON":    ("B", "debia ser D", g4_B_g1, 150.0, g4_B_g2, 180.0),
    "EXTREMADURA":        ("B", "debia ser D", g4_B_g1, 150.0, g4_B_g2, 180.0),
    "ANDALUCIA OESTE":    ("B", "debia ser D", g4_B_g1, 150.0, g4_B_g2, 180.0),
}

print("Regiones con tarifa INCORRECTA en G4:")
for region, (current_bucket, should_be, g1_actual, g1_ok, g2_actual, g2_ok) in mal_g4.items():
    if g1_actual is None: g1_actual = "N/A"
    if g2_actual is None: g2_actual = "N/A"
    g1_err = g1_actual != g1_ok
    g2_err = g2_actual != g2_ok
    if g1_err or g2_err:
        print(f"  [BUG-G4] {region}: bucket={current_bucket}")
        if g1_err: print(f"           Grado1 actual={g1_actual}EUR / Excel={g1_ok}EUR (diferencia={float(g1_ok)-float(g1_actual) if g1_actual!='N/A' else '?'}EUR)")
        if g2_err: print(f"           Grado2 actual={g2_actual}EUR / Excel={g2_ok}EUR (diferencia={float(g2_ok)-float(g2_actual) if g2_actual!='N/A' else '?'}EUR)")
        ERRORS.append(("G4", region, f"G1={g1_ok}/G2={g2_ok}", f"G1={g1_actual}/G2={g2_actual}"))

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("BLOQUE C: G5_SOUND — Verificacion Baleares en bucket incorrecto")
print("="*70)
print("""
Excel dice (hoja 'Portes'):
  5. Anti Impacto (SOUND) — Franco desde 1.500 EUR
  
  < 1500EUR:
    - 50EUR : Cataluna, Aragon-La Rioja, Levante, PV-Nav-Cant,
              Com.Madrid, Castilla-La Mancha, Andalucia Este
    - 90EUR : BALEARES, Asturias-Galicia, Castilla y Leon,
              Extremadura, Andalucia Oeste
  
  DIFERENCIA CLAVE: Baleares en G5 paga 90EUR (tarifa ALTA),
  a diferencia de G1/G2/G3 donde paga 50/90/90EUR (tarifa BAJA).
""")

json_g5 = rules.SHIPPING_GROUPS.get("G5_SOUND", [])
print("JSON actual G5:")
for r in json_g5:
    print(f"  bucket={r['region_bucket_key']} [{r['min_order_eur']}-{r['max_order_eur']}] = {r['price_eur']}EUR")

g5_A = sg_price("G5_SOUND", "A", 0.0)
g5_B = sg_price("G5_SOUND", "B", 0.0)
baleares_bucket = rules.get_region_bucket(rules.get_region_by_cp("07001"))

print(f"\nBaleares (CP 07xxx): bucket asignado = '{baleares_bucket}'")
print(f"G5 precio Bucket A = {g5_A}EUR (tarifa baja)")
print(f"G5 precio Bucket B = {g5_B}EUR (tarifa alta)")
print()

if baleares_bucket == "A":
    print(f"  [BUG-G5] Baleares paga {g5_A}EUR (Bucket A) pero Excel exige 90EUR (Bucket B)")
    print(f"           Bajo-cobro de {90.0 - (g5_A or 0):.0f}EUR por envio SOUND a Baleares < 1500EUR")
    ERRORS.append(("G5_SOUND", "BALEARES", "90EUR (Bucket B)", f"{g5_A}EUR (Bucket A)"))
else:
    print(f"  [OK] Baleares correctamente en Bucket B para G5")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("BLOQUE D: Mapa completo de regiones por CP")
print("="*70)

from db.commercial_rules import get_region_by_cp, get_region_bucket

test_regions = [
    ("08001", "Barcelona (Cataluna)"),
    ("50001", "Zaragoza (Aragon-Rioja)"),
    ("03001", "Alicante (Levante)"),
    ("07001", "Palma (Baleares)"),
    ("48001", "Bilbao (PV-Nav-Can)"),
    ("28001", "Madrid"),
    ("02001", "Albacete (CLM)"),
    ("23001", "Jaen (And.Este)"),
    ("33001", "Oviedo (Asturias-Galicia)"),
    ("47001", "Valladolid (CyL)"),
    ("06001", "Badajoz (Extremadura)"),
    ("41001", "Sevilla (And.Oeste)"),
]

for cp, desc in test_regions:
    region = get_region_by_cp(cp)
    bucket = get_region_bucket(region)
    g1_price   = sg_price("G1_GENERAL", bucket, 0.0) or 0
    g4_price   = sg_price("G4_ANTIIMPACTO_NO_SOUND", bucket, 0.0) or 0
    g5_price   = sg_price("G5_SOUND", bucket, 0.0) or 0
    print(f"  {desc}: region={region}, bucket={bucket} -> G1={g1_price}E G4={g4_price}E G5={g5_price}E")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("RESUMEN FINAL")
print("="*70)

if ERRORS:
    print(f"\nERRORES CRITICOS detectados: {len(ERRORS)}")
    for group, region, expected, actual in ERRORS:
        print(f"  [{group}] {region}")
        print(f"    Excel espera : {expected}")
        print(f"    JSON tiene   : {actual}")
else:
    print("  Sin errores criticos en G1/G2/G3.")

print("""
PLAN DE ACCION REQUERIDO:
  1. G4_ANTIIMPACTO_NO_SOUND: Definir buckets C y D (o ajustar tarifas A/B).
     - C: Cataluna+Levante+Madrid  -> 90E/120E/0E
     - D: RESTO (incl. Baleares, Aragon, PV-Nav-Can, CLM, And.Este, etc.) -> 150E/180E/0E
  
  2. G5_SOUND: Reclasificar Baleares a Bucket B para este grupo especificamente.
     - Baleares en G5 debe pagar 90EUR < 1500E (no 50EUR como hace ahora).
  
  3. Requiere nueva funcion de bucket por grupo (no una funcion global A/B),
     o los SHIPPING_GROUPS deben usar buckets C y D para G4.
""")
