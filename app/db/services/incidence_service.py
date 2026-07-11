from typing import List, Dict, Optional
from loguru import logger
import os

class IncidenceService:
    def __init__(self, odoo_service):
        self.odoo = odoo_service
        # Mappings based on existing Odoo IDs from previous inspection
        # Official Team Mappings based on type
        self.TEAM_MAP = {
            'faltante': 2,        # Logística
            'presentacion': 2,    # Logística
            'daño': 2,            # Logística / Transporte
            'direccion': 3,       # Comercial / Datos maestro
            'producto_no_f': 4,    # Calidad / Producción
            'material_roto': 4    # Calidad / Logística-Transporte
        }
        # Official Stages
        self.STAGE_MAP = {
            'nuevo': 1,            # Nuevo
            'analisis': 2,         # En progreso
            'accion': 2,           # En progreso
            'pendiente': 3,        # En espera
            'resuelto': 4,         # Hecho
            'cerrado': 4           # Hecho
        }


    def get_ticket_by_so(self, so_name: str) -> Optional[Dict]:
        """Check if an incidence already exists for a Sale Order."""
        with self.odoo._lock:
            self.odoo._ensure_connected()
            Ticket = self.odoo.odoo.env['helpdesk.ticket']
            # Search for tickets linked to this SO name or ID
            SO = self.odoo.odoo.env['sale.order']
            so_ids = SO.search([('name', '=', so_name)], limit=1)
            if not so_ids:
                return None
            
            so_id = so_ids[0]
            results = Ticket.search_read([('x_sale_order_id', '=', so_id)], ['name', 'stage_id', 'number'])
            return results[0] if results else None

    def create_incidence(self, vals: Dict) -> Optional[int]:
        """Create a new ticket with activities and attachments."""
        with self.odoo._lock:
            self.odoo._ensure_connected()
            try:
                # Get SO ID — optional: internal movements may not have a linked SO in Odoo.
                # If no matching sale.order is found, the ticket is still created without it.
                so_id: int | bool = False
                so_name = vals.get('so_name', '').strip()
                if so_name:
                    SO = self.odoo.odoo.env['sale.order']
                    so_ids = SO.search([('name', '=', so_name)], limit=1)
                    if so_ids:
                        so_id = so_ids[0]
                    else:
                        logger.warning(
                            f"[IncidenceService] SO '{so_name}' no encontrado en Odoo. "
                            "El ticket se creará sin x_sale_order_id vinculado."
                        )
                team_id = self.TEAM_MAP.get(vals['type'], 3)
                if vals.get('sub_type') == 'transporte': team_id = 2
                
                odoo_vals: dict = {
                    'name': vals['summary'],
                    'description': f"Almacén: {vals.get('warehouse', 'Desconocido')}\n\n{vals['description']}",
                    'team_id': team_id,
                    'priority': vals['priority'],
                    'x_picking_id': vals['picking_id'],
                    'x_units_affected': vals.get('units', 0),
                    'stage_id': self.STAGE_MAP['nuevo']
                }
                # Only link the SO when we actually found one in Odoo
                if so_id:
                    odoo_vals['x_sale_order_id'] = so_id
                
                # Use context to suppress automatic notifications
                Ticket = self.odoo.odoo.env['helpdesk.ticket'].with_context(
                    mail_notrack=True, 
                    mail_create_nosummary=True, 
                    tracking_disable=True
                )
                ticket_id = Ticket.create(odoo_vals)
                
                # Add attachments if any
                if vals.get('attachments'):
                    Attachment = self.odoo.odoo.env['ir.attachment']
                    import base64
                    for name, content in vals['attachments']:
                        Attachment.create({
                            'name': name,
                            'datas': base64.b64encode(content).decode('ascii'),
                            'res_model': 'helpdesk.ticket',
                            'res_id': ticket_id
                        })
                
                # AUTOMATIC ACTIVITIES
                activity_msg = "Revisar información de incidencia"
                if vals['type'] in ['faltante', 'presentacion']: activity_msg = "Analizar stock y picking"
                elif vals['type'] == 'daño': activity_msg = "Reclamar a transportista / Revisar fotos"
                elif vals['type'] in ['producto_no_f', 'material_roto']: activity_msg = "Inspección técnica de producto"
                
                from datetime import datetime, timedelta
                deadline = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
                
                try:
                    self.odoo.create_activity(
                        res_model='helpdesk.ticket',
                        res_id=ticket_id,
                        summary=activity_msg,
                        date_deadline=deadline
                    )
                except: pass

                return ticket_id
                
            except Exception as e:
                logger.error(f"Error creating incidence: {e}")
                return None

    def resolve_incidence(self, ticket_id: int, vals: Dict) -> bool:
        """
        Close an incidence enforcing mandatory fields.
        vals: {'root_cause': str, 'final_action': str, 'conform': bool}
        """
        # IMPORTANT: Use the same lock as other methods to prevent race conditions.
        # Without this lock, a concurrent thread could read the ticket state before
        # the write completes and then revert it back to "open" (the reported bug).
        with self.odoo._lock:
            self.odoo._ensure_connected()
            try:
                odoo_vals = {
                    'x_root_cause': vals['root_cause'],
                    'x_final_action': vals['final_action'],
                    'x_client_conform': vals['conform'],
                    'stage_id': self.STAGE_MAP['cerrado']
                }
                # Use context to suppress automatic notifications
                Ticket = self.odoo.odoo.env['helpdesk.ticket'].with_context(
                    mail_notrack=True,
                    tracking_disable=True
                )
                Ticket.write([ticket_id], odoo_vals)
                logger.info(f"[IncidenceService] Ticket {ticket_id} cerrado correctamente.")
                return True
            except Exception as e:
                logger.error(f"Error resolving incidence: {e}")
                return False

    def assign_incidence(self, ticket_id: int, role_name: str) -> bool:
        """Assigns a ticket to a user or team based on role name."""
        try:
            self.odoo._ensure_connected()
            Ticket = self.odoo.odoo.env['helpdesk.ticket']
            
            # Assignment Mapping Logic
            # IDs based on debug analysis
            vals = {}
            r = role_name.lower()
            
            if "gabriela" in r:
                vals = {'user_id': 69, 'team_id': 1} # Gabriela + Admin
            elif "administración" in r:
                vals = {'user_id': False, 'team_id': 1} # Admin Team
            elif "logística" in r:
                vals = {'user_id': False, 'team_id': 2} # Logística Team
            elif "calidad" in r:
                # Default to Admin if specific Quality team doesn't exist
                vals = {'user_id': False, 'team_id': 1}
            elif "comercial" in r:
                vals = {'user_id': False, 'team_id': 3} # Customer Service Team
            
            if vals:
                # Use context to suppress automatic notifications
                Ticket = self.odoo.odoo.env['helpdesk.ticket'].with_context(
                    mail_notrack=True,
                    tracking_disable=True
                )
                Ticket.write([ticket_id], vals)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error assigning incidence: {e}")
            return False


    def get_active_incidences(self) -> List[Dict]:
        """Fetch all active tickets."""
        logger.info("Incidences: Starting get_active_incidences...")
        with self.odoo._lock:
            self.odoo._ensure_connected()
            Ticket = self.odoo.odoo.env['helpdesk.ticket']
            # Fetch all tickets to allow UI filtering (including closed)
            domain = [] 
            logger.info("Incidences: Querying helpdesk.ticket...")
            recs = Ticket.search_read(domain, [
                'name', 'number', 'user_id', 'team_id', 'stage_id', 
                'priority', 'x_sale_order_id', 'x_picking_id', 'create_date',
                'description'
            ])
        
        results = []
        logger.info(f"Incidences: Found {len(recs)} tickets. Processing meta-data...")
        
        # Batch fetch SO data for these tickets
        so_ids = [r['x_sale_order_id'][0] for r in recs if r.get('x_sale_order_id')]
        so_data_map = {}
        if so_ids:
            SO = self.odoo.odoo.env['sale.order']
            # Fetch 'state_order_id' (Estado de pedido), 'transporter_id' and 'warehouse_id'
            so_recs = SO.search_read(
                [('id', 'in', so_ids)], 
                ['state_order_id', 'transporter_id', 'warehouse_id']
            )
            so_data_map = {s['id']: s for s in so_recs}

        for r in recs:
            # Reliability order: Field in description > Linked Picking Name
            warehouse = "Pinto" # Default
            if r.get('description') and "Almac\u00e9n:" in r['description']:
                try:
                    line = [l for l in r['description'].split('\n') if "Almac\u00e9n:" in l][0]
                    found_wh = line.replace("Almac\u00e9n:", "").strip()
                    if found_wh: warehouse = found_wh
                except: pass
            
            # Priority 2: SO Warehouse field
            so_id = r['x_sale_order_id'][0] if r.get('x_sale_order_id') else None
            so_info = so_data_map.get(so_id, {})
            if not warehouse or warehouse == "Pinto":
                so_wh = so_info.get('warehouse_id', [0, ""])[1]
                if so_wh:
                    # Map common names
                    if "abrer" in so_wh.lower(): warehouse = "Abrera"
                    elif "silla" in so_wh.lower() or "valenc" in so_wh.lower(): warehouse = "Valencia"
                    elif "barcel" in so_wh.lower(): warehouse = "Barcelona"
                    elif "gav" in so_wh.lower(): warehouse = "Gavà"
                    elif "madrid" in so_wh.lower() and "deleg" in so_wh.lower(): warehouse = "Delegación Madrid"
                    elif "pinto" in so_wh.lower(): warehouse = "Pinto"

            # Priority 3: Picking Prefixes
            if (not warehouse or warehouse == "Pinto") and r.get('x_picking_id'):
                p_name = r['x_picking_id'][1].upper()
                if "VAL" in p_name: warehouse = "Valencia"
                elif "BCN" in p_name: warehouse = "Barcelona"
                elif "AB" in p_name: warehouse = "Abrera"
                elif "GAV" in p_name: warehouse = "Gavà"
                elif "MAD2" in p_name: warehouse = "Delegación Madrid"
                elif "MAD3" in p_name: warehouse = "Pinto"
            
            # Priority 4: Regex/Keyword match in summary (name)
            if (not warehouse or warehouse == "Pinto") and r.get('name'):
                name_u = r['name'].upper()
                if "ABR1" in name_u or "ABRERA" in name_u: warehouse = "Abrera"
                elif "VAL1" in name_u or "VALENCIA" in name_u: warehouse = "Valencia"
                elif "BCN1" in name_u or "BARCELONA" in name_u: warehouse = "Barcelona"
                elif "GAV1" in name_u or "GAVA" in name_u: warehouse = "Gavà"

            
            # Extract SO related data
            so_id = r['x_sale_order_id'][0] if r.get('x_sale_order_id') else None
            so_info = so_data_map.get(so_id, {})
            
            results.append({
                'id': r['id'],
                'number': r['number'],
                'name': r['name'],
                'user': r['user_id'][1] if r['user_id'] else "Sin asignar",
                'team': r['team_id'][1] if r['team_id'] else "Sin equipo",
                'team_id': r['team_id'][0] if r.get('team_id') else 0, # Added for filtering
                'stage': r['stage_id'][1] if r['stage_id'] else "",
                'stage_id': r['stage_id'][0] if r.get('stage_id') else 0, # Added for filtering
                'priority': r['priority'],
                'so': r['x_sale_order_id'][1] if r['x_sale_order_id'] else "",
                'so_status': so_info.get('state_order_id', [0, ""])[1], # Added for "Pedido Emitido"
                'transporter': so_info.get('transporter_id', [0, ""])[1], # Added for transport filter
                'warehouse': warehouse,
                'date': r['create_date']
            })

        logger.info(f"Incidences: get_active_incidences complete with {len(results)} results.")
        return results

    def get_ticket_messages(self, ticket_id: int) -> List[Dict]:
        """Fetch communication history (chatter) for a ticket."""
        self.odoo._ensure_connected()
        try:
            Message = self.odoo.odoo.env['mail.message']
            domain = [('res_id', '=', ticket_id), ('model', '=', 'helpdesk.ticket')]
            recs = Message.search_read(domain, ['body', 'author_id', 'date', 'message_type'], order='date desc')
            
            import re
            msgs = []
            for r in recs:
                # Basic HTML cleaning for the body
                body = re.sub('<[^<]+?>', '', r['body']) if r['body'] else ""
                msgs.append({
                    'author': r['author_id'][1] if r['author_id'] else "Sistema",
                    'body': body.strip(),
                    'date': str(r['date']),
                    'type': r['message_type']
                })
            return msgs
        except Exception as e:
            logger.error(f"Error fetching ticket messages: {e}")
            return []

    def post_ticket_message(self, ticket_id: int, body: str) -> bool:
        """Post a new message to the ticket chatter."""
        self.odoo._ensure_connected()
        try:
            Ticket = self.odoo.odoo.env['helpdesk.ticket'].with_context(
                mail_notrack=True,
                tracking_disable=True
            )
            Ticket.message_post(ticket_id, body=body, message_type='comment', subtype_xmlid='mail.mt_comment')
            return True
        except Exception as e:
            logger.error(f"Error posting message to ticket: {e}")
            return False

    def get_incidence_stats(self) -> Dict:
        """
        Fetch aggregated statistics for the dashboard (BUG-006 fix).
        NOTA: No se filtran por stage_id con IDs hardcodeados porque los IDs reales
        del entorno Odoo pueden diferir. Se usa dominio abierto igual que
        get_active_incidences, que sí devuelve resultados correctos según los logs.
        """
        try:
            with self.odoo._lock:
                self.odoo._ensure_connected()
                Ticket = self.odoo.odoo.env['helpdesk.ticket']
                # Dominio abierto — misma estrategia que get_active_incidences
                recs = Ticket.search_read(
                    [],
                    ['name', 'x_picking_id', 'stage_id', 'description']
                )

            stats = {
                'by_warehouse': {},
                'by_stage': {},
                'total': len(recs)
            }

            for r in recs:
                # ── Almacén: misma lógica de prioridades que get_active_incidences ──
                wh = 'Otros'

                # P1: descripción "Almacén: X"
                if r.get('description') and 'Almac\u00e9n:' in r['description']:
                    try:
                        line = [l for l in r['description'].split('\n') if 'Almac\u00e9n:' in l][0]
                        found = line.replace('Almac\u00e9n:', '').strip()
                        if found:
                            wh = found
                    except Exception:
                        pass

                # P2: prefijo del albarán
                if wh == 'Otros' and r.get('x_picking_id'):
                    p_name = r['x_picking_id'][1].upper()
                    if 'MAD' in p_name or 'PIN' in p_name:
                        wh = 'Pinto'
                    elif 'VAL' in p_name:
                        wh = 'Valencia'
                    elif 'BCN' in p_name or 'BAR' in p_name:
                        wh = 'Barcelona'
                    elif 'AB' in p_name:
                        wh = 'Abrera'
                    elif 'GAV' in p_name:
                        wh = 'Gavà'

                # P3: keyword en el título del ticket
                if wh == 'Otros' and r.get('name'):
                    n = r['name'].upper()
                    if 'ABRERA' in n or 'ABR1' in n:
                        wh = 'Abrera'
                    elif 'VALENC' in n or 'VAL1' in n:
                        wh = 'Valencia'
                    elif 'BARCELONA' in n or 'BCN1' in n:
                        wh = 'Barcelona'
                    elif 'PINTO' in n or 'MAD3' in n:
                        wh = 'Pinto'

                stats['by_warehouse'][wh] = stats['by_warehouse'].get(wh, 0) + 1

                # Etapa
                stage = r['stage_id'][1] if r.get('stage_id') else 'Desconocido'
                stats['by_stage'][stage] = stats['by_stage'].get(stage, 0) + 1

            return stats
        except Exception as e:
            logger.error(f"Error fetching incidence stats: {e}")
            return {}


