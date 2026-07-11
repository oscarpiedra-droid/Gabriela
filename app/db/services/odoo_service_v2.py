"""
OdooServiceV2 - Modern Odoo Integration for Gabriela Rojas.
"""
try:
    import odoorpc
    ODOORPC_AVAILABLE = True
except ImportError:
    ODOORPC_AVAILABLE = False

from datetime import datetime
from typing import List, Dict, Optional
import os
from loguru import logger
import requests

import threading

class OdooServiceV2:
    def __init__(self, url=None, db=None, username=None, password=None):
        self.url = url or os.getenv("ODOO_URL")
        self.db = db or os.getenv("ODOO_DB")
        self.username = username or os.getenv("ODOO_USER")
        self.password = password or os.getenv("ODOO_PASS")
        self.odoo: Optional[odoorpc.ODOO] = None
        self._connected = False
        self._uid = None
        self._session = requests.Session()
        self._lock = threading.RLock()

    def connect(self) -> bool:
        if not ODOORPC_AVAILABLE: return False
        
        with self._lock:
            if self._connected: return True
            
            try:
                url_clean = (self.url or "").strip().rstrip('/')
                if not url_clean:
                    raise ValueError("Odoo URL is not configured.")

                if url_clean.startswith('https://'):
                    host = url_clean.replace('https://', '')
                    protocol = 'jsonrpc+ssl'
                    port = 443
                else:
                    host = url_clean.replace('http://', '')
                    protocol = 'jsonrpc'
                    port = 8069
                
                if ':' in host:
                    host, port_str = host.split(':')
                    port = int(port_str)

                logger.info(f"Odoo Connect: Host={host}, DB={self.db}, User={self.username}")
                self.odoo = odoorpc.ODOO(host, protocol=protocol, port=port, timeout=30)
                self.odoo.login(self.db, self.username, self.password)
                
                # DEFINITIVE FIX: Authenticate the HTTP Session in parallel
                # This bypasses odoorpc's report download limitation for Odoo 16
                auth_url = f"{url_clean}/web/session/authenticate"
                auth_payload = {
                    "jsonrpc": "2.0",
                    "params": {
                        "db": self.db,
                        "login": self.username,
                        "password": self.password
                    }
                }
                try:
                    auth_resp = self._session.post(auth_url, json=auth_payload, timeout=10)
                    if auth_resp.status_code == 200:
                        logger.info("Odoo: HTTP Session authenticated successfully.")
                    else:
                        logger.warning(f"Odoo: HTTP Session auth failed (Status {auth_resp.status_code})")
                except Exception as e:
                    logger.warning(f"Odoo: HTTP Session auth failed with error: {e}")

                self._uid = self.odoo.env.uid
                self._connected = True
                logger.info(f"Odoo Connected Successfully (UID: {self._uid})")
                return True
            except Exception as e:
                logger.error(f"Odoo Connection Error: {e}")
                self._connected = False
                return False

    def _ensure_connected(self, force_reconnect: bool = False):
        """Garantiza que la conexión está activa. Si force_reconnect=True,
        cierra la sesión actual y vuelve a autenticar (usado tras WinError 10053
        u otros errores de socket que abortan la conexión TCP)."""
        if force_reconnect:
            logger.warning("Odoo: forzando reconexión tras error de socket...")
            self._connected = False
            self.odoo = None
        if not self._connected:
            if not self.connect():
                raise RuntimeError("Could not connect to Odoo")

    # ── Errores de socket que justifican un reintento automático ────────────
    _SOCKET_ERRORS = (
        ConnectionAbortedError,   # WinError 10053
        ConnectionResetError,     # WinError 10054
        BrokenPipeError,
        TimeoutError,
        OSError,
    )

    def _call_with_retry(self, fn, *args, max_retries: int = 2, **kwargs):
        """
        Ejecuta fn(*args, **kwargs) con hasta max_retries reconexiones
        automáticas si se producen errores de red/socket.

        Uso típico dentro de un método del servicio::

            recs = self._call_with_retry(
                lambda: self.odoo.env['sale.order'].search_read(domain, fields)
            )
        """
        import urllib.error as _ue
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except (_ue.URLError, *self._SOCKET_ERRORS) as exc:
                last_exc = exc
                logger.warning(
                    f"Odoo socket error (intento {attempt}/{max_retries}): {exc}. "
                    f"Reconectando..."
                )
                try:
                    self._ensure_connected(force_reconnect=True)
                except Exception as reconn_exc:
                    logger.error(f"Odoo: reconexión fallida: {reconn_exc}")
                    raise
        raise last_exc  # type: ignore[misc]

    def sync_pickings(self, picking_type_codes=["outgoing", "internal"], warehouse_prefix="MAD3%", states=['assigned', 'confirmed', 'waiting', 'partially_available', 'draft', 'done', 'cancel']) -> List[Dict]:
        with self._lock:
            self._ensure_connected()
            Picking = self.odoo.env['stock.picking']
            domain = [
                ('picking_type_code', 'in', picking_type_codes),
                ('name', 'ilike', warehouse_prefix),
                ('state', 'in', states)
            ]
            
            recs = Picking.search_read(
                domain, 
                ['name', 'origin', 'partner_id', 'carrier_id', 'state', 'scheduled_date', 'sale_id'],
                limit=300,
                order='scheduled_date desc'
            )

            
            results = []
            for r in recs:
                results.append({
                    'external_id': r['id'],
                    'name': r['name'],
                    'origin': r['origin'] or "",
                    'partner': r['partner_id'][1] if r.get('partner_id') else "",
                    'carrier_name': r['carrier_id'][1] if r.get('carrier_id') else "",
                    'state': r['state'],
                    'date': r['scheduled_date'],
                    'sale_id': r['sale_id'][0] if r.get('sale_id') else None,
                    'sale_name': r['sale_id'][1] if r.get('sale_id') else ""
                })
            return results

    def get_picking_pdf(self, picking_id: int) -> Optional[bytes]:
        """Official reports via authenticated HTTP session (Odoo 16 workaround)."""
        with self._lock:
            self._ensure_connected()
            try:
                url_base = self.url.strip().rstrip('/')
                # We use the authenticated self._session
                pdf_url = f"{url_base}/report/pdf/stock.report_deliveryslip/{picking_id}"
                
                logger.info(f"Odoo: Downloading PDF via HTTP Session: {pdf_url}")
                resp = self._session.get(pdf_url, timeout=20)
                
                if resp.status_code == 200:
                    content = resp.content
                    if content and content.startswith(b'%PDF-'):
                        logger.info(f"Odoo: PDF downloaded successfully ({len(content)} bytes).")
                        return content
                    else:
                        logger.error("Odoo: Received status 200 but content is not a valid PDF.")
                        return None
                else:
                    logger.error(f"Odoo: PDF HTTP download failed with status {resp.status_code}")
                    return None
            except Exception as e:
                logger.error(f"Error downloading Odoo PDF via HTTP: {e}")
                return None

    def send_email_with_odoo(self, res_model, res_id, to_email, cc_emails, subject, body, attachment_name=None, attachment_content=None):
        """Envia email vía Odoo. Devuelve tupla (success: bool, error_msg: str | None)."""
        with self._lock:
            self._ensure_connected()
            try:
                attachments_encoded = []
                if attachment_name and attachment_content:
                    import base64
                    encoded = base64.b64encode(attachment_content).decode('ascii')
                    attachments_encoded.append((attachment_name, encoded))
                
                # 1. Post to chatter for traceability
                try:
                    record = self.odoo.env[res_model].browse(res_id)
                    record.message_post(
                        body=body,
                        subject=subject,
                        message_type='comment',
                        subtype_xmlid='mail.mt_comment',
                    )
                    logger.debug(f"[Odoo] Post to chatter successful for {res_model}:{res_id}")
                except Exception as e:
                    logger.warning(f"[Odoo] Failed to post to chatter for {res_model}:{res_id} (Permission issue?): {e}")
                    # We continue even if chatter fails to ensure the email is sent
                
                # 2. Force external email via mail.mail (more reliable)
                Mail = self.odoo.env['mail.mail']
                mail_vals = {
                    'subject': subject,
                    'body_html': body,
                    'email_to': to_email,
                    'email_cc': cc_emails,
                    'model': res_model,
                    'res_id': res_id,
                    'auto_delete': False,
                }
                
                # Add attachments to mail.mail if any
                if attachments_encoded:
                    Attachment = self.odoo.env['ir.attachment']
                    att_ids = []
                    for name, content in attachments_encoded:
                        attr_id = Attachment.create({
                            'name': name,
                            'datas': content,
                            'res_model': 'mail.mail',
                            'res_id': 0,  # Temporarily 0
                        })
                        att_ids.append(attr_id)
                    mail_vals['attachment_ids'] = [(6, 0, att_ids)]
                
                mail_id = Mail.create(mail_vals)
                Mail.send([mail_id])
                logger.info(f"Odoo email sent OK (mail.id={mail_id}, to={to_email!r})")
                return True, None
            except Exception as e:
                logger.error(f"send_email_with_odoo ERROR: {e}")
                return False, str(e)

    def create_activity(self, res_model, res_id, summary, date_deadline):
        with self._lock:
            self._ensure_connected()
            try:
                Activity = self.odoo.env['mail.activity']
                act_type = self.odoo.env['mail.activity.type'].search([('name', 'ilike', 'To Do')], limit=1)
                
                # Attempt to create activity. This might fail if the user lacks permissions for specific related records
                try:
                    Activity.create({
                        'res_model_id': self.odoo.env['ir.model'].search([('model', '=', res_model)], limit=1)[0],
                        'res_id': res_id,
                        'activity_type_id': act_type[0] if act_type else 1,
                        'summary': summary,
                        'date_deadline': date_deadline,
                        'user_id': self._uid
                    })
                    logger.info(f"[Odoo] Activity created for {res_model}:{res_id} : {summary}")
                except Exception as e:
                    logger.warning(f"[Odoo] Failed to create activity for {res_model}:{res_id} (Permission issue?): {e}")
                    # Non-blocking, return True anyway as the intent was handled
                
                return True
            except Exception as e:
                logger.error(f"Error activity: {e}")
                return False

    def get_salesperson_email(self, picking_id):
        with self._lock:
            self._ensure_connected()
            try:
                pick = self.odoo.env['stock.picking'].browse(picking_id)
                if pick.sale_id and pick.sale_id.user_id:
                    return pick.sale_id.user_id.login
            except: pass
            return ""

    def get_so_name(self, picking_id: int) -> str:
        with self._lock:
            self._ensure_connected()
            try:
                pick = self.odoo.env['stock.picking'].browse(picking_id)
                if pick.sale_id:
                    return pick.sale_id.name
            except: pass
            return ""

    def search_picking_global(self, query: str) -> List[Dict]:
        """Search for pickings across all warehouses by name or SO name."""
        with self._lock:
            self._ensure_connected()
            Picking = self.odoo.env['stock.picking']
            
            # Search by picking name OR origin (SO name)
            domain = [
                '|',
                ('name', 'ilike', query),
                ('origin', 'ilike', query)
            ]
            
            recs = Picking.search_read(
                domain, 
                ['name', 'origin', 'partner_id', 'carrier_id', 'state', 'scheduled_date'],
                limit=10,
                order='scheduled_date desc'
            )
            
            results = []
            for r in recs:
                results.append({
                    'external_id': r['id'],
                    'name': r['name'],
                    'origin': r['origin'] or "",
                    'partner': r['partner_id'][1] if r.get('partner_id') else "",
                    'carrier_name': r['carrier_id'][1] if r.get('carrier_id') else "",
                    'state': r['state'],
                    'date': r['scheduled_date']
                })
            return results

    def unified_search(self, query: str) -> List[Dict]:
        """Search across Pickings, Sales Orders, and Helpdesk Tickets."""
        with self._lock:
            self._ensure_connected()
            results = []
            
            # 1. Search Pickings
            Picking = self.odoo.env['stock.picking']
            p_recs = Picking.search_read(['|', ('name', 'ilike', query), ('origin', 'ilike', query)], ['name', 'origin', 'partner_id', 'state', 'scheduled_date'], limit=5)
            for r in p_recs:
                results.append({
                    'module': 'Logística',
                    'ref': r['name'],
                    'origin': r['origin'] or "",
                    'partner': r['partner_id'][1] if r.get('partner_id') else "",
                    'status': r['state'],
                    'date': r['scheduled_date'],
                    'id': r['id'],
                    'type': 'picking'
                })
            
            # 2. Search Sales Orders
            SO = self.odoo.env['sale.order']
            s_recs = SO.search_read(['|', ('name', 'ilike', query), ('client_order_ref', 'ilike', query)], ['name', 'partner_id', 'state', 'date_order'], limit=5)
            for r in s_recs:
                results.append({
                    'module': 'Comercial',
                    'ref': r['name'],
                    'origin': '',
                    'partner': r['partner_id'][1] if r.get('partner_id') else "",
                    'status': r['state'],
                    'date': r['date_order'],
                    'id': r['id'],
                    'type': 'sale'
                })

            # 3. Search Incidences
            Ticket = self.odoo.env['helpdesk.ticket']
            t_recs = Ticket.search_read(['|', ('name', 'ilike', query), ('number', 'ilike', query)], ['number', 'name', 'stage_id', 'create_date'], limit=5)
            for r in t_recs:
                results.append({
                    'module': 'Incidencias',
                    'ref': r['number'],
                    'origin': r['name'],
                    'partner': '',
                    'status': r['stage_id'][1] if r.get('stage_id') else "",
                    'date': r['create_date'],
                    'id': r['id'],
                    'type': 'ticket'
                })
                
            return results

    def get_extended_picking_data(self, picking_id: int) -> Dict:

        """Fetches full details of a picking for email templates."""
        with self._lock:
            self._ensure_connected()
            Picking = self.odoo.env['stock.picking']
            
            # Read picking data
            p_data = Picking.search_read(
                [('id', '=', picking_id)], 
                ['name', 'partner_id', 'note', 'scheduled_date']
            )
            if not p_data: return {}
            p = p_data[0]
            
            res = {
                'name': p['name'],
                'partner_name': p['partner_id'][1] if p['partner_id'] else "",
                'note': p['note'] or "",
                'scheduled_date': p['scheduled_date'][:10] if p['scheduled_date'] else "", # YYYY-MM-DD
            }
            
            # Get address from partner_id since partner_shipping_id is not guaranteed
            if p['partner_id']:
                ship_id = p['partner_id'][0] # Fallback to principal partner
                Partner = self.odoo.env['res.partner']
                addr = Partner.search_read(
                    [('id', '=', ship_id)], 
                    ['street', 'zip', 'city', 'state_id', 'country_id', 'phone', 'mobile']
                )
                if addr:
                    a = addr[0]
                    res['address'] = f"{a['street'] or ''}, {a['zip'] or ''} {a['city'] or ''} {a['state_id'][1] if a['state_id'] else ''} {a['country_id'][1] if a['country_id'] else ''}".strip()
                    res['phone'] = a['phone'] or a['mobile'] or ""
            
            
            return res

    def get_stock_and_reservations(self, query_sku: str = "", limit: int = 500) -> List[Dict]:
        """Fetch stock and reservation details. Optionally filter by SKU/name."""
        with self._lock:
            self._ensure_connected()
            try:
                # 1. Base domain for quants: internal locations only
                domain = [('location_id.usage', '=', 'internal')]
                if query_sku:
                    domain.append(('product_id.display_name', 'ilike', query_sku))
                else:
                    # If no query, limit to those having positive quantity
                    domain.append(('quantity', '>', 0))
                
                Quant = self.odoo.env['stock.quant']
                quants = Quant.search_read(
                    domain,
                    ['product_id', 'location_id', 'quantity', 'reserved_quantity'],
                    limit=limit,
                    order='quantity desc'
                )
                
                # Fetch weights for products
                product_ids = list(set(q['product_id'][0] for q in quants if q.get('product_id')))
                product_weights = {}
                if product_ids:
                    Product = self.odoo.env['product.product']
                    products = Product.search_read([('id', 'in', product_ids)], ['id', 'weight', 'default_code'])
                    for p in products:
                        product_weights[p['id']] = {
                            'weight': p.get('weight', 0.0),
                            'default_code': p.get('default_code', '')
                        }
                
                results = []
                for q in quants:
                    product = q['product_id'][1] if q.get('product_id') else "Desconocido"
                    product_id = q['product_id'][0] if q.get('product_id') else 0
                    location = q['location_id'][1] if q.get('location_id') else "Desconocida"
                    location_id = q['location_id'][0] if q.get('location_id') else 0
                    qty = q.get('quantity', 0)
                    reserved = q.get('reserved_quantity', 0)
                    available = qty - reserved
                    
                    if qty == 0 and reserved == 0:
                        continue
                        
                    p_info = product_weights.get(product_id, {})
                    weight_per_unit = p_info.get('weight', 0.0)
                    default_code = p_info.get('default_code', '')
                    
                    if default_code:
                        product_name = default_code
                    else:
                        product_name = product # Fallback to [REF] Descriptor
                        
                    results.append({
                        'product': product_name,
                        'product_id': product_id,
                        'location': location,
                        'location_id': location_id,
                        'qty': qty,
                        'available': available,
                        'reserved': reserved,
                        'assigned_orders': "",
                        'weight_per_unit': weight_per_unit,
                        'total_weight': qty * weight_per_unit
                    })
                    
                # 2. Fetch the reserved move lines to get assigned orders
                if results:
                    product_ids = list(set(r['product_id'] for r in results))
                    location_ids = list(set(r['location_id'] for r in results))
                    
                    MoveLine = self.odoo.env['stock.move.line']
                    # Search active reservations in these locations for these products
                    moves = MoveLine.search_read([
                        ('product_id', 'in', product_ids),
                        ('location_id', 'in', location_ids),
                        ('state', 'in', ['assigned', 'partially_available'])
                    ], ['product_id', 'location_id', 'picking_id'])
                    
                    # Create a mapping: (product_id, location_id) -> set of picking names
                    res_map = {}
                    for m in moves:
                        p_id = m['product_id'][0] if m.get('product_id') else None
                        l_id = m['location_id'][0] if m.get('location_id') else None
                        picking = m.get('picking_id')
                        
                        if p_id and l_id and picking:
                            origin = picking[1]  # Picking Name e.g. AB/OUT/0001
                            key = (p_id, l_id)
                            if key not in res_map:
                                res_map[key] = set()
                            res_map[key].add(origin)
                            
                    for r in results:
                        key = (r['product_id'], r['location_id'])
                        if key in res_map:
                            r['assigned_orders'] = ", ".join(sorted(list(res_map[key])))
                            
                return results

            except Exception as e:
                logger.error(f"Error fetching stock reservations: {e}")
                return []

    def get_all_products_master(self, query: str = "") -> List[Dict]:
        """Fetch all active products, their stock per warehouse, and dimensions from an external CSV."""
        with self._lock:
            self._ensure_connected()
            try:
                import pandas as pd
                
                # 1. Fetch products from Odoo
                domain = [('type', 'in', ['product', 'consu'])]
                if query:
                    domain.append('|')
                    domain.append(('name', 'ilike', query))
                    domain.append(('default_code', 'ilike', query))
                    
                Product = self.odoo.env['product.product']
                products = Product.search_read(
                    domain,
                    ['default_code', 'name', 'type', 'uom_id'],
                    limit=1000,
                    order='default_code asc'
                )
                
                # Create a base dict for quick lookup mapping Product ID -> Data
                master_dict = {
                    p['id']: {
                        'id': p['id'],
                        'default_code': p.get('default_code') or '',
                        'name': p.get('name') or '',
                        'uom': p['uom_id'][1] if p.get('uom_id') else '',
                        'stock_abrera': 0.0,
                        'stock_silla': 0.0,
                        'assigned_orders': set(),
                        'ancho_m': '',
                        'largo_m': '',
                        'espesor_mm': '',
                        'peso_kg': ''
                    } for p in products
                }
                
                product_ids = list(master_dict.keys())
                
                if not product_ids:
                    return []
                
                # 2. Fetch stock data (quants) in internal locations
                Quant = self.odoo.env['stock.quant']
                quants = Quant.search_read(
                    [('product_id', 'in', product_ids), ('location_id.usage', '=', 'internal')],
                    ['product_id', 'location_id', 'quantity']
                )
                
                Location = self.odoo.env['stock.location']
                locs = Location.search_read([('usage', '=', 'internal')], ['id', 'name', 'complete_name'])
                loc_map = {l['id']: l['complete_name'].upper() for l in locs}
                
                for q in quants:
                    pid = q['product_id'][0] if q.get('product_id') else None
                    lid = q['location_id'][0] if q.get('location_id') else None
                    qty = q.get('quantity', 0.0)
                    
                    if pid and lid and pid in master_dict:
                        loc_name = loc_map.get(lid, '')
                        if 'ABRERA' in loc_name:
                            master_dict[pid]['stock_abrera'] += qty
                        elif 'SILLA' in loc_name:
                            master_dict[pid]['stock_silla'] += qty
                
                # 3. Fetch reserved moves for these products to find assigned orders
                MoveLine = self.odoo.env['stock.move.line']
                moves = MoveLine.search_read([
                    ('product_id', 'in', product_ids),
                    ('state', 'in', ['assigned', 'partially_available']),
                    ('location_id.usage', '=', 'internal')
                ], ['product_id', 'picking_id'])
                
                for m in moves:
                    pid = m['product_id'][0] if m.get('product_id') else None
                    picking = m.get('picking_id')
                    if pid and picking and pid in master_dict:
                        master_dict[pid]['assigned_orders'].add(picking[1])
                        
                # 4. Fetch the external CSV for dimensions
                try:
                    csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTnOqJY2bxOMvHV9Zs0u1q6fX2I3jybjP2pleeEQozKddAHi43BrVx4H_PqZO7tB4KTbTJVjr5i6K48/pub?gid=487943712&single=true&output=csv"
                    # Skip the first rows to align headers correctly. Looking at the data, row 3 seems to contain headers.
                    df = pd.read_csv(csv_url, skiprows=2) 
                    
                    # Ensure minimal required columns exist
                    cols = df.columns
                    ref_col = 'Referencia interna' if 'Referencia interna' in cols else cols[0]
                    ancho_col = 'Ancho (m)' if 'Ancho (m)' in cols else None
                    largo_col = 'Largo (m)' if 'Largo (m)' in cols else None
                    espesor_col = 'Espesor (mm)' if 'Espesor (mm)' in cols else None
                    peso_col = 'Peso (kgr)' if 'Peso (kgr)' in cols else None
                    
                    
                    # Convert DataFrame to dict mapping string Reference -> dict of dims
                    # Dropping NA references
                    df_valid = df.dropna(subset=[ref_col])
                    
                    # The CSV might have numbers as strings like "11,003", replace comma, stringify
                    csv_data = {}
                    for _, row in df_valid.iterrows():
                        ref = str(row[ref_col]).replace('"', '').strip()
                        # normalize internal ref slightly to match potential odoo formats 
                        # sometimes "11,003" in CSV is "11003" in odoo or vice versa. We keep it as is first.
                        csv_data[ref] = {
                            'ancho': str(row[ancho_col]) if ancho_col and pd.notna(row[ancho_col]) else '',
                            'largo': str(row[largo_col]) if largo_col and pd.notna(row[largo_col]) else '',
                            'espesor': str(row[espesor_col]) if espesor_col and pd.notna(row[espesor_col]) else '',
                            'peso': str(row[peso_col]) if peso_col and pd.notna(row[peso_col]) else ''
                        }
                    
                    # Merge into master_dict
                    for pid, pdata in master_dict.items():
                        odee_ref = pdata['default_code'].strip()
                        # try exact match
                        if odee_ref in csv_data:
                            match = csv_data[odee_ref]
                        else:
                            # try adding a comma if it's 5 digits long like 11003 -> 11,003
                            alt_ref = f"{odee_ref[:2]},{odee_ref[2:]}" if len(odee_ref) == 5 and odee_ref.isdigit() else ""
                            if alt_ref in csv_data:
                                match = csv_data[alt_ref]
                            else:
                                match = None
                                
                        if match:
                            pdata['ancho_m'] = match['ancho']
                            pdata['largo_m'] = match['largo']
                            pdata['espesor_mm'] = match['espesor']
                            pdata['peso_kg'] = match['peso']
                            
                            
                except Exception as csv_ex:
                    logger.error(f"Error fetching external CSV for dimensions: {csv_ex}")
                
                # 5. Format outputs
                results = []
                for pdata in master_dict.values():
                    # Format assigned orders as comma separated string
                    orders_str = ", ".join(sorted(list(pdata['assigned_orders'])))
                    pdata['assigned_orders'] = orders_str
                    results.append(pdata)
                    
                # Sort by default_code
                results.sort(key=lambda x: x['default_code'])
                return results

            except Exception as e:
                logger.error(f"Error fetching master products list: {e}")
                return []

    def get_orders_with_articles(self, query: str = "") -> List[Dict]:
        """Fetch pending orders, their articles, and the available stock in Abrera, Silla, and Pinto."""
        with self._lock:
            self._ensure_connected()
            try:
                # 1. Fetch pending outbound pickings
                domain = [
                    ('picking_type_id.code', '=', 'outgoing'),
                    ('state', 'in', ['confirmed', 'partially_available', 'assigned'])
                ]
                if query:
                    domain.append('|')
                    domain.append(('name', 'ilike', query))
                    domain.append(('origin', 'ilike', query))
                    
                Picking = self.odoo.env['stock.picking']
                pickings = Picking.search_read(
                    domain,
                    ['name', 'origin', 'carrier_id'],
                    limit=500,
                    order='scheduled_date desc'
                )
                
                if not pickings:
                    return []
                    
                picking_ids = [p['id'] for p in pickings]
                
                # 2. Fetch stock moves (lines) for these pickings
                Move = self.odoo.env['stock.move']
                moves = Move.search_read(
                    [('picking_id', 'in', picking_ids)],
                    ['picking_id', 'product_id', 'product_uom_qty']
                )
                
                # Organize products per picking
                picking_products = {}
                product_ids = set()
                for m in moves:
                    pid = m['picking_id'][0] if m.get('picking_id') else None
                    prod = m['product_id'] if m.get('product_id') else None
                    if pid and prod:
                        qty = m.get('product_uom_qty', 0)
                        if pid not in picking_products:
                            picking_products[pid] = []
                        picking_products[pid].append((prod[0], prod[1], qty))
                        product_ids.add(prod[0])
                        
                if not product_ids:
                    return []
                    
                # 3. Fetch stock levels for these products in internal locations
                Quant = self.odoo.env['stock.quant']
                quants = Quant.search_read(
                    [('product_id', 'in', list(product_ids)), ('location_id.usage', '=', 'internal')],
                    ['product_id', 'location_id', 'quantity']
                )
                
                Location = self.odoo.env['stock.location']
                locs = Location.search_read([('usage', '=', 'internal')], ['id', 'complete_name'])
                loc_map = {l['id']: l['complete_name'].upper() for l in locs}
                
                # Precompute product stock per location
                prod_stock = {p: {'Abrera': 0.0, 'Silla': 0.0, 'Pinto': 0.0} for p in product_ids}
                for q in quants:
                    p = q['product_id'][0] if q.get('product_id') else None
                    l = q['location_id'][0] if q.get('location_id') else None
                    qty = q.get('quantity', 0.0)
                    if p and l and p in prod_stock:
                        lname = loc_map.get(l, '')
                        if 'ABRERA' in lname:
                            prod_stock[p]['Abrera'] += qty
                        elif 'SILLA' in lname:
                            prod_stock[p]['Silla'] += qty
                        elif 'MAD3' in lname or 'PINTO' in lname or 'MADRID' in lname:
                            prod_stock[p]['Pinto'] += qty

                # 4. Fetch additional product dimensions and weight from CSV
                import pandas as pd
                product_props = {}
                try:
                    df = pd.read_csv('https://docs.google.com/spreadsheets/d/e/2PACX-1vTnOqJY2bxOMvHV9Zs0u1q6fX2I3jybjP2pleeEQozKddAHi43BrVx4H_PqZO7tB4KTbTJVjr5i6K48/pub?gid=487943712&single=true&output=csv', skiprows=2)
                    for index, row in df.iterrows():
                        ref = str(row.get('Referencia interna', '')).strip()
                        if pd.isna(row.get('Referencia interna')):
                            continue
                        product_props[ref] = {
                            'uom': str(row.get('Unidad de Medida de Venta', '')),
                            'pallet_qty': str(row.get('Unidades incluidas', '')),
                            'width': str(row.get('Ancho (m)', '')),
                            'length': str(row.get('Largo (m)', '')),
                            'thickness': str(row.get('Espesor (mm)', '')),
                            'weight': row.get('Peso (kgr)', 0.0)
                        }
                except Exception as e:
                    logger.error(f"Error fetching CSV product properties: {e}")

                # 5. Build final result list
                results = []
                for p in pickings:
                    pid = p['id']
                    prods = picking_products.get(pid, [])
                    if not prods:
                        continue
                        
                    name = p['name']
                    if p.get('origin'):
                        name = f"{name} ({p['origin']})"
                        
                    carrier = p['carrier_id'][1] if p.get('carrier_id') else ""
                    
                    arts_str = []
                    uom_str = []
                    pallet_qty_str = []
                    dim_str = []
                    peso_str = []
                    abrera_str = []
                    silla_str = []
                    pinto_str = []
                    
                    for prod_id, prod_name, qty in prods:
                        # e.g., "[CODE] Name"
                        code = prod_name.split(']')[0].replace('[', '') if '[' in prod_name else prod_name
                        code = code.strip()
                        arts_str.append(f"{code} (x{qty})")
                        
                        abrera_qty = prod_stock[prod_id]['Abrera']
                        silla_qty = prod_stock[prod_id]['Silla']
                        pinto_qty = prod_stock[prod_id]['Pinto']
                        
                        abrera_str.append(f"{abrera_qty}")
                        silla_str.append(f"{silla_qty}")
                        pinto_str.append(f"{pinto_qty}")
                        
                        # Product properties
                        props = product_props.get(code, {})
                        
                        uom = props.get('uom', '-')
                        if pd.isna(uom) or uom == 'nan': uom = '-'
                        uom_str.append(str(uom))
                        
                        p_qty = props.get('pallet_qty', '-')
                        if pd.isna(p_qty) or p_qty == 'nan': p_qty = '-'
                        pallet_qty_str.append(str(p_qty))
                        
                        w = props.get('width', '-')
                        l = props.get('length', '-')
                        t = props.get('thickness', '-')
                        if pd.isna(w) or w == 'nan': w = '-'
                        if pd.isna(l) or l == 'nan': l = '-'
                        if pd.isna(t) or t == 'nan': t = '-'
                        dim = f"{w}m x {l}m x {t}mm" if w != '-' and l != '-' and t != '-' else "-"
                        dim_str.append(dim)
                        
                        weight = props.get('weight', 0.0)
                        if pd.isna(weight): weight = 0.0
                        total_stock = abrera_qty + silla_qty + pinto_qty
                        total_weight = float(weight) * total_stock
                        peso_str.append(f"{total_weight:.2f}")
                        
                    results.append({
                        'picking_id': pid,
                        'pedido': name,
                        'ruta': carrier,
                        'articulos': "\n".join(arts_str),
                        'uom': "\n".join(uom_str),
                        'pallet_qty': "\n".join(pallet_qty_str),
                        'dimensiones': "\n".join(dim_str),
                        'peso_stock': "\n".join(peso_str),
                        'abrera': "\n".join(abrera_str),
                        'silla': "\n".join(silla_str),
                        'pinto': "\n".join(pinto_str),
                        '_raw_prods': prods  # for totals
                    })
                    
                return results

            except Exception as e:
                logger.error(f"Error fetching orders with stock: {e}")
                import traceback
                traceback.print_exc()
                return []

    def get_so_id(self, name: str) -> Optional[int]:
        """Returns the Odoo database ID of a Sales Order by its name."""
        with self._lock:
            self._ensure_connected()
            try:
                SO = self.odoo.env['sale.order']
                ids = SO.search([('name', '=', name)], limit=1)
                return ids[0] if ids else None
            except Exception as e:
                logger.error(f"Error get_so_id {name}: {e}")
                return None

    def get_incidences_by_so(self, so_name: str) -> List[Dict]:
        """Returns a list of helpdesk tickets related to a Sales Order name."""
        with self._lock:
            self._ensure_connected()
            try:
                Ticket = self.odoo.env['helpdesk.ticket']
                # Search by SO name in ticket name or description
                recs = Ticket.search_read(
                    ['|', ('name', 'ilike', so_name), ('description', 'ilike', so_name)],
                    ['number', 'name', 'stage_id', 'create_date'],
                    limit=20
                )
                results = []
                for r in recs:
                    results.append({
                        'number': r['number'],
                        'name': r['name'],
                        'status': r['stage_id'][1] if r.get('stage_id') else "",
                        'date': r['create_date']
                    })
                return results
            except Exception as e:
                logger.error(f"Error get_incidences_by_so {so_name}: {e}")
                return []
