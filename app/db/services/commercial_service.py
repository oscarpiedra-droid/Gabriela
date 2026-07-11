from typing import List, Dict
from loguru import logger
import db.commercial_rules as rules
from db.services.commercial_conditions_service import DiscountProposalService
from db.services.homologacion_service import HomologacionService, HomologacionStatus

# ── CAPA DE HOMOLOGACIÓN ─────────────────────────────────────────────────────
# El motor de validación NUNCA usa comparación textual libre ni slug-matching.
# Toda resolución de segmento pasa por el catálogo maestro homologacion_clientes.json
# mediante búsqueda EXACTA (case-sensitive).
# Referencia: spec v2026-01 §3 "Regla maestra del motor de validación".
_homologacion_svc = HomologacionService()

# Tipos de uso que admiten tabla estándar de descuentos
_USO_TARIFABLE = {"ESTÁNDAR", "SOUND"}



class CommercialService:
    _problematic_sos = set() # Cache SOs that trigger Odoo server errors

    def __init__(self, odoo_service):
        self.odoo = odoo_service
        self.discount_proposal = DiscountProposalService()

    def get_pending_orders(self) -> List[Dict]:
        """Fetch confirmed Sale Orders with related Incidences."""
        logger.info("Commercial: Starting get_pending_orders...")
        with self.odoo._lock:
            self.odoo._ensure_connected()
            SO = self.odoo.odoo.env['sale.order']
            # Fetch strictly 'Pedido Emitido' (state_order_id ilike 'Pedido Emitido') to avoid Offers
            domain = [('state_order_id.name', 'ilike', 'Pedido Emitido')]
            
            logger.info("Commercial: Querying sale.order...")
            recs = self.odoo._call_with_retry(
                lambda: SO.search_read(
                    domain,
                    ['name', 'partner_id', 'amount_untaxed', 'date_order', 'user_id', 'state', 'state_order_id', 'carrier_id'],
                    limit=200,
                    order='date_order desc'
                )
            )
            
            logger.info(f"Commercial: Found {len(recs)} orders raw. Filtering 'Recoge Cliente'...")
            # Excluir pedidos "Recoge Cliente" — no aplica validación de portes ni descuentos
            def _es_recoge_cliente(rec):
                carrier = rec.get('carrier_id')
                if not carrier:
                    return False
                cname = carrier[1].lower() if isinstance(carrier, (list, tuple)) and len(carrier) > 1 else ""
                return 'recoge' in cname and 'cliente' in cname

            recs_validos = [r for r in recs if not _es_recoge_cliente(r)]
            skipped = len(recs) - len(recs_validos)
            if skipped:
                logger.info(f"Commercial: Excluidos {skipped} pedidos 'Recoge Cliente' del validador.")

            # Batch fetch incidences to avoid N+1 queries in UI thread
            so_ids = [r['id'] for r in recs_validos]
            Ticket = self.odoo.odoo.env['helpdesk.ticket']
            tickets_data = Ticket.search_read([('x_sale_order_id', 'in', so_ids)], ['x_sale_order_id', 'name', 'stage_id', 'number'])
            ticket_map = {t['x_sale_order_id'][0]: t for t in tickets_data}

        results = []
        for r in recs_validos:
            results.append({
                'id': r['id'],
                'name': r['name'],
                'partner_id_int': r['partner_id'][0] if r['partner_id'] else None,
                'partner': r['partner_id'][1] if r['partner_id'] else "Consumidor Final",
                'amount': r['amount_untaxed'],
                'date': r['date_order'],
                'salesperson_id': r['user_id'][0] if r['user_id'] else None,
                'salesperson': r['user_id'][1] if r['user_id'] else "No asignado",
                'state': r['state'],
                'so_status': r['state_order_id'][1] if r.get('state_order_id') else "",
                'incidence': ticket_map.get(r['id'])
            })
        logger.info(f"Commercial: get_pending_orders finished with {len(results)} results (excluidos Recoge Cliente).")
        return results

    def get_ai_suggestions(self, recent_validations: List[Dict]) -> List[Dict]:
        """
        Analyzes recent blocked validations. If a client appears frequently 
        blocked due to discounts, the AI suggests creating a Custom Rule for them.
        """
        suggestions = []
        client_blocks = {}
        
        for v in recent_validations:
            if (v.get('status') == 'BLOQUEADO' or v.get('status') == 'ERROR') and v.get('partner_id_int'):
                pid = v['partner_id_int']
                client_blocks[pid] = client_blocks.get(pid, {'count': 0, 'name': v.get('partner', 'Unknown')})
                client_blocks[pid]['count'] += 1
                
        for pid, data in client_blocks.items():
            if data['count'] >= 2: # Very aggressive threshold for demo purposes (suggest after 2 blocks)
                suggestions.append({
                    'type': 'new_rule',
                    'partner_id': pid,
                    'msg': f"💡 El cliente '{data['name']}' ha sido bloqueado {data['count']} veces recientemente por descuentos excesivos. ¿Deseas configurarle unas Reglas de Cliente exclusivas para agilizar sus pedidos?"
                })
        return suggestions

    def get_client_leak_report(self, days=30) -> List[Dict]:
        """
        Generates a comprehensive report of commercial leaks (fuga) per client
        over the last X days based on confirmed sale orders.
        """
        from datetime import datetime, timedelta
        date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"Commercial: Generating leak report for the last {days} days...")
        
        # Ensure connection
        self.odoo._ensure_connected()
        
        # We look for confirmed orders (sale) or emitted (Pedido Emitido) in the last X days
        # In this context, 'sale' state usually means confirmed.
        domain = [
            ('date_order', '>=', date_limit),
            '|',
            ('state', '=', 'sale'),
            ('state_order_id.name', 'ilike', 'Pedido Emitido')
        ]
        
        SO = self.odoo.odoo.env['sale.order']
        recs = SO.search_read(domain, ['id', 'name', 'partner_id', 'amount_total'], order='date_order desc')
        
        if not recs:
            return []
            
        so_ids = [r['id'] for r in recs]
        
        # Validate all these historical orders to see what was "leaked"
        logger.info(f"Commercial: Validating {len(so_ids)} historical orders for leak report...")
        validations = self.batch_validate_orders(so_ids)
        
        # Group by client using the existing method
        return self.get_filtered_clients(validations)

    def get_filtered_clients(self, recent_validations: List[Dict]) -> List[Dict]:
        """
        Groups blocked validation results by client, summarizing the total fuga comercial 
        and the list of blocked orders. This helps identify clients who systematically 
        violate commercial constraints.
        """
        client_map = {}
        for v in recent_validations:
            if (v.get('status') == 'BLOQUEADO' or v.get('status') == 'ERROR') and v.get('partner_id_int'):
                pid = v['partner_id_int']
                name = v.get('partner_name') or v.get('partner', 'Desconocido')
                fuga = v.get('fuga_comercial', 0.0)
                so_name = v.get('so_name', 'SO? ')
                
                if pid not in client_map:
                    client_map[pid] = {
                        'partner_id': pid,
                        'partner_name': name,
                        'blocked_count': 0,
                        'total_fuga': 0.0,
                        'orders': []
                    }
                    
                client_map[pid]['blocked_count'] += 1
                client_map[pid]['total_fuga'] += fuga
                if so_name not in client_map[pid]['orders']:
                    client_map[pid]['orders'].append(so_name)
                    
        # Filter and sort (e.g., return those with at least 1 blocked order, sorted by highest fuga or count)
        results = list(client_map.values())
        results.sort(key=lambda x: (x['total_fuga'], x['blocked_count']), reverse=True)
        return results

    def calculate_fuga_comercial(self, validations: List[Dict] = None, so_ids: List[int] = None) -> float:
        """
        Calculates the estimated monetary loss from over-discounted, blocked orders.
        If validations is omitted, it will use batch_validate_orders to fetch and compute instantly.
        """
        total_fuga = 0.0
        
        if not validations and so_ids:
            validations = self.batch_validate_orders(so_ids)
            
        if not validations:
            return 0.0
            
        # Also return the actual full reports so the caller has them
        self.last_batch_validations = validations
            
        for v in validations:
            # We sum leakage from ALL orders, even if they are only WARNING or OK
            # to get the real impact of manual over-discounts or shipping leaks.
            if 'fuga_comercial' in v:
                total_fuga += v['fuga_comercial']
        return total_fuga

    def batch_validate_orders(self, so_ids: List[int]) -> List[Dict]:
        """
        Validates multiple SOs simultaneously making only 5 massive queries to Odoo instead
        of N*5 queries. This heavily optimizes the KPI startup time.
        """
        try:
            self.odoo._ensure_connected()
            if not so_ids: return []
            
            rules.load_from_json()
            
            # 1. Fetch all Orders
            SO = self.odoo.odoo.env['sale.order']
            orders_data = SO.search_read([('id', 'in', so_ids)], [
                'name', 'partner_id', 'partner_shipping_id', 'amount_untaxed',
                'order_line', 'carrier_id', 'user_id', 'supervisor_id', 'pricelist_id',
                'partner_type'  # Many2one: Tipo de cliente del pedido (campo personalizado Odoo)
            ])
            
            # 2. Gather Partner IDs for ZIPs and Categories
            all_partner_ids = set()
            all_line_ids = set()
            for o in orders_data:
                if o['partner_id']: all_partner_ids.add(o['partner_id'][0])
                if o['partner_shipping_id']: all_partner_ids.add(o['partner_shipping_id'][0])
                for line_id in o['order_line']:
                    all_line_ids.add(line_id)
                    
            # 3. Fetch Partners — solo zip y customer_type (Many2one oficial)
            partner_map = {}
            if all_partner_ids:
                partners = self.odoo._call_with_retry(
                    lambda: self.odoo.odoo.env['res.partner'].search_read(
                        [('id', 'in', list(all_partner_ids))], ['zip', 'customer_type']
                    )
                )
                for p in partners:
                    partner_map[p['id']] = p
                    
            # 5. Fetch all Lines
            line_map = {}
            all_prod_ids = set()
            if all_line_ids:
                lines = self.odoo.odoo.env['sale.order.line'].search_read([('id', 'in', list(all_line_ids))], ['name', 'price_subtotal', 'product_uom_qty', 'product_id', 'discount'])
                for l in lines:
                    line_map[l['id']] = l
                    if l['product_id']: all_prod_ids.add(l['product_id'][0])
                    
            # 6. Fetch all Products for gama
            prod_map = {}
            if all_prod_ids:
                prods = self.odoo.odoo.env['product.product'].search_read([('id', 'in', list(all_prod_ids))], ['categ_id', 'default_code'])
                for pr in prods:
                    prod_map[pr['id']] = {
                        'categ': pr.get('categ_id')[1] if pr.get('categ_id') else "",
                        'code': pr.get('default_code', "")
                    }

            # ------------- COMPUTE OFFLINE -------------
            results = []
            bur_clients = rules.BUR_GROUP_CLIENTS
            
            for order in orders_data:
                # Guard: excluir pedidos "Recoge Cliente" — transporte propio, no aplica validación
                _carrier_raw = order.get('carrier_id')
                _carrier_str = _carrier_raw[1].lower() if (_carrier_raw and len(_carrier_raw) > 1) else ""
                if 'recoge' in _carrier_str and 'cliente' in _carrier_str:
                    logger.debug(f"[{order['name']}] Recoge Cliente — excluido del validador comercial.")
                    continue

                report = {
                    'so_id': order['id'],
                    'so_name': order['name'],
                    'id': order['id'],
                    'amount_total': order['amount_untaxed'],
                    'status': 'OK',
                    'portes': {'status': 'OK', 'actual': 0.0, 'expected': 0.0, 'msg': ''},
                    'discounts': {'status': 'OK', 'lines': []},
                    'management': {'status': 'OK', 'msg': ''},
                    'fuga_comercial': 0.0,
                    'notes': ''
                }
                
                # Initial Setup
                p_id = order['partner_id'][0] if order['partner_id'] else None
                s_id = order['partner_shipping_id'][0] if order['partner_shipping_id'] else p_id
                p_name = order['partner_id'][1] if order['partner_id'] else ""

                # FIX: inicializar partner_id_int/partner_name en el report ANTES de cualquier
                # 'continue' de homologación, para que los reports ERROR/REVISION/ESPECIAL
                # también lleven estos campos y sean identificables en la UI.
                report['partner_id_int'] = p_id
                report['partner_name']   = p_name
                
                zip_code = ""
                if s_id and s_id in partner_map:
                    zip_code = partner_map[s_id].get('zip') or ""
                if not zip_code and p_id and p_id in partner_map:
                    zip_code = partner_map[p_id].get('zip') or ""
                    
                region = rules.get_region_by_cp(zip_code)
                region_bucket = rules.get_region_bucket(region) # 'A' or 'B'
                zone = rules.PENINSULA if region != "BALEARES" else rules.BALEARES
                base_imponible = order['amount_untaxed']
                
                # Determinar Tipo de cliente → ejecutar homologación.
                # Fuente 1: partner_type del pedido (ya en memoria, sin query extra).
                # Fuente 2: customer_type del partner (fallback si el pedido no tiene partner_type).
                # El servicio de homologación maneja internamente el pass-through
                # para tipos no registrados en catálogo.
                _pt = order.get('partner_type')
                if _pt and isinstance(_pt, (list, tuple)) and len(_pt) > 1:
                    customer_type_raw = _pt[1]
                else:
                    _ct = (partner_map.get(p_id) or {}).get('customer_type')
                    customer_type_raw = _ct[1] if (_ct and isinstance(_ct, (list, tuple)) and len(_ct) > 1) else ""

                homo_result = _homologacion_svc.homologar(customer_type_raw)
                report['homologacion'] = {
                    'odoo_tipo_cliente':   homo_result.odoo_tipo_cliente,
                    'segmento_aplicacion': homo_result.segmento_aplicacion,
                    'status':              homo_result.status.value,
                    'mensaje':             homo_result.mensaje_funcional,
                    'winning_rule_id':     homo_result.winning_rule_id,
                }

                # Si la homologación no es tarifable → bloquear inmediatamente
                if homo_result.status == HomologacionStatus.SIN_HOMOLOGACION:
                    report['status'] = 'ERROR'
                    report['notes'] = homo_result.mensaje_funcional
                    results.append(report)
                    logger.error(f"[{order['name']}] {homo_result.mensaje_funcional}")
                    continue

                if homo_result.status == HomologacionStatus.POR_DEFINIR:
                    report['status'] = 'REVISION'
                    report['notes'] = homo_result.mensaje_funcional
                    results.append(report)
                    logger.warning(f"[{order['name']}] {homo_result.mensaje_funcional}")
                    continue

                if homo_result.status == HomologacionStatus.FUERA_TABLA:
                    report['status'] = 'ESPECIAL'
                    report['notes'] = homo_result.mensaje_funcional
                    results.append(report)
                    logger.warning(f"[{order['name']}] {homo_result.mensaje_funcional}")
                    continue

                # Segmento homologado OK → continuar validación normal
                customer_type = homo_result.segmento_aplicacion
                customer_key  = customer_type  # para compatibilidad con código posterior

                # Check if this customer has special conditions
                # BUR_GROUP_CLIENTS is a set of client name strings (no per-client sub-rules)
                customer_special_rules = {}
                # (membership check via `is_bur_group` below; no dict lookup needed)
                
                # Check Management (Bur Group overlap check for management)
                is_bur_group = p_name in bur_clients
                if is_bur_group:
                    comercial = order['user_id'][0] if order['user_id'] else None
                    supervisor = order['supervisor_id'][0] if order['supervisor_id'] else None
                    # Solo bloqueamos si el supervisor está asignado Y no coincide con el comercial.
                    # Si supervisor es None (ej. Director Territorial sin supervisor en Odoo), lo permitimos.
                    if supervisor is not None and comercial != supervisor:
                        report['management']['status'] = 'Error'
                        report['management']['msg'] = "Gestión: Comercial != Supervisor"
                        report['status'] = 'BLOQUEADO'

                # Gather Lines Data
                order_lines = []
                for lid in order['order_line']:
                    if lid in line_map:
                        ol = line_map[lid].copy()
                        pr_id = ol['product_id'][0] if ol['product_id'] else None
                        ol['default_code'] = prod_map[pr_id]['code'] if pr_id and pr_id in prod_map else ""
                        order_lines.append(ol)

                # Paso 3 (P1): Check special client "Tarifa Distribuidor Platino (EUR)"
                pricelist_name = order['pricelist_id'][1] if order.get('pricelist_id') else ""
                is_platino = "Tarifa Distribuidor Platino" in pricelist_name
                
                predominant_sku_code = ""
                max_line_subtotal = -1.0
                actual_portes = 0.0
                has_valid_lines = False
                
                for line in order_lines:
                    lname = line['name'].lower()
                    if 'portes' in lname or 'entrega' in lname:
                        actual_portes += line.get('price_subtotal', 0)
                    elif line.get('product_uom_qty', 0) > 0:
                        has_valid_lines = True
                        subtotal = line.get('price_subtotal', 0)
                        if subtotal > max_line_subtotal:
                            max_line_subtotal = subtotal
                            predominant_sku_code = line['default_code']

                # Recopilar familias del pedido (para bonus +2 GAMAS / +OTRA GAMA)
                familias_pedido: set = set()
                for _l in order_lines:
                    _ln = _l['name'].lower()
                    if _l.get('product_uom_qty', 0) > 0 and 'portes' not in _ln and 'entrega' not in _ln:
                        _flb = rules.SKU_MASTER.get(_l['default_code'], {}).get('family_logic_base', '')
                        if _flb:
                            familias_pedido.add(_flb)

                # Paso 5 & 6 & 9: Resolve discounts, XPS logic and Pallet Break
                fuga_total = 0.0
                for line in order_lines:
                    lname = line['name'].lower()
                    if line.get('product_uom_qty', 0) <= 0 or 'portes' in lname or 'entrega' in lname: continue
                    
                    prod_code = line['default_code']
                    sku_info = rules.SKU_MASTER.get(prod_code, {})
                    pallet_size = sku_info.get('pallet_size_m2')
                    family_logic_base = sku_info.get('family_logic_base', '')
                    qty = line['product_uom_qty']

                    # Paso 5: XPS strict checks
                    is_xps_strict = prod_code in ["98.020", "98.021", "98.022"]
                    if is_xps_strict and pallet_size:
                        if abs(qty % pallet_size) > 0.01 and abs((qty % pallet_size) - pallet_size) > 0.01:
                            report['discounts']['status'] = 'Dissonancia'
                            report['discounts']['lines'].append({
                                'product': f"{line['name']} (XPS Estricto - Palet incompleto)",
                                'applied': qty,
                                'allowed': f"Múltiplos de {pallet_size}",
                                'diff': 0,
                                'price_subtotal': 0
                            })
                            report['status'] = 'BLOQUEADO'

                    # Paso 4: Excel Proposal 2026 (or Customer Override)
                    actual_dto = line.get('discount', 0)
                    
                    # Determinamos el límite de descuento: Prioridad Cliente Especial > Propuesta General Excel
                    dto_max_override = None
                    if customer_special_rules:
                        if base_imponible <= 1500:
                            dto_max_override = customer_special_rules.get('dto_max_hasta_1500_pct')
                        else:
                            dto_max_override = customer_special_rules.get('dto_max_mas_1500_pct')
                    
                    if dto_max_override is not None:
                        # Usamos regla de cliente especial
                        rules_max = float(dto_max_override)
                        if actual_dto > rules_max:
                            diff = actual_dto - rules_max
                            report['discounts']['status'] = 'Dissonancia'
                            report['discounts']['lines'].append({
                                'product': f"{line['name']} (Regla Especial Cliente)",
                                'applied': actual_dto,
                                'allowed': rules_max,
                                'diff': diff,
                                'price_subtotal': line.get('price_subtotal', 0)
                            })
                            fuga_total += (line.get('price_subtotal', 0) * diff / 100)
                            report['status'] = 'BLOQUEADO'
                    else:
                        # Usamos propuesta general del Excel 2026
                        p_res = self.discount_proposal.validate_range(
                            segmento=customer_type,
                            familia=family_logic_base,
                            base_imponible=base_imponible,
                            territorio=zone,
                            dto_solicitado=actual_dto,
                            familias_en_pedido=familias_pedido,
                        )
                        
                        if p_res.get('status') == 'BLOQUEADO':
                            rules_max = p_res['rules']['max']
                            diff = actual_dto - rules_max
                            report['discounts']['status'] = 'Dissonancia'
                            report['discounts']['lines'].append({
                                'product': f"{line['name']} (Excel 2026)",
                                'applied': actual_dto,
                                'allowed': rules_max,
                                'diff': diff,
                                'price_subtotal': line.get('price_subtotal', 0)
                            })
                            fuga_total += (line.get('price_subtotal', 0) * diff / 100)
                            report['status'] = 'BLOQUEADO'
                    
                    # Paso 9: Evaluate pallet break and penalties (Alert + XPS Penalty)
                    is_break_pallet_enabled = sku_info.get('break_pallet_flag', False)
                    if is_break_pallet_enabled and not is_xps_strict and pallet_size:
                        if abs(qty % pallet_size) > 0.01 and abs((qty % pallet_size) - pallet_size) > 0.01:
                            if family_logic_base == 'XPS':
                                line['cm_xps_penalty'] = True
                            line['pallet_break_alert'] = True

                # Paso 7: Resolve standard shipping with new 2026 grouping rules
                # 1. Group by SG and check for 'all_franco'.
                # El importe TOTAL del pedido (excl. portes/entrega) es la base tarifaria,
                # no el subtotal parcial de cada grupo. Regla comercial: si el pedido
                # conjunto supera el umbral de un grupo, ese grupo es franco.
                sg_subtotals = {}
                any_all_franco = False
                total_products_base = 0.0  # importe total de todas las lineas de producto (excl. portes)
                for line in order_lines:
                    lname = line.get('name', '').lower()
                    if line.get('product_uom_qty', 0) <= 0 or 'portes' in lname or 'entrega' in lname:
                        continue

                    sku = line.get('default_code', '')
                    sku_info = rules.SKU_MASTER.get(sku, {})
                    line_total = line.get('price_subtotal', 0)
                    total_products_base += line_total  # TODOS suman al total (umbral)

                    # FIX BUG-1: lineas de servicio no en SKU_MASTER (MANIPULACION, accesorios)
                    # contribuyen al total_products_base (umbral) pero NO generan un grupo de
                    # envio propio. Sin este fix, MANIPULACION crea 'G1_GENERAL' ficticio.
                    if not sku_info:
                        continue

                    if sku_info.get('all_franco'):
                        any_all_franco = True

                    item_sg = sku_info.get('shipping_group_key', 'G1_GENERAL')
                    sg_subtotals[item_sg] = sg_subtotals.get(item_sg, 0) + line_total

                # 2. Calculate sum of costs per group.
                # IMPORTANTE: se usa total_products_base (importe total del pedido)
                # como comparador para cada grupo, NO el subtotal parcial.
                total_standard_shipping = 0.0
                applied_sgs = []

                if any_all_franco:
                    total_standard_shipping = 0.0
                    msg_prefix = f"Región: {region} (Franco por SKU 'all_franco')"
                else:
                    for sg in sg_subtotals:  # solo grupos de productos reales
                        sg_rules = rules.SHIPPING_GROUPS.get(sg, [])
                        # FIX: usar bucket especifico por grupo (G4=C/D, G5=Baleares en B)
                        sg_bucket = rules.get_region_bucket_for_group(region, sg)
                        group_cost = 0.0
                        for r in sg_rules:
                            if r['region_bucket_key'] == sg_bucket and \
                               r['min_order_eur'] <= total_products_base <= r['max_order_eur']:
                                group_cost = float(r['price_eur'])
                                break

                        if group_cost > 0:
                            applied_sgs.append(f"{sg}({group_cost}€)")
                        total_standard_shipping += group_cost

                    if not applied_sgs:
                        msg_prefix = f"Región: {region} (Franco por grupos)"
                    else:
                        msg_prefix = f"Región: {region} ({' + '.join(applied_sgs)})"

                expected_portes = total_standard_shipping

                # Add CM XPS penalties
                cm_xps_penalties = sum([50.0 for line in order_lines if line.get('cm_xps_penalty')])
                if cm_xps_penalties > 0:
                    expected_portes += cm_xps_penalties
                    msg_prefix += f" + Rotura Palet CM XPS (+{cm_xps_penalties}€)"

                # Paso 8 (E1, E2, E3): Excepciones de portes
                # E1 — Dto. lineal >= 30% (Peninsula) / 25% (Baleares): portes gratis
                # IMPORTANT: E1 SOLO aplica cuando el pedido NO llega al umbral de franquicia
                # (expected_portes > 0). Si ya es 0 por tramo de tarifa, no tocar msg_prefix.
                # Ref: Portes Abril 2026 — nota al pie de Gama 1.
                min_dto_for_free_portes = 30.0 if zone == rules.PENINSULA else 25.0
                all_lines_high_discount = True
                for l in order_lines:
                    lname = l['name'].lower()
                    if l.get('product_uom_qty', 0) > 0 and 'portes' not in lname and 'entrega' not in lname:
                        if not rules.SKU_MASTER.get(l.get('default_code', '')):
                            continue  # servicio/accesorio: no cuenta para check E1
                        if l.get('discount', 0) < min_dto_for_free_portes - 0.01:
                            all_lines_high_discount = False

                carrier_name = order['carrier_id'][1].lower() if order.get('carrier_id') else ""
                if is_platino:
                    expected_portes = 0.0
                    msg_prefix = "Tarifa Distribuidor Platino (Portes Pagados)"
                elif has_valid_lines and all_lines_high_discount and expected_portes > 0:
                    # E1: solo cuando aún no era franco por importe
                    expected_portes = 0.0
                    msg_prefix = f"Dto. Lineal >= {min_dto_for_free_portes}% (Portes Gratis)"
                elif carrier_name and 'recoge' in carrier_name and 'cliente' in carrier_name:
                    expected_portes = 0.0
                    msg_prefix = "Recoge cliente"
                
                report['portes']['actual'] = actual_portes
                report['portes']['expected'] = expected_portes
                if abs(actual_portes - expected_portes) > 0.01:
                    report['portes']['status'] = 'Dissonancia'
                    report['portes']['msg'] = f"{msg_prefix}. Esperado {expected_portes}€ vs {actual_portes}€ actual."
                    if report['status'] == 'OK': report['status'] = 'WARNING'
                    # Leakage from shipping
                    if expected_portes > actual_portes:
                        fuga_total += (expected_portes - actual_portes)
                    
                report['fuga_comercial'] = fuga_total
                # partner_id_int y partner_name ya asignados al inicio del bucle (ver FIX arriba)
                results.append(report)
                
            return results
        except OSError as e:
            # Errores de red (timeout, WinError 10060, conexión rechazada, etc.)
            # Se re-lanzan para que el worker de la UI pueda mostrar un aviso claro
            # en lugar de devolver silenciosamente una lista vacía que confunde al usuario.
            logger.error(f"Batch validation — error de RED con Odoo: {e}")
            raise
        except Exception as e:
            logger.error(f"Batch validation — error interno: {e}", exc_info=True)
            return []

    def notify_salesperson(self, so_id: int, message: str) -> bool:
        """Posts a reprimand/notification directly into the Odoo Chatter."""
        try:
            self.odoo._ensure_connected()
            SO = self.odoo.odoo.env['sale.order']
            SO.message_post([so_id], body=f"📢 <b>Control Comercial Automático:</b><br/>{message}", message_type="comment")
            return True
        except Exception as e:
            logger.error(f"Failed to notify salesperson on SO {so_id}: {e}")
            return False

    def validate_order(self, so_id: int) -> Dict:
        """Validates an SO against Portes and Discount rules using the exact 11-step flow."""
        try:
            self.odoo._ensure_connected()
            rules.load_from_json()
            SO = self.odoo.odoo.env['sale.order']
            order_data_res = SO.search_read([('id', '=', so_id)], [
                'name', 'partner_id', 'partner_shipping_id', 'amount_untaxed',
                'order_line', 'carrier_id', 'user_id', 'supervisor_id', 'pricelist_id',
                'partner_type'  # Many2one: Tipo de cliente del pedido
            ])
            if not order_data_res: return {'status': 'ERROR', 'error_msg': 'SO not found'}
            order_data = order_data_res[0]
            
            # Initial Setup
            p_id = order_data['partner_id'][0] if order_data['partner_id'] else None
            s_id = order_data['partner_shipping_id'][0] if order_data['partner_shipping_id'] else p_id
            p_name = order_data['partner_id'][1] if order_data['partner_id'] else ""
            
            zip_code = ""
            if s_id:
                ship_res = self.odoo.odoo.env['res.partner'].search_read([('id', '=', s_id)], ['zip'])
                zip_code = ship_res[0].get('zip') or "" if ship_res else ""
            if not zip_code and p_id:
                partner_res = self.odoo.odoo.env['res.partner'].search_read([('id', '=', p_id)], ['zip'])
                zip_code = partner_res[0].get('zip') or "" if partner_res else ""
                
            region = rules.get_region_by_cp(zip_code)
            zone = rules.PENINSULA if region != "BALEARES" else rules.BALEARES
            base_imponible = order_data['amount_untaxed']
            
            report = {
                'so_id': so_id,
                'so_name': order_data['name'],
                'status': 'OK',
                'portes': {'status': 'OK', 'actual': 0.0, 'expected': 0.0, 'msg': ''},
                'discounts': {'status': 'OK', 'lines': []},
                'management': {'status': 'OK', 'msg': ''},
                'fuga_comercial': 0.0,
                'notes': ''
            }

            region_bucket = rules.get_region_bucket(region) # 'A' or 'B'

            # Determinar Tipo de cliente → ejecutar homologación.
            # Fuente 1: partner_type del pedido (ya en memoria, sin query extra).
            # Fuente 2: customer_type del partner (si el pedido no trae partner_type).
            _pt = order_data.get('partner_type')
            if _pt and isinstance(_pt, (list, tuple)) and len(_pt) > 1:
                customer_type_raw = _pt[1]
            else:
                p_read_res = self.odoo.odoo.env['res.partner'].search_read(
                    [('id', '=', p_id)], ['customer_type']
                ) if p_id else []
                _ct = p_read_res[0].get('customer_type') if p_read_res else None
                customer_type_raw = _ct[1] if (_ct and isinstance(_ct, (list, tuple)) and len(_ct) > 1) else ""

            homo_result = _homologacion_svc.homologar(customer_type_raw)

            report['homologacion'] = {
                'odoo_tipo_cliente':   homo_result.odoo_tipo_cliente,
                'segmento_aplicacion': homo_result.segmento_aplicacion,
                'status':              homo_result.status.value,
                'mensaje':             homo_result.mensaje_funcional,
                'winning_rule_id':     homo_result.winning_rule_id,
            }
            logger.info(
                f"[{order_data['name']}] Homologación: {homo_result.mensaje_funcional}"
            )

            # Si la homologación no permite validación automática → devolver error
            if homo_result.status == HomologacionStatus.SIN_HOMOLOGACION:
                report['status'] = 'ERROR'
                report['notes'] = homo_result.mensaje_funcional
                return report

            if homo_result.status == HomologacionStatus.POR_DEFINIR:
                report['status'] = 'REVISION'
                report['notes'] = homo_result.mensaje_funcional
                return report

            if homo_result.status == HomologacionStatus.FUERA_TABLA:
                report['status'] = 'ESPECIAL'
                report['notes'] = homo_result.mensaje_funcional
                return report

            # Segmento homologado OK → continuar validación normal
            customer_type = homo_result.segmento_aplicacion
            customer_key  = customer_type  # compatibilidad con código posterior

            # Check if this customer has special conditions (Step 1 & 3 Fix)
            # BUR_GROUP_CLIENTS is a set of client name strings (no per-client sub-rules)
            customer_special_rules = {}
            # membership is checked below via is_bur_group; no dict indexing needed

            # Check Management (Bur Group overlap check for management)
            bur_clients = rules.BUR_GROUP_CLIENTS
            is_bur_group = p_name and p_name.strip() in bur_clients
            if is_bur_group:
                comercial = order_data['user_id'][0] if order_data['user_id'] else None
                supervisor = order_data['supervisor_id'][0] if order_data['supervisor_id'] else None
                # Solo bloqueamos si el supervisor está asignado Y no coincide con el comercial.
                # Si supervisor es None (ej. Director Territorial sin supervisor en Odoo), lo permitimos.
                if supervisor is not None and comercial != supervisor:
                    report['management']['status'] = 'Error'
                    report['management']['msg'] = "Gestión: Comercial != Supervisor"
                    report['status'] = 'BLOQUEADO'

            # Gather Lines Data
            line_ids = order_data['order_line']
            lines_data = []
            if line_ids:
                lines_data = self.odoo.odoo.env['sale.order.line'].search_read([('id', 'in', line_ids)], ['name', 'price_subtotal', 'product_uom_qty', 'product_id', 'discount', 'price_unit'])
            
            # Decorate line_data with product_code
            for line in lines_data:
                p_id_prod = line['product_id'][0] if line['product_id'] else None
                if p_id_prod:
                    p_read_prod = self.odoo.odoo.env['product.product'].search_read([('id', '=', p_id_prod)], ['default_code'])
                    line['default_code'] = p_read_prod[0].get('default_code', "") if p_read_prod else ""
                else:
                    line['default_code'] = ""

            # Paso 3 (P1): Check special client "Tarifa Distribuidor Platino (EUR)"
            pricelist_name = order_data['pricelist_id'][1] if order_data.get('pricelist_id') else ""
            is_platino = "Tarifa Distribuidor Platino" in pricelist_name
            
            # Paso 4 (P2) is handled inside the per-line loop to apply the 55/60 rule.
            
            predominant_sku_code = ""
            max_line_subtotal = -1.0
            actual_portes = 0.0
            has_valid_lines = False
            
            for line in lines_data:
                lname = line['name'].lower()
                if 'portes' in lname or 'entrega' in lname:
                    actual_portes += line.get('price_subtotal', 0)
                elif line['product_uom_qty'] > 0:
                    has_valid_lines = True
                    subtotal = line.get('price_subtotal', 0)
                    if subtotal > max_line_subtotal:
                        max_line_subtotal = subtotal
                        predominant_sku_code = line['default_code']

            # Recopilar familias del pedido (para bonus +2 GAMAS / +OTRA GAMA)
            familias_pedido: set = set()
            for _l in lines_data:
                _ln = _l['name'].lower()
                if _l['product_uom_qty'] > 0 and 'portes' not in _ln and 'entrega' not in _ln:
                    _flb = rules.SKU_MASTER.get(_l['default_code'], {}).get('family_logic_base', '')
                    if _flb:
                        familias_pedido.add(_flb)

            # Paso 5 & 6: Resolve discounts and XPS logic
            fuga_total = 0.0
            for line in lines_data:
                lname = line['name'].lower()
                if line['product_uom_qty'] <= 0 or 'portes' in lname or 'entrega' in lname: continue
                
                prod_code = line['default_code']
                sku_info = rules.SKU_MASTER.get(prod_code, {})
                pallet_size = sku_info.get('pallet_size_m2')
                family_logic_base = sku_info.get('family_logic_base', '')

                # 98.020/98.021/98.022 logic (Paso 5)
                is_xps_strict = prod_code in ["98.020", "98.021", "98.022"]
                qty = line['product_uom_qty']
                
                if is_xps_strict and pallet_size:
                    if abs(qty % pallet_size) > 0.01 and abs((qty % pallet_size) - pallet_size) > 0.01:
                        report['discounts']['status'] = 'Dissonancia'
                        report['discounts']['lines'].append({
                            'product': f"{line['name']} (XPS Estricto - Palet incompleto)",
                            'applied': qty,
                            'allowed': f"Múltiplos de {pallet_size}",
                            'diff': 0,
                            'price_subtotal': 0
                        })
                        report['status'] = 'BLOQUEADO'

                actual_dto = line.get('discount', 0)
                
                # Double Validation Logic (Step 3 Fix): Special Rule Override > Excel Proposal 2026
                rules_max = None
                is_from_special = False
                
                if customer_special_rules:
                    dto_max_override = None
                    if base_imponible <= 1500:
                        dto_max_override = customer_special_rules.get('dto_max_hasta_1500_pct')
                    else:
                        dto_max_override = customer_special_rules.get('dto_max_mas_1500_pct')
                    
                    if dto_max_override is not None:
                        rules_max = float(dto_max_override)
                        is_from_special = True

                if rules_max is None:
                    # Fallback to general Excel 2026 Proposal
                    p_res = self.discount_proposal.validate_range(
                        segmento=customer_type,
                        familia=family_logic_base,
                        base_imponible=base_imponible,
                        territorio=zone,
                        dto_solicitado=actual_dto,
                        familias_en_pedido=familias_pedido,
                    )
                    if p_res.get('status') == 'BLOQUEADO':
                        rules_max = p_res['rules']['max']
                
                # Final check against rules_max (either special or general)
                if rules_max is not None and actual_dto > rules_max:
                    diff = actual_dto - rules_max
                    report['discounts']['status'] = 'Dissonancia'
                    label = "Regla Especial Cliente" if is_from_special else "Excel 2026"
                    report['discounts']['lines'].append({
                        'product': f"{line['name']} ({label})",
                        'applied': actual_dto,
                        'allowed': rules_max,
                        'diff': diff,
                        'price_subtotal': line.get('price_subtotal', 0)
                    })
                    fuga_total += (line.get('price_subtotal', 0) * diff / 100)
                    report['status'] = 'BLOQUEADO'

                # Paso 9: Evaluate pallet break and penalties
                is_break_pallet_enabled = sku_info.get('break_pallet_flag', False)
                if is_break_pallet_enabled and not is_xps_strict and pallet_size:
                    if abs(qty % pallet_size) > 0.01 and abs((qty % pallet_size) - pallet_size) > 0.01:
                        # Maintain 50€ penalty for XPS logic
                        if family_logic_base == 'XPS':
                            line['cm_xps_penalty'] = True
                        
                        # Generic alert for any break_pallet_flag
                        line['pallet_break_alert'] = True

            # Paso 7: Resolve expected shipping with new 2026 grouping rules.
            # REGLA COMERCIAL: el importe TOTAL del pedido (base producto, excl. portes/entrega)
            # determina el tramo tarifario de cada grupo de envío.
            sg_subtotals = {}
            any_all_franco = False
            total_products_base = 0.0  # importe total de todas las lineas de producto (excl. portes)
            for line in lines_data:
                lname = line.get('name', '').lower()
                if line.get('product_uom_qty', 0) <= 0 or 'portes' in lname or 'entrega' in lname:
                    continue

                sku = line.get('default_code', '')
                sku_info = rules.SKU_MASTER.get(sku, {})
                line_total = line.get('price_subtotal', 0)
                total_products_base += line_total  # TODOS suman al total (umbral)

                # FIX BUG-1: lineas de servicio no en SKU_MASTER (MANIPULACION, accesorios)
                # contribuyen al total_products_base (umbral) pero NO generan grupo propio.
                if not sku_info:
                    continue

                if sku_info.get('all_franco'):
                    any_all_franco = True

                item_sg = sku_info.get('shipping_group_key', 'G1_GENERAL')
                sg_subtotals[item_sg] = sg_subtotals.get(item_sg, 0) + line_total

            total_standard_shipping = 0.0
            applied_sgs = []

            if any_all_franco:
                total_standard_shipping = 0.0
                msg_prefix = f"Región: {region} (Franco por SKU 'all_franco')"
            else:
                for sg in sg_subtotals:  # solo grupos de productos reales
                    sg_rules = rules.SHIPPING_GROUPS.get(sg, [])
                    # FIX: usar bucket especifico por grupo (G4=C/D, G5=Baleares en B)
                    sg_bucket = rules.get_region_bucket_for_group(region, sg)
                    group_cost = 0.0
                    for r in sg_rules:
                        if r['region_bucket_key'] == sg_bucket and \
                           r['min_order_eur'] <= total_products_base <= r['max_order_eur']:
                            group_cost = float(r['price_eur'])
                            break

                    if group_cost > 0:
                        applied_sgs.append(f"{sg}({group_cost}€)")
                    total_standard_shipping += group_cost

                if not applied_sgs:
                    msg_prefix = f"Región: {region} (Franco por grupos)"
                else:
                    msg_prefix = f"Región: {region} ({' + '.join(applied_sgs)})"

            expected_portes = total_standard_shipping

            # Add pallet break penalties and alerts
            cm_xps_penalties = sum([50.0 for line in lines_data if line.get('cm_xps_penalty')])
            pallet_alerts = [line.get('default_code') for line in lines_data if line.get('pallet_break_alert')]

            if cm_xps_penalties > 0:
                expected_portes += cm_xps_penalties
                msg_prefix += f" + Rotura Palet XPS (+{cm_xps_penalties}€)"

            if pallet_alerts:
                report['notes'] += f" [ALERT: Rotura de palet en SKUs: {', '.join(pallet_alerts)}]"

            # Paso 8 (E1, E2): Excepciones de portes
            # E1 — Dto. lineal >= 30% (Peninsula) / 25% (Baleares): portes gratis
            # IMPORTANT: E1 SOLO aplica cuando expected_portes > 0 (no llega al umbral de franquicia).
            # Si ya es 0 por tramo de tarifa, no sobreescribir msg_prefix.
            # Ref: Portes Abril 2026 — nota al pie de Gama 1.
            min_dto_for_free_portes = 30.0 if zone == rules.PENINSULA else 25.0
            all_lines_high_discount = True
            for l in lines_data:
                lname = l['name'].lower()
                if l['product_uom_qty'] > 0 and 'portes' not in lname and 'entrega' not in lname:
                    if not rules.SKU_MASTER.get(l.get('default_code', '')):
                        continue  # servicio/accesorio: no cuenta para check E1
                    if l.get('discount', 0) < min_dto_for_free_portes - 0.01:
                        all_lines_high_discount = False

            carrier_name = order_data['carrier_id'][1].lower() if order_data.get('carrier_id') else ""
            if is_platino:
                expected_portes = 0.0
                msg_prefix = "Tarifa Distribuidor Platino (Portes Pagados)"
            elif has_valid_lines and all_lines_high_discount and expected_portes > 0:
                # E1: solo cuando aún no era franco por importe
                expected_portes = 0.0
                msg_prefix = f"Dto. Lineal >= {min_dto_for_free_portes}% (Portes Gratis)"
            elif carrier_name and 'recoge' in carrier_name and 'cliente' in carrier_name:
                expected_portes = 0.0
                msg_prefix = "Recoge cliente"
            
            report['portes']['actual'] = actual_portes
            report['portes']['expected'] = expected_portes
            if abs(actual_portes - expected_portes) > 0.01:
                report['portes']['status'] = 'Dissonancia'
                report['portes']['msg'] = f"{msg_prefix}. Esperado {expected_portes}€ vs {actual_portes}€ actual."
                if report['status'] == 'OK': report['status'] = 'WARNING'
                # Leakage from shipping (Step 4 Fix)
                if expected_portes > actual_portes:
                    fuga_total += (expected_portes - actual_portes)
                
            report['fuga_comercial'] = fuga_total
            report['partner_id_int'] = p_id
            report['partner_name'] = p_name
            return report

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {'status': 'ERROR', 'error_msg': str(e)}

    def post_chatter_dissonance(self, so_id: int, report: Dict, exception_reason: str = ""):
        """Posts a detailed dissonance report to Odoo chatter."""
        self.odoo._ensure_connected()
        SO = self.odoo.odoo.env['sale.order']
        order = SO.browse(so_id)
        
        body = f"⚠️ <b>Control Comercial 2026 - Disonancias Detectadas</b><br/>"
        body += f"<b>Nº Pedido:</b> {order.name}<br/>"
        body += f"<b>Cliente:</b> {order.partner_id.name}<br/>"
        body += f"<b>CP Destino:</b> {order.partner_shipping_id.zip}<br/>"
        body += f"<b>Base sin IVA:</b> {order.amount_untaxed:.2f}€<br/>"
        body += f"<b>Comercial:</b> {order.user_id.name if order.user_id else 'No asignado'}<br/>"
        
        if report['management']['status'] != 'OK':
             body += f"<br/>👤 <b>Error de Gestión:</b> {report['management']['msg']}<br/>"

        if report['portes']['status'] != 'OK':
            body += f"<br/>📦 <b>Portes:</b><br/>Actual: {report['portes']['actual']}€ | Esperado: {report['portes']['expected']}€<br/>"
            body += f"Regla aplicada: <i>{report['portes']['msg']}</i><br/>"
        
        if report['discounts']['status'] != 'OK':
            body += f"<br/>💸 <b>Descuentos Excedidos:</b><table border='1' style='border-collapse: collapse;'>"
            body += "<tr><th>Producto</th><th>Aplicado</th><th>Permitido</th><th>Dif.</th></tr>"
            for l in report['discounts']['lines']:
                diff_str = f"+{l['diff']}%" if l['diff'] > 0 else "N/A"
                body += f"<tr><td>{l['product']}</td><td>{l['applied']}</td><td>{l['allowed']}</td><td style='color:red;'>{diff_str}</td></tr>"
            body += "</table>"
        
        if exception_reason:
            body += f"<br/>✍️ <b>Motivo de la excepción:</b> {exception_reason}<br/>"
        
        body += f"<br/>@Responsable Territorial @Director Nacional - Revisión requerida."
        order.message_post(body=body)
        return True

    def evaluar_cliente(self, partner_id: int) -> Dict:
        """
        Realiza un análisis profundo de un cliente específico:
        - Revisa pedidos recientes (últimos 6 meses).
        - Calcula fuga comercial acumulada.
        - Identifica patrones de bloqueo.
        - Genera sugerencia de IA para Reglas de Cliente.
        """
        logger.info(f"Commercial: Evaluando cliente {partner_id}...")
        try:
            self.odoo._ensure_connected()
            from datetime import datetime, timedelta
            date_limit = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d %H:%M:%S')
            
            SO = self.odoo.odoo.env['sale.order']
            domain = [
                ('partner_id', '=', partner_id),
                ('date_order', '>=', date_limit),
                ('state', 'in', ['sale', 'done'])
            ]
            
            recs = SO.search_read(domain, ['name', 'amount_untaxed', 'date_order'], limit=50)
            
            if not recs:
                return {
                    'status': 'SIN_DATOS',
                    'msg': 'No se encontraron pedidos recientes para evaluar.',
                    'fuga_total': 0.0,
                    'bloqueos': 0,
                    'score': 100
                }
            
            so_ids = [r['id'] for r in recs]
            validations = self.batch_validate_orders(so_ids)
            
            total_fuga = 0.0
            bloqueos = 0
            for v in validations:
                total_fuga += v.get('fuga_comercial', 0.0)
                if v.get('status') == 'BLOQUEADO':
                    bloqueos += 1
            
            # Cálculo de "Score de Salud Comercial" (0-100)
            # Penalizamos por bloqueos y por fuga relativa al volumen
            total_ventas = sum(r['amount_untaxed'] for r in recs) or 1.0
            fuga_relativa = (total_fuga / total_ventas) * 100
            score = max(0, 100 - (bloqueos * 10) - (fuga_relativa * 2))
            
            # Sugerencia de IA
            suggestion = ""
            if bloqueos >= 3 or fuga_relativa > 5:
                suggestion = f"💡 Se recomienda crear una Regla de Cliente personalizada. Este cliente ha generado {total_fuga:.2f}€ de fuga comercial en {bloqueos} pedidos bloqueados."
            elif bloqueos > 0:
                suggestion = "💡 Considere revisar los descuentos aplicados manualmente por el comercial."
            else:
                suggestion = "✅ El cliente mantiene un comportamiento comercial excelente según las reglas 2026."
                
            return {
                'status': 'OK',
                'partner_id': partner_id,
                'pedidos_analizados': len(recs),
                'bloqueos': bloqueos,
                'fuga_total': total_fuga,
                'fuga_relativa': round(fuga_relativa, 2),
                'score': int(score),
                'sugerencia_ai': suggestion,
                'detalles': validations
            }
        except Exception as e:
            logger.error(f"Error evaluando cliente {partner_id}: {e}")
            return {'status': 'ERROR', 'msg': str(e)}

    def apply_portes_correction(self, so_id: int, expected_portes: float):
        """Corrects the shipping cost on the SO."""
        self.odoo._ensure_connected()
        SO = self.odoo.odoo.env['sale.order']
        order = SO.browse(so_id)
        found = False
        for line in order.order_line:
            if 'portes' in line.name.lower() or 'entrega' in line.name.lower():
                line.write({'price_unit': expected_portes})
                found = True
                break
        if not found: return False
        order.message_post(body=f"✅ Portes corregidos automáticamente a {expected_portes}€ según política 2026.")
        return True

    def check_so_compliance(self, so_name: str) -> str:
        """Quick check for LogisticsTab."""
        try:
            if so_name in self._problematic_sos: return 'UNKNOWN'
            self.odoo._ensure_connected()
            SO = self.odoo.odoo.env['sale.order']
            so_ids = SO.search([('name', '=', so_name)], limit=1)
            if not so_ids: return 'UNKNOWN'
            report = self.validate_order(so_ids[0])
            return report['status']
        except Exception as e:
            msg = str(e)
            if "risk_amount_exceeded" in msg:
                self._problematic_sos.add(so_name)
                logger.warning(f"Odoo Server Error (Skiping): {so_name} has a partner with a broken risk calculation. {msg}")
            else:
                logger.error(f"Commercial check failed for SO {so_name}: {e}")
            return 'UNKNOWN'
