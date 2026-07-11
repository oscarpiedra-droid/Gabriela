from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QFormLayout, QGroupBox, QSplitter
)
from PySide6.QtCore import Qt
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import seaborn as sns
import bur2000_theme

from db.services.analytics_service import AnalyticsService
import warnings
warnings.filterwarnings('ignore') # Matplotlib / seaborn compatibility warnings suppression

# Ensure seaborn uses a decent style
sns.set_theme(style="darkgrid")
# Update matplotlib parameters according to dark theme
plt.rcParams.update({
    "figure.facecolor": bur2000_theme.BUR.background,
    "axes.facecolor": bur2000_theme.BUR.nav_bg,
    "text.color": bur2000_theme.BUR.text,
    "axes.labelcolor": bur2000_theme.BUR.text,
    "xtick.color": bur2000_theme.BUR.text,
    "ytick.color": bur2000_theme.BUR.text,
})

class AnalyticsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = AnalyticsService()
        self.service.train_model() # Train immediately on synthetic data
        self._build_ui()
        self._plot_metrics()
        
    def _build_ui(self):
        title_style = f"font-size: 16px; font-weight: bold; color: {bur2000_theme.BUR.primary};"
        group_box_style = f"font-weight: bold; color: {bur2000_theme.BUR.text};"
        
        main_layout = QHBoxLayout(self)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel (Charts)
        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)
        
        title = QLabel("📊 Distribución Histórica (Datos Sintéticos)")
        title.setStyleSheet(title_style)
        chart_layout.addWidget(title)
        
        self.figure, self.axes = plt.subplots(2, 1, figsize=(6, 8))
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        
        splitter.addWidget(chart_widget)
        
        # Right Panel (ML & Predictor)
        ml_widget = QWidget()
        ml_layout = QVBoxLayout(ml_widget)
        
        ml_title = QLabel("🤖 Predictor de Portes (Machine Learning)")
        ml_title.setStyleSheet(title_style)
        ml_layout.addWidget(ml_title)
        
        # Stats Group
        stats_group = QGroupBox("Resumen de Datos Generados")
        stats_group.setStyleSheet(group_box_style)
        stats_layout = QFormLayout(stats_group)
        stats = self.service.get_summary_stats()
        stats_layout.addRow("Órdenes Simuladas:", QLabel(str(stats.get("Total_Orders", 0))))
        stats_layout.addRow("Coste Promedio Envío:", QLabel(f"{stats.get('Avg_Shipping', 0):.2f} €"))
        stats_layout.addRow("Familias Únicas:", QLabel(str(stats.get("Families", 0))))
        ml_layout.addWidget(stats_group)
        
        # Predictor Group
        pred_group = QGroupBox("Proyección de Coste por Pedido")
        pred_group.setStyleSheet(group_box_style)
        pred_form = QFormLayout(pred_group)
        
        self.cb_zone = QComboBox()
        self.cb_zone.addItems(self.service.label_encoders.get("ZONA", {}).classes_ if "ZONA" in self.service.label_encoders else ["PENINSULA", "BALEARES", "CANARIAS", "INTERNACIONAL"])
        
        self.cb_family = QComboBox()
        self.cb_family.addItems(self.service.label_encoders.get("FAMILIA", {}).classes_ if "FAMILIA" in self.service.label_encoders else ["default"])
        
        self.sp_weight = QSpinBox()
        self.sp_weight.setRange(10, 10000)
        self.sp_weight.setValue(100)
        self.sp_weight.setSuffix(" kg")
        
        pred_form.addRow("Zona Destino:", self.cb_zone)
        pred_form.addRow("Familia Prod:", self.cb_family)
        pred_form.addRow("Peso Estimado:", self.sp_weight)
        
        btn_predict = QPushButton("🔮 Predecir Coste con Random Forest")
        btn_predict.setStyleSheet(bur2000_theme.BUR.button_primary)
        btn_predict.clicked.connect(self._run_prediction)
        pred_form.addRow(btn_predict)
        
        self.lbl_result = QLabel("---")
        self.lbl_result.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {bur2000_theme.BUR.primary}; margin-top: 15px;")
        self.lbl_result.setAlignment(Qt.AlignCenter)
        pred_form.addRow(self.lbl_result)
        
        ml_layout.addWidget(pred_group)
        ml_layout.addStretch()
        
        splitter.addWidget(ml_widget)
        # 60/40 ratio
        splitter.setSizes([600, 400])
        
        main_layout.addWidget(splitter)
        
    def _plot_metrics(self):
        df = self.service.df
        if df is None or len(df) == 0:
            return
            
        self.axes[0].clear()
        self.axes[1].clear()
        
        # Plot 1: Shipping Cost Distribution by Zone
        sns.boxplot(data=df, x="ZONA", y="COSTE_ENVIO_EUR", ax=self.axes[0], palette="Set2")
        self.axes[0].set_title("Coste de Envío vs Zona")
        self.axes[0].set_ylabel("Coste (€)")
        
        # Plot 2: Average Shipping by Family (Top 10)
        top_families = df.groupby("FAMILIA")["COSTE_ENVIO_EUR"].mean().sort_values(ascending=False).head(10)
        sns.barplot(x=top_families.values, y=top_families.index, ax=self.axes[1], palette="magma")
        self.axes[1].set_title("Top 10 Coste Promedio por Familia")
        self.axes[1].set_xlabel("Coste Promedio (€)")
        
        self.figure.tight_layout()
        self.canvas.draw()
        
    def _run_prediction(self):
        z = self.cb_zone.currentText()
        f = self.cb_family.currentText()
        w = self.sp_weight.value()
        
        res = self.service.predict_shipping(z, f, w)
        self.lbl_result.setText(res)
