from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
import os

class LogViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visor de Logs - Gabriela Rojas Pro")
        self.resize(800, 500)
        self._build_ui()
        
        self.log_file = "gabriela_rojas.log" # Assuming this is the log file used by loguru/logging
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_logs)
        self.timer.start(2000)
        self._refresh_logs()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("📜 Registros del Sistema")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', monospace; font-size: 10px;")
        layout.addWidget(self.text_edit)
        
        btns = QHBoxLayout()
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.close)
        btns.addStretch()
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _refresh_logs(self):
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    # Get last 100 lines
                    lines = f.readlines()
                    content = "".join(lines[-100:])
                    self.text_edit.setPlainText(content)
                    self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())
            else:
                self.text_edit.setPlainText("Archivo de log no encontrado.")
        except Exception as e:
            self.text_edit.setPlainText(f"Error leyendo logs: {e}")
