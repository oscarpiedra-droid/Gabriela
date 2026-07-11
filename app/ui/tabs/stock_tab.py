import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QApplication, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont

# Thread for fetching stock data asynchronously to keep UI responsive
class FetchStockWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, odoo_service, query_sku=""):
        super().__init__()
        self.odoo_service = odoo_service
        self.query_sku = query_sku

    def run(self):
        try:
            results = self.odoo_service.get_stock_and_reservations(self.query_sku)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class StockTab(QWidget):
    def __init__(self, odoo_service):
        super().__init__()
        self.odoo_service = odoo_service
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 1. Header & Search Bar
        header_layout = QHBoxLayout()
        title_label = QLabel("Control de Inventario y Disponibilidad")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        title_label.setFont(font)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar SKU o Nombre del Producto...")
        self.search_input.setMinimumWidth(300)
        self.search_input.returnPressed.connect(self.load_data)

        self.btn_search = QPushButton("Buscar")
        self.btn_search.clicked.connect(self.load_data)
        
        self.btn_refresh = QPushButton("Refrescar Todo")
        self.btn_refresh.clicked.connect(lambda: self.load_data(refresh_all=True))

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.search_input)
        header_layout.addWidget(self.btn_search)
        header_layout.addWidget(self.btn_refresh)

        # Summary Cards
        cards_layout = QHBoxLayout()
        self.lbl_total_stock = self.create_summary_card("Stock Total (Ud)")
        self.lbl_total_avail = self.create_summary_card("Disponible (Ud)")
        self.lbl_total_resv = self.create_summary_card("Reservado (Ud)")
        self.lbl_total_weight = self.create_summary_card("Peso Total (Kg)")
        
        cards_layout.addWidget(self.lbl_total_stock)
        cards_layout.addWidget(self.lbl_total_avail)
        cards_layout.addWidget(self.lbl_total_resv)
        cards_layout.addWidget(self.lbl_total_weight)

        # 2. Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Referencia", "Almacén / Ubicación", "Stock a Mano", 
            "Stock Disponible", "Stock Reservado", "Peso Total (Kg)", "Pedidos Asignados"
        ])
        
        # Adjust column sizes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)     # Producto
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Ubicación
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # A mano
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Disponible
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Reservado
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents) # Peso
        header.setSectionResizeMode(6, QHeaderView.Stretch)          # Asignados
        
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        # 3. Status
        self.status_label = QLabel("Listo. Ingrese una búsqueda o haga clic en 'Refrescar Todo'.")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")

        # 4. Loading overlay sobre la tabla (fix BUG-003)
        # Se superpone sobre la tabla para evitar que el usuario vea filas vacías
        # mientras los KPI cards ya muestran totales.
        self._table_container = QFrame()
        self._table_container.setStyleSheet("")
        table_stack = QVBoxLayout(self._table_container)
        table_stack.setContentsMargins(0, 0, 0, 0)
        table_stack.setSpacing(0)
        table_stack.addWidget(self.table)

        self._loading_overlay = QLabel("📦 Cargando inventario...")
        self._loading_overlay.setAlignment(Qt.AlignCenter)
        self._loading_overlay.setStyleSheet(
            "background: rgba(255,255,255,220); color: #555; font-size: 16px; "
            "font-style: italic; border: 1px solid #ddd; border-radius: 8px;"
        )
        self._loading_overlay.setVisible(False)

        layout.addLayout(header_layout)
        layout.addLayout(cards_layout)
        layout.addWidget(self._table_container)
        layout.addWidget(self._loading_overlay)
        layout.addWidget(self.status_label)
        
        # Load initial data automatically
        self.load_data(refresh_all=True)

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

    def load_data(self, refresh_all=False):
        query = "" if refresh_all else self.search_input.text().strip()
        
        self.btn_search.setEnabled(False)
        self.btn_refresh.setEnabled(False)

        # BUG-003 fix: NO limpiamos la tabla ni llamamos processEvents().
        # En su lugar mostramos el overlay para indicar carga sin dejar
        # la tabla vacía con KPIs ya actualizados (race condition visual).
        self._loading_overlay.setText(
            f"📦 Cargando {'todo el inventario' if refresh_all else f'resultados para «{query}»'}..."
        )
        self._loading_overlay.setVisible(True)
        self._table_container.setVisible(False)

        self.status_label.setText(
            f"Cargando datos{' (General)' if refresh_all else f' para {query}'}..."
        )
        self.status_label.setStyleSheet("color: orange; font-style: italic;")

        # Start asynchronous fetch
        self.worker = FetchStockWorker(self.odoo_service, query)
        self.worker.finished.connect(self.on_data_loaded)
        self.worker.error.connect(self.on_data_error)
        self.worker.start()

    def highlight_location(self, item: QTableWidgetItem, location_name: str):
        """Highlights recognized Bur2000 warehouse canonical prefixes"""
        location_upper = location_name.upper()
        if "AB/STOCK" in location_upper:
            item.setBackground(QColor("#E3F2FD"))  # Light blue - Abrera
            item.setForeground(QColor("#0D47A1"))
        elif "VA/STOCK" in location_upper:
            item.setBackground(QColor("#FFE0B2"))  # Light orange - Silla
            item.setForeground(QColor("#E65100"))
        elif "MAD3/" in location_upper:
            item.setBackground(QColor("#E8F5E9"))  # Light green - Madrid
            item.setForeground(QColor("#1B5E20"))
        else:
            item.setForeground(QColor("#424242"))

    def style_quantity(self, item: QTableWidgetItem, qty: float, is_available: bool = False):
        try:
            val = float(qty)
            if val <= 0:
                item.setForeground(QColor("red"))
            elif is_available and val > 0:
                item.setForeground(QColor("green"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
        except:
            pass

    def on_data_loaded(self, results):
        self.btn_search.setEnabled(True)
        self.btn_refresh.setEnabled(True)

        # BUG-003 fix: Primero rellena la tabla, luego la hace visible.
        # Así nunca hay un momento donde los KPI cards tienen datos y la tabla está vacía.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))

        tot_stock = 0.0
        tot_avail = 0.0
        tot_resv = 0.0
        tot_weight = 0.0

        for row, data in enumerate(results):
            # Product
            prod_item = QTableWidgetItem(str(data.get('product', '')))
            
            # Location
            loc_str = str(data.get('location', ''))
            loc_item = QTableWidgetItem(loc_str)
            self.highlight_location(loc_item, loc_str)

            # Quantities
            qty = data.get('qty', 0)
            avail = data.get('available', 0)
            resv = data.get('reserved', 0)
            weight = data.get('total_weight', 0)
            
            tot_stock += qty
            tot_avail += avail
            tot_resv += resv
            tot_weight += weight
            
            qty_item = QTableWidgetItem(f"{qty:.2f}")
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            avail_item = QTableWidgetItem(f"{avail:.2f}")
            avail_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.style_quantity(avail_item, avail, is_available=True)
            
            resv_item = QTableWidgetItem(f"{resv:.2f}")
            resv_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if resv > 0:
                resv_item.setForeground(QColor("#E65100")) # Orange for reserved
                
            weight_item = QTableWidgetItem(f"{weight:.2f}")
            weight_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Orders
            orders_item = QTableWidgetItem(str(data.get('assigned_orders', '')))
            if resv > 0 and not orders_item.text():
                orders_item.setText("Revisar Odoo (Reserva sin origen)")
                orders_item.setForeground(QColor("gray"))
                font = orders_item.font()
                font.setItalic(True)
                orders_item.setFont(font)

            self.table.setItem(row, 0, prod_item)
            self.table.setItem(row, 1, loc_item)
            self.table.setItem(row, 2, qty_item)
            self.table.setItem(row, 3, avail_item)
            self.table.setItem(row, 4, resv_item)
            self.table.setItem(row, 5, weight_item)
            self.table.setItem(row, 6, orders_item)

        self.table.setSortingEnabled(True)

        # KPIs y tabla se actualizan en el mismo momento (no hay race condition)
        self.lbl_total_stock.setText(f"<b>Stock Total (Ud)</b><br><span style='font-size:18px;'>{tot_stock:,.2f}</span>")
        self.lbl_total_avail.setText(f"<b>Disponible (Ud)</b><br><span style='font-size:18px; color:green;'>{tot_avail:,.2f}</span>")
        self.lbl_total_resv.setText(f"<b>Reservado (Ud)</b><br><span style='font-size:18px; color:#E65100;'>{tot_resv:,.2f}</span>")
        self.lbl_total_weight.setText(f"<b>Peso Total (Kg)</b><br><span style='font-size:18px;'>{tot_weight:,.2f}</span>")

        # Ocultar overlay y mostrar tabla (BUG-003)
        self._loading_overlay.setVisible(False)
        self._table_container.setVisible(True)

        self.status_label.setText(f"Mostrando {len(results)} registros.")
        self.status_label.setStyleSheet("color: green; font-style: normal;")

    def on_data_error(self, err_msg):
        self.btn_search.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.status_label.setText(f"Error al cargar: {err_msg}")
        self.status_label.setStyleSheet("color: red; font-style: bold;")
        QMessageBox.warning(self, "Error de Conexión", f"No se pudo cargar el inventario.\nDetalles: {err_msg}")
