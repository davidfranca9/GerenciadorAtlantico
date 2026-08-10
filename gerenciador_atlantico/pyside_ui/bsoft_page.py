from __future__ import annotations

import os
import re
import threading
import time
import traceback
from datetime import datetime

import pdfplumber
import requests
from docx import Document
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QParallelAnimationGroup, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..servicos.bsoft_api import (
    atualizar_pessoa_fisica_bsoft,
    atualizar_pessoa_juridica_bsoft,
    cadastrar_endereco_bsoft,
    cadastrar_pessoa_fisica_bsoft,
    cadastrar_pessoa_juridica_bsoft,
    cadastrar_veiculo_bsoft,
)
from ..servicos.ocr import (
    carregar_cidades_nova_logica,
    extrair_dados_cnh_com_azure_api,
    extrair_dados_crlv_com_azure_api,
    extrair_dados_rntrc_com_azure_api,
    normalizar_texto_sem_acento,
    obter_texto_do_arquivo_com_azure,
)
from ..shared import (
    BSOFT_API_PASSWORD,
    BSOFT_API_USER,
    BSOFT_CATEGORIAS_VEICULO,
    BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP,
    BSOFT_CATEGORY_TO_EQUIPMENT_MAP,
    BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP,
    BSOFT_MARCA_ID_LOOKUP,
    BSOFT_TIPOS_CARROCERIA_NOMES,
    BSOFT_TIPOS_EQUIPAMENTO,
    BSOFT_TIPOS_RODADO_NOMES,
    PLANILHA_CIDADES,
    get_key_from_value,
)
from .widgets import apply_shadow


_CITY_CACHE = None


def _load_cities():
    global _CITY_CACHE
    if _CITY_CACHE is None:
        _CITY_CACHE = carregar_cidades_nova_logica(PLANILHA_CIDADES) or {}
    return _CITY_CACHE


