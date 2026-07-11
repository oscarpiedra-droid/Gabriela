# -*- coding: utf-8 -*-
"""
patch_xps_parquet_final.py
Fix final: CM XPS y PARQUET tienen los valores de +2 GAMAS / +OTRA GAMA en las
claves base. Restaura los valores BASE del Excel correctos.

CM XPS BASE (01.002.x) por segmento — valores del Excel, fila sin nota "+2 GAMAS":
  ALMACENES_ESPECIALISTAS_PYL:  6000+=55/50, 3000=52/47, 1500=50/45, <1500=45/40
  ALMACENES_GENERALISTAS:       6000+=55/50, 3000=52/47, 1500=50/45, <1500=45/40
  EMPRESAS_CONSTRUCTORAS:       8000+=57/52, 6000=55/50, 3000=52/47, 1500=50/45, <1500=45/40
  EMPRESAS_INSTALADORAS:        6000+=60/55, 3000=55/50, <3000=52/47

PARQUET BASE (21.xxx) en ALMACENES_INSTALADORES_SOUND:
  3000+=58/53, 1500=55/50, <1500=53/48
"""
import re, json
BASE = 'app/db/commercial_rules_v2.json'
with open(BASE, encoding='utf-8') as f:
    data = json.loads(re.sub(r'\bNaN\b', 'null', f.read()))
SD = data['SKU_DISCOUNTS']

# ── CM XPS base values ────────────────────────────────────────────────────────
XPS_BASE = {
    "ALMACENES_ESPECIALISTAS_PYL": [
        {"min_eur_order": 6000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
        {"min_eur_order": 3000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 52.0, "dscto_baleares_pct": 47.0},
        {"min_eur_order": 1500.0, "max_eur_order": 3000.0,   "dscto_peninsula_pct": 50.0, "dscto_baleares_pct": 45.0},
        {"min_eur_order": 0.0,    "max_eur_order": 1500.0,   "dscto_peninsula_pct": 45.0, "dscto_baleares_pct": 40.0},
    ],
    "ALMACENES_GENERALISTAS": [
        {"min_eur_order": 6000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
        {"min_eur_order": 3000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 52.0, "dscto_baleares_pct": 47.0},
        {"min_eur_order": 1500.0, "max_eur_order": 3000.0,   "dscto_peninsula_pct": 50.0, "dscto_baleares_pct": 45.0},
        {"min_eur_order": 0.0,    "max_eur_order": 1500.0,   "dscto_peninsula_pct": 45.0, "dscto_baleares_pct": 40.0},
    ],
    "EMPRESAS_CONSTRUCTORAS": [
        {"min_eur_order": 8000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 57.0, "dscto_baleares_pct": 52.0},
        {"min_eur_order": 6000.0, "max_eur_order": 8000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
        {"min_eur_order": 3000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 52.0, "dscto_baleares_pct": 47.0},
        {"min_eur_order": 1500.0, "max_eur_order": 3000.0,   "dscto_peninsula_pct": 50.0, "dscto_baleares_pct": 45.0},
        {"min_eur_order": 0.0,    "max_eur_order": 1500.0,   "dscto_peninsula_pct": 45.0, "dscto_baleares_pct": 40.0},
    ],
    "EMPRESAS_INSTALADORAS": [
        {"min_eur_order": 6000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 60.0, "dscto_baleares_pct": 55.0},
        {"min_eur_order": 3000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
        {"min_eur_order": 0.0,    "max_eur_order": 3000.0,   "dscto_peninsula_pct": 52.0, "dscto_baleares_pct": 47.0},
    ],
}

# ── PARQUET base values ───────────────────────────────────────────────────────
PARQUET_BASE = [
    {"min_eur_order": 3000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 58.0, "dscto_baleares_pct": 53.0},
    {"min_eur_order": 1500.0, "max_eur_order": 3000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
    {"min_eur_order": 0.0,    "max_eur_order": 1500.0,   "dscto_peninsula_pct": 53.0, "dscto_baleares_pct": 48.0},
]

patched = 0
for sku, sku_data in SD.items():
    # CM XPS
    if sku.startswith('01.002'):
        for seg_key, rules in XPS_BASE.items():
            if seg_key in sku_data:
                sku_data[seg_key] = rules
                patched += 1
    # PARQUET
    if sku.startswith('21.'):
        sku_data['ALMACENES_INSTALADORES_SOUND'] = PARQUET_BASE
        patched += 1

with open(BASE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"OK: {patched} bloques parcheados (CM XPS base + PARQUET base)")

# Verificación rápida
xps = SD.get('01.002', {})
alm_esp = xps.get('ALMACENES_ESPECIALISTAS_PYL', [])
print(f"\nVerificacion CM XPS 01.002 / ALMACENES_ESPECIALISTAS_PYL:")
for r in alm_esp:
    print(f"  {r['min_eur_order']:.0f}-{r['max_eur_order']:.0f}: T={r['dscto_peninsula_pct']} B={r['dscto_baleares_pct']}")
    
parquet = SD.get('21.001', {})
p_sound = parquet.get('ALMACENES_INSTALADORES_SOUND', [])
print(f"\nVerificacion PARQUET 21.001 / ALMACENES_INSTALADORES_SOUND:")
for r in p_sound:
    print(f"  {r['min_eur_order']:.0f}-{r['max_eur_order']:.0f}: T={r['dscto_peninsula_pct']} B={r['dscto_baleares_pct']}")
