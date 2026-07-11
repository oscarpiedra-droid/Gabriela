from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
    QTextEdit, QComboBox, QPushButton, QHBoxLayout, 
    QLabel, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt
import bur2000_theme

class IncidenceResolutionWizard(QDialog):
    def __init__(self, ticket_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Cerrar Incidencia - {ticket_data['number']}")
        self.resize(500, 450)
        self.ticket_data = ticket_data
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("🏁 Cierre de Incidencia")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(title)
        
        info = QLabel(f"Ticket: {self.ticket_data['number']} - {self.ticket_data['name']}")
        info.setStyleSheet("color: #6b7280; font-style: italic;")
        layout.addWidget(info)
        
        form = QFormLayout()
        
        self.txt_root_cause = QTextEdit()
        self.txt_root_cause.setPlaceholderText("¿Cuál fue la causa real detectada?")
        form.addRow("Causa Raíz:", self.txt_root_cause)
        
        self.txt_final_action = QTextEdit()
        self.txt_final_action.setPlaceholderText("¿Qué acción se tomó para resolverlo?")
        form.addRow("Acción Final:", self.txt_final_action)
        
        self.chk_conform = QCheckBox("Cliente conforme con la resolución")
        self.chk_conform.setStyleSheet("font-weight: bold;")
        form.addRow("", self.chk_conform)
        
        layout.addLayout(form)
        
        # Buttons
        btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_close = QPushButton("Cerrar Ticket Definitivamente")
        self.btn_close.setStyleSheet(f"background-color: {bur2000_theme.BUR.primary}; color: white; font-weight: bold; padding: 10px;")
        self.btn_close.clicked.connect(self._validate_and_accept)
        
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(self.btn_close)
        layout.addLayout(btns)

    def _validate_and_accept(self):
        if not self.txt_root_cause.toPlainText().strip() or not self.txt_final_action.toPlainText().strip():
            QMessageBox.warning(self, "Error", "La Causa Raíz y la Acción Final son obligatorias para el cierre (Mejora Continua).")
            return
            
        self.accept()

    def get_data(self):
        return {
            'root_cause': self.txt_root_cause.toPlainText().strip(),
            'final_action': self.txt_final_action.toPlainText().strip(),
            'conform': self.chk_conform.isChecked()
        }
