from pathlib import Path
import sys
import os
from dotenv import load_dotenv

env_path = str(Path(__file__).resolve().parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('app').joinpath('.env'))
load_dotenv(env_path)

sys.path.append(Nonestr(Path(__file__).resolve().parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('app')))

from db.services.odoo_service_v2 import OdooServiceV2

service = OdooServiceV2()
if service.connect():
    print("Connected!")
    try:
        Ticket = service.odoo.env['helpdesk.ticket']
        print("helpdesk.ticket model exists!")
        tickets = Ticket.search_read([], ['name', 'stage_id'], limit=5)
        for t in tickets:
            print(t)
    except Exception as e:
        print(f"Error fetching tickets: {e}")
else:
    print("Failed to connect.")
