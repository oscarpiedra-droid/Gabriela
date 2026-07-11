from db.services.commercial_conditions_service import DiscountProposalService
import pandas as pd

dps = DiscountProposalService()
records = dps.get_proposal_data()

# Filtrar por segmento y familia
target_segment = "ALMACENES GENERALISTAS"
target_families = ["REFLECTIVOS_EXCL_CM_XPS_SYC", "CM_XPS_SYC"]

print(f"Buscando reglas para {target_segment} en {target_families}")

rows = [r for r in records if str(r.get('Segmento', '')).strip().upper() == target_segment]
for fam in target_families:
    fam_rows = [r for r in rows if str(r.get('Familia', '')).strip().upper() == fam.upper()]
    print(f"\nFAMILIA: {fam}")
    for r in fam_rows:
        desde = r.get('Base imponible desde (EUR)', 0)
        hasta = r.get('Base imponible hasta (EUR)', 'N/A')
        max_pen = r.get('DTO máximo Península (%)', 0)
        max_bal = r.get('DTO máximo Baleares (%)', 0)
        print(f"  Tramo: {desde} - {hasta} | Máx Pen: {max_pen}% | Máx Bal: {max_bal}%")
