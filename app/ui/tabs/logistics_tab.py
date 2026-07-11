from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFrame, QAbstractItemView, QDialog,
    QLineEdit, QComboBox, QFileDialog

)
from PySide6.QtCore import Qt, QTimer, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
import bur2000_theme
from db.services.logistics_service import LogisticsService
from db.services.commercial_service import CommercialService
from ui.dialogs.logistics_email_wizard import LogisticsEmailWizard
from ui.workers.odoo_worker import OdooWorker
from loguru import logger

class LogisticsTab(QWidget):
    def __init__(self, conn=None, odoo_service=None, parent=None):
        super().__init__(parent)
        self.odoo = odoo_service
        self.logic = LogisticsService(odoo_service) if odoo_service else None
        self.all_pickings = []
        self.filtered_pickings = []
        self.threadpool = QThreadPool()
        
        self._build_ui()
        
        # Auto-refresh timer (1 minute aggressive polling)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(60 * 1000)

        
        # Immediate refresh on start
        QTimer.singleShot(500, self.refresh_data)
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # --- KPI DASHBOARD ---
        kpi_layout = QHBoxLayout()
        self.kpi_waiting = self._create_kpi_card("⏳ Pendientes", "0", bur2000_theme.BUR.STATUS_WAITING)
        self.kpi_ready = self._create_kpi_card("✅ Preparados", "0", bur2000_theme.BUR.STATUS_READY)
        self.kpi_total = self._create_kpi_card("📦 Total", "0", bur2000_theme.BUR.blue)
        
        kpi_layout.addWidget(self.kpi_waiting)
        kpi_layout.addWidget(self.kpi_ready)
        kpi_layout.addWidget(self.kpi_total)
        layout.addLayout(kpi_layout)
        
        # --- SEARCH & CONTROLS ---
        controls = QHBoxLayout()
        
        # Warehouse Selector
        self.wh_selector = QComboBox()
        operational_warehouses = ["Abrera", "Pinto", "Valencia"]
        for wh_name in self.logic.WAREHOUSES.keys():
            if wh_name in operational_warehouses:
                self.wh_selector.addItem(wh_name)
        self.wh_selector.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.wh_selector.currentIndexChanged.connect(self.refresh_data)
        controls.addWidget(QLabel("📍 Almacén:"))
        controls.addWidget(self.wh_selector, 1)

        # Origin Filter
        self.origin_selector = QComboBox()
        self.origin_selector.addItems(["Todos", "Salidas (OUT)", "Entradas (INT)"])
        self.origin_selector.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.origin_selector.currentIndexChanged.connect(self._filter_data)
        controls.addWidget(QLabel("📦 Origen:"))
        controls.addWidget(self.origin_selector, 1)

        # Status Filter
        self.status_selector = QComboBox()
        self.status_selector.addItems(["Todos los Estados", "Pendientes", "Preparados", "Completados", "Cancelados"])
        self.status_selector.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.status_selector.currentIndexChanged.connect(self._filter_data)
        controls.addWidget(QLabel("🚦 Estado:"))
        controls.addWidget(self.status_selector, 1)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Buscar por cliente, origen o transportista...")
        self.search_bar.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.search_bar.textChanged.connect(self._filter_data)
        controls.addWidget(self.search_bar, 3)
        
        controls.addStretch(1)
        
        self.btn_refresh = QPushButton("🔄 Sincronizar")
        self.btn_refresh.setStyleSheet(bur2000_theme.BUR.button_secondary)
        self.btn_refresh.clicked.connect(self.refresh_data)
        controls.addWidget(self.btn_refresh)

        # BUG-005: Botón cancelar — visible solo durant la carga
        self.btn_cancel = QPushButton("✕ Cancelar")
        self.btn_cancel.setStyleSheet(
            "background-color: #dc3545; color: white; border-radius: 4px; "
            "font-weight: bold; padding: 6px 12px; border: none;"
        )
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_refresh)
        controls.addWidget(self.btn_cancel)
        
        self.btn_export = QPushButton("📊 Exportar Excel")
        self.btn_export.setStyleSheet(bur2000_theme.BUR.button_secondary)
        self.btn_export.clicked.connect(self._export_to_excel)
        controls.addWidget(self.btn_export)
        
        layout.addLayout(controls)

        
        # --- TABLE ---
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["Referencia", "Cliente", "Almacén", "Origen", "Transportista", "Estado", "Doc", "Email", "Incidencia"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 100) # Almacén
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(6, 110) # Doc
        self.table.setColumnWidth(7, 80) # Email
        self.table.setColumnWidth(8, 130) # Incidencia
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed) # Doc Fixed
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed) # Email Fixed
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed) # Incidencia Fixed
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{ 
                gridline-color: {bur2000_theme.BUR.border}; 
                background-color: white;
                alternate-background-color: {bur2000_theme.BUR.background};
                border: 1px solid {bur2000_theme.BUR.border}; 
                color: {bur2000_theme.BUR.text};
            }} 
            QHeaderView::section {{ 
                background-color: {bur2000_theme.BUR.background}; 
                padding: 10px; 
                border: none;
                border-bottom: 2px solid {bur2000_theme.BUR.border};
                font-weight: bold;
            }}
        """)
        layout.addWidget(self.table)
        
        # New: Incidence & Commercial Service
        from db.services.incidence_service import IncidenceService
        self.incidence_service = IncidenceService(self.odoo)
        self.comm_service = CommercialService(self.odoo)

    def _create_kpi_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white; 
                border-radius: 4px; 
                border-bottom: 3px solid {color};
                padding: 5px;
            }}
        """)
        lay = QVBoxLayout(card)
        t = QLabel(title)
        t.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 13px; font-weight: 800; text-transform: uppercase;")
        v = QLabel(value)
        v.setStyleSheet(f"color: {bur2000_theme.BUR.text}; font-size: 28px; font-weight: bold;")
        lay.addWidget(t)
        lay.addWidget(v)
        card.value_label = v 
        return card

    def _create_status_badge(self, state):
        badge = QLabel(state.upper())
        color = bur2000_theme.BUR.STATUS_DRAFT
        if state == 'assigned': color = bur2000_theme.BUR.STATUS_READY
        elif state in ['waiting', 'confirmed', 'partially_available']: color = bur2000_theme.BUR.STATUS_WAITING
        elif state == 'done': color = bur2000_theme.BUR.STATUS_READY # Using ready color or primary for completed
        elif state == 'draft': color = bur2000_theme.BUR.muted
        elif state == 'cancel': color = bur2000_theme.BUR.STATUS_ERROR


        
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background-color: {color}22; color: {color}; border-radius: 4px; font-weight: 800; font-size: 10px; padding: 2px; border: 2px solid {color};")
        badge.setFixedSize(90, 22)
        
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(badge)
        return container

    def refresh_data(self):
        """Spawns a background worker to fetch data from Odoo."""
        if not self.btn_refresh.isEnabled():
            return
        
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳ Cargando...")
        self.btn_cancel.setVisible(True)  # BUG-005: mostrar botón cancelar
        
        wh_name = self.wh_selector.currentText()
        wh_prefix = self.logic.WAREHOUSES.get(wh_name, "MAD3/")
        
        # Create worker
        self.worker = OdooWorker(self.logic.get_pickings, wh_prefix)
        self.worker.signals.result.connect(self._on_refresh_finished)
        self.worker.signals.error.connect(self._on_refresh_error)
        self.worker.signals.finished.connect(self._on_refresh_completed)
        
        self.threadpool.start(self.worker)

        # BUG-005: Timeout de seguridad (45s) — restaurar botón si el worker se cuelga
        if not hasattr(self, '_safety_timer'):
            self._safety_timer = QTimer(self)
            self._safety_timer.setSingleShot(True)
            self._safety_timer.timeout.connect(self._on_safety_timeout)
        self._safety_timer.start(45_000)

    def _cancel_refresh(self):
        """Cancela el worker actual y restaura el estado del botón (BUG-005)."""
        if hasattr(self, '_safety_timer'):
            self._safety_timer.stop()
        self._on_refresh_completed()
        logger.warning("[LogisticsTab] Sincronización cancelada por el usuario.")

    def _on_safety_timeout(self):
        """Si el worker no terminó en 45s, restaurar UI (BUG-005)."""
        logger.error("[LogisticsTab] Worker de sincronización agotado (timeout 45s). Restaurando UI.")
        self._on_refresh_completed()

    def _on_refresh_finished(self, data):
        self.all_pickings = data
        self._update_kpis()
        self._filter_data()

    def _on_refresh_error(self, error_msg):
        logger.error(f"Logistics: Refresh Error: {error_msg}")

    def _on_refresh_completed(self):
        """Restaura botón Sincronizar y oculta el botón Cancelar (BUG-005)."""
        if hasattr(self, '_safety_timer'):
            self._safety_timer.stop()
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 Sincronizar")
        self.btn_cancel.setVisible(False)

    def _update_kpis(self):
        waiting = len([p for p in self.all_pickings if p['state'] in ['waiting', 'confirmed', 'partially_available', 'draft']])

        ready = len([p for p in self.all_pickings if p['state'] == 'assigned'])
        
        self.kpi_waiting.value_label.setText(str(waiting))
        self.kpi_ready.value_label.setText(str(ready))
        self.kpi_total.value_label.setText(str(len(self.all_pickings)))

    def _filter_data(self):
        text = self.search_bar.text().lower()
        origin_filter = self.origin_selector.currentText()
        status_filter = self.status_selector.currentText()

        self.filtered_pickings = []
        for p in self.all_pickings:
            # Text search
            match_text = (text in p['name'].lower() or 
                          text in p['partner'].lower() or 
                          text in p['origin'].lower() or 
                          text in p.get('carrier_name', '').lower())
            if not match_text:
                continue
                
            # Origin filter
            if origin_filter == "Salidas (OUT)" and "/OUT/" not in p['name']:
                continue
            if origin_filter == "Entradas (INT)" and "/INT/" not in p['name']:
                continue
                
            # Status filter
            state = p['state']
            if status_filter == "Pendientes" and state not in ['waiting', 'confirmed', 'partially_available', 'draft']:
                continue
            if status_filter == "Preparados" and state != 'assigned':
                continue
            if status_filter == "Completados" and state != 'done':
                continue
            if status_filter == "Cancelados" and state != 'cancel':
                continue
                
            self.filtered_pickings.append(p)
            
        self._update_table()

    def _update_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        current_wh = self.wh_selector.currentText()
        for i, p in enumerate(self.filtered_pickings):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(p['name']))
            self.table.setItem(i, 1, QTableWidgetItem(p.get('partner', '')))
            
            wh_item = QTableWidgetItem(current_wh)
            wh_item.setTextAlignment(Qt.AlignCenter)
            from PySide6.QtGui import QColor
            wh_item.setForeground(QColor(bur2000_theme.BUR.primary))
            self.table.setItem(i, 2, wh_item)
            
            self.table.setItem(i, 3, QTableWidgetItem(p['origin']))
            self.table.setItem(i, 4, QTableWidgetItem(p.get('carrier_name', '')))
            
            # Status Badge
            state = p['state']
            status_widget = self._create_status_badge(state)
            self.table.setItem(i, 5, QTableWidgetItem(state))
            self.table.setCellWidget(i, 5, status_widget)
            
            # PDF Button Container
            btn_container = QWidget()
            btn_lay = QHBoxLayout(btn_container)
            btn_lay.setContentsMargins(0, 0, 0, 0)
            btn_lay.setSpacing(4)

            # 1. VER PDF Button
            btn_pdf = QPushButton("VER PDF 📄")
            btn_pdf.setToolTip("Pulsar para abrir albarán")
            btn_pdf.setFixedWidth(75)
            btn_pdf.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bur2000_theme.BUR.secondary};
                    color: {bur2000_theme.BUR.primary};
                    border: 2px solid {bur2000_theme.BUR.primary};
                    font-size: 10px;
                    font-weight: 900;
                    padding: 4px;
                    border-radius: 4px;
                }}
                QPushButton:hover {{ background-color: white; }}
            """)
            btn_pdf.clicked.connect(lambda chk=False, pick=p: self._view_pdf(pick))
            
            # 2. Open Folder Button
            btn_fold = QPushButton("📂")
            btn_fold.setToolTip("Abrir carpeta de exportaciones")
            btn_fold.setFixedWidth(30)
            btn_fold.setStyleSheet(f"background-color: white; border: 1px solid {bur2000_theme.BUR.border}; padding: 4px; border-radius: 4px;")
            btn_fold.clicked.connect(self._open_exports_folder)
            
            btn_lay.addWidget(btn_pdf)
            btn_lay.addWidget(btn_fold)
            
            self.table.setItem(i, 6, QTableWidgetItem(""))
            self.table.setCellWidget(i, 6, btn_container)
            
            # Email Button
            btn_email = QPushButton("📤 Enviar")
            btn_email.setStyleSheet(f"background-color: {bur2000_theme.BUR.lvl1}; border: 1px solid {bur2000_theme.BUR.border};")
            btn_email.clicked.connect(lambda chk=False, pick=p: self._open_wizard(pick))
            self.table.setItem(i, 7, QTableWidgetItem(""))
            self.table.setCellWidget(i, 7, btn_email)
            
            # --- Incidence Button / Status - USE PRE-FETCHED DATA ---
            existing = p.get('incidence')
            
            btn_inc = QPushButton()
            if not existing:
                btn_inc.setText("⚠️ Crear Incidencia")
                btn_inc.setStyleSheet(f"background-color: {bur2000_theme.BUR.lvl2}; border: 1px solid {bur2000_theme.BUR.border}; color: {bur2000_theme.BUR.text}; font-size: 11px; font-weight: bold;")
            else:
                status_text = existing['stage_id'][1]
                btn_inc.setText(f"🎫 {status_text}")
                color = bur2000_theme.BUR.STATUS_WAITING
                if "progreso" in status_text.lower() or "en análisis" in status_text.lower(): color = bur2000_theme.BUR.blue
                elif "Hecho" in status_text or "Resuelto" in status_text or "Cerrado" in status_text: color = bur2000_theme.BUR.STATUS_READY
                
                btn_inc.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold; font-size: 11px; border: none; border-radius: 4px;")
            
            self.table.setItem(i, 8, QTableWidgetItem(status_text if existing else ""))
            
            # --- Commercial Compliance Block - USE PRE-FETCHED DATA ---
            compliance = p.get('compliance', 'UNKNOWN')
            if compliance == 'BLOQUEADO':
                btn_email.setEnabled(False)
                btn_email.setToolTip("⚠️ Bloqueado por Control Comercial (Disonancia en descuentos)")
                btn_email.setText("🚫 Bloqueado")
                btn_email.setStyleSheet(f"background-color: {bur2000_theme.BUR.STATUS_ERROR}; color: white; border: none;")
            
            btn_inc.clicked.connect(lambda chk=False, pick=p: self._manage_incidence(pick))
            self.table.setCellWidget(i, 8, btn_inc)
            
        self.table.setSortingEnabled(True)

    def _view_pdf(self, picking):
        """Ultra-robust opening logic using system explorer."""
        import os
        import subprocess
        try:
            success, info = self.logic.open_picking_pdf(picking['external_id'], picking['name'])
            if not success:
                QMessageBox.critical(self, "Error Odoo", info)
                return

            filepath = info
            # Method 0: Verify existence
            if not os.path.exists(filepath):
                QMessageBox.warning(self, "Error", f"El archivo no se encuentra en el disco:\n{filepath}")
                return

            # Method 1: os.startfile (Standard)
            try:
                os.startfile(filepath)
                return
            except: pass

            # Method 2: CMD Start (Force opening via shell)
            try:
                import subprocess
                subprocess.run(f'cmd /c start "" "{filepath}"', shell=True, check=True)
                return
            except Exception as e:
                logger.error(f"CMD Start failed: {e}")

            # Method 3: Explorer (Open folder with file selected as fallback)
            try:
                subprocess.run(['explorer', '/select,', filepath])
            except: pass
            
            QMessageBox.information(self, "PDF Descargado", f"El archivo se ha guardado pero Windows no permite abrirlo automáticamente.\n\nSe ha abierto la carpeta de descargas.\n\nRuta: {filepath}")

        except Exception as e:
            QMessageBox.warning(self, "Error de Apertura", f"Error crítico: {e}")

    def _open_exports_folder(self):
        """Opens the exports folder in Windows Explorer."""
        import os
        import subprocess
        try:
            # Consistent with logistics_service root calculation
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            export_dir = os.path.join(root_dir, "exports")
            if not os.path.exists(export_dir):
                os.makedirs(export_dir, exist_ok=True)
            
            subprocess.run(['explorer', export_dir])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir la carpeta: {e}")

    def _open_wizard(self, picking):
        """Prepares email data and opens the LogisticsEmailWizard."""
        try:
            data = self.logic.prepare_email_data(picking)
            wizard = LogisticsEmailWizard(data, self.logic, self)
            if wizard.exec() == QDialog.Accepted:

                final_data = wizard.get_final_data()
                success, error_msg = self.logic.execute_workflow(
                    picking_id=data['picking_id'],
                    to_email=final_data['to'],
                    cc_emails=final_data['cc'],
                    subject=final_data['subject'],
                    body=final_data['body'],
                    is_recoge=final_data['is_recoge']
                )
                
                if success:
                    QMessageBox.information(self, "Éxito", "El albarán ha sido enviado correctamente y se han creado las actividades en Odoo.")
                    self.refresh_data()
                else:
                    detail = error_msg or "Error desconocido."
                    logger.error(f"[LogisticsTab] Fallo al enviar albarán: {detail}")
                    QMessageBox.critical(
                        self, "Error al enviar albarán",
                        f"No se pudo enviar el albarán a Odoo.\n\n"
                        f"<b>Motivo:</b> {detail}\n\n"
                        f"Verifique la conexión con Odoo e inténtelo de nuevo."
                    )
        except Exception as e:
            logger.error(f"Error in _open_wizard: {e}")
            QMessageBox.critical(self, "Error", f"Ocurrió un error al abrir el asistente: {e}")

    def _manage_incidence(self, picking):
        # 1. Use pre-fetched sale_name to avoid a redundant Odoo call in the main thread
        so_name = picking.get('sale_name', '').strip()

        # 2. Fallback: if not in the dict, try the origin field (e.g. "S049404")
        if not so_name:
            so_name = picking.get('origin', '').strip()

        # 3. If still empty, let user input the SO reference manually
        if not so_name:
            from PySide6.QtWidgets import QInputDialog
            so_name, ok = QInputDialog.getText(
                self,
                "Referencia del Pedido",
                f"No se encontró un Pedido de Venta vinculado automáticamente a «{picking['name']}».\n\n"
                "Introduce manualmente la referencia del pedido (ej: S049404):"
            )
            if not ok or not so_name.strip():
                return
            so_name = so_name.strip()
            
        # Check rule: 1 incidence per SO
        existing = self.incidence_service.get_ticket_by_so(so_name)
        if existing:
            QMessageBox.information(self, "Aviso", f"Ya existe una incidencia abierta para este pedido: {existing['number']}\nEtapa: {existing['stage_id'][1]}")
            return
            
        # Open Wizard
        from ui.dialogs.incidence_wizard import IncidenceWizard
        data = {
            'picking_id': picking['external_id'],
            'picking_name': picking['name'],
            'so_name': so_name
        }
        wizard = IncidenceWizard(data, self)
        if wizard.exec() == QDialog.Accepted:
            f = wizard.get_data()
            ticket_id = self.incidence_service.create_incidence(f)
            if ticket_id:
                QMessageBox.information(self, "Éxito", f"Incidencia creada correctamente.")
            else:
                QMessageBox.critical(self, "Error Odoo", "No se pudo crear la incidencia.\n\nEs probable que el usuario de Odoo no tenga permisos suficientes para crear Tickets de Helpdesk.")

    def _export_to_excel(self):
        """Export current filtered pickings to Excel."""
        if not self.filtered_pickings:
            QMessageBox.warning(self, "Sin datos", "No hay datos para exportar.")
            return

        try:
            import pandas as pd
        except ImportError:
            QMessageBox.critical(self, "Librería faltante", "Para exportar a Excel necesitas instalar 'pandas' y 'openpyxl'.\n\nPor favor, ejecuta Gabriela.bat para actualizar.")
            return

        from datetime import datetime
        default_name = f"Logistica_{self.wh_selector.currentText()}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Excel Logística", default_name, "Excel Files (*.xlsx)")
        
        if not path:
            return

        try:
            rows = []
            for p in self.filtered_pickings:
                rows.append({
                    'Referencia': p['name'],
                    'Almacén': self.wh_selector.currentText(),
                    'Origen': p['origin'],
                    'Cliente': p['partner'],
                    'Transportista': p['carrier'],
                    'Estado': p['state_desc'],
                    'Fecha': p['date']
                })
            
            df = pd.DataFrame(rows)
            df.to_excel(path, index=False)
            QMessageBox.information(self, "Éxito", f"Archivo guardado correctamente en:\n{path}")
            import os
            os.startfile(os.path.dirname(path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Fallo al exportar: {e}")


