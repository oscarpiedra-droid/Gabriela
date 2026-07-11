from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

class LogisticsService:
    WAREHOUSES = {
        "Pinto": "MAD3%",
        "Gavà": "GAV1%",
        "Delegación Madrid": "MAD2%",
        "Valencia": "VA%",
        "Barcelona": "BCN%",
        "Abrera": "AB%"
    }

    
    ALOBERA_BILDUTRUCK_EMAIL = "alobera@bildutruck.es"
    
    def __init__(self, odoo_service):
        self.odoo = odoo_service

    def get_pickings(self, warehouse_prefix):
        logger.info(f"Logistics: Starting get_pickings for {warehouse_prefix}...")
        pickings = self.odoo.sync_pickings(warehouse_prefix=warehouse_prefix)
        if not pickings: 
            logger.info("Logistics: No pickings found.")
            return []

        logger.info(f"Logistics: Found {len(pickings)} pickings. Batch fetching SO data...")
        # Batch fetch incidences to avoid N+1 queries in UI thread
        so_ids = [p['sale_id'] for p in pickings if p['sale_id']]
        if so_ids:
            from db.services.commercial_service import CommercialService
            comm_service = CommercialService(self.odoo)
            
            # Fetch Incidences
            logger.info("Logistics: Fetching incidences for SO list...")
            with self.odoo._lock:
                Ticket = self.odoo.odoo.env['helpdesk.ticket']
                tickets = Ticket.search_read([('x_sale_order_id', 'in', so_ids)], ['x_sale_order_id', 'stage_id', 'number'])
            
            ticket_map = {t['x_sale_order_id'][0]: t for t in tickets}
            logger.info(f"Logistics: Found {len(tickets)} tickets. Applying compliance checks...")
            
            for p in pickings:
                sid = p['sale_id']
                p['incidence'] = ticket_map.get(sid) if sid else None
                p['compliance'] = 'PENDING' # Placeholder to avoid slow sequential calls
        
        logger.info(f"Logistics: Processing complete for {len(pickings)} pickings.")
        return pickings

    def prepare_email_data(self, picking):
        picking_id = picking['external_id']
        picking_name = picking['name']
        salesperson_email = self.odoo.get_salesperson_email(picking_id)
        
        # Fetch detailed data for templates
        ext = self.odoo.get_extended_picking_data(picking_id)
        
        subject_prefix = "Albarán de Salida"
        carrier_name = picking.get('carrier_name', '').lower()
        is_recoge = "recoge" in carrier_name or "cliente" in carrier_name
        
        if is_recoge:
            subject = f"RECOGE CLIENTE: {picking_name} - {ext.get('partner_name', '')}"
        else:
            subject = f"Envío Logística: {picking_name} - {ext.get('partner_name', '')}"

        body = self.get_email_body(ext, is_recoge)
        
        return {
            'picking_id': picking_id,
            'picking_name': picking_name,
            'to': self.ALOBERA_BILDUTRUCK_EMAIL if "MAD3" in picking_name else "",
            'cc': salesperson_email or "",
            'subject': subject,
            'body': body,
            'is_recoge': is_recoge,
            'ext_data': ext # Store details for re-generation in UI
        }

    def get_email_body(self, ext_data, is_recoge):
        """Generates the HTML body based on the variant."""
        picking_name = ext_data.get('name', '')
        partner_name = ext_data.get('partner_name', '')
        date = ext_data.get('scheduled_date', '')
        address = ext_data.get('address', 'Dirección no disponible')
        phone = ext_data.get('phone', 'No disponible')
        note = ext_data.get('note', '')
        
        body = f"""
        <p>Buenos días,</p>
        <p>Adjunto el albarán <b>{picking_name}</b> del cliente <b>{partner_name}</b>.</p>
        """
        
        if is_recoge:
            body += f"<p>Este albarán es un <b>RECOGE CLIENTE</b>.</p>"
        else:
            body += f"""
            <p>Para ser enviado EL <b>{date}</b> a la siguiente dirección:</p>
            <p style='margin-left: 20px;'>{address}</p>
            <p><b>Teléfono:</b> {phone}</p>
            """
            
        if note:
            # Format notes with line breaks
            note_html = note.replace('\n', '<br>')
            body += f"<p><b>Nota:</b><br/>{note_html}</p>"
            
        body += f"""
        <p>Una vez que se haya entregado el material, os agradeceríamos que nos remitan el albarán debidamente firmado.</p>
        <p>Saludos.</p>
        """
        return body


    def execute_workflow(self, picking_id, to_email, cc_emails, subject, body, is_recoge):
        logger.info(f"[Logistics] execute_workflow → picking_id={picking_id}, to={to_email!r}")
        
        # 1. Descargar PDF
        pdf_content = self.odoo.get_picking_pdf(picking_id)
        if not pdf_content:
            logger.error(f"[Logistics] Fallo al descargar PDF del albarán {picking_id}. Comprueba la sesión HTTP de Odoo.")
            return False, "No se pudo descargar el PDF desde Odoo. La sesión puede haber expirado."
        
        logger.info(f"[Logistics] PDF descargado correctamente ({len(pdf_content)} bytes). Enviando email...")
        
        # 2. Enviar email vía Odoo
        success, error_msg = self.odoo.send_email_with_odoo(
            res_model='stock.picking', res_id=picking_id,
            to_email=to_email, cc_emails=cc_emails,
            subject=subject, body=body,
            attachment_name=f"Albaran_{picking_id}.pdf",
            attachment_content=pdf_content
        )
        
        if success:
            logger.info(f"[Logistics] Email enviado correctamente para picking {picking_id}.")
            today = datetime.now()
            if is_recoge:
                self.odoo.create_activity('stock.picking', picking_id, "Recibir albarán firmado", (today + timedelta(days=5)).strftime("%Y-%m-%d"))
            else:
                self.odoo.create_activity('stock.picking', picking_id, "Confirmar carga", (today + timedelta(days=1)).strftime("%Y-%m-%d"))
                self.odoo.create_activity('stock.picking', picking_id, "Recibir albarán firmado", (today + timedelta(days=5)).strftime("%Y-%m-%d"))
            return True, None
        
        logger.error(f"[Logistics] Fallo al enviar email para picking {picking_id}: {error_msg}")
        return False, error_msg

    def open_picking_pdf(self, picking_id, picking_name):
        """Fetches PDF from Odoo and saves it locally, returning the path."""
        pdf_content = self.odoo.get_picking_pdf(picking_id)
        if not pdf_content:
            return False, "No se pudo obtener el PDF de Odoo."
            
        try:
            # Ensure exports directory exists in the absolute root
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            export_dir = os.path.join(root_dir, "exports")
            os.makedirs(export_dir, exist_ok=True)
            
            import time
            timestamp = int(time.time())
            clean_name = picking_name.replace("/", "_")
            filepath = os.path.normpath(os.path.join(export_dir, f"{clean_name}_{timestamp}.pdf"))
            
            with open(filepath, "wb") as f:
                f.write(pdf_content)
                f.flush()
                os.fsync(f.fileno())
            
            if not os.path.exists(filepath):
                return False, f"El archivo no se pudo crear en: {filepath}"
                
            return True, filepath
        except Exception as e:
            logger.error(f"Error saving PDF: {e}")
            return False, f"Error al guardar: {str(e)}"
