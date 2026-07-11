# -*- coding: utf-8 -*-
"""
patch_g4_shipping_groups.py
Añade los buckets C y D a G4_ANTIIMPACTO_NO_SOUND en commercial_rules_v2.json.
Segun el Excel oficial "Nueva Politica de Portes 2026":
  - Bucket C (Cataluna + Levante + Madrid): <500=90E, 500-3000=120E, >=3000=0E
  - Bucket D (Resto, incluye Baleares, Aragon, PV-Nav-Can, CLM, And.Este,
              Asturias-Galicia, CyL, Extremadura, And.Oeste): <500=150E, 500-3000=180E, >=3000=0E
"""
import sys, os, re, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

BASE = os.path.join(os.path.dirname(__file__), '..', 'app', 'db', 'commercial_rules_v2.json')

with open(BASE, 'r', encoding='utf-8') as f:
    raw = f.read()

raw = re.sub(r'\bNaN\b', 'null', raw)
data = json.loads(raw)

# Reemplazar completamente G4 con la estructura correcta (C y D)
data['SHIPPING_GROUPS']['G4_ANTIIMPACTO_NO_SOUND'] = [
    # ─ Bucket C: Cataluna + Levante + Madrid (tarifa baja)
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "C", "price_eur": 0.0},
    {"min_order_eur": 500.0,  "max_order_eur": 3000.0,   "region_bucket_key": "C", "price_eur": 120.0},
    {"min_order_eur": 0.0,    "max_order_eur": 500.0,    "region_bucket_key": "C", "price_eur": 90.0},
    # ─ Bucket D: Resto de regiones (tarifa alta, incluye Baleares, Aragon, etc.)
    {"min_order_eur": 3000.0, "max_order_eur": 999999.0, "region_bucket_key": "D", "price_eur": 0.0},
    {"min_order_eur": 500.0,  "max_order_eur": 3000.0,   "region_bucket_key": "D", "price_eur": 180.0},
    {"min_order_eur": 0.0,    "max_order_eur": 500.0,    "region_bucket_key": "D", "price_eur": 150.0},
]

with open(BASE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("OK: G4_ANTIIMPACTO_NO_SOUND actualizado con buckets C y D en commercial_rules_v2.json")

# Verificacion
import db.commercial_rules as rules
rules.load_from_json()
print("\nG4 en JSON tras patch:")
for r in rules.SHIPPING_GROUPS.get('G4_ANTIIMPACTO_NO_SOUND', []):
    print(f"  bucket={r['region_bucket_key']} [{r['min_order_eur']}-{r['max_order_eur']}] = {r['price_eur']}EUR")
