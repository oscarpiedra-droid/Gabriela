from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QGridLayout, QScrollArea,
    QSizePolicy, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QPoint, QTimer, QThread
from PySide6.QtGui import QPixmap, QImage
import bur2000_theme
from loguru import logger
import io
import os


class StatsRefreshWorker(QThread):
    """Worker para cargar estadísticas de incidencias en segundo plano (BUG-006 fix)."""
    done = Signal(dict)
    error = Signal(str)

    def __init__(self, stats_service):
        super().__init__()
        self.stats_service = stats_service

    def run(self):
        try:
            stats = self.stats_service.get_incidence_stats()
            self.done.emit(stats or {})
        except Exception as e:
            self.error.emit(str(e))


class CatalogQualityWorker(QThread):
    """Worker: analiza calidad de datos del catálogo Odoo (GAP 3)."""
    done  = Signal(dict)
    error = Signal(str)

    def __init__(self, odoo_service):
        super().__init__()
        self.svc = odoo_service

    def run(self):
        svc = self.svc
        if not svc:
            self.error.emit("Sin conexión Odoo")
            return
        try:
            def _ex(model, method, *args, **kw):
                try:
                    acquired = svc._lock.acquire(timeout=8)
                    if not acquired:
                        return [] if method in ("search", "search_read") else None
                    try:
                        svc._ensure_connected()
                        return getattr(svc.odoo.env[model], method)(*args, **kw)
                    finally:
                        svc._lock.release()
                except Exception as e:
                    logger.warning(f"[Catalog QA] {model}.{method}: {e}")
                    return [] if method in ("search", "search_read") else None

            # Total productos activos con SKU
            all_ids = _ex("product.product", "search",
                          [["active", "=", True], ["default_code", "!=", False]], limit=2000)
            total = len(all_ids) if all_ids else 0

            if total == 0:
                self.done.emit({"total": 0, "sin_upp": 0, "sin_peso": 0, "sin_dims": 0})
                return

            # Productos sin embalaje (sin UPP)
            pkg_ids = _ex("product.packaging", "search", [["product_id.active", "=", True]], limit=5000)
            prods_con_pkg: set = set()
            if pkg_ids:
                pkg_rows = _ex("product.packaging", "read", pkg_ids[:500], ["product_id"]) or []
                for r in pkg_rows:
                    pid = r.get("product_id")
                    if pid:
                        prods_con_pkg.add(int(pid[0]))
            sin_upp = max(0, total - len(prods_con_pkg))

            # Productos sin peso
            no_weight_ids = _ex("product.product", "search",
                                [["active", "=", True], ["default_code", "!=", False],
                                 ["weight", "=", 0.0]], limit=2000)
            sin_peso = len(no_weight_ids) if no_weight_ids else 0

            # Productos sin volumen (proxy de sin dimensiones)
            no_vol_ids = _ex("product.product", "search",
                             [["active", "=", True], ["default_code", "!=", False],
                              ["volume", "=", 0.0]], limit=2000)
            sin_dims = len(no_vol_ids) if no_vol_ids else 0

            self.done.emit({
                "total":    total,
                "sin_upp":  sin_upp,
                "sin_peso": sin_peso,
                "sin_dims": sin_dims,
            })
        except Exception as e:
            logger.error(f"[Catalog QA] Error: {e}")
            self.error.emit(str(e))



