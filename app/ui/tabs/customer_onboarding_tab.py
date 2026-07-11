from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFormLayout, QGroupBox, QMessageBox, QFrame, QProgressBar, 
    QFileDialog, QTabWidget, QCheckBox, QDialog, QDialogButtonBox, 
    QAbstractItemView, QSplitter, QScrollArea, QTextEdit,
    QComboBox
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread
from PySide6.QtGui import QFont, QColor
import json
import os
import urllib.request
import io
import csv
from datetime import datetime
from typing import Any
from db.services.customer_onboarding_service import CustomerOnboardingService
from db.services.commercial_service import CommercialService
from db.connection import get_conn
from bur2000_theme import BUR
from loguru import logger

# ── Configuración Centralizada ──────────────────────────────────────────────
class LeadsConfig:
    # URL del CSV de Google Forms (Solicitudes)
    # Se usa la versión unificada del antiguo web_leads_tab.py
    WEB_LEADS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ0E--igXeWWS_bf0Au_8j3mPOWlYCa_4_NCYB1PlC8349530-2L3gFMvQzfKARMT0M9AP3X0Ug3dYU/pub?gid=223267114&single=true&output=csv"
    
    # Archivo central de estados de leads (unificado)
    STATUS_FILE = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'db', 'leads_status.json')
    )

def _load_leads_status() -> dict:
    """Carga el estado de procesamiento desde un JSON local (unificado)."""
    if not os.path.exists(LeadsConfig.STATUS_FILE):
        return {}
    try:
        with open(LeadsConfig.STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Migración Robusta: Asegurar que todas las entradas usen el nuevo formato
            # El antiguo usaba 'estado': 'procesado', el nuevo 'status': 'alta'
            modified = False
            for k, v in data.items():
                if "estado" in v:
                    state = v.pop("estado")
                    v["status"] = "alta" if state == "procesado" else state
                    if "last_update" not in v:
                        v["last_update"] = datetime.now().isoformat()
                    modified = True
                elif "status" in v and v["status"] == "procesado":
                    v["status"] = "alta"
                    if "last_update" not in v:
                        v["last_update"] = datetime.now().isoformat()
                    modified = True
                elif "status" in v and "last_update" not in v:
                    v["last_update"] = datetime.now().isoformat()
                    modified = True
            
            if modified:
                with open(LeadsConfig.STATUS_FILE, "w", encoding="utf-8") as fw:
                    json.dump(data, fw, indent=4)
            return data
    except Exception as e:
        logger.error(f"Error cargando estados onboarding: {e}")
        return {}

def _save_leads_status(status_dict: dict[str, Any]):
    try:
        # Aseguramos que usamos siempre la ruta unificada de la config
        with open(LeadsConfig.STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_dict, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Could not save leads_status: {e}")

def _lead_key(row: list) -> str:
    """Clave única por solicitud: fecha + NIF."""
    def sg(i): return row[i].strip() if i < len(row) else ""
    return f"{sg(0)}_{sg(2)}"

class WebLeadsWorker(QThread):
    finished = Signal(list, dict)  # Emit (rows, odoo_matches)
    error = Signal(str)

    def __init__(self, service=None, url: str = None):
        super().__init__()
        self.url = url or LeadsConfig.WEB_LEADS_URL
        self.service = service

    def run(self):
        try:
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                content = resp.read().decode('utf-8')
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)
            
            odoo_matches = {}
            if self.service and len(rows) > 1:
                # Extract NIFs (index 2)
                nifs = [r[2].strip() for r in rows[1:] if len(r) > 2]
                if nifs:
                    odoo_matches = self.service.search_by_nifs(nifs)
            
            self.finished.emit(rows, odoo_matches)
        except Exception as e:
            self.error.emit(str(e))

# ── JSON path ────────────────────────────────────────────────────────────────
_COMERCIALES_JSON = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'db', 'comerciales.json')
)

# ── JSON helpers ─────────────────────────────────────────────────────────────

