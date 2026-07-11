# -*- coding: utf-8 -*-
"""Inspecciona claves de CM XPS en el JSON."""
import re, json
with open('app/db/commercial_rules_v2.json', encoding='utf-8') as f:
    data = json.loads(re.sub(r'\bNaN\b','null', f.read()))
SD = data['SKU_DISCOUNTS']

# Ver que claves tiene un SKU de CM XPS
for sku in ['01.002', '01.002-1', '01.002-2']:
    if sku in SD:
        print(f'Claves en {sku}:', list(SD[sku].keys()))
        # Ver valor actual de ALMACENES_ESPECIALISTAS_PYL
        seg = SD[sku].get('ALMACENES_ESPECIALISTAS_PYL', [])
        print('  ALM_ESP_PYL:')
        for r in seg:
            print(f'    {r["min_eur_order"]}-{r["max_eur_order"]}: T={r["dscto_peninsula_pct"]} B={r["dscto_baleares_pct"]}')
        break

# Ver SKUs de PARQUET
for sku in ['21.001', '21.001-1']:
    if sku in SD:
        print(f'\nClaves en {sku}:', list(SD[sku].keys()))
        seg = SD[sku].get('ALMACENES_INSTALADORES_SOUND', [])
        print('  ALMACENES_INSTALADORES_SOUND:')
        for r in seg:
            print(f'    {r["min_eur_order"]}-{r["max_eur_order"]}: T={r["dscto_peninsula_pct"]} B={r["dscto_baleares_pct"]}')
        break
