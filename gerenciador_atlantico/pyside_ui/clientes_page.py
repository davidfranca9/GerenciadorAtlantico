from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QPushButton,
)

from .widgets import apply_shadow


class ClientesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 6)
        layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("Panel")
        apply_shadow(hero, blur=28, y_offset=9, alpha=52)

        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(10)

        title = QLabel("Clientes")
        title.setObjectName("PanelTitle")
        hero_layout.addWidget(title)

        subtitle = QLabel("Centralize roteiro, localizador interno e contato do cliente aqui sem poluir a Ordem de Coleta.")
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)

        helper = QLabel("O localizador fica so no banco interno. Roteiro e contato continuam disponiveis no fluxo do agendamento.")
        helper.setObjectName("MetaValueAccent")
        helper.setWordWrap(True)
        hero_layout.addWidget(helper)
        layout.addWidget(hero)

        form_panel = QFrame()
        form_panel.setObjectName("Panel")
        apply_shadow(form_panel, blur=28, y_offset=9, alpha=52)

        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(24, 20, 24, 20)
        form_layout.setSpacing(14)

        form_title = QLabel("Roteiro e Atendimento")
        form_title.setObjectName("PanelTitle")
        form_layout.addWidget(form_title)

        form_copy = QLabel("Preencha o roteiro, o localizador interno e o contato do cliente para acompanhamento interno.")
        form_copy.setObjectName("MetaLabel")
        form_copy.setWordWrap(True)
        form_layout.addWidget(form_copy)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)

        roteiro_box, self.route_field = self._field(
            "Roteiro",
            multiline=True,
            placeholder="Ex.: Salvador -> Candeias -> Camacari",
        )
        localizador_box, self.locator_field = self._field(
            "Localizador",
            placeholder="Ex.: LOC-12345",
        )
        contato_box, self.client_contact_field = self._field(
            "Contato do Cliente",
            placeholder="Nome / telefone / e-mail",
        )

        grid.addWidget(roteiro_box, 0, 0, 2, 1)
        grid.addWidget(localizador_box, 0, 1)
        grid.addWidget(contato_box, 1, 1)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        form_layout.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addStretch(1)

        clear_button = QPushButton("Limpar Dados")
        clear_button.setObjectName("SecondaryButton")
        clear_button.setCursor(Qt.PointingHandCursor)
        clear_button.clicked.connect(self.clear_route_details)
        actions.addWidget(clear_button)
        form_layout.addLayout(actions)

        layout.addWidget(form_panel)
        layout.addStretch(1)

    def _field(self, label, multiline=False, placeholder=""):
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel(label)
        title.setObjectName("FieldLabel")
        layout.addWidget(title)

        if multiline:
            widget = QTextEdit()
            widget.setFixedHeight(112)
            wrapper.setMinimumHeight(140)
        else:
            widget = QLineEdit()
            widget.setFixedHeight(46)
            wrapper.setMinimumHeight(70)

        widget.setObjectName("TextField")
        widget.setPlaceholderText(placeholder)
        layout.addWidget(widget)
        return wrapper, widget

    def clear_route_details(self):
        self.route_field.clear()
        self.locator_field.clear()
        self.client_contact_field.clear()

    def get_route_details(self):
        return {
            "roteiro": self.route_field.toPlainText().strip(),
            "localizador": self.locator_field.text().strip(),
            "contato_cliente": self.client_contact_field.text().strip(),
        }

    def refresh_theme(self):
        return None
