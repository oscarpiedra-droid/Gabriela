from dataclasses import dataclass


@dataclass(frozen=True)
class BurTheme:
    bg: str
    bg_alt: str
    surface: str
    text: str
    muted: str
    border: str
    blue: str
    green: str
    orange: str
    purple: str
    secondary: str  # Added
    surface_hover: str  # Added
    surface_dark: str  # Added
    # Semantic colors
    danger: str
    danger_light: str  # New
    warning: str
    success: str
    info: str
    # Skill Levels
    lvl1: str
    lvl2: str
    lvl3: str
    # Premium
    glass: str
    font_family: str = "'Plus Jakarta Sans', 'Inter', 'Segoe UI', sans-serif"
    radius: int = 12
    shadow: str = "0 4px 12px rgba(0, 0, 0, 0.1)"
    # Extras for Pro Header
    highlight: str = "#714B67"
    highlight_bg: str = "#F3E8FF"  # Added this one as it was used in step 54/55
    primary_dark: str = "#5D3D55"
    blue_hover: str = "#4338ca"
    bg_hover: str = "#F1F5F9"  # Default light hover
    success_alt: str = "#DCFCE7" # Light green bg
    danger_alt: str = "#FEE2E2"  # Light red bg
    info_alt: str = "#E0F2FE"    # Light sky bg
    # Animations & Effects
    transition_fast: str = "all 0.2s ease-in-out"
    transition_base: str = "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
    gradient_prime: str = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1D365C, stop:1 #2D5288)"
    gradient_success: str = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669)"


# LOGÍSTICA BUR2000 Premium Theme (Modern Slate & Royal Blue)
BUR = BUR_DEFAULT = BurTheme(
    bg="#F8FAFC",          # Slate 50 (Modern App BG)
    bg_alt="#F1F5F9",      # Slate 100
    surface="#FFFFFF",     # Pure white for cards/panels
    text="#0F172A",        # Slate 900 (Sharp, readable text)
    muted="#64748B",       # Slate 500 (Secondary text)
    border="#E2E8F0",      # Slate 200 (Soft borders)
    blue="#2563EB",        # Blue 600 (Vibrant interaction)
    green="#10B981",       # Emerald 500
    orange="#F59E0B",      # Amber 500
    purple="#8B5CF6",      # Violet 500
    secondary="#6366F1",   # Indigo 500
    surface_hover="#F1F5F9", # Hover state
    surface_dark="#E2E8F0",  # Slate 200 (slightly darker)
    danger="#EF4444",      # Red 500
    danger_light="#FEE2E2",
    warning="#F59E0B",
    success="#10B981",
    info="#3B82F6",
    lvl1="#F8FAFC",
    lvl2="#E2E8F0",
    lvl3="#CBD5E1",
    glass="rgba(255, 255, 255, 0.85)",
    font_family="'Inter', 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif",
    radius=12,
    shadow="0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
    highlight="#1D4ED8",   # Blue 700
    primary_dark="#1E3A8A",# Blue 900
    blue_hover="#1D4ED8",  # Blue 700
    bg_hover="#F1F5F9",
    success_alt="#D1FAE5",
    danger_alt="#FEE2E2",
    info_alt="#DBEAFE",
)

# Dark Theme (Premium Zinc & Indigo)
BUR_DARK = BurTheme(
    bg="#09090B",          # Zinc 950
    bg_alt="#18181B",      # Zinc 900
    surface="#18181B",     # Surface matching Zinc 900
    text="#FAFAFA",        # Zinc 50
    muted="#A1A1AA",       # Zinc 400
    border="#27272A",      # Zinc 800
    blue="#3B82F6",        # Blue 500
    green="#22C55E",       # Emerald 500
    orange="#F59E0B",      # Amber 500
    purple="#8B5CF6",      # Violet 500
    secondary="#6366F1",   # Indigo 500
    surface_hover="#27272A", # Zinc 800
    surface_dark="#09090B",  # Zinc 950 (darker surface)
    danger="#EF4444",      # Red 500
    danger_light="#450A0A",# Very dark red
    warning="#F59E0B",
    success="#22C55E",
    info="#3B82F6",
    lvl1="#27272A",
    lvl2="#3F3F46",
    lvl3="#52525B",
    glass="rgba(9, 9, 11, 0.85)",
    font_family="'Inter', 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif",
    radius=12,
    shadow="0 10px 15px -3px rgba(0, 0, 0, 0.5)",
    highlight="#60A5FA",   # Blue 400
    primary_dark="#000000",
    blue_hover="#60A5FA",
    highlight_bg="#27272A",
)


