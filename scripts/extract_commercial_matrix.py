import pandas as pd
import json
import os
from datetime import datetime

# Rutas
path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\Validador de pedidos\validador pedidos bur2000 matriz_logica_v2.xlsx'
output_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\app\db\commercial_rules_v2.json'

# Leemos Excel
xl = pd.ExcelFile(path)

# 1. SKU_MASTER
df_sku = xl.parse('05_SKU_MASTER')
sku_master = df_sku.to_dict(orient='records')

# 2. BUR_GROUP_CLIENTS (Extracción de campos de regla especial)
df_clients = xl.parse('03_CLIENTES_BUR_GROUP')
bur_group_clients = {}
for _, row in df_clients.iterrows():
    cli = str(row['cliente']).strip()
    bur_group_clients[cli] = {
        'dto_max_hasta_1500_pct': float(row['dto_max_hasta_1500_pct']) if pd.notna(row['dto_max_hasta_1500_pct']) else None,
        'dto_max_mas_1500_pct': float(row['dto_max_mas_1500_pct']) if pd.notna(row['dto_max_mas_1500_pct']) else None,
        'supervisor_required': bool(row['requiere_comercial_igual_supervisor']) if pd.notna(row['requiere_comercial_igual_supervisor']) else False
    }

# 3. SHIPPING_GROUPS
df_shipping = xl.parse('08_PORTES_NORMALIZADOS')
shipping_groups = {}
for _, row in df_shipping.iterrows():
    group_key = str(row['shipping_group_key']).strip()
    if group_key not in shipping_groups:
        shipping_groups[group_key] = []
    
    shipping_groups[group_key].append({
        'min_order_eur': float(row['order_min_eur']) if pd.notna(row['order_min_eur']) else 0.0,
        'max_order_eur': float(row['order_max_eur']) if pd.notna(row['order_max_eur']) else 999999.0,
        'region_bucket_key': str(row['region_bucket_key']).strip(),
        'price_eur': float(row['expected_shipping_eur']) if pd.notna(row['expected_shipping_eur']) else 0.0
    })

# 4. SKU_DISCOUNTS (Deduplicación lógica de tramos overlapping)
df_desc = xl.parse('07_SKU_DTO_EXPANDIDA')
sku_discounts_raw = {}

for _, row in df_desc.iterrows():
    sku = str(row['sku']).strip()
    segment = str(row['segment_key']).strip()
    if segment == "NO_STANDARD_RULE": continue

    if sku not in sku_discounts_raw:
        sku_discounts_raw[sku] = {}
    if segment not in sku_discounts_raw[sku]:
        sku_discounts_raw[sku][segment] = {} 

    min_eur = float(row['order_min_eur']) if pd.notna(row['order_min_eur']) else 0.0
    max_eur = float(row['order_max_eur']) if pd.notna(row['order_max_eur']) else 999999.0
    dscto_p = float(row['max_discount_territorial_pct']) if pd.notna(row['max_discount_territorial_pct']) else 0.0
    dscto_b = float(row['max_discount_baleares_pct']) if pd.notna(row['max_discount_baleares_pct']) else 0.0

    if min_eur not in sku_discounts_raw[sku][segment]:
        sku_discounts_raw[sku][segment][min_eur] = {
            'min_eur_order': min_eur,
            'max_eur_order': max_eur,
            'dscto_peninsula_pct': dscto_p,
            'dscto_baleares_pct': dscto_b
        }
    else:
        existing = sku_discounts_raw[sku][segment][min_eur]
        if dscto_p > existing['dscto_peninsula_pct']:
            existing['dscto_peninsula_pct'] = dscto_p
            existing['dscto_baleares_pct'] = dscto_b

sku_discounts = {}
for sku, segments in sku_discounts_raw.items():
    sku_discounts[sku] = {}
    for segment, tramos_dict in segments.items():
        sorted_keys = sorted(tramos_dict.keys(), reverse=True)
        sku_discounts[sku][segment] = [tramos_dict[k] for k in sorted_keys]

# 5. GENERACIÓN FINAL
data = {
    'LAST_UPDATE': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    'SKU_MASTER': sku_master,
    'BUR_GROUP_CLIENTS': bur_group_clients,
    'SHIPPING_GROUPS': shipping_groups,
    'SKU_DISCOUNTS': sku_discounts
}

with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    
print(f"Generated {output_path} successfully ({len(sku_discounts)} SKUs processed).")
