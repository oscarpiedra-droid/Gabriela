
import os
import sys
from dotenv import load_dotenv

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

def explore_partner_fields():
    print("Iniciando servicio Odoo...")
    # OdooServiceV2 lee de os.getenv en el __init__ si no se pasan parámetros
    odoo_svc = OdooServiceV2()
    
    print(f"Conectando a {odoo_svc.url} / {odoo_svc.db}...")
    if not odoo_svc.connect():
        logger.error("No se pudo conectar a Odoo. Verifica el archivo .env")
        return
    print("Conectado con éxito.")

    Partner = odoo_svc.odoo.env['res.partner']
    
    # Intentar obtener la definición de los campos
    print("Obteniendo definición de campos interesantes...")
    fields = Partner.fields_get()
    
    keywords = ['tipo', 'type', 'client', 'category', 'segment', 'tag']
    interesting_fields = {k: v for k, v in fields.items() if any(kw in k.lower() or kw in v.get('string', '').lower() for kw in keywords)}
    
    print("\n--- CAMPOS INTERESANTES EN res.partner ---")
    for fname, fdef in interesting_fields.items():
        print(f"- {fname}: {fdef.get('string')} ({fdef.get('type')})")

    # Listar todas las etiquetas presentes en partners
    print("\n--- LISTANDO ETIQUETAS USADAS (category_id) ---")
    Tag = odoo_svc.odoo.env['res.partner.category']
    # Buscamos tags que estén en uso
    all_partners = Partner.search_read([('category_id', '!=', False)], fields=['category_id'], limit=1000)
    
    used_tag_ids = set()
    for p in all_partners:
        if p.get('category_id'):
            for tid in p['category_id']:
                used_tag_ids.add(tid)
            
    if used_tag_ids:
        # read() devuelve una lista de diccionarios
        tags_data = Tag.read(list(used_tag_ids), ['name', 'parent_id'])
        print(f"Total de etiquetas distintas encontradas en uso: {len(tags_data)}")
        for t in sorted(tags_data, key=lambda x: x['name']):
            parent = t['parent_id'][1] if t['parent_id'] else ""
            full_name = f"{parent} / {t['name']}" if parent else t['name']
            print(f"  * {full_name} (ID: {t['id']})")
    else:
        print("No se encontraron etiquetas en uso en partners.")

if __name__ == "__main__":
    explore_partner_fields()
