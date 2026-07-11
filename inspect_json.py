import json
with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\app\db\commercial_rules_v2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print(data['SKU_DISCOUNTS'].keys())
