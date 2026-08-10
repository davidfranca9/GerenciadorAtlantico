from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..servicos.fretes_db import (
    buscar_ultima_cotacao_por_destino,
    cadastrar_cotacao_frete,
    listar_cotacoes_frete,
)
from ..servicos.ocr import carregar_cidades_nova_logica
from ..shared import PLANILHA_CIDADES
from .widgets import apply_shadow


class AnaliseFretesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.city_options = self._load_city_options()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 6)
        layout.setSpacing(14)

        layout.addWidget(self._build_form_panel())
        layout.addWidget(self._build_search_panel())
        layout.addWidget(self._build_table_panel(), 1)

        self.reload_quotes()

    def _panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        apply_shadow(panel, blur=28, y_offset=9, alpha=52)
        return panel

    def _load_city_options(self):
        try:
            cities_by_uf = carregar_cidades_nova_logica(PLANILHA_CIDADES) or {}
        except Exception:
            return []

        cities = set()
        for city_list in cities_by_uf.values():
            for city_name, _ibge in city_list:
                text = str(city_name or "").strip()
                if text:
                    cities.add(text)
        return sorted(cities)

    def _build_form_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel("Cadastro de Fretes")
        title.setObjectName("PanelTitle")
        subtitle = QLabel("Registre novas cotações por data, destino e valor por tonelada.")
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        grid.addWidget(self._field_label("Data da Cotação"), 0, 0)
        grid.addWidget(self._field_label("Destino"), 0, 1)
        grid.addWidget(self._field_label("Valor do Frete / Ton"), 0, 2)

        self.date_edit = QDateEdit()
        self.date_edit.setObjectName("DateField")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setButtonSymbols(QAbstractSpinBox.UpDownArrows)

        self.destino_combo = self._build_city_combo()

        self.valor_field = QLineEdit()
        self.valor_field.setObjectName("TextField")
        self.valor_field.setPlaceholderText("150,00")
        self.valor_field.setFixedHeight(46)
        self.valor_field.setValidator(QDoubleValidator(0.0, 999999.99, 2, self))

        grid.addWidget(self.date_edit, 1, 0)
        grid.addWidget(self.destino_combo, 1, 1)
        grid.addWidget(self.valor_field, 1, 2)

        layout.addLayout(grid)

        self.form_status = QLabel("Preencha os campos e clique em cadastrar.")
        self.form_status.setObjectName("MetaLabel")
        self.form_status.setWordWrap(True)
        layout.addWidget(self.form_status)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)

        save_btn = QPushButton("Cadastrar Cotação")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._register_quote)

        clear_btn = QPushButton("Limpar Campos")
        clear_btn.setObjectName("SecondaryButton")
        clear_btn.clicked.connect(self._clear_form)

        buttons.addWidget(save_btn)
        buttons.addWidget(clear_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return panel

    def _build_search_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Consulta por Destino")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(12)

        self.search_combo = self._build_city_combo()
        self.search_combo.setMinimumWidth(320)

        filter_btn = QPushButton("Consultar Destino")
        filter_btn.setObjectName("PrimaryButton")
        filter_btn.clicked.connect(self._filter_by_destination)

        reset_btn = QPushButton("Mostrar Todas")
        reset_btn.setObjectName("SecondaryButton")
        reset_btn.clicked.connect(self._show_all_quotes)

        row.addWidget(self.search_combo, 1)
        row.addWidget(filter_btn)
        row.addWidget(reset_btn)
        layout.addLayout(row)

        self.search_result = QLabel("Consulte um destino para ver a última cotação cadastrada.")
        self.search_result.setObjectName("MetaLabel")
        self.search_result.setWordWrap(True)
        layout.addWidget(self.search_result)
        return panel

    def _build_table_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(20, 16, 20, 12)
        top.setSpacing(12)

        title = QLabel("Cotações Cadastradas")
        title.setObjectName("PanelTitle")
        self.table_summary = QLabel("0 registro(s)")
        self.table_summary.setObjectName("MetaLabel")

        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.table_summary)
        layout.addLayout(top)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("FretesTable")
        self.table.setHorizontalHeaderLabels(["Data", "Destino", "Valor / Tonelada"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        self.table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignCenter)
        self.table.horizontalHeaderItem(1).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeaderItem(2).setTextAlignment(Qt.AlignCenter)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 420)
        self.table.setColumnWidth(2, 220)

        layout.addWidget(self.table)
        return panel

    def _field_label(self, text):
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _build_city_combo(self):
        combo = QComboBox()
        combo.setObjectName("TextField")
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMinimumHeight(46)
        combo.addItem("")
        combo.addItems(self.city_options)

        completer = QCompleter(self.city_options, combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)
        return combo

    def reload_quotes(self, destino: str | None = None):
        rows = listar_cotacoes_frete(destino)
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        self.table_summary.setText(f"{len(rows)} registro(s)")

        for row_index, row in enumerate(rows):
            self.table.setRowHeight(row_index, 42)
            values = [
                row.get("data_cotacao", ""),
                row.get("destino", ""),
                self._format_currency(row.get("valor_tonelada", 0)),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                align = Qt.AlignCenter if col in {0, 2} else Qt.AlignLeft
                item.setTextAlignment(Qt.AlignVCenter | align)
                self.table.setItem(row_index, col, item)

    def refresh_theme(self):
        pass

    def _register_quote(self):
        destino = self.destino_combo.currentText().strip()
        if not destino:
            QMessageBox.warning(self, "Fretes", "Informe o destino da cotação.")
            return

        valor_text = self.valor_field.text().strip()
        valor = self._parse_currency(valor_text)
        if valor is None or valor <= 0:
            QMessageBox.warning(self, "Fretes", "Informe um valor válido por tonelada.")
            return

        data_cotacao = self.date_edit.date().toString("dd/MM/yyyy")
        try:
            cotacao_id = cadastrar_cotacao_frete(data_cotacao, destino, valor)
        except Exception as exc:
            QMessageBox.critical(self, "Fretes", f"Nao foi possivel cadastrar a cotacao.\n\n{exc}")
            return

        self.form_status.setText(
            f"Cotacao #{cotacao_id} registrada para {destino} em {data_cotacao} por {self._format_currency(valor)}."
        )
        self.search_combo.setCurrentText(destino)
        self._clear_form(keep_status=True)
        self._update_destination_options(destino)
        self._filter_by_destination()
        QMessageBox.information(self, "Fretes", "Cotação cadastrada com sucesso.")

    def _filter_by_destination(self):
        destino = self.search_combo.currentText().strip()
        if not destino:
            QMessageBox.warning(self, "Fretes", "Informe um destino para consultar.")
            return

        self.reload_quotes(destino)
        ultima = buscar_ultima_cotacao_por_destino(destino)
        if ultima is None:
            self.search_result.setText(f"Nenhuma cotação encontrada para {destino}.")
            return

        self.search_result.setText(
            f"Última cotação para {destino}: {self._format_currency(ultima.get('valor_tonelada', 0))} "
            f"por tonelada em {ultima.get('data_cotacao', '-')}"
        )

    def _show_all_quotes(self):
        self.search_combo.setCurrentIndex(0)
        self.search_result.setText("Listando todas as cotações cadastradas.")
        self.reload_quotes()

    def _clear_form(self, keep_status=False):
        self.date_edit.setDate(QDate.currentDate())
        self.destino_combo.setCurrentIndex(0)
        self.destino_combo.setEditText("")
        self.valor_field.clear()
        if not keep_status:
            self.form_status.setText("Preencha os campos e clique em cadastrar.")

    def _update_destination_options(self, destino):
        text = str(destino or "").strip()
        if not text or text in self.city_options:
            return
        self.city_options.append(text)
        self.city_options.sort()
        for combo in (self.destino_combo, self.search_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            combo.addItems(self.city_options)
            combo.blockSignals(False)

    def _parse_currency(self, value):
        text = str(value or "").strip()
        if not text:
            return None
        text = text.replace("R$", "").replace(" ", "")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None

    def _format_currency(self, value):
        try:
            amount = float(value)
        except (TypeError, ValueError):
            amount = 0.0
        inteiro, decimal = f"{amount:.2f}".split(".")
        grupos = []
        while inteiro:
            grupos.append(inteiro[-3:])
            inteiro = inteiro[:-3]
        inteiro_formatado = ".".join(reversed(grupos)) if grupos else "0"
        return f"R$ {inteiro_formatado},{decimal}"
