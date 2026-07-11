import sys
import os

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app.db.services.commercial_conditions_service import DiscountProposal2026

def test_bur_group():
    from app.db import commercial_rules as rules
    
    bur_clients = rules.BUR_GROUP_CLIENTS
    print(f"BUR GROUP CLIENTS: {bur_clients}")

    tests = ["BUR-TEST", "ABRERA - BUR-01", "Imperbur", "BUR-023"]

    for t in tests:
        p_name_str = (t or "").strip()
        is_bur_group = bool(p_name_str in bur_clients or "BUR-" in p_name_str)
        print(f"Client: {t} | Is BUR Group: {is_bur_group}")

def test_platino_discount():
    dp = DiscountProposal2026()
    # Distribuidor Platino, XPS family, any base_imponible.
    # Should now allow 20%
    res = dp.validate_range(segmento='Distribuidor Platino', familia='XPS', base_imponible=500, dto_solicitado=20)
    print(f"Platino XPS 20%: {res}")
    res = dp.validate_range(segmento='Distribuidor Platino', familia='XPS', base_imponible=500, dto_solicitado=21)
    print(f"Platino XPS 21%: {res}")

if __name__ == "__main__":
    test_bur_group()
    test_platino_discount()
