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
        Ticket = service.odoo.env['helpdesk.ticket']
        # Find a ticket to resolve
        tickets = Ticket.search_read([('stage_id', 'not in', [4, 5, 6])], ['id', 'name'], limit=1)
        if tickets:
            t_id = tickets[0]['id']
            odoo_vals = {
                'x_root_cause': 'Test root cause',
                'x_final_action': 'Test final action',
                'x_client_conform': True,
                'stage_id': 4
            }
            try:
                # Use context to suppress automatic notifications
                TicketContext = Ticket.with_context(
                    mail_notrack=True,
                    tracking_disable=True
                )
                TicketContext.write(t_id, odoo_vals)
                res = {'success': True, 'ticket_id': t_id}
            except Exception as e:
                res = {'success': False, 'error': str(e), 'ticket_id': t_id}
        else:
            res = {'success': False, 'error': 'No open tickets found'}
            
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_resolve_test.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except Exception as e:
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_resolve_test.json', 'w', encoding='utf-8') as f:
            json.dump({'error': str(e)}, f)
