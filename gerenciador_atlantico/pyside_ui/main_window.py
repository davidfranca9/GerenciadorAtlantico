from __future__ import annotations

import sys
import uuid

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .analise_fretes_page import AnaliseFretesPage
from .agendamentos_page import AgendamentosPage
from .bsoft_page import BsoftPage
from .clientes_page import ClientesPage
from .contrato_window import ContratoPage
from .form_pages import CartaFretePage, OrdemColetaPage
from .theme import apply_app_theme, current_theme_name, detect_system_theme
from .widgets import BackgroundWidget, BrandLogo, UserChip, apply_shadow


ADMIN_MAC_ADDRESS = "08:97:98:64:AF:8E"

NAV_SECTIONS = [
    (
        "Logistica",
        [
            ("CONTRATO", "CONTRATO", "CT"),
            ("ORDEM DE COLETA", "ORDEM DE COLETA", "OC"),
            ("AGENDAMENTOS", "AGENDAMENTOS", "AG"),
            ("PEDIDOS GRANDES", "PEDIDOS GRANDES", "PG"),
            ("ANALISE DE FRETES", "ANALISE DE FRETES", "AF"),
        ],
    ),
    (
        "Financeiro",
        [
            ("CARTA FRETE", "CARTA FRETE", "CF"),
        ],
    ),
    (
        "Cadastro",
        [
            ("BUONNY", "BUONNY", "BU"),
            ("BSOFT TMS", "BSOFT TMS", "BS"),
        ],
    ),
    (
        "Clientes",
        [
            ("CLIENTES", "CLIENTES", "CL"),
        ],
    ),
]


def is_admin_machine():
    mac = ":".join(f"{uuid.getnode():012x}"[i:i + 2] for i in range(0, 12, 2)).upper()
    return mac == ADMIN_MAC_ADDRESS


class PlaceholderPage(QWidget):
    def __init__(self, title, description, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 6)
        layout.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("Panel")
        apply_shadow(hero, blur=32, y_offset=10, alpha=56)

        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 28, 28, 28)
        hero_layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("PanelTitle")

        desc_label = QLabel(description)
        desc_label.setObjectName("MetaLabel")
        desc_label.setWordWrap(True)

        state = QLabel("Base pronta para migracao")
        state.setObjectName("MetaValueAccent")

        note = QLabel("Essa area ja esta dentro da shell PySide e pode receber a logica antiga sem depender de tkinter.")
        note.setObjectName("MetaLabel")
        note.setWordWrap(True)

        hero_layout.addWidget(title_label)
        hero_layout.addWidget(desc_label)
        hero_layout.addSpacing(10)
        hero_layout.addWidget(state)
        hero_layout.addWidget(note)

        layout.addWidget(hero)
        layout.addStretch(1)


