import sys
import os
import json
from dotenv import load_dotenv

env_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\app\.env'
load_dotenv(env_path)

sys.path.append(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\app')

from db.services.odoo_service_v2 import OdooServiceV2

service = OdooServiceV2()
if service.connect():
    try:
        Stage = service.odoo.env['helpdesk.stage']
    except Exception as e:
        stage_err = str(e)
    else:
        stage_err = "Exists"
        
    try:
        TicketStage = service.odoo.env['helpdesk.ticket.stage']
        stages = TicketStage.search_read([], ['id', 'name'])
    except Exception as e:
        ticket_stage_err = str(e)
        stages = []
        
    res = {
        'helpdesk.stage': stage_err,
        'helpdesk.ticket.stage': ticket_stage_err if 'ticket_stage_err' in locals() else 'Exists',
        'stages': stages
    }
    
    with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_stages2.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
