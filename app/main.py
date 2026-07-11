import sys
import os
# Fix for restricted sys.path in portable Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QFrame, QHBoxLayout, QTabWidget, QPushButton,
    QFileDialog, QDialog, QMessageBox
)
from PySide6.QtCore import Qt, QBuffer, QIODevice, QThread, Signal, QEventLoop
from PySide6.QtGui import QPixmap
import base64
import datetime
from ui.tabs.logistics_tab import LogisticsTab
from ui.tabs.incidence_tab import IncidenceTab
from ui.tabs.dashboard_tab import DashboardTab
from ui.tabs.technical_tab import TechnicalTab
from ui.tabs.admin_tab import AdminTab
from ui.tabs.improvements_tab import ImprovementsTab
from ui.tabs.analytics_tab import AnalyticsTab
from ui.tabs.inventory_tab import InventoryTab
from ui.tabs.customer_onboarding_tab import CustomerOnboardingTab
from ui.tabs.commercial_conditions_tab import CommercialConditionsTab
from ui.tabs.optimization_tab import OptimizationTab
from db.services.odoo_service_v2 import OdooServiceV2
from db.services.commercial_conditions_service import CommercialConditionsService
from db.services.commercial_service import CommercialService
from ui.tabs.commercial_validator_tab import CommercialValidatorTab
from loguru import logger
from dotenv import load_dotenv
import bur2000_theme

load_dotenv()

# Log file configuration for the Viewer
logger.add("gabriela_rojas.log", rotation="10 MB", backtrace=True, diagnose=True)

class GabrielaRojasApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gabriela Rojas - Panel de Control Bur2000 (v3.5)")
        self.resize(1200, 850)

        
        # Odoo Service setup
        self.odoo_service = OdooServiceV2(
            url=os.getenv("ODOO_URL"),
            db=os.getenv("ODOO_DB"),
            username=os.getenv("ODOO_USER"),
            password=os.getenv("ODOO_PASS")
        )
        
        self.comm_service = CommercialConditionsService()
        self.commercial_validator_service = CommercialService(self.odoo_service)
        
        self._build_ui()
        
    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background-color: {bur2000_theme.BUR.background};")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header (Odoo Top Bar Style)
        header = QFrame()
        header.setMinimumHeight(60)
        header.setStyleSheet(f"background-color: {bur2000_theme.BUR.nav_bg}; border-bottom: 1px solid {bur2000_theme.BUR.primary};")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 0, 20, 0)
        
        title_box = QVBoxLayout()
        title = QLabel("GABRIELA ROJAS")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {bur2000_theme.BUR.nav_text}; letter-spacing: 1px;")
        subtitle = QLabel("Operaciones Logísticas")
        subtitle.setStyleSheet(f"font-size: 10px; color: {bur2000_theme.BUR.secondary}; font-weight: bold; text-transform: uppercase;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        h_lay.addLayout(title_box)
        
        h_lay.addStretch()
        
        # UTILITY BUTTONS (Odoo Navbar Action style)
        btn_box = QHBoxLayout()
        btn_box.setSpacing(20)
        
        util_btn_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {bur2000_theme.BUR.nav_text};
                border: 1px solid {bur2000_theme.BUR.muted};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {bur2000_theme.BUR.muted};
            }}
        """
        
        btn_logs = QPushButton("📜 Historial de Cambios")
        btn_logs.setStyleSheet(util_btn_style)
        btn_logs.clicked.connect(self._show_changelog)
        btn_box.addWidget(btn_logs)

        btn_calc = QPushButton("🧮 Calculadora")
        btn_calc.setStyleSheet(util_btn_style)
        btn_calc.setToolTip("Calculadora logística de productos: pallets, bultos, peso y LDM")
        btn_calc.clicked.connect(self._show_calculator)
        btn_box.addWidget(btn_calc)

        btn_screenshot = QPushButton("📸 Capturar Pantalla")
        btn_screenshot.setStyleSheet(util_btn_style)
        btn_screenshot.setToolTip("Captura la ventana actual y permite guardarla en disco")
        btn_screenshot.clicked.connect(self._take_screenshot)
        btn_box.addWidget(btn_screenshot)
        
        btn_real_logs = QPushButton("📋 Ver Logs")
        btn_real_logs.setStyleSheet(util_btn_style)
        btn_real_logs.clicked.connect(self._show_real_logs)
        btn_box.addWidget(btn_real_logs)
        
        btn_faq = QPushButton("❓ Ayuda")

        btn_faq.setStyleSheet(util_btn_style)
        btn_faq.clicked.connect(self._show_faq)
        btn_box.addWidget(btn_faq)
        
        btn_odoo = QPushButton("🌐 Odoo")
        btn_odoo.setStyleSheet(f"background-color: {bur2000_theme.BUR.secondary}; color: white; border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
        btn_odoo.clicked.connect(self._open_odoo_helpdesk)
        btn_box.addWidget(btn_odoo)
        
        h_lay.addLayout(btn_box)
        
        layout.addWidget(header)
        
        # Tabs (Odoo Menu Style)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(bur2000_theme.BUR.tab_style)
        
        # Initialize tabs
        self.incidence_tab = IncidenceTab(odoo_service=self.odoo_service, parent=self)
        
        self.dashboard_tab = DashboardTab(parent=self)
        self.dashboard_tab.set_stats_service(self.incidence_tab.service)
        self.dashboard_tab.set_odoo_service(self.odoo_service)  # GAP 3 — Estado Catálogo
        
        self.dashboard_tab.navigation_requested.connect(self.tabs.setCurrentIndex)
        self.dashboard_tab.external_link_requested.connect(lambda link: self._open_odoo_helpdesk() if link == "odoo" else None)
        self.dashboard_tab.survey_requested.connect(self._show_survey)
        self.dashboard_tab.mejoras_requested.connect(self._show_mejoras)

        self.logistics_tab = LogisticsTab(conn=None, odoo_service=self.odoo_service, parent=self)
        self.incidence_tab.status_count_changed.connect(self._update_incidence_badge)

        self.technical_tab = TechnicalTab(odoo_service=self.odoo_service, incidence_service=self.incidence_tab.service, parent=self)
        self.analytics_tab = AnalyticsTab(parent=self)
        self.improvements_tab = ImprovementsTab(odoo_service=self.odoo_service, parent=self)

        self.inventory_tab = InventoryTab(odoo_service=self.odoo_service, parent=self)
        self.onboarding_tab = CustomerOnboardingTab(odoo_service=self.odoo_service)
        
        self.commercial_conditions_tab = CommercialConditionsTab(service=self.comm_service, validator_service=self.commercial_validator_service)
        
        self.optimization_tab = OptimizationTab(parent=self)
        self.admin_tab = AdminTab(parent=self)
        
        
        self.tabs.addTab(self.dashboard_tab, "🏠 Inicio")
        self.tabs.addTab(self.logistics_tab, "🚛 Logística")
        self.tabs.addTab(self.incidence_tab, "🎫 Incidencias")
        self.tabs.addTab(self.inventory_tab, "📦 Stock y Artículos")
        self.tabs.addTab(self.onboarding_tab, "🆕 Alta Clientes")
        self.tabs.addTab(self.commercial_conditions_tab, "📈 Condiciones 2026")
        self.tabs.addTab(self.technical_tab, "🤖 Asistente")
        self.tabs.addTab(self.analytics_tab, "📊 Analíticas y ML")
        self.tabs.addTab(self.improvements_tab, "💡 Mejoras")
        self.tabs.addTab(self.optimization_tab, "🚀 Optimización PC")
        self.tabs.addTab(self.admin_tab, "⚙️ Ajustes")

        
        layout.addWidget(self.tabs)
        
        # Developer attribution footer
        footer = QLabel("Software desarrollado por Oscar Piedra Osuna")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 10px; padding: 5px; background: white; border-top: 1px solid {bur2000_theme.BUR.border};")
        layout.addWidget(footer)
        
        self.setCentralWidget(central)

    def _show_changelog(self):
        from ui.dialogs.faq_dialog import FAQDialog
        diag = FAQDialog(self, mode="changelog")
        diag.exec()

    def _show_calculator(self):
        from ui.dialogs.product_calculator_dialog import ProductCalculatorDialog
        dlg = ProductCalculatorDialog(odoo_service=self.odoo_service, parent=self)
        dlg.exec()

    def _show_real_logs(self):
        import os
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gabriela_rojas.log")
        if os.path.exists(log_path):
            os.startfile(log_path)

    def _show_faq(self):
        from ui.dialogs.faq_dialog import FAQDialog
        FAQDialog(self, mode="faq").exec()

    def _show_survey(self):
        from ui.dialogs.survey_dialog import SurveyDialog
        SurveyDialog(self).exec()

    def _show_mejoras(self):
        """Opens the internal email improvements dialog from the Dashboard shortcut."""
        from ui.dialogs.improvements_email_wizard import ImprovementsEmailWizard
        wizard = ImprovementsEmailWizard(initial_text="", odoo_service=self.odoo_service, parent=self)
        wizard.exec()


    def _take_screenshot(self):
        """Captura la ventana principal y permite guardarla o enviarla por Odoo Mail."""
        pixmap: QPixmap = self.grab()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"gabriela_{ts}.png"

        dlg = QDialog(self)
        dlg.setWindowTitle("📸 Captura de Pantalla")
        dlg.setMinimumWidth(400)
        from PySide6.QtWidgets import QVBoxLayout as _VL, QLabel as _QL
        dlg_lay = _VL(dlg)

        preview_lbl = _QL()
        preview_lbl.setPixmap(pixmap.scaledToWidth(380, Qt.TransformationMode.SmoothTransformation))
        dlg_lay.addWidget(preview_lbl)

        info_lbl = _QL(
            f"<b>Captura lista</b> ({pixmap.width()}×{pixmap.height()} px)<br>"
            "Elige qué hacer:"
        )
        info_lbl.setWordWrap(True)
        dlg_lay.addWidget(info_lbl)

        btn_save = QPushButton("💾 Guardar en disco...")
        btn_save.setStyleSheet(
            "background-color: #10B981; color: white; font-weight: bold;"
            " padding: 6px 14px; border-radius: 4px;"
        )
        dlg_lay.addWidget(btn_save)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("padding: 6px 14px;")
        dlg_lay.addWidget(btn_cancel)

        def _do_save():
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Guardar captura", default_name, "PNG (*.png);;All Files (*)"
            )
            if path:
                if pixmap.save(path, "PNG"):
                    QMessageBox.information(dlg, "Guardado", f"Imagen guardada en:\n{path}")
                    logger.info(f"Captura guardada: {path}")
                else:
                    QMessageBox.warning(dlg, "Error", "No se pudo guardar la imagen.")
            dlg.accept()

        btn_save.clicked.connect(_do_save)
        btn_cancel.clicked.connect(dlg.reject)
        dlg.exec()

    def _update_incidence_badge(self, count):
        text = "🎫 Incidencias"
        if count > 0:
            text += f" ({count})"
        self.tabs.setTabText(2, text) # 2 is the index of Incidencias tab

    def _handle_onboarding_request(self, data: dict):
        """Switch to Onboarding tab and fill form with lead data."""
        self.tabs.setCurrentWidget(self.onboarding_tab)
        # We need to implement fill_form_from_dict in CustomerOnboardingTab
        if hasattr(self.onboarding_tab, "fill_form_from_dict"):
            self.onboarding_tab.fill_form_from_dict(data)

    def _open_odoo_helpdesk(self):

        import webbrowser
        url = os.getenv("ODOO_URL", "").rstrip('/')
        if url:
            webbrowser.open(f"{url}/web#action=helpdesk.helpdesk_ticket_dashboard")


class GitUpdateThread(QThread):
    """Comprueba y aplica actualizaciones de git en background."""
    done     = Signal(str, int, str)
    progress = Signal(str)

    def run(self):
        import subprocess
        from pathlib import Path as _P
        repo_dir = str(_P(__file__).parent)

        def _run(*args):
            return subprocess.run(
                ["git", *args], cwd=repo_dir,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
        try:
            self.progress.emit("Comprobando actualizaciones...")
            hash_before = (_run("rev-parse", "HEAD").stdout.strip() or "?")[:7]
            if _run("fetch", "--quiet", "origin").returncode != 0:
                self.done.emit("error", 0, "Sin acceso a git remote")
                return
            pending = len([l for l in _run("log", "HEAD..origin/main", "--oneline").stdout.strip().splitlines() if l.strip()])
            if pending == 0:
                self.done.emit("ok_uptodate", 0, "Sistema al dia")
                return
            self.progress.emit(f"Aplicando {pending} actualizacion(es)...")
            r = _run("pull", "--ff-only", "origin", "main")
            if r.returncode != 0:
                self.done.emit("error", pending, f"Pull fallo: {r.stderr[:120]}")
                return
            hash_after = (_run("rev-parse", "HEAD").stdout.strip() or "?")[:7]
            self.done.emit("ok_updated", pending, f"{pending} actualizacion(es) [{hash_before}->{hash_after}]")
        except subprocess.TimeoutExpired:
            self.done.emit("error", 0, "Timeout")
        except FileNotFoundError:
            self.done.emit("error", 0, "git no encontrado en PATH")
        except Exception as e:
            self.done.emit("error", 0, str(e))


if __name__ == "__main__":
    import subprocess as _sp
    from PySide6.QtGui import QFont

    app = QApplication(sys.argv)

    # Fuente Inter (branding BUR2000)
    _font = QFont()
    _font.setFamily("Inter")
    _font.setPointSize(10)
    app.setFont(_font)

    # Hash git como version
    git_hash = "unknown"
    try:
        _r = _sp.run(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, encoding="utf-8",
            creationflags=_sp.CREATE_NO_WINDOW if hasattr(_sp, 'CREATE_NO_WINDOW') else 0
        )
        if _r.returncode == 0:
            git_hash = _r.stdout.strip()[:7]
    except Exception:
        pass

    from ui.components.splash_screen import BurSplashScreen
    splash = BurSplashScreen(app_name="Gabriela Rojas", app_version=git_hash, show_git_status=True)
    splash.show()
    splash.set_progress(5, "Verificando actualizaciones...")
    app.processEvents()

    # Git update en background
    git_thread = GitUpdateThread()
    git_loop   = QEventLoop()
    git_thread.done.connect(lambda st, n, m: (splash.set_git_status(st, m), git_loop.quit()))
    git_thread.progress.connect(lambda msg: splash.set_progress(8, msg))
    git_thread.start()
    git_loop.exec()

    splash.set_progress(50, "Cargando panel de control...")
    app.processEvents()

    window = GabrielaRojasApp()

    splash.set_progress(100, "Listo")
    app.processEvents()

    splash.finish(window)
    window.showMaximized()
    sys.exit(app.exec())
