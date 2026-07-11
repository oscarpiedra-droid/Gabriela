import pandas as pd # Already installed in requirements.txt
import urllib.request
import io
import csv

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal
import logging
from ui.dialogs.incidence_wizard import IncidenceWizard

logger = logging.getLogger(__name__)

class ArticlesFetchThread(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, odoo_service):
        super().__init__()
        self.odoo_service = odoo_service

    def run(self):
        try:
            data = self.odoo_service.get_orders_with_articles()
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class ArticlesTab(QWidget):
    def __init__(self, odoo_service):
        super().__init__()
        self.odoo_service = odoo_service
        self.all_data = []
        self._setup_ui()
        self.load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Top Controls
        controls_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por Pedido o Ruta...")
        self.search_input.textChanged.connect(self._filter_table)
        controls_layout.addWidget(self.search_input)

        self.refresh_btn = QPushButton("Actualizar Datos")
        self.refresh_btn.clicked.connect(self.load_data)
        controls_layout.addWidget(self.refresh_btn)

        layout.addLayout(controls_layout)

        # Loading Label
        self.loading_label = QLabel("Cargando pedidos asigandos y stock de artículos...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.hide()
        layout.addWidget(self.loading_label)

        # Summary Cards
        cards_layout = QHBoxLayout()
        self.lbl_total_pedidos = self.create_summary_card("Total Pedidos")
        self.lbl_rutas = self.create_summary_card("Rutas Diferentes")
        
        cards_layout.addWidget(self.lbl_total_pedidos)
        cards_layout.addWidget(self.lbl_rutas)
        
        layout.addLayout(cards_layout)

        # Table
        self.table = QTableWidget()
        headers = [
            "Pedido", "Ruta", "Artículos", "UdM", "Cant. por Palet", "Dimensiones", "Peso (Total)", "Almacén Abrera", "Almacén Silla", "Almacén Pinto"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        # Enable multi-line text mapping
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        # Enable context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)

    def create_summary_card(self, title):
        card = QLabel(f"<b>{title}</b><br><span style='font-size:18px;'>0</span>")
        card.setAlignment(Qt.AlignCenter)
        card.setStyleSheet("""
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 10px;
        """)
        return card

    def load_data(self):
        self.refresh_btn.setEnabled(False)
        self.loading_label.show()
        self.table.setRowCount(0)
        self.all_data = []

        self.fetch_thread = ArticlesFetchThread(self.odoo_service)
        self.fetch_thread.finished.connect(self._on_data_loaded)
        self.fetch_thread.error.connect(self._on_error)
        self.fetch_thread.start()

    def _on_data_loaded(self, data):
        self.all_data = data
        self._populate_table(self.all_data)
        self.refresh_btn.setEnabled(True)
        self.loading_label.hide()

    def _on_error(self, message):
        self.refresh_btn.setEnabled(True)
        self.loading_label.hide()
        QMessageBox.critical(self, "Error", f"Error al cargar artículos:\n{message}")

    def _populate_table(self, data):
        self.table.setRowCount(0)
        
        tot_pedidos = len(data)
        rutas_set = set()
        
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            p_id = row_data.get('picking_id')
            p_full_name = str(row_data.get('pedido', ''))
            
            # Helper to extract parts if needed, but we'll use raw data for the Wizard
            # format is usually "OUT/001 (SO123)"
            
            ruta = row_data.get('ruta', '')
            if ruta:
                rutas_set.add(ruta)
            
            item_pedido = QTableWidgetItem(p_full_name)
            if p_id:
                item_pedido.setData(Qt.UserRole, p_id)
            
            self.table.setItem(row, 0, item_pedido)
            self.table.setItem(row, 1, QTableWidgetItem(str(row_data.get('ruta', ''))))
            self.table.setItem(row, 2, QTableWidgetItem(str(row_data.get('articulos', ''))))
            self.table.setItem(row, 3, QTableWidgetItem(str(row_data.get('uom', ''))))
            self.table.setItem(row, 4, QTableWidgetItem(str(row_data.get('pallet_qty', ''))))
            self.table.setItem(row, 5, QTableWidgetItem(str(row_data.get('dimensiones', ''))))
            self.table.setItem(row, 6, QTableWidgetItem(str(row_data.get('peso_stock', ''))))
            
            item_abrera = QTableWidgetItem(str(row_data.get('abrera', '')))
            item_silla = QTableWidgetItem(str(row_data.get('silla', '')))
            item_pinto = QTableWidgetItem(str(row_data.get('pinto', '')))
            
            self.table.setItem(row, 7, item_abrera)
            self.table.setItem(row, 8, item_silla)
            self.table.setItem(row, 9, item_pinto)
            
        self.lbl_total_pedidos.setText(f"<b>Total Pedidos</b><br><span style='font-size:18px; color:#2196F3;'>{tot_pedidos}</span>")
        self.lbl_rutas.setText(f"<b>Rutas Diferentes</b><br><span style='font-size:18px; color:#E65100;'>{len(rutas_set)}</span>")

    def _filter_table(self, text):
        search_text = text.lower()
        filtered_data = []
        for row in self.all_data:
            pedido = str(row.get('pedido', '')).lower()
            ruta = str(row.get('ruta', '')).lower()
            if search_text in pedido or search_text in ruta:
                filtered_data.append(row)
        self._populate_table(filtered_data)

    def _show_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        item = self.table.item(row, 0)
        picking_id = item.data(Qt.UserRole)
        full_name = item.text() # e.g. "AB/OUT/00123 (S00456)"
        
        # Extract Picking Name and SO name from the string
        # Typically "PICKING (SO)"
        picking_name = full_name
        so_name = ""
        if "(" in full_name and ")" in full_name:
            parts = full_name.split("(")
            picking_name = parts[0].strip()
            so_name = parts[1].replace(")", "").strip()

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 1px solid #ced4da; }")
        
        action_incidence = menu.addAction("📝 Registrar Incidencia")
        action_incidence.triggered.connect(lambda: self._open_incidence_wizard(picking_id, picking_name, so_name))
        
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _open_incidence_wizard(self, picking_id, picking_name, so_name):
        if not picking_id:
            QMessageBox.warning(self, "Aviso", "No se puede registrar incidencia para este registro (ID no encontrado).")
            return
            
        data = {
            'picking_id': picking_id,
            'picking_name': picking_name,
            'so_name': so_name
        }
        
        from db.services.incidence_service import IncidenceService
        
        wizard = IncidenceWizard(data, self)
        if wizard.exec_():
            f = wizard.get_data()
            try:
                inc_service = IncidenceService(self.odoo_service)
                ticket_id = inc_service.create_incidence(f)
                if ticket_id:
                    QMessageBox.information(self, "Éxito", "La incidencia ha sido creada correctamente en Odoo.")
                else:
                    QMessageBox.warning(self, "Aviso", "No se recibió confirmación de creación desde Odoo.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al procesar la incidencia: {e}")
            
            # Optionally refresh to show status (if we add a column for it)
            self.load_data()
