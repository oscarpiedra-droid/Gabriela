import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv()
from app.db.services.odoo_service_v2 import OdooServiceV2

svc = OdooServiceV2()
if not svc.connect():
    print("No conectado"); exit()

env = svc.odoo.env

# Buscar el pedido SO50214
orders = env['sale.order'].search_read([['name','=','SO50214']], ['partner_id','partner_shipping_id'])
if not orders:
    print("SO50214 no encontrado"); exit()

o = orders[0]
p_id = o['partner_id'][0]
p_name = o['partner_id'][1]
print(f"Cliente: {p_name} (id={p_id})")

# Tags del cliente
partner = env['res.partner'].search_read([['id','=',p_id]], ['name','category_id','zip','city'])
pr = partner[0]
print(f"CP: {pr.get('city','')}, {pr.get('zip','')}")
print(f"category_id (raw): {pr['category_id']}")

if pr['category_id']:
    cats = env['res.partner.category'].read(pr['category_id'], ['name','parent_id'])
    print(f"Tags en Odoo:")
    for c in cats:
        parent = c['parent_id'][1] if c.get('parent_id') else '—'
        print(f"  id={c['id']}  nombre='{c['name']}'  padre='{parent}'")
else:
    print("Sin categorías/tags asignados en Odoo")

# Verificar en catálogo homologación
from app.db.services.homologacion_service import HomologacionService
homo = HomologacionService()
print(f"\nEntradas en catálogo homologación ({homo.get_catalog_size()}):")
for e in homo.listar_entradas():
    print(f"  '{e['odoo_tipo_cliente']}' → '{e['segmento_aplicacion']}'")
