"""probe_sku.py — verifica si 22.005-1 está en SKU_MASTER y su family_logic_base."""
import sys, os, json, re

BASE = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(BASE, "app", "db", "commercial_rules_v2.json")

with open(json_path, "r", encoding="utf-8") as f:
    raw = f.read()
raw = re.sub(r"\bNaN\b", "null", raw)
data = json.loads(raw)

sku_raw = data.get("SKU_MASTER", {})
if isinstance(sku_raw, list):
    sku_master = {item["sku"]: item for item in sku_raw if "sku" in item}
else:
    sku_master = sku_raw

ref = "22.005-1"
info = sku_master.get(ref)
if info:
    print(f"SKU {ref} ENCONTRADO:")
    print(f"  family_logic_base = {repr(info.get('family_logic_base', ''))}")
    for k, v in info.items():
        print(f"  {k}: {v}")
else:
    print(f"SKU {ref} NO ENCONTRADO en SKU_MASTER")
    similares = [k for k in sku_master if ref[:5] in k]
    print(f"  Similares (prefix {ref[:5]}): {similares[:10]}")
    print(f"  Total SKUs en master: {len(sku_master)}")
    print(f"  Muestra 10: {list(sku_master.keys())[:10]}")

# Mostrar los segmentos únicos en SPECIAL_CUSTOMERS
specials = data.get("SPECIAL_CUSTOMERS", {})
print(f"\nSPECIAL_CUSTOMERS: {list(specials.keys())[:5]}")
