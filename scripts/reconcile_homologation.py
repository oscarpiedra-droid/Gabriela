import os
import sys
import json
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv

# Añadir el path raíz para importar módulos locales
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.services.odoo_service_v2 import OdooServiceV2
from app.db.services.homologacion_service import HomologacionService, HomologacionStatus

def reconcile_homologation():
    """
    Script de reconciliación para detectar discrepancias entre el maestro JSON
    de homologación y los datos reales en Odoo.
    """
    load_dotenv()
    
    # 1. Cargar Homologación Local
    homologacion_svc = HomologacionService()
    local_catalog = homologacion_svc._catalog  # dict[odoo_tipo_cliente, entry]
    
    # 2. Conectar a Odoo
    odoo = OdooServiceV2()
    if not odoo.connect():
        logger.error("No se pudo conectar a Odoo. Verifica .env (ODOO_URL, ODOO_DB, etc.)")
        return

    logger.info("--- Iniciando Reconciliación de Homologación de Clientes ---")
    
    try:
        # 3. Obtener "Tipos de Cliente" (Modelo customer.type)
        CustomerType = odoo.env['customer.type']
        odoo_types = CustomerType.search_read([], ['name'])
        odoo_type_names = set(t['name'].strip() for t in odoo_types if t.get('name'))
        
        # 4. Obtener "Categorías (Tags)" (Modelo res.partner.category)
        PartnerCategory = odoo.env['res.partner.category']
        odoo_categories = PartnerCategory.search_read([], ['name'])
        odoo_category_names = set(c['name'].strip() for c in odoo_categories if c.get('name'))

        # Unificar todas las posibilidades de Odoo
        all_odoo_labels = odoo_type_names.union(odoo_category_names)
        
        # 5. Buscar pedidos recientes para ver el impacto real
        SaleOrder = odoo.env['sale.order']
        # Buscamos los últimos 500 pedidos para tener una muestra estadística buena
        recent_orders = SaleOrder.search_read(
            [('state', 'in', ['sale', 'done'])], 
            ['name', 'partner_id', 'partner_type'],  # Nota: el spec dice partner_status o partner_type
            limit=500, 
            order='date_order desc'
        )
        
        # Necesitaremos información extra de los partners (categorías)
        partner_ids = list(set(o['partner_id'][0] for o in recent_orders if o.get('partner_id')))
        partner_data = {}
        if partner_ids:
            Partner = odoo.env['res.partner']
            partners = Partner.search_read([('id', 'in', partner_ids)], ['id', 'category_id'])
            for p in partners:
                # category_id viene como [ (id1, name1), (id2, name2) ]
                partner_data[p['id']] = [cat[1].strip() for cat in p.get('category_id', [])]

        used_in_orders = {} # label -> [order_names]
        orders_without_label = []

        for order in recent_orders:
            order_name = order['name']
            order_labels = []
            
            # a) partner_type (campo primario)
            pt = order.get('partner_type')
            if pt and isinstance(pt, (list, tuple)) and len(pt) >= 2:
                order_labels.append(pt[1].strip())
            
            # b) partner categories (fallback)
            pid = order['partner_id'][0] if order.get('partner_id') else None
            if pid in partner_data:
                order_labels.extend(partner_data[pid])
            
            if not order_labels:
                orders_without_label.append(order_name)
                continue
                
            for label in order_labels:
                if label not in used_in_orders: used_in_orders[label] = []
                # Solo guardar los primeros para el reporte
                if len(used_in_orders[label]) < 10:
                    used_in_orders[label].append(order_name)

        # 6. Cálculo de Inconsistencias
        inconsistencies_odoo_to_json = []  # Presente en Odoo, falta en JSON
        inconsistencies_json_to_odoo = []  # Presente en JSON, falta en Odoo

        # A. Detectar qué falta en el JSON
        for label in sorted(list(all_odoo_labels)):
            if label not in local_catalog:
                usage = used_in_orders.get(label, [])
                inconsistencies_odoo_to_json.append({
                    "label": label,
                    "usage_count": len(usage),
                    "sample_orders": usage[:5]
                })

        # B. Detectar qué falta en Odoo (reglas obsoletas o cambiadas)
        for json_label in sorted(list(local_catalog.keys())):
            if json_label not in all_odoo_labels:
                inconsistencies_json_to_odoo.append({
                    "label": json_label,
                    "status": "Huerfana (No existe en Odoo)"
                })

        # C. Casos de CASE-SENSITIVITY (Muy importante)
        case_sensitivity_issues = []
        odoo_lower = {l.lower(): l for l in all_odoo_labels}
        for json_label in local_catalog.keys():
            if json_label not in all_odoo_labels:
                if json_label.lower() in odoo_lower:
                    case_sensitivity_issues.append({
                        "json": json_label,
                        "odoo": odoo_lower[json_label.lower()],
                        "msg": "Diferencia de mayúsculas/minúsculas — El motor fallará en el match exacto."
                    })

        # 7. Generar resultados finales
        report = {
            "meta": {
                "timestamp": datetime.now().isoformat(),
                "odoo_instance": odoo.url,
                "json_version": "v2026-01"
            },
            "summary": {
                "total_odoo_labels": len(all_odoo_labels),
                "total_json_entries": len(local_catalog),
                "missing_in_json": len(inconsistencies_odoo_to_json),
                "obsolete_in_json": len(inconsistencies_json_to_odoo),
                "case_sensitivity_hazards": len(case_sensitivity_issues),
                "recent_orders_analyzed": len(recent_orders),
                "orders_failing_due_to_no_label": len(orders_without_label)
            },
            "missing_entries_detail": inconsistencies_odoo_to_json,
            "obsolete_entries_detail": inconsistencies_json_to_odoo,
            "case_sensitivity_detail": case_sensitivity_issues,
            "orders_without_label_detail": orders_without_label[:20]
        }

        # Guardar en JSON
        output_file = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "homologation_report.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)

        # Imprimir resumen por consola
        logger.success("--- RECONCILIACIÓN FINALIZADA ---")
        logger.info(f"Reporte generado: {output_file}")
        logger.info(f"Faltan en JSON: {len(inconsistencies_odoo_to_json)} tipos detectados en Odoo.")
        logger.info(f"Entradas obsoletas en JSON: {len(inconsistencies_json_to_odoo)}")
        logger.warning(f"Riesgos de Case-Sensitivity: {len(case_sensitivity_issues)} (IMPORTANTE: El motor es exact match)")
        logger.error(f"Pedidos RECORTADOS (Sin etiqueta alguna): {len(orders_without_label)}")

    except Exception as e:
        logger.exception(f"Error fatal durante la reconciliación: {e}")

if __name__ == "__main__":
    reconcile_homologation()
