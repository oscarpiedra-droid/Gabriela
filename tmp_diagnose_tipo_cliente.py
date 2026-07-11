"""
Diagnóstico: descubre dónde vive el campo 'Tipo de cliente' para SO50189.
Ejecutar desde la raíz del proyecto con el entorno conda gabriela:
    python tmp_diagnose_tipo_cliente.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv()
from app.db.services.odoo_service_v2 import OdooServiceV2

svc = OdooServiceV2()
if not svc.connect():
    print("No conectado"); exit()

env = svc.odoo.env
SO_NAME = "SO50189"

# ── 1. Buscar el pedido ────────────────────────────────────────────
orders = env['sale.order'].search_read([['name', '=', SO_NAME]], ['partner_id'])
if not orders:
    print(f"{SO_NAME} no encontrado"); exit()

o = orders[0]
so_id   = o['id']
p_id    = o['partner_id'][0]
p_name  = o['partner_id'][1]
print(f"\n>> Pedido {SO_NAME}  id={so_id}")
print(f">> Cliente: {p_name}  (partner_id={p_id})\n")

# ── 2. Buscar campos 'tipo' en sale.order ─────────────────────────
print("="*60)
print("[sale.order] Campos que contienen 'tipo'/'cliente'/'segmento':")
print("="*60)
so_fields = env['sale.order'].fields_get(attributes=['string', 'type', 'relation'])
tipo_so = {k: v for k, v in so_fields.items()
           if any(t in (k + v.get('string', '')).lower()
                  for t in ['tipo', 'client', 'segmen', 'x_tipo'])}
for fname, info in sorted(tipo_so.items()):
    print(f"  {fname:45s} [{info['type']:12s}] '{info['string']}'")

if tipo_so:
    vals = env['sale.order'].read([so_id], list(tipo_so.keys()))[0]
    print(f"\n  Valores en SO{so_id}:")
    for k in sorted(tipo_so):
        print(f"    {k:45s} = {vals.get(k)!r}")

# ── 3. Buscar campos 'tipo' en res.partner ────────────────────────
print("\n" + "="*60)
print("[res.partner] Campos que contienen 'tipo'/'segmento'/'customer':")
print("="*60)
rp_fields = env['res.partner'].fields_get(attributes=['string', 'type', 'relation'])
tipo_rp = {k: v for k, v in rp_fields.items()
           if any(t in (k + v.get('string', '')).lower()
                  for t in ['tipo', 'segmen', 'customer_type', 'x_tipo'])}
for fname, info in sorted(tipo_rp.items()):
    print(f"  {fname:45s} [{info['type']:12s}] '{info['string']}'")

if tipo_rp:
    rp_vals = env['res.partner'].read([p_id], list(tipo_rp.keys()))[0]
    print(f"\n  Valores en partner {p_id}:")
    for k in sorted(tipo_rp):
        print(f"    {k:45s} = {rp_vals.get(k)!r}")

# ── 4. Ver category_id (etiquetas actuales) ───────────────────────
print("\n" + "="*60)
print(f"[res.partner id={p_id}] category_id (etiquetas/tags):")
print("="*60)
pr = env['res.partner'].read([p_id], ['category_id', 'name'])[0]
cat_ids = pr.get('category_id', [])
if cat_ids:
    cats = env['res.partner.category'].read(cat_ids, ['name', 'parent_id'])
    for c in cats:
        parent = c['parent_id'][1] if c.get('parent_id') else '(sin padre)'
        print(f"  id={c['id']:5d}  nombre='{c['name']}'  padre='{parent}'")
else:
    print("  *** SIN etiquetas (category_id=[]) — por eso falla la homologación ***")

print("\n>> Diagnóstico completo.\n")
