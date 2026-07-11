# -*- coding: utf-8 -*-
"""
patch_portes_abril2026.py
Actualiza SHIPPING_GROUPS en commercial_rules_v2.json con las tarifas
vigentes desde 01/04/2026 (hoja 'Portes Abril 2026' del Excel maestro).

Cambios respecto a Enero 2026:
  G1: A Grado1 50->60, A Grado2 90->110, B Grado1 90->110, B Grado2 120->140
  G2: A 90->110, B 120->140
  G3: SIN CAMBIOS (90/120 igual)
  G4: C Grado1 90->110, C Grado2 120->140, D Grado1 150->180, D Grado2 180->200
  G5: A 50->60, B 90->110
"""
import sys, os, re, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

BASE = os.path.join(os.path.dirname(__file__), '..', 'app', 'db', 'commercial_rules_v2.json')

with open(BASE, 'r', encoding='utf-8') as f:
    raw = re.sub(r'\bNaN\b', 'null', f.read())
data = json.loads(raw)

SG = data['SHIPPING_GROUPS']

# ── G1: Air-Bur Termic / Termoreflex / Acústicos / Impermeabilizantes ─────────
# Franco desde 1.500€ (sin cambio). Tarifas subidas.
SG['G1_GENERAL'] = [
    {"min_order_eur": 1500.0, "max_order_eur": 999999.0, "region_bucket_key": "A", "price_eur": 0.0},
    {"min_order_eur": 1500.0, "max_order_eur": 999999.0, "region_bucket_key": "B", "price_eur": 0.0},
    {"min_order_eur": 500.0,  "max_order_eur": 1500.0,   "region_bucket_key": "A", "price_eur": 110.0},
    {"min_order_eur": 500.0,  "max_order_eur": 1500.0,   "region_bucket_key": "B", "price_eur": 140.0},
    {"min_order_eur": 0.0,    "max_order_eur": 500.0,    "region_bucket_key": "A", "price_eur": 60.0},
    {"min_order_eur": 0.0,    "max_order_eur": 500.0,    "region_bucket_key": "B", "price_eur": 110.0},
]

# ── G2: CM XPS ────────────────────────────────────────────────────────────────
# Franco desde 3.000€ (sin cambio). Tarifas subidas.
SG['G2_CM_XPS'] = [
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "A", "price_eur": 0.0},
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "B", "price_eur": 0.0},
    {"min_order_eur": 0.0,    "max_order_eur": 3000.0,   "region_bucket_key": "A", "price_eur": 110.0},
    {"min_order_eur": 0.0,    "max_order_eur": 3000.0,   "region_bucket_key": "B", "price_eur": 140.0},
]

# ── G3: Acústica (AGLO) ───────────────────────────────────────────────────────
# SIN CAMBIOS (90/120€). El Excel Abril 2026 mantiene las mismas tarifas.
# (Ya está correcto en el JSON, solo lo dejamos explícito)
SG['G3_ACUSTICA_AGLO'] = [
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "A", "price_eur": 0.0},
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "B", "price_eur": 0.0},
    {"min_order_eur": 0.0,    "max_order_eur": 3000.0,   "region_bucket_key": "A", "price_eur": 90.0},
    {"min_order_eur": 0.0,    "max_order_eur": 3000.0,   "region_bucket_key": "B", "price_eur": 120.0},
]

# ── G4: Anti Impacto (NO SOUND) ───────────────────────────────────────────────
# Franco desde 3.000€. Buckets C y D (no A/B).
# C: SOLO Cataluña + Levante + Madrid
# D: RESTO (Aragón, Baleares, PV-Nav-Can, CLM, And.Este, Asturias, CyL, Ext., And.Oeste)
SG['G4_ANTIIMPACTO_NO_SOUND'] = [
    # ─ Bucket C: Cataluña + Levante + Madrid ─
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "C", "price_eur": 0.0},
    {"min_order_eur": 500.0,  "max_order_eur": 3000.0,   "region_bucket_key": "C", "price_eur": 140.0},
    {"min_order_eur": 0.0,    "max_order_eur": 500.0,    "region_bucket_key": "C", "price_eur": 110.0},
    # ─ Bucket D: Resto de regiones ─
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "D", "price_eur": 0.0},
    {"min_order_eur": 500.0,  "max_order_eur": 3000.0,   "region_bucket_key": "D", "price_eur": 200.0},
    {"min_order_eur": 0.0,    "max_order_eur": 500.0,    "region_bucket_key": "D", "price_eur": 180.0},
]

# ── G5: Anti Impacto (SOUND / PARQUET) ────────────────────────────────────────
# Franco desde 1.500€ (sin cambio). Baleares en Bucket B. Tarifas subidas.
SG['G5_SOUND'] = [
    {"min_order_eur": 1500.0, "max_order_eur": 999999.0, "region_bucket_key": "A", "price_eur": 0.0},
    {"min_order_eur": 1500.0, "max_order_eur": 999999.0, "region_bucket_key": "B", "price_eur": 0.0},
    {"min_order_eur": 0.0,    "max_order_eur": 1500.0,   "region_bucket_key": "A", "price_eur": 60.0},
    {"min_order_eur": 0.0,    "max_order_eur": 1500.0,   "region_bucket_key": "B", "price_eur": 110.0},
]

with open(BASE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("OK: SHIPPING_GROUPS actualizados con tarifas Abril 2026")
print()
print("Tarifas aplicadas:")
for g, rows in SG.items():
    if g.startswith('G'):
        print(f"\n  {g}:")
        for r in rows:
            print(f"    bucket={r['region_bucket_key']} [{r['min_order_eur']:.0f}-{r['max_order_eur']:.0f}] = {r['price_eur']}EUR")
