import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QFrame,
    QFormLayout, QComboBox, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
import bur2000_theme
from db.services.odoo_service_v2 import OdooServiceV2
from db.services.customer_local_db import CustomerLocalDB
from db.services.commercial_conditions_service import DiscountProposalService
from loguru import logger
from dotenv import load_dotenv, set_key
import db.commercial_rules as rules

class AdminTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_settings()
        self._build_ui()

    def _load_settings(self):
        load_dotenv(override=True)
        self.url = os.getenv("ODOO_URL", "")
        self.db = os.getenv("ODOO_DB", "")
        self.user = os.getenv("ODOO_USER", "")
        self.password = os.getenv("ODOO_PASS", "")
        self.ai_provider = os.getenv("AI_PROVIDER", "OpenAI")
        self.ai_api_key = os.getenv("AI_API_KEY", "")

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll Area for the whole page
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background-color: {bur2000_theme.BUR.background};")
        
        container = QWidget()
        container.setStyleSheet(f"background-color: {bur2000_theme.BUR.background};")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(25)
        container_layout.setAlignment(Qt.AlignHCenter) # Center cards horizontally

        max_width = 850
        input_style = f"""
            QLineEdit, QComboBox {{
                padding: 10px;
                border: 1px solid {bur2000_theme.BUR.border};
                border-radius: 6px;
                background-color: white;
                font-size: 13px;
                selection-background-color: {bur2000_theme.BUR.primary};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 2px solid {bur2000_theme.BUR.secondary};
            }}
        """

        # --- SECTION: ODOO ---
        odoo_group = QFrame()
        odoo_group.setMaximumWidth(max_width)
        odoo_group.setStyleSheet(bur2000_theme.BUR.card_style)
        odoo_layout = QVBoxLayout(odoo_group)
        odoo_layout.setContentsMargins(30, 30, 30, 30)
        
        o_title = QLabel("⚙️ Conexión con Odoo")
        o_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary}; margin-bottom: 15px;")
        odoo_layout.addWidget(o_title)

        o_form = QFormLayout()
        o_form.setSpacing(15)
        o_form.setLabelAlignment(Qt.AlignRight)
        
        self.edit_url = QLineEdit(self.url)
        self.edit_url.setPlaceholderText("https://ejemplo.odoo.com")
        self.edit_url.setStyleSheet(input_style)
        
        self.edit_db = QLineEdit(self.db)
        self.edit_db.setStyleSheet(input_style)
        
        self.edit_user = QLineEdit(self.user)
        self.edit_user.setStyleSheet(input_style)
        
        self.edit_pass = QLineEdit(self.password)
        self.edit_pass.setEchoMode(QLineEdit.Password)
        self.edit_pass.setStyleSheet(input_style)

        o_form.addRow("🔗 URL del Servidor:", self.edit_url)
        o_form.addRow("📦 Base de Datos:", self.edit_db)
        o_form.addRow("👤 Usuario (Email):", self.edit_user)
        o_form.addRow("🔑 Contraseña:", self.edit_pass)
        odoo_layout.addLayout(o_form)
        
        # Test Connection specifically for Odoo
        odoo_btn_lay = QHBoxLayout()
        self.btn_test = QPushButton("🧪 Probar Conexión")
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.btn_test.setStyleSheet(f"background-color: white; border: 1px solid {bur2000_theme.BUR.primary}; color: {bur2000_theme.BUR.primary}; padding: 8px 20px; font-weight: bold; border-radius: 4px;")
        self.btn_test.clicked.connect(self._test_connection)
        odoo_btn_lay.addStretch()
        odoo_btn_lay.addWidget(self.btn_test)
        odoo_layout.addLayout(odoo_btn_lay)

        container_layout.addWidget(odoo_group)

        # --- SECTION: AI ---
        ai_group = QFrame()
        ai_group.setMaximumWidth(max_width)
        ai_group.setStyleSheet(bur2000_theme.BUR.card_style)
        ai_layout = QVBoxLayout(ai_group)
        ai_layout.setContentsMargins(30, 30, 30, 30)
        
        ai_title_lay = QHBoxLayout()
        ai_title = QLabel("🧠 Inteligencia Artificial")
        ai_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        ai_title_lay.addWidget(ai_title)
        ai_layout.addLayout(ai_title_lay)
        ai_layout.addSpacing(10)

        ai_form = QFormLayout()
        ai_form.setSpacing(15)
        ai_form.setLabelAlignment(Qt.AlignRight)

        self.combo_ai = QComboBox()
        self.combo_ai.addItems(["OpenAI", "Anthropic (Claude)", "Google (Gemini)", "Groq (Ultra-Rápido)", "Ollama (Local)", "Mock (Simulado)"])
        self.combo_ai.setCurrentText(self.ai_provider)
        self.combo_ai.setStyleSheet(input_style)
        
        self.edit_ai_key = QLineEdit(self.ai_api_key)
        self.edit_ai_key.setEchoMode(QLineEdit.Password)
        self.edit_ai_key.setPlaceholderText("Pegue su API Key aquí...")
        self.edit_ai_key.setStyleSheet(input_style)
        
        ai_form.addRow("🤖 Proveedor:", self.combo_ai)
        ai_form.addRow("🔑 API Key:", self.edit_ai_key)
        ai_layout.addLayout(ai_form)
        
        container_layout.addWidget(ai_group)

        # --- SECTION: MAINTENANCE ---
        maint_group = QFrame()
        maint_group.setMaximumWidth(max_width)
        maint_group.setStyleSheet(bur2000_theme.BUR.card_style)
        maint_layout = QHBoxLayout(maint_group)
        maint_layout.setContentsMargins(30, 20, 30, 20)
        
        m_info = QVBoxLayout()
        m_title = QLabel("📚 Políticas Comerciales")
        m_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {bur2000_theme.BUR.text};")
        m_desc = QLabel("Estado: Política 2026 activa y operativa.")
        m_desc.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 12px;")
        m_info.addWidget(m_title)
        m_info.addWidget(m_desc)
        
        self.btn_sync = QPushButton("🔄 Sincronizar Ahora")
        self.btn_sync.setCursor(Qt.PointingHandCursor)
        self.btn_sync.setStyleSheet(bur2000_theme.BUR.button_secondary)
        self.btn_sync.clicked.connect(self._sync_policies)
        
        maint_layout.addLayout(m_info)
        maint_layout.addStretch()
        maint_layout.addWidget(self.btn_sync)
        
        container_layout.addWidget(maint_group)

        # --- SECTION: LOCAL DB CLIENTES ---
        localdb_group = QFrame()
        localdb_group.setMaximumWidth(max_width)
        localdb_group.setStyleSheet(bur2000_theme.BUR.card_style)
        localdb_layout = QVBoxLayout(localdb_group)
        localdb_layout.setContentsMargins(30, 30, 30, 30)
        localdb_layout.setSpacing(12)

        # Cabecera
        ldb_hdr = QHBoxLayout()
        ldb_title = QLabel("📋 Clientes Dados de Alta (BD Local)")
        ldb_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        self._ldb_count_lbl = QLabel("")
        self._ldb_count_lbl.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 12px;")
        ldb_hdr.addWidget(ldb_title)
        ldb_hdr.addStretch()
        ldb_hdr.addWidget(self._ldb_count_lbl)
        localdb_layout.addLayout(ldb_hdr)

        # Buscador
        search_row = QHBoxLayout()
        self._ldb_search = QLineEdit()
        self._ldb_search.setPlaceholderText("🔍  Buscar por NIF o nombre...")
        self._ldb_search.setStyleSheet(input_style)
        self._ldb_search.returnPressed.connect(self._search_local_customers)
        btn_search = QPushButton("Buscar")
        btn_search.setCursor(Qt.PointingHandCursor)
        btn_search.setStyleSheet(bur2000_theme.BUR.button_secondary)
        btn_search.clicked.connect(self._search_local_customers)
        btn_reload = QPushButton("🔄 Recargar")
        btn_reload.setCursor(Qt.PointingHandCursor)
        btn_reload.setStyleSheet(bur2000_theme.BUR.button_secondary)
        btn_reload.clicked.connect(self._load_local_customers)
        btn_open_folder = QPushButton("📁 Abrir carpeta BD")
        btn_open_folder.setCursor(Qt.PointingHandCursor)
        btn_open_folder.setStyleSheet(bur2000_theme.BUR.button_secondary)
        btn_open_folder.clicked.connect(self._open_local_db_folder)
        search_row.addWidget(self._ldb_search)
        search_row.addWidget(btn_search)
        search_row.addWidget(btn_reload)
        search_row.addWidget(btn_open_folder)
        localdb_layout.addLayout(search_row)

        # Tabla
        cols = ["NIF", "Nombre", "Tipo", "Comercial", "Ciudad", "CP",
                "Email", "Teléfono", "Acción", "Fecha", "Odoo ID"]
        self._ldb_table = QTableWidget(0, len(cols))
        self._ldb_table.setHorizontalHeaderLabels(cols)
        self._ldb_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._ldb_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._ldb_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._ldb_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._ldb_table.verticalHeader().setVisible(False)
        self._ldb_table.setAlternatingRowColors(True)
        self._ldb_table.setMinimumHeight(220)
        self._ldb_table.setStyleSheet("""
            QTableWidget { border: 1px solid #e0e0e0; border-radius: 4px; font-size: 12px; }
            QHeaderView::section { background: #f5f5f5; font-weight: bold; padding: 6px; border: none; border-bottom: 1px solid #ddd; }
            QTableWidget::item:selected { background-color: #e3f2fd; color: black; }
        """)
        localdb_layout.addWidget(self._ldb_table)
        container_layout.addWidget(localdb_group)
        self._load_local_customers()

        # --- SECTION: DISCOUNT PROPOSAL 2026 ---
        proposal_group = QFrame()
        proposal_group.setMaximumWidth(max_width)
        proposal_group.setStyleSheet(bur2000_theme.BUR.card_style)
        proposal_layout = QVBoxLayout(proposal_group)
        proposal_layout.setContentsMargins(30, 30, 30, 30)
        proposal_layout.setSpacing(12)

        # Header
        prop_hdr = QHBoxLayout()
        prop_title = QLabel("💰 Propuesta de Descuentos 2026")
        prop_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        self._prop_count_lbl = QLabel("")
        self._prop_count_lbl.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 12px;")
        prop_hdr.addWidget(prop_title)
        prop_hdr.addStretch()
        prop_hdr.addWidget(self._prop_count_lbl)
        proposal_layout.addLayout(prop_hdr)

        # Search / Filter
        prop_search_row = QHBoxLayout()
        self._prop_search = QLineEdit()
        self._prop_search.setPlaceholderText("🔍  Filtrar por familia o segmento...")
        self._prop_search.setStyleSheet(input_style)
        self._prop_search.textChanged.connect(self._filter_proposal_data)
        btn_prop_reload = QPushButton("🔄 Recargar Excel")
        btn_prop_reload.setCursor(Qt.PointingHandCursor)
        btn_prop_reload.setStyleSheet(bur2000_theme.BUR.button_secondary)
        btn_prop_reload.clicked.connect(self._load_proposal_data)
        prop_search_row.addWidget(self._prop_search)
        prop_search_row.addWidget(btn_prop_reload)
        proposal_layout.addLayout(prop_search_row)

        # Table
        prop_cols = ["Segmento", "Familia", "Desde (€)", "Hasta (€)", "DTO Min P", "DTO Max P", "DTO Min B", "DTO Max B"]
        self._prop_table = QTableWidget(0, len(prop_cols))
        self._prop_table.setHorizontalHeaderLabels(prop_cols)
        self._prop_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._prop_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._prop_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._prop_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._prop_table.verticalHeader().setVisible(False)
        self._prop_table.setAlternatingRowColors(True)
        self._prop_table.setMinimumHeight(300)
        self._prop_table.setStyleSheet(self._ldb_table.styleSheet())
        proposal_layout.addWidget(self._prop_table)
        
        container_layout.addWidget(proposal_group)
        self._cached_proposal_data = [] # Store records for filtering
        self._load_proposal_data()

        # Bottom stretch
        container_layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # FIXED BOTTOM ACTION BAR
        action_bar = QFrame()
        action_bar.setFixedHeight(70)
        action_bar.setStyleSheet(f"background-color: white; border-top: 1px solid {bur2000_theme.BUR.border};")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(40, 0, 40, 0)
        
        help_warn = QLabel("⚠️ Recuerda reiniciar tras cambiar datos de conexión.")
        help_warn.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-style: italic;")
        action_layout.addWidget(help_warn)
        action_layout.addStretch()
        
        self.btn_save = QPushButton("💾 GUARDAR TODO")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setMinimumWidth(200)
        self.btn_save.setMinimumHeight(45)
        self.btn_save.setStyleSheet(bur2000_theme.BUR.button_primary)
        self.btn_save.clicked.connect(self._save_settings)
        action_layout.addWidget(self.btn_save)
        
        main_layout.addWidget(action_bar)

    def _test_connection(self):
        url = self.edit_url.text().strip()
        db = self.edit_db.text().strip()
        user = self.edit_user.text().strip()
        pwd = self.edit_pass.text().strip()

        if not all([url, db, user, pwd]):
            QMessageBox.warning(self, "Campos incompletos", "Por favor completa todos los campos de Odoo.")
            return

        self.btn_test.setEnabled(False)
        self.btn_test.setText("⏳ Conectando...")
        
        try:
            test_service = OdooServiceV2(url=url, db=db, username=user, password=pwd)
            if test_service.connect():
                QMessageBox.information(self, "Conexión OK", "Conexión con Odoo establecida con éxito.")
            else:
                QMessageBox.critical(self, "Fallo", "No se pudo conectar. Revisa URL, DB y Credenciales.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Fallo crítico: {e}")
        finally:
            self.btn_test.setEnabled(True)
            self.btn_test.setText("🧪 Probar Conexión")

    def _save_settings(self):
        url = self.edit_url.text().strip()
        db = self.edit_db.text().strip()
        user = self.edit_user.text().strip()
        pwd = self.edit_pass.text().strip()
        ai_prov = self.combo_ai.currentText()
        ai_key = self.edit_ai_key.text().strip()

        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
        
        try:
            set_key(env_path, "ODOO_URL", url)
            set_key(env_path, "ODOO_DB", db)
            set_key(env_path, "ODOO_USER", user)
            set_key(env_path, "ODOO_PASS", pwd)
            set_key(env_path, "AI_PROVIDER", ai_prov)
            set_key(env_path, "AI_API_KEY", ai_key)
            
            QMessageBox.information(self, "Guardado", "Configuración actualizada. Aplica tras reiniciar.")
            logger.info("Admin UI: Settings saved successfully.")
        except Exception as e:
            logger.error(f"Error saving: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def _sync_policies(self):
        try:
            self.btn_sync.setEnabled(False)
            rules.load_from_json()
            QMessageBox.information(self, "Sincronizado", "Reglas comerciales recargadas correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo sincronizar: {e}")
        finally:
            self.btn_sync.setEnabled(True)

    # ------------------------------------------------------------------ #
    #  Base de datos local de clientes                                    #
    # ------------------------------------------------------------------ #
    def _populate_ldb_table(self, rows):
        """Rellena self._ldb_table con una lista de dicts de clientes."""
        self._ldb_table.setRowCount(0)
        for rec in rows:
            r = self._ldb_table.rowCount()
            self._ldb_table.insertRow(r)
            values = [
                rec.get("nif", ""),
                rec.get("nombre", ""),
                rec.get("tipo_cliente", ""),
                rec.get("comercial", ""),
                rec.get("ciudad", ""),
                rec.get("cp", ""),
                rec.get("email", ""),
                rec.get("telefono", ""),
                rec.get("accion", ""),
                (rec.get("fecha_mod") or rec.get("fecha_alta") or "")[:10],
                str(rec.get("odoo_partner_id") or ""),
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                # Colorear fila según acción
                if rec.get("accion") == "alta":
                    item.setForeground(QColor("#1565C0"))   # azul → nueva
                self._ldb_table.setItem(r, c, item)

    def _load_local_customers(self):
        try:
            db = CustomerLocalDB()
            rows = db.get_all(limit=500)
            self._populate_ldb_table(rows)
            total = db.count()
            self._ldb_count_lbl.setText(f"Total: {total} cliente(s)")
        except Exception as e:
            logger.error(f"[AdminTab] Error cargando BD local: {e}")
            self._ldb_count_lbl.setText("(sin datos)")

    def _search_local_customers(self):
        query = self._ldb_search.text().strip()
        if not query:
            self._load_local_customers()
            return
        try:
            db = CustomerLocalDB()
            # Buscar por NIF exacto primero, luego por nombre
            by_nif = db.search_by_nif(query)
            if by_nif:
                rows = [by_nif]
            else:
                rows = db.search_by_name(query)
            self._populate_ldb_table(rows)
            self._ldb_count_lbl.setText(f"{len(rows)} resultado(s) para '{query}'")
        except Exception as e:
            logger.error(f"[AdminTab] Error buscando en BD local: {e}")

    def _open_local_db_folder(self):
        try:
            db = CustomerLocalDB()
            folder = os.path.dirname(db.db_path)
            os.startfile(folder)   # Windows: abre el explorador
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir la carpeta: {e}")

    # ------------------------------------------------------------------ #
    #  Propuesta de Descuentos 2026                                      #
    # ------------------------------------------------------------------ #
    def _load_proposal_data(self):
        try:
            svc = DiscountProposalService()
            self._cached_proposal_data = svc.get_proposal_data()
            self._prop_count_lbl.setText(svc.get_summary_stats())
            self._filter_proposal_data()
        except Exception as e:
            logger.error(f"[AdminTab] Error loading proposal Excel: {e}")
            self._prop_count_lbl.setText("Error al cargar Excel")

    def _filter_proposal_data(self):
        query = self._prop_search.text().lower().strip()
        self._prop_table.setRowCount(0)
        
        for rec in self._cached_proposal_data:
            segmento = str(rec.get("Segmento", "")).lower()
            familia = str(rec.get("Familia", "")).lower()
            
            if query and query not in segmento and query not in familia:
                continue
                
            r = self._prop_table.rowCount()
            self._prop_table.insertRow(r)
            
            # Formatear números
            desde = f"{rec.get('Base imponible desde (EUR)', 0):,.2f}€"
            hasta = rec.get('Base imponible hasta (EUR)', "")
            hasta_str = f"{hasta:,.2f}€" if isinstance(hasta, (int, float)) else "Abierto"
            
            dto_min_p = f"{rec.get('DTO mínimo Península (%)', 0)}%"
            dto_max_p = f"{rec.get('DTO máximo Península (%)', 0)}%"
            dto_min_b = f"{rec.get('DTO mínimo Baleares (%)', 0)}%"
            dto_max_b = f"{rec.get('DTO máximo Baleares (%)', 0)}%"
            
            values = [
                rec.get("Segmento", ""),
                rec.get("Familia", ""),
                desde,
                hasta_str,
                dto_min_p,
                dto_max_p,
                dto_min_b,
                dto_max_b
            ]
            
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if c >= 2: # Alineación numérica para importes y porcentajes
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._prop_table.setItem(r, c, item)
