"""
Splash screen with progress bar for application startup.
Unified design based on DashCoo implementation for Grupo BUR2000.
"""
from PySide6.QtWidgets import QSplashScreen, QProgressBar, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
import bur2000_theme
import os

class BurSplashScreen(QSplashScreen):
    def __init__(self, app_name="Grupo BUR2000", app_version="1.0.0", show_git_status=True):
        # Create a transparent splash pixmap
        pixmap = QPixmap(800, 680)
        pixmap.fill(Qt.transparent)
        
        super().__init__(pixmap, Qt.WindowStaysOnTopHint)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        
        self.app_name = app_name
        self.app_version = app_version
        
        # Try to load the company logo
        self.logo_pixmap = None
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        logo_path = os.path.join(base_dir, "assets", "BUR2000-logo-color.png")
        if os.path.exists(logo_path):
            self.logo_pixmap = QPixmap(logo_path)
        
        # Create progress bar below logo with modern gradient style
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setGeometry(150, 400, 500, 30)
        
        # Get colors from theme or use fallbacks
        theme_blue = getattr(getattr(bur2000_theme, 'BUR', None), 'blue', "#1e3a8a")
        theme_text = getattr(getattr(bur2000_theme, 'BUR', None), 'text', "#1e293b")
        theme_font = getattr(getattr(bur2000_theme, 'BUR', None), 'font_family', "Segoe UI")
        self.theme_font = theme_font
        
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 2px solid {theme_blue};
                border-radius: 15px;
                background-color: rgba(255, 255, 255, 0.9);
                text-align: center;
                font-weight: bold;
                color: {theme_text};
                font-size: 12px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {theme_blue}, 
                    stop:0.5 #5ec575,
                    stop:1 #f39c12);
                border-radius: 13px;
            }}
        """)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        # Status label below progress bar
        self.status_label = QLabel(f"Iniciando {app_name}...", self)
        self.status_label.setGeometry(50, 445, 700, 30)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"""
            color: {theme_text};
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 0.5px;
            background-color: rgba(255, 255, 255, 0.8);
            border-radius: 5px;
            padding: 5px;
        """)
        
        # Timestamp label
        from datetime import datetime
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S")
        self.time_label = QLabel(f"Estado: ⏳ Iniciando ({timestamp})", self)
        self.time_label.setGeometry(50, 485, 700, 30)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("""
            color: #10b981;
            font-size: 13px;
            font-weight: 600;
            background-color: rgba(16, 185, 129, 0.1);
            border-radius: 6px;
            padding: 5px;
        """)
        
        # Git Status Label
        self.git_label = QLabel(self)
        self.git_label.setGeometry(50, 525, 700, 30)
        self.git_label.setAlignment(Qt.AlignCenter)
        if show_git_status:
            self.set_git_status("loading", "Verificando actualizaciones de Git...")
        else:
            self.git_label.hide()
            
        self.showMessage("", Qt.AlignBottom | Qt.AlignCenter, QColor("white"))

    def showMessage(self, message, alignment=Qt.AlignBottom, color=QColor("white")):
        """Override to update the status label and repaint instead of native QSplashScreen drawing."""
        if message:
            self.status_label.setText(message)
            from datetime import datetime
            now = datetime.now()
            timestamp = now.strftime("%H:%M:%S")
            self.time_label.setText(f"Estado: ⏳ {message} ({timestamp})")
        self.repaint()

    def set_git_status(self, estado, mensaje):
        """
        Update the git status label.
        estado = 'ok_uptodate' | 'ok_updated' | 'error' | 'loading'
        """
        if estado == "ok_uptodate":
            style = """
                color: #10b981;
                font-size: 12px;
                font-weight: bold;
                background-color: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 6px;
                padding: 4px;
            """
            prefix = "✅ "
        elif estado == "ok_updated":
            style = """
                color: #3b82f6;
                font-size: 12px;
                font-weight: bold;
                background-color: rgba(59, 130, 246, 0.08);
                border: 1px solid rgba(59, 130, 246, 0.2);
                border-radius: 6px;
                padding: 4px;
            """
            prefix = "⬇️  "
        elif estado == "error":
            style = """
                color: #6b7280;
                font-size: 12px;
                font-weight: bold;
                background-color: rgba(107, 114, 128, 0.08);
                border: 1px solid rgba(107, 114, 128, 0.2);
                border-radius: 6px;
                padding: 4px;
            """
            prefix = "ℹ️  "
        else:  # loading
            style = """
                color: #f59e0b;
                font-size: 12px;
                font-weight: bold;
                background-color: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.2);
                border-radius: 6px;
                padding: 4px;
            """
            prefix = "🔄 "
            
        self.git_label.setStyleSheet(style)
        self.git_label.setText(f"{prefix}{mensaje}")
        self.git_label.show()
        self.repaint()

    def drawContents(self, painter: QPainter):
        # Enable anti-aliasing for smooth rendering
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # Draw white background with rounded corners
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 800, 680, 20, 20)
        
        # Draw company logo in center (transparent background)
        if self.logo_pixmap:
            # Scale logo to fit nicely
            logo_width = 500
            logo_height = 300
            scaled_logo = self.logo_pixmap.scaled(
                logo_width, logo_height, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            # Center the logo
            x = (800 - scaled_logo.width()) // 2
            y = 50
            painter.drawPixmap(x, y, scaled_logo)
        else:
            # Fallback text if logo not found
            theme_blue = getattr(getattr(bur2000_theme, 'BUR', None), 'blue', "#1e3a8a")
            painter.setPen(QColor(theme_blue))
            font = QFont(self.theme_font, 48, QFont.Bold)
            painter.setFont(font)
            painter.drawText(0, 120, 800, 80, Qt.AlignCenter, "BUR 2000")
            
            # Subtitle
            font = QFont(self.theme_font, 18)
            painter.setFont(font)
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(0, 210, 800, 40, Qt.AlignCenter, "AISLAMIENTO INTEGRAL")
        
        # Title of the app or "Grupo BUR2000" in bold below logo
        font = QFont(self.theme_font, 14, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#1e293b"))
        painter.drawText(0, 360, 800, 30, Qt.AlignCenter, "Grupo BUR2000")
        
        # Version at bottom
        font = QFont(self.theme_font, 10)
        painter.setFont(font)
        painter.setPen(QColor(120, 120, 120))
        painter.drawText(0, 640, 800, 30, Qt.AlignCenter, f"{self.app_name} v{self.app_version}")
        
        super().drawContents(painter)

    def setProgress(self, pct):
        """Alias for compatibility with legacy setProgress calls."""
        self.set_progress(pct)

    def set_progress(self, value, message=""):
        """Update progress bar and status message."""
        self.progress_bar.setValue(value)
        if message:
            self.status_label.setText(message)
            
        # Update timestamp on major steps
        from datetime import datetime
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S")
        self.time_label.setText(f"Estado: ⏳ {message} ({timestamp})")
        
        self.repaint()
