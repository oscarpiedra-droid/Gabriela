from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QAbstractItemView, QMessageBox
)
from PySide6.QtCore import Qt
import bur2000_theme

class GlobalSearchDialog(QDialog):
    def __init__(self, odoo_service, parent=None):
        super().__init__(parent)
        self.odoo = odoo_service
        self.setWindowTitle("Buscador Global de Pedidos / Albaranes")
        self.resize(800, 500)
        self.selected_picking = None
        self._build_ui()
        
    def _build_ui(self):
        self.setStyleSheet(f"background-color: {bur2000_theme.BUR.background};")
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        title = QLabel("🔍 Buscador de Pedidos")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        layout.addWidget(title)
        
        search_lay = QHBoxLayout()
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("Escribe el número de pedido (S0000) o albarán (MAD3/...)")
        self.txt_query.setStyleSheet(f"padding: 8px; border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; background: white;")
        self.txt_query.returnPressed.connect(self._do_search)
        
        btn_search = QPushButton("Buscar")
        btn_search.setStyleSheet(bur2000_theme.BUR.button_primary)
        btn_search.clicked.connect(self._do_search)
        
        search_lay.addWidget(self.txt_query)
        search_lay.addWidget(btn_search)
        layout.addLayout(search_lay)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Módulo", "Referencia", "Información/Cliente", "Estado", "Fecha", "Acción"])

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
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
                padding: 8px; 
                border-bottom: 2px solid {bur2000_theme.BUR.border};
                font-weight: bold;
            }}
        """)
        layout.addWidget(self.table)
        
        self.lbl_status = QLabel("Introduce un término de búsqueda.")
        self.lbl_status.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-style: italic;")
        layout.addWidget(self.lbl_status)

    def _do_search(self):
        query = self.txt_query.text().strip()
        if len(query) < 3:
            QMessageBox.warning(self, "Aviso", "Introduce al menos 3 caracteres.")
            return
            
        self.lbl_status.setText("Buscando en Odoo...")
        self.table.setRowCount(0)
        
        try:
            results = self.odoo.unified_search(query)
            if not results:
                self.lbl_status.setText("No se encontraron resultados.")
                return
                
            self.table.setRowCount(len(results))
            for i, r in enumerate(results):
                mod_item = QTableWidgetItem(r['module'])
                mod_item.setTextAlignment(Qt.AlignCenter)
                if r['module'] == 'Incidencias': mod_item.setForeground(Qt.red)
                elif r['module'] == 'Logística': mod_item.setForeground(Qt.blue)
                
                self.table.setItem(i, 0, mod_item)
                self.table.setItem(i, 1, QTableWidgetItem(r['ref']))
                
                info = f"{r['partner']} | {r['origin']}".strip(" | ")
                self.table.setItem(i, 2, QTableWidgetItem(info))
                
                status_item = QTableWidgetItem(r['status'])
                status_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 3, status_item)
                
                date_str = str(r['date'] or "")[:16] # Show time if available
                self.table.setItem(i, 4, QTableWidgetItem(date_str))
                
                if r['type'] == 'picking':
                    btn_select = QPushButton("🚩 Incidencia")
                    btn_select.setStyleSheet(f"background-color: {bur2000_theme.BUR.lvl1}; font-size: 11px;")
                    btn_select.clicked.connect(lambda chk=False, pick=r: self._select_and_close(pick))
                    self.table.setCellWidget(i, 5, btn_select)
                else:
                    lbl = QLabel("Solo lectura")
                    lbl.setAlignment(Qt.AlignCenter)
                    lbl.setStyleSheet("color: gray; font-size: 10px;")
                    self.table.setCellWidget(i, 5, lbl)
                
            self.lbl_status.setText(f"Se encontraron {len(results)} resultados.")
            
        except Exception as e:

            QMessageBox.critical(self, "Error", f"Error en la búsqueda: {e}")
            self.lbl_status.setText("Error en la conexión.")

    def _select_and_close(self, picking):
        self.selected_picking = picking
        self.accept()

    def get_selected_picking(self):
        return self.selected_picking
