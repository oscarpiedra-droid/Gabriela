import re
import unicodedata
import os
import base64
from typing import List, Dict, Any, Optional
from loguru import logger
from .customer_local_db import CustomerLocalDB

class CustomerOnboardingService:
    def __init__(self, odoo_service):
        self.odoo_service = odoo_service
        self.local_db = CustomerLocalDB()

    def _ensure_connected(self):
        self.odoo_service._ensure_connected()

    def normalize_str(self, text: str) -> str:
        if not text:
            return ""
        # Remove accents
        text = "".join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        )
        # To uppercase
        text = text.upper().strip()
        # Remove double spaces
        text = re.sub(r'\s+', ' ', text)
        return text

    def normalize_name(self, name: str, is_individual: bool = False) -> str:
        normalized = self.normalize_str(name)
        if is_individual and "," not in normalized:
            # Simple heuristic: split by space and rearrange 
            # (assuming last word or two are name? No, usually first two are surnames)
            # Given the complexity, we'll just normalize what the user inputs, 
            # but provide a hint in the UI.
            return normalized
        return normalized

    def normalize_phone(self, phone: str) -> str:
        if not phone: return ""
        # Remove non-numeric characters except +
        return re.sub(r'[^\d+]', '', phone)

    def search_by_nif(self, nif: str) -> List[Dict[str, Any]]:
        self._ensure_connected()
        Partner = self.odoo_service.odoo.env['res.partner']
        # Remove dots/hyphens for more robust search if needed, but spec says "Copiar valor validado"
        # We search by vat field in Odoo
        recs = Partner.search_read([('vat', '=', nif)], ['id', 'name', 'vat', 'is_company'])
        return recs

    def search_by_nifs(self, nifs: List[str]) -> Dict[str, int]:
        """Bulk search for several NIFs, returning a map {nif: partner_id}."""
        if not nifs:
            return {}
        self._ensure_connected()
        Partner = self.odoo_service.odoo.env['res.partner']
        # Remove empty strings
        nifs = [n for n in nifs if n.strip()]
        if not nifs:
            return {}
        
        recs = Partner.search_read([('vat', 'in', nifs)], ['id', 'vat'])
        return {r['vat']: r['id'] for r in recs if r.get('vat')}

    def search_by_name(self, name: str) -> List[Dict[str, Any]]:
        self._ensure_connected()
        Partner = self.odoo_service.odoo.env['res.partner']
        # Searching by name for the "duplicate alert"
        recs = Partner.search_read([('name', '=', name)], ['id', 'name', 'vat', 'is_company'])
        return recs

    def get_supervisor_for_commercial(self, commercial_name: str) -> Optional[str]:
        # Based on spec: JORDI CODINA -> ADRIAN VALLE
        mapping = {
            "JORDI CODINA": "ADRIAN VALLE",
            # Add more based on Bur2000 reality
        }
        return mapping.get(commercial_name.upper())

    def get_location_from_zip(self, zip_code: str) -> Optional[Dict[str, Any]]:
        self._ensure_connected()
        # Heuristic search in existing partners to guess city/state
        Partner = self.odoo_service.odoo.env['res.partner']
        recs = Partner.search_read([('zip', '=', zip_code)], ['city', 'state_id'], limit=1)
        if recs and recs[0].get('city'):
            return {
                'city': recs[0]['city'],
                'state_id': recs[0]['state_id'][0] if recs[0].get('state_id') else None,
                'state_name': recs[0]['state_id'][1] if recs[0].get('state_id') else None,
            }
        return None

    def get_all_states(self) -> List[Dict[str, Any]]:
        self._ensure_connected()
        State = self.odoo_service.odoo.env['res.country.state']
        Country = self.odoo_service.odoo.env['res.country']
        spain = Country.search([('code', '=', 'ES')], limit=1)
        domain = [('country_id', '=', spain[0])] if spain else []
        return State.search_read(domain, ['id', 'name'], order='name asc')

    def create_or_update_customer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point for onboarding.
        data keys expected:
          - nif (str)
          - is_company (bool)
          - name (str)
          - street (str)
          - zip (str)
          - city (str, optional - will try auto-fill)
          - state_id (int, optional)
          - phone (str)
          - mobile (str)
          - email_facturacion (str)
          - email_principal (str)
          - commercial_agent (str)
          - customer_type (str)
          - payment_mode (str)
          - payment_terms (str)
          - iban (str, optional)
          - delivery_address (dict, optional: street, zip, phone, email, notes)
          - document_path (str, optional)
        """
        self._ensure_connected()
        nif = data.get('nif', "").strip()
        if not nif:
            return {"status": "error", "message": "NIF obligatorio"}
            
        # IBAN Early Validation
        iban_clean = None
        if data.get('iban'):
            iban_clean = data['iban'].replace(" ", "").upper()
            if not re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$', iban_clean):
                return {"status": "error", "message": f"El formato del IBAN no es válido: {data['iban']}"}

        normalized_name = self.normalize_name(data['name'], not data['is_company'])
        
        # 1. Search existing
        existing_partners = self.search_by_nif(nif)
        partner_id = None
        action_type = "alta"

        if existing_partners:
            partner_id = existing_partners[0]['id']
            action_type = "actualizacion"
            logger.info(f"Found existing partner {partner_id} for NIF {nif}")
        else:
            # Check by name just for alert
            by_name = self.search_by_name(normalized_name)
            if by_name:
                logger.warning(f"Coincidencia por nombre ({normalized_name}) pero no NIF ({nif}). Alerta duplicado.")
        
        # 2. Build values
        res_partner_vals = {
            'is_company': data.get('is_company', True),
            'name': normalized_name,
            'street': self.normalize_str(data.get('street', "")),
            'zip': data.get('zip', ""),
            'vat': nif,
            'customer_rank': 1,  # Odoo 14+ reemplaza el bool 'customer' con este entero (≥1 = cliente)
        }
        
        # Phone logic: Rule 5 - Si solo hay uno, repetirlo
        p1 = self.normalize_phone(data.get('phone', ""))
        p2 = self.normalize_phone(data.get('mobile', ""))
        if p1 and not p2: p2 = p1
        if p2 and not p1: p1 = p2
        res_partner_vals['phone'] = p1
        res_partner_vals['mobile'] = p2

        # Email logic: Rule 7.1 - Prioridad absoluta al email de facturacion
        email_fact = data.get('email_facturacion', "").strip()
        email_princ = data.get('email_principal', "").strip()
        final_admin_email = email_fact or email_princ
        res_partner_vals['email'] = final_admin_email

        # Search for CP/City if needed
        if data.get('zip') and not data.get('city'):
            loc = self.get_location_from_zip(data['zip'])
            if loc:
                res_partner_vals['city'] = loc['city']
                if not data.get('state_id'):
                    res_partner_vals['state_id'] = loc['state_id']
        elif data.get('city'):
             res_partner_vals['city'] = self.normalize_str(data['city'])
        
        if data.get('state_id'):
            res_partner_vals['state_id'] = data['state_id']

        # Venta y Compra Tab (7.3)
        # Commercial / User ID
        if data.get('commercial_agent'):
            User = self.odoo_service.odoo.env['res.users']
            users = User.search_read([('name', 'ilike', data['commercial_agent'])], ['id'], limit=1)
            if users:
                res_partner_vals['user_id'] = users[0]['id']
                # Supervisor lookup
                supervisor_name = self.get_supervisor_for_commercial(data['commercial_agent'])
                if supervisor_name:
                    supervisors = User.search_read([('name', 'ilike', supervisor_name)], ['id'], limit=1)
                    if supervisors:
                        res_partner_vals['supervisor_id'] = supervisors[0]['id']

        # Plazos de pago
        if data.get('payment_terms'):
            PaymentTerm = self.odoo_service.odoo.env['account.payment.term']
            terms = PaymentTerm.search_read([('name', 'ilike', data['payment_terms'])], ['id'], limit=1)
            if terms:
                res_partner_vals['property_payment_term_id'] = terms[0]['id']
                
        # Modo de pago
        if data.get('payment_mode'):
            PaymentMode = self.odoo_service.odoo.env['account.payment.mode']
            modes = PaymentMode.search_read([('name', 'ilike', data['payment_mode'])], ['id'], limit=1)
            if modes:
                res_partner_vals['customer_payment_mode_id'] = modes[0]['id']
                
        # Tipo de cliente (Categoría)
        if data.get('customer_type'):
            Category = self.odoo_service.odoo.env['res.partner.category']
            cats = Category.search_read([('name', 'ilike', data['customer_type'])], ['id'], limit=1)
            if cats:
                # Many2many field notation for writing in dict via odoorpc is [(6, 0, [ids])]
                res_partner_vals['category_id'] = [(6, 0, [cats[0]['id']])]

        # Risk Management (7.4)
        if action_type == "alta":
            res_partner_vals.update({
                'credit_limit': 2000.0,
                # These fields depend on Bur2000's specific module for risk
                # Often x_risk_credit_policy or similar
            })

        # 3. Write to Odoo
        Partner = self.odoo_service.odoo.env['res.partner']
        try:
            if partner_id:
                Partner.write([partner_id], res_partner_vals)
            else:
                partner_id = Partner.create(res_partner_vals)
            
            # 4. Delivery Address (7.2)
            d_addr = data.get('delivery_address')
            if d_addr and d_addr.get('street'):
                # Search if d_addr already exists
                existing_child = Partner.search_read([
                    ('parent_id', '=', partner_id),
                    ('type', '=', 'delivery'),
                    ('street', '=', self.normalize_str(d_addr['street']))
                ], ['id'])
                
                delivery_vals = {
                    'parent_id': partner_id,
                    'type': 'delivery',
                    'name': self.normalize_str(d_addr.get('name', 'REF. OBRA')),
                    'street': self.normalize_str(d_addr['street']),
                    'zip': d_addr.get('zip', ""),
                    'phone': self.normalize_phone(d_addr.get('phone', "")),
                    'mobile': self.normalize_phone(d_addr.get('mobile', "")),
                    'comment': self.build_delivery_notes(d_addr),
                }
                
                if existing_child:
                    Partner.write([existing_child[0]['id']], delivery_vals)
                else:
                    Partner.create(delivery_vals)

            # 5. Bank Account (7.5)
            if iban_clean and data.get('payment_mode') == 'DOMICILIACION BANCARIA':
                Bank = self.odoo_service.odoo.env['res.partner.bank']
                existing_bank = Bank.search_read([('partner_id', '=', partner_id), ('acc_number', '=', iban_clean)], ['id'])
                if not existing_bank:
                    Bank.create({
                        'partner_id': partner_id,
                        'acc_number': iban_clean,
                    })

            # 6. Chatter (Rule 6.2)
            msg = f"<h3>Alta/actualización generada desde Bur2000</h3>"
            msg += f"<p><b>Operación:</b> {action_type.upper()}</p>"
            
            # Detalle comercial solicitado
            msg += "<h4>Condiciones Comerciales Solicitadas:</h4><ul>"
            msg += f"<li><b>Condiciones:</b> {data.get('requested_conditions', 'N/A')}</li>"
            msg += f"<li><b>Descuentos:</b> {data.get('commercial_discounts', 'N/A')}</li>"
            msg += f"<li><b>Facturación Estimada:</b> {data.get('estimated_revenue', '0')} €</li>"
            msg += f"<li><b>Grupo Descuento:</b> {data.get('discount_group', 'General')}</li>"
            msg += "</ul>"
            
            Partner.message_post([partner_id], body=msg, message_type='comment', subtype_id='mail.mt_note')
            
            # 7. Attachment implementation if document_path exists (Rule 7.5)
            doc_path = data.get('document_path')
            if doc_path and os.path.exists(doc_path):
                try:
                    with open(doc_path, "rb") as f:
                        file_content = f.read()
                        encoded_content = base64.b64encode(file_content).decode('ascii')
                    
                    Attachment = self.odoo_service.odoo.env['ir.attachment']
                    Attachment.create({
                        'name': os.path.basename(doc_path),
                        'datas': encoded_content,
                        'res_model': 'res.partner',
                        'res_id': partner_id,
                    })
                    logger.info(f"Attachment created for partner {partner_id} from {doc_path}")
                except Exception as att_err:
                    logger.error(f"Error creating attachment: {att_err}")

            # ── Guardar también en BD local ───────────────────────────
            try:
                local_id = self.local_db.upsert(data, partner_id, action_type)
                logger.info(f"[LocalDB] Guardado local OK → id_local={local_id}")
            except Exception as local_err:
                logger.warning(f"[LocalDB] No se pudo guardar localmente: {local_err}")
                local_id = None
            # ──────────────────────────────────────────────────────────

            return {
                "status": "success",
                "partner_id": partner_id,
                "action": action_type,
                "local_id": local_id,
            }

        except Exception as e:
            logger.error(f"Error onboarding customer: {e}")
            return {"status": "error", "message": str(e)}

    def build_delivery_notes(self, d_addr: Dict) -> str:
        # Rule 7.2 format
        notes = []
        notes.append(f"LLAMAR ANTES A {self.normalize_str(d_addr.get('contact_name', ''))}")
        notes.append(f"{'SI' if d_addr.get('access_trailer') else 'NO'} ACCEDE TRAILER")
        notes.append(f"{'SI' if d_addr.get('descarga_medios') else 'NO'} TIENEN MEDIOS DE DESCARGA")
        if d_addr.get('extra_notes'):
            notes.append(d_addr['extra_notes'])
        return "\n".join(notes)