class DashboardCard(QFrame):
    clicked = Signal()
    
    def __init__(self, title, icon, color, description, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 160) # Set reasonable minimums, not absolute fixed geometry
        self.setMaximumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.color = color
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        self.icon_label = QLabel(icon)
        self.icon_label.setStyleSheet(f"font-size: 42px; background: transparent;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {bur2000_theme.BUR.text};")
        self.title_label.setAlignment(Qt.AlignCenter)
        
        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet(f"font-size: 11px; color: {bur2000_theme.BUR.muted};")
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)
        
        self.setStyleSheet(f"""
            DashboardCard {{
                background-color: white;
                border: 1px solid {bur2000_theme.BUR.border};
                border-radius: 12px;
                border-bottom: 4px solid {color};
            }}
        """)
        
        # Hover Animation
        self._ani = QPropertyAnimation(self, b"pos")
        self._ani.setDuration(150)

    def enterEvent(self, event):
        self.setStyleSheet(self.styleSheet().replace("background-color: white;", f"background-color: {bur2000_theme.BUR.background};"))
        self.setGraphicsEffect(None) # Clear any effect
        # Simple lift using margin-top is more reliable in grids than pos() animation
        self.setContentsMargins(0, 0, 0, 5) 
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self.styleSheet().replace(f"background-color: {bur2000_theme.BUR.background};", "background-color: white;"))
        self.setContentsMargins(0, 5, 0, 0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

class DashboardTab(QWidget):
    navigation_requested = Signal(int)    # index of tab to switch to
    external_link_requested = Signal(str) # category/id for external URL
    survey_requested = Signal()
    mejoras_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stats_service = None  # Set by main
        self.odoo_service  = None  # Set by main (para GAP 3)
        self._catalog_worker: CatalogQualityWorker | None = None
        self._build_ui()
        
    def set_stats_service(self, service):
        self.stats_service = service
        # Refresh stats every 5 mins
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_stats)
        self.refresh_timer.start(5 * 60 * 1000)
        QTimer.singleShot(1000, self.refresh_stats)

    def set_odoo_service(self, odoo_svc):
        """Inyectar el servicio Odoo para el panel de calidad de catálogo (GAP 3)."""
        self.odoo_service = odoo_svc
        QTimer.singleShot(3000, self.refresh_catalog_quality)

        
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(20)
        
        # Welcome Header (Smaller to fit stats)
        welcome = QLabel("¡Hola, Gabriela! 👋")
        welcome.setStyleSheet(f"font-size: 28px; font-weight: 800; color: {bur2000_theme.BUR.primary};")
        main_layout.addWidget(welcome)
        
        # Content Layout
        content_lay = QHBoxLayout()
        content_lay.setSpacing(40)
        
        # Left: Cards Grid
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(20)
        grid.setContentsMargins(0, 0, 0, 0)
        
        cards = [
            ("Logística", "🚛", bur2000_theme.BUR.secondary, "Albaranes y envíos.", 1),
            ("Incidencias", "🎫", bur2000_theme.BUR.primary, "Post-venta y calidad.", 2),
            ("Stock y Artículos", "📦", "#4a148c", "Inventario y referencias.", 3),
            ("Alta Clientes", "🆕", bur2000_theme.BUR.primary, "Ficha comercial.", 4),
            ("Condiciones 2026", "📈", "#059669", "Rangos de DTOS.", 5),
            ("Asistente Técnico", "🤖", "#4a148c", "IA de soporte.", 6),
            ("Analíticas y ML", "📊", "#2563eb", "Predicciones y métricas.", 7),
            ("Mejoras", "💡", "#fbbf24", "Sugerencias y tareas.", 8),
            ("Optimización PC", "🚀", "#e11d48", "Limpieza y RAM.", 9),
            ("Ajustes", "⚙️", bur2000_theme.BUR.muted, "Preferencias.", 10)
        ]

        for i, (title, icon, color, desc, target) in enumerate(cards):
            card = DashboardCard(title, icon, color, desc, self)
            if isinstance(target, int):
                card.clicked.connect(lambda t=target: self.navigation_requested.emit(t))
            elif target == "survey":
                card.clicked.connect(self.survey_requested.emit)
            elif target == "mejoras":
                card.clicked.connect(self.mejoras_requested.emit)
            else:
                card.clicked.connect(lambda t=target: self.external_link_requested.emit(t))
            
            grid.addWidget(card, i // 4, i % 4) # Switch to 4 columns to fit them better when maximized
            
        # Give column stretch to grid so it stays balanced
        for c in range(4):
            grid.setColumnStretch(c, 1)

        content_lay.addWidget(grid_widget, 3) # Give more horizontal weight to grid vs stats
        
        # Right: Stats Panel (contenedor con dos tarjetas)
        right_col = QWidget()
        right_lay = QVBoxLayout(right_col)
        right_lay.setSpacing(16)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # ── Tarjeta: Estado de Incidencias ──────────────────────────────────
        self.stats_panel = QFrame()
        self.stats_panel.setStyleSheet(
            f"background: white; border: 1px solid {bur2000_theme.BUR.border};"
            f" border-radius: 15px;"
        )
        sp_lay = QVBoxLayout(self.stats_panel)
        sp_lay.setContentsMargins(20, 20, 20, 20)

        sp_title = QLabel("📊 Estado de Incidencias")
        sp_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {bur2000_theme.BUR.text};")
        sp_lay.addWidget(sp_title)

        self.lbl_stats_summary = QLabel("Cargando métricas...")
        self.lbl_stats_summary.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 12px;")
        sp_lay.addWidget(self.lbl_stats_summary)

        self.chart_label = QLabel()
        self.chart_label.setMinimumSize(280, 240)
        self.chart_label.setAlignment(Qt.AlignCenter)
        sp_lay.addWidget(self.chart_label)

        sp_lay.addSpacing(12)
        btn_report = QPushButton("📊 Generar Cierre Mensual")
        btn_report.setStyleSheet(bur2000_theme.BUR.button_primary)
        btn_report.setFixedHeight(38)
        btn_report.clicked.connect(self._generate_monthly_report)
        sp_lay.addWidget(btn_report)
        sp_lay.addStretch()

        right_lay.addWidget(self.stats_panel)

        # ── Tarjeta: Estado Catálogo Odoo (GAP 3) ───────────────────────────
        self.catalog_panel = QFrame()
        self.catalog_panel.setStyleSheet(
            f"background: white; border: 1px solid {bur2000_theme.BUR.border};"
            f" border-radius: 15px;"
        )
        cat_lay = QVBoxLayout(self.catalog_panel)
        cat_lay.setContentsMargins(20, 16, 20, 16)
        cat_lay.setSpacing(10)

        # Cabecera con botón refresh
        cat_header = QHBoxLayout()
        cat_title = QLabel("🗂️ Estado Catálogo Odoo")
        cat_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {bur2000_theme.BUR.text};")
        cat_header.addWidget(cat_title)
        cat_header.addStretch()
        btn_cat_refresh = QPushButton("↻")
        btn_cat_refresh.setFixedSize(28, 28)
        btn_cat_refresh.setToolTip("Actualizar diagnóstico catálogo")
        btn_cat_refresh.setStyleSheet(
            f"QPushButton {{ background: {bur2000_theme.BUR.surface}; border: 1px solid"
            f" {bur2000_theme.BUR.border}; border-radius: 6px; font-size: 14px; }}"
            f" QPushButton:hover {{ background: {bur2000_theme.BUR.primary}; color: white; }}"
        )
        btn_cat_refresh.clicked.connect(self.refresh_catalog_quality)
        cat_header.addWidget(btn_cat_refresh)
        cat_lay.addLayout(cat_header)

        # KPI rows
        self._cat_kpis: dict[str, QLabel] = {}
        kpi_defs = [
            ("total",    "📦 Productos activos",   bur2000_theme.BUR.text),
            ("sin_upp",  "⚠️ Sin embalaje/UPP",    bur2000_theme.BUR.STATUS_WAITING),
            ("sin_peso", "⚠️ Sin peso definido",   bur2000_theme.BUR.STATUS_WAITING),
            ("sin_dims", "⚠️ Sin volumen/dims",    bur2000_theme.BUR.STATUS_WAITING),
        ]
        for key, label_text, color in kpi_defs:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 12px; color: {bur2000_theme.BUR.muted};")
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")
            val.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            cat_lay.addLayout(row)
            self._cat_kpis[key] = val

        self.lbl_cat_status = QLabel("Esperando conexión Odoo...")
        self.lbl_cat_status.setStyleSheet(f"font-size: 11px; color: {bur2000_theme.BUR.muted}; font-style: italic;")
        self.lbl_cat_status.setAlignment(Qt.AlignCenter)
        cat_lay.addWidget(self.lbl_cat_status)

        right_lay.addWidget(self.catalog_panel)
        right_lay.addStretch()

        content_lay.addWidget(right_col, 1)
        
        main_layout.addLayout(content_lay)
        main_layout.addStretch()

    def refresh_stats(self):
        """Lanza el worker de estadísticas en un QThread (fix BUG-006)."""
        if not self.stats_service:
            return
        # Cancelar worker previo si sigue corriendo
        if hasattr(self, '_stats_worker') and self._stats_worker and self._stats_worker.isRunning():
            return  # ya hay uno en marcha, no lanzar otro
        self.lbl_stats_summary.setText("Actualizando...")
        self._stats_worker = StatsRefreshWorker(self.stats_service)
        self._stats_worker.done.connect(self._on_stats_loaded)
        self._stats_worker.error.connect(self._on_stats_error)
        self._stats_worker.start()

    def refresh_catalog_quality(self):
        """Lanza el worker de calidad del catálogo Odoo (GAP 3)."""
        if not self.odoo_service:
            self.lbl_cat_status.setText("Sin conexión Odoo configurada")
            return
        if self._catalog_worker and self._catalog_worker.isRunning():
            return
        self.lbl_cat_status.setText("⏳ Analizando catálogo...")
        for v in self._cat_kpis.values():
            v.setText("…")
        self._catalog_worker = CatalogQualityWorker(self.odoo_service)
        self._catalog_worker.done.connect(self._on_catalog_loaded)
        self._catalog_worker.error.connect(self._on_catalog_error)
        self._catalog_worker.start()

    def _on_catalog_loaded(self, data: dict):
        total    = data.get("total", 0)
        sin_upp  = data.get("sin_upp", 0)
        sin_peso = data.get("sin_peso", 0)
        sin_dims = data.get("sin_dims", 0)

        self._cat_kpis["total"].setText(str(total))
        self._cat_kpis["sin_upp"].setText(f"{sin_upp}  ({int(sin_upp/total*100) if total else 0}%)")
        self._cat_kpis["sin_peso"].setText(f"{sin_peso}  ({int(sin_peso/total*100) if total else 0}%)")
        self._cat_kpis["sin_dims"].setText(f"{sin_dims}  ({int(sin_dims/total*100) if total else 0}%)")

        # Color semafórico en sin_upp (el más crítico para logística)
        pct = sin_upp / total if total else 0
        color = (
            bur2000_theme.BUR.STATUS_READY    if pct < 0.1 else
            bur2000_theme.BUR.STATUS_WAITING  if pct < 0.3 else
            bur2000_theme.BUR.STATUS_ERROR
        )
        self._cat_kpis["sin_upp"].setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")

        from datetime import datetime
        ts = datetime.now().strftime("%H:%M")
        self.lbl_cat_status.setText(f"Actualizado a las {ts}")
        logger.info(f"[Dashboard GAP3] Catálogo: {total} prods, {sin_upp} sin UPP")

    def _on_catalog_error(self, err: str):
        logger.warning(f"[Dashboard GAP3] Error catálogo: {err}")
        self.lbl_cat_status.setText(f"⚠️ Error: {err[:60]}")

    def _on_stats_loaded(self, stats: dict):
        """Recibe estadísticas del worker y actualiza la UI."""
        if not stats:
            self.lbl_stats_summary.setText("Sin datos de incidencias")
            return
        total = stats.get('total', 0)
        self.lbl_stats_summary.setText(
            f"<b>{total}</b> ticket{'s' if total != 1 else ''} activo{'s' if total != 1 else ''}"
        )
        wh_data = stats.get('by_warehouse', {})
        # Filtrar almacenes con 0 tickets para que el gráfico no esté plano
        wh_data_filtered = {k: v for k, v in wh_data.items() if v > 0}
        if wh_data_filtered:
            self._render_chart(wh_data_filtered)
        elif total > 0:
            # Hay tickets pero sin almacén detectado — mostrar total genérico
            self._render_chart({'Sin clasificar': total})
        else:
            self._render_chart({'Sin incidencias': 0})

    def _on_stats_error(self, err: str):
        from loguru import logger
        logger.error(f"Error cargando stats dashboard: {err}")
        self.lbl_stats_summary.setText("Error al cargar incidencias")

    def _generate_monthly_report(self):
        """Creates a professional Excel closing for the month."""
        if not self.stats_service: return
        
        try:
            import pandas as pd
            from datetime import datetime
            
            self.lbl_stats_summary.setText("⏳ Generando reporte...")
            
            # Fetch full list for the report
            tickets = self.stats_service.get_active_incidences()
            stats = self.stats_service.get_incidence_stats()
            
            if not tickets:
                QMessageBox.warning(self, "Sin datos", "No hay incidencias activas este mes.")
                return

            default_name = f"Cierre_Mensual_Gabriela_{datetime.now().strftime('%Y_%m')}.xlsx"
            path, _ = QFileDialog.getSaveFileName(self, "Guardar Cierre Mensual", default_name, "Excel Files (*.xlsx)")
            if not path:
                return

            # Create multiple sheets
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                # 1. Summary Sheet
                summary_data = []
                for k, v in stats['by_warehouse'].items():
                    summary_data.append({'Almacén': k, 'Tickets Activos': v})
                
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Resumen Almacenes', index=False)
                
                # 2. Detailed Sheet
                pd.DataFrame(tickets).to_excel(writer, sheet_name='Detalle Incidencias', index=False)
            
            QMessageBox.information(self, "Reporte Hecho", f"El cierre mensual se ha guardado en:\n{path}")
            os.startfile(path)
            self.refresh_stats()
            
        except Exception as e:
            QMessageBox.critical(self, "Error de Reporte", f"No se pudo generar el Excel: {e}")
            self.refresh_stats()

    def _render_chart(self, wh_data):

        try:
            import matplotlib.pyplot as plt
            import numpy as np
            
            # Use Agg backend for headless/Qt
            plt.switch_backend('Agg')
            
            fig, ax = plt.subplots(figsize=(4, 4), dpi=80)
            fig.patch.set_facecolor('none')
            ax.set_facecolor('none')
            
            names = list(wh_data.keys())
            values = list(wh_data.values())
            colors = [bur2000_theme.BUR.primary, bur2000_theme.BUR.secondary, bur2000_theme.BUR.accent, bur2000_theme.BUR.muted]
            
            # Clean plot
            ax.bar(names, values, color=colors[:len(names)])
            ax.set_title("Tickets por Almacén", color=bur2000_theme.BUR.text, fontsize=12, fontweight='bold')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.tick_params(colors=bur2000_theme.BUR.muted, labelsize=10)
            
            # Save to buffer
            buf = io.BytesIO()
            plt.savefig(buf, format='png', transparent=True, bbox_inches='tight')
            plt.close(fig)
            
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue())
            self.chart_label.setPixmap(pixmap)
        except Exception as e:
            from loguru import logger
            logger.error(f"Chart Render Error: {e}")

