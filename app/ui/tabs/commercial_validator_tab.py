from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QHBoxLayout, QMessageBox, QInputDialog,
    QCheckBox, QLineEdit, QComboBox, QFrame, QScrollArea, QFileDialog, QDialog
)
from PySide6.QtCore import QThread, Signal, QTimer, Qt, QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtCore import QUrl
from loguru import logger
import bur2000_theme
import base64
import datetime
from db.services.commercial_service import CommercialService
from db.services.homologacion_service import HomologacionService

class PendingValidatorWorker(QThread):
    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, service):
        super().__init__()
        self.service = service

    def run(self):
        try:
            pending = self.service.get_pending_orders()
            if not pending:
                self.finished_signal.emit([])
                return

            pending = pending[:50]
            so_ids = [p['id'] for p in pending]

            validations = self.service.batch_validate_orders(so_ids)
            v_map = {v['so_id']: v for v in validations if 'so_id' in v}
            for p in pending:
                p['validation'] = v_map.get(p['id'])

            # ── Enriquecer con líneas detalladas (1 query extra) ──────────────
            try:
                env = self.service.odoo.odoo.env

                # Obtener todos los IDs de líneas de los pedidos pendientes
                orders_raw = env['sale.order'].search_read(
                    [('id', 'in', so_ids)],
                    ['id', 'name', 'order_line', 'partner_id',
                     'partner_shipping_id', 'carrier_id', 'pricelist_id']
                )
                order_meta = {o['id']: o for o in orders_raw}

                all_line_ids = []
                for o in orders_raw:
                    all_line_ids.extend(o['order_line'])

                lines_raw = env['sale.order.line'].search_read(
                    [('id', 'in', all_line_ids)],
                    ['order_id', 'name', 'product_id',
                     'product_uom_qty', 'discount', 'price_unit', 'price_subtotal']
                ) if all_line_ids else []

                # Obtener default_code en bloque
                prod_ids = list({l['product_id'][0] for l in lines_raw if l.get('product_id')})
                prods_raw = env['product.product'].search_read(
                    [('id', 'in', prod_ids)], ['default_code']
                ) if prod_ids else []
                prod_sku = {p['id']: (p.get('default_code') or '') for p in prods_raw}

                # Indexar líneas por order_id
                lines_by_order: dict = {}
                for l in lines_raw:
                    oid = l['order_id'][0] if l.get('order_id') else None
                    if oid is None:
                        continue
                    pid = l['product_id'][0] if l.get('product_id') else None
                    lines_by_order.setdefault(oid, []).append({
                        'sku':        prod_sku.get(pid, ''),
                        'name':       l['name'],
                        'qty':        float(l.get('product_uom_qty') or 0),
                        'dto':        float(l.get('discount') or 0),
                        'price_unit': float(l.get('price_unit') or 0),
                        'subtotal':   float(l.get('price_subtotal') or 0),
                    })

                # Adjuntar al pendiente
                for p in pending:
                    sid = p['id']
                    p['lines_detail']  = lines_by_order.get(sid, [])
                    meta               = order_meta.get(sid, {})
                    p['carrier_name']  = meta.get('carrier_id', [None, ''])[1] if meta.get('carrier_id') else ''
                    p['pricelist_name']= meta.get('pricelist_id', [None, ''])[1] if meta.get('pricelist_id') else ''
                    ship_id            = meta.get('partner_shipping_id')
                    p['shipping_id']   = ship_id[0] if ship_id else None
            except Exception as enrich_err:
                import traceback
                from loguru import logger as _log
                _log.warning(f"[Validator] No se pudieron enriquecer líneas: {enrich_err}")

            self.finished_signal.emit(pending)
        except Exception as e:
            self.error_signal.emit(str(e))



class AssignSegmentWorker(QThread):
    """
    Worker para asignar una categoría (tipo de cliente) a un partner en Odoo
    y revalidar el pedido (fix BUG-002).
    """
    finished_signal = Signal(bool, str)  # (success, message)

    def __init__(self, service, partner_id: int, category_name: str, so_id: int):
        super().__init__()
        self.service = service
        self.partner_id = partner_id
        self.category_name = category_name
        self.so_id = so_id

    def run(self):
        try:
            odoo = self.service.odoo
            odoo._ensure_connected()

            # 1. Buscar o crear la categoría en Odoo
            Category = odoo.odoo.env['res.partner.category']
            cat_ids = Category.search([('name', '=', self.category_name)], limit=1)
            if not cat_ids:
                cat_id = Category.create({'name': self.category_name})
                logger.info(f"[BUG-002] Categoría creada en Odoo: '{self.category_name}' id={cat_id}")
            else:
                cat_id = cat_ids[0]
                logger.info(f"[BUG-002] Categoría encontrada en Odoo: '{self.category_name}' id={cat_id}")

            # 2. Asignar al partner (many2many: reemplazar lista completa con [(6,0,[id])])
            Partner = odoo.odoo.env['res.partner']
            Partner.write([self.partner_id], {'category_id': [(4, cat_id)]})
            logger.info(f"[BUG-002] Partner {self.partner_id} actualizado con categoría id={cat_id}")

            # 3. Post chatter en el pedido
            SO = odoo.odoo.env['sale.order']
            SO.message_post(
                [self.so_id],
                body=f"🏷️ <b>Segmento asignado manualmente desde BUR2000:</b> {self.category_name}",
                message_type='comment'
            )

            self.finished_signal.emit(True, f"Segmento '{self.category_name}' asignado correctamente al cliente.")
        except Exception as e:
            logger.error(f"[BUG-002] Error asignando segmento: {e}")
            self.finished_signal.emit(False, str(e))
            
