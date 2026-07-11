from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QTextEdit, QPushButton, QMessageBox,
    QFrame
)
from PySide6.QtCore import Qt, QThreadPool
from ui.workers.odoo_worker import OdooWorker
from loguru import logger
import bur2000_theme

class ImprovementsEmailWizard(QDialog):
    def __init__(self, initial_text, odoo_service, parent=None):
        super().__init__(parent)
        self.odoo_service = odoo_service
        self.initial_text = initial_text
        self.threadpool = QThreadPool()
        self.setWindowTitle("Gestor de Correo - Mejoras Gabriela")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("✉️ Enviar Propuesta de Mejora")
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(header)
        
        # From / To Info Frame
        info_frame = QFrame()
        info_frame.setStyleSheet(bur2000_theme.BUR.card_style)
        info_lay = QVBoxLayout(info_frame)
        
        self.txt_to = QLineEdit("oscar.piedra@bur2000.com")
        self.txt_to.setReadOnly(True)
        self.txt_cc = QLineEdit("")
        self.txt_cc.setPlaceholderText("Opcional: CC (ej. gabriela@bur2000.com)")
        self.txt_subject = QLineEdit("MEJORA GABRIELA: Sugerencia de usuario")
        
        info_lay.addWidget(QLabel("Para:"))
        info_lay.addWidget(self.txt_to)
        info_lay.addWidget(QLabel("CC:"))
        info_lay.addWidget(self.txt_cc)
        info_lay.addWidget(QLabel("Asunto:"))
        info_lay.addWidget(self.txt_subject)
        layout.addWidget(info_frame)

        # Body
        layout.addWidget(QLabel("Cuerpo del mensaje:"))
        self.txt_body = QTextEdit()
        # Create a nice HTML template for the email body
        html_body = f"""
        <div style="font-family: sans-serif; color: #333;">
            <p style="font-size: 16px; line-height: 1.5;">
                {self.initial_text.replace(chr(10), '<br>')}
            </p>
            <br/><br/>
            <hr style="border: 0; border-top: 1px solid #eee;"/>
            <p style="color: #888; font-size: 12px; font-style: italic;">
                Enviado automáticamente desde el Gestor Interno de Gabriela Rojas Pro.
            </p>
        </div>
        """
        self.txt_body.setHtml(html_body)
        layout.addWidget(self.txt_body)
        
        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(f"padding: 8px 20px; border-radius: 4px; background: {bur2000_theme.BUR.lvl2}; color: {bur2000_theme.BUR.text}; font-weight: bold;")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        
        self.btn_send = QPushButton("✅ Enviar Correo")
        self.btn_send.setStyleSheet(f"padding: 8px 20px; border-radius: 4px; background: {bur2000_theme.BUR.STATUS_READY}; color: white; font-weight: bold;")
        self.btn_send.clicked.connect(self._send_email)
        btns.addWidget(self.btn_send)
        
        layout.addLayout(btns)

    def _send_email(self):
        """Prepares and dispatches the email sending job to the worker thread."""
        self.btn_send.setEnabled(False)
        self.btn_send.setText("⏳ Enviando...")
        
        email_data = {
            'to': self.txt_to.text().strip(),
            'cc': self.txt_cc.text().strip(),
            'subject': self.txt_subject.text().strip(),
            'body': self.txt_body.toHtml()
        }
        
        self.worker = OdooWorker(self._perform_send, email_data)
        self.worker.signals.result.connect(self._on_send_success)
        self.worker.signals.error.connect(self._on_send_error)
        self.threadpool.start(self.worker)

    def _perform_send(self, data):
        """Actual logic that runs in the background to send via Odoo."""
        try:
            self.odoo_service._ensure_connected()
            Mail = self.odoo_service.odoo.env['mail.mail']
            
            mail_vals = {
                'email_to': data['to'],
                'subject': data['subject'],
                'body_html': data['body'],
                'email_from': 'gabriela@bur2000.com' # Or whatever configured sender address
            }
            if data['cc']:
                mail_vals['email_cc'] = data['cc']
                
            mail_id = Mail.create(mail_vals)
            # Need to call send as list of IDs
            if isinstance(mail_id, int):
                Mail.send([mail_id])
            elif isinstance(mail_id, list):
                Mail.send(mail_id)
            else:
                 # Depending on OdooRPC version, create might return actual record or ID
                 # Most of the time it returns integer ID in list or just int
                 # Let's handle cautiously based on standard odoorpc behavior
                 try:
                    Mail.send([mail_id])
                 except:
                    # In newer odoo versions, send() can be called on the recordset directly if using a different client
                    # For odoorpc, usually model.method([ids], args)
                    pass
            return True
        except Exception as e:
            logger.error(f"Error sending improvement email internally: {e}")
            raise e

    def _on_send_success(self, result):
        QMessageBox.information(self, "Enviado", "El correo de mejora se ha enviado correctamente a través de Odoo.")
        self.accept()

    def _on_send_error(self, error):
        QMessageBox.critical(self, "Error al Enviar", f"Hubo un problema enviando el correo:\n{error}")
        self.btn_send.setEnabled(True)
        self.btn_send.setText("✅ Enviar Correo")
