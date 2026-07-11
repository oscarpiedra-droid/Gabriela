from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt
import bur2000_theme


class SurveyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Encuesta de Satisfacción - Bur 2000")
        self.setFixedWidth(520)
        self.ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(18)

        title = QLabel("⭐ Valoración de la Experiencia")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(title)

        info = QLabel("Tu opinión nos ayuda a seguir mejorando Gabriela.")
        info.setStyleSheet(f"color: {bur2000_theme.BUR.muted};")
        layout.addWidget(info)

        questions = [
            (1, "¿Cómo valoras la rapidez de las consultas a Odoo?"),
            (2, "¿Qué te parece el nuevo panel de Incidencias?"),
            (3, "¿Te resulta útil el sistema de Portes y Descuentos?"),
            (4, "¿Cómo calificarías la redacción del Asistente IA?"),
            (5, "¿Qué nota le darías a Gabriela en general?"),
        ]

        self.stars_widgets = {}

        for q_id, q_text in questions:
            q_lay = QVBoxLayout()
            lbl = QLabel(q_text)
            lbl.setStyleSheet("font-weight: bold; margin-bottom: 4px;")
            q_lay.addWidget(lbl)

            star_lay = QHBoxLayout()
            star_lay.setSpacing(8)

            btns = []
            for i in range(1, 6):
                btn = QPushButton("☆")
                btn.setFixedSize(36, 36)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(
                    "QPushButton { font-size: 24px; border: none; background: transparent; color: #d1d5db; }"
                )
                btn.clicked.connect(lambda chk=False, q=q_id, val=i: self._set_rating(q, val))
                star_lay.addWidget(btn)
                btns.append(btn)

            self.stars_widgets[q_id] = btns
            star_lay.addStretch()
            q_lay.addLayout(star_lay)
            layout.addLayout(q_lay)

        layout.addWidget(QLabel("✍️ Comentarios adicionales:"))
        self.txt_feedback = QTextEdit()
        self.txt_feedback.setPlaceholderText("¿Alguna sugerencia o mejora?")
        self.txt_feedback.setFixedHeight(80)
        layout.addWidget(self.txt_feedback)

        btn_send = QPushButton("⭐ Enviar Valoración")
        btn_send.setStyleSheet(bur2000_theme.BUR.button_primary)
        btn_send.setFixedHeight(45)
        btn_send.clicked.connect(self._submit)
        layout.addWidget(btn_send)

    def _set_rating(self, q_id, val):
        self.ratings[q_id] = val
        for i, btn in enumerate(self.stars_widgets[q_id]):
            if i < val:
                btn.setText("⭐")
                btn.setStyleSheet("font-size: 24px; border: none; background: transparent;")
            else:
                btn.setText("☆")
                btn.setStyleSheet("font-size: 24px; border: none; background: transparent; color: #d1d5db;")

    def _submit(self):
        if any(v == 0 for v in self.ratings.values()):
            QMessageBox.warning(self, "Incompleto", "Por favor, responde a todas las preguntas con estrellas.")
            return

        QMessageBox.information(self, "¡Gracias!", "Tu valoración ha sido registrada. ¡Seguimos mejorando!")
        self.accept()