# Theme State
_CURRENT_THEME = BUR


def set_theme_mode(mode: str):
    global _CURRENT_THEME, BUR
    if mode == "dark":
        _CURRENT_THEME = BUR_DARK
    else:
        _CURRENT_THEME = BUR
    # Update legacy constant just in case
    BUR = _CURRENT_THEME


def get_theme() -> BurTheme:
    return _CURRENT_THEME

# Common Styles
BTN_PRIMARY = f"background-color: {BUR.blue}; color: white; border-radius: {BUR.radius}px; padding: 6px 12px; font-weight: 600; border: none;"
BTN_SECONDARY = f"background-color: {BUR.surface}; color: {BUR.text}; border: 1px solid {BUR.border}; border-radius: {BUR.radius}px; padding: 6px 12px; font-weight: 600;"
BTN_DANGER = f"background-color: {BUR.danger}; color: white; border-radius: {BUR.radius}px; padding: 6px 12px; font-weight: 600; border: none;"

GROUP_BOX = f"QGroupBox {{ font-weight: bold; border: 1px solid {BUR.border}; border-radius: {BUR.radius}px; margin-top: 6px; padding-top: 10px; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }}"

def get_global_stylesheet():
    return f"""
        QMainWindow {{
            background-color: {BUR.bg};
        }}
        QWidget {{
            font-family: 'Segoe UI', 'Inter', sans-serif;
            color: {BUR.text};
        }}
        QLabel {{
            font-size: 13px;
            font-weight: 500;
        }}
        QGroupBox {{
            background-color: {BUR.surface};
            border: 1px solid {BUR.border};
            border-radius: 12px;
            margin-top: 20px;
            font-size: 14px;
            font-weight: bold;
            color: {BUR.text};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 15px;
            top: 0px;
            padding: 0 5px;
            background-color: {BUR.surface};
            color: {BUR.blue};
        }}
        QLineEdit, QComboBox, QDoubleSpinBox {{
            padding: 8px 12px;
            border: 1px solid {BUR.border};
            border-radius: 6px;
            background-color: {BUR.bg};
            font-size: 13px;
            selection-background-color: {BUR.blue};
        }}
        QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {BUR.blue};
            background-color: {BUR.surface};
        }}
        QPushButton {{
            background-color: {BUR.bg_alt};
            color: {BUR.muted};
            border: 1px solid {BUR.border};
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {BUR.border};
        }}
        #primaryButton {{
            background-color: {BUR.blue};
            color: white;
            border: none;
            font-size: 15px;
            padding: 12px;
            border-radius: 8px;
        }}
        #primaryButton:hover {{
            background-color: {BUR.primary_dark};
        }}
        #secondaryButton {{
            background-color: {BUR.surface};
            color: {BUR.blue};
            border: 1px solid {BUR.blue};
            font-size: 13px;
            padding: 8px 14px;
            border-radius: 6px;
            font-weight: 600;
        }}
        #secondaryButton:hover {{
            background-color: {BUR.info_alt};
        }}
        QTextEdit {{
            background-color: {BUR.surface};
            color: {BUR.text};
            border: 1px solid {BUR.border};
            border-radius: 12px;
            padding: 15px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 14px;
        }}
        QTabWidget::pane {{ border: 0; }}
        QTabBar::tab {{
            background: {BUR.bg_alt};
            color: {BUR.muted};
            padding: 12px 24px;
            margin-right: 4px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-weight: bold;
            font-size: 14px;
        }}
        QTabBar::tab:selected {{
            background: {BUR.surface};
            color: {BUR.blue};
            border-bottom: 2px solid {BUR.blue};
        }}
        QTabBar::tab:hover:!selected {{
            background: {BUR.border};
            color: {BUR.muted};
        }}
    """

