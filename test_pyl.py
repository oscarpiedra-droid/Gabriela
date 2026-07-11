
import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.db.services.homologacion_service import HomologacionService, HomologacionStatus

svc = HomologacionService()
res = svc.homologar("PYL")

print(f"Odoo Tag: {res.odoo_tipo_cliente}")
print(f"Segment: {res.segmento_aplicacion}")
print(f"Status: {res.status}")

res2 = svc.homologar("Almacenes Especialistas (PYL)")
print(f"\nOdoo Tag: {res2.odoo_tipo_cliente}")
print(f"Segment: {res2.segmento_aplicacion}")
print(f"Status: {res2.status}")