def _read_json_raw() -> dict:
    """Load the full JSON file (all comerciales, including inactive)."""
    try:
        with open(_COMERCIALES_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error leyendo comerciales.json: {e}")
        return {"comerciales": []}


def _write_json_raw(data: dict) -> bool:
    """Persist the full JSON file, keeping _comment and _campos blocks."""
    try:
        with open(_COMERCIALES_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error guardando comerciales.json: {e}")
        return False


def load_comerciales() -> list:
    """Return only active agents — used by the dropdown."""
    data = _read_json_raw()
    return [c for c in data.get('comerciales', []) if c.get('activo', True)]


# ── Dialog: add / edit a single agent ────────────────────────────────────────

class AgentDialog(QDialog):
    """Small form to create or edit a comercial entry."""

    TIPOS = [
        "NACIONAL", "MIXTO", "ALMACENES", "CONSTRUCCIÓN",
        "PARQUET", "ALMAC / PARQUET", "CONST / ALMAC", "GRANDES CUENTAS"
    ]

    def __init__(self, parent=None, agent: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Comercial" if agent is None else "Editar Comercial")
        self.setMinimumWidth(520)
        self._build_ui(agent or {})

    def _build_ui(self, a: dict):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.f_codigo = QLineEdit(a.get('codigo', ''))
        self.f_nombre = QLineEdit(a.get('nombre', ''))
        self.f_nombre.setPlaceholderText("EN MAYÚSCULAS — ej: JUAN GARCÍA")

        self.f_tipo = QComboBox()
        self.f_tipo.addItems(self.TIPOS)
        if a.get('tipo'):
            idx = self.f_tipo.findText(a['tipo'], Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self.f_tipo.setCurrentIndex(idx)

        self.f_zona = QLineEdit(a.get('zona', ''))
        self.f_zona.setPlaceholderText("Territorios asignados")
        self.f_email = QLineEdit(a.get('email', ''))
        self.f_email.setPlaceholderText("nombre@bur2000.com")
        self.f_telefono = QLineEdit(a.get('telefono', ''))

        form.addRow("Código interno:", self.f_codigo)
        form.addRow("Nombre *:", self.f_nombre)
        form.addRow("Tipo:", self.f_tipo)
        form.addRow("Zona:", self.f_zona)
        form.addRow("Email:", self.f_email)
        form.addRow("Teléfono:", self.f_telefono)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept(self):
        if not self.f_nombre.text().strip():
            QMessageBox.warning(self, "Requerido", "El nombre es obligatorio.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "codigo": self.f_codigo.text().strip(),
            "nombre": self.f_nombre.text().strip().upper(),
            "tipo": self.f_tipo.currentText(),
            "zona": self.f_zona.text().strip(),
            "email": self.f_email.text().strip(),
            "telefono": self.f_telefono.text().strip(),
            "activo": True,
        }


# ── Web Stats Widget (embebido — reemplaza web_stats_tab.py eliminado) ───────

class _WebStatsWidget(QFrame):
    """
    Mini-dashboard con estadísticas de solicitudes web.
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.total_val: QLabel
        self.total_lbl: QLabel
        self.pend_val: QLabel
        self.pend_lbl: QLabel
        self.done_val: QLabel
        self.done_lbl: QLabel
        self._rows: list[Any] = []
        self.init_ui()

    def init_ui(self):
        self.setObjectName("StatsPanel")
        self.setStyleSheet(f"""
            #StatsPanel {{
                background: {BUR.surface};
                border: 1px solid {BUR.border};
                border-radius: 8px;
            }}
            .StatLabel {{
                color: {BUR.accent};
                font-size: 11px;
                font-weight: bold;
            }}
            .StatValue {{
                color: {BUR.primary};
                font-size: 20px;
                font-weight: bold;
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(30)

        # Total
        self.total_val = QLabel("0")
        self.total_val.setProperty("class", "StatValue")
        _ = self.total_val
        self.total_lbl = QLabel("SOLICITUDES TOTALES")
        self.total_lbl.setProperty("class", "StatLabel")
        _ = self.total_lbl
        
        v1 = QVBoxLayout()
        v1.addWidget(self.total_val)
        v1.addWidget(self.total_lbl)
        layout.addLayout(v1)

        # Separator
        line1 = QFrame(); line1.setFrameShape(QFrame.Shape.VLine); line1.setStyleSheet(f"background:{BUR.border};")
        layout.addWidget(line1)

        # Pendientes
        self.pend_val = QLabel("0")
        self.pend_val.setProperty("class", "StatValue")
        self.pend_val.setStyleSheet(f"color: {BUR.STATUS_ERROR};")
        self.pend_lbl = QLabel("PENDIENTES")
        self.pend_lbl.setProperty("class", "StatLabel")

        v2 = QVBoxLayout()
        v2.addWidget(self.pend_val)
        v2.addWidget(self.pend_lbl)
        layout.addLayout(v2)

        # Separator
        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.VLine); line2.setStyleSheet(f"background:{BUR.border};")
        layout.addWidget(line2)

        # Procesadas
        self.done_val = QLabel("0")
        self.done_val.setProperty("class", "StatValue")
        self.done_val.setStyleSheet(f"color: {BUR.STATUS_READY};")
        self.done_lbl = QLabel("ALTAS ODOO")
        self.done_lbl.setProperty("class", "StatLabel")

        v3 = QVBoxLayout()
        v3.addWidget(self.done_val)
        v3.addWidget(self.done_lbl)
        layout.addLayout(v3)
        
        layout.addStretch()

    def refresh_from_rows(self, rows: list[Any], status: dict[str, Any] | None = None):
        """Actualiza las estadísticas a partir de las filas del CSV.
        Llamar desde load_web_leads() con los datos del worker.
        """
        self._rows = rows
        total    = max(0, len(rows) - 1)  # excluir cabecera
        # Cargamos el estado persistido para calcular procesadas
        status   = _load_leads_status()
        done     = sum(1 for r in rows[1:] if status.get(_lead_key(r), {}).get("status") == "alta")
        pending  = total - done

        self.total_val.setText(str(total))
        self.pend_val.setText(str(pending))
        self.done_val.setText(str(done))


# ── Main tab ─────────────────────────────────────────────────────────────────

class CustomerOnboardingTab(QWidget):
    def __init__(self, odoo_service: Any):
        super().__init__()
        self.service: CustomerOnboardingService = CustomerOnboardingService(odoo_service)
        self.commercial_service: CommercialService = CommercialService(odoo_service)
        self._leads_status: dict[str, Any] = {}
        self._raw_data: list[Any] = []
        self._current_lead_uid: str | None = None
        
        # UI Attributes (initialized in init_ui)
        self.kpi_total: QFrame = QFrame()
        self.kpi_pend: QFrame = QFrame()
        self.kpi_hoy: QFrame = QFrame()
        self.progress_load: QProgressBar = QProgressBar()
        self.leads_search: QLineEdit = QLineEdit()
        self.btn_load_leads: QPushButton = QPushButton()
        self.lbl_leads_count: QLabel = QLabel()
        self.leads_table: QTableWidget = QTableWidget()
        self.lead_detail_text: QTextEdit = QTextEdit()
        self._no_results_lbl: QLabel = QLabel()
        
        self.init_ui()
        # Cargar solicitudes dinámicamente al arrancar
        self.load_web_leads()

    # ── UI construction ───────────────────────────────────────────────────────

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Title
        header = QLabel("Alta y Actualización de Clientes")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #E74C3C;")
        main_layout.addWidget(header)

        # The Card / TabWidget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"QTabBar::tab {{ padding: 10px 20px; font-weight: bold; color: {BUR.primary}; font-size: 13px; }}")

        # Tab: Web (Stats) — widget embebido, reemplaza el módulo web_stats_tab.py eliminado
        self.web_stats_comp = _WebStatsWidget()
        self.tabs.addTab(self.web_stats_comp, "Web 📊")

        # Tab: Solicitudes (Leads list)
        tab_solicitudes = QWidget()
        lay_solicitudes = QVBoxLayout(tab_solicitudes)
        lay_solicitudes.addWidget(self._build_web_leads_group())
        self.tabs.addTab(tab_solicitudes, "Solicitudes")

        # Tab: Datos Principales (Fiscal + Contacto)
        tab_fiscal = QWidget()
        lay_fiscal = QVBoxLayout(tab_fiscal)
        lay_fiscal.addWidget(self._build_fiscal_group())
        lay_fiscal.addWidget(self._build_contact_group())
        lay_fiscal.addStretch()
        self.tabs.addTab(tab_fiscal, "Fiscal y Contacto")

        # Tab: Comerciales y Entrega
        tab_com = QWidget()
        lay_com = QVBoxLayout(tab_com)
        lay_com.addWidget(self._build_commercial_group())
        lay_com.addWidget(self._build_delivery_group())
        lay_com.addWidget(self._build_doc_group())
        lay_com.addStretch()
        self.tabs.addTab(tab_com, "Comercial y Entrega")

        # Tab: Gestión Comerciales
        tab_agents = QWidget()
        lay_agents = QVBoxLayout(tab_agents)
        lay_agents.addWidget(self._build_agents_admin_group())
        lay_agents.addStretch()
        self.tabs.addTab(tab_agents, "Gestión Comerciales")

        # Tab: Configuración ⚙️
        self.tabs.addTab(self._build_config_tab(), "Configuración ⚙️")

        main_layout.addWidget(self.tabs)

        # Action buttons
        btn_layout = QHBoxLayout()
        self.validate_btn = QPushButton("📋 Validar y Normalizar")
        self.validate_btn.setStyleSheet(BUR.button_primary)
        self.validate_btn.clicked.connect(self.run_validation)

        self.process_btn = QPushButton("🚀 Procesar en Odoo")
        self.process_btn.setStyleSheet(BUR.button_secondary)
        self.process_btn.clicked.connect(self.run_onboarding)

        btn_layout.addWidget(self.validate_btn)
        btn_layout.addWidget(self.process_btn)
        main_layout.addLayout(btn_layout)

    def _make_kpi(self, title: str, val: str, color: str) -> QFrame:
        """Crea una tarjeta KPI premium."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: white; border-radius: 8px; border: 1px solid {BUR.border};
            }}
        """)
        l = QVBoxLayout(card)
        l.setContentsMargins(12, 8, 12, 8)
        t = QLabel(title.upper())
        t.setStyleSheet(f"color: {BUR.muted}; font-size: 10px; font-weight: bold;")
        l.addWidget(t)
        v = QLabel(str(val))
        v.setObjectName("kpi_value")
        v.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        l.addWidget(v)
        return card

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_web_leads_group(self) -> QGroupBox:
        g = QGroupBox("📥 Solicitudes Web Pendientes (Google Forms)")
        g.setMinimumHeight(420)
        lay = QVBoxLayout(g)

        # ── KPI Cards ────────────────────────────────────────────────────────
        kpi_lay = QHBoxLayout()
        self.kpi_total = self._make_kpi("Total Solicitudes", "0", BUR.primary)
        self.kpi_pend = self._make_kpi("🔴 Pendientes", "0", BUR.STATUS_ERROR)
        self.kpi_hoy = self._make_kpi("Hoy", "0", "#27AE60")
        
        kpi_lay.addWidget(self.kpi_total)
        kpi_lay.addWidget(self.kpi_pend)
        kpi_lay.addWidget(self.kpi_hoy)
        lay.addLayout(kpi_lay)

        # ── Toolbar with Search ──────────────────────────────────────────────
        bar = QHBoxLayout()
        
        # Search Box
        self.leads_search = QLineEdit()
        self.leads_search.setPlaceholderText("🔍 Buscar por Nombre, NIF o Provincia...")
        self.leads_search.setClearButtonEnabled(True)
        self.leads_search.setFixedWidth(300)
        self.leads_search.setStyleSheet(f"border: 1px solid {BUR.border}; border-radius: 4px; padding: 4px 8px;")
        self.leads_search.textChanged.connect(self._filter_web_leads)
        
        self.btn_load_leads = QPushButton("🔄 Descargar Solicitudes")
        self.btn_load_leads.setStyleSheet(BUR.button_primary)
        self.btn_load_leads.clicked.connect(self.load_web_leads)

        self.lbl_leads_count = QLabel("Sin datos")
        self.lbl_leads_count.setStyleSheet(f"color: {BUR.muted}; font-size: 11px;")

        bar.addWidget(self.leads_search)
        bar.addSpacing(10)
        bar.addWidget(self.btn_load_leads)
        bar.addWidget(self.lbl_leads_count)
        bar.addStretch()
        lay.addLayout(bar)

        # Progress bar for loading
        self.progress_load = QProgressBar()
        self.progress_load.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {BUR.border};
                border-radius: 4px;
                text-align: center;
                height: 12px;
                font-size: 10px;
                color: {BUR.primary};
            }}
            QProgressBar::chunk {{
                background-color: {BUR.primary};
            }}
        """)
        self.progress_load.setVisible(False)
        lay.addWidget(self.progress_load)

        # Space
        lay.addSpacing(10)

        # ── Splitter: tabla izquierda | detalle derecha ───────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Tabla de solicitudes
        self.leads_table = QTableWidget(0, 6)
        self.leads_table.setHorizontalHeaderLabels(
            ["Estado", "Fecha", "Empresa / Nombre", "NIF", "Provincia", "Tipo Cliente"])
        self.leads_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.leads_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.leads_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.leads_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.leads_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.leads_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.leads_table.setSortingEnabled(True)
        self._no_results_lbl = QLabel("🔍  Sin resultados para la búsqueda actual")
        self._no_results_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results_lbl.setStyleSheet(f"color:{BUR.muted}; font-size:12px; padding:8px;")
        self._no_results_lbl.setVisible(False)
        self.leads_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.leads_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.leads_table.setAlternatingRowColors(True)
        self.leads_table.verticalHeader().setVisible(False)
        # Table Configuration
        self.leads_table.setMinimumWidth(380)
        self.leads_table.itemSelectionChanged.connect(self._on_lead_click)
        self.leads_table.itemDoubleClicked.connect(self.on_lead_selected)

        leads_left_container = QWidget()
        leads_left_layout = QVBoxLayout(leads_left_container)
        leads_left_layout.setContentsMargins(0, 0, 0, 0)
        leads_left_layout.addWidget(self.leads_table)
        leads_left_layout.addWidget(self._no_results_lbl)
        splitter.addWidget(leads_left_container)

        # Panel de detalle (derecha)
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(8, 0, 0, 0)

        detail_title = QLabel("📋  Detalle de Solicitud")
        detail_title.setStyleSheet(f"font-weight:bold; font-size:13px; color:{BUR.primary};")
        detail_layout.addWidget(detail_title)

        self.lead_detail_text = QTextEdit()
        self.lead_detail_text.setReadOnly(True)
        self.lead_detail_text.setStyleSheet("""
            QTextEdit {
                background: #F7F9FC;
                border: 1px solid #DEE2E6;
                border-radius: 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                padding: 8px;
            }
        """)
        self.lead_detail_text.setPlaceholderText(
            "Selecciona una solicitud de la lista para ver el detalle completo...")
        detail_layout.addWidget(self.lead_detail_text, 1)

        # Botones de acción del detalle
        act_bar = QHBoxLayout()
        self.btn_lead_form = QPushButton("📝  Abrir en Formulario")
        self.btn_lead_form.setStyleSheet(BUR.button_secondary)
        self.btn_lead_form.setToolTip("Carga los datos en el formulario de Alta para revisión completa")
        self.btn_lead_form.clicked.connect(self._lead_open_in_form)
        self.btn_lead_form.setEnabled(False)

        self.btn_lead_alta = QPushButton("🚀  Alta Directa en Odoo")
        self.btn_lead_alta.setStyleSheet(BUR.button_primary) # Note: button_primary is Navy, Alta Directa was Green. 
        # Actually, let's check if there is a success style. 
        # Looking at bur2000_theme.py: row 25 STATUS_READY = "#2BB673"
        # Since I don't want to break the design language, I'll stick to primary/secondary for now or use the fixed color if requested.
        # But the error was btn_primary.
        self.btn_lead_alta.setToolTip("Crea el cliente directamente en Odoo con los datos del formulario web")
        self.btn_lead_alta.clicked.connect(self._lead_alta_directa)
        self.btn_lead_alta.setEnabled(False)

        act_bar.addWidget(self.btn_lead_form)
        act_bar.addWidget(self.btn_lead_alta)
        act_bar.addStretch()
        detail_layout.addLayout(act_bar)

        splitter.addWidget(detail_container)
        splitter.setSizes([420, 480])
        lay.addWidget(splitter)

        self.web_leads_data = []       # filas crudas del CSV
        self._current_lead_row = None  # fila seleccionada actualmente
        self._leads_status = _load_leads_status()  # {key: {status, odoo_id}}
        return g

    def _build_config_tab(self) -> QWidget:
        """Pestaña para ajustar URLs y rutas sin tocar código (unificado)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        
        form = QFormLayout()
        
        self.cfg_url = QLineEdit(LeadsConfig.WEB_LEADS_URL)
        form.addRow("URL Formulario (CSV):", self.cfg_url)
        
        self.cfg_status_path = QLineEdit(LeadsConfig.STATUS_FILE)
        self.cfg_status_path.setReadOnly(True)  # No queremos que lo toquen sin saber
        form.addRow("Ruta JSON Estados:", self.cfg_status_path)
        
        lay.addLayout(form)
        
        btn_save = QPushButton("💾 Guardar Cambios Config")
        btn_save.clicked.connect(self._save_config_from_ui)
        lay.addWidget(btn_save)
        
        lay.addStretch()
        return w

    def _save_config_from_ui(self):
        LeadsConfig.WEB_LEADS_URL = self.cfg_url.text().strip()
        QMessageBox.information(self, "Configuración", "✅ URL del formulario actualizada para esta sesión.")

    def _build_fiscal_group(self) -> QGroupBox:
        g = QGroupBox("Datos Fiscales (Obligatorios)")
        lay = QFormLayout(g)

        self.nif_input = QLineEdit()
        self.nif_input.setPlaceholderText("Identificador único (CIF/NIF)")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Razón Social o Apellidos, Nombre")
        self.is_company_check = QCheckBox("Es Empresa (Sociedad)")
        self.is_company_check.setChecked(True)
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("Calle, número...")
        self.zip_input = QLineEdit()
        self.zip_input.setPlaceholderText("C.P.")
        self.city_input = QLineEdit()
        self.state_combo = QComboBox()
        self.populate_states()

        self.zip_input.editingFinished.connect(self.update_location_from_zip)

        lay.addRow("NIF/CIF:", self.nif_input)
        lay.addRow("", self.is_company_check)
        lay.addRow("Nombre/Razón Social:", self.name_input)
        lay.addRow("Dirección Fiscal:", self.address_input)
        lay.addRow("Código Postal:", self.zip_input)
        lay.addRow("Ciudad:", self.city_input)
        lay.addRow("Provincia:", self.state_combo)
        return g

    def _build_contact_group(self) -> QGroupBox:
        g = QGroupBox("Datos de Contacto")
        lay = QFormLayout(g)

        self.phone_input = QLineEdit()
        self.mobile_input = QLineEdit()
        self.email_fact_input = QLineEdit()
        self.email_fact_input.setPlaceholderText("Prioridad para Administración")
        self.email_princ_input = QLineEdit()

        lay.addRow("Teléfono Fijo:", self.phone_input)
        lay.addRow("Móvil:", self.mobile_input)
        lay.addRow("Email Facturación:", self.email_fact_input)
        lay.addRow("Email Principal:", self.email_princ_input)
        return g

    def _build_commercial_group(self) -> QGroupBox:
        g = QGroupBox("Datos Comerciales y Facturación")
        lay = QFormLayout(g)

        # Agent combo + refresh button
        self.agent_combo = QComboBox()
        self.agent_combo.setMinimumWidth(280)
        self._load_agents_combo()

        agent_row = QHBoxLayout()
        agent_row.addWidget(self.agent_combo, 1)
        self.agent_refresh_btn = QPushButton("↺")
        self.agent_refresh_btn.setFixedWidth(32)
        self.agent_refresh_btn.setToolTip("Recargar lista desde comerciales.json")
        self.agent_refresh_btn.clicked.connect(self._on_refresh_clicked)
        agent_row.addWidget(self.agent_refresh_btn)

        self.cust_type_combo = QComboBox()
        self.cust_type_combo.addItems([
            "Distribuidor oficial", "Almacen de construccion",
            "Instalador", "Empresa constructora"
        ])

        self.payment_mode_combo = QComboBox()
        self.payment_mode_combo.addItems([
            "TRANSFERENCIA", "DOMICILIACION BANCARIA",
            "PAGARE", "CONFIRMING", "A LA VISTA"
        ])

        self.payment_terms_input = QLineEdit()
        self.payment_terms_input.setPlaceholderText("Ej: 20 dias FF; dia de pago 5")
        self.iban_input = QLineEdit()
        self.iban_input.setPlaceholderText("Obligatorio si es Domiciliación")

        self.invoice_type_combo = QComboBox()
        self.invoice_type_combo.addItems([
            "N-No Agrupada (Por entrega)", "M-Una Factura/Mes (Mensual)"
        ])

        # Nuevos campos solicitados
        self.requested_conditions_input = QTextEdit()
        self.requested_conditions_input.setPlaceholderText("Comentarios o condiciones solicitadas por el cliente...")
        self.requested_conditions_input.setFixedHeight(55)

        self.commercial_discounts_input = QTextEdit()
        self.commercial_discounts_input.setPlaceholderText("Descuentos o promociones especiales acordadas...")
        self.commercial_discounts_input.setFixedHeight(55)

        self.estimated_revenue_input = QLineEdit()
        self.estimated_revenue_input.setPlaceholderText("Facturación anual estimada en €")

        self.discount_group_combo = QComboBox()
        self.discount_group_combo.addItems([
            "Sin Grupo / General",
            "GRUPO A (Grandes Cuentas)",
            "GRUPO B (Almacenes)",
            "GRUPO C (Instaladores)",
            "GRUPO ESPECIAL (Obra)"
        ])

        # Botón de Validación Comercial
        self.btn_commercial_validate = QPushButton("⚖️ Validar Perfil Comercial")
        self.btn_commercial_validate.setStyleSheet(BUR.button_primary)
        self.btn_commercial_validate.setMinimumHeight(38)
        self.btn_commercial_validate.clicked.connect(self.run_commercial_validation)

        lay.addRow("Agente Comercial:", agent_row)
        lay.addRow("Tipo de Cliente:", self.cust_type_combo)
        lay.addRow("Modo de Pago:", self.payment_mode_combo)
        lay.addRow("Plazos de Pago:", self.payment_terms_input)
        lay.addRow("IBAN / Cuenta:", self.iban_input)
        lay.addRow("Tipo Factura:", self.invoice_type_combo)
        
        lay.addRow(QLabel("<b>CONDICIONES COMERCIALES</b>"))
        lay.addRow("Condiciones Solicitadas:", self.requested_conditions_input)
        lay.addRow("Descuentos Acordados:", self.commercial_discounts_input)
        lay.addRow("Facturación Estimada (€):", self.estimated_revenue_input)
        lay.addRow("Grupo de Descuento:", self.discount_group_combo)
        lay.addRow("", self.btn_commercial_validate)
        return g

    def _build_delivery_group(self) -> QGroupBox:
        g = QGroupBox("Dirección de Entrega (Si es distinta)")
        self.has_delivery_check = QCheckBox("Usar dirección de entrega alternativa")
        lay = QFormLayout(g)

        self.d_name_input = QLineEdit()
        self.d_name_input.setPlaceholderText("REF. OBRA - CIUDAD")
        self.d_street_input = QLineEdit()
        self.d_zip_input = QLineEdit()
        self.d_phone_input = QLineEdit()
        self.d_contact_name = QLineEdit()
        self.d_trailer_check = QCheckBox("Accede Tráiler")
        self.d_medios_check = QCheckBox("Tiene medios de descarga")
        self.d_extra_notes = QTextEdit()
        self.d_extra_notes.setFixedHeight(55)

        lay.addRow("", self.has_delivery_check)
        lay.addRow("Nombre Ref.:", self.d_name_input)
        lay.addRow("Vía y Nº:", self.d_street_input)
        lay.addRow("C.P.:", self.d_zip_input)
        lay.addRow("Teléfono Entrega:", self.d_phone_input)
        lay.addRow("Contacto en Obra:", self.d_contact_name)
        lay.addRow("Logística:", self.d_trailer_check)
        lay.addRow("", self.d_medios_check)
        lay.addRow("Notas Libres:", self.d_extra_notes)
        return g

    def _build_doc_group(self) -> QGroupBox:
        g = QGroupBox("Documentación (Opcional - Rule 7.5)")
        lay = QHBoxLayout(g)
        self.doc_path_input = QLineEdit()
        self.doc_path_input.setPlaceholderText("Ruta al archivo NIF/VIES...")
        self.doc_path_input.setReadOnly(True)
        self.doc_browse_btn = QPushButton("📁 Buscar Archivo")
        self.doc_browse_btn.clicked.connect(self.browse_document)
        lay.addWidget(self.doc_path_input)
        lay.addWidget(self.doc_browse_btn)
        return g

    def _build_agents_admin_group(self) -> QGroupBox:
        """Collapsible panel for managing the agents list."""
        g = QGroupBox("⚙️  Gestión de Comerciales")
        g.setCheckable(True)
        g.setChecked(False)   # collapsed by default
        g.toggled.connect(lambda on: g.setMaximumHeight(16777215 if on else 30))
        g.setMaximumHeight(30)

        outer = QVBoxLayout(g)
        outer.setContentsMargins(6, 6, 6, 6)

        # ── Table ────────────────────────────────────────────────────────────
        COLS = ["Código", "Nombre", "Tipo", "Zona", "Email", "Teléfono", "Activo"]
        self.agents_table = QTableWidget(0, len(COLS))
        self.agents_table.setHorizontalHeaderLabels(COLS)
        self.agents_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)   # Zona stretches
        self.agents_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.agents_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.agents_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.agents_table.setMinimumHeight(220)
        self.agents_table.setAlternatingRowColors(True)
        self.agents_table.verticalHeader().setVisible(False)
        outer.addWidget(self.agents_table)

        # ── Button bar ───────────────────────────────────────────────────────
        bar = QHBoxLayout()

        btn_new = QPushButton("➕  Nuevo Comercial")
        btn_new.setStyleSheet("background-color: #27AE60; color: white; padding: 6px 12px;")
        btn_new.clicked.connect(self._agent_new)

        btn_edit = QPushButton("✏️  Editar Seleccionado")
        btn_edit.setStyleSheet("background-color: #2980B9; color: white; padding: 6px 12px;")
        btn_edit.clicked.connect(self._agent_edit)

        self.btn_toggle = QPushButton("🔴  Desactivar")
        self.btn_toggle.setStyleSheet("background-color: #E67E22; color: white; padding: 6px 12px;")
        self.btn_toggle.clicked.connect(self._agent_toggle)

        btn_save = QPushButton("💾  Guardar Cambios")
        btn_save.setStyleSheet(f"background-color: {BUR.primary}; color: white; padding: 6px 12px;")
        btn_save.clicked.connect(self._agents_save)

        bar.addWidget(btn_new)
        bar.addWidget(btn_edit)
        bar.addWidget(self.btn_toggle)
        bar.addStretch()
        bar.addWidget(btn_save)
        outer.addLayout(bar)

        # Fill table when panel is expanded
        g.toggled.connect(lambda on: self._refresh_agents_table() if on else None)

        return g

    # ── Agents admin helpers ──────────────────────────────────────────────────

    def _refresh_agents_table(self):
        """Reload table from JSON (all agents, including inactive)."""
        data = _read_json_raw()
        agents = data.get('comerciales', [])
        self.agents_table.setRowCount(0)
        for a in agents:
            row = self.agents_table.rowCount()
            self.agents_table.insertRow(row)
            vals = [
                a.get('codigo', ''),
                a.get('nombre', ''),
                a.get('tipo', ''),
                a.get('zona', ''),
                a.get('email', ''),
                a.get('telefono', ''),
                '✅ Activo' if a.get('activo', True) else '⛔ Inactivo',
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if not a.get('activo', True):
                    item.setForeground(QColor('#888888'))
                self.agents_table.setItem(row, col, item)
        self.agents_table.resizeColumnToContents(0)
        self.agents_table.resizeColumnToContents(6)

    def _selected_row_index(self) -> int | None:
        """Return the selected row index, or None with a warning."""
        rows = self.agents_table.selectedItems()
        if not rows:
            QMessageBox.information(self, "Selección", "Selecciona un comercial de la tabla.")
            return None
        return self.agents_table.currentRow()

    def _agent_new(self):
        dlg = AgentDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = _read_json_raw()
            data.setdefault('comerciales', []).append(dlg.get_data())
            if _write_json_raw(data):
                self._refresh_agents_table()
                self._load_agents_combo()
                QMessageBox.information(self, "Guardado", "Comercial añadido correctamente.")

    def _agent_edit(self):
        row = self._selected_row_index()
        if row is None:
            return
        data = _read_json_raw()
        agent = data['comerciales'][row]
        dlg = AgentDialog(self, agent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_data()
            updated['activo'] = agent.get('activo', True)  # preserve active state
            data['comerciales'][row] = updated
            if _write_json_raw(data):
                self._refresh_agents_table()
                self._load_agents_combo()
                QMessageBox.information(self, "Guardado", "Comercial actualizado.")

    def _agent_toggle(self):
        row = self._selected_row_index()
        if row is None:
            return
        data = _read_json_raw()
        agent = data['comerciales'][row]
        current = agent.get('activo', True)
        action = "desactivar" if current else "activar"
        reply = QMessageBox.question(
            self, "Confirmar",
            f"¿{action.capitalize()} a {agent['nombre']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            agent['activo'] = not current
            if _write_json_raw(data):
                self._refresh_agents_table()
                self._load_agents_combo()
                QMessageBox.information(
                    self, "OK",
                    f"{agent['nombre']} {'desactivado' if current else 'activado'}."
                )

    def _agents_save(self):
        """Force-write: notifies user the file is already up to date (saves are instant)."""
        QMessageBox.information(
            self, "Guardado",
            "Los cambios se guardan automáticamente con cada acción.\n"
            f"Fichero: {_COMERCIALES_JSON}"
        )

    def _on_refresh_clicked(self):
        self._load_agents_combo()
        QMessageBox.information(self, "Recargado", "Lista de comerciales actualizada.")

    # ── Agent combo ───────────────────────────────────────────────────────────

    def _load_agents_combo(self):
        """Populate the dropdown from comerciales.json (active only)."""
        prev = self.agent_combo.currentText()
        self.agent_combo.clear()
        comerciales = load_comerciales()
        if not comerciales:
            comerciales = [
                {'codigo': '', 'nombre': 'VENTAS DIRECTAS', 'tipo': 'NACIONAL',
                 'zona': '', 'email': ''}
            ]
        for c in comerciales:
            label = f"{c['nombre']}  ({c['tipo']})"
            self.agent_combo.addItem(label, userData=c)
            idx = self.agent_combo.count() - 1
            self.agent_combo.setItemData(
                idx, c.get('zona', ''), Qt.ItemDataRole.ToolTipRole)
        # Restore previous selection if possible
        if prev:
            found = self.agent_combo.findText(
                prev.split('(')[0].strip(), Qt.MatchFlag.MatchContains)
            if found >= 0:
                self.agent_combo.setCurrentIndex(found)
        logger.debug(f"Cargados {len(comerciales)} comerciales activos en el combo")

    def get_selected_agent_data(self) -> dict:
        """Return full dict for the currently selected agent."""
        return self.agent_combo.currentData() or {}

    # ── Form data ─────────────────────────────────────────────────────────────

    def get_form_data(self) -> dict:
        data = {
            'nif':                  self.nif_input.text(),
            'is_company':           self.is_company_check.isChecked(),
            'name':                 self.name_input.text(),
            'street':               self.address_input.text(),
            'zip':                  self.zip_input.text(),
            'city':                 self.city_input.text(),
            'phone':                self.phone_input.text(),
            'mobile':               self.mobile_input.text(),
            'email_facturacion':    self.email_fact_input.text(),
            'email_principal':      self.email_princ_input.text(),
            'commercial_agent':     self.agent_combo.currentText().split('(')[0].strip(),
            'commercial_agent_email': (self.agent_combo.currentData() or {}).get('email', ''),
            'commercial_agent_code':  (self.agent_combo.currentData() or {}).get('codigo', ''),
            'customer_type':        self.cust_type_combo.currentText(),
            'payment_mode':         self.payment_mode_combo.currentText(),
            'payment_terms':        self.payment_terms_input.text(),
            'iban':                 self.iban_input.text(),
            'invoice_type':         self.invoice_type_combo.currentText(),
            'document_path':        self.doc_path_input.text(),
            'state_id':             self.state_combo.currentData(),
            
            # Nuevos campos comerciales
            'requested_conditions': self.requested_conditions_input.toPlainText().strip(),
            'commercial_discounts': self.commercial_discounts_input.toPlainText().strip(),
            'estimated_revenue':    self.estimated_revenue_input.text().strip(),
            'discount_group':       self.discount_group_combo.currentText(),
        }
        if self.has_delivery_check.isChecked():
            data['delivery_address'] = {
                'name':           self.d_name_input.text(),
                'street':         self.d_street_input.text(),
                'zip':            self.d_zip_input.text(),
                'phone':          self.d_phone_input.text(),
                'contact_name':   self.d_contact_name.text(),
                'access_trailer': self.d_trailer_check.isChecked(),
                'descarga_medios': self.d_medios_check.isChecked(),
                'extra_notes':    self.d_extra_notes.toPlainText(),
            }
        return data

    def fill_form_from_dict(self, data: dict):
        """
        Llena el formulario con un diccionario de datos.
        Útil para Altas rápidas desde solicitudes web o sincronización.
        """
        # Fiscal
        if 'nif' in data: self.nif_input.setText(str(data['nif']))
        if 'name' in data: self.name_input.setText(str(data['name']))
        if 'is_company' in data: self.is_company_check.setChecked(bool(data['is_company']))
        if 'address' in data: self.address_input.setText(str(data['address']))
        if 'street' in data: self.address_input.setText(str(data['street'])) # Alias
        if 'zip' in data: self.zip_input.setText(str(data['zip']))
        if 'city' in data: self.city_input.setText(str(data['city']))
        
        # Provincia (State)
        state_val = data.get('state') or data.get('state_id')
        if state_val:
            if isinstance(state_val, int):
                idx = self.state_combo.findData(state_val)
                if idx >= 0: self.state_combo.setCurrentIndex(idx)
            else:
                idx = self.state_combo.findText(str(state_val).upper(), Qt.MatchFlag.MatchContains)
                if idx >= 0: self.state_combo.setCurrentIndex(idx)

        # Contacto
        if 'phone' in data: self.phone_input.setText(str(data['phone']))
        if 'mobile' in data: self.mobile_input.setText(str(data['mobile']))
        if 'email' in data: 
            self.email_princ_input.setText(str(data['email']))
            self.email_fact_input.setText(str(data['email']))
        if 'email_principal' in data: self.email_princ_input.setText(str(data['email_principal']))
        if 'email_facturacion' in data: self.email_fact_input.setText(str(data['email_facturacion']))

        # Comercial
        agent_name = data.get('comercial_name') or data.get('commercial_agent')
        if agent_name:
            idx = self.agent_combo.findText(str(agent_name), Qt.MatchFlag.MatchContains)
            if idx >= 0: self.agent_combo.setCurrentIndex(idx)

        if 'customer_type' in data: self.cust_type_combo.setCurrentText(str(data['customer_type']))
        if 'payment_mode' in data: self.payment_mode_combo.setCurrentText(str(data['payment_mode']))
        
        # Plazos de pago / pay_days
        pay_days = data.get('pay_days') or data.get('payment_terms')
        if pay_days:
            self.payment_terms_input.setText(str(pay_days))

        if 'iban' in data: self.iban_input.setText(str(data['iban']))
        if 'invoice_type' in data: self.invoice_type_combo.setCurrentText(str(data['invoice_type']))

        # Dirección de entrega
        if 'shipping' in data:
            shipping = data['shipping']
            if isinstance(shipping, dict):
                self.has_delivery_check.setChecked(True)
                if 'name' in shipping: self.d_name_input.setText(str(shipping['name']))
                if 'street' in shipping: self.d_street_input.setText(str(shipping['street']))
                if 'zip' in shipping: self.d_zip_input.setText(str(shipping['zip']))
                if 'phone' in shipping: self.d_phone_input.setText(str(shipping['phone']))
                if 'contact_name' in shipping: self.d_contact_name.setText(str(shipping['contact_name']))
            elif isinstance(shipping, str) and shipping.strip():
                # Si viene como string, lo ponemos en las notas o intentamos algo básico
                self.has_delivery_check.setChecked(True)
                self.d_street_input.setText(shipping)

        if 'notes' in data:
            self.d_extra_notes.setText(str(data['notes']))

        # Auto-switch to Fiscal tab (index 2)
        if hasattr(self, 'tabs'):
            self.tabs.setCurrentIndex(2)

    # ── State / ZIP helpers ───────────────────────────────────────────────────

    def populate_states(self):
        try:
            states = self.service.get_all_states()
            self.state_combo.clear()
            self.state_combo.addItem("- Seleccione Provincia -", None)
            for s in states:
                self.state_combo.addItem(s['name'], s['id'])
        except Exception as e:
            logger.error(f"Error cargando provincias: {e}")

    def _search_customer_odoo(self):
        """Busca si el cliente ya existe en Odoo por su NIF."""
        vat = self.nif_input.text().strip()
        if not vat: return
        
        try:
            with get_conn(auto_return=True) as _:
                found = self.service.search_by_nif(vat)
            if found:
                QMessageBox.information(self, "Odoo Match", f"Cliente encontrado en Odoo:\n{found[0]['name']}")
        except Exception as e:
            logger.error(f"Error buscando cliente en Odoo: {e}")

    def update_location_from_zip(self):
        zip_code = self.zip_input.text().strip()
        if len(zip_code) >= 5:
            try:
                loc = self.service.get_location_from_zip(zip_code)
                if loc:
                    self.city_input.setText(loc['city'])
                    if loc['state_id']:
                        idx = self.state_combo.findData(loc['state_id'])
                        if idx >= 0:
                            self.state_combo.setCurrentIndex(idx)
            except Exception as e:
                logger.warning(f"Zip lookup failed: {e}")

    # ── Main actions ──────────────────────────────────────────────────────────

    def run_validation(self):
        data = self.get_form_data()
        if not data['nif']:
            QMessageBox.warning(self, "Validación", "El NIF es obligatorio.")
            return
        if not data['name']:
            QMessageBox.warning(self, "Validación", "El Nombre Legal es obligatorio.")
            return
        # Normalise in place
        self.name_input.setText(
            self.service.normalize_name(data['name'], not data['is_company']))
        self.address_input.setText(self.service.normalize_str(data['street']))
        p1 = self.service.normalize_phone(data['phone'])
        p2 = self.service.normalize_phone(data['mobile'])
        if p1 and not p2: p2 = p1
        if p2 and not p1: p1 = p2
        self.phone_input.setText(p1)
        self.mobile_input.setText(p2)

        existing = self.service.search_by_nif(data['nif'])
        if existing:
            QMessageBox.information(
                self, "Resultado",
                f"NIF encontrado: {existing[0]['name']}.\nEl proceso realizará una ACTUALIZACIÓN.")
        else:
            QMessageBox.information(
                self, "Resultado",
                "NIF no encontrado. El proceso realizará un ALTA NUEVA.")

    def run_commercial_validation(self):
        """Ejecuta la validación del perfil comercial usando el motor de CommercialService."""
        data = self.get_form_data()
        nif = data.get('nif')
        tipo_cliente = data.get('customer_type')
        grupo_dto = data.get('discount_group')
        fact_estimada = data.get('estimated_revenue')

        if not nif or not tipo_cliente:
            QMessageBox.warning(self, "Validación Comercial", "Se requiere NIF y Tipo de Cliente para validar.")
            return

        try:
            # Convertir facturación a float si es posible
            rev = 0.0
            if fact_estimada:
                rev = float(fact_estimada.replace("€", "").replace(".", "").replace(",", ".").strip())
            
            # Llamar al servicio comercial
            res = self.commercial_service.evaluar_cliente(
                nif=nif,
                tipo_cliente=tipo_cliente,
                grupo_descuento=grupo_dto,
                facturacion_estimada=rev
            )

            # Mostrar resultado con estética premium
            msg = f"<h3>Análisis Comercial para {nif}</h3><hr/>"
            if res['status'] == 'OK':
                msg += f"<p style='color:green;'><b>✅ Perfil Validado:</b> Las condiciones se ajustan a la política comercial.</p>"
            else:
                msg += f"<p style='color:orange;'><b>⚠️ Revisión Requerida:</b> {res.get('message', 'No cumple criterios estándar.')}</p>"
            
            msg += f"<p><b>Recomendación:</b> {res.get('recommendation', 'Sin recomendación específica.')}</p>"
            
            QMessageBox.information(self, "Validación Comercial Automática", msg)

        except Exception as e:
            logger.error(f"Error en validación comercial: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo completar la validación: {str(e)}")

    def run_onboarding(self):
        data = self.get_form_data()
        reply = QMessageBox.question(
            self, "Confirmar",
            "¿Seguro que deseas procesar este registro en Odoo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            res = self.service.create_or_update_customer(data)
            if res['status'] == 'success':
                QMessageBox.information(
                    self, "Éxito",
                    f"Operación exitosa: {res['action'].upper()}.\nID Odoo: {res['partner_id']}")
                self.doc_path_input.clear()
                
                # Update status of associated web lead 
                if self._current_lead_uid is not None:
                    self._leads_status[self._current_lead_uid] = {
                        "status": "alta",
                        "last_update": datetime.now().isoformat()
                    }
                    _save_leads_status(self._leads_status)
                    self._current_lead_uid = None
                    self.load_web_leads()
            else:
                QMessageBox.critical(
                    self, "Error",
                    f"Fallo al procesar: {res['message']}")

    def browse_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar NIF/VIES", "",
            "PDF Files (*.pdf);;Images (*.jpg *.png);;All Files (*)")
        if file_path:
            self.doc_path_input.setText(file_path)

    def load_web_leads(self):
        """Descargar solicitudes unificada."""
        self.btn_load_leads.setText("⏳ Cargando...")
        self.btn_load_leads.setEnabled(False)
        self.progress_load.setVisible(True)
        self.progress_load.setValue(10)

        # Usar el worker con el service para cruzar con Odoo
        self.worker = WebLeadsWorker(service=self.service)
        self.worker.finished.connect(self._on_leads_loaded)
        self.worker.error.connect(self._on_leads_error)
        self.worker.start()


    def _on_leads_loaded(self, rows: list, odoo_matches: dict = None):
        """Callback cuando termina el worker de descarga."""
        self.btn_load_leads.setText("🔄 Actualizar Solicitudes")
        self.btn_load_leads.setEnabled(True)
        self.progress_load.setVisible(False)
        self.leads_table.setSortingEnabled(False)
        self.leads_table.setRowCount(0)
        
        if not rows or len(rows) <= 1:
            self.lbl_leads_count.setText("No hay solicitudes nuevas.")
            # Limpiar stats si no hay nada
            if hasattr(self, 'web_stats_comp'):
                self.web_stats_comp.refresh_from_rows([])
            self.leads_table.setSortingEnabled(True)
            return

        # Sincronizar el mini-dashboard (Widget Estadísticas) — incluye odoo_matches
        if hasattr(self, 'web_stats_comp'):
            self.web_stats_comp.refresh_from_rows(rows, odoo_matches or {})

        header = rows[0]
        data_rows = rows[1:]
        total = len(data_rows)
        pendientes = 0
        hoy_count = 0
        today_str = datetime.now().strftime("%Y-%m-%d")

        for row in data_rows:
            def sg(i: int) -> str: return str(row[i]).strip() if i < len(row) else ""
            
            created_at = sg(0)
            nif = sg(2)
            uid = _lead_key(row)
            lead_status = self._leads_status.get(uid, {"status": "pending"})
            
            # Cruzar con Odoo (si odoo_matches existe y tiene el NIF)
            in_odoo = False
            if odoo_matches and nif in odoo_matches:
                in_odoo = True
            
            # Status display
            st = lead_status.get("status", "pending")
            if in_odoo:
                status_text = "✅ Odoo OK"
                status_color = BUR.STATUS_READY
            elif st == "alta":
                status_text = "🚀 Procesado"
                status_color = BUR.STATUS_READY
            elif st == "revisando":
                status_text = "👀 Revisando"
                status_color = BUR.STATUS_WAITING
            else:
                status_text = "🔴 Pendiente"
                status_color = BUR.STATUS_ERROR
                pendientes += 1
            
            if created_at.startswith(today_str):
                hoy_count += 1

            r_idx = self.leads_table.rowCount()
            self.leads_table.insertRow(r_idx)
            
            item_status = QTableWidgetItem(status_text)
            item_status.setForeground(QColor(status_color))
            f = item_status.font(); f.setBold(True); item_status.setFont(f)
            # Guardamos la fila original en el Item
            item_status.setData(int(Qt.ItemDataRole.UserRole), row)
            self.leads_table.setItem(r_idx, 0, item_status)

            # Col 1 — Fecha (índice 0 del CSV)
            date_text = sg(0)[:10] if len(sg(0)) >= 10 else sg(0)
            self.leads_table.setItem(r_idx, 1, QTableWidgetItem(date_text))
            # Col 2 — Empresa / Nombre (índice 1)
            self.leads_table.setItem(r_idx, 2, QTableWidgetItem(sg(1)))
            # Col 3 — NIF (índice 2)
            self.leads_table.setItem(r_idx, 3, QTableWidgetItem(nif))
            # Col 4 — Provincia (índice 6)
            self.leads_table.setItem(r_idx, 4, QTableWidgetItem(sg(6)))
            # Col 5 — Tipo Cliente (índice 17, si existe)
            self.leads_table.setItem(r_idx, 5, QTableWidgetItem(sg(17)))

        self.leads_table.setSortingEnabled(True)
        self.lbl_leads_count.setText(f"Mostrando {total} solicitudes")
        
        # Actualizar KPIs locales (Pestaña Solicitudes)
        for kpi, val in [(self.kpi_total, total), (self.kpi_pend, pendientes), (self.kpi_hoy, hoy_count)]:
            if kpi:
                lbl = kpi.findChild(QLabel, "kpi_value")
                if lbl: lbl.setText(str(val))

        self.worker = None

    def _on_leads_error(self, message):
        logger.error(f"WebLeadsWorker error: {message}")
        self.btn_load_leads.setText("🔄 Actualizar Solicitudes")
        self.btn_load_leads.setEnabled(True)
        self.progress_load.setValue(0)
        self.progress_load.setVisible(False)
        self.lbl_leads_count.setText("⚠️ Error al cargar solicitudes")
        QMessageBox.critical(self, "Error de Conexión",
            f"No se pudieron descargar las solicitudes web:\n\n{message}\n\nComprueba la conexión a Internet y vuelve a intentarlo.")
        self.worker = None

    def _filter_web_leads(self):
        """Filtra la tabla de solicitudes web en tiempo real con feedback visual."""
        query = self.leads_search.text().lower().strip()
        visible_count = 0
        for i in range(self.leads_table.rowCount()):
            match = not query  # Si no hay query, mostrar todo
            if query:
                for j in range(self.leads_table.columnCount()):
                    item = self.leads_table.item(i, j)
                    if item and query in item.text().lower():
                        match = True
                        break
            self.leads_table.setRowHidden(i, not match)
            if match:
                visible_count += 1

        # Feedback visual cuando no hay resultados
        has_data = self.leads_table.rowCount() > 0
        no_match = has_data and visible_count == 0
        if hasattr(self, '_no_results_lbl'):
            self._no_results_lbl.setVisible(no_match)
        # Actualizar contador
        total = self.leads_table.rowCount()
        if query and has_data:
            self.lbl_leads_count.setText(f"{visible_count} de {total} solicitudes")
        elif has_data:
            self.lbl_leads_count.setText(f"Mostrando {total} solicitudes")

    def _on_lead_click(self):
        """Muestra detalle al pulsar una fila."""
        row_idx = self.leads_table.currentRow()
        if row_idx < 0: return
        
        item = self.leads_table.item(row_idx, 0)
        row = item.data(int(Qt.ItemDataRole.UserRole))
        if not row: return

        def sg(i: int) -> str: return str(row[i]).strip() if i < len(row) else ""
        def row_html(label: str, val: str) -> str:
            return f"<tr><td style='color:#666; width:120px;'>{label}:</td><td style='font-weight:500;'>{val or '-'}</td></tr>"

        # Determinar badge de estado para el encabezado
        uid_status = self._leads_status.get(_lead_key(row), {}).get("status", "pending")
        if uid_status == "alta":
            badge = f"<span style='background:{BUR.STATUS_READY};color:white;border-radius:4px;padding:2px 8px;font-size:10px;'>🚀 PROCESADO</span>"
        elif uid_status == "revisando":
            badge = f"<span style='background:{BUR.STATUS_WAITING};color:white;border-radius:4px;padding:2px 8px;font-size:10px;'>👀 REVISANDO</span>"
        else:
            badge = f"<span style='background:{BUR.STATUS_ERROR};color:white;border-radius:4px;padding:2px 8px;font-size:10px;'>🔴 PENDIENTE</span>"

        def section_header(title: str) -> str:
            return (
                f"<tr><td colspan='2' style='background:{BUR.surface}; padding:6px; "
                f"border-bottom:1px solid {BUR.primary}; color:{BUR.primary}; "
                f"font-weight:bold; font-size:12px;'>{title}</td></tr>"
            )

        html = f"""
        <div style='font-family:Segoe UI,sans-serif; padding:4px;'>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
            <tr>
              <td><span style='color:{BUR.primary}; font-size:16px; font-weight:bold;'>{sg(1)}</span></td>
              <td align="right">{badge}</td>
            </tr>
          </table>
          <table width="100%" cellpadding="4" cellspacing="0" style='border-collapse:collapse;'>
            {section_header('🏢 IDENTIFICACIÓN')}
            {row_html('NIF/CIF', sg(2))}
            {row_html('Provincia', sg(6))}
            {row_html('Dirección', sg(3))}
            {row_html('C.P. / Ciudad', f"{sg(4)} {sg(5)}")}
            {row_html('Email', sg(9))}
            {row_html('Teléfonos', f"{sg(7)} / {sg(8)}")}

            {section_header('💰 PAGO Y FACTURACIÓN')}
            {row_html('Modo Pago', sg(10))}
            {row_html('Plazo de Pago', sg(37))}
            {row_html('Día de Pago', sg(11))}
            {row_html('IBAN', sg(15))}
            {row_html('Banco', sg(16))}
            {row_html('Tipo Factura', sg(14))}

            {section_header('🚛 LOGÍSTICA DE ENTREGA')}
            {row_html('Misma dir.', sg(21))}
            {row_html('Dir. Entrega', sg(29))}
            {row_html('C.P. Entrega', sg(30))}
            {row_html('Población', sg(31))}
            {row_html('Tipo Destino', sg(25))}
            {row_html('Contacto Obra', sg(22))}
            {row_html('Accede Tráiler', sg(26))}
            {row_html('Medios descarga', sg(27))}
            {row_html('Notas entrega', sg(28))}

            {section_header('📝 NOTAS Y METADATA')}
            {row_html('Notas libres', sg(20))}
            {row_html('Enviado el', sg(0))}
          </table>
        </div>
        """
        self.lead_detail_text.setHtml(html)
        self.btn_lead_form.setEnabled(True)
        # Alta directa si no está ya en alta
        uid = _lead_key(row)
        already_alta = self._leads_status.get(uid, {}).get("status") == "alta"
        self.btn_lead_alta.setEnabled(not already_alta)

    def _lead_open_in_form(self):
        """Carga el lead seleccionado en el formulario completo (llama al doble-clic)."""
        row_idx = self.leads_table.currentRow()
        if row_idx < 0:
            return
        item = self.leads_table.item(row_idx, 0)
        if item:
            self.on_lead_selected(item)

    def _lead_alta_directa(self):
        """Alta directa desde el panel de revisión, sin salir de la pestaña Solicitudes."""
        row_idx = self.leads_table.currentRow()
        if row_idx < 0:
            return
        
        item = self.leads_table.item(row_idx, 0)
        if not item:
            return
        row = item.data(int(Qt.ItemDataRole.UserRole))
        if not row:
            return
        
        # Pedir confirmación
        empresa = row[1].strip() if len(row) > 1 else "esta empresa"
        reply = QMessageBox.question(
            self, "Confirmar Alta Directa",
            f"¿Dar de alta a <b>{empresa}</b> directamente en Odoo?\n\n"
            f"Se usarán los datos tal como llegaron del formulario web.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Cargar los datos en el formulario interno para asegurar que todos los valores (provincia, combos) se asientan bien.
        item = self.leads_table.item(row_idx, 0)
        if item:
            self.on_lead_selected(item)

        # Obtenemos la data parseada y rica de la UI
        data = self.get_form_data()
        res = self.service.create_or_update_customer(data)

        key = _lead_key(row)
        if res['status'] == 'success':
            self._leads_status[key] = {
                "status": "alta",
                "odoo_id": res['partner_id'],
                "action": res['action'],
                "last_update": datetime.now().isoformat()
            }
            _save_leads_status(self._leads_status)
            
            # Recargar tabla para refrescar badge
            self.load_web_leads() 
            QMessageBox.information(
                self, "✅ Alta Completada",
                f"Cliente dado de alta correctamente.\n"
                f"Acción: {res['action'].upper()}\n"
                f"ID Odoo: {res['partner_id']}")
            self._on_lead_click()  # refrescar detalle lateral
        else:
            QMessageBox.critical(
                self, "Error en Alta",
                f"No se pudo procesar el alta:\n{res['message']}")

    def on_lead_selected(self, item):
        """Doble-clic: carga datos en el formulario completo y salta a pestaña Fiscal."""
        row_idx = item.row()
        item_status = self.leads_table.item(row_idx, 0)
        if not item_status:
            return
        row = item_status.data(int(Qt.ItemDataRole.UserRole))
        if not row:
            return

        def sg(idx):
            return row[idx].strip() if idx < len(row) else ""

        # Fiscal
        self.name_input.setText(sg(1))
        self.nif_input.setText(sg(2))
        self.address_input.setText(sg(3))
        self.zip_input.setText(sg(4))
        self.city_input.setText(sg(5))

        provincia = sg(6).upper()
        if provincia:
            found = self.state_combo.findText(provincia, Qt.MatchFlag.MatchContains)
            if found >= 0:
                self.state_combo.setCurrentIndex(found)

        # Contacto
        self.phone_input.setText(sg(7))
        self.mobile_input.setText(sg(8))
        self.email_princ_input.setText(sg(9))
        self.email_fact_input.setText(sg(13))

        # Modo de pago
        modo_pago = sg(10).upper()
        if "TRANSFERENCIA" in modo_pago:
            self.payment_mode_combo.setCurrentText("TRANSFERENCIA")
        elif "DOMICILIA" in modo_pago:
            self.payment_mode_combo.setCurrentText("DOMICILIACION BANCARIA")
        elif "PAGAR" in modo_pago:
            self.payment_mode_combo.setCurrentText("PAGARE")
        elif "CONFIRMING" in modo_pago:
            self.payment_mode_combo.setCurrentText("CONFIRMING")

        # sg(37)=Plazo de Pago, sg(11)=Día de Pago (según cabeceras reales del CSV)
        plazo = sg(37)
        dia_pago = sg(11)
        self.payment_terms_input.setText(
            f"{plazo} / Día: {dia_pago}" if plazo and dia_pago else plazo or dia_pago)
        self.iban_input.setText(sg(15))
        self.requested_conditions_input.setText(sg(20))

        # Tipo factura
        self.invoice_type_combo.setCurrentText(
            "N-No Agrupada (Por entrega)" if "No Agrupada" in sg(14)
            else "M-Una Factura/Mes (Mensual)")

        # Tipo cliente
        tipo_cliente = sg(32).upper()
        if "ALMAC" in tipo_cliente:
            self.cust_type_combo.setCurrentText("Almacen de construccion")
        elif "CONSTRUCT" in tipo_cliente:
            self.cust_type_combo.setCurrentText("Empresa constructora")
        elif "INSTALADOR" in tipo_cliente or "REFORMISTA" in tipo_cliente:
            self.cust_type_combo.setCurrentText("Instalador")

        # Dirección de entrega
        misma_dir = sg(21).upper()
        if "NO" in misma_dir:
            self.has_delivery_check.setChecked(True)
            self.d_street_input.setText(sg(29))
            self.d_zip_input.setText(sg(30))
            self.d_name_input.setText(sg(31))
            self.d_contact_name.setText(sg(22))
            self.d_phone_input.setText(sg(23))
            self.d_trailer_check.setChecked("SI" in sg(26).upper())
            self.d_medios_check.setChecked("SI" in sg(27).upper())
            self.d_extra_notes.setText(sg(28))
        else:
            self.has_delivery_check.setChecked(False)
            for w in (self.d_street_input, self.d_zip_input, self.d_name_input,
                      self.d_contact_name, self.d_phone_input):
                w.clear()
            self.d_extra_notes.clear()

        # Configurar UID del lead y marcar como revisando
        uid = _lead_key(row)
        self._current_lead_uid = uid
        
        status_info = self._leads_status.get(uid, {})
        if status_info.get('status', 'pendiente') == 'pendiente':
            self._leads_status[uid] = {
                'status': 'revisando',
                'last_update': datetime.now().isoformat()
            }
            _save_leads_status(self._leads_status)

        self.tabs.setCurrentIndex(2)

        QMessageBox.information(
            self, "Datos Cargados",
            f"✅ Datos de <b>{sg(1)}</b> cargados en el formulario.\n"
            "Ve a la pestaña 'Fiscal y Contacto' para revisar y completar,\n"
            "luego pulsa '🚀 Procesar en Odoo'.")
