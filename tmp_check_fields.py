from pathlib import Path
import sys
import os
import json
from dotenv import load_dotenv

env_path = str(Path(__file__).resolve().parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('app').joinpath('.env'))
load_dotenv(env_path)

sys.path.append(Nonestr(Path(__file__).resolve().parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('app')))

from db.services.odoo_service_v2 import OdooServiceV2

service = OdooServiceV2()
if service.connect():
    try:
        Ticket = service.odoo.env['helpdesk.ticket']
        fields = Ticket.fields_get()
        field_keys = list(fields.keys())
        
        # Check custom fields in the service
        custom_fields = [
            'x_root_cause', 'x_final_action', 'x_client_conform', 
            'x_sale_order_id', 'x_picking_id', 'x_units_affected'
        ]
        
        present = {}
        for cf in custom_fields:
            if cf in fields:
                present[cf] = fields[cf]['type']
            else:
                present[cf] = "Missing"
        
        res = {
            "all_x_fields": [f for f in field_keys if f.startswith('x_')],
            "custom_fields_check": present
        }
        
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_check_fields.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except Exception as e:
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_check_fields.json', 'w', encoding='utf-8') as f:
            json.dump({'error': str(e)}, f)
