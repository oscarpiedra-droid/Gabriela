from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QScrollArea, QFrame, 
    QWidget, QMessageBox
)
from PySide6.QtCore import Qt
import bur2000_theme

class ChatterDialog(QDialog):
    def __init__(self, ticket_data, service, parent=None):
        super().__init__(parent)
        self.ticket = ticket_data
        self.service = service
        self.setWindowTitle(f"💬 Chatter - {self.ticket['number']}")
        self.resize(550, 700)
        self._build_ui()
        self._load_messages()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel(f"Historial de {self.ticket['number']}")
        header.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(header)

        # New: Ticket Description/Summary Block
        desc_frame = QFrame()
        desc_frame.setStyleSheet(f"background-color: {bur2000_theme.BUR.lvl2}; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 6px; padding: 10px;")
        desc_lay = QVBoxLayout(desc_frame)
        lbl_desc_title = QLabel("📝 Descripción de la Incidencia")
        lbl_desc_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #555;")
        lbl_desc = QLabel(self.ticket.get('description', self.ticket.get('name', 'Sin descripción detallada disponible.')))
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 12px; color: #111; margin-top: 5px;")
        desc_lay.addWidget(lbl_desc_title)
        desc_lay.addWidget(lbl_desc)

        layout.addWidget(desc_frame)

        # Scroll Area for Messages
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(f"background-color: {bur2000_theme.BUR.background}; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 8px;")
        
        self.msg_container = QWidget()
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setAlignment(Qt.AlignTop)
        self.msg_layout.setSpacing(10)
        self.scroll.setWidget(self.msg_container)
        layout.addWidget(self.scroll, 5)

        # New Message Area
        layout.addWidget(QLabel("✍️ Escribir respuesta:"))
        self.txt_msg = QTextEdit()
        self.txt_msg.setPlaceholderText("Escribe un mensaje para Odoo...")
        self.txt_msg.setFixedHeight(100)
        self.txt_msg.setStyleSheet(f"border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; padding: 5px;")
        layout.addWidget(self.txt_msg, 1)

        # Actions
        actions = QHBoxLayout()
        actions.addStretch()
        
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        actions.addWidget(btn_close)

        self.btn_send = QPushButton("🚀 Enviar a Odoo")
        self.btn_send.setStyleSheet(bur2000_theme.BUR.button_primary)
        self.btn_send.setFixedSize(150, 35)
        self.btn_send.clicked.connect(self._send_message)
        actions.addWidget(self.btn_send)
        
        layout.addLayout(actions)

    def _load_messages(self):
        # Clear existing
        while self.msg_layout.count():
            item = self.msg_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        messages = self.service.get_ticket_messages(self.ticket['id'])
        if not messages:
            lbl = QLabel("No hay mensajes previos.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: gray; margin-top: 20px;")
            self.msg_layout.addWidget(lbl)
            return

        for m in messages:
            card = QFrame()
            card.setStyleSheet(f"background: white; border: 1px solid #eee; border-radius: 6px; padding: 10px;")
            c_lay = QVBoxLayout(card)
            
            meta = QHBoxLayout()
            author = QLabel(f"👤 <b>{m['author']}</b>")
            date = QLabel(m['date'])
            date.setStyleSheet("color: gray; font-size: 10px;")
            meta.addWidget(author)
            meta.addStretch()
            meta.addWidget(date)
            c_lay.addLayout(meta)
            
            body = QLabel(m['body'])
            body.setWordWrap(True)
            body.setStyleSheet("margin-top: 5px; color: #333;")
            c_lay.addWidget(body)
            
            self.msg_layout.addWidget(card)

    def _send_message(self):
        body = self.txt_msg.toPlainText().strip()
        if not body:
            return

        self.btn_send.setEnabled(False)
        self.btn_send.setText("⏳ ...")
        
        if self.service.post_ticket_message(self.ticket['id'], body):
            self.txt_msg.clear()
            self._load_messages()
            # Scroll to bottom
            self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        else:
            QMessageBox.critical(self, "Error", "No se pudo enviar el mensaje.")
            
        self.btn_send.setEnabled(True)
        self.btn_send.setText("🚀 Enviar a Odoo")
