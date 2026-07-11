
import os
import sys
from dotenv import load_dotenv
import json

# Añadir la raíz del proyecto al sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Cargar .env
load_dotenv()

from loguru import logger

try:
    from app.db.services.odoo_service_v2 import OdooServiceV2
except ImportError as e:
    print(f"Error de importación: {e}")
    sys.exit(1)

def explore():
    odoo_svc = OdooServiceV2()
    if not odoo_svc.connect():
        print("No se pudo conectar a Odoo")
        return

    Partner = odoo_svc.odoo.env['res.partner']
    Tag = odoo_svc.odoo.env['res.partner.category']
    
    # Buscar tags usados
    all_partners = Partner.search_read([('category_id', '!=', False)], fields=['category_id'], limit=3000)
    
    used_tag_ids = set()
    for p in all_partners:
        if p.get('category_id'):
            for tid in p['category_id']:
                used_tag_ids.add(tid)
    
    results = []
    if used_tag_ids:
        tags_data = Tag.read(list(used_tag_ids), ['name', 'parent_id'])
        for t in tags_data:
            parent = t['parent_id'][1] if t['parent_id'] else ""
            full_name = f"{parent} / {t['name']}" if parent else t['name']
            results.append({"name": t['name'], "full_name": full_name, "id": t['id']})
    
    with open('odoo_tags.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    
    print(f"Sincronizados {len(results)} tags en odoo_tags.json")

if __name__ == "__main__":
    explore()