class OrderActionWorker(QThread):
    finished_signal = Signal(bool, str)
    
    def __init__(self, service, action, so_ids: list, reason="", extra_data=None):
        super().__init__()
        self.service = service
        self.action = action
        self.so_ids = so_ids
        self.reason = reason
        self.extra_data = extra_data or {}

    def run(self):
        try:
            SO = self.service.odoo.odoo.env['sale.order']
            
            if self.action == "aprobar":
                for sid in self.so_ids:
                    try: SO.action_approve([sid])
                    except: SO.message_post([sid], body="✅ Pedido Aprobado por el departamento de Administración.", message_type="comment")
                self.finished_signal.emit(True, f"{len(self.so_ids)} Pedidos Aprobados.")
                
            elif self.action == "devolver":
                msg = f"❌ Pedido Devuelto por Administración.<br/><b>Motivo:</b> {self.reason}"
                for sid in self.so_ids:
                    SO.message_post([sid], body=msg, message_type="comment")
                self.finished_signal.emit(True, f"{len(self.so_ids)} Pedidos Devueltos al comercial.")
                
            elif self.action == "confirmar":
                # En BUR2000 'Confirmar' desde el Validador Comercial NO es action_confirm de Odoo.
                # Debe ser una aprobación administrativa (pisa el estado a nivel chatter o usa action_approve si existe)
                # para que logística lo vea, pero SIN crear el albarán todavía.
                for sid in self.so_ids:
                    try:
                        SO.action_approve([sid])
                    except:
                        SO.message_post([sid], body="🚀 Pedido validado comercialmente por Administración (BUR2000). Pendiente de confirmación final.", message_type="comment")
                self.finished_signal.emit(True, f"{len(self.so_ids)} Pedidos validados comercialivamente.")
                
            elif self.action == "autofix_portes":
                for sid in self.so_ids:
                    self.service.apply_portes_correction(sid, self.extra_data.get('expected_portes', 0.0))
                self.finished_signal.emit(True, "Portes auto-corregidos en Odoo.")
                
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class CommercialValidatorTab(QWidget):
    def __init__(self, service: CommercialService, parent=None):
        super().__init__(parent)
        self.service = service
        self.worker = None
        self.all_records = []
        self.auto_pilot_enabled = False
        self._current_detail_partner_id = None  # para el panel de asignación (BUG-002)
        self._current_detail_so_id = None
        
        self._build_ui()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        self.timer.start(60000)
        
        self.load_data()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        # Header Title and Refresh
        header_lay = QHBoxLayout()
        title_lbl = QLabel("✅ Validador Automático Mega Pro")
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {getattr(bur2000_theme.BUR, 'primary', '#2C3E50')};")
        header_lay.addWidget(title_lbl)
        
        self.chk_autopilot = QCheckBox("🤖 Modo Piloto Automático (Aprueba Válidos solo)")
        self.chk_autopilot.setStyleSheet("font-weight: bold; color: #6f42c1;")
        self.chk_autopilot.toggled.connect(self._toggle_autopilot)
        header_lay.addWidget(self.chk_autopilot)
        
        header_lay.addStretch()
        
        self.btn_refresh = QPushButton("↻ Actualizar Ahora")
        self.btn_refresh.setStyleSheet(getattr(bur2000_theme.BUR, 'button_secondary', ''))
        self.btn_refresh.clicked.connect(self.load_data)
        header_lay.addWidget(self.btn_refresh)


        lay.addLayout(header_lay)

        # KPI Dashboard
        self.kpi_layout = QHBoxLayout()
        
        self.lbl_kpi_total = self._create_kpi_card("Total Pendientes", "0", "#17a2b8")
        self.lbl_kpi_valid = self._create_kpi_card("Válidos", "0", "#10B981")
        self.lbl_kpi_blocked = self._create_kpi_card("Bloqueados", "0", "#dc3545")
        self.lbl_kpi_fuga = self._create_kpi_card("Fuga Rescatada", "0.00 €", "#ffc107", text_color="black")

        self.kpi_layout.addWidget(self.lbl_kpi_total)
        self.kpi_layout.addWidget(self.lbl_kpi_valid)
        self.kpi_layout.addWidget(self.lbl_kpi_blocked)
        self.kpi_layout.addWidget(self.lbl_kpi_fuga)
        lay.addLayout(self.kpi_layout)

        # Search and Filters
        filter_lay = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Buscar por Referencia o Cliente...")
        self.txt_search.textChanged.connect(self._render_table)
        filter_lay.addWidget(self.txt_search)
        
        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["Todos", "Válidos", "Bloqueados", "Warnings", "Sin segmento"])
        self.cmb_status.currentTextChanged.connect(self._render_table)
        filter_lay.addWidget(self.cmb_status)
        lay.addLayout(filter_lay)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["☑", "ID Pedido", "Referencia", "Cliente", "Fecha", "Total", "Estado", "Acciones"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(f"QTableWidget {{ background-color: white; border: 1px solid {getattr(bur2000_theme.BUR, 'border', '#ccc')}; border-radius: 6px; }}")
        self.table.itemClicked.connect(self._on_row_clicked)
        lay.addWidget(self.table)

        # ── Panel de Criterios (visible al clicar una fila) ──────
        # Barra de título con botón toggle para el panel de asignación
        criteria_header = QHBoxLayout()
        criteria_title = QLabel("🔍 Criterio de Validación Detallado")
        criteria_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #555; margin-top: 6px;")
        criteria_header.addWidget(criteria_title)
        criteria_header.addStretch()

        # Botón toggle para el panel de asignación (solo visible cuando hay pedido sin segmento)
        self.btn_toggle_assign = QPushButton("⚠️ Segmento sin asignar  ▼")
        self.btn_toggle_assign.setStyleSheet(
            "background-color: #f57f17; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        self.btn_toggle_assign.setVisible(False)
        self.btn_toggle_assign.clicked.connect(self._toggle_assign_panel)
        criteria_header.addWidget(self.btn_toggle_assign)
        lay.addLayout(criteria_header)

        # ── Panel de Asignación colapsable (empieza oculto) ─────────────
        self.assign_panel = QFrame()
        self.assign_panel.setStyleSheet(
            "QFrame { background: #fff8e1; border: 1px solid #f9a825; border-radius: 8px; "
            "margin-bottom: 4px; }"
        )
        assign_lay = QHBoxLayout(self.assign_panel)
        assign_lay.setContentsMargins(12, 8, 12, 8)
        assign_lay.setSpacing(8)

        assign_icon = QLabel("⚠️")
        assign_icon.setStyleSheet("font-size: 18px;")
        assign_lay.addWidget(assign_icon)

        assign_msg = QLabel("<b>Segmento sin asignar.</b> Selecciona el tipo de cliente y guárdalo en Odoo:")
        assign_msg.setStyleSheet("color: #5d4037; font-size: 12px;")
        assign_lay.addWidget(assign_msg)

        self.cmb_segment_assign = QComboBox()
        self.cmb_segment_assign.setMinimumWidth(320)
        self.cmb_segment_assign.setStyleSheet(
            "background: white; border: 1px solid #f9a825; border-radius: 4px; padding: 4px;"
        )
        # ── Orden por frecuencia de uso (los más habituales primero) ────
        _PRIORITY_ORDER = [
            # 1. Constructoras y empresa
            "Empresas Constructoras",
            "Constructora",
            "Constructor",
            "Empresa de Reformas",
            "Promotora",
            "Aplicador. Independiente",
            "Aplicador",
            "Arquitecto / Estudio",
            # 2. Distribuidores
            "Distribuidor Oficial. Independiente",
            "Distribuidor Oficial",
            "Distribuidor Oficial. Grupo de Compra",
            "Distribuidor Oficial. Grupo Compra BDB",
            "Distribuidor Oficial. Grupo Compra BigMat",
            "Distribuidor Oficial. Grupo Compra BME",
            "Distribuidor Oficial. Grupo Compra Ibricks",
            "Distribuidor Oficial. Grupo Compra Matdeco",
            "Distribuidor Potencial. Independiente",
            "Distribuidor Potencial. Grupo Compra BDB",
            "Distribuidor Potencial. Grupo Compra BigMat",
            "Distribuidor Potencial. Grupo Compra BME",
            "Distribuidor Potencial. Grupo Compra EMCCAT",
            "Distribuidor Potencial. Grupo Compra Gamma",
            "Distribuidor Potencial. Grupo Compra Ibergroup",
            "Distribuidor Potencial. Grupo Compra Ibricks",
            "Distribuidor Potencial. Grupo Compra Magatzem",
            "Distribuidor Potencial. Grupo Compra Matdeco",
            "Distribuidor Potencial. Grupo Compra Saint Gobain",
            # 3. Almacenes
            "Almacén de Construcción. Independiente",
            "Almacén de Construcción",
            "Almacén de Construcción. Grupo de Compra",
            "Almacén de Construcción. Grupo Compra BDB",
            "Almacén de Construcción. Grupo Compra BigMat",
            "Almacén de Construcción. Grupo Compra BME",
            "Almacén de Construcción. Grupo Compra EMCCAT",
            "Almacén de Construcción. Grupo Compra Gamma",
            "Almacén de Construcción. Grupo Compra Ibergroup",
            "Almacén de Construcción. Grupo Compra Ibricks",
            "Almacén de Construcción. Grupo Compra Magatzem",
            "Almacén de Construcción. Grupo Compra Matdeco",
            "Almacén de Construcción. Grupo Compra UNYCO",
            "Almacenes Especializados",
            "Almacenes Especialistas (PYL)",
            "Almacén de Aislamientos",
            # 4. Instaladores
            "Instaladores y Reformistas",
            "Instalador de Cubiertas y Forjados",
            "Instaladores de Aislamientos PYL",
            # 5. PYL / Parquet / Sound
            "PYL",
            "Almacén de Parquet. Independiente",
            "Almacén de Parquet. Grupo Compra Ibricks",
            "Almacén de Parquet. Grupo BDB",
            "Parquet Francesc. Independiente",
            "Instalador de Parquet",
            # 6. Ferretería
            "Ferretería. Independiente",
            "Ferretería",
            "Ferretería. Grupo de Compra",
            # 7. Fuera de tabla / especiales
            "Particular",
            "Promotores o Arquitectos o Particular",
            "Administración Pública",
            "Exportación",
            "Direccional. Nacional",
            "Direccional. Internacional",
            "Tipo de Empresa por Definir",
            # 8. Axarquía (al final)
        ]
        try:
            _homo_svc = HomologacionService()
            all_entries = {e['odoo_tipo_cliente']: e for e in _homo_svc.listar_entradas()}
            # Añadir primero los del orden prioritario que existen en catálogo
            added = set()
            for key in _PRIORITY_ORDER:
                if key in all_entries:
                    e = all_entries[key]
                    lbl = f"{e['odoo_tipo_cliente']}  →  {e['segmento_aplicacion']}"
                    self.cmb_segment_assign.addItem(lbl, userData=e['odoo_tipo_cliente'])
                    added.add(key)
            # Añadir el resto (Axarquía y cualquier nuevo)
            for key, e in all_entries.items():
                if key not in added:
                    lbl = f"{e['odoo_tipo_cliente']}  →  {e['segmento_aplicacion']}"
                    self.cmb_segment_assign.addItem(lbl, userData=e['odoo_tipo_cliente'])
        except Exception:
            pass
        assign_lay.addWidget(self.cmb_segment_assign)

        self.btn_assign_segment = QPushButton("💾 Guardar y Revalidar")
        self.btn_assign_segment.setStyleSheet(
            "background-color: #f57f17; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 6px 12px; min-width: 160px;"
        )
        self.btn_assign_segment.clicked.connect(self._assign_segment_action)
        assign_lay.addWidget(self.btn_assign_segment)
        assign_lay.addStretch()

        self.assign_panel.setVisible(False)  # oculto por defecto
        lay.addWidget(self.assign_panel)

        # Scroll de detalle
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFixedHeight(340)
        self.detail_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #ddd; border-radius: 8px; background: #f8f9fa; }"
        )
        self.detail_lbl = QLabel(
            "<i style='color:#999;'>Haz clic en cualquier pedido de la tabla para ver el criterio de validación detallado "
            "(% aplicado vs % permitido, portes, gestión comercial).</i>"
        )
        self.detail_lbl.setTextFormat(Qt.RichText)
        self.detail_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.detail_lbl.setWordWrap(True)
        self.detail_lbl.setContentsMargins(14, 12, 14, 12)
        self.detail_scroll.setWidget(self.detail_lbl)
        lay.addWidget(self.detail_scroll)

        
        # Mass Actions 
        mass_lay = QHBoxLayout()
        self.chk_select_all = QCheckBox("Seleccionar Todos")
        self.chk_select_all.stateChanged.connect(self._toggle_select_all)
        mass_lay.addWidget(self.chk_select_all)
        
        mass_lay.addStretch()
        
        btn_mass_confirm = QPushButton("🔵 Aprobar Seleccionados")
        btn_mass_confirm.setStyleSheet("background-color: #007bff; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_mass_confirm.clicked.connect(lambda: self.execute_mass_action("confirmar"))
        mass_lay.addWidget(btn_mass_confirm)
        
        btn_mass_return = QPushButton("🔴 Devolver Seleccionados")
        btn_mass_return.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_mass_return.clicked.connect(lambda: self.execute_mass_action("devolver"))
        mass_lay.addWidget(btn_mass_return)
        
        lay.addLayout(mass_lay)

    def _create_kpi_card(self, title, value, bg_color, text_color="white"):
        card = QFrame()
        card.setStyleSheet(f"background-color: {bg_color}; border-radius: 8px;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 10, 15, 10)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {text_color}; font-size: 11px; font-weight: bold; opacity: 0.8;")
        
        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"color: {text_color}; font-size: 24px; font-weight: bold;")
        lbl_val.setProperty("kpi_value", True)
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        card.value_label = lbl_val
        return card

    def _toggle_autopilot(self, checked):
        self.auto_pilot_enabled = checked
        if checked:
            QMessageBox.information(self, "Piloto Automático", "A partir de ahora, cada 60s los pedidos VÁLIDOS se aprobarán de forma silenciosa.")

    def _toggle_select_all(self, state):
        checked = (state == Qt.Checked.value or state == Qt.Checked)
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk:
                chk.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def timer_tick(self):
        if self.auto_pilot_enabled and self.all_records:
            # Encuentra los validos y los confirma automagicamente
            valid_ids = [r['id'] for r in self.all_records if r and r.get('validation') and r.get('validation', {}).get('status') == 'OK']
            if valid_ids:
                logger.info(f"Piloto automático aprobando {len(valid_ids)} pedidos.")
                worker = OrderActionWorker(self.service, "confirmar", valid_ids)
                worker.finished_signal.connect(lambda s, m: self.load_data())
                worker.start()
                return
        self.load_data()

    def load_data(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Actualizando...")
        self.worker = PendingValidatorWorker(self.service)
        self.worker.finished_signal.connect(self._on_data_loaded)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_data_loaded(self, records):
        # Mantenemos todos los registros, incluyendo ALERTA_TIPO_CLIENTE (antes se filtraban)
        # para que el usuario pueda identificarlos y gestionarlos visualmente.
        self.all_records = records
        self._update_kpis()
        self._render_table()
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("↻ Actualizar Ahora")
        logger.info(f"Validador automático actualizado: {len(self.all_records)} pedidos cargados.")

    def _on_error(self, error_msg: str):
        """Maneja errores del worker de validación: distingue red vs lógica interna."""
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("↻ Actualizar Ahora")

        is_network_error = any(kw in error_msg for kw in [
            "WinError", "urlopen", "10060", "10061", "Connection refused",
            "timed out", "timeout", "RemoteDisconnected", "ConnectionResetError"
        ])

        if is_network_error:
            logger.warning(f"[Validador] Error de red detectado: {error_msg}")
            QMessageBox.warning(
                self,
                "Sin conexión con Odoo",
                "⚠️ No se pudo conectar con el servidor Odoo.\n\n"
                "El servidor tardó demasiado en responder o está fuera de línea.\n\n"
                "Acciones recomendadas:\n"
                "  1. Verifica que Odoo está activo y accesible.\n"
                "  2. Comprueba la VPN / red corporativa.\n"
                "  3. Usa el botón '↻ Actualizar Ahora' para reintentar.\n\n"
                f"Detalle técnico: {error_msg[:120]}..."
            )
        else:
            logger.error(f"[Validador] Error interno: {error_msg}")
            QMessageBox.critical(
                self,
                "Error en Validador Comercial",
                f"❌ Se produjo un error inesperado en el validador:\n\n{error_msg[:300]}"
            )



    def _update_kpis(self):
        total = len(self.all_records)
        valids = sum(1 for r in self.all_records if r and r.get('validation') and r.get('validation', {}).get('status') == 'OK')
        blockeds = sum(1 for r in self.all_records
                       if r and r.get('validation') and
                       r.get('validation', {}).get('status') in ('ERROR', 'BLOQUEADO', 'REVISION', 'ESPECIAL'))
        warnings = sum(1 for r in self.all_records if r and r.get('validation') and r.get('validation', {}).get('status') == 'WARNING')
        
        fuga = 0.0
        for r in self.all_records:
            if not r: continue
            val = r.get('validation', {})
            if not val: continue
            portes = val.get('portes', {})
            if portes.get('status') == 'Dissonancia':
                exp = float(portes.get('expected', 0))
                act = float(portes.get('actual', 0))
                if exp > act: fuga += (exp - act)
        
        self.lbl_kpi_total.value_label.setText(str(total))
        self.lbl_kpi_valid.value_label.setText(str(valids))
        self.lbl_kpi_blocked.value_label.setText(str(blockeds + warnings))  # combining blockers and warnings visually might be ok, or just blockeds
        self.lbl_kpi_fuga.value_label.setText(f"{fuga:.2f} €")

    def _render_table(self):
        self.table.setRowCount(0)
        search_txt = self.txt_search.text().lower()
        status_filter = self.cmb_status.currentText()
        
        for r in self.all_records:
            if not r: continue
            val = r.get('validation') or {}
            status = val.get('status', 'DESCONOCIDO')
            
            client_name = r.get('partner', '')
            ref = str(r.get('name', ''))
            
            # Filters
            if search_txt and search_txt not in client_name.lower() and search_txt not in ref.lower():
                continue
            if status_filter == "Válidos" and status != 'OK': continue
            if status_filter == "Bloqueados" and status not in ('ERROR', 'REVISION', 'ESPECIAL', 'BLOQUEADO'): continue
            if status_filter == "Warnings" and status != 'WARNING': continue
            if status_filter == "Sin segmento" and status != 'ERROR': continue

            row = self.table.rowCount()
            self.table.insertRow(row)
            
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, chk_item)
            # Guardamos id para seleccion masiva
            chk_item.setData(Qt.UserRole, r.get('id', 0))
            
            if status == 'OK':
                color = Qt.green
                display_status = "✅ VÁLIDO"
            elif status == 'ERROR':
                color = Qt.red
                display_status = "🔴 BLOQUEADO - Sin segmento"
            elif status == 'BLOQUEADO':
                color = Qt.red
                display_status = "🔴 BLOQUEADO"
            elif status == 'REVISION':
                from PySide6.QtGui import QColor
                color = QColor("#e67e22")  # naranja
                display_status = "⚠️ POR DEFINIR"
            elif status == 'ESPECIAL':
                from PySide6.QtGui import QColor
                color = QColor("#8e44ad")  # morado
                display_status = "📌 FUERA TABLA"
            elif status == 'ALERTA_TIPO_CLIENTE':
                from PySide6.QtGui import QColor
                color = QColor("#6f42c1")
                display_status = "⚠️ CLASIFICAR"
            elif status == 'WARNING':
                color = Qt.darkYellow
                display_status = "🟡 AVISO"
            else:
                color = Qt.darkYellow
                display_status = status.upper()
                
            reason = val.get('notes', '')
            sub_msgs = []
            for sub_key in ['discounts', 'portes', 'management']:
                sub_dict = val.get(sub_key, {})
                if isinstance(sub_dict, dict) and sub_dict.get('msg'):
                    sub_msgs.append(sub_dict.get('msg'))
            # also check management status
            mgmt = val.get('management', {})
            if isinstance(mgmt, dict) and mgmt.get('status') not in ('OK', None, '') and mgmt.get('msg'):
                if mgmt['msg'] not in sub_msgs:
                    sub_msgs.append(mgmt['msg'])
            if sub_msgs:
                combined = " | ".join(sub_msgs)
                reason = f"{reason} | {combined}" if reason else combined
            if not reason and status == 'OK':
                reason = "Condiciones correctas"
                
            id_item = QTableWidgetItem(str(r.get('id', '')))
            # Store full validation dict and ref for detail panel
            id_item.setData(Qt.UserRole + 1, val)
            id_item.setData(Qt.UserRole + 2, ref)
            id_item.setData(Qt.UserRole + 3, r.get('lines_detail', []))
            id_item.setData(Qt.UserRole + 4, {
                'carrier_name':   r.get('carrier_name', ''),
                'pricelist_name': r.get('pricelist_name', ''),
                'amount':         r.get('amount', 0),
                'partner':        r.get('partner', ''),
                'date':           str(r.get('date', '')),
            })
            self.table.setItem(row, 1, id_item)


            so_id = str(r.get('id', ''))
            base_url = str(getattr(getattr(self.service, 'odoo', None), 'url', '') or '').strip().rstrip('/')
            if base_url:
                odoo_url = f"{base_url}/web#id={so_id}&model=sale.order&view_type=form"
                lbl_link = QLabel(f'<a href="{odoo_url}" style="color: #2b78e4; text-decoration: underline; font-weight: bold;">{ref}</a>')
                lbl_link.setOpenExternalLinks(True)
                lbl_link.setStyleSheet("margin-left: 5px;")
                self.table.setCellWidget(row, 2, lbl_link)
            else:
                self.table.setItem(row, 2, QTableWidgetItem(ref))
            
            self.table.setItem(row, 3, QTableWidgetItem(client_name))
            self.table.setItem(row, 4, QTableWidgetItem(str(r.get('date', ''))))
            self.table.setItem(row, 5, QTableWidgetItem(f"{r.get('amount', 0):.2f} €"))
            
            status_item = QTableWidgetItem(display_status)
            status_item.setForeground(Qt.white)
            status_item.setBackground(color)
            status_item.setTextAlignment(Qt.AlignCenter)
            tooltip_text = self._build_tooltip(val, reason)
            if tooltip_text:
                status_item.setToolTip(tooltip_text)
            self.table.setItem(row, 6, status_item)
            
            # Actions widget
            btn_widget = QWidget()
            btn_lay = QHBoxLayout(btn_widget)
            btn_lay.setContentsMargins(2, 2, 2, 2)
            btn_lay.setSpacing(5)

            btn_style = "font-size: 11px; font-weight: bold; padding: 4px 8px; border-radius: 4px;"
            
            # Portes autocorrect button logic — requires confirmation before applying
            expected_portes = None
            if val.get('portes', {}).get('status') == 'Dissonancia':
                expected_portes = val.get('portes', {}).get('expected', 0.0)
                actual_portes   = val.get('portes', {}).get('actual', 0.0)
                btn_fix = QPushButton("✨ Auto-Fix Portes")
                btn_fix.setStyleSheet(f"background-color: #6f42c1; color: white; {btn_style}")
                btn_fix.clicked.connect(
                    lambda checked=False, sid=so_id, xp=expected_portes, ap=actual_portes:
                        self._confirm_autofix_portes(sid, float(xp), float(ap))
                )
                btn_lay.addWidget(btn_fix)
            
            btn_confirmar = QPushButton("Confirmar")
            btn_confirmar.setStyleSheet(f"background-color: #007bff; color: white; {btn_style}")
            btn_devolver = QPushButton("Devolver")
            btn_devolver.setStyleSheet(f"background-color: #dc3545; color: white; {btn_style}")
            btn_historial = QPushButton("📋 Historial")
            btn_historial.setStyleSheet(f"background-color: #6c757d; color: white; {btn_style}")
            btn_historial.setToolTip("Ver historial de cambios (chatter) del pedido en Odoo")

            btn_confirmar.clicked.connect(lambda checked=False, id=so_id: self.execute_order_action("confirmar", [int(id)]))
            btn_devolver.clicked.connect(lambda checked=False, id=so_id: self.execute_order_action("devolver", [int(id)]))
            btn_historial.clicked.connect(lambda checked=False, id=so_id: self._open_odoo_chatter(id))

            btn_lay.addWidget(btn_confirmar)
            btn_lay.addWidget(btn_devolver)
            btn_lay.addWidget(btn_historial)
            btn_lay.addStretch()
            
            self.table.setCellWidget(row, 7, btn_widget)

    def _build_tooltip(self, val: dict, base_reason: str) -> str:
        """Construye un tooltip enriquecido con el % del tramo permitido y detalles por línea."""
        parts = []
        if base_reason:
            parts.append(base_reason)

        discount_block = val.get('discounts', {})
        lines = discount_block.get('lines', []) if isinstance(discount_block, dict) else []
        if lines:
            parts.append("── Descuentos ──")
            for ln in lines:
                product = ln.get('product', '?')
                applied = ln.get('applied', '?')
                allowed = ln.get('allowed', '?')
                next_max = ln.get('next_max')
                aviso = ln.get('aviso', False)

                if aviso and next_max is not None:
                    parts.append(
                        f"⚠ {product}\n"
                        f"   Aplicado: {applied}%  |  Tramo máx: {allowed}%  (sig. tramo: {next_max}%)"
                    )
                elif applied != '?' and allowed != '?':
                    parts.append(
                        f"❌ {product}\n"
                        f"   Aplicado: {applied}%  |  Máx permitido: {allowed}%"
                    )

        portes_block = val.get('portes', {})
        if isinstance(portes_block, dict) and portes_block.get('status') == 'Dissonancia':
            expected = portes_block.get('expected', 0)
            actual   = portes_block.get('actual', 0)
            parts.append(f"── Portes ──\n  Actual: {actual:.2f}€  |  Correcto: {expected:.2f}€")

        return "\n".join(parts)

    def _on_row_clicked(self, item):
        """Al clicar cualquier celda de una fila, muestra el panel de criterios
        y gestiona el panel de asignación de segmento (BUG-002)."""
        row = item.row()
        id_item = self.table.item(row, 1)
        if not id_item:
            return
        val = id_item.data(Qt.UserRole + 1)
        ref = id_item.data(Qt.UserRole + 2) or "?"
        lines_detail = id_item.data(Qt.UserRole + 3) or []
        order_meta   = id_item.data(Qt.UserRole + 4) or {}
        status = val.get('status', '?') if val else '?'
        if not val:
            self.detail_lbl.setText("<i style='color:#999;'>Sin datos de validación.</i>")
            self.assign_panel.setVisible(False)
            self.btn_toggle_assign.setVisible(False)
            return
        html = self._build_detail_html(val, ref, status, lines_detail, order_meta)
        self.detail_lbl.setText(html)

        # ── Botón toggle de asignación (solo si falta segmento) ────────────
        needs_segment = status in ('ERROR', 'REVISION') and \
            (not val.get('homologacion', {}).get('segmento_aplicacion'))

        # Panel siempre empieza COLAPSADO al cambiar de fila
        self.assign_panel.setVisible(False)
        self.btn_toggle_assign.setVisible(needs_segment)
        if needs_segment:
            self.btn_toggle_assign.setText("⚠️ Segmento sin asignar  ▼")

            # Guardar partner_id y so_id para el worker
            r_data = next(
                (r for r in self.all_records if str(r.get('id', '')) == id_item.text()),
                None
            )
            self._current_detail_partner_id = r_data.get('partner_id_int') if r_data else None
            self._current_detail_so_id = int(id_item.text()) if id_item.text().isdigit() else None

    def _toggle_assign_panel(self):
        """Despliega/colapsa el panel de asignación de segmento."""
        visible = self.assign_panel.isVisible()
        self.assign_panel.setVisible(not visible)
        if visible:
            self.btn_toggle_assign.setText("⚠️ Segmento sin asignar  ▼")
        else:
            self.btn_toggle_assign.setText("⚠️ Segmento sin asignar  ▲")


    def _build_detail_html(self, val: dict, ref: str, status: str,
                           lines_detail: list = None, order_meta: dict = None) -> str:
        """Genera el HTML detallado de criterios de validación para el panel inferior."""
        _status_colors = {
            'OK':       ('#27AE60', '✅'),
            'BLOQUEADO':('#dc3545', '🚫'),
            'ERROR':    ('#dc3545', '❌'),
            'WARNING':  ('#f39c12', '⚠️'),
            'REVISION': ('#6f42c1', '🔍'),
            'ESPECIAL': ('#17a2b8', '⭐'),
            'ALERTA_TIPO_CLIENTE': ('#6f42c1', '⚠️'),
        }
        color, icon = _status_colors.get(status, ('#888', '❓'))
        lines_detail = lines_detail or []
        order_meta   = order_meta   or {}

        html = (f"<div style='font-family: Arial, sans-serif; font-size: 12px;'>"
                f"<span style='font-weight:bold; font-size:14px; color:{color};'>"
                f"{icon} {ref}  —  {status}</span>&nbsp;&nbsp;")

        homo = val.get('homologacion', {})
        if isinstance(homo, dict):
            seg  = homo.get('segmento_aplicacion', '–')
            tipo = homo.get('odoo_tipo_cliente', '–')
            html += (f"<span style='color:#555;'>Segmento: <b>{seg}</b> &nbsp;|&nbsp; "
                     f"Tipo Odoo: <b>{tipo}</b></span>")

        # ── Meta del pedido ───────────────────────────────────────────────────
        carrier   = order_meta.get('carrier_name', '')  or '—'
        pricelist = order_meta.get('pricelist_name', '') or '—'
        partner   = order_meta.get('partner', '')        or '—'
        amount    = order_meta.get('amount', 0)
        date_str  = order_meta.get('date', '')           or '—'
        html += (f"<br/><span style='color:#777; font-size:11px;'>"
                 f"👤 {partner} &nbsp;|&nbsp; 📅 {date_str[:10]} &nbsp;|&nbsp; "
                 f"💶 {float(amount):,.2f}€ &nbsp;|&nbsp; "
                 f"🚚 {carrier} &nbsp;|&nbsp; 📋 {pricelist}</span>")

        html += "<hr style='border:none; border-top:1px solid #e0e0e0; margin:8px 0;'/>"

        # ── Líneas del pedido ────────────────────────────────────────────────
        if lines_detail:
            actual_portes = 0.0
            product_lines = []
            for l in lines_detail:
                lname_l = l['name'].lower()
                if 'portes' in lname_l or 'entrega' in lname_l:
                    actual_portes += l['subtotal']
                elif l['qty'] > 0:
                    product_lines.append(l)

            html += ("<b>📦 Líneas del pedido:</b>"
                     "<table style='width:100%;border-collapse:collapse;font-size:11px;margin:4px 0;'>"
                     "<tr style='background:#1D365C;color:white;'>"
                     "<th style='padding:3px 6px;text-align:left;'>SKU</th>"
                     "<th style='padding:3px 6px;text-align:left;'>Descripción</th>"
                     "<th style='padding:3px 6px;text-align:right;'>Cant</th>"
                     "<th style='padding:3px 6px;text-align:right;'>P. Unit</th>"
                     "<th style='padding:3px 6px;text-align:center;'>Dto %</th>"
                     "<th style='padding:3px 6px;text-align:right;'>Subtotal</th>"
                     "</tr>")

            for l in lines_detail:
                dto    = l['dto']
                lname_l = l['name'].lower()
                is_portes = 'portes' in lname_l or 'entrega' in lname_l

                if is_portes:
                    row_bg = "#e8f4fd"
                    dto_cell = f"<td style='text-align:center;padding:3px 6px;color:#17a2b8;'>— portes</td>"
                elif dto > 30:
                    row_bg = "#fdecea"
                    dto_cell = (f"<td style='text-align:center;padding:3px 6px;"
                                f"font-weight:bold;color:#dc3545;'>{dto:.1f}% ⚠️</td>")
                elif dto > 25:
                    row_bg = "#fff9e6"
                    dto_cell = (f"<td style='text-align:center;padding:3px 6px;"
                                f"font-weight:bold;color:#f39c12;'>{dto:.1f}%</td>")
                else:
                    row_bg = "white"
                    dto_cell = (f"<td style='text-align:center;padding:3px 6px;'>"
                                f"{dto:.1f}%</td>")

                short_name = l['name'][:50] + "…" if len(l['name']) > 50 else l['name']
                html += (f"<tr style='background:{row_bg};border-bottom:1px solid #f0f0f0;'>"
                         f"<td style='padding:3px 6px;font-family:monospace;'>{l['sku'] or '—'}</td>"
                         f"<td style='padding:3px 6px;'>{short_name}</td>"
                         f"<td style='padding:3px 6px;text-align:right;'>{l['qty']:g}</td>"
                         f"<td style='padding:3px 6px;text-align:right;'>{l['price_unit']:.2f}€</td>"
                         f"{dto_cell}"
                         f"<td style='padding:3px 6px;text-align:right;font-weight:bold;'>{l['subtotal']:,.2f}€</td>"
                         "</tr>")
            html += "</table>"

            # Fila resumen portes
            if actual_portes > 0:
                html += (f"<span style='font-size:11px;color:#17a2b8;'>"
                         f"🚚 Línea de portes en pedido: <b>{actual_portes:.2f}€</b></span><br/>")
            else:
                html += ("<span style='font-size:11px;color:#e74c3c;'>"
                         "🚚 Sin línea de portes en el pedido</span><br/>")

        html += "<hr style='border:none; border-top:1px solid #e0e0e0; margin:8px 0;'/>"

        # ── Descuentos ──
        disc  = val.get('discounts', {})
        dlines = disc.get('lines', []) if isinstance(disc, dict) else []
        if dlines:
            html += ("<b>💸 Descuentos por línea:</b>"
                     "<table style='width:100%; border-collapse:collapse; font-size:11px; margin:6px 0;'>"
                     "<tr style='background:#f0f0f0;'>"
                     "<th style='text-align:left;padding:4px 6px;'>Producto</th>"
                     "<th style='text-align:center;padding:4px 6px;'>% Aplicado</th>"
                     "<th style='text-align:center;padding:4px 6px;'>% Permitido</th>"
                     "<th style='text-align:center;padding:4px 6px;'>Diferencia</th>"
                     "<th style='text-align:left;padding:4px 6px;'>Criterio</th>"
                     "</tr>")
            for ln in dlines:
                prod    = ln.get('product', '?')
                applied = ln.get('applied', '?')
                allowed = ln.get('allowed', '?')
                diff    = ln.get('diff', 0)
                aviso   = ln.get('aviso', False)
                next_m  = ln.get('next_max')
                if aviso:
                    row_col = '#fff9e6'; ic = '#f39c12'
                    diff_s  = f"+{diff:.1f}%" if isinstance(diff, (int,float)) else '–'
                    crit    = f"⚠️ Escalado. Sig. tramo máx: {next_m}%" if next_m else "⚠️ Zona de escalado"
                else:
                    row_col = '#fdecea'; ic = '#dc3545'
                    diff_s  = f"+{diff:.1f}%" if isinstance(diff, (int,float)) else '–'
                    crit    = "❌ Supera el máximo permitido"
                html += (f"<tr style='background:{row_col};border-bottom:1px solid #eee;'>"
                         f"<td style='padding:3px 6px;'>{prod}</td>"
                         f"<td style='text-align:center;padding:3px 6px;font-weight:bold;'>{applied}%</td>"
                         f"<td style='text-align:center;padding:3px 6px;'>{allowed}%</td>"
                         f"<td style='text-align:center;padding:3px 6px;color:{ic};font-weight:bold;'>{diff_s}</td>"
                         f"<td style='padding:3px 6px;color:{ic};'>{crit}</td>"
                         "</tr>")
            html += "</table>"
        else:
            html += "<span style='color:#27AE60;'>✅ <b>Descuentos:</b> Todas las líneas dentro del tramo permitido.</span><br/>"

        # ── Portes (causa raíz) ───────────────────────────────────────────────
        portes = val.get('portes', {})
        if isinstance(portes, dict):
            ps = portes.get('status', 'OK')
            pa = portes.get('actual', 0.0)
            pe = portes.get('expected', 0.0)
            pm = portes.get('msg', '')

            # Análisis de causa
            carrier    = order_meta.get('carrier_name', '').lower()
            pricelist  = order_meta.get('pricelist_name', '')
            is_platino = 'platino' in pricelist.lower()
            is_recoge  = ('recoge' in carrier and 'cliente' in carrier)

            if ps == 'OK':
                html += f"<span style='color:#27AE60;'>✅ <b>Portes:</b> Correctos ({pa:.2f} €)</span><br/>"
            else:
                # Causa del warning
                causes = []
                if pa == 0 and not is_platino and not is_recoge:
                    causes.append("Sin línea de portes en el pedido")
                if pa > 0 and (is_platino or is_recoge):
                    causes.append(f"Portes cobrados ({pa:.2f}€) pero debería ser GRATIS")
                if abs(pa - pe) > 0.01 and pa != 0:
                    causes.append(f"Importe incorrecto: {pa:.2f}€ vs {pe:.2f}€ esperados")

                cause_html = "".join(f"<li>{c}</li>" for c in causes) if causes else f"<li>{pm}</li>"
                html += (f"<div style='background:#fff3e0;border-left:4px solid #f39c12;"
                         f"padding:5px 10px;border-radius:4px;margin:4px 0;'>"
                         f"<b>📦 Portes con disonancia</b><br/>"
                         f"Actual: <b>{pa:.2f}€</b> &nbsp;→&nbsp; Esperado: <b>{pe:.2f}€</b><br/>"
                         f"<i style='color:#888;'>{pm}</i><br/>"
                         f"<ul style='margin:4px 0 0 12px;padding:0;color:#c0392b;font-size:11px;'>{cause_html}</ul>"
                         f"</div>")

        # ── Gestión ──
        mgmt = val.get('management', {})
        if isinstance(mgmt, dict) and mgmt.get('status') not in ('OK', None, ''):
            html += (f"<div style='background:#fdecea;border-left:4px solid #dc3545;"
                     f"padding:5px 10px;border-radius:4px;margin:4px 0;'>"
                     f"<b>👤 Error de Gestión:</b> {mgmt.get('msg','–')}</div>")

        # ── Veredicto final ──────────────────────────────────────────────────
        verdicts = []
        if val.get('portes', {}).get('status') == 'Dissonancia':
            verdicts.append(("#e74c3c", "🚚 Corregir línea de portes o asignar tarifa correcta"))
        for dl in val.get('discounts', {}).get('lines', []):
            if not dl.get('aviso'):
                verdicts.append(("#e74c3c", f"💸 Descuento excedido en: {dl.get('product','?')}"))
        mgmt2 = val.get('management', {})
        if isinstance(mgmt2, dict) and mgmt2.get('status') not in ('OK', None, ''):
            verdicts.append(("#e74c3c", f"👤 {mgmt2.get('msg','Error de gestión')}"))
        if not verdicts:
            verdicts.append(("#27ae60", "✅ Pedido sin incidencias comerciales"))

        html += "<div style='margin-top:8px;padding:6px 10px;background:#f8f9fa;border-radius:6px;border:1px solid #dee2e6;'>"
        html += "<b style='font-size:12px;'>🔎 Veredicto</b><br/>"
        for vc, vt in verdicts:
            html += f"<span style='color:{vc};font-size:11px;'>▶ {vt}</span><br/>"
        html += "</div>"

        notes = val.get('notes', '')
        if notes:
            html += f"<p style='color:#777;font-size:11px;margin:4px 0;'><i>{notes}</i></p>"

        html += "</div>"
        return html


    def _confirm_autofix_portes(self, so_id: str, expected_portes: float, actual_portes: float):
        """Muestra un diálogo de confirmación antes de enviar la corrección de portes a Odoo."""
        reply = QMessageBox.question(
            self,
            "Confirmar Auto-Fix de Portes",
            f"⚠️  Se modificará el pedido <b>{so_id}</b> en Odoo:\n\n"
            f"   Portes actuales:    <b>{actual_portes:.2f} €</b>\n"
            f"   Portes correctos:  <b>{expected_portes:.2f} €</b>\n\n"
            f"¿Confirmar el cambio?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.execute_order_action(
                "autofix_portes",
                [int(so_id)],
                extra_data={'expected_portes': expected_portes}
            )

    def _open_odoo_chatter(self, so_id: str):
        """Abre el navegador en el formulario del pedido en Odoo (chatter/historial)."""
        base_url = str(getattr(getattr(self.service, 'odoo', None), 'url', '') or '').strip().rstrip('/')
        if not base_url:
            QMessageBox.warning(self, "Sin URL", "No se pudo obtener la URL de Odoo configurada.")
            return
        url = f"{base_url}/web#id={so_id}&model=sale.order&view_type=form"
        QDesktopServices.openUrl(QUrl(url))
        logger.info(f"Abriendo chatter de pedido {so_id} en Odoo: {url}")

    def _assign_segment_action(self):
        """Asigna el segmento seleccionado al partner del pedido y revalida (BUG-002)."""
        partner_id = self._current_detail_partner_id
        so_id = self._current_detail_so_id

        if not partner_id or not so_id:
            QMessageBox.warning(
                self, "Sin datos",
                "No se pudo determinar el cliente del pedido. "
                "Haz clic de nuevo en la fila del pedido bloqueado."
            )
            return

        category_name = self.cmb_segment_assign.currentData()  # text exacto del campo odoo_tipo_cliente
        if not category_name:
            QMessageBox.warning(self, "Sin selección", "Por favor selecciona un tipo de cliente.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirmar asignación de segmento",
            f"<b>¿Asignar el tipo de cliente?</b><br/><br/>"
            f"Tipo seleccionado: <b>{category_name}</b><br/>"
            f"Se escribirá en Odoo sobre el partner id={partner_id} "
            f"y se añadirá una nota en el pedido SO id={so_id}.<br/><br/>"
            f"<i>Después de guardar, pulsa 'Actualizar Ahora' para revalidar el pedido.</i>",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        self.btn_assign_segment.setEnabled(False)
        self.btn_assign_segment.setText("⏳ Guardando...")

        self._assign_worker = AssignSegmentWorker(
            self.service, partner_id, category_name, so_id
        )
        self._assign_worker.finished_signal.connect(self._on_assign_segment_finished)
        self._assign_worker.start()

    def _on_assign_segment_finished(self, success: bool, message: str):
        """Callback del worker de asignación de segmento."""
        self.btn_assign_segment.setEnabled(True)
        self.btn_assign_segment.setText("💾 Guardar y Revalidar")
        self.assign_panel.setVisible(False)
        if success:
            QMessageBox.information(
                self, "✅ Segmento Asignado",
                f"{message}\n\nEl validador se actualizará automáticamente."
            )
            self.load_data()  # revalidar tabla completa
        else:
            QMessageBox.critical(
                self, "Error al asignar",
                f"No se pudo asignar el segmento en Odoo:\n{message}"
            )

    def _on_error(self, message):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("↻ Actualizar Ahora")
        logger.error(f"Error cargando validador: {message}")
        QMessageBox.warning(self, "Error", f"No se pudo actualizar el validador:\n{message}")

    def execute_mass_action(self, action: str):
        selected_ids = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() == Qt.Checked:
                selected_ids.append(chk.data(Qt.UserRole))
                
        if not selected_ids:
            QMessageBox.information(self, "Sin Selección", "No has seleccionado ningún pedido.")
            return
            
        self.execute_order_action(action, selected_ids)

    def execute_order_action(self, action: str, so_ids: list, extra_data: dict = None):
        reason = ""
        if action == "devolver":
            reason, ok = QInputDialog.getText(self, "Devolver Pedido", f"Razón para devolver los pedidos {so_ids}:")
            if not ok or not reason.strip():
                return
                
        self.action_worker = OrderActionWorker(self.service, action, so_ids, reason, extra_data)
        self.action_worker.finished_signal.connect(self._on_action_finished)
        self.action_worker.start()
        
    def _on_action_finished(self, success: bool, message: str):
        if success:
            QMessageBox.information(self, "Éxito", message)
            self.load_data()
        else:
            QMessageBox.warning(self, "Error", f"Fallo al ejecutar la acción:\n{message}")
