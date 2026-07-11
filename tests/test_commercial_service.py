import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))
from unittest.mock import MagicMock
from db.services.commercial_service import CommercialService

@pytest.fixture
def mock_odoo():
    odoo = MagicMock()
    return odoo

@pytest.fixture
def commercial_service(mock_odoo):
    return CommercialService(mock_odoo)

def test_get_filtered_clients(commercial_service):
    validations = [
        {'status': 'BLOQUEADO', 'partner_id_int': 1, 'partner_name': 'Cliente A', 'fuga_comercial': 150.0, 'so_name': 'SO001'},
        {'status': 'BLOQUEADO', 'partner_id_int': 1, 'partner_name': 'Cliente A', 'fuga_comercial': 50.0, 'so_name': 'SO002'},
        {'status': 'OK', 'partner_id_int': 2, 'partner_name': 'Cliente B', 'fuga_comercial': 0.0, 'so_name': 'SO003'},
        {'status': 'ERROR', 'partner_id_int': 3, 'partner_name': 'Cliente C', 'fuga_comercial': 500.0, 'so_name': 'SO004'}
    ]
    
    clients = commercial_service.get_filtered_clients(validations)
    
    assert len(clients) == 2
    # Client C has higher fuga so should be first
    assert clients[0]['partner_id'] == 3
    assert clients[0]['total_fuga'] == 500.0
    assert clients[0]['blocked_count'] == 1
    assert clients[0]['orders'] == ['SO004']
    
    # Client A should be second
    assert clients[1]['partner_id'] == 1
    assert clients[1]['total_fuga'] == 200.0
    assert clients[1]['blocked_count'] == 2
    assert clients[1]['orders'] == ['SO001', 'SO002']
    assert clients[1]['partner_name'] == 'Cliente A'

def test_calculate_fuga_comercial(commercial_service):
    validations = [
        {'status': 'BLOQUEADO', 'fuga_comercial': 150.0},
        {'status': 'ERROR', 'fuga_comercial': 50.0},
        {'status': 'OK', 'fuga_comercial': 0.0},
        {'status': 'WARNING', 'fuga_comercial': 20.0}
    ]
    
    fuga = commercial_service.calculate_fuga_comercial(validations=validations)
    
    assert fuga == 220.0

def test_get_ai_suggestions(commercial_service):
    validations = [
        {'status': 'BLOQUEADO', 'partner_id_int': 1, 'partner': 'Cliente A'},
        {'status': 'BLOQUEADO', 'partner_id_int': 1, 'partner': 'Cliente A'},
        {'status': 'OK', 'partner_id_int': 2, 'partner': 'Cliente B'},
    ]
    
    suggestions = commercial_service.get_ai_suggestions(validations)
    assert len(suggestions) == 1
    assert suggestions[0]['partner_id'] == 1
    assert "Cliente A" in suggestions[0]['msg']
