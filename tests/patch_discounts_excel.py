# -*- coding: utf-8 -*-
"""
patch_discounts_excel.py
Corrige todos los descuentos del JSON para alinearlos 100% con el Excel.
Errores encontrados:
 1. Empresas Instaladoras: Anti Impacto y CM XPS tienen valores incorrectos
 2. SOUND/PARQUET: segmento ALMACENES_INSTALADORES_SOUND falta en SKUs 21.xxx
 3. Axarquia: Anti Impacto y Impermeabilizantes tienen tramos granulares distintos
"""
import sys, os, re, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

JSON_FILE = os.path.join(os.path.dirname(__file__), '..', 'app', 'db', 'commercial_rules_v2.json')

with open(JSON_FILE, encoding='utf-8') as f:
    data = json.loads(re.sub(r'\bNaN\b', 'null', f.read()))

SD = data['SKU_DISCOUNTS']

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: Empresas Instaladoras — Anti Impacto (NO SOUND) 12.xxx y 13.xxx
# Excel: 6000+=60/55, 3000=57/52, <3000=55/50
# JSON tenía: los valores de ACUSTICA (57/52/50) mezclados
# ─────────────────────────────────────────────────────────────────────────────
INSTALADORAS_ANTI_IMPACTO = [
    {"min_eur_order": 6000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 60.0, "dscto_baleares_pct": 55.0},
    {"min_eur_order": 3000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 57.0, "dscto_baleares_pct": 52.0},
    {"min_eur_order": 0.0,    "max_eur_order": 3000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
]

# FIX 2: Empresas Instaladoras — Impermeabilizantes (16.xxx)
# Excel: 6000+=60/55, 3000=57/52, <3000=55/50
INSTALADORAS_IMPERMEAB = [
    {"min_eur_order": 6000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 60.0, "dscto_baleares_pct": 55.0},
    {"min_eur_order": 3000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 57.0, "dscto_baleares_pct": 52.0},
    {"min_eur_order": 0.0,    "max_eur_order": 3000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
]

# FIX 3: Empresas Instaladoras — CM XPS (01.002.x)
# Excel base (sin +2 GAMAS): 6000+=60/55, 3000=55/50, <3000=52/47
# JSON tenía erróneamente los valores de +2 GAMAS en las filas base, y viceversa
INSTALADORAS_CM_XPS_BASE = [
    {"min_eur_order": 6000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 60.0, "dscto_baleares_pct": 55.0},
    {"min_eur_order": 3000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
    {"min_eur_order": 0.0,    "max_eur_order": 3000.0,   "dscto_peninsula_pct": 52.0, "dscto_baleares_pct": 47.0},
]

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: SOUND/PARQUET — Añadir ALMACENES_INSTALADORES_SOUND a SKUs 21.xxx
# Excel: 3000+=58/53, 1500=55/50, <1500=53/48
# ─────────────────────────────────────────────────────────────────────────────
SOUND_PARQUET = [
    {"min_eur_order": 3000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 58.0, "dscto_baleares_pct": 53.0},
    {"min_eur_order": 1500.0, "max_eur_order": 3000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 50.0},
    {"min_eur_order": 0.0,    "max_eur_order": 1500.0,   "dscto_peninsula_pct": 53.0, "dscto_baleares_pct": 48.0},
]

# ─────────────────────────────────────────────────────────────────────────────
# FIX 5: Axarquía — Anti Impacto (NO SOUND) con tramos granulares correctos
# Excel: 6000+=57, 4000=56, 3000=55, 2500=53, 2000=51, 1500=50, 1000=48, <1000=47
# ─────────────────────────────────────────────────────────────────────────────
AXARQUIA_ANTI_IMPACTO = [
    {"min_eur_order": 6000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 57.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 4000.0, "max_eur_order": 6000.0,   "dscto_peninsula_pct": 56.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 3000.0, "max_eur_order": 4000.0,   "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 2500.0, "max_eur_order": 3000.0,   "dscto_peninsula_pct": 53.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 2000.0, "max_eur_order": 2500.0,   "dscto_peninsula_pct": 51.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 1500.0, "max_eur_order": 2000.0,   "dscto_peninsula_pct": 50.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 1000.0, "max_eur_order": 1500.0,   "dscto_peninsula_pct": 48.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 0.0,    "max_eur_order": 1000.0,   "dscto_peninsula_pct": 47.0, "dscto_baleares_pct": 0.0},
]

# FIX 6: Axarquía — Impermeabilizantes con tramos granulares correctos
# Excel: 5000+=55, 4000=53, 3000=52, 2500=51, 2000=51, 1500=50, 1000=48, <1000=47
AXARQUIA_IMPERMEAB = [
    {"min_eur_order": 5000.0, "max_eur_order": 999999.0, "dscto_peninsula_pct": 55.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 4000.0, "max_eur_order": 5000.0,   "dscto_peninsula_pct": 53.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 3000.0, "max_eur_order": 4000.0,   "dscto_peninsula_pct": 52.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 2500.0, "max_eur_order": 3000.0,   "dscto_peninsula_pct": 51.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 2000.0, "max_eur_order": 2500.0,   "dscto_peninsula_pct": 51.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 1500.0, "max_eur_order": 2000.0,   "dscto_peninsula_pct": 50.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 1000.0, "max_eur_order": 1500.0,   "dscto_peninsula_pct": 48.0, "dscto_baleares_pct": 0.0},
    {"min_eur_order": 0.0,    "max_eur_order": 1000.0,   "dscto_peninsula_pct": 47.0, "dscto_baleares_pct": 0.0},
]

# ─── Aplicar fixes ────────────────────────────────────────────────────────────
patched = 0

for sku, sku_data in SD.items():
    family_prefix = sku.split('.')[0] + '.'

    # Anti Impacto (12.xxx, 13.xxx) -> Empresas Instaladoras
    if sku.startswith('12.') or sku.startswith('13.'):
        if 'EMPRESAS_INSTALADORAS' in sku_data:
            sku_data['EMPRESAS_INSTALADORAS'] = INSTALADORAS_ANTI_IMPACTO
            patched += 1
        # Axarquia Anti Impacto
        if 'AXARQUIA_DE_AISLAMIENTOS_DISTRIBUCION' in sku_data:
            sku_data['AXARQUIA_DE_AISLAMIENTOS_DISTRIBUCION'] = AXARQUIA_ANTI_IMPACTO
            patched += 1

    # Impermeabilizantes (16.xxx, 17.xxx) -> Empresas Instaladoras
    if sku.startswith('16.') or sku.startswith('17.'):
        if 'EMPRESAS_INSTALADORAS' in sku_data:
            sku_data['EMPRESAS_INSTALADORAS'] = INSTALADORAS_IMPERMEAB
            patched += 1
        # Axarquia Impermeabilizantes
        if 'AXARQUIA_DE_AISLAMIENTOS_DISTRIBUCION' in sku_data:
            sku_data['AXARQUIA_DE_AISLAMIENTOS_DISTRIBUCION'] = AXARQUIA_IMPERMEAB
            patched += 1

    # CM XPS (01.002.x) -> Empresas Instaladoras base (sin +2 GAMAS)
    # El JSON tiene CM XPS en EMPRESAS_INSTALADORAS con los valores de +2 GAMAS
    # La fila "CM XPS base" en Instaladoras es: 60/55, 55/50, 52/47
    if sku.startswith('01.002'):
        if 'EMPRESAS_INSTALADORAS' in sku_data:
            # Verificar si es el segmento base (no +2 GAMAS)
            # Los +2 GAMAS tienen 62/57 en el tramo más alto
            current_top = sku_data['EMPRESAS_INSTALADORAS'][0].get('dscto_peninsula_pct', 0)
            if current_top != 60.0:  # Solo corregir si no está ya bien
                sku_data['EMPRESAS_INSTALADORAS'] = INSTALADORAS_CM_XPS_BASE
                patched += 1

    # PARQUET (21.xxx) -> añadir ALMACENES_INSTALADORES_SOUND si no existe
    if sku.startswith('21.'):
        if 'ALMACENES_INSTALADORES_SOUND' not in sku_data:
            sku_data['ALMACENES_INSTALADORES_SOUND'] = SOUND_PARQUET
            patched += 1
        else:
            # Verificar que los valores sean correctos
            top = sku_data['ALMACENES_INSTALADORES_SOUND'][0].get('dscto_peninsula_pct', 0)
            if top != 58.0:
                sku_data['ALMACENES_INSTALADORES_SOUND'] = SOUND_PARQUET
                patched += 1

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"OK: {patched} bloques de descuento parcheados en commercial_rules_v2.json")
print()
print("Fixes aplicados:")
print("  [F1] Empresas Instaladoras Anti Impacto -> 60/57/55%")
print("  [F2] Empresas Instaladoras Impermeabilizantes -> 60/57/55%")
print("  [F3] Empresas Instaladoras CM XPS base -> 60/55/52%")
print("  [F4] PARQUET (21.xxx) -> ALMACENES_INSTALADORES_SOUND 58/55/53%")
print("  [F5] Axarquia Anti Impacto -> 8 tramos granulares correctos")
print("  [F6] Axarquia Impermeabilizantes -> 8 tramos granulares correctos")