class BsoftPage(QWidget):
    progress_changed = Signal(str)
    error_requested = Signal(str, str)
    info_requested = Signal(str, str)
    documents_ready = Signal(object, object)
    cep_ready = Signal(object)
    cnpj_ready = Signal(object)
    registration_finished = Signal(bool, str)
    documents_reset_requested = Signal()
    cep_reset_requested = Signal()
    cnpj_reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cidades_por_uf = _load_cities()
        self.vehicle_fields = {}
        self._panel_animations = {}
        self.owner_api_data = None
        self._registration_running = False

        self.progress_changed.connect(self._set_status)
        self.error_requested.connect(self._show_error)
        self.info_requested.connect(self._show_info)
        self.documents_ready.connect(self._populate_from_documents)
        self.cep_ready.connect(self._populate_address_from_cep)
        self.cnpj_ready.connect(self._populate_owner_from_cnpj)
        self.registration_finished.connect(self._handle_registration_finished)
        self.documents_reset_requested.connect(self._reset_import_documents_button)
        self.cep_reset_requested.connect(self._reset_cep_lookup_state)
        self.cnpj_reset_requested.connect(self._reset_cnpj_lookup_button)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 8)
        content_layout.setSpacing(14)

        content_layout.addWidget(self._build_header_panel())
        content_layout.addWidget(self._build_driver_panel())
        content_layout.addWidget(self._build_address_panel())
        content_layout.addWidget(self._build_vehicle_panel())
        content_layout.addWidget(self._build_owner_panel())
        content_layout.addWidget(self._build_action_panel())
        content_layout.addStretch(1)

        self._clear_fields()

    def refresh_theme(self):
        pass

    def _panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        apply_shadow(panel, blur=26, y_offset=8, alpha=42)
        return panel

    def _sub_panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return panel

    def _button(self, text, primary=False):
        button = QPushButton(text)
        button.setObjectName("PrimaryButton" if primary else "SecondaryButton")
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(44)
        return button

    def _line_edit(self, label, placeholder=""):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel(label)
        title.setObjectName("FieldLabel")

        edit = QLineEdit()
        edit.setObjectName("TextField")
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(46)
        edit.setClearButtonEnabled(True)

        layout.addWidget(title)
        layout.addWidget(edit)
        return wrapper, edit

    def _combo_field(self, label, values):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel(label)
        title.setObjectName("FieldLabel")

        combo = QComboBox()
        combo.setObjectName("TextField")
        combo.setMinimumHeight(46)
        combo.addItems(values)
        combo.setMaxVisibleItems(14)

        layout.addWidget(title)
        layout.addWidget(combo)
        return wrapper, combo

    def _build_header_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Cadastro Bsoft TMS")
        title.setObjectName("PanelTitle")

        subtitle = QLabel(
            "Importe a O.C., processe CNH/CRLV/RNTRC, complete o cadastro do proprietário e envie tudo para a Bsoft sem depender da tela antiga."
        )
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(12)

        self.btn_import_oc = self._button("Importar da O.C.")
        self.btn_import_oc.clicked.connect(self._handle_import_oc)

        self.btn_import_docs = self._button("Importar Documentos")
        self.btn_import_docs.clicked.connect(self._handle_import_documents)

        self.btn_clear = self._button("Limpar Campos")
        self.btn_clear.clicked.connect(self._clear_fields)

        actions.addWidget(self.btn_import_oc)
        actions.addWidget(self.btn_import_docs)
        actions.addWidget(self.btn_clear)
        actions.addStretch(1)

        self.status_label = QLabel("Fluxo pronto. Você pode importar a O.C., documentos ou preencher manualmente.")
        self.status_label.setObjectName("MetaLabel")
        self.status_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        return panel

    def _build_driver_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Dados Pessoais e CNH do Motorista")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)

        self.driver_fields = {
            "nome": self._line_edit("Nome Completo", "Nome do motorista"),
            "cpf": self._line_edit("CPF", "000.000.000-00"),
            "fone": self._line_edit("Celular", "(00) 00000-0000"),
            "dtNascimento": self._line_edit("Data de Nascimento", "DD/MM/AAAA"),
            "rntrc": self._line_edit("RNTRC do Motorista", "Número do RNTRC"),
            "cnh_numero": self._line_edit("Nº Registro CNH", "Número do registro"),
            "cnh_seguro": self._line_edit("Seguro CNH", "Número do seguro"),
            "cnh_categoria": self._line_edit("Categoria", "Categoria da CNH"),
            "cnh_espelho": self._line_edit("Nº do Espelho", "Número do espelho"),
            "cnh_validade": self._line_edit("Validade CNH", "DD/MM/AAAA"),
            "cnh_emissao": self._line_edit("Data de Emissão", "DD/MM/AAAA"),
            "cnh_primeira": self._line_edit("1ª Habilitação", "DD/MM/AAAA"),
        }

        placements = [
            ("nome", 0, 0),
            ("cpf", 1, 0),
            ("fone", 2, 0),
            ("dtNascimento", 3, 0),
            ("rntrc", 4, 0),
            ("cnh_numero", 0, 1),
            ("cnh_seguro", 1, 1),
            ("cnh_categoria", 2, 1),
            ("cnh_espelho", 3, 1),
            ("cnh_validade", 4, 1),
            ("cnh_emissao", 5, 1),
            ("cnh_primeira", 6, 1),
        ]
        for key, row, column in placements:
            grid.addWidget(self.driver_fields[key][0], row, column)

        layout.addLayout(grid)
        return panel

    def _build_address_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Endereço do Motorista")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)

        self.address_fields = {
            "cep": self._line_edit("CEP", "00000-000"),
            "logradouro": self._line_edit("Logradouro", "Rua, avenida, travessa"),
            "numero": self._line_edit("Número", "Número"),
            "bairro": self._line_edit("Bairro", "Bairro"),
            "estado": self._combo_field("Estado", sorted(self.cidades_por_uf.keys())),
            "cidade": self._combo_field("Cidade", []),
            "complemento": self._line_edit("Complemento", "Complemento"),
            "inscricaoEstadual": self._line_edit("Inscrição Estadual", "ISENTO"),
            "inscricaoMunicipal": self._line_edit("Inscrição Municipal", "ISENTO"),
            "tipoEndereco": self._combo_field("Tipo Endereço", ["Nacional", "Estrangeiro"]),
            "enderecoPreferencial": self._combo_field("Endereço Preferencial", ["Sim", "Não"]),
            "cobrancaPreferencial": self._combo_field("Cobrança Preferencial", ["Sim", "Não"]),
            "ieNaoContribuinte": self._combo_field("IE Não Contribuinte", ["Sim", "Não"]),
        }

        self.address_fields["cep"][1].editingFinished.connect(self._handle_cep_lookup)
        self.address_fields["estado"][1].currentTextChanged.connect(lambda _text: self._update_city_combo("end"))

        placements = [
            ("cep", 0, 0),
            ("logradouro", 1, 0),
            ("numero", 2, 0),
            ("bairro", 3, 0),
            ("estado", 4, 0),
            ("cidade", 5, 0),
            ("complemento", 6, 0),
            ("inscricaoEstadual", 0, 1),
            ("inscricaoMunicipal", 1, 1),
            ("tipoEndereco", 2, 1),
            ("enderecoPreferencial", 3, 1),
            ("cobrancaPreferencial", 4, 1),
            ("ieNaoContribuinte", 5, 1),
        ]
        for key, row, column in placements:
            grid.addWidget(self.address_fields[key][0], row, column)

        layout.addLayout(grid)
        return panel

    def _build_vehicle_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Veículos")
        title.setObjectName("PanelTitle")

        subtitle = QLabel("Cadastre o cavalo e, se necessário, habilite os reboques abaixo.")
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)

        toggles = QHBoxLayout()
        toggles.setSpacing(20)
        self.check_reboque1 = QCheckBox("Adicionar Reboque 1 (Placa 2)")
        self.check_reboque1.toggled.connect(self._toggle_reboque1_panel)
        self.check_reboque2 = QCheckBox("Adicionar Reboque 2 (Placa 3)")
        self.check_reboque2.toggled.connect(self._toggle_reboque2_panel)
        toggles.addWidget(self.check_reboque1)
        toggles.addWidget(self.check_reboque2)
        toggles.addStretch(1)

        self.vehicle_panels = {
            "cavalo": self._build_vehicle_section("Dados do Cavalo Mecânico (Placa 1)", "cavalo"),
            "reboque1": self._build_vehicle_section("Dados do Reboque 1 (Placa 2)", "reboque1"),
            "reboque2": self._build_vehicle_section("Dados do Reboque 2 (Placa 3)", "reboque2"),
        }

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(toggles)
        layout.addWidget(self.vehicle_panels["cavalo"])
        layout.addWidget(self.vehicle_panels["reboque1"])
        layout.addWidget(self.vehicle_panels["reboque2"])

        self._prepare_collapsible_panel("reboque1", expanded=False)
        self._prepare_collapsible_panel("reboque2", expanded=False)
        self.check_reboque2.setEnabled(False)
        return panel

    def _build_vehicle_section(self, title_text, suffix):
        panel = self._sub_panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel(title_text)
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)

        fields = {
            "placa": self._line_edit("Placa", "ABC1D23"),
            "renavam": self._line_edit("RENAVAM", "Número do renavam"),
            "eixos": self._line_edit("Qtd. de Eixos", "Quantidade de eixos"),
            "estado": self._combo_field("Estado", sorted(self.cidades_por_uf.keys())),
            "cidade": self._combo_field("Cidade", []),
            "marca": self._combo_field("Marca", []),
            "modelo": self._line_edit("Modelo", "Modelo"),
            "categoria": self._combo_field("Categoria do Veículo", sorted(BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP.keys())),
            "rodado": self._combo_field("Tipo Rodado", list(BSOFT_TIPOS_RODADO_NOMES.values())),
            "carroceria": self._combo_field("Tipo Carroceria", list(BSOFT_TIPOS_CARROCERIA_NOMES.values())),
            "equipamento": self._combo_field("Tipo de Equipamento", sorted(BSOFT_TIPOS_EQUIPAMENTO.keys())),
        }

        fields["placa"][1].textChanged.connect(lambda _text, s=suffix: self._format_plate(s))
        fields["estado"][1].currentTextChanged.connect(lambda _text, s=suffix: self._update_city_combo(s))
        fields["categoria"][1].currentTextChanged.connect(lambda _text, s=suffix: self._handle_vehicle_category_change(s))

        placements = [
            ("placa", 0, 0),
            ("renavam", 1, 0),
            ("eixos", 2, 0),
            ("estado", 3, 0),
            ("cidade", 4, 0),
            ("marca", 0, 1),
            ("modelo", 1, 1),
            ("categoria", 2, 1),
            ("rodado", 3, 1),
            ("carroceria", 4, 1),
            ("equipamento", 5, 1),
        ]
        for key, row, column in placements:
            grid.addWidget(fields[key][0], row, column)

        self.vehicle_fields[suffix] = {key: widget for key, (_wrapper, widget) in fields.items()}
        layout.addLayout(grid)
        return panel

    def _build_owner_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel("Proprietário do Veículo")
        title.setObjectName("PanelTitle")
        self.check_owner = QCheckBox("Motorista é o proprietário do(s) veículo(s)")
        self.check_owner.toggled.connect(self._toggle_owner_panel)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.check_owner)

        subtitle = QLabel("Se o veículo estiver em nome de outra empresa, preencha os dados abaixo.")
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)

        self.owner_form = self._sub_panel()
        owner_layout = QVBoxLayout(self.owner_form)
        owner_layout.setContentsMargins(18, 18, 18, 18)
        owner_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        self.owner_fields = {
            "cnpj": self._line_edit("CPF / CNPJ do Proprietário", "00.000.000/0000-00"),
            "razao_social": self._line_edit("Razão Social / Nome", "Razão social"),
            "rntrc": self._line_edit("RNTRC do Proprietário", "Número do RNTRC"),
            "tipo": self._combo_field("Tipo Transportadora (PJ)", ["ETC", "CTC", "Equiparado"]),
        }

        self.btn_lookup_cnpj = self._button("Buscar por CNPJ")
        self.btn_lookup_cnpj.clicked.connect(self._handle_cnpj_lookup)

        top_row.addWidget(self.owner_fields["cnpj"][0], 1)
        top_row.addWidget(self.btn_lookup_cnpj, 0, Qt.AlignBottom)

        owner_grid = QGridLayout()
        owner_grid.setHorizontalSpacing(18)
        owner_grid.setVerticalSpacing(12)
        owner_grid.addWidget(self.owner_fields["razao_social"][0], 0, 0)
        owner_grid.addWidget(self.owner_fields["rntrc"][0], 1, 0)
        owner_grid.addWidget(self.owner_fields["tipo"][0], 0, 1)

        owner_layout.addLayout(top_row)
        owner_layout.addLayout(owner_grid)

        layout.addLayout(title_row)
        layout.addWidget(subtitle)
        layout.addWidget(self.owner_form)
        return panel

    def _build_action_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Ação Final")
        title.setObjectName("PanelTitle")

        subtitle = QLabel("Quando os dados estiverem conferidos, envie o cadastro completo para a Bsoft.")
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)

        self.register_hint = QLabel("Campos mínimos: Nome e CPF do motorista. O restante pode ser importado da documentação.")
        self.register_hint.setObjectName("MetaLabel")
        self.register_hint.setWordWrap(True)

        self.btn_register = self._button("Cadastrar Tudo na Bsoft", primary=True)
        self.btn_register.setMinimumHeight(52)
        self.btn_register.clicked.connect(self._handle_register)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.register_hint)
        layout.addWidget(self.btn_register)
        return panel

    def _set_status(self, text):
        self.status_label.setText(text)
        if self._registration_running:
            self.btn_register.setText(text)

    def _show_error(self, title, message):
        self.status_label.setText(message.splitlines()[0])
        QMessageBox.critical(self, title, message)

    def _show_info(self, title, message):
        self.status_label.setText(message.splitlines()[0])
        QMessageBox.information(self, title, message)

    def _set_combo_items(self, combo, items, keep_current=False):
        current = combo.currentText() if keep_current else ""
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        combo.blockSignals(False)
        if current:
            self._set_combo_text(combo, current)

    def _set_combo_text(self, combo, value):
        text = (value or "").strip()
        if not text:
            combo.setCurrentIndex(-1)
            return
        index = combo.findText(text, Qt.MatchFixedString)
        if index == -1:
            combo.addItem(text)
            index = combo.findText(text, Qt.MatchFixedString)
        combo.setCurrentIndex(index)

    def _get_field_text(self, fields, key):
        widget = fields[key][1] if isinstance(fields[key], tuple) else fields[key]
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return widget.text().strip()

    def _set_field_text(self, fields, key, value):
        widget = fields[key][1] if isinstance(fields[key], tuple) else fields[key]
        cleaned = self._clean_value(value)
        if isinstance(widget, QComboBox):
            self._set_combo_text(widget, cleaned)
        else:
            widget.setText(cleaned)

    def _clean_value(self, value):
        text = "" if value is None else str(value).strip()
        if text.lower() in {"não encontrada", "nao encontrada", "formato inválido", "formato invalido"}:
            return ""
        return text

    def _format_plate(self, suffix):
        field = self.vehicle_fields[suffix]["placa"]
        cleaned = re.sub(r"[^A-Za-z0-9]", "", field.text().upper())[:7]
        formatted = f"{cleaned[:3]}-{cleaned[3:]}" if len(cleaned) > 3 else cleaned
        if formatted == field.text():
            return
        field.blockSignals(True)
        field.setText(formatted)
        field.blockSignals(False)

    def _toggle_owner_panel(self):
        is_owner = self.check_owner.isChecked()
        self.owner_form.setVisible(not is_owner)
        self.btn_lookup_cnpj.setEnabled(not is_owner)

    def _toggle_reboque1_panel(self):
        visible = self.check_reboque1.isChecked()
        self.check_reboque2.setEnabled(visible)
        self._animate_vehicle_panel("reboque1", visible)
        if not visible:
            self.check_reboque2.setChecked(False)
            self._clear_vehicle_fields("reboque1")
            self._clear_vehicle_fields("reboque2")

    def _toggle_reboque2_panel(self):
        visible = self.check_reboque2.isChecked() and self.check_reboque1.isChecked()
        self._animate_vehicle_panel("reboque2", visible)
        if not visible:
            self._clear_vehicle_fields("reboque2")

    def _prepare_collapsible_panel(self, key, expanded):
        panel = self.vehicle_panels[key]
        expanded_height = max(panel.sizeHint().height(), 1)
        panel.setProperty("expandedHeight", expanded_height)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if expanded:
            panel.setMinimumHeight(expanded_height)
            panel.setMaximumHeight(expanded_height)
            panel.setVisible(True)
        else:
            panel.setMinimumHeight(0)
            panel.setMaximumHeight(0)
            panel.setVisible(False)

    def _animate_vehicle_panel(self, key, expanded):
        panel = self.vehicle_panels[key]
        expanded_height = int(panel.property("expandedHeight") or panel.sizeHint().height() or 1)

        if expanded:
            panel.setVisible(True)

        existing = self._panel_animations.get(key)
        if existing is not None and existing.state():
            existing.stop()

        group = QParallelAnimationGroup(self)
        for prop_name in (b"minimumHeight", b"maximumHeight"):
            animation = QPropertyAnimation(panel, prop_name, self)
            animation.setDuration(160)
            animation.setStartValue(panel.minimumHeight() if prop_name == b"minimumHeight" else panel.maximumHeight())
            animation.setEndValue(expanded_height if expanded else 0)
            animation.setEasingCurve(QEasingCurve.OutCubic if expanded else QEasingCurve.InOutCubic)
            group.addAnimation(animation)

        def finalize():
            if expanded:
                panel.setMinimumHeight(expanded_height)
                panel.setMaximumHeight(expanded_height)
            else:
                panel.setVisible(False)
                panel.setMinimumHeight(0)
                panel.setMaximumHeight(0)

        group.finished.connect(finalize)
        self._panel_animations[key] = group
        group.start()

    def _update_city_combo(self, suffix):
        if suffix == "end":
            state_combo = self.address_fields["estado"][1]
            city_combo = self.address_fields["cidade"][1]
        else:
            state_combo = self.vehicle_fields[suffix]["estado"]
            city_combo = self.vehicle_fields[suffix]["cidade"]

        state = state_combo.currentText().strip()
        cities = [cidade for cidade, _ibge in self.cidades_por_uf.get(state, [])]
        self._set_combo_items(city_combo, cities)

    def _handle_vehicle_category_change(self, suffix):
        category = self.vehicle_fields[suffix]["categoria"].currentText().strip()
        brands = sorted(BSOFT_CATEGORY_TO_SIMPLE_BRANDS_MAP.get(category, []))
        self._set_combo_items(self.vehicle_fields[suffix]["marca"], brands)

        category_id = BSOFT_CATEGORIAS_VEICULO.get(category)
        if category_id is None:
            return

        equipment_id = BSOFT_CATEGORY_TO_EQUIPMENT_MAP.get(category_id)
        equipment_name = next((desc for desc, code in BSOFT_TIPOS_EQUIPAMENTO.items() if code == equipment_id), "")
        rodado_id = BSOFT_CATEGORY_ID_TO_RODADO_ID_MAP.get(category_id, "00")
        rodado_name = BSOFT_TIPOS_RODADO_NOMES.get(rodado_id, "NÃO APLICÁVEL")

        self._set_combo_text(self.vehicle_fields[suffix]["equipamento"], equipment_name)
        self._set_combo_text(self.vehicle_fields[suffix]["rodado"], rodado_name)

    def _clear_vehicle_fields(self, suffix):
        for key, widget in self.vehicle_fields[suffix].items():
            if isinstance(widget, QComboBox):
                if key == "cidade":
                    self._set_combo_items(widget, [])
                else:
                    widget.setCurrentIndex(-1)
            else:
                widget.clear()

    def _clear_fields(self):
        for fields in (self.driver_fields, self.address_fields, self.owner_fields):
            for _key, (_wrapper, widget) in fields.items():
                if isinstance(widget, QComboBox):
                    widget.setCurrentIndex(-1)
                else:
                    widget.clear()

        self.address_fields["inscricaoEstadual"][1].setText("ISENTO")
        self.address_fields["inscricaoMunicipal"][1].setText("ISENTO")
        self._set_combo_text(self.address_fields["tipoEndereco"][1], "Nacional")
        self._set_combo_text(self.address_fields["enderecoPreferencial"][1], "Sim")
        self._set_combo_text(self.address_fields["cobrancaPreferencial"][1], "Não")
        self._set_combo_text(self.address_fields["ieNaoContribuinte"][1], "Sim")

        for suffix in ("cavalo", "reboque1", "reboque2"):
            self._clear_vehicle_fields(suffix)

        self.owner_api_data = None
        self.check_owner.setChecked(True)
        self.check_reboque1.setChecked(False)
        self.check_reboque2.setChecked(False)
        self._toggle_owner_panel()
        self._toggle_reboque1_panel()
        self._toggle_reboque2_panel()
        self._set_status("Fluxo pronto. Você pode importar a O.C., documentos ou preencher manualmente.")

    def _handle_import_oc(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o arquivo da Ordem de Coleta",
            "",
            "Documentos (*.docx *.pdf);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        try:
            text = self._read_oc_text(file_path)
            data = self._extract_oc_data(text)
        except Exception as exc:
            QMessageBox.critical(self, "Erro de Leitura", f"Não foi possível ler o arquivo da O.C.\n\n{exc}")
            return

        self._clear_fields()
        self._set_field_text(self.driver_fields, "nome", data.get("nome"))
        self._set_field_text(self.driver_fields, "cpf", data.get("cpf"))
        self._set_field_text(self.driver_fields, "cnh_numero", data.get("cnh"))
        self._set_field_text(self.driver_fields, "fone", data.get("fone"))

        self.vehicle_fields["cavalo"]["placa"].setText(self._clean_value(data.get("placa_cavalo")))
        if data.get("placa_carreta1"):
            self.check_reboque1.setChecked(True)
            self.vehicle_fields["reboque1"]["placa"].setText(self._clean_value(data.get("placa_carreta1")))
        if data.get("placa_carreta2"):
            self.check_reboque1.setChecked(True)
            self.check_reboque2.setChecked(True)
            self.vehicle_fields["reboque2"]["placa"].setText(self._clean_value(data.get("placa_carreta2")))

        self._set_status(f"Dados da O.C. importados de {os.path.basename(file_path)}.")
        QMessageBox.information(self, "Sucesso", "Dados importados com sucesso da Ordem de Coleta.")

    def _read_oc_text(self, file_path):
        extension = os.path.splitext(file_path)[1].lower()
        if extension == ".docx":
            document = Document(file_path)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if extension == ".pdf":
            with pdfplumber.open(file_path) as pdf:
                texts = [page.extract_text() for page in pdf.pages]
            return "\n".join(filter(None, texts))
        raise ValueError(f"O formato '{extension}' não é suportado.")

    def _extract_oc_data(self, text):
        normalized = normalizar_texto_sem_acento(text).replace("–", "-").replace("—", "-").replace("â€“", "-").replace("â€”", "-")
        data = {}

        motorista = re.search(
            r"MOTORISTA:\s*([\d.\-]+)\s*-\s*([A-Z\s]+?)(?=\s+CNH:|\s+FONE:|\n)",
            normalized,
            re.MULTILINE,
        )
        if motorista:
            data["cpf"] = motorista.group(1).strip()
            data["nome"] = motorista.group(2).strip()

        cnh = re.search(r"CNH:\s*(\d+)", normalized)
        if cnh:
            data["cnh"] = cnh.group(1).strip()

        phone = re.search(r"FONE:\s*([\d\s()\-]+)", normalized)
        if phone:
            data["fone"] = phone.group(1).strip()

        patterns = {
            "placa_cavalo": r"1\w*\s*PLACA:\s*([A-Z0-9\-]+)",
            "placa_carreta1": r"2\w*\s*PLACA:\s*([A-Z0-9\-]+)",
            "placa_carreta2": r"3\w*\s*PLACA:\s*([A-Z0-9\-]+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, normalized)
            if match:
                data[key] = match.group(1).strip()
        return data

    def _handle_import_documents(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecione os documentos",
            "",
            "Documentos (*.pdf *.jpg *.jpeg *.png *.bmp);;Todos os arquivos (*.*)",
        )
        if not files:
            return

        self.btn_import_docs.setEnabled(False)
        self.btn_import_docs.setText("Processando...")
        self._set_status("Processando documentos com OCR...")
        threading.Thread(target=self._process_documents_worker, args=(files,), daemon=True).start()

    def _process_documents_worker(self, files):
        try:
            driver_data = {}
            vehicle_docs = []

            for file_path in files:
                text = obter_texto_do_arquivo_com_azure(file_path)
                if not text:
                    continue
                doc_type = self._classify_document(text)
                if doc_type == "CNH":
                    driver_data.update(extrair_dados_cnh_com_azure_api(text))
                elif doc_type == "CRLV":
                    vehicle_docs.append(extrair_dados_crlv_com_azure_api(text))
                elif doc_type == "RNTRC":
                    driver_data.update(extrair_dados_rntrc_com_azure_api(text))

            self.documents_ready.emit(driver_data, vehicle_docs)
        except Exception as exc:
            self.error_requested.emit("Erro no OCR", f"Não foi possível processar os documentos.\n\n{exc}")
            self.documents_reset_requested.emit()

    def _reset_import_documents_button(self):
        self.btn_import_docs.setEnabled(True)
        self.btn_import_docs.setText("Importar Documentos")

    def _reset_cep_lookup_state(self):
        self.address_fields["cep"][1].setEnabled(True)

    def _reset_cnpj_lookup_button(self):
        self.btn_lookup_cnpj.setEnabled(not self.check_owner.isChecked() and not self._registration_running)
        self.btn_lookup_cnpj.setText("Buscar por CNPJ")

    def _classify_document(self, text):
        upper = normalizar_texto_sem_acento(text)
        if "CARTEIRA NACIONAL DE HABILITA" in upper:
            return "CNH"
        if "CERTIFICADO DE REGISTRO E LICENCIAMENTO" in upper:
            return "CRLV"
        if "RNTRC" in upper or "TRANSPORTADORES RODOVIARIOS DE CARGAS" in upper:
            return "RNTRC"
        return "DESCONHECIDO"

    def _populate_from_documents(self, driver_data, vehicle_docs):
        if not driver_data and not vehicle_docs:
            self._reset_import_documents_button()
            QMessageBox.warning(self, "OCR", "Nenhum dado útil foi encontrado nos documentos selecionados.")
            self._set_status("Os documentos foram lidos, mas nenhum dado útil foi encontrado.")
            return

        self._clear_fields()

        mapping = {
            "nome": "nome",
            "cpf": "cpf",
            "dtNascimento": "dtNascimento",
            "rntrc": "rntrc",
            "cnh_numero": "numero",
            "cnh_seguro": "seguro",
            "cnh_categoria": "categoria",
            "cnh_espelho": "protocolo",
            "cnh_validade": "dtValidade",
            "cnh_emissao": "dtExpedicao",
            "cnh_primeira": "dtPrimeiraExpedicao",
        }
        for field_key, data_key in mapping.items():
            self._set_field_text(self.driver_fields, field_key, driver_data.get(data_key))

        vehicle_slots = ("cavalo", "reboque1", "reboque2")
        for index, data in enumerate(vehicle_docs[:3]):
            suffix = vehicle_slots[index]
            if suffix == "reboque1":
                self.check_reboque1.setChecked(True)
            elif suffix == "reboque2":
                self.check_reboque1.setChecked(True)
                self.check_reboque2.setChecked(True)

            vehicle = self.vehicle_fields[suffix]
            vehicle["placa"].setText(self._clean_value(data.get("placa")))
            vehicle["renavam"].setText(self._clean_value(data.get("renavam")))
            vehicle["modelo"].setText(self._clean_value(data.get("modelo")))
            vehicle["eixos"].setText(self._clean_value(data.get("eixos")))

            category = self._clean_value(data.get("categoria_veiculo"))
            if not category and suffix == "reboque1":
                category = "SEMI-REBOQUE 1"
            elif not category and suffix == "reboque2":
                category = "SEMI-REBOQUE 2"
            self._set_combo_text(vehicle["categoria"], category)
            self._handle_vehicle_category_change(suffix)
            self._set_combo_text(vehicle["marca"], self._clean_value(data.get("marca")))
            self._set_combo_text(vehicle["carroceria"], self._clean_value(data.get("tipo_carroceria")))
            self._set_combo_text(vehicle["estado"], self._clean_value(data.get("estado")))
            self._update_city_combo(suffix)
            self._set_combo_text(vehicle["cidade"], self._clean_value(data.get("cidade")))

        self._set_status("Documentos processados e formulário preenchido.")
        self._reset_import_documents_button()
        QMessageBox.information(self, "Sucesso", "Documentos processados e campos preenchidos.")

    def _handle_cep_lookup(self):
        cep = re.sub(r"\D", "", self.address_fields["cep"][1].text())
        if not cep:
            return
        if len(cep) != 8:
            QMessageBox.warning(self, "CEP inválido", "O CEP deve conter 8 dígitos.")
            return

        self.address_fields["cep"][1].setEnabled(False)
        self._set_status("Consultando CEP...")
        threading.Thread(target=self._cep_lookup_worker, args=(cep,), daemon=True).start()

    def _cep_lookup_worker(self, cep):
        try:
            response = requests.get(f"https://brasilapi.com.br/api/cep/v1/{cep}", timeout=10)
            response.raise_for_status()
            self.cep_ready.emit(response.json())
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                self.error_requested.emit("CEP não encontrado", f"O CEP '{cep}' não foi encontrado.")
            else:
                self.error_requested.emit("Erro na consulta de CEP", f"A API retornou um erro inesperado.\n\n{exc}")
        except requests.exceptions.RequestException as exc:
            self.error_requested.emit("Erro de rede", f"Não foi possível consultar o CEP.\n\n{exc}")
        finally:
            self.cep_reset_requested.emit()

    def _populate_address_from_cep(self, data):
        self.address_fields["logradouro"][1].setText(self._clean_value(data.get("street")))
        self.address_fields["bairro"][1].setText(self._clean_value(data.get("neighborhood")))
        self.address_fields["complemento"][1].clear()
        self._set_combo_text(self.address_fields["estado"][1], self._clean_value(data.get("state")))
        self._update_city_combo("end")
        self._set_combo_text(self.address_fields["cidade"][1], self._clean_value(data.get("city")))
        self.address_fields["numero"][1].setFocus()
        self._set_status("Endereço preenchido pela consulta de CEP.")

    def _handle_cnpj_lookup(self):
        cnpj = re.sub(r"\D", "", self.owner_fields["cnpj"][1].text())
        if len(cnpj) != 14:
            QMessageBox.warning(self, "CNPJ inválido", "O CNPJ deve conter 14 dígitos.")
            return

        self.btn_lookup_cnpj.setEnabled(False)
        self.btn_lookup_cnpj.setText("Buscando...")
        self._set_status("Consultando CNPJ...")
        threading.Thread(target=self._cnpj_lookup_worker, args=(cnpj,), daemon=True).start()

    def _cnpj_lookup_worker(self, cnpj):
        try:
            response = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=15)
            response.raise_for_status()
            self.cnpj_ready.emit(response.json())
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                self.error_requested.emit("CNPJ não encontrado", f"O CNPJ '{cnpj}' não foi encontrado.")
            else:
                self.error_requested.emit("Erro na consulta de CNPJ", f"A API retornou um erro inesperado.\n\n{exc}")
        except requests.exceptions.RequestException as exc:
            self.error_requested.emit("Erro de rede", f"Não foi possível consultar o CNPJ.\n\n{exc}")
        finally:
            self.cnpj_reset_requested.emit()

    def _populate_owner_from_cnpj(self, data):
        self.owner_api_data = data
        self.owner_fields["razao_social"][1].setText(self._clean_value(data.get("razao_social")))
        self.owner_fields["rntrc"][1].setFocus()
        self._set_status("Razão social preenchida pela consulta de CNPJ.")

    def _handle_register(self):
        if self._registration_running:
            return

        has_vehicle = any(self._vehicle_plate_present(suffix) for suffix in ("cavalo", "reboque1", "reboque2"))
        allow_without_vehicle = False
        if not has_vehicle:
            answer = QMessageBox.question(
                self,
                "Nenhum veículo",
                "Nenhum veículo foi informado. Deseja continuar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            allow_without_vehicle = True

        self._registration_running = True
        self._set_registration_state(True, "1/5: Preparando dados...")
        threading.Thread(target=self._register_worker, args=(allow_without_vehicle,), daemon=True).start()

    def _vehicle_plate_present(self, suffix):
        if suffix == "reboque1" and not self.check_reboque1.isChecked():
            return False
        if suffix == "reboque2" and not self.check_reboque2.isChecked():
            return False
        return bool(self.vehicle_fields[suffix]["placa"].text().strip())

    def _set_registration_state(self, busy, text=None):
        self.btn_register.setEnabled(not busy)
        self.btn_import_oc.setEnabled(not busy)
        self.btn_import_docs.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)
        self.btn_lookup_cnpj.setEnabled(not busy and not self.check_owner.isChecked())
        self.btn_register.setText(text or "Cadastrar Tudo na Bsoft")
        if text:
            self._set_status(text)

    def _handle_registration_finished(self, success, message):
        self._registration_running = False
        self._set_registration_state(False)
        if success:
            self._set_status(message)
            QMessageBox.information(self, "Sucesso", message)
        else:
            self._set_status(message.splitlines()[0])
            QMessageBox.critical(self, "Erro no Processo", message)

    def _register_worker(self, allow_without_vehicle):
        try:
            def update_progress(text):
                self.progress_changed.emit(text)

            def format_api_date(value):
                text = self._clean_value(value)
                if not text:
                    return None
                try:
                    return datetime.strptime(text, "%d/%m/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    return None

            def call_api(func, *args, default_error="Falha na comunicação com a Bsoft."):
                captured = []
                result = func(*args, error_handler=lambda _title, message: captured.append(message))
                if result is None and captured:
                    raise RuntimeError(captured[-1])
                if result is None and default_error:
                    raise RuntimeError(default_error)
                return result

            update_progress("1/5: Preparando dados...")
            driver_payload = {
                "nome": self._get_field_text(self.driver_fields, "nome"),
                "cpf": re.sub(r"\D", "", self._get_field_text(self.driver_fields, "cpf")),
                "fone": re.sub(r"\D", "", self._get_field_text(self.driver_fields, "fone")),
                "is_owner": self.check_owner.isChecked(),
                "rntrc": self._get_field_text(self.driver_fields, "rntrc"),
                "dtNascimento": format_api_date(self._get_field_text(self.driver_fields, "dtNascimento")),
                "cnh": {
                    "numero": self._get_field_text(self.driver_fields, "cnh_numero"),
                    "seguro": self._get_field_text(self.driver_fields, "cnh_seguro"),
                    "categoria": self._get_field_text(self.driver_fields, "cnh_categoria"),
                    "protocolo": self._get_field_text(self.driver_fields, "cnh_espelho"),
                    "dtValidade": format_api_date(self._get_field_text(self.driver_fields, "cnh_validade")),
                    "dtExpedicao": format_api_date(self._get_field_text(self.driver_fields, "cnh_emissao")),
                    "dtPrimeiraExpedicao": format_api_date(self._get_field_text(self.driver_fields, "cnh_primeira")),
                },
            }
            if not driver_payload["nome"] or not driver_payload["cpf"]:
                raise ValueError("O Nome e o CPF do motorista são obrigatórios.")

            update_progress("2/5: Validando motorista...")
            driver_exists = self._search_person_by_cpf(driver_payload["cpf"])
            if driver_exists:
                driver_response = call_api(
                    atualizar_pessoa_fisica_bsoft,
                    driver_payload["cpf"],
                    driver_payload,
                    default_error="Falha ao atualizar o motorista na Bsoft.",
                )
            else:
                driver_response = call_api(
                    cadastrar_pessoa_fisica_bsoft,
                    driver_payload,
                    default_error="Falha ao cadastrar o motorista na Bsoft.",
                )
            driver_id = driver_response.get("codPessoa")
            if not driver_id:
                raise RuntimeError("A Bsoft não retornou o identificador do motorista.")

            update_progress("3/5: Salvando endereço...")
            if not driver_exists:
                motorista_disponivel = False
                for _attempt in range(10):
                    time.sleep(2)
                    if self._search_person_by_cpf(driver_payload["cpf"]):
                        motorista_disponivel = True
                        break
                if not motorista_disponivel:
                    raise RuntimeError("A API da Bsoft não disponibilizou o motorista a tempo para vincular o endereço.")

            address_payload = self._build_driver_address_payload()
            if address_payload.get("logradouro"):
                call_api(
                    cadastrar_endereco_bsoft,
                    driver_id,
                    address_payload,
                    default_error="Falha ao salvar o endereço do motorista.",
                )

            update_progress("4/5: Validando proprietário...")
            owner_id = driver_id
            rntrc_final = driver_payload["rntrc"]
            if not self.check_owner.isChecked():
                owner_id, rntrc_final = self._save_owner_company(call_api)

            update_progress("5/5: Cadastrando veículos...")
            vehicle_payloads = self._build_vehicle_payloads(driver_id, owner_id, driver_payload["cpf"], rntrc_final)
            if not vehicle_payloads and not allow_without_vehicle:
                raise ValueError("Nenhum veículo foi informado para cadastro.")

            saved = 0
            for payload in vehicle_payloads:
                call_api(
                    cadastrar_veiculo_bsoft,
                    payload,
                    default_error=f"Falha ao cadastrar o veículo {payload.get('placa', '')}.",
                )
                saved += 1
                time.sleep(1)

            self.registration_finished.emit(
                True,
                f"Processo concluído com sucesso. {saved} veículo(s) salvo(s) para '{driver_payload['nome']}'.",
            )
        except ValueError as exc:
            self.registration_finished.emit(False, str(exc))
        except Exception as exc:
            traceback.print_exc()
            self.registration_finished.emit(False, str(exc))

    def _search_person_by_cpf(self, cpf):
        if not cpf:
            return None
        url = f"https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/fisicas/{cpf}"
        try:
            response = requests.get(url, auth=(BSOFT_API_USER, BSOFT_API_PASSWORD), timeout=20)
            if response.status_code == 200 and response.text and response.json():
                return response.json()[0].get("id")
        except requests.exceptions.RequestException:
            return None
        return None

    def _search_company_by_cnpj(self, cnpj):
        if not cnpj:
            return None
        url = f"https://atlanticofertlog.bsoft.app/services/index.php/pessoas/v1/pessoas/juridicas/{cnpj}"
        try:
            response = requests.get(url, auth=(BSOFT_API_USER, BSOFT_API_PASSWORD), timeout=20)
            if response.status_code == 200 and response.text and response.json():
                return response.json()[0].get("id")
        except requests.exceptions.RequestException:
            return None
        return None

    def _build_driver_address_payload(self):
        state = self._get_field_text(self.address_fields, "estado")
        city = self._get_field_text(self.address_fields, "cidade")
        return {
            "tipoEndereco": "N" if self._get_field_text(self.address_fields, "tipoEndereco") == "Nacional" else "E",
            "cep": self._format_cep(self._get_field_text(self.address_fields, "cep")),
            "bairro": self._get_field_text(self.address_fields, "bairro"),
            "cidade": city,
            "estado": state,
            "numero": self._get_field_text(self.address_fields, "numero"),
            "complemento": self._get_field_text(self.address_fields, "complemento"),
            "logradouro": self._get_field_text(self.address_fields, "logradouro"),
            "cobrancaPreferencial": "S" if self._get_field_text(self.address_fields, "cobrancaPreferencial") == "Sim" else "N",
            "enderecoPreferencial": "S" if self._get_field_text(self.address_fields, "enderecoPreferencial") == "Sim" else "N",
            "codIBGE": self._find_ibge_code(state, city),
            "inscricaoMunicipal": self._get_field_text(self.address_fields, "inscricaoMunicipal") or "ISENTO",
            "inscricaoEstadual": self._get_field_text(self.address_fields, "inscricaoEstadual") or "ISENTO",
            "inscricaoEstadualNaoContribuinte": "S" if self._get_field_text(self.address_fields, "ieNaoContribuinte") == "Sim" else "N",
        }

    def _save_owner_company(self, call_api):
        owner_document = re.sub(r"\D", "", self._get_field_text(self.owner_fields, "cnpj"))
        if len(owner_document) != 14:
            raise ValueError("O CNPJ do proprietário é obrigatório e deve conter 14 dígitos.")

        payload = {
            "cnpj": owner_document,
            "razao_social": self._get_field_text(self.owner_fields, "razao_social"),
            "tipoTransportadora": {"ETC": "E", "CTC": "C", "Equiparado": "EQ"}.get(self._get_field_text(self.owner_fields, "tipo")),
            "rntrc": self._get_field_text(self.owner_fields, "rntrc"),
        }
        if not all(payload.values()):
            raise ValueError("Todos os campos do proprietário PJ são obrigatórios.")

        existing = self._search_company_by_cnpj(owner_document)
        if existing:
            response = call_api(
                atualizar_pessoa_juridica_bsoft,
                owner_document,
                payload,
                default_error="Falha ao atualizar o proprietário na Bsoft.",
            )
        else:
            response = call_api(
                cadastrar_pessoa_juridica_bsoft,
                payload,
                default_error="Falha ao cadastrar o proprietário na Bsoft.",
            )

        owner_id = response.get("codPessoa")
        if not owner_id:
            raise RuntimeError("A Bsoft não retornou o identificador do proprietário.")

        if self.owner_api_data and re.sub(r"\D", "", str(self.owner_api_data.get("cnpj", ""))) == owner_document:
            owner_address = self._build_owner_address_payload()
            if owner_address.get("logradouro"):
                time.sleep(5)
                call_api(
                    cadastrar_endereco_bsoft,
                    owner_id,
                    owner_address,
                    default_error="Falha ao salvar o endereço do proprietário.",
                )

        return owner_id, payload["rntrc"]

    def _build_owner_address_payload(self):
        data = self.owner_api_data or {}
        state = self._clean_value(data.get("uf"))
        city = self._clean_value(data.get("municipio"))
        state_registration = "ISENTO"
        for item in data.get("inscricoes_estaduais", []) or []:
            if item.get("ativo"):
                state_registration = item.get("inscricao_estadual") or "ISENTO"
                break
        return {
            "tipoEndereco": "N",
            "cep": self._format_cep(self._clean_value(data.get("cep"))),
            "bairro": self._clean_value(data.get("bairro")),
            "cidade": city,
            "estado": state,
            "numero": self._clean_value(data.get("numero")),
            "complemento": self._clean_value(data.get("complemento")),
            "logradouro": self._clean_value(data.get("logradouro")),
            "codIBGE": self._find_ibge_code(state, city),
            "inscricaoMunicipal": "ISENTO",
            "inscricaoEstadual": state_registration,
            "inscricaoEstadualNaoContribuinte": "S",
            "enderecoPreferencial": "S",
            "cobrancaPreferencial": "S",
        }

    def _build_vehicle_payloads(self, driver_id, owner_id, driver_cpf, rntrc_final):
        payloads = []
        for suffix in ("cavalo", "reboque1", "reboque2"):
            if suffix == "reboque1" and not self.check_reboque1.isChecked():
                continue
            if suffix == "reboque2" and not self.check_reboque2.isChecked():
                continue

            fields = self.vehicle_fields[suffix]
            plate = fields["placa"].text().strip().upper()
            if not plate:
                continue

            state = fields["estado"].currentText().strip()
            city = fields["cidade"].currentText().strip()
            category = fields["categoria"].currentText().strip()
            brand = fields["marca"].currentText().strip()
            if not state or not city:
                raise ValueError(f"Estado e cidade são obrigatórios para o veículo de placa {plate}.")
            if not category or not brand:
                raise ValueError(f"Categoria e marca são obrigatórias para o veículo de placa {plate}.")

            city_ibge = self._find_ibge_code(state, city)
            if not city_ibge:
                raise ValueError(f"Não foi possível encontrar o código IBGE para {city} - {state}.")

            category_id = BSOFT_CATEGORIAS_VEICULO.get(category)
            if category_id is None:
                raise ValueError(f"A categoria '{category}' não é válida para o veículo de placa {plate}.")

            brand_id = BSOFT_MARCA_ID_LOOKUP.get((brand, category))
            if brand_id is None:
                raise ValueError(f"Não foi possível encontrar o código da marca para {brand} / {category}.")

            payloads.append(
                {
                    "placa": plate,
                    "renavam": fields["renavam"].text().strip(),
                    "rntrc": rntrc_final,
                    "tara": "9000",
                    "capacidadeCarga": "32000",
                    "capM3": "32",
                    "modeloVeiculo": fields["modelo"].text().strip(),
                    "quantidadeEixos": fields["eixos"].text().strip(),
                    "marcaVeiculo": brand_id,
                    "categoriaVeiculo": category_id,
                    "grupoVeiculo": 2,
                    "tipoRodado": get_key_from_value(BSOFT_TIPOS_RODADO_NOMES, fields["rodado"].currentText().strip()),
                    "tipoCarroceria": get_key_from_value(BSOFT_TIPOS_CARROCERIA_NOMES, fields["carroceria"].currentText().strip()),
                    "tipoEquipamento": BSOFT_TIPOS_EQUIPAMENTO.get(fields["equipamento"].currentText().strip()),
                    "motoristaEhProprietario": self.check_owner.isChecked(),
                    "estado": state,
                    "cidade": city_ibge,
                    "proprietario_id": owner_id,
                    "motorista_documento": driver_cpf,
                    "motoristaId": driver_id,
                    "arrendatarioId": owner_id,
                }
            )
        return payloads

    def _find_ibge_code(self, state, city):
        normalized_city = normalizar_texto_sem_acento(city)
        for city_name, ibge in self.cidades_por_uf.get(state, []):
            if normalizar_texto_sem_acento(city_name) == normalized_city:
                return ibge
        return None

    def _format_cep(self, cep):
        digits = re.sub(r"\D", "", cep or "")
        if len(digits) == 8:
            return f"{digits[:5]}-{digits[5:]}"
        return digits
