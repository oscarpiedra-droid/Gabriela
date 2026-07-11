from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from ui.tabs.stock_tab import StockTab
from ui.tabs.articles_tab import ArticlesTab
from ui.tabs.product_query_tab import ProductQueryTab

class InventoryTab(QWidget):
    def __init__(self, odoo_service, parent=None):
        super().__init__(parent)
        self.odoo_service = odoo_service
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        self.stock_subtab        = StockTab(self.odoo_service)
        self.articles_subtab     = ArticlesTab(self.odoo_service)
        self.product_query_subtab = ProductQueryTab(self.odoo_service)
        
        self.tabs.addTab(self.stock_subtab,         "📦 Existencias (Stock)")
        self.tabs.addTab(self.articles_subtab,       "🏷️ Artículos y Pedidos")
        self.tabs.addTab(self.product_query_subtab,  "🔍 Consulta de Producto")
        
        layout.addWidget(self.tabs)
