from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QTextEdit, QLineEdit,
    QProgressBar, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
import bur2000_theme
from db.services.technical_service import TechnicalService

class TechnicalTab(QWidget):
    def __init__(self, odoo_service, incidence_service=None, parent=None):
        super().__init__(parent)
        self.service = TechnicalService(odoo_service)
        self.incidence_service = incidence_service
        self._build_ui()

        
        # Basic refresh loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(30000) # Every 30s
        
        QTimer.singleShot(500, self.refresh_data)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # 1. Header & Status
        header = QHBoxLayout()
        title = QLabel("🤖 Centro de Control: Empleado Invisible")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        header.addWidget(title)
        header.addStretch()
        
        self.bot_status_label = QLabel("🟢 SISTEMA ACTIVO")
        self.bot_status_label.setStyleSheet(f"background: {bur2000_theme.BUR.STATUS_READY}; color: white; padding: 5px 15px; border-radius: 12px; font-weight: bold;")
        header.addWidget(self.bot_status_label)
        layout.addLayout(header)
        
        # 2. Stats Dashboard
        stats_layout = QHBoxLayout()
        self.kpi_total = self._create_stat_card("Procesados Hoy", "0", bur2000_theme.BUR.text)
        self.kpi_auto = self._create_stat_card("Respuestas IA", "0", bur2000_theme.BUR.secondary)
        self.kpi_waiting = self._create_stat_card("En Consulta (Wha)", "0", bur2000_theme.BUR.primary)
        
        stats_layout.addWidget(self.kpi_total)
        stats_layout.addWidget(self.kpi_auto)
        stats_layout.addWidget(self.kpi_waiting)
        layout.addLayout(stats_layout)
        
        # 3. Main Body Split
        body = QHBoxLayout()
        body.setSpacing(20)
        
        # 3.1 Recent Activity Log
        log_side = QVBoxLayout()
        log_side.addWidget(QLabel("📝 Registro de Actividad (Gmail Técnico)"))
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Hora", "Cliente", "Acción AI", "Resumen"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(f"border: 1px solid {bur2000_theme.BUR.border}; background: white;")
        log_side.addWidget(self.table)
        
        # 3.2 Drafting Simulator
        draft_side = QFrame()
        draft_side.setFixedWidth(400)
        draft_side.setStyleSheet(f"background: {bur2000_theme.BUR.lvl2}; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 8px;")
        draft_lay = QVBoxLayout(draft_side)
        draft_lay.setContentsMargins(20, 20, 20, 20)
        
        draft_lay.addWidget(QLabel("🎙️ Simulador de Respuesta (Voz a Mail)"))
        
        # New: Ticket Selection
        ticket_lay = QHBoxLayout()
        ticket_lay.addWidget(QLabel("Destino:"))
        self.ticket_selector = QComboBox()
        self.ticket_selector.addItem("Selecciona un Ticket activo...", None)
        self.ticket_selector.setStyleSheet(f"padding: 6px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        ticket_lay.addWidget(self.ticket_selector, 1)
        
        self.btn_refresh_tickets = QPushButton("🔄")
        self.btn_refresh_tickets.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 4px; padding: 4px;")
        self.btn_refresh_tickets.clicked.connect(self._fetch_active_tickets)
        ticket_lay.addWidget(self.btn_refresh_tickets)
        draft_lay.addLayout(ticket_lay)

        self.input_voice = QTextEdit()
        self.input_voice.setPlaceholderText("Pega aquí la transcripción del audio o escribe tus notas informales...")
        self.input_voice.setFixedHeight(90)
        self.input_voice.setStyleSheet("background: white; border-radius: 4px;")
        draft_lay.addWidget(self.input_voice)
        
        self.btn_refine = QPushButton("✨ Redactar Profesional")
        self.btn_refine.setStyleSheet(bur2000_theme.BUR.button_primary)
        self.btn_refine.clicked.connect(self._refine_text)
        draft_lay.addWidget(self.btn_refine)
        
        draft_lay.addWidget(QLabel("📄 Borrador del Agente:"))
        self.output_mail = QTextEdit()
        self.output_mail.setReadOnly(True)
        self.output_mail.setStyleSheet("background: #fdfdfd; color: #444; border-radius: 4px; border: 1px dashed #ccc;")
        draft_lay.addWidget(self.output_mail)
        
            
        self.btn_send = QPushButton("📨 Enviar como tecnico@bur2000.com")
        self.btn_send.setStyleSheet(bur2000_theme.BUR.button_secondary)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self._send_mail)
        draft_lay.addWidget(self.btn_send)
        
        draft_lay.addSpacing(10)
        self.btn_analyze = QPushButton("🧪 Análisis Avanzado (Incidencias)")
        self.btn_analyze.setStyleSheet(f"background-color: {bur2000_theme.BUR.accent}; color: white; border-radius: 4px; font-weight: bold;")
        self.btn_analyze.setFixedHeight(40)
        self.btn_analyze.clicked.connect(self._run_ai_analysis)
        draft_lay.addWidget(self.btn_analyze)
        
        body.addLayout(log_side, 2)
        body.addWidget(draft_side, 1)
        layout.addLayout(body)


    def _create_stat_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"background: white; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 8px;")
        lay = QVBoxLayout(card)
        t = QLabel(title)
        t.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 12px;")
        t.setAlignment(Qt.AlignCenter)
        v = QLabel(value)
        v.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        v.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(v)
        # Store label to update later
        card.value_label = v
        return card

    def refresh_data(self):
        stats = self.service.get_bot_stats()
        self.kpi_total.value_label.setText(str(stats['processed']))
        self.kpi_auto.value_label.setText(str(stats['automated']))
        self.kpi_waiting.value_label.setText(str(stats['consultations']))
        self.bot_status_label.setText(f"🟢 {stats['status'].upper()}")

        # Trigger initial fetch if empty
        if self.ticket_selector.count() <= 1:
            self._fetch_active_tickets()

        # Update Log Table
        history = self.service.get_recent_activity()
        self.table.setRowCount(0)
        for i, entry in enumerate(history):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(entry['time']))
            self.table.setItem(i, 1, QTableWidgetItem(entry['client']))
            
            act_item = QTableWidgetItem(entry['action'])
            if "Automático" in entry['action']: act_item.setForeground(QColor(bur2000_theme.BUR.STATUS_READY))
            elif "Consulta" in entry['action']: act_item.setForeground(QColor(bur2000_theme.BUR.blue))
            self.table.setItem(i, 2, act_item)
            
            self.table.setItem(i, 3, QTableWidgetItem(entry['summary']))

    def _fetch_active_tickets(self):
        if not self.incidence_service: return
        self.btn_refresh_tickets.setEnabled(False)
        from ui.workers.odoo_worker import OdooWorker
        worker = OdooWorker(self.incidence_service.get_active_incidences)
        worker.signals.result.connect(self._on_tickets_fetched)
        worker.signals.error.connect(lambda e: self.btn_refresh_tickets.setEnabled(True))
        
        # Need access to threadpool
        import PySide6.QtCore as qc
        if not hasattr(self, 'threadpool'): self.threadpool = qc.QThreadPool()
        self.threadpool.start(worker)

    def _on_tickets_fetched(self, tickets):
        self.btn_refresh_tickets.setEnabled(True)
        self.ticket_selector.clear()
        self.ticket_selector.addItem("Selecciona un Ticket activo...", None)
        for t in tickets:
            if t['stage'] not in ['Hecho', 'Resuelto', 'Cancelado']:
                self.ticket_selector.addItem(f"{t['number']} - {t['name']}", t['id'])

    def _refine_text(self):
        raw = self.input_voice.toPlainText()
        if not raw: return
        
        self.btn_refine.setText("⏳ Pensando...")
        self.btn_refine.setEnabled(False)
        
        from ui.workers.odoo_worker import OdooWorker
        import PySide6.QtCore as qc
        if not hasattr(self, 'threadpool'): self.threadpool = qc.QThreadPool()
        
        def drafting_task():
            return self.service.refine_draft(raw)
            
        worker = OdooWorker(drafting_task)
        worker.signals.result.connect(self._show_refined)
        worker.signals.error.connect(lambda e: self._show_refined(f"Error: {e}"))
        self.threadpool.start(worker)

    def _show_refined(self, refined_text):
        self.output_mail.setPlainText(refined_text)
        self.btn_refine.setText("✨ Redactar Profesional")
        self.btn_refine.setEnabled(True)
        self.btn_send.setEnabled(True)

    def _send_mail(self):
        ticket_id = self.ticket_selector.currentData()
        ticket_name = self.ticket_selector.currentText()
        if not ticket_id:
            QMessageBox.warning(self, "Atención", "Debe seleccionar un Ticket de destino primero.")
            return

        msg = self.output_mail.toPlainText()
        if not msg: return
        
        self.btn_send.setText("Enviando...")
        self.btn_send.setEnabled(False)

        from ui.workers.odoo_worker import OdooWorker
        import PySide6.QtCore as qc
        if not hasattr(self, 'threadpool'): self.threadpool = qc.QThreadPool()
        
        def send_task():
            # As a standard, send generic replies to 'catchall' unless parsed.
            return self.service.send_via_bot(
                recipient="atencion-al-cliente@bur2000.com", 
                subject=f"Respuesta Automática - Ticket {ticket_name.split('-')[0].strip()}", 
                body=msg,
                ticket_id=ticket_id,
                ticket_name=ticket_name
            )
            
        worker = OdooWorker(send_task)
        worker.signals.result.connect(self._on_mail_sent)
        worker.signals.error.connect(self._on_mail_error)
        self.threadpool.start(worker)

    def _on_mail_sent(self, success):
        self.btn_send.setText("📨 Enviar a Odoo")
        if success:
            QMessageBox.information(self, "Enviado", "La contestación técnica ha sido insertada en el historial del ticket (Odoo Chatter) con éxito.")
            self.input_voice.clear()
            self.output_mail.clear()
            self.btn_send.setEnabled(False)
            self.refresh_data()
        else:
            QMessageBox.critical(self, "Error", "El servidor de Odoo rechazó la publicación del mensaje.")
            self.btn_send.setEnabled(True)
            
    def _on_mail_error(self, e):
        QMessageBox.critical(self, "Error de Conexión", f"Excepción crítica enviando el mail: {e}")
        self.btn_send.setText("📨 Enviar a Odoo")
        self.btn_send.setEnabled(True)

    def _run_ai_analysis(self):
        if not self.incidence_service:
            QMessageBox.warning(self, "Error", "Servicio de incidencias no disponible.")
            return

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("🧪 Analizando...")
        
        # Get stats (Blocking, but fast)
        stats = self.incidence_service.get_incidence_stats()
        
        from ui.workers.odoo_worker import OdooWorker
        import PySide6.QtCore as qc
        if not hasattr(self, 'threadpool'): self.threadpool = qc.QThreadPool()
        
        def analysis_task():
            return self.service.get_ai_insights(stats)

        worker = OdooWorker(analysis_task)
        worker.signals.result.connect(self._fetch_analysis_done)
        worker.signals.error.connect(self._fetch_analysis_error)
        self.threadpool.start(worker)

    def _fetch_analysis_done(self, analysis):
        self.output_mail.setPlainText(analysis)
        QMessageBox.information(self, "Análisis Completo", "El asistente ha analizado el estado de las incidencias.\nConsulta el cuadro superior.")
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("🧪 Análisis Avanzado (Incidencias)")

    def _fetch_analysis_error(self, e):
        QMessageBox.critical(self, "Error", f"Fallo en el análisis: {e}")
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("🧪 Análisis Avanzado (Incidencias)")

