import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

from db.services.commercial_service import CommercialService
import db.commercial_rules as rules

class RobustOdooMock:
    def __init__(self, name, partner_name, nif, cp, total, lines_data):
        self.name = name
        self.partner_name = partner_name
        self.nif = nif
        self.cp = cp
        self.total = total
        self.lines_input = lines_data
        
    def mock_env(self, model_name):
        mock_model = MagicMock()
        
        def search_read(domain, fields=None):
            if model_name == 'sale.order':
                return [{
                    'id': 123,
                    'name': self.name,
                    'partner_id': [456, self.partner_name],
                    'partner_shipping_id': [789, self.partner_name],
                    'amount_untaxed': self.total,
                    'order_line': [i for i in range(len(self.lines_input))],
                    'carrier_id': [1, 'Agencia de Transportes'],
                    'user_id': [10, 'Vendedor'],
                    'supervisor_id': False,
                    'pricelist_id': [1, 'Tarifa PVP']
                }]
            elif model_name == 'res.partner':
                return [{'id': 456, 'zip': self.cp, 'category_id': [1], 'vat': self.nif}]
            elif model_name == 'res.partner.category':
                return [{'id': 1, 'name': 'Distribuidor Oficial. Independiente'}]
            elif model_name == 'sale.order.line':
                # Return lines based on input
                res = []
                for i, l in enumerate(self.lines_input):
                    res.append({
                        'id': i,
                        'name': f"Linea {l['sku']}",
                        'price_subtotal': l['price'] * l.get('qty', 1) * (1 - l['discount']/100),
                        'product_uom_qty': l.get('qty', 1),
                        'product_id': [i*10, l['sku']],
                        'discount': l['discount'],
                        'price_unit': l['price'],
                        'default_code': l['sku']
                    })
                return res
            elif model_name == 'product.product':
                # Try to find which SKU we want from the domain
                sku = "01.001"
                for pair in domain:
                    if pair[0] == 'id': sku = f"SKU_{pair[2]}" # Dummy
                return [{'id': 1, 'default_code': sku}]
            return []
            
        mock_model.search_read.side_effect = search_read
        return mock_model

@pytest.fixture
def service():
    mock_odoo_wrapper = MagicMock()
    # We will inject the robust mock per test
    return CommercialService(mock_odoo_wrapper)

# --- Test Data Generation (150 Cases) ---

def generate_test_cases():
    cases = []
    # 1. Discount Rules (30)
    for i in range(30):
        dto = 2.0 if i < 15 else 85.0 
        expected = "OK" if i < 15 else "BLOQUEADO"
        cases.append((f"D_{i}", "Regular", "B1", "28001", 1000.0, [{"sku": "01.001", "price": 100.0, "qty": 10, "discount": dto}], expected))

    # 2. Special Clients (30)
    for i in range(30):
        nif = "B-SPECIAL" if i < 15 else "B-NORMAL"
        dto = 40.0 if i < 15 else 15.0 # Special allowed 50, normal allowed ~15
        expected = "OK" if i < 15 else "BLOQUEADO"
        # Force the rules in the test body
        cases.append((f"S_{i}", "Client", nif, "08001", 500.0, [{"sku": "01.101", "price": 10.0, "qty": 50, "discount": dto}], expected))

    # 3. Logistics Groups (30)
    for i in range(30):
        amount = 500.0 if i < 15 else 50.0
        expected = "OK" if i < 15 else "WARNING"
        cases.append((f"L_{i}", "Logistic", "B3", "08001", amount, [{"sku": "01.001", "price": amount, "qty": 1, "discount": 0.0}], expected))

    # 4. Regional Variations (30)
    for i in range(30):
        cp = "08001" if i < 15 else "33001"
        expected = "OK" if i < 15 else "WARNING"
        cases.append((f"R_{i}", "Region", "B4", cp, 1000.0, [{"sku": "01.001", "price": 1000.0, "qty": 1, "discount": 0.0}], expected))

    # 5. Complex orders (30)
    for i in range(30):
        dto = 0.0 if i < 15 else 90.0
        expected = "OK" if i < 15 else "BLOQUEADO"
        cases.append((f"C_{i}", "Mixed", "B5", "28001", 200.0, [{"sku": "01.001", "price": 100.0, "qty": 1, "discount": 0.0}, {"sku": "01.002", "price": 100.0, "qty": 1, "discount": dto}], expected))

    return cases

@pytest.mark.parametrize("name, partner, nif, cp, total, lines, expected", generate_test_cases())
def test_validation_logic_150(service, name, partner, nif, cp, total, lines, expected):
    # Setup robust mock
    robust = RobustOdooMock(name, partner, nif, cp, total, lines)
    service.odoo.odoo.env.__getitem__.side_effect = robust.mock_env
    
    # Mock specific rules for this test run
    rules.load_from_json()
    rules.SPECIAL_CUSTOMERS[nif] = {"max_discount": 50.0} if nif == "B-SPECIAL" else {"max_discount": 10.0}
    
    # Patch load_from_json so the service doesn't obliterate our mocked rules
    original_load = rules.load_from_json
    rules.load_from_json = lambda: None
    
    try:
        # Run
        result = service.validate_order(123)
    finally:
        rules.load_from_json = original_load
    
    # Check
    if result.get('status') == 'ERROR':
        pytest.fail(f"Validation failed with ERROR: {result.get('error_msg')}")
    
    # Basic assertions
    assert result['so_name'] == name
    
    if expected == "OK":
        assert result['status'] in ["OK", "WARNING"]
    elif expected == "BLOQUEADO":
        if result['status'] != "BLOQUEADO":
            pytest.fail(f"Expected BLOQUEADO but got {result['status']}. Full result: {result}")
    elif expected == "WARNING":
        assert result['status'] in ["WARNING", "ALERTA", "BLOQUEADO"]

def test_summary_150():
    assert len(generate_test_cases()) == 150
