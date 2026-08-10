import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QToolButton

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


THEMES = {
    "dark": {
        "window_bg": "#0b1217",
        "window_mid": "#0f171d",
        "window_end": "#091015",
        "shell": "#121a21",
        "panel": "#151f27",
        "panel_alt": "#18232c",
        "panel_soft": "#1b2731",
        "border": "#26333e",
        "border_soft": "#22303a",
        "divider": "rgba(40, 53, 65, 0.95)",
        "text": "#edf3f7",
        "muted": "#96a4b4",
        "muted_soft": "#768495",
        "accent": "#6b9c49",
        "accent_strong": "#7db55a",
        "accent_deep": "#4f7f33",
        "accent_glow": "#9bd46f",
        "row_selected": "#203126",
        "shadow": "#000000",
        "shell_rgba": "rgba(18, 26, 33, 0.92)",
        "shell_border_rgba": "rgba(55, 71, 84, 0.85)",
        "topbar_rgba": "rgba(24, 35, 44, 0.94)",
        "topbar_border_rgba": "rgba(49, 65, 78, 0.95)",
        "panel_rgba": "rgba(22, 31, 39, 0.96)",
        "panel_border_rgba": "rgba(43, 58, 70, 0.92)",
        "secondary_button_bg": "rgba(24, 35, 44, 0.96)",
        "secondary_button_hover": "rgba(29, 42, 52, 1.0)",
        "metric_icon_bg": "rgba(107, 156, 73, 0.12)",
        "table_row_border": "rgba(37, 50, 61, 0.9)",
        "backdrop_glow_primary": "#6b9c49",
        "backdrop_glow_secondary": "#6b9c49",
        "backdrop_glow_primary_alpha": 68,
        "backdrop_glow_secondary_alpha": 22,
        "backdrop_line": "#a0b0bd",
        "backdrop_line_alpha": 18,
        "backdrop_arc": "#abd47a",
        "backdrop_arc_alpha": 20,
        "backdrop_path": "#ffffff",
        "backdrop_path_alpha": 10,
        "brand_cutout": "#121a21",
        "brand_leaf": "#f4fbef",
    },
    "light": {
        "window_bg": "#f1f2f4",
        "window_mid": "#ebecef",
        "window_end": "#dfe4e8",
        "shell": "#f5f6f8",
        "panel": "#f8f8fa",
        "panel_alt": "#ffffff",
        "panel_soft": "#eef1f4",
        "border": "#d7dce2",
        "border_soft": "#e3e7eb",
        "divider": "rgba(217, 221, 226, 0.95)",
        "text": "#2f3442",
        "muted": "#7b8492",
        "muted_soft": "#a4acb6",
        "accent": "#628d4b",
        "accent_strong": "#7aa65e",
        "accent_deep": "#4f7b3f",
        "accent_glow": "#628d4b",
        "row_selected": "#edf4e8",
        "shadow": "#000000",
        "shell_rgba": "rgba(245, 246, 248, 0.96)",
        "shell_border_rgba": "rgba(214, 218, 223, 0.95)",
        "topbar_rgba": "rgba(249, 249, 251, 0.96)",
        "topbar_border_rgba": "rgba(224, 227, 231, 0.95)",
        "panel_rgba": "rgba(248, 248, 250, 0.97)",
        "panel_border_rgba": "rgba(221, 225, 230, 0.94)",
        "secondary_button_bg": "rgba(245, 246, 248, 0.98)",
        "secondary_button_hover": "rgba(237, 240, 244, 1.0)",
        "metric_icon_bg": "rgba(98, 141, 75, 0.10)",
        "table_row_border": "rgba(226, 229, 233, 0.95)",
        "backdrop_glow_primary": "#7aa65e",
        "backdrop_glow_secondary": "#b8c2cb",
        "backdrop_glow_primary_alpha": 44,
        "backdrop_glow_secondary_alpha": 30,
        "backdrop_line": "#c7ced6",
        "backdrop_line_alpha": 42,
        "backdrop_arc": "#b9c3cb",
        "backdrop_arc_alpha": 58,
        "backdrop_path": "#ffffff",
        "backdrop_path_alpha": 86,
        "brand_cutout": "#f5f6f8",
        "brand_leaf": "#f8fbf5",
    },
}

