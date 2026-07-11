import sys
import os
from dotenv import load_dotenv

env_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\app\.env'
load_dotenv(env_path)

sys.path.append(r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\app')

from db.services.odoo_service_v2 import OdooServiceV2

service = OdooServiceV2()
if service.connect():
    print("Connected!")
    try:
        Stage = service.odoo.env['helpdesk.stage']
        stages = Stage.search_read([], ['id', 'name'])
        for s in stages:
            print(f"Stage ID: {s['id']}, Name: {s['name']}")
    except Exception as e:
        print(f"Error fetching stages: {e}")
else:
    print("Failed to connect.")
