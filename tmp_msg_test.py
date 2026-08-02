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
        # Find a ticket to post message
        tickets = Ticket.search_read([], ['id', 'name'], limit=1)
        res = {'success': False, 'msg': 'No open tickets found'}
        if tickets:
            t_id = tickets[0]['id']
            try:
                TicketContext = Ticket.with_context(
                    mail_notrack=True,
                    tracking_disable=True
                )
                TicketContext.message_post(t_id, body='Test message from Gabriela', message_type='comment', subtype_xmlid='mail.mt_comment')
                res = {'success': True, 'ticket_id': t_id}
            except Exception as e:
                res = {'success': False, 'error': str(e), 'ticket_id': t_id}
            
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_msg_test.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except Exception as e:
        with open(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\tmp_msg_test.json', 'w', encoding='utf-8') as f:
            json.dump({'error': str(e)}, f)