CURRENT_THEME = "dark"
COLORS = dict(THEMES[CURRENT_THEME])


def _resolve_theme_name(theme_name=None):
    if theme_name in THEMES:
        return theme_name
    return CURRENT_THEME


def current_theme_name():
    return CURRENT_THEME


def set_theme(theme_name):
    global CURRENT_THEME
    resolved = _resolve_theme_name(theme_name)
    CURRENT_THEME = resolved
    COLORS.clear()
    COLORS.update(THEMES[resolved])
    return resolved


def detect_system_theme():
    if sys.platform == "win32" and winreg is not None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "light" if value else "dark"
        except OSError:
            pass
    return CURRENT_THEME


def build_palette(theme_name=None):
    c = THEMES[_resolve_theme_name(theme_name)]
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(c["window_bg"]))
    palette.setColor(QPalette.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.Base, QColor(c["panel"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["panel_alt"]))
    palette.setColor(QPalette.Text, QColor(c["text"]))
    palette.setColor(QPalette.Button, QColor(c["panel_alt"]))
    palette.setColor(QPalette.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.Highlight, QColor(c["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor(c["panel_alt"]))
    palette.setColor(QPalette.ToolTipText, QColor(c["text"]))
    return palette


def build_calendar_stylesheet(theme_name=None):
    c = THEMES[_resolve_theme_name(theme_name)]
    return f"""
    QCalendarWidget, QCalendarWidget QWidget {{
        background: {c["panel_alt"]};
        color: {c["text"]};
    }}

    QWidget#qt_calendar_navigationbar {{
        background: {c["panel_soft"]};
        border-bottom: 1px solid {c["border_soft"]};
    }}

    QCalendarWidget QToolButton {{
        min-height: 30px;
        color: {c["text"]};
        background: transparent;
        border: none;
        padding: 0 10px;
        font-size: 10pt;
        font-weight: 600;
    }}

    QCalendarWidget QToolButton#qt_calendar_prevmonth,
    QCalendarWidget QToolButton#qt_calendar_nextmonth {{
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        padding: 0;
        font-size: 14pt;
        font-weight: 700;
        color: {c["accent_glow"]};
        border-radius: 10px;
        text-align: center;
        outline: none;
    }}

    QCalendarWidget QToolButton:hover {{
        background: {c["secondary_button_hover"]};
        border-radius: 10px;
    }}

    QCalendarWidget QMenu {{
        background: {c["panel_alt"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
    }}

    QCalendarWidget QMenu::item:selected {{
        background: {c["row_selected"]};
    }}

    QCalendarWidget QSpinBox {{
        min-height: 28px;
        color: {c["text"]};
        background: {c["panel_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 0 8px;
        selection-background-color: {c["accent_deep"]};
        selection-color: #ffffff;
    }}

    QCalendarWidget QSpinBox::up-button,
    QCalendarWidget QSpinBox::down-button {{
        width: 16px;
        border: none;
        background: transparent;
    }}

    QCalendarWidget QAbstractItemView:enabled {{
        background: {c["panel_alt"]};
        color: {c["text"]};
        selection-background-color: {c["accent"]};
        selection-color: #ffffff;
        outline: 0;
    }}

    QCalendarWidget QAbstractItemView:disabled {{
        color: {c["muted_soft"]};
    }}
    """


def style_calendar_widget(widget, theme_name=None):
    widget.setStyleSheet(build_calendar_stylesheet(theme_name))
    for object_name, arrow_text in (("qt_calendar_prevmonth", "<"), ("qt_calendar_nextmonth", ">")):
        button = widget.findChild(QToolButton, object_name)
        if button is None:
            continue
        button.setIcon(QIcon())
        button.setText(arrow_text)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.NoFocus)


def apply_app_theme(app, theme_name=None):
    resolved = set_theme(theme_name or detect_system_theme())
    app.setStyle("Fusion")
    app.setPalette(build_palette(resolved))
    app.setStyleSheet(build_stylesheet(resolved))
    app.setProperty("atl_theme", resolved)
    return resolved


def apply_dark_palette(app):
    return apply_app_theme(app, "dark")


def build_stylesheet(theme_name=None):
    c = THEMES[_resolve_theme_name(theme_name)]
    return f"""
    QWidget {{
        color: {c["text"]};
        font-family: "Segoe UI";
        font-size: 10pt;
    }}

    QWidget#WindowRoot {{
        background: transparent;
    }}

    QFrame#Shell {{
        background: transparent;
        border: none;
        border-radius: 0px;
    }}

    QFrame#TopBar {{
        background: {c["topbar_rgba"]};
        border: 1px solid {c["topbar_border_rgba"]};
        border-radius: 24px;
    }}

    QFrame#Panel, QFrame#MetricsBar {{
        background: {c["panel_rgba"]};
        border: 1px solid {c["panel_border_rgba"]};
        border-radius: 22px;
    }}

    QFrame#SidebarShell {{
        background: {c["panel_rgba"]};
        border: 1px solid {c["panel_border_rgba"]};
        border-top-left-radius: 0px;
        border-bottom-left-radius: 0px;
        border-top-right-radius: 22px;
        border-bottom-right-radius: 22px;
    }}

    QLabel#BrandTitle {{
        font-size: 18pt;
        font-weight: 700;
        letter-spacing: 0.2px;
    }}

    QLabel#PanelTitle {{
        font-size: 13pt;
        font-weight: 700;
        color: {c["text"]};
    }}

    QLabel#SidebarTitle {{
        font-size: 11pt;
        font-weight: 700;
        color: {c["text"]};
    }}

    QLabel#SidebarCaption {{
        font-size: 9pt;
        font-weight: 600;
        color: {c["muted"]};
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }}

    QLabel#PanelMinor {{
        font-size: 10pt;
        font-weight: 600;
        color: {c["muted"]};
        text-transform: uppercase;
    }}

    QLabel#MetaValue {{
        font-size: 13pt;
        font-weight: 700;
        color: {c["text"]};
    }}

    QLabel#MetaValueAccent {{
        font-size: 13pt;
        font-weight: 700;
        color: {c["accent_glow"]};
    }}

    QLabel#MetaLabel {{
        font-size: 10pt;
        color: {c["muted"]};
    }}

    QLabel#UserAvatar {{
        min-width: 34px;
        max-width: 34px;
        min-height: 34px;
        max-height: 34px;
        border-radius: 17px;
        background: {c["panel_soft"]};
        border: 1px solid {c["border"]};
        font-weight: 700;
        qproperty-alignment: AlignCenter;
    }}

    QLabel#UserName {{
        font-size: 10pt;
        font-weight: 600;
    }}

    QLabel#UserBadge {{
        min-width: 24px;
        max-width: 24px;
        min-height: 24px;
        max-height: 24px;
        border-radius: 12px;
        background: {c["accent"]};
        color: #ffffff;
        font-size: 9pt;
        font-weight: 700;
        qproperty-alignment: AlignCenter;
    }}

    QPushButton#NavButton {{
        color: {c["muted"]};
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 14px 6px 12px 6px;
        font-size: 10pt;
        font-weight: 600;
    }}

    QPushButton#NavButton:hover {{
        color: {c["text"]};
    }}

    QPushButton#NavButton:checked {{
        color: {c["accent_glow"]};
        border-bottom: 2px solid {c["accent_glow"]};
    }}

    QPushButton#PrimaryButton {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c["accent"]}, stop:1 {c["accent_deep"]});
        border: 1px solid {c["accent_strong"]};
        border-radius: 14px;
        min-height: 24px;
        padding: 0 18px;
        font-size: 10pt;
        font-weight: 700;
        color: #ffffff;
    }}

    QPushButton#PrimaryButton:hover {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c["accent_strong"]}, stop:1 {c["accent"]});
    }}

    QPushButton#PrimaryButton:pressed {{
        background-color: {c["accent_deep"]};
    }}

    QPushButton#SecondaryButton {{
        background-color: {c["secondary_button_bg"]};
        border: 1px solid {c["border"]};
        border-radius: 14px;
        min-height: 24px;
        padding: 0 18px;
        font-size: 10pt;
        font-weight: 600;
        color: {c["text"]};
    }}

    QPushButton#SecondaryButton:hover {{
        background-color: {c["secondary_button_hover"]};
    }}

    QPushButton#SidebarToggle {{
        background-color: {c["secondary_button_bg"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        color: {c["text"]};
        font-size: 11pt;
        font-weight: 700;
    }}

    QPushButton#SidebarToggle:hover {{
        background-color: {c["secondary_button_hover"]};
    }}

    QPushButton#SidebarButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 14px;
        min-height: 40px;
        padding: 0 12px;
        color: {c["muted"]};
        font-size: 10pt;
        font-weight: 600;
        text-align: left;
    }}

    QPushButton#SidebarButton:hover {{
        background: {c["secondary_button_hover"]};
        border: 1px solid {c["border_soft"]};
        color: {c["text"]};
    }}

    QPushButton#SidebarButton:checked {{
        background: {c["row_selected"]};
        border: 1px solid {c["accent"]};
        color: {c["accent_glow"]};
    }}

    QPushButton#SidebarButton[compact="true"] {{
        padding: 0;
        text-align: center;
        font-size: 8.5pt;
        font-weight: 700;
    }}

    QDateEdit#DateField {{
        min-height: 44px;
        background: {c["panel_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        padding: 0 14px;
        font-size: 10pt;
        font-weight: 600;
    }}

    QDateEdit#DateField::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: right;
        width: 20px;
        border-left: 1px solid {c["border_soft"]};
    }}

    QDateEdit#DateField::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
    }}

    QCalendarWidget {{
        background: {c["panel_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 14px;
    }}

    QCalendarWidget QWidget {{
        background: {c["panel_alt"]};
        color: {c["text"]};
    }}

    QCalendarWidget QWidget#qt_calendar_navigationbar {{
        background: {c["panel_soft"]};
        border-bottom: 1px solid {c["border_soft"]};
        border-top-left-radius: 14px;
        border-top-right-radius: 14px;
    }}

    QCalendarWidget QToolButton {{
        min-height: 30px;
        color: {c["text"]};
        background: transparent;
        border: none;
        padding: 0 10px;
        font-size: 10pt;
        font-weight: 600;
    }}

    QCalendarWidget QToolButton:hover {{
        background: {c["secondary_button_hover"]};
        border-radius: 10px;
    }}

    QCalendarWidget QMenu {{
        background: {c["panel_alt"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
    }}

    QCalendarWidget QMenu::item:selected {{
        background: {c["row_selected"]};
    }}

    QCalendarWidget QSpinBox {{
        min-height: 28px;
        color: {c["text"]};
        background: {c["panel_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 0 8px;
        selection-background-color: {c["accent_deep"]};
        selection-color: #ffffff;
    }}

    QCalendarWidget QSpinBox::up-button,
    QCalendarWidget QSpinBox::down-button {{
        width: 16px;
        border: none;
        background: transparent;
    }}

    QCalendarWidget QAbstractItemView:enabled {{
        background: {c["panel_alt"]};
        color: {c["text"]};
        selection-background-color: {c["accent"]};
        selection-color: #ffffff;
        outline: 0;
    }}

    QCalendarWidget QAbstractItemView:disabled {{
        color: {c["muted_soft"]};
    }}

    QRadioButton {{
        spacing: 8px;
        font-size: 10pt;
        color: {c["text"]};
    }}

    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 1px solid {c["muted_soft"]};
        background: {c["panel_alt"]};
    }}

    QRadioButton::indicator:checked {{
        background: {c["accent"]};
        border: 1px solid {c["accent_glow"]};
    }}

    QCheckBox {{
        spacing: 8px;
        font-size: 10pt;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {c["muted_soft"]};
        background: {c["panel_alt"]};
    }}

    QCheckBox::indicator:checked {{
        background: {c["accent"]};
        border: 1px solid {c["accent_glow"]};
    }}

    QLineEdit#TextField {{
        background: {c["panel_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        padding: 0 12px;
        color: {c["text"]};
        selection-background-color: {c["accent_deep"]};
        selection-color: #ffffff;
    }}

    QComboBox#TextField {{
        background: {c["panel_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        padding: 0 34px 0 12px;
        color: {c["text"]};
        min-height: 44px;
    }}

    QComboBox#TextField::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border-left: 1px solid {c["border_soft"]};
        background: transparent;
        border-top-right-radius: 12px;
        border-bottom-right-radius: 12px;
    }}

    QComboBox#TextField::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
    }}

    QComboBox#TextField QAbstractItemView {{
        background: {c["panel_alt"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        padding: 6px;
        selection-background-color: {c["row_selected"]};
        selection-color: {c["text"]};
        outline: 0;
    }}

    QTextEdit#TextField, QPlainTextEdit#TextField {{
        background: {c["panel_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        padding: 10px 12px;
        color: {c["text"]};
        selection-background-color: {c["accent_deep"]};
        selection-color: #ffffff;
    }}

    QLineEdit#TextField:focus, QComboBox#TextField:focus, QTextEdit#TextField:focus, QPlainTextEdit#TextField:focus {{
        border: 1px solid {c["accent"]};
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QLabel#FieldLabel {{
        font-size: 10pt;
        font-weight: 600;
        color: {c["muted"]};
    }}

    QTableWidget#ContractsTable,
    QTableWidget#AgendamentosTable,
    QTableWidget#FretesTable {{
        background: {c["panel_alt"]};
        border: none;
        color: {c["text"]};
        gridline-color: {c["border_soft"]};
        selection-background-color: {c["row_selected"]};
        selection-color: {c["text"]};
        outline: none;
    }}

    QHeaderView::section {{
        background: {c["panel_alt"]};
        color: {c["muted"]};
        border: none;
        border-bottom: 1px solid {c["border_soft"]};
        padding: 12px 10px;
        font-size: 9pt;
        font-weight: 700;
        text-align: left;
    }}

    QTableWidget::item {{
        color: {c["text"]};
        background: {c["panel_alt"]};
        border-bottom: 1px solid {c["table_row_border"]};
        padding: 14px 10px;
        font-weight: 600;
    }}

    QTableWidget::item:selected {{
        background: {c["row_selected"]};
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 6px 0;
    }}

    QScrollBar::handle:vertical {{
        background: {c["border"]};
        border-radius: 5px;
        min-height: 28px;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QFrame#MetricItem {{
        background: transparent;
        border: none;
    }}

    QLabel#MetricIcon {{
        min-width: 34px;
        max-width: 34px;
        min-height: 34px;
        max-height: 34px;
        border-radius: 10px;
        background: {c["metric_icon_bg"]};
        color: {c["accent_glow"]};
        font-size: 12pt;
        font-weight: 700;
        qproperty-alignment: AlignCenter;
    }}

    QLabel#MetricValue {{
        font-size: 14pt;
        font-weight: 700;
    }}

    QLabel#MetricValuePrimary {{
        font-size: 14pt;
        font-weight: 700;
        color: {c["accent_glow"]};
    }}

    QLabel#MetricLabel {{
        font-size: 10pt;
        color: {c["muted"]};
    }}

    QFrame#ActionPrimary, QFrame#ActionSecondary {{
        border-radius: 16px;
        border: 1px solid {c["border"]};
    }}

    QFrame#ActionPrimary {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent"]},
            stop:1 {c["accent_deep"]});
        border: 1px solid {c["accent_strong"]};
    }}

    QFrame#ActionSecondary {{
        background: {c["secondary_button_bg"]};
    }}

    QFrame#ActionPrimary[hovered="true"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent_strong"]},
            stop:1 {c["accent"]});
    }}

    QFrame#ActionSecondary[hovered="true"] {{
        background: {c["secondary_button_hover"]};
    }}

    QLabel#ActionIconPrimary {{
        color: #ffffff;
        font-size: 21pt;
        font-weight: 700;
    }}

    QLabel#ActionIconSecondary {{
        color: {c["accent_glow"]};
        font-size: 16pt;
        font-weight: 700;
    }}

    QLabel#ActionTitle {{
        font-size: 11pt;
        font-weight: 600;
    }}

    QLabel#ActionChevron {{
        font-size: 18pt;
        color: {c["muted"]};
        font-weight: 400;
    }}

    QFrame#Divider {{
        background: {c["divider"]};
        min-width: 1px;
        max-width: 1px;
    }}

    QLabel#Dots {{
        font-size: 15pt;
        color: {c["muted_soft"]};
        font-weight: 700;
    }}
    """
