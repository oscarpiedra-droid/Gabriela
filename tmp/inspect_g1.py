import json
d = json.load(open('app/db/commercial_rules_v2.json', encoding='utf-8'))
sg = d['SHIPPING_GROUPS']
g1 = sg['G1_GENERAL']
print('G1_GENERAL tramos:')
for r in sorted(g1, key=lambda x: x['min_order_eur']):
    print(f"  Bucket={r['region_bucket_key']} | {r['min_order_eur']}-{r['max_order_eur']} -> {r['price_eur']}")
