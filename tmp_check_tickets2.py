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
        # Let's get the distinct stage_ids from active tickets
        tickets = Ticket.search_read([], ['stage_id'], limit=50)
        stages = {}
        for t in tickets:
            if t.get('stage_id'):
                s = t['stage_id']
                stages[s[0]] = s[1]
                
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_stages.json', 'w', encoding='utf-8') as f:
            json.dump(stages, f)
            
    except Exception as e:
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_stages.json', 'w', encoding='utf-8') as f:
            json.dump({'error': str(e)}, f)
