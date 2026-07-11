"""
Commercial Rules 2026 - Official Consolidated Policy.
Now dynamic: loads from commercial_rules_v2.json.
"""
import os
import re
import json

# Path to the JSON relative to this file
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_JSON_PATH = os.path.join(_BASE_DIR, 'commercial_rules_v2.json')

_RULES_DATA = {}
SKU_MASTER = {}
BUR_GROUP_CLIENTS: set = set()  # set of client name strings for O(1) lookup
SHIPPING_GROUPS = {}
SKU_DISCOUNTS = {}
SPECIAL_CUSTOMERS = {}
DISCOUNT_RULES = {} # Keep as alias for SKU_DISCOUNTS if needed

# For compatibility or local use
PENINSULA = "peninsula"
BALEARES = "baleares"

def load_from_json():
    global _RULES_DATA, SKU_MASTER, BUR_GROUP_CLIENTS, SHIPPING_GROUPS, SKU_DISCOUNTS, DISCOUNT_RULES, SPECIAL_CUSTOMERS
    
    # Path to the JSON relative to this file
    base_path = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_path, 'commercial_rules_v2.json')
    
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        # pandas exports NaN as bare `NaN` which is invalid JSON → replace with null
        raw_text = re.sub(r'\bNaN\b', 'null', raw_text)
        _RULES_DATA = json.loads(raw_text)
    else:
        _RULES_DATA = {
            "SKU_MASTER": {},
            "BUR_GROUP_CLIENTS": [],
            "SHIPPING_GROUPS": {},
            "SKU_DISCOUNTS": {},
            "DISCOUNT_RULES": {},
            "SPECIAL_CUSTOMERS": {}
        }

    # SKU_MASTER puede ser lista [{sku:..., ...}] o dict {sku: {...}}
    # Normalizamos siempre a dict {sku_code: {datos}}
    _raw_sku = _RULES_DATA.get("SKU_MASTER", {})
    if isinstance(_raw_sku, list):
        SKU_MASTER = {item["sku"]: item for item in _raw_sku if "sku" in item}
    else:
        SKU_MASTER = _raw_sku

    # BUR_GROUP_CLIENTS: el JSON lo almacena como lista de nombres.
    # Normalizamos a set para lookups O(1) con el operador `in`.
    _raw_bgc = _RULES_DATA.get("BUR_GROUP_CLIENTS", [])
    if isinstance(_raw_bgc, list):
        BUR_GROUP_CLIENTS = set(_raw_bgc)
    elif isinstance(_raw_bgc, dict):
        BUR_GROUP_CLIENTS = set(_raw_bgc.keys())
    else:
        BUR_GROUP_CLIENTS = set()

    SHIPPING_GROUPS = _RULES_DATA.get("SHIPPING_GROUPS", {})
    SKU_DISCOUNTS = _RULES_DATA.get("SKU_DISCOUNTS", {})
    DISCOUNT_RULES = SKU_DISCOUNTS  # Alias to match existing code logic
    SPECIAL_CUSTOMERS = _RULES_DATA.get("SPECIAL_CUSTOMERS", {})

# Initial Load (single call on module import)
load_from_json()

def get_all_families():
    """Extract unique product families dynamically from the loaded SKU_MASTER."""
    gamas = set()
    for _, item in (SKU_MASTER.items() if isinstance(SKU_MASTER, dict) else []):
        if "family_logic_base" in item:
            gamas.add(item["family_logic_base"])
    return sorted(list(gamas))

def get_region_by_cp(cp: str) -> str:
    if not cp: return "ESTANDAR"
    prefix = cp[:2]
    # High Cost Regions (Bucket B)
    if prefix in ["33", "15", "27", "32", "36"]: return "ASTURIAS-GALICIA"
    if prefix in ["05", "09", "24", "34", "37", "40", "42", "47", "49"]: return "CASTILLA Y LEON"
    if prefix in ["06", "10"]: return "EXTREMADURA"
    if prefix in ["11", "21", "41", "14"]: return "ANDALUCIA OESTE"
    
    # Standard Cost Regions (Bucket A)
    if prefix in ["08", "17", "25", "43"]: return "CATALUÑA"
    if prefix in ["22", "44", "50", "26"]: return "ARAGON-RIOJA"
    if prefix in ["03", "12", "46"]: return "LEVANTE"
    if prefix == "07": return "BALEARES"
    if prefix in ["01", "48", "20", "31", "39"]: return "NORTE (PV-NAV-CAN)"
    if prefix == "28": return "MADRID"
    if prefix in ["02", "13", "16", "19", "45"]: return "CASTILLA LA MANCHA"
    if prefix in ["23", "04", "18", "29"]: return "ANDALUCIA ESTE"
    
    return "ESTANDAR"

def get_region_bucket(region: str) -> str:
    """Bucket generico A/B (valido para G1, G2, G3). NO usar para G4 ni G5."""
    heavy_regions = ["ASTURIAS-GALICIA", "CASTILLA Y LEON", "EXTREMADURA", "ANDALUCIA OESTE"]
    return "B" if region in heavy_regions else "A"


def get_region_bucket_for_group(region: str, shipping_group: str) -> str:
    """
    Devuelve el bucket tarifario correcto segun el grupo de envio y la region.

    Los grupos G1/G2/G3 usan la division estandar A/B:
      - Bucket A (tarifa baja): Cataluna, Aragon, Levante, Baleares, PV-Nav-Can,
                                Madrid, Castilla-La Mancha, Andalucia Este.
      - Bucket B (tarifa alta): Asturias-Galicia, Castilla y Leon, Extremadura,
                                Andalucia Oeste.

    G4 (Anti Impacto NO SOUND) tiene 3 niveles tarifarios segun el Excel 2026:
      - Bucket C (90/120 EUR):  SOLO Cataluna + Levante + Madrid.
      - Bucket D (150/180 EUR): RESTO: Aragon, Baleares, PV-Nav-Can, CLM,
                                And.Este, Asturias-Galicia, CyL, Extremadura, And.Oeste.

    G5 (SOUND / PARQUET) es igual que A/B pero Baleares paga tarifa ALTA (B):
      - Bucket A (50 EUR < 1500E): Cataluna, Aragon, Levante, PV-Nav-Can, Madrid,
                                   CLM, Andalucia Este.
      - Bucket B (90 EUR < 1500E): BALEARES + Asturias-Galicia, CyL, Extremadura,
                                   Andalucia Oeste.
    """
    if shipping_group == "G4_ANTIIMPACTO_NO_SOUND":
        # Solo Cataluna, Levante y Madrid tienen tarifa baja (C)
        low_cost_g4 = {"CATALUÑA", "LEVANTE", "MADRID"}
        return "C" if region in low_cost_g4 else "D"

    if shipping_group == "G5_SOUND":
        # Baleares en G5 va a tarifa alta (B), no A
        heavy_g5 = {"ASTURIAS-GALICIA", "CASTILLA Y LEON", "EXTREMADURA",
                    "ANDALUCIA OESTE", "BALEARES"}
        return "B" if region in heavy_g5 else "A"

    # G1, G2, G3, y cualquier grupo nuevo: bucket generico A/B
    return get_region_bucket(region)
