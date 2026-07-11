from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QMessageBox, QFrame, QDialog
)
from PySide6.QtCore import Qt, QThreadPool
from ui.workers.odoo_worker import OdooWorker
import bur2000_theme
from loguru import logger

class ImprovementsTab(QWidget):
    def __init__(self, odoo_service, parent=None):
        super().__init__(parent)
        self.odoo_service = odoo_service
        self.threadpool = QThreadPool()
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Header
        header = QLabel("💡 Propuestas de Mejora")
        header.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(header)
        
        info = QLabel("Tu feedback es fundamental para seguir evolucionando Gabriela. Redacta aquí cualquier mejora o sugerencia.")
        info.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 14px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Editor Frame
        self.card = QFrame()
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border: 1px solid {bur2000_theme.BUR.border};
                border-radius: 12px;
            }}
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        
        self.txt_improvement = QTextEdit()
        self.txt_improvement.setPlaceholderText("Escribe aquí tu sugerencia detallada...")
        self.txt_improvement.setStyleSheet(f"""
            QTextEdit {{
                border: none;
                font-size: 14px;
                color: {bur2000_theme.BUR.text};
            }}
        """)
        card_layout.addWidget(self.txt_improvement)
        
        layout.addWidget(self.card)
        
        # Footer Action
        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_send = QPushButton("📤 Abrir Gestor Interno de Gabriela")
        self.btn_send.setStyleSheet(bur2000_theme.BUR.button_primary + "padding: 12px 30px; font-size: 14px;")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.clicked.connect(self._send_improvement)
        footer.addWidget(self.btn_send)
        
        layout.addLayout(footer)
        layout.addStretch()

    def _send_improvement(self):
        text = self.txt_improvement.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Campo vacío", "Por favor, escribe algo en el área de texto para iniciar tu sugerencia.")
            return
            
        from ui.dialogs.improvements_email_wizard import ImprovementsEmailWizard
        
        wizard = ImprovementsEmailWizard(initial_text=text, odoo_service=self.odoo_service, parent=self)
        if wizard.exec() == QDialog.Accepted:
            self.txt_improvement.clear()