class AtlanticoMainWindow(QMainWindow):
    _SIDEBAR_EXPANDED_WIDTH = 220
    _SIDEBAR_COLLAPSED_WIDTH = 72

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Atlantico Fertlog")
        self.resize(1536, 1024)
        self.setMinimumSize(1280, 860)

        self.pages = {}
        self.nav_buttons = {}
        self._nav_button_labels = {}
        self._sidebar_section_labels = []
        self._sidebar_expanded = True
        self._sidebar_animation = None

        root = BackgroundWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("Shell")
        root_layout.addWidget(shell)

        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        shell_layout.addWidget(self.sidebar, 0)

        content_column = QWidget()
        content_layout = QVBoxLayout(content_column)
        content_layout.setContentsMargins(12, 10, 10, 10)
        content_layout.setSpacing(8)

        content_layout.addWidget(self._build_top_bar())

        self.stack = QStackedWidget()
        self.stack.setObjectName("PageStack")
        self.stack.setStyleSheet("QStackedWidget#PageStack { background: transparent; }")
        content_layout.addWidget(self.stack, 1)
        shell_layout.addWidget(content_column, 1)

        self._build_pages()
        self._refresh_page_themes()
        self._apply_sidebar_state()
        self.show_page("CONTRATO")

        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(2500)
        self._theme_timer.timeout.connect(self._sync_theme_with_windows)
        self._theme_timer.start()

    def _build_top_bar(self):
        frame = QFrame()
        frame.setObjectName("TopBar")
        frame.setMinimumHeight(68)
        apply_shadow(frame, blur=32, y_offset=10, alpha=56)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 10, 16, 10)
        layout.setSpacing(14)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_row.addWidget(BrandLogo())

        brand_title = QLabel("ATLANTICO FERTLOG")
        brand_title.setObjectName("BrandTitle")
        brand_row.addWidget(brand_title)

        brand_widget = QWidget()
        brand_widget.setLayout(brand_row)
        layout.addWidget(brand_widget, 0, Qt.AlignVCenter)

        self.page_indicator = QLabel("CONTRATO")
        self.page_indicator.setObjectName("PanelMinor")
        layout.addWidget(self.page_indicator, 0, Qt.AlignVCenter)

        layout.addStretch(1)
        layout.addWidget(UserChip(), 0, Qt.AlignRight | Qt.AlignVCenter)
        return frame

    def _build_sidebar(self):
        frame = QFrame()
        frame.setObjectName("SidebarShell")
        frame.setMinimumWidth(self._SIDEBAR_EXPANDED_WIDTH)
        frame.setMaximumWidth(self._SIDEBAR_EXPANDED_WIDTH)
        frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        apply_shadow(frame, blur=28, y_offset=9, alpha=48)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.sidebar_title = QLabel("Setores")
        self.sidebar_title.setObjectName("SidebarTitle")
        top_row.addWidget(self.sidebar_title, 1)

        self.toggle_button = QPushButton("<")
        self.toggle_button.setObjectName("SidebarToggle")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.setFixedSize(36, 36)
        self.toggle_button.clicked.connect(self.toggle_sidebar)
        top_row.addWidget(self.toggle_button, 0, Qt.AlignRight)
        layout.addLayout(top_row)

        self.sidebar_caption = QLabel("Navegacao principal")
        self.sidebar_caption.setObjectName("SidebarCaption")
        layout.addWidget(self.sidebar_caption)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        sections = list(NAV_SECTIONS)
        if is_admin_machine():
            sections.append(("Sistema", [("ADMIN", "ADMIN", "AD")]))

        for section_title, pages in sections:
            section_label = QLabel(section_title.upper())
            section_label.setObjectName("SidebarCaption")
            layout.addWidget(section_label)
            self._sidebar_section_labels.append(section_label)

            for button_label, page_key, compact_label in pages:
                button = QPushButton(button_label)
                button.setObjectName("SidebarButton")
                button.setCheckable(True)
                button.setCursor(Qt.PointingHandCursor)
                button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                button.setToolTip(button_label)
                button.clicked.connect(lambda checked=False, key=page_key: self.show_page(key))
                self.nav_group.addButton(button)
                self.nav_buttons[page_key] = button
                self._nav_button_labels[page_key] = (button_label, compact_label)
                layout.addWidget(button)

        layout.addStretch(1)
        return frame

    def _build_pages(self):
        self._add_page("BUONNY", PlaceholderPage("Buonny", "Consulta rapida e cadastro da Buonny serao migrados para componentes Qt."))
        self.contrato_page = ContratoPage()
        self.clients_page = ClientesPage()
        self.ordem_coleta_page = OrdemColetaPage(self.contrato_page, self.clients_page)
        self.agendamentos_page = AgendamentosPage()
        self.ordem_coleta_page.agendamento_registrado.connect(self.agendamentos_page.reload_data)
        self._add_page("CONTRATO", self.contrato_page)
        self._add_page("ORDEM DE COLETA", self.ordem_coleta_page)
        self._add_page("CARTA FRETE", CartaFretePage())
        self._add_page("CLIENTES", self.clients_page)
        self._add_page("AGENDAMENTOS", self.agendamentos_page)
        self._add_page("PEDIDOS GRANDES", PlaceholderPage("Pedidos Grandes", "A listagem e o controle de saldo vao virar uma pagina nativa PySide."))
        self._add_page("BSOFT TMS", BsoftPage())
        self._add_page("ANALISE DE FRETES", AnaliseFretesPage())
        if is_admin_machine():
            self._add_page("ADMIN", PlaceholderPage("Admin", "O controle remoto de bloqueio e senha sera portado para dialogos e overlays PySide."))

    def _add_page(self, key, widget):
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def _refresh_page_themes(self):
        for widget in self.pages.values():
            refresh = getattr(widget, "refresh_theme", None)
            if callable(refresh):
                refresh()

    def toggle_sidebar(self):
        start_width = self.sidebar.maximumWidth()
        end_width = (
            self._SIDEBAR_COLLAPSED_WIDTH
            if self._sidebar_expanded
            else self._SIDEBAR_EXPANDED_WIDTH
        )

        group = QParallelAnimationGroup(self)
        for property_name in (b"minimumWidth", b"maximumWidth"):
            animation = QPropertyAnimation(self.sidebar, property_name, group)
            animation.setDuration(180)
            animation.setStartValue(start_width)
            animation.setEndValue(end_width)
            animation.setEasingCurve(QEasingCurve.InOutCubic)
            group.addAnimation(animation)

        self._sidebar_expanded = not self._sidebar_expanded
        self._apply_sidebar_state()
        self._sidebar_animation = group
        group.start()

    def _apply_sidebar_state(self):
        self.sidebar_title.setVisible(self._sidebar_expanded)
        self.sidebar_caption.setVisible(self._sidebar_expanded)
        self.toggle_button.setText("<" if self._sidebar_expanded else ">")

        for label in self._sidebar_section_labels:
            label.setVisible(self._sidebar_expanded)

        for page_key, button in self.nav_buttons.items():
            expanded_label, compact_label = self._nav_button_labels[page_key]
            button.setText(expanded_label if self._sidebar_expanded else compact_label)
            button.setProperty("compact", not self._sidebar_expanded)
            button.style().unpolish(button)
            button.style().polish(button)

    def show_page(self, key):
        widget = self.pages.get(key)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        if key in self.nav_buttons:
            self.nav_buttons[key].setChecked(True)
            self.page_indicator.setText(self._nav_button_labels[key][0])

    def _sync_theme_with_windows(self):
        desired_theme = detect_system_theme()
        if desired_theme == current_theme_name():
            return
        app = QApplication.instance()
        if app is None:
            return
        apply_app_theme(app, desired_theme)
        self._refresh_page_themes()
        self.centralWidget().update()
        self.update()


def run_app():
    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    window = AtlanticoMainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
