from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QLineEdit, QSizePolicy,
    QTabWidget, QComboBox, QFormLayout, QGroupBox, QDoubleSpinBox,
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QBrush
import pandas as pd
import os
import json
from loguru import logger
import bur2000_theme
from db.services.commercial_conditions_service import (
    SEGMENT_COLORS, DEFAULT_SEGMENT_COLOR,
    COL_SEGMENTO, COL_FAMILIA, COL_TRAMO, COL_DTO_TER, COL_DTO_BAL, COL_CONDICION,
)

class CommercialConditionsWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, service):
        super().__init__()
        self.service = service

    def run(self):
        try:
            records = self.service.get_proposal_data()
            self.finished.emit(records)
        except Exception as e:
            self.error.emit(str(e))

class SimLoadOrderWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, service, order_ref):
        super().__init__()
        self.service = service
        self.order_ref = order_ref
        
    def run(self):
        try:
            if not self.service:
                self.error.emit("Validator Service not injected")
                return
            self.service.odoo._ensure_connected()
            SO = self.service.odoo.odoo.env['sale.order']
            domain = [('name', 'ilike', self.order_ref)] if self.order_ref.startswith('S') else [('name', 'ilike', f'%{self.order_ref}%')]
            so_recs = SO.search_read(domain, ['id', 'name', 'partner_id', 'amount_untaxed', 'partner_shipping_id'], limit=1)
            
            if not so_recs:
                self.error.emit("Pedido no encontrado en Odoo.")
                return
                
            so = so_recs[0]
            # Extraer segmento y datos
            eval_data = self.service.evaluar_cliente(so['partner_id'][0])
            report = self.service.validate_order(so['id'])
            
            result = {
                'id': so['id'],
                'name': so['name'],
                'amount': so['amount_untaxed'],
                'zone': 'Baleares' if 'Baleares' in str(so.get('partner_shipping_id', '')) else 'Península',
                'segmento': eval_data.get('calificacion', 'C'),
                'report': report
            }
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class CommercialConditionsTab(QWidget):
    """
    Tab specifically for viewing the 2026 Commercial Discount Proposals.
    Muestra los rangos de descuentos por segmento, familia y tramo de base imponible.
    """
    def __init__(self, service=None, validator_service=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.validator_service = validator_service
        self.full_data = pd.DataFrame()
        self._build_ui()
        self.load_data()

    def _build_ui(self):
        main_lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        main_lay.addWidget(self.tabs)

        from ui.tabs.commercial_validator_tab import CommercialValidatorTab
        if self.validator_service:
            self.validator_tab = CommercialValidatorTab(service=self.validator_service)
        else:
            self.validator_tab = QWidget()

        # ====== TAB 1: Matriz de Descuentos ======
        tab_matriz = QWidget()
        lay = QVBoxLayout(tab_matriz)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(15)

        # ── Header ────────────────────────────────────────────────────────
        header = QHBoxLayout()
        title_lbl = QLabel("📈 Condiciones Comerciales 2026 — Tabla Maestra")
        title_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        header.addWidget(title_lbl)
        header.addStretch()

        # Filtro Segmento
        self.filter_seg = QComboBox()
        self.filter_seg.setMinimumWidth(220)
        self.filter_seg.addItem("Todos los Segmentos")
        self.filter_seg.currentIndexChanged.connect(lambda _: self._apply_filters())
        header.addWidget(QLabel("Segmento:"))
        header.addWidget(self.filter_seg)

        # Filtro Familia
        self.filter_fam = QComboBox()
        self.filter_fam.setMinimumWidth(200)
        self.filter_fam.addItem("Todas las Familias")
        self.filter_fam.currentIndexChanged.connect(lambda _: self._apply_filters())
        header.addWidget(QLabel("Familia:"))
        header.addWidget(self.filter_fam)

        # Buscar texto libre
        self.filter_txt = QLineEdit()
        self.filter_txt.setPlaceholderText("🔍 Buscar...")
        self.filter_txt.setMaximumWidth(160)
        self.filter_txt.textChanged.connect(lambda _: self._apply_filters())
        header.addWidget(self.filter_txt)

        self.btn_refresh = QPushButton("🔄 Actualizar")
        self.btn_refresh.setStyleSheet(bur2000_theme.BUR.button_secondary)
        self.btn_refresh.setFixedWidth(120)
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.clicked.connect(self.load_data)
        header.addWidget(self.btn_refresh)

        self.btn_import = QPushButton("📥 Importar Excel")
        self.btn_import.setStyleSheet(
            "background-color: #1565C0; color: white; border-radius: 6px; font-weight: bold; padding: 0 8px;"
        )
        self.btn_import.setFixedWidth(140)
        self.btn_import.setFixedHeight(34)
        self.btn_import.clicked.connect(self._import_from_excel)
        header.addWidget(self.btn_import)

        lay.addLayout(header)

        # ── Leyenda de colores de segmentos ───────────────────────────────
        legend_lay = QHBoxLayout()
        legend_lay.setSpacing(6)
        lbl_legend = QLabel("Segmentos:")
        lbl_legend.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        legend_lay.addWidget(lbl_legend)
        for seg_name, color in SEGMENT_COLORS.items():
            chip = QLabel(f"  {seg_name.split('(')[0].strip()}  ")
            chip.setStyleSheet(
                f"background: {color}; border: 1px solid #ccc; border-radius: 4px;"
                f" font-size: 10px; padding: 2px 4px;"
            )
            legend_lay.addWidget(chip)
        legend_lay.addStretch()
        lay.addLayout(legend_lay)

        # ── KPI Cards ─────────────────────────────────────────────────────
        cards_lay = QHBoxLayout()
        self.card_total    = self._make_kpi("Tramos Totales",  "0", "#E1F5FE", "#0288D1")
        self.card_segments = self._make_kpi("Segmentos",       "0", "#E8F5E9", "#2E7D32")
        self.card_families = self._make_kpi("Familias Producto","0", "#FFF3E0", "#E65100")
        cards_lay.addWidget(self.card_total[0])
        cards_lay.addWidget(self.card_segments[0])
        cards_lay.addWidget(self.card_families[0])
        lay.addLayout(cards_lay)

        # ── Tabla ─────────────────────────────────────────────────────────
        self.table = QTableWidget()
        cols = [
            "Segmento",
            "Familia",
            "Tramo facturación",
            "DTO Territorial (%)",
            "DTO Baleares (%)",
            "Condición mínima",
        ]
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(False)   # Colores propios por segmento
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {bur2000_theme.BUR.border};
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }}
            QHeaderView::section {{
                background-color: #1A237E;
                color: white;
                padding: 7px 6px;
                border: none;
                border-right: 1px solid #3949AB;
                font-weight: bold;
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid #f0f0f0;
            }}
            QTableWidget::item:selected {{
                background-color: #90CAF9;
                color: #000;
            }}
        """)
        lay.addWidget(self.table)
        
        # ====== TAB 2: Simulador de Pedidos ======
        tab_simulador = QWidget()
        self._build_sim_tab(tab_simulador)
        
        # Add tabs (REORDERED AS REQUESTED)
        self.tabs.addTab(self.validator_tab, "✅ Validador")
        self.tabs.addTab(tab_simulador, "🛒 Simulador Pedido")
        self.tabs.addTab(tab_matriz, "📊 Matriz Base")

    def _build_sim_tab(self, parent_widget):
        lay = QVBoxLayout(parent_widget)
        lay.setContentsMargins(30, 30, 30, 30)

        header = QLabel("Calculadora de Condiciones por Pedido")
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        lay.addWidget(header)
        
        # Real Order Loader
        real_order_group = QGroupBox("🚀 Cargar de un Pedido Real Odoo para Simular")
        real_lay = QHBoxLayout(real_order_group)
        self.txt_sim_so = QLineEdit()
        self.txt_sim_so.setPlaceholderText("Ej: SO23019")
        real_lay.addWidget(self.txt_sim_so)
        btn_sim_load = QPushButton("⬇️ Obtener y Simular desde ERP")
        btn_sim_load.setStyleSheet("background-color: #6f42c1; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px;")
        btn_sim_load.clicked.connect(self._load_real_order)
        real_lay.addWidget(btn_sim_load)
        lay.addWidget(real_order_group)
        
        form_group = QGroupBox("Datos del Nuevo Pedido / Simulador Manual")
        form_lay = QFormLayout(form_group)
        
        self.sim_segmento = QComboBox()
        self.sim_familia = QComboBox()
        self.sim_base = QDoubleSpinBox()
        self.sim_base.setRange(0, 9999999)
        self.sim_base.setPrefix("€ ")
        self.sim_base.setDecimals(2)
        
        self.sim_zona = QComboBox()
        self.sim_zona.addItems(["Península", "Baleares/Canarias/Intl"])
        
        form_lay.addRow("Segmento Cliente:", self.sim_segmento)
        form_lay.addRow("Familia de Producto:", self.sim_familia)
        form_lay.addRow("Base Imponible del Pedido:", self.sim_base)
        form_lay.addRow("Zona de Envío:", self.sim_zona)
        
        lay.addWidget(form_group)
        
        btn_calc = QPushButton("⚖️ Calcular Condiciones a Aplicar")
        btn_calc.setStyleSheet(bur2000_theme.BUR.button_primary)
        btn_calc.setFixedHeight(40)
        btn_calc.clicked.connect(self._calculate_conditions)
        lay.addWidget(btn_calc)
        
        self.sim_results = QLabel("Introduce los datos y pulsa Calcular...")
        self.sim_results.setStyleSheet(f"background: white; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 8px; padding: 20px; font-size: 14px;")
        self.sim_results.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.sim_results.setWordWrap(True)
        lay.addWidget(self.sim_results)
        
        lay.addStretch()

    def _load_real_order(self):
        ref = self.txt_sim_so.text().strip()
        if not ref:
            QMessageBox.warning(self, "Aviso", "Por favor ingresa una Referencia de Pedido (ej: SO12345)")
            return
            
        if hasattr(self, 'btn_refresh'):
            self.btn_refresh.setEnabled(False)
        self.sim_results.setText("<i>Obteniendo datos de Odoo y procesando validador comercial...</i>")
        
        self.sim_worker = SimLoadOrderWorker(self.validator_service, ref)
        self.sim_worker.finished.connect(self._on_real_order_loaded)
        self.sim_worker.error.connect(self._on_real_order_error)
        self.sim_worker.start()

    def _on_real_order_loaded(self, result: dict):
        if hasattr(self, 'btn_refresh'):
            self.btn_refresh.setEnabled(True)

        # Auto-fill manual inputs with extracted data if possible
        idx_seg = self.sim_segmento.findText(result.get('segmento', ''))
        if idx_seg >= 0: self.sim_segmento.setCurrentIndex(idx_seg)
        self.sim_base.setValue(result.get('amount', 0))
        if 'Baleares' in result.get('zone', ''):
            self.sim_zona.setCurrentIndex(1)
        else:
            self.sim_zona.setCurrentIndex(0)
            
        report = result.get('report', {})
        status = report.get('status', '??')
        
        _status_colors = {
            'OK':       ('#27AE60', '✅'),
            'BLOQUEADO':('#dc3545', '🚫'),
            'WARNING':  ('#f39c12', '⚠️'),
            'REVISION': ('#6f42c1', '🔍'),
            'ESPECIAL': ('#17a2b8', '⭐'),
            'ERROR':    ('#dc3545', '❌'),
        }
        color, icon = _status_colors.get(status, ('#888', '?'))
        
        homo = report.get('homologacion', {})
        segmento_homo = homo.get('segmento_aplicacion', result.get('segmento', '–'))
        tipo_odoo     = homo.get('odoo_tipo_cliente', '–')
        homo_msg      = homo.get('mensaje', '')

        # BUG-004: Detectar si el bloqueo es por segmento vacío
        segmento_missing = status in ('ERROR', 'REVISION', 'BLOQUEADO') and \
            (not segmento_homo or segmento_homo in ('–', '-', 'None', ''))

        html = f"""
        <div style='font-family: Arial, sans-serif; font-size: 13px;'>
          <div style='background: {color}18; border-left: 6px solid {color};
               padding: 12px 18px; border-radius: 6px; margin-bottom: 14px;'>
            <span style='font-size: 20px; font-weight: bold; color: {color};'>
              {icon} {result['name']}  —  {status}
            </span><br/>
            <span style='color: #444;'>
              Importe: <b>{result['amount']:.2f} €</b> &nbsp;|&nbsp;
              Segmento Homologado: <b>{segmento_homo}</b> &nbsp;|&nbsp;
              Tipo Odoo: <b>{tipo_odoo}</b>
            </span>
          </div>
        """
        
        # ── Sección de Homologación ─────────────────────────────
        # BUG-004: Bloque de ayuda contextual cuando falta el segmento
        if segmento_missing:
            so_id_val = result.get('id', '')
            odoo_url = ''
            if self.validator_service:
                base = str(getattr(getattr(self.validator_service, 'odoo', None), 'url', '') or '').rstrip('/')
                if base and so_id_val:
                    odoo_url = f"{base}/web#id={so_id_val}&model=sale.order&view_type=form"
            odoo_link = (
                f"<a href='{odoo_url}' style='color:#1565C0; font-weight:bold;'>"
                f"🔗 Abrir pedido en Odoo y asignar Tipo de Cliente</a>"
                if odoo_url else ""
            )
            html += (
                "<div style='background:#fff3e0; border: 2px solid #f57f17; "
                "border-radius: 8px; padding: 14px 18px; margin-bottom: 14px;'>"
                "<p style='margin:0 0 8px 0; font-size:14px; color:#bf360c;'>"
                "<b>❓ ¿Por qué está bloqueado?</b></p>"
                "<p style='margin:0 0 6px 0; color:#5d4037;'>"
                "El cliente de este pedido <b>no tiene asignado un Tipo de Cliente</b> "
                "(<code>category_id</code>) en Odoo. Sin esta etiqueta, el motor de "
                "validación no puede determinar el segmento tarifario y bloquea el pedido.</p>"
                "<p style='margin:0 0 6px 0; color:#5d4037;'><b>🛠️ Cómo resolverlo:</b></p>"
                "<ol style='margin:0 0 8px 16px; color:#5d4037;'>"
                "<li>Abre el pedido en Odoo con el enlace de abajo.</li>"
                "<li>Haz clic en el nombre del cliente para ir a su ficha.</li>"
                "<li>En la pestaña <b>Ventas &amp; Compras</b>, asigna el <b>Tipo de cliente</b> correcto.</li>"
                "<li>Vuelve aquí y pulsa <b>➡️ Obtener y Simular</b> de nuevo.</li>"
                "</ol>"
                f"<p style='margin:0;'>{odoo_link}</p>"
                "</div>"
            )
        elif homo_msg:
            html += f"<p style='color:#555; margin: 4px 0 10px 0;'><i>🏷️ {homo_msg}</i></p>"

        
        # ── Sección de Descuentos (criterios explicados) ────────
        discounts_block = report.get('discounts', {})
        d_lines = discounts_block.get('lines', []) if isinstance(discounts_block, dict) else []
        
        if d_lines:
            html += "<b>💸 Descuentos por línea:</b>"
            html += ("<table style='width:100%; border-collapse: collapse; margin: 8px 0 14px 0; "
                     "font-size: 12px;'>")
            html += ("<tr style='background:#f0f0f0;'>"
                     "<th style='text-align:left; padding:5px 8px;'>Producto</th>"
                     "<th style='text-align:center; padding:5px 8px;'>% Aplicado</th>"
                     "<th style='text-align:center; padding:5px 8px;'>% Permitido</th>"
                     "<th style='text-align:center; padding:5px 8px;'>Diferencia</th>"
                     "<th style='text-align:left; padding:5px 8px;'>Criterio</th>"
                     "</tr>")
            for ln in d_lines:
                prod    = ln.get('product', '?')
                applied = ln.get('applied', '?')
                allowed = ln.get('allowed', '?')
                diff    = ln.get('diff', 0)
                aviso   = ln.get('aviso', False)
                next_m  = ln.get('next_max')
                
                if aviso:
                    row_color = '#fff3cd'
                    diff_str  = f"+{diff:.1f}%" if isinstance(diff, (int, float)) else '–'
                    criterio  = f"⚠️ En zona de escalado. Siguiente tramo máx: {next_m}%" if next_m else "⚠️ Zona de escalado"
                    icon_col  = '#f39c12'
                else:
                    row_color = '#fdecea'
                    diff_str  = f"+{diff:.1f}%" if isinstance(diff, (int, float)) else '–'
                    criterio  = "❌ Supera el máximo permitido para este tramo/segmento"
                    icon_col  = '#dc3545'
                
                html += (f"<tr style='background:{row_color}; border-bottom: 1px solid #eee;'>"
                         f"<td style='padding:5px 8px;'>{prod}</td>"
                         f"<td style='text-align:center; padding:5px 8px; font-weight:bold;'>{applied}%</td>"
                         f"<td style='text-align:center; padding:5px 8px;'>{allowed}%</td>"
                         f"<td style='text-align:center; padding:5px 8px; color:{icon_col}; font-weight:bold;'>{diff_str}</td>"
                         f"<td style='padding:5px 8px; color:{icon_col};'>{criterio}</td>"
                         "</tr>")
            html += "</table>"
        else:
            html += "<p style='color:#27AE60;'>✅ <b>Descuentos:</b> Todas las líneas dentro del tramo permitido.</p>"
        
        # ── Sección de Portes ───────────────────────────────────
        portes_block = report.get('portes', {})
        if isinstance(portes_block, dict):
            p_status  = portes_block.get('status', 'OK')
            p_actual  = portes_block.get('actual', 0.0)
            p_expect  = portes_block.get('expected', 0.0)
            p_msg     = portes_block.get('msg', '')
            if p_status == 'OK':
                html += f"<p style='color:#27AE60;'>✅ <b>Portes:</b> Correctos ({p_actual:.2f} €)</p>"
            else:
                html += (f"<div style='background:#fff3e0; border-left:4px solid #f39c12; "
                         f"padding:8px 12px; border-radius:4px; margin-bottom:10px;'>"
                         f"<b>📦 Portes con disonancia</b><br/>"
                         f"Actual: <b>{p_actual:.2f} €</b> &nbsp;→&nbsp; Esperado según tabla: <b>{p_expect:.2f} €</b><br/>"
                         f"<i style='color:#888;'>{p_msg}</i>"
                         f"</div>")
        
        # ── Sección de Gestión ──────────────────────────────────
        mgmt_block = report.get('management', {})
        if isinstance(mgmt_block, dict) and mgmt_block.get('status') != 'OK':
            html += (f"<div style='background:#fdecea; border-left:4px solid #dc3545; "
                     f"padding:8px 12px; border-radius:4px; margin-bottom:10px;'>"
                     f"<b>👤 Error de Gestión:</b> {mgmt_block.get('msg', '–')}"
                     f"</div>")
        
        # ── Notas adicionales ───────────────────────────────────
        notes = report.get('notes', '')
        if notes:
            html += f"<p style='color:#777; font-size:11px;'><i>{notes}</i></p>"
        
        html += "</div>"
        self.sim_results.setText(html)
        
    def _on_real_order_error(self, err: str):
        if hasattr(self, 'btn_refresh'):
            self.btn_refresh.setEnabled(True)
        self.sim_results.setText(f"<b style='color:red;'>Error Simulador ERP:</b> {err}")

    def _make_kpi(self, title, val, bg, fg):
        f = QFrame()
        f.setStyleSheet(f"background: {bg}; border-radius: 8px; border-left: 6px solid {fg};")
        f.setFixedHeight(80)
        l = QVBoxLayout(f)
        l.setContentsMargins(20, 10, 20, 10)
        
        lbl_v = QLabel(val)
        lbl_v.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {fg};")
        
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"font-size: 11px; color: {fg}; text-transform: uppercase; font-weight: 800;")
        
        l.addWidget(lbl_v)
        l.addWidget(lbl_t)
        return f, lbl_v

    def load_data(self):
        if not self.service:
            logger.error("No service provided to CommercialConditionsTab")
            return

        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳ Cargando...")

        self.worker = CommercialConditionsWorker(self.service)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_data_error)
        self.worker.start()

    def _on_data_loaded(self, records):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 Actualizar")

        if not records:
            logger.warning("No data returned from CommercialConditionsService")
            return

        df = pd.DataFrame(records)
        self.full_data = df
        self._display_data(df)

        # KPIs
        self.card_total[1].setText(str(len(df)))
        seg_col = COL_SEGMENTO if COL_SEGMENTO in df.columns else 'Segmento'
        fam_col = COL_FAMILIA  if COL_FAMILIA  in df.columns else 'Familia'
        self.card_segments[1].setText(str(df[seg_col].nunique()) if seg_col in df.columns else "0")
        self.card_families[1].setText(str(df[fam_col].nunique()) if fam_col in df.columns else "0")

        # Combos Simulador + Filtros
        self.sim_segmento.clear()
        self.sim_familia.clear()
        self.filter_seg.blockSignals(True)
        self.filter_seg.clear()
        self.filter_seg.addItem("Todos los Segmentos")
        self.filter_fam.blockSignals(True)
        self.filter_fam.clear()
        self.filter_fam.addItem("Todas las Familias")

        if seg_col in df.columns:
            segments = sorted(df[seg_col].dropna().unique().tolist())
            self.sim_segmento.addItems([str(s) for s in segments])
            self.filter_seg.addItems([str(s) for s in segments])
        if fam_col in df.columns:
            families = sorted(df[fam_col].dropna().unique().tolist())
            self.sim_familia.addItems([str(f) for f in families])
            self.filter_fam.addItems([str(f) for f in families])

        self.filter_seg.blockSignals(False)
        self.filter_fam.blockSignals(False)

    def _on_data_error(self, err_msg):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 Actualizar")
        logger.error(f"Error cargando propuesta 2026: {err_msg}")

    def _display_data(self, df: pd.DataFrame):
        """Rellena la tabla con colores por segmento, igual al Excel original."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for _, row in df.iterrows():
            r_idx = self.table.rowCount()
            self.table.insertRow(r_idx)

            seg   = str(row.get(COL_SEGMENTO, "") or "")
            fam   = str(row.get(COL_FAMILIA,  "") or "")
            tramo = row.get(COL_TRAMO, "")
            dto_t = row.get(COL_DTO_TER, "")
            dto_b = row.get(COL_DTO_BAL, "")
            cond  = str(row.get(COL_CONDICION, "") or "")

            # Formato tramo
            if tramo is None or (isinstance(tramo, float) and pd.isna(tramo)):
                tramo_str = ""
            elif isinstance(tramo, (int, float)):
                tramo_str = f"{int(tramo):,} €".replace(",", ".")
            else:
                tramo_str = str(tramo)

            # Formato DTO
            def fmt_dto(v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return "—"  # sin aplica
                try:
                    return f"{float(v):.0f} %"
                except (ValueError, TypeError):
                    return str(v)

            values = [seg, fam, tramo_str, fmt_dto(dto_t), fmt_dto(dto_b), cond]

            # Color de fondo por segmento (igual al Excel)
            bg_hex = SEGMENT_COLORS.get(seg, DEFAULT_SEGMENT_COLOR)
            bg_color = QColor(bg_hex)

            for col_i, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setBackground(QBrush(bg_color))
                # Centrar columnas numéricas
                if col_i in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignCenter)
                # Negrita en DTO Territorial (la columna clave)
                if col_i == 3:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                # Guardar dict original como UserRole para filtros seguros
                if col_i == 0:
                    item.setData(Qt.UserRole, dict(row))
                self.table.setItem(r_idx, col_i, item)

        self.table.setSortingEnabled(True)

    def _apply_filters(self):
        seg  = self.filter_seg.currentText()
        fam  = self.filter_fam.currentText()
        txt  = self.filter_txt.text().strip().lower() if hasattr(self, 'filter_txt') else ""

        for r in range(self.table.rowCount()):
            # Usar UserRole si está disponible (más robusto con sorting)
            item0 = self.table.item(r, 0)
            item1 = self.table.item(r, 1)
            v_seg = item0.text() if item0 else ""
            v_fam = item1.text() if item1 else ""

            show = True
            if seg != "Todos los Segmentos" and v_seg != seg:
                show = False
            if fam != "Todas las Familias" and v_fam != fam:
                show = False
            if txt:
                row_text = " ".join(
                    self.table.item(r, c).text() if self.table.item(r, c) else ""
                    for c in range(self.table.columnCount())
                ).lower()
                if txt not in row_text:
                    show = False

            self.table.setRowHidden(r, not show)

    def _import_from_excel(self):
        """
        FR-003: Importa un nuevo Excel maestro de condiciones comerciales con PREVIEW DIFF.
        Muestra filas nuevas (verde), modificadas (amarillo), eliminadas (rojo) y sin cambio
        antes de confirmar. Escribe un log de importación en condiciones_import_log.json.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Excel de Condiciones Comerciales 2026",
            os.path.dirname(self.service.excel_path) if self.service else "",
            "Excel (*.xlsx *.xls)",
        )
        if not path:
            return

        # ── 1. Leer el Excel nuevo con el servicio ───────────────────────────
        try:
            import copy
            old_path = self.service.excel_path
            # Leer datos actuales (antes de importar)
            current_records = self.service.get_proposal_data() or []

            # Leer datos del nuevo Excel sin tocar el servicio aún
            tmp_service = type(self.service)(excel_path=path)
            new_records = tmp_service._read_excel_condiciones()
            if not new_records:
                QMessageBox.critical(
                    self, "Error al leer Excel",
                    f"No se encontraron datos en:\n{path}\n\n"
                    "Verifica que la hoja se llame exactamente:\n"
                    "'Condiciones de dtos Enero 2026'\ny que las cabeceras estén en la fila 17."
                )
                return
        except Exception as e:
            QMessageBox.critical(self, "Error al leer Excel", str(e))
            return

        # ── 2. Calcular diff (PK = Segmento + Familia + Tramo) ───────────────
        from db.services.commercial_conditions_service import (
            COL_SEGMENTO, COL_FAMILIA, COL_TRAMO, COL_DTO_TER, COL_DTO_BAL, COL_CONDICION
        )

        def _pk(r):
            return (
                str(r.get(COL_SEGMENTO, '')).strip(),
                str(r.get(COL_FAMILIA, '')).strip(),
                str(r.get(COL_TRAMO, '')).strip(),
            )

        current_map = {_pk(r): r for r in current_records}
        new_map     = {_pk(r): r for r in new_records}

        diff_rows = []   # (tipo, pk, old_row, new_row)
        for pk, new_r in new_map.items():
            if pk not in current_map:
                diff_rows.append(('NUEVO', pk, None, new_r))
            else:
                old_r = current_map[pk]
                changed = any(
                    str(old_r.get(c, '')) != str(new_r.get(c, ''))
                    for c in [COL_DTO_TER, COL_DTO_BAL, COL_CONDICION]
                )
                if changed:
                    diff_rows.append(('MODIFICADO', pk, old_r, new_r))
                else:
                    diff_rows.append(('SIN_CAMBIO', pk, old_r, new_r))

        for pk, old_r in current_map.items():
            if pk not in new_map:
                diff_rows.append(('ELIMINADO', pk, old_r, None))

        n_new  = sum(1 for t, *_ in diff_rows if t == 'NUEVO')
        n_mod  = sum(1 for t, *_ in diff_rows if t == 'MODIFICADO')
        n_del  = sum(1 for t, *_ in diff_rows if t == 'ELIMINADO')
        n_ok   = sum(1 for t, *_ in diff_rows if t == 'SIN_CAMBIO')

        # ── 3. Diálogo de Preview ────────────────────────────────────────────
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox, QFrame
        )
        from PySide6.QtGui import QColor, QBrush

        dlg = QDialog(self)
        dlg.setWindowTitle("📥 Preview — Importación de Condiciones 2026")
        dlg.setMinimumSize(900, 560)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Resumen en cabecera
        summary_lbl = QLabel(
            f"<b>Excel nuevo:</b> <code>{os.path.basename(path)}</code>"
            f"&nbsp;&nbsp;|&nbsp;&nbsp;"
            f"<span style='color:#27AE60;'>+{n_new} nuevas</span>"
            f"&nbsp;&nbsp;"
            f"<span style='color:#f39c12;'>~{n_mod} modificadas</span>"
            f"&nbsp;&nbsp;"
            f"<span style='color:#dc3545;'>−{n_del} eliminadas</span>"
            f"&nbsp;&nbsp;"
            f"<span style='color:#888;'>{n_ok} sin cambio</span>"
        )
        summary_lbl.setStyleSheet("font-size: 13px; padding: 6px;")
        lay.addWidget(summary_lbl)

        # Leyenda
        legend_lay = QHBoxLayout()
        for txt, clr in [("🟢 Nueva", "#d4edda"), ("🟡 Modificada", "#fff3cd"),
                          ("🔴 Eliminada", "#f8d7da"), ("⬜ Sin cambio", "#f0f0f0")]:
            chip = QLabel(f"  {txt}  ")
            chip.setStyleSheet(f"background:{clr}; border: 1px solid #ccc; border-radius: 4px; padding: 2px 6px;")
            legend_lay.addWidget(chip)
        legend_lay.addStretch()
        lay.addLayout(legend_lay)

        # Tabla diff
        diff_table = QTableWidget()
        diff_table.setColumnCount(7)
        diff_table.setHorizontalHeaderLabels([
            "Estado", "Segmento", "Familia", "Tramo",
            "DTO Terr. ANTES→DESPUÉS", "DTO Bal. ANTES→DESPUÉS", "Condición mínima"
        ])
        diff_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        diff_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        diff_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        diff_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        diff_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        diff_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        diff_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        diff_table.setEditTriggers(QTableWidget.NoEditTriggers)
        diff_table.setSelectionBehavior(QTableWidget.SelectRows)
        diff_table.verticalHeader().setVisible(False)
        diff_table.setSortingEnabled(True)
        diff_table.setStyleSheet("""
            QTableWidget { border: 1px solid #ddd; border-radius: 6px; }
            QHeaderView::section { background: #1A237E; color: white;
                padding: 6px; font-weight: bold; border: none; }
        """)

        _colors = {
            'NUEVO':     QColor('#d4edda'),
            'MODIFICADO': QColor('#fff3cd'),
            'ELIMINADO': QColor('#f8d7da'),
            'SIN_CAMBIO': QColor('#f5f5f5'),
        }
        _labels = {
            'NUEVO': '✚ Nueva', 'MODIFICADO': '~ Modificada',
            'ELIMINADO': '✖ Eliminada', 'SIN_CAMBIO': '= Sin cambio'
        }

        # Ordenar: primero cambios, luego sin cambio
        _order = {'NUEVO': 0, 'MODIFICADO': 1, 'ELIMINADO': 2, 'SIN_CAMBIO': 3}
        diff_rows.sort(key=lambda x: (_order.get(x[0], 9), x[1]))

        diff_table.setRowCount(len(diff_rows))
        for i, (tipo, pk, old_r, new_r) in enumerate(diff_rows):
            bg = QBrush(_colors.get(tipo, QColor('#ffffff')))
            row_data = new_r or old_r or {}
            old_dto_t = str(old_r.get(COL_DTO_TER, '–') or '–') if old_r else '–'
            new_dto_t = str(new_r.get(COL_DTO_TER, '–') or '–') if new_r else '–'
            old_dto_b = str(old_r.get(COL_DTO_BAL, '—') or '—') if old_r else '—'
            new_dto_b = str(new_r.get(COL_DTO_BAL, '—') or '—') if new_r else '—'

            dto_t_str = f"{old_dto_t} → {new_dto_t}" if tipo == 'MODIFICADO' else new_dto_t
            dto_b_str = f"{old_dto_b} → {new_dto_b}" if tipo == 'MODIFICADO' else new_dto_b

            cells = [
                _labels.get(tipo, tipo),
                str(row_data.get(COL_SEGMENTO, '')),
                str(row_data.get(COL_FAMILIA, '')),
                str(row_data.get(COL_TRAMO, '')),
                dto_t_str,
                dto_b_str,
                str(row_data.get(COL_CONDICION, '')),
            ]
            for j, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                it.setBackground(bg)
                if j == 0 and tipo == 'MODIFICADO':
                    it.setForeground(QBrush(QColor('#856404')))
                    font = it.font(); font.setBold(True); it.setFont(font)
                diff_table.setItem(i, j, it)

        lay.addWidget(diff_table)

        # Nota informativa si no hay cambios
        if n_new == 0 and n_mod == 0 and n_del == 0:
            info = QLabel("ℹ️ El Excel nuevo es idéntico al actual. No hay cambios que aplicar.")
            info.setStyleSheet("color: #555; font-style: italic; padding: 4px;")
            lay.addWidget(info)

        # Botones
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("✅ Confirmar Importación")
        btn_box.button(QDialogButtonBox.Cancel).setText("❌ Cancelar")
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(
            "background:#27AE60; color:white; font-weight:bold; padding:6px 16px; border-radius:4px;"
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        lay.addWidget(btn_box)

        if dlg.exec() != QDialog.Accepted:
            return

        # ── 4. Aplicar la importación ────────────────────────────────────────
        try:
            self.service.excel_path = path
            self.service.invalidate_cache()
            self.load_data()

            # ── 5. Log de importación ────────────────────────────────────────
            import datetime
            log_path = os.path.join(os.path.dirname(path), "condiciones_import_log.json")
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "usuario": "Gabriela",
                "archivo_origen": path,
                "resumen": {
                    "nuevas": n_new,
                    "modificadas": n_mod,
                    "eliminadas": n_del,
                    "sin_cambio": n_ok,
                    "total_nuevo": len(new_records),
                },
            }
            existing_log = []
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        existing_log = json.load(f)
                except Exception:
                    existing_log = []
            existing_log.insert(0, log_entry)
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(existing_log[:50], f, indent=2, ensure_ascii=False)

            logger.info(
                f"[FR-003] Importación confirmada: +{n_new} nuevas, ~{n_mod} modificadas, "
                f"-{n_del} eliminadas. Log: {log_path}"
            )
            QMessageBox.information(
                self, "✅ Importación completada",
                f"Se han importado correctamente las condiciones desde:\n{os.path.basename(path)}\n\n"
                f"  +{n_new} reglas nuevas\n"
                f"  ~{n_mod} reglas modificadas\n"
                f"  −{n_del} reglas eliminadas\n\n"
                f"Log guardado en: {log_path}"
            )
        except Exception as e:
            logger.error(f"[FR-003] Error al aplicar importación: {e}")
            QMessageBox.critical(self, "Error de importación", str(e))


    def _save_matrix_changes(self):
        """Guarda la vista actual de la tabla (solo visible) como override JSON."""
        records = []
        for r in range(self.table.rowCount()):
            if self.table.isRowHidden(r):
                continue
            item0 = self.table.item(r, 0)
            orig = item0.data(Qt.UserRole) if item0 else None
            if orig:
                records.append(orig)

        if not records:
            QMessageBox.warning(self, "Sin datos", "No hay filas visibles para guardar.")
            return

        if self.service and self.service.save_proposal_data(records):
            QMessageBox.information(self, "Guardado", "✅ La matriz comercial se ha guardado exitosamente.")
        else:
            QMessageBox.warning(self, "Error", "No se pudo guardar la matriz (revisa los logs)")

    def _calculate_conditions(self):
        """
        Simulador manual de condiciones comerciales.
        Usa las columnas reales del Excel 2026:
          - Segmento, Familia, Tramo facturaci\u00f3n
          - DTO Territorial (%), DTO Baleares (%)
          - Condici\u00f3n m\u00ednima (familias/referencias)
        """
        import math

        if self.full_data.empty:
            self.sim_results.setText(
                "<b style='color:#dc3545;'>\u26a0\ufe0f Datos no cargados.</b><br>"
                "Pulsa <b>\U0001f504 Actualizar</b> en la pesta\u00f1a Matriz para cargar el Excel."
            )
            return

        seg  = self.sim_segmento.currentText().strip()
        fam  = self.sim_familia.currentText().strip()
        base = self.sim_base.value()
        zona = self.sim_zona.currentText()
        es_baleares = "Baleares" in zona

        df = self.full_data

        # ── 1. Filtrar por Segmento + Familia ────────────────────────────────
        col_seg = COL_SEGMENTO
        col_fam = COL_FAMILIA
        col_tramo = COL_TRAMO
        col_ter   = COL_DTO_TER
        col_bal   = COL_DTO_BAL
        col_cond  = COL_CONDICION

        if col_seg not in df.columns or col_fam not in df.columns:
            self.sim_results.setText(
                "<b style='color:#dc3545;'>Error:</b> Columnas del Excel no encontradas.<br>"
                f"Esperadas: '{col_seg}', '{col_fam}'. Disponibles: {list(df.columns)[:6]}"
            )
            return

        match = df[
            (df[col_seg].astype(str).str.strip() == seg) &
            (df[col_fam].astype(str).str.strip() == fam)
        ]

        if match.empty:
            self.sim_results.setText(
                f"<b style='color:#dc3545;'>\u274c Sin reglas</b> para:<br>"
                f"&nbsp;&nbsp;Segmento: <b>{seg}</b><br>"
                f"&nbsp;&nbsp;Familia: <b>{fam}</b><br><br>"
                f"<span style='color:#888;'>Comprueba que el segmento y familia existen en la Matriz Base.</span>"
            )
            return

        # ── 2. Encontrar el tramo que aplica (mismo algoritmo que validate_range) ──
        def _parse_tramo_min(v):
            if v is None: return 0.0
            try: return float(v)
            except: return 0.0  # "< 1.000 \u20ac" -> tramo abierto por abajo = 0

        def _safe_float(v):
            if v is None: return None
            try:
                f = float(v)
                return None if math.isnan(f) else f
            except: return None

        # Ordenar candidatos por tramo desc (mayor tramo primero)
        match = match.copy()
        match['_tmin'] = match[col_tramo].apply(_parse_tramo_min)
        match = match.sort_values('_tmin', ascending=False)

        rule_row = None
        for _, r in match.iterrows():
            if base >= r['_tmin']:
                rule_row = r
                break

        if rule_row is None:
            self.sim_results.setText(
                f"<b style='color:#dc3545;'>\u274c Sin tramo aplicable</b> "
                f"para importe <b>{base:,.2f} \u20ac</b>.<br>"
                f"<span style='color:#888;'>El importe es inferior al tramo m\u00ednimo de esta familia.</span>"
            )
            return

        # ── 3. Extraer DTO ───────────────────────────────────────────────────
        dto_ter = _safe_float(rule_row.get(col_ter))
        dto_bal = _safe_float(rule_row.get(col_bal))
        condicion = str(rule_row.get(col_cond, '') or '').strip()
        tramo_val = rule_row.get(col_tramo, '')

        # Formato de tramo legible
        try:
            tramo_str = f"\u2265 {int(float(tramo_val)):,} \u20ac".replace(',', '.')
        except Exception:
            tramo_str = str(tramo_val)

        # DTO aplicable seg\u00fan zona
        if es_baleares:
            dto_aplicable = dto_bal if dto_bal is not None else dto_ter  # Axarqu\u00eda fallback
            dto_fuente    = "Baleares" if dto_bal is not None else "Territorial (fallback)"
        else:
            dto_aplicable = dto_ter
            dto_fuente    = "Territorial (Pen\u00ednsula)"

        # ── 4. Construir respuesta HTML ──────────────────────────────────────
        primary = getattr(bur2000_theme.BUR, 'primary', '#1A237E')
        success = getattr(bur2000_theme.BUR, 'success', '#27AE60')
        surface = getattr(bur2000_theme.BUR, 'surface', '#F8F9FA')
        warn_c  = '#f39c12'

        dto_str = f"{dto_aplicable:.0f}%" if dto_aplicable is not None else "No definido"
        dto_ter_str = f"{dto_ter:.0f}%" if dto_ter is not None else "\u2014"
        dto_bal_str = f"{dto_bal:.0f}%" if dto_bal is not None else "N/A (distribuidor peninsular)"

        color_dto = success if dto_aplicable is not None else warn_c

        html = f"""
        <div style='font-family: Arial, sans-serif; font-size: 13px;'>
          <div style='background: {primary}12; border-left: 6px solid {primary};
               padding: 12px 18px; border-radius: 6px; margin-bottom: 14px;'>
            <span style='font-size: 16px; font-weight: bold; color: {primary};'>
              \ud83d\udcca Condiciones para {seg}
            </span><br/>
            <span style='color: #555;'>
              Familia: <b>{fam}</b> &nbsp;|&nbsp;
              Tramo: <b>{tramo_str}</b> &nbsp;|&nbsp;
              Zona: <b>{zona}</b>
            </span>
          </div>

          <div style='background: {color_dto}15; border: 2px solid {color_dto};
               border-radius: 8px; padding: 16px 20px; margin-bottom: 14px; text-align: center;'>
            <div style='font-size: 13px; color: #555; margin-bottom: 4px;'>
              DTO M\u00c1XIMO PERMITIDO ({dto_fuente})
            </div>
            <div style='font-size: 32px; font-weight: bold; color: {color_dto};'>
              {dto_str}
            </div>
          </div>

          <table style='width:100%; border-collapse: collapse; font-size: 12px; margin-bottom: 12px;'>
            <tr style='background: #f5f5f5;'>
              <th style='text-align:left; padding: 6px 10px; border: 1px solid #ddd;'>Campo</th>
              <th style='text-align:left; padding: 6px 10px; border: 1px solid #ddd;'>Valor</th>
            </tr>
            <tr>
              <td style='padding: 6px 10px; border: 1px solid #ddd;'>Importe del pedido</td>
              <td style='padding: 6px 10px; border: 1px solid #ddd; font-weight: bold;'>{base:,.2f} \u20ac</td>
            </tr>
            <tr style='background: #fafafa;'>
              <td style='padding: 6px 10px; border: 1px solid #ddd;'>Tramo aplicado</td>
              <td style='padding: 6px 10px; border: 1px solid #ddd;'>{tramo_str}</td>
            </tr>
            <tr>
              <td style='padding: 6px 10px; border: 1px solid #ddd;'>DTO Territorial (Pen\u00ednsula)</td>
              <td style='padding: 6px 10px; border: 1px solid #ddd; font-weight: bold; color: {success};'>{dto_ter_str}</td>
            </tr>
            <tr style='background: #fafafa;'>
              <td style='padding: 6px 10px; border: 1px solid #ddd;'>DTO Baleares</td>
              <td style='padding: 6px 10px; border: 1px solid #ddd; font-weight: bold;'>{dto_bal_str}</td>
            </tr>
        """
        if condicion:
            html += f"""
            <tr>
              <td style='padding: 6px 10px; border: 1px solid #ddd;'>Condici\u00f3n m\u00ednima</td>
              <td style='padding: 6px 10px; border: 1px solid #ddd; color: #555;'>{condicion}</td>
            </tr>
            """
        html += "</table>"

        # Nota si Axarqu\u00eda usa fallback a Territorial en Baleares
        if es_baleares and dto_bal is None and dto_ter is not None:
            html += (
                "<div style='background:#fff3e0; border-left:4px solid #f57f17; "
                "padding: 8px 12px; border-radius: 4px; font-size: 12px; color: #bf360c;'>"
                "\u26a0\ufe0f Este segmento no tiene DTO Baleares definido. "
                "Se aplica el DTO Territorial como fallback (distribuidor peninsular exclusivo)."
                "</div>"
            )

        html += "</div>"
        self.sim_results.setText(html)
