from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
    QTextEdit, QComboBox, QPushButton, QHBoxLayout, 
    QLabel, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
import bur2000_theme
import os

class IncidenceWizard(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Nueva Incidencia - {data['picking_name']}")
        self.resize(500, 600)
        self.data = data # Contains picking_id, picking_name, so_name
        self.files = []
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("📝 Registro de Incidencia")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(title)
        
        form = QFormLayout()
        
        self.txt_so = QLineEdit(self.data['so_name'])
        self.txt_so.setReadOnly(True)
        self.txt_so.setStyleSheet("background-color: #f3f4f6;")
        form.addRow("Pedido de Venta:", self.txt_so)
        
        # Extract and show warehouse info
        p_name = self.data['picking_name']
        warehouse_default = "Pinto"
        if "VAL" in p_name: warehouse_default = "Valencia"
        elif "BCN" in p_name: warehouse_default = "Barcelona"
        elif "AB" in p_name: warehouse_default = "Abrera"
        elif "GAV" in p_name: warehouse_default = "Gav\u00e0"
        
        self.cb_wh = QComboBox()
        self.cb_wh.addItems([
            "Pinto", "Valencia", "Barcelona", 
            "Gav\u00e0", "Delegaci\u00f3n Madrid", "Abrera"
        ])
        
        # Set default based on picking name
        index = self.cb_wh.findText(warehouse_default)
        if index >= 0:
            self.cb_wh.setCurrentIndex(index)
            
        form.addRow("Almac\u00e9n:", self.cb_wh)
        
        self.cb_type = QComboBox()
        self.cb_type.addItems([
            "Faltante / material incompleto",
            "Presentación incorrecta",
            "Daño por manipulación/transporte",
            "Error de dirección de entrega",
            "Producto no funciona / no pega",
            "Material roto / descuadrado"
        ])
        form.addRow("Tipo de Incidencia:", self.cb_type)
        
        self.txt_summary = QLineEdit()
        self.txt_summary.setPlaceholderText("Título corto del problema")
        form.addRow("Resumen:", self.txt_summary)
        
        self.txt_detail = QTextEdit()
        self.txt_detail.setPlaceholderText("Explica detalladamente qué ha pasado...")
        form.addRow("Detalle:", self.txt_detail)
        
        self.txt_units = QLineEdit()
        self.txt_units.setPlaceholderText("0")
        form.addRow("Unidades Afectadas:", self.txt_units)
        
        self.cb_priority = QComboBox()
        self.cb_priority.addItem("Baja", "0")
        self.cb_priority.addItem("Media", "1")
        self.cb_priority.addItem("Alta", "2")
        self.cb_priority.addItem("Urgente", "3")
        self.cb_priority.setCurrentIndex(1)
        form.addRow("Urgencia:", self.cb_priority)
        
        layout.addLayout(form)
        
        # Attachments
        att_lay = QHBoxLayout()
        self.lbl_files = QLabel("Sin adjuntos (obligatorio en daños)")
        self.lbl_files.setStyleSheet("font-style: italic; color: #6b7280;")
        btn_att = QPushButton("📎 Adjuntar Fotos")
        btn_att.clicked.connect(self._add_files)
        att_lay.addWidget(self.lbl_files)
        att_lay.addStretch()
        att_lay.addWidget(btn_att)
        layout.addLayout(att_lay)
        
        # Buttons
        btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_create = QPushButton("Crear Incidencia")
        self.btn_create.setStyleSheet(f"background-color: {bur2000_theme.BUR.primary}; color: white; font-weight: bold; padding: 10px;")
        self.btn_create.clicked.connect(self._validate_and_accept)
        
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(self.btn_create)
        layout.addLayout(btns)

    MAX_TOTAL_SIZE = 5 * 1024 * 1024 # 5MB

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Seleccionar fotos", "", "Images (*.png *.jpg *.jpeg)")
        if files:
            # Check individual and total sizes
            valid_files = []
            total_size = 0
            errors = []
            
            for f in files:
                size = os.path.getsize(f)
                if size > 3 * 1024 * 1024:
                    errors.append(f"El archivo {os.path.basename(f)} supera los 3MB.")
                    continue
                valid_files.append(f)
                total_size += size
                
            if total_size > self.MAX_TOTAL_SIZE:
                QMessageBox.warning(self, "Límite Excedido", f"El tamaño total de los adjuntos ({total_size/1024/1024:.1f}MB) supera el límite de 5MB.\n\nPor favor, reduce el número de fotos o su calidad.")
                return
                
            if errors:
                QMessageBox.warning(self, "Archivos omitidos", "\n".join(errors))
            
            self.files = valid_files
            size_mb = total_size / 1024 / 1024
            self.lbl_files.setText(f"{len(valid_files)} archivos ({size_mb:.1f}MB)")
            self.lbl_files.setStyleSheet("color: #10b981; font-weight: bold;")


    def _validate_and_accept(self):
        if not self.txt_summary.text() or not self.txt_detail.toPlainText():
            QMessageBox.warning(self, "Error", "El resumen y el detalle son obligatorios.")
            return
        
        tipo = self.cb_type.currentText().lower()
        if ("daño" in tipo or "roto" in tipo) and not self.files:
            QMessageBox.warning(self, "Error", "Para este tipo de incidencias es obligatorio adjuntar fotos.")
            return
            
        self.accept()

    def get_data(self):
        # Map localized types to keys for the service
        tipo_raw = self.cb_type.currentText()
        tipo_map = {
            "Faltante": "faltante",
            "Presentación": "presentacion",
            "Daño": "daño",
            "Dirección": "direccion",
            "Producto no funciona": "producto_no_f",
            "Material roto": "material_roto"
        }
        final_type = "faltante"
        for k, v in tipo_map.items():
            if k in tipo_raw:
                final_type = v
                break
                
        # Read file contents
        attachments = []
        for fpath in self.files:
            try:
                with open(fpath, 'rb') as f:
                    attachments.append((os.path.basename(fpath), f.read()))
            except: pass

        return {
            'so_name': self.data['so_name'],
            'picking_id': self.data['picking_id'],
            'warehouse': self.cb_wh.currentText(),
            'type': final_type,
            'summary': self.txt_summary.text(),
            'description': self.txt_detail.toPlainText(),
            'units': int(self.txt_units.text() or 0),
            'priority': self.cb_priority.currentData(),
            'attachments': attachments
        }
