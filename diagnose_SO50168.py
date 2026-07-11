"""
diagnose_SO50168.py  —  Consulta directa a Odoo para diagnosticar el WARNING
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from app.db.services.odoo_service_v2 import OdooServiceV2

SO_NAME = "SO50168"

def fmt(v): return f"{float(v):,.2f}€" if v else "0.00€"
def sep(): print("─" * 70)

def main():
    svc = OdooServiceV2()
    if not svc.connect():
        print("❌ No se pudo conectar a Odoo"); return

    env = svc.odoo.env

    # 1. Buscar el pedido
    orders = env["sale.order"].search_read(
        [["name", "=", SO_NAME]],
        fields=["id","name","partner_id","partner_shipping_id","amount_untaxed",
                "amount_total","state","order_line","carrier_id",
                "user_id","supervisor_id","pricelist_id","date_order"]
    )
    if not orders:
        print(f"❌ {SO_NAME} no encontrado en Odoo"); return

    o = orders[0]
    sep()
    print(f"  DIAGNÓSTICO:  {SO_NAME}")
    sep()
    print(f"  Cliente       : {o['partner_id'][1] if o['partner_id'] else '—'}")
    print(f"  Estado        : {o['state']}")
    print(f"  Base impon.   : {fmt(o['amount_untaxed'])}")
    print(f"  Total c/IVA   : {fmt(o['amount_total'])}")
    print(f"  Fecha         : {str(o['date_order'])[:10]}")
    print(f"  Tarifa        : {o['pricelist_id'][1] if o.get('pricelist_id') else '—'}")
    print(f"  Transportista : {o['carrier_id'][1] if o.get('carrier_id') else '—'}")
    print(f"  Comercial     : {o['user_id'][1] if o.get('user_id') else '—'}")
    print(f"  Supervisor    : {o['supervisor_id'][1] if o.get('supervisor_id') else '—'}")

    # 2. Dirección de envío → CP → Región
    s_id = o["partner_shipping_id"][0] if o["partner_shipping_id"] else (o["partner_id"][0] if o["partner_id"] else None)
    p_id = o["partner_id"][0] if o["partner_id"] else None

    zip_code = ""
    if s_id:
        ship = env["res.partner"].search_read([["id","=",s_id]], ["zip","city","state_id"])
        if ship:
            zip_code = ship[0].get("zip") or ""
            city = ship[0].get("city","")
            state = ship[0]["state_id"][1] if ship[0].get("state_id") else ""
            print(f"  CP envío      : {zip_code}  ({city}, {state})")

    if not zip_code and p_id:
        part = env["res.partner"].search_read([["id","=",p_id]], ["zip"])
        zip_code = part[0].get("zip","") if part else ""

    # 3. Tags / tipo del cliente
    cat_name = "—"
    if p_id:
        pr = env["res.partner"].search_read([["id","=",p_id]], ["category_id"])
        if pr and pr[0].get("category_id"):
            cats = env["res.partner.category"].read(pr[0]["category_id"], ["name"])
            cat_name = " | ".join(c["name"] for c in cats)
    print(f"  Tipo cliente  : {cat_name}")

    # 4. Líneas del pedido
    sep()
    print("  LÍNEAS DEL PEDIDO")
    sep()
    line_ids = o["order_line"]
    lines = env["sale.order.line"].read(
        line_ids,
        ["name","product_uom_qty","product_id","discount","price_unit","price_subtotal"]
    )

    # Enriquecer con default_code
    prod_ids = [l["product_id"][0] for l in lines if l.get("product_id")]
    prod_map = {}
    if prod_ids:
        prods = env["product.product"].search_read([["id","in",prod_ids]], ["default_code","categ_id"])
        prod_map = {p["id"]: p for p in prods}

    actual_portes = 0.0
    product_lines = []
    print(f"  {'SKU':<12} {'Nombre':<38} {'Cant':>7} {'Dto':>6} {'Subtotal':>10}")
    print(f"  {'':─<12} {'':─<38} {'':─<7} {'':─<6} {'':─<10}")

    for l in lines:
        lname = l["name"]
        qty = float(l.get("product_uom_qty") or 0)
        dto = float(l.get("discount") or 0)
        sub = float(l.get("price_subtotal") or 0)
        pid = l["product_id"][0] if l["product_id"] else None
        sku = prod_map.get(pid, {}).get("default_code", "") if pid else ""

        lname_l = lname.lower()
        if "portes" in lname_l or "entrega" in lname_l:
            actual_portes += sub
            marker = "  ← PORTES"
        else:
            marker = ""
            if qty > 0:
                categ = prod_map.get(pid, {}).get("categ_id", ["",""])[1] if pid else ""
                product_lines.append({
                    "sku": sku, "name": lname, "qty": qty,
                    "dto": dto, "sub": sub, "categ": categ
                })

        short_name = lname[:37] + "…" if len(lname) > 37 else lname
        print(f"  {(sku or '—'):<12} {short_name:<38} {qty:>7.0f} {dto:>5.1f}% {sub:>10,.2f}{marker}")

    sep()
    print(f"  Portes REAL en pedido : {fmt(actual_portes)}")

    # 5. Resumen de descuentos
    sep()
    print("  ANÁLISIS DESCUENTOS")
    sep()
    base = float(o["amount_untaxed"])
    tramo = "≤1.500€" if base <= 1500 else ">1.500€"
    print(f"  Base imponible: {fmt(base)} → tramo {tramo}")
    any_over = False
    for pl in product_lines:
        flag = ""
        if pl["dto"] > 30:
            flag = "  ⚠️  >30%"
            any_over = True
        elif pl["dto"] > 25:
            flag = "  ⚠️  >25%"
        print(f"  {pl['sku']:<12} dto={pl['dto']:.1f}%{flag}")

    # 6. Cálculo simplificado de portes esperados
    sep()
    print("  ANÁLISIS PORTES")
    sep()
    # Región aproximada por CP (lógica simplificada)
    region_label = "REGIÓN DESCONOCIDA"
    if zip_code:
        cp_num = int(zip_code[:2]) if zip_code[:2].isdigit() else 0
        baleares_prefixes = {"07"}
        canarias_prefixes = {"35","38"}
        cp2 = zip_code[:2]
        if cp2 in baleares_prefixes:
            region_label = "BALEARES"
        elif cp2 in canarias_prefixes:
            region_label = "CANARIAS"
        else:
            region_label = f"PENINSULA (CP {zip_code})"

    print(f"  Región detectada    : {region_label}")
    all_free = all(pl["dto"] >= (30 if "BAL" not in region_label else 25) - 0.01 for pl in product_lines if pl["qty"] > 0)
    print(f"  Todas líneas >30%dto: {'✅ Sí → Portes GRATIS esperados' if all_free else '❌ No'}")

    carrier_raw = o["carrier_id"][1].lower() if o.get("carrier_id") else ""
    is_recoge   = ("recoge" in carrier_raw and "cliente" in carrier_raw)
    print(f"  Transportista       : {o['carrier_id'][1] if o.get('carrier_id') else '—'}")
    print(f"  ¿Recoge cliente?    : {'✅ Sí → Portes GRATIS esperados' if is_recoge else '❌ No'}")
    is_platino = "Platino" in (o["pricelist_id"][1] if o.get("pricelist_id") else "")
    print(f"  ¿Tarifa Platino?    : {'✅ Sí → Portes GRATIS esperados' if is_platino else '❌ No'}")

    sep()
    if all_free or is_recoge or is_platino:
        portes_esperados = 0.0
        motivo = "Exención aplicada"
    else:
        portes_esperados = None  # Necesita SKU_MASTER completo para calcular exacto
        motivo = "Calculado por grupo de producto (ver validador)"

    print(f"  Portes REAL         : {fmt(actual_portes)}")
    if portes_esperados is not None:
        print(f"  Portes ESPERADOS    : {fmt(portes_esperados)}")
        diff = abs(actual_portes - portes_esperados)
        if diff > 0.01:
            print(f"  ❌ DIFERENCIA       : {fmt(diff)}  → CAUSA DEL WARNING")
        else:
            print(f"  ✅ Sin diferencia en portes")
    else:
        print(f"  Portes ESPERADOS    : {motivo}")

    sep()
    print("  VEREDICTO")
    sep()
    issues = []
    if actual_portes == 0 and not all_free and not is_recoge and not is_platino:
        issues.append("Sin línea de portes cuando debería haberla")
    if actual_portes > 0 and (all_free or is_recoge or is_platino):
        issues.append(f"Portes cobrados ({fmt(actual_portes)}) cuando debería ser GRATIS")
    if any_over:
        issues.append("Hay descuentos >30% → revisar con validador completo")
    if not issues:
        issues.append("Diferencia en importe de portes (tarifa de grupo no coincide)")

    for i in issues:
        print(f"  ⚠️  {i}")
    sep()

if __name__ == "__main__":
    main()
