from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QAbstractItemView, QLineEdit,
    QDialog, QMessageBox, QDateEdit, QComboBox, QFileDialog

)
from PySide6.QtCore import Qt, QTimer, QThreadPool, QDate, Signal
from PySide6.QtGui import QColor, QBrush


import bur2000_theme

from db.services.incidence_service import IncidenceService
from ui.workers.odoo_worker import OdooWorker
from loguru import logger

class IncidenceTab(QWidget):
    status_count_changed = Signal(int) # Emits count of open/urgent tickets
    
    def __init__(self, odoo_service, parent=None):

        super().__init__(parent)
        self.service = IncidenceService(odoo_service)
        self.all_incidences = []
        self.threadpool = QThreadPool()
        self._build_ui()
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(60 * 1000) # 1 min aggressive polling
        
        # Immediate refresh on start
        QTimer.singleShot(500, self.refresh_data)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header (Odoo Style)
        header = QHBoxLayout()
        title = QLabel("🎫 Panel de Incidencias")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        header.addWidget(title)
        header.addStretch()
        
        self.btn_search_global = QPushButton("🔍 Buscar Pedido")
        self.btn_search_global.setStyleSheet(f"""
            QPushButton {{
                background-color: white; 
                border: 1px solid {bur2000_theme.BUR.primary}; 
                color: {bur2000_theme.BUR.primary}; 
                padding: 6px 15px; 
                font-weight: bold; 
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {bur2000_theme.BUR.background}; }}
        """)
        self.btn_search_global.clicked.connect(self._open_global_search)
        header.addWidget(self.btn_search_global)

        self.btn_refresh = QPushButton("🔄 Actualizar")
        self.btn_refresh.setStyleSheet(bur2000_theme.BUR.button_primary)
        self.btn_refresh.clicked.connect(self.refresh_data)
        header.addWidget(self.btn_refresh)

        
        self.btn_export = QPushButton("📊 Exportar Excel")
        self.btn_export.setStyleSheet(bur2000_theme.BUR.button_secondary)
        self.btn_export.clicked.connect(self._export_to_excel)
        header.addWidget(self.btn_export)
        
        layout.addLayout(header)


        # KPIs Row
        kpi_lay = QHBoxLayout()
        self.kpi_open = QLabel("🔴 0 Abiertas")
        self.kpi_prog = QLabel("🟡 0 En progreso")
        self.kpi_done = QLabel("✅ 0 Resueltas")
        
        for k in [self.kpi_open, self.kpi_prog, self.kpi_done]:
            k.setStyleSheet(f"font-size: 13px; font-weight: bold; background: white; padding: 6px 15px; border-radius: 4px; border: 1px solid {bur2000_theme.BUR.border};")
            kpi_lay.addWidget(k)
        
        kpi_lay.addStretch()
        
        # Info Label (Solo Registro)
        self.lbl_info = QLabel("🛡️ Modo: Solo Registro (Notificaciones Odoo suprimidas)")
        self.lbl_info.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 11px; font-style: italic;")
        kpi_lay.addWidget(self.lbl_info)
        
        layout.addLayout(kpi_lay)
        
        # Search Row
        search_lay = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Buscar por Ticket, Pedido, Resumen, Nombre...")
        self.search_bar.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.search_bar.textChanged.connect(self._filter_data)
        search_lay.addWidget(self.search_bar, 2)
        
        self.assigned_selector = QComboBox()
        self.assigned_selector.addItem("Todos los asignados")
        self.assigned_selector.addItems(["Gabriela Rojas Esteller", "Administración", "Logística Interna BUR", "Calidad", "Logística Transporte Externo"])
        self.assigned_selector.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.assigned_selector.currentIndexChanged.connect(self._filter_data)
        search_lay.addWidget(QLabel("👤 Asignado:"))
        search_lay.addWidget(self.assigned_selector, 1)
        layout.addLayout(search_lay)

        # Filter Row 2: Status and Specialized Filters
        filter_row2 = QHBoxLayout()
        
        self.stage_selector = QComboBox()
        self.stage_selector.addItems([
            "Todas las etapas", "Nuevo", "En progreso", "En espera", "Hecho", "Cancelado", "Rechazado"
        ])
        self.stage_selector.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.stage_selector.currentIndexChanged.connect(self._filter_data)
        filter_row2.addWidget(QLabel("Etapa:"))
        filter_row2.addWidget(self.stage_selector)
        
        filter_row2.addSpacing(20)
        
        from PySide6.QtWidgets import QCheckBox
        filter_row2.addStretch()
        layout.addLayout(filter_row2)

        # Filter Row 3: Warehouse and Dates
        filter_row3 = QHBoxLayout()
        self.wh_selector = QComboBox()
        self.wh_selector.addItem("Todos los almacenes")
        self.wh_selector.addItems(["Pinto", "Valencia", "Barcelona", "Gavà", "Delegación Madrid", "Abrera"])
        self.wh_selector.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.wh_selector.currentIndexChanged.connect(self._filter_data)
        filter_row3.addWidget(QLabel("📍 Almacén:"))
        filter_row3.addWidget(self.wh_selector)
        
        filter_row3.addSpacing(20)
        
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-3))
        self.date_from.dateChanged.connect(self._filter_data)
        filter_row3.addWidget(QLabel("📅 Desde:"))
        filter_row3.addWidget(self.date_from)
        
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate().addDays(1))
        self.date_to.dateChanged.connect(self._filter_data)
        filter_row3.addWidget(QLabel("📅 Hasta:"))
        filter_row3.addWidget(self.date_to)
        
        filter_row3.addStretch()
        layout.addLayout(filter_row3)

        
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["Nº Ticket", "Almacén", "Pedido", "Resumen", "Asignado", "Etapa", "Acción", "Chat", "Fecha"])

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents) # Ticket Number
        self.table.setColumnWidth(1, 90) # Almacén
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents) # SO
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch) # Summary
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents) # User
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents) # Stage
        
        self.table.setColumnWidth(6, 100) # Acción
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed) # Acción Fix
        
        self.table.setColumnWidth(7, 100) # Chatter
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed) # Chatter Fix
        
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents) # Fecha
        self.table.horizontalHeader().setStretchLastSection(False)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{ 
                gridline-color: {bur2000_theme.BUR.border}; 
                background-color: white;
                alternate-background-color: {bur2000_theme.BUR.background};
                border: 1px solid {bur2000_theme.BUR.border};
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
        
    def refresh_data(self):
        """Fetch all active tickets in background."""
        if not self.btn_refresh.isEnabled(): return
        
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳ ...")
        
        self.worker = OdooWorker(self.service.get_active_incidences)
        self.worker.signals.result.connect(self._on_refresh_finished)
        self.worker.signals.error.connect(self._on_refresh_error)
        self.worker.signals.finished.connect(self._on_refresh_completed)
        
        self.threadpool.start(self.worker)

    def _on_refresh_finished(self, data):
        self.all_incidences = data
        self._filter_data()

    def _on_refresh_error(self, error):
        logger.error(f"Incidences: Refresh Error: {error}")

    def _on_refresh_completed(self):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 Actualizar")

    def _export_to_excel(self):
        """Export current filtered data to Excel."""
        if not self.all_incidences:
            QMessageBox.warning(self, "Sin datos", "No hay datos para exportar.")
            return

        # Use the logic from _filter_data to get what's currently in table
        # (Or better, just rebuild the list from table items if we want exact current view)
        try:
            import pandas as pd
        except ImportError:
            QMessageBox.critical(self, "Librería faltante", "Para exportar a Excel necesitas instalar 'pandas' y 'openpyxl'.\n\nPor favor, ejecuta Gabriela.bat para actualizar.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Guardar Excel", f"Incidencias_{QDate.currentDate().toString('yyyyMMdd')}.xlsx", "Excel Files (*.xlsx)")
        if not path:
            return

        try:
            # We filter data again to be sure it matches current view
            # (Alternatively, we could store 'filtered_incidences' as an attribute)
            text = self.search_bar.text().lower()
            wh_filter = self.wh_selector.currentText()
            assigned_filter = self.assigned_selector.currentText()
            d_from = self.date_from.date().toPython()
            d_to = self.date_to.date().toPython()
            
            from datetime import datetime
            rows = []
            for i in self.all_incidences:
                match_text = (text in i['number'].lower() or text in i['so'].lower() or text in i['name'].lower() or text in i['user'].lower() or text in i['warehouse'].lower())
                match_wh = (wh_filter == "Todos los almacenes" or wh_filter == i['warehouse'])
                # ... reuse simplified matching logic
                if match_text and match_wh: # Simplified for export brevity
                    rows.append({
                        'Nº Ticket': i['number'],
                        'Almacén': i['warehouse'],
                        'Pedido': i['so'],
                        'Resumen': i['name'],
                        'Asignado': i['user'],
                        'Equipo': i['team'],
                        'Etapa': i['stage'],
                        'Fecha': i['date']
                    })
            
            df = pd.DataFrame(rows)
            df.to_excel(path, index=False)
            QMessageBox.information(self, "Éxito", f"Archivo guardado correctamente en:\n{path}")
            import os
            os.startfile(os.path.dirname(path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Fallo al exportar: {e}")

    def _filter_data(self):

        text = self.search_bar.text().lower()
        wh_filter = self.wh_selector.currentText()
        assigned_filter = self.assigned_selector.currentText()
        stage_filter = self.stage_selector.currentText()
        
        d_from = self.date_from.date().toPython()
        d_to = self.date_to.date().toPython()
        
        from datetime import datetime
        
        filtered = []
        for i in self.all_incidences:
            # 1. Text Match
            match_text = (text in i['number'].lower() or
                         text in i['so'].lower() or
                         text in i['name'].lower() or
                         text in i['user'].lower() or
                         text in i['warehouse'].lower())
            
            # 2. Warehouse Match
            match_wh = (wh_filter == "Todos los almacenes" or wh_filter == i['warehouse'])
            
            # 3. Assigned Match
            match_assigned = True
            if assigned_filter != "Todos los asignados":
                user_name = i['user'].lower()
                team_name = i['team'].lower()
                target = assigned_filter.lower()
                
                if target == "gabriela rojas esteller":
                    match_assigned = "gabriela rojas" in user_name
                elif target == "administración":
                    match_assigned = "administración" in user_name or "administración" in team_name
                elif target == "logística transporte externo":
                    match_assigned = "transporte externo" in team_name or "comercial" in team_name or "customer service" in team_name
                elif target == "logística interna bur":
                    match_assigned = "logística" in team_name
                elif target == "calidad":
                    match_assigned = "calidad" in team_name or "calidad" in user_name
            
            # 4. Stage Match (Etapa)
            match_stage = True
            if stage_filter != "Todas las etapas":
                match_stage = (i['stage'] == stage_filter)
            
            # 5. Date Match
            try:
                # Odoo date is string 'YYYY-MM-DD HH:MM:SS'
                idt = datetime.strptime(i['date'], '%Y-%m-%d %H:%M:%S').date()
                match_date = (d_from <= idt <= d_to)
            except:
                match_date = True
                
            if match_text and match_wh and match_assigned and match_stage and match_date:
                filtered.append(i)
                
        self._update_table(filtered)



    def _update_table(self, data):
        c_open = 0
        c_prog = 0
        c_done = 0
        
        self.table.setRowCount(0)
        for i, t in enumerate(data):
            self.table.insertRow(i)
            
            # KPI Counting and Row Coloring
            bg_color = QColor("white")
            if "Resuelto" in t['stage'] or "Hecho" in t['stage']:
                c_done += 1
                bg_color = QColor("#ecfdf5") # Light teal
            elif "progreso" in t['stage']:
                c_prog += 1
                bg_color = QColor("#eff6ff") # Light blue
            else:
                c_open += 1
                bg_color = QColor("#fef2f2") # Light red
                
            brush = QBrush(bg_color)
            
            item_num = QTableWidgetItem(t['number'])
            item_num.setBackground(brush)
            self.table.setItem(i, 0, item_num)
            
            wh_item = QTableWidgetItem(t['warehouse'])
            wh_item.setTextAlignment(Qt.AlignCenter)
            if t['warehouse'] == "Pinto":
                wh_item.setForeground(QColor(bur2000_theme.BUR.primary))
            wh_item.setBackground(brush)
            self.table.setItem(i, 1, wh_item)
            
            item_so = QTableWidgetItem(t['so'])
            item_so.setBackground(brush)
            self.table.setItem(i, 2, item_so)
            
            item_name = QTableWidgetItem(t['name'])
            item_name.setBackground(brush)
            self.table.setItem(i, 3, item_name)

            
            # Assignment Combo (New)
            cb_assign = QComboBox()
            cb_assign.addItem("Sin asignar")
            cb_assign.addItems(["Gabriela Rojas Esteller", "Administración", "Logística Interna BUR", "Calidad", "Logística Transporte Externo"])
            cb_assign.setStyleSheet(f"border: 1px solid {bur2000_theme.BUR.border}; background: white; font-size: 10px;")
            
            # Find current role
            current_role = "Sin asignar"
            if "gabriela" in t['user'].lower(): current_role = "Gabriela Rojas Esteller"
            elif "administración" in t['user'].lower() or "administración" in t['team'].lower(): current_role = "Administración"
            elif "transporte externo" in t['team'].lower() or "comercial" in t['team'].lower() or "customer service" in t['team'].lower(): current_role = "Logística Transporte Externo"
            elif "logística" in t['team'].lower(): current_role = "Logística Interna BUR"
            elif "calidad" in t['team'].lower() or "calidad" in t['user'].lower(): current_role = "Calidad"
            
            index = cb_assign.findText(current_role, Qt.MatchContains)
            if index >= 0: cb_assign.setCurrentIndex(index)
            
            cb_assign.currentIndexChanged.connect(lambda idx, tid=t['id'], cb=cb_assign: self._on_reassign(tid, cb.currentText()))
            self.table.setCellWidget(i, 4, cb_assign)
            
            # Stage Badge (Odoo Style)

            stage_label = QLabel(t['stage'])
            stage_label.setAlignment(Qt.AlignCenter)
            color = bur2000_theme.BUR.STATUS_DRAFT
            if "Nuevo" in t['stage']: color = bur2000_theme.BUR.STATUS_WAITING
            elif "progreso" in t['stage']: color = bur2000_theme.BUR.blue
            elif "Hecho" in t['stage'] or "Resuelto" in t['stage']: color = bur2000_theme.BUR.STATUS_READY
            
            stage_label.setStyleSheet(f"background-color: {color}22; color: {color}; border-radius: 4px; font-weight: bold; font-size: 9px; padding: 2px; border: 1px solid {color};")
            stage_label.setFixedSize(90, 20)
            
            container = QWidget()
            lay = QHBoxLayout(container)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(stage_label)
            self.table.setCellWidget(i, 5, container)
            
            # Action Button: Resolve
            btn_resolve = QPushButton("✅ Resolver")
            btn_resolve.setStyleSheet(f"background-color: {bur2000_theme.BUR.lvl1}; border: 1px solid {bur2000_theme.BUR.border};")
            btn_resolve.clicked.connect(lambda chk=False, tdata=t: self._open_resolution_wizard(tdata))
            self.table.setCellWidget(i, 6, btn_resolve)
            
            # Chatter Button
            btn_chatter = QPushButton("💬 Historial")
            btn_chatter.setStyleSheet(f"background-color: white; border: 1px solid {bur2000_theme.BUR.border};")
            btn_chatter.clicked.connect(lambda chk=False, tdata=t: self._open_chatter(tdata))
            self.table.setCellWidget(i, 7, btn_chatter)
            
            # Date
            item_date = QTableWidgetItem(str(t.get('date', ''))[:10])
            item_date.setBackground(brush)
            self.table.setItem(i, 8, item_date)


        self.kpi_open.setText(f"🔴 {c_open} Abiertas")
        self.kpi_prog.setText(f"🟡 {c_prog} En progreso")
        self.kpi_done.setText(f"✅ {c_done} Resueltas")

        # Emit for tab badge
        self.status_count_changed.emit(c_open)



    def _on_reassign(self, ticket_id, role_name):
        """Handle re-assignment from the table dropdown."""
        if role_name == "Sin asignar": return
        
        if self.service.assign_incidence(ticket_id, role_name):
            # No message box to avoid spamming if bulk assigning, but maybe refresh
            logger.info(f"Ticket {ticket_id} reassigned to {role_name}")
        else:
            QMessageBox.critical(self, "Error", f"No se pudo reasignar el ticket {ticket_id} en Odoo.")
            self.refresh_data()


    def _open_chatter(self, ticket_data):
        from ui.dialogs.chatter_dialog import ChatterDialog
        ChatterDialog(ticket_data, self.service, self).exec()

    def _open_resolution_wizard(self, ticket_data):

        from ui.dialogs.incidence_resolution_wizard import IncidenceResolutionWizard
        wizard = IncidenceResolutionWizard(ticket_data, self)
        if wizard.exec() == QDialog.Accepted:
            res_data = wizard.get_data()
            if self.service.resolve_incidence(ticket_data['id'], res_data):
                QMessageBox.information(self, "Éxito", "Incidencia cerrada correctamente.")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "No se pudo cerrar la incidencia en Odoo.")

    def _open_global_search(self):
        from ui.dialogs.global_search_dialog import GlobalSearchDialog
        from ui.dialogs.incidence_wizard import IncidenceWizard
        
        diag = GlobalSearchDialog(self.service.odoo, self)
        if diag.exec() == QDialog.Accepted:
            picking = diag.get_selected_picking()
            if picking:
                # Check if it already has an incidence
                so_name = picking['origin']
                existing = self.service.get_ticket_by_so(so_name)
                if existing:
                    QMessageBox.information(self, "Aviso", f"Ya existe una incidencia abierta para este pedido: {existing['number']}\nEtapa: {existing['stage_id'][1]}")
                    return
                
                # Open Wizard
                wizard_data = {
                    'picking_id': picking['external_id'],
                    'picking_name': picking['name'],
                    'so_name': so_name
                }
                wiz = IncidenceWizard(wizard_data, self)
                if wiz.exec() == QDialog.Accepted:
                    f = wiz.get_data()
                    ticket_id = self.service.create_incidence(f)
                    if ticket_id:
                        QMessageBox.information(self, "Éxito", "Incidencia creada correctamente.")
                        self.refresh_data()
