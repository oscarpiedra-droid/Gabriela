import os, sys
# Add app to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from db.connection import OdooService
from db.services.homologacion_service import HomologacionService, HomologacionStatus
from loguru import logger

def scan_homologation():
    odoo = OdooService()
    homologacion_svc = HomologacionService()
    
    with odoo._lock:
        odoo._ensure_connected()
        SO = odoo.odoo.env['sale.order']
        # Fetch confirmed sale orders
        domain = [('state_order_id.name', 'ilike', 'Pedido Emitido')]
        recs = SO.search_read(domain, ['name', 'partner_id', 'amount_untaxed'], limit=100)
        
        print(f"Scanning {len(recs)} orders...")
        for r in recs:
            so_name = r['name']
            partner = r['partner_id']
            # Get odoo_tipo_cliente from partner
            partner_id = partner[0] if partner else None
            if not partner_id: continue
            
            p_data = odoo.odoo.execute_kw(odoo.db, odoo.uid, odoo.password, 'res.partner', 'read', [partner_id], ['tipo_cliente'])
            tipo_cliente = p_data[0].get('tipo_cliente') if p_data else None
            
            res = homologacion_svc.homologar(tipo_cliente)
            if res.status == HomologacionStatus.SIN_HOMOLOGACION:
                print(f"[SIN_HOMO] {so_name} | Client Type: '{tipo_cliente}' | Partner: {partner[1]}")
            elif res.status != HomologacionStatus.OK:
                print(f"[{res.status}] {so_name} | Segmento: '{res.segmento_aplicacion}'")

if __name__ == "__main__":
    scan_homologation()
