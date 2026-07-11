
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(r'C:\Users\User\Desktop\Bur2000_v2\Gabriela\app'))
sys.path.insert(0, os.path.abspath(r'C:\Users\User\Desktop\Bur2000_v2\Gabriela'))
load_dotenv(os.path.abspath(r'C:\Users\User\Desktop\Bur2000_v2\Gabriela\app\.env'))

from app.db.services.odoo_service_v2 import OdooServiceV2
from app.db.services.commercial_service import CommercialService

c = OdooServiceV2()
c._ensure_connected()
svc = CommercialService(c)
res = svc.get_pending_orders()
import json

orders = [o for o in res if o.get('name') == 'SO49803']
with open('res_pending.json', 'w', encoding='utf-8') as f:
    json.dump(orders, f, indent=2)

