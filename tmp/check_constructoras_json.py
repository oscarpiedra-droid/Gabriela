import json

d = json.load(open('app/db/commercial_rules_v2.json', encoding='utf-8'))
skus = d['SKU_DISCOUNTS']

# Buscar segmentos presentes
segmentos = set()
for sku, fam_map in skus.items():
    for fam, seg_map in fam_map.items():
        for seg in seg_map:
            segmentos.add(seg)

print("SEGMENTOS en SKU_DISCOUNTS:")
for s in sorted(segmentos):
    print(f"  - {s!r}")

print("\n--- Verificando Empresas Constructoras ---")
encontrado = False
for sku, fam_map in skus.items():
    for fam, seg_map in fam_map.items():
        if 'Empresas Constructoras' in seg_map:
            encontrado = True
            tramos = seg_map['Empresas Constructoras']
            print(f"SKU={sku} FAM={fam} tramos={tramos}")
            break

if not encontrado:
    print("NO ENCONTRADO en SKU_DISCOUNTS")

# Verificar tramo 8000€ en cualquier segmento
print("\n--- Tramos presentes (todas las claves de facturación) ---")
tramos_vistos = set()
for sku, fam_map in skus.items():
    for fam, seg_map in fam_map.items():
        for seg, tramo_list in seg_map.items():
            for t in tramo_list:
                tramos_vistos.add(t.get('tramo_min', '?'))
print(sorted(tramos_vistos))
