from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QTextEdit, QPushButton, QCheckBox,
    QFrame
)
import bur2000_theme

class LogisticsEmailWizard(QDialog):
    def __init__(self, email_data, logic_service, parent=None):
        super().__init__(parent)
        self.data = email_data
        self.logic = logic_service
        self.setWindowTitle(f"Gabriela Rojas: {self.data['picking_name']}")
        self.setMinimumWidth(500)
        self._build_ui()


    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        header = QLabel("📤 Enviar Albarán (Gabriela Rojas)")
        header.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(header)
        
        info_frame = QFrame()
        info_frame.setStyleSheet(bur2000_theme.BUR.card_style)
        info_lay = QVBoxLayout(info_frame)
        info_text = f"<b>Picking:</b> {self.data['picking_name']}<br>"
        info_text += f"<b>Variante:</b> {'Recoge Cliente' if self.data['is_recoge'] else 'Envío Logística'}"
        info_lay.addWidget(QLabel(info_text))
        layout.addWidget(info_frame)
        
        self.txt_to = QLineEdit(self.data['to'])
        self.txt_to.setPlaceholderText("correo@ejemplo.com")
        self.txt_cc = QLineEdit(self.data['cc'])
        self.txt_subject = QLineEdit(self.data['subject'])
        self.txt_body = QTextEdit()
        self.txt_body.setHtml(self.data['body'])
        
        layout.addWidget(QLabel("Para:"))
        layout.addWidget(self.txt_to)
        layout.addWidget(QLabel("CC:"))
        layout.addWidget(self.txt_cc)
        layout.addWidget(QLabel("Asunto:"))
        layout.addWidget(self.txt_subject)
        layout.addWidget(QLabel("Mensaje:"))
        layout.addWidget(self.txt_body)
        
        self.chk_recoge = QCheckBox("Es 'Recoge Cliente'")
        self.chk_recoge.setChecked(self.data['is_recoge'])
        self.chk_recoge.toggled.connect(self._on_recoge_toggled)
        layout.addWidget(self.chk_recoge)

        
        btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        self.btn_send = QPushButton("✅ Enviar")
        self.btn_send.setStyleSheet(f"background: {bur2000_theme.BUR.primary}; color: white; padding: 8px; font-weight: bold;")
        self.btn_send.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(self.btn_send)
        layout.addLayout(btns)

    def _on_recoge_toggled(self, checked):
        """Update subject and body when type changes."""
        ext = self.data.get('ext_data', {})
        partner_name = ext.get('partner_name', '')
        picking_name = self.data['picking_name']
        
        if checked:
            new_subject = f"RECOGE CLIENTE: {picking_name} - {partner_name}"
        else:
            new_subject = f"Envío Logística: {picking_name} - {partner_name}"
            
        self.txt_subject.setText(new_subject)
        
        # Regenerate body via logic service
        new_body = self.logic.get_email_body(ext, checked)
        self.txt_body.setHtml(new_body)

    def get_final_data(self):
        return {
            'to': self.txt_to.text(),
            'cc': self.txt_cc.text(),
            'subject': self.txt_subject.text(),
            'body': self.txt_body.toHtml(),
            'is_recoge': self.chk_recoge.isChecked()
        }

