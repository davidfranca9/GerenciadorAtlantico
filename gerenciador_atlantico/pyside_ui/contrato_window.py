from __future__ import annotations

import sys

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCalendarWidget,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..servicos.ocr import carregar_cidades_nova_logica, parse_pdf_fields
from ..shared import PLANILHA_CIDADES
from .theme import apply_app_theme, current_theme_name, style_calendar_widget
from .widgets import ActionTile, BackgroundWidget, BrandLogo, MetricItem, UserChip, apply_shadow


SAMPLE_ROWS = [
    {
        "checked": True,
        "produto": "MAP",
        "toneladas": 150,
        "embalagem": "Granel",
        "pedido": "1203",
        "cliente": "Agro Silva",
        "clidente": "Rio Verde",
        "cidade": "Rio Verde",
    },
    {
        "checked": True,
        "produto": "Ureia",
        "toneladas": 120,
        "embalagem": "Saco",
        "pedido": "1309",
        "cliente": "Agro Souza",
        "clidente": "Uberlândia",
        "cidade": "Uberlândia",
    },
    {
        "checked": True,
        "produto": "Super Simples",
        "toneladas": 100,
        "embalagem": "Granel",
        "pedido": "1150",
        "cliente": "Terra Fértil",
        "clidente": "Campinas",
        "cidade": "Campinas",
    },
    {
        "checked": True,
        "produto": "MAP",
        "toneladas": 200,
        "embalagem": "Saco",
        "pedido": "1213",
        "cliente": "Plantar Agro",
        "clidente": "Sorriso",
        "cidade": "Sorriso",
    },
]


class ContratoPage(QWidget):
    state_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lista_cidades = self._load_city_list()
        self.contract_rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 6)
        layout.setSpacing(14)

        filter_panel = self._build_filter_panel()
        contracts_panel = self._build_contracts_panel()
        metrics_bar = self._build_metrics_bar()
        actions_panel = self._build_actions_panel()

        filter_panel.setMaximumHeight(210)
        metrics_bar.setMaximumHeight(108)
        actions_panel.setMaximumHeight(140)

        layout.addWidget(filter_panel)
        layout.addWidget(contracts_panel, 1)
        layout.addWidget(metrics_bar)
        layout.addWidget(actions_panel)

    def _load_city_list(self):
        try:
            return carregar_cidades_nova_logica(PLANILHA_CIDADES) or {}
        except Exception:
            return {}

    def _normalize_contract_row(self, product):
        return {
            "checked": True,
            "produto": str(product.get("produto", "")).strip(),
            "toneladas": product.get("toneladas", ""),
            "embalagem": str(product.get("embalagem", "")).strip(),
            "pedido": str(product.get("contrato", "")).strip(),
            "cliente": str(product.get("cliente", "")).strip(),
            "cidade": str(product.get("cidade", "")).strip(),
        }

    def _panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        apply_shadow(panel, blur=32, y_offset=10, alpha=56)
        return panel

    def _build_filter_panel(self):
        panel = self._panel()
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Filtro de Carregamento")
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch(1)

        select_button = QPushButton("🗁  Selecionar Contratos (PDF)")
        select_button.setObjectName("PrimaryButton")
        header.addWidget(select_button, 0, Qt.AlignRight)
        select_button.clicked.connect(self._select_contracts)
        layout.addLayout(header)

        self.selection_status = QLabel("Nenhum contrato carregado. Selecione os PDFs.")
        self.selection_status.setObjectName("MetaLabel")
        layout.addWidget(self.selection_status)

        line = QFrame()
        line.setObjectName("Divider")
        line.setFixedHeight(1)
        line.setMinimumWidth(0)
        line.setMaximumWidth(16777215)
        layout.addWidget(line)

        controls = QHBoxLayout()
        controls.setSpacing(28)

        date_col = QVBoxLayout()
        date_col.setSpacing(8)

        date_label = QLabel("Data de Carregamento")
        date_label.setObjectName("PanelMinor")
        date_col.addWidget(date_label)

        self.date_edit = QDateEdit()
        self.date_edit.setObjectName("DateField")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate(2026, 3, 12))
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.date_edit.setMinimumWidth(280)
        calendar = QCalendarWidget(self.date_edit)
        calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        calendar.setGridVisible(False)
        style_calendar_widget(calendar, current_theme_name())
        self.date_edit.setCalendarWidget(calendar)
        date_col.addWidget(self.date_edit, 0, Qt.AlignLeft)

        controls.addLayout(date_col)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(48)
        controls.addWidget(divider)

        supplier_col = QVBoxLayout()
        supplier_col.setSpacing(10)
        supplier_label = QLabel("Fornecedor")
        supplier_label.setObjectName("PanelMinor")
        supplier_col.addWidget(supplier_label)

        radio_row = QHBoxLayout()
        radio_row.setSpacing(16)

        radio_group = QButtonGroup(self)
        self.fertimax_radio = QRadioButton("Fertimax")
        self.fertimax_radio.setChecked(True)
        self.heringer_radio = QRadioButton("Heringer")
        radio_group.setExclusive(True)
        radio_group.addButton(self.fertimax_radio)
        radio_group.addButton(self.heringer_radio)
        radio_row.addWidget(self.fertimax_radio)
        radio_row.addWidget(self.heringer_radio)
        radio_row.addStretch(1)
        supplier_col.addLayout(radio_row)

        controls.addLayout(supplier_col, 1)
        self.date_edit.dateChanged.connect(self.state_changed.emit)
        self.fertimax_radio.toggled.connect(self.state_changed.emit)
        self.heringer_radio.toggled.connect(self.state_changed.emit)
        layout.addLayout(controls)
        return panel

    def _build_contracts_panel(self):
        panel = self._panel()
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(24, 16, 18, 12)
        title = QLabel("Contratos Disponíveis")
        title.setObjectName("PanelTitle")
        top.addWidget(title)
        top.addStretch(1)
        dots = QLabel("•••")
        dots.setObjectName("Dots")
        top.addWidget(dots)
        layout.addLayout(top)

        line = QFrame()
        line.setObjectName("Divider")
        line.setFixedHeight(1)
        line.setMinimumWidth(0)
        line.setMaximumWidth(16777215)
        layout.addWidget(line)

        self.table = QTableWidget(len(self.contract_rows), 7)
        self.table.setObjectName("ContractsTable")
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.table.setHorizontalHeaderLabels(
            [
                "Selecionar",
                "Produto",
                "Toneladas",
                "Embalagem",
                "Pedido",
                "Cliente",
                "Cidade",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        widths = [120, 260, 130, 150, 120, 230, 190]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

        self.row_checks = []
        for row_index, row in enumerate(self.contract_rows):
            self.table.setRowHeight(row_index, 46)

            checkbox = QCheckBox()
            checkbox.setChecked(row["checked"])
            checkbox.stateChanged.connect(self._update_metrics)
            self.row_checks.append(checkbox)

            checkbox_holder = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_holder)
            checkbox_layout.setContentsMargins(14, 0, 0, 0)
            checkbox_layout.addWidget(checkbox, 0, Qt.AlignLeft | Qt.AlignVCenter)
            checkbox_layout.addStretch(1)
            self.table.setCellWidget(row_index, 0, checkbox_holder)

            values = [
                row["produto"],
                str(row["toneladas"]),
                row["embalagem"],
                row["pedido"],
                row["cliente"],
                row["cidade"],
            ]
            for offset, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignCenter if offset in (2, 3, 4) else Qt.AlignLeft))
                self.table.setItem(row_index, offset, item)

        if self.contract_rows:
            self.table.selectRow(0)
        layout.addWidget(self.table)
        return panel

    def _build_metrics_bar(self):
        bar = QFrame()
        bar.setObjectName("MetricsBar")
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        apply_shadow(bar, blur=28, y_offset=10, alpha=44)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(22, 10, 22, 10)
        layout.setSpacing(16)

        self.metric_tons = MetricItem("↗", "0", "Toneladas Selecionadas", accent=True)
        self.metric_orders_a = MetricItem("▤", "0", "Produtos Selecionados")
        self.metric_orders_b = MetricItem("◫", "0", "Produtos na Lista")
        self.metric_clients = MetricItem("◉", "0", "Clientes Únicos")

        metrics = [self.metric_tons, self.metric_orders_a, self.metric_orders_b, self.metric_clients]
        for idx, metric in enumerate(metrics):
            layout.addWidget(metric, 1)
            if idx < len(metrics) - 1:
                divider = QFrame()
                divider.setObjectName("Divider")
                divider.setFixedHeight(52)
                layout.addWidget(divider)

        self._update_metrics()
        return bar

    def _build_actions_panel(self):
        panel = self._panel()
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(14)

        title = QLabel("Ações Operacionais")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(14)

        register = ActionTile("+", "Registrar Pedido Grande", variant="primary")
        insert = ActionTile("▤", "Inserir na Planilha", variant="secondary")
        email = ActionTile("✉", "Enviar Planilha Geral", variant="secondary")

        register.clicked.connect(lambda: self._show_action("Registrar Pedido Grande"))
        insert.clicked.connect(lambda: self._show_action("Inserir na Planilha"))
        email.clicked.connect(lambda: self._show_action("Enviar Planilha Geral"))

        row.addWidget(register, 1)
        row.addWidget(insert, 1)
        row.addWidget(email, 1)

        layout.addLayout(row)
        return panel

    def _show_action(self, name):
        QMessageBox.information(self, "Ação", f"Ação '{name}' acionada.")

    def _update_metrics(self):
        selected_rows = [row for row, checkbox in zip(self.contract_rows, self.row_checks) if checkbox.isChecked()]
        total_tons = sum(self._safe_ton(item.get("toneladas")) for item in selected_rows)
        self.metric_tons.set_value(total_tons)
        self.metric_orders_a.set_value(len(selected_rows))
        self.metric_orders_b.set_value(len(self.contract_rows))

        clientes_unicos = {
            str(item.get("cliente", "")).strip()
            for item in self.contract_rows
            if str(item.get("cliente", "")).strip()
        }
        self.metric_clients.set_value(len(clientes_unicos))
        self.state_changed.emit()

    def _select_contracts(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecione os Contratos em PDF",
            "",
            "Arquivos PDF (*.pdf)",
        )
        if not files:
            return

        extracted_rows = []
        files_without_rows = 0

        for path in files:
            try:
                products = parse_pdf_fields(path, self.lista_cidades, None)
            except Exception:
                files_without_rows += 1
                continue

            if not products:
                files_without_rows += 1
                continue

            for product in products:
                extracted_rows.append(self._normalize_contract_row(product))

        self.contract_rows = extracted_rows
        self._reload_table()
        if extracted_rows:
            self.selection_status.setText(
                f"{len(extracted_rows)} produto(s) carregado(s) de {len(files)} PDF(s)."
            )
            if files_without_rows:
                self.selection_status.setText(
                    f"{len(extracted_rows)} produto(s) carregado(s). "
                    f"{files_without_rows} PDF(s) não geraram itens."
                )
        else:
            self.selection_status.setText("Nenhum contrato foi extraído dos PDFs selecionados.")
        self.state_changed.emit()

    def _reload_table(self):
        self.table.clearContents()
        self.table.setRowCount(len(self.contract_rows))
        self.row_checks = []

        for row_index, row in enumerate(self.contract_rows):
            self.table.setRowHeight(row_index, 46)

            checkbox = QCheckBox()
            checkbox.setChecked(bool(row.get("checked", True)))
            checkbox.stateChanged.connect(self._update_metrics)
            self.row_checks.append(checkbox)

            checkbox_holder = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_holder)
            checkbox_layout.setContentsMargins(14, 0, 0, 0)
            checkbox_layout.addWidget(checkbox, 0, Qt.AlignLeft | Qt.AlignVCenter)
            checkbox_layout.addStretch(1)
            self.table.setCellWidget(row_index, 0, checkbox_holder)

            values = [
                row.get("produto", ""),
                str(row.get("toneladas", "")),
                row.get("embalagem", ""),
                row.get("pedido", ""),
                row.get("cliente", ""),
                row.get("cidade", ""),
            ]
            for offset, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignCenter if offset in (2, 3, 4) else Qt.AlignLeft))
                self.table.setItem(row_index, offset, item)

        if self.contract_rows:
            self.table.selectRow(0)
        self._update_metrics()

    def _safe_ton(self, value):
        try:
            if value in ("", None):
                return 0
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return 0

    def get_selected_contracts(self):
        selected = []
        for row, checkbox in zip(self.contract_rows, self.row_checks):
            if not checkbox.isChecked():
                continue
            selected.append(
                {
                    "produto": row.get("produto", ""),
                    "toneladas": row.get("toneladas", ""),
                    "embalagem": row.get("embalagem", ""),
                    "contrato": row.get("pedido", ""),
                    "pedido": row.get("pedido", ""),
                    "cliente": row.get("cliente", ""),
                    "cidade": row.get("cidade", ""),
                }
            )
        return selected

    def get_loading_date(self):
        return self.date_edit.date().toString("dd/MM/yyyy")

    def get_supplier(self):
        if getattr(self, "heringer_radio", None) and self.heringer_radio.isChecked():
            return "Heringer"
        return "Fertimax"

    def refresh_theme(self):
        style_calendar_widget(self.date_edit.calendarWidget(), current_theme_name())


class ContratoMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Atlântico Fertlog | Contrato")
        self.resize(1536, 1024)
        self.setMinimumSize(1280, 860)

        root = BackgroundWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("Shell")
        root_layout.addWidget(shell)

        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(8)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setMinimumHeight(74)
        apply_shadow(top_bar, blur=32, y_offset=10, alpha=56)

        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(26, 14, 20, 14)
        top_layout.setSpacing(24)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(14)
        brand_row.addWidget(BrandLogo())
        brand_title = QLabel("ATLÂNTICO FERTLOG")
        brand_title.setObjectName("BrandTitle")
        brand_row.addWidget(brand_title)

        brand_widget = QWidget()
        brand_widget.setLayout(brand_row)
        top_layout.addWidget(brand_widget, 0, Qt.AlignVCenter)

        nav_placeholder = QWidget()
        nav_placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top_layout.addWidget(nav_placeholder, 1)
        top_layout.addWidget(UserChip(), 0, Qt.AlignRight | Qt.AlignVCenter)
        shell_layout.addWidget(top_bar)

        shell_layout.addWidget(ContratoPage(), 1)


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    window = ContratoMainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
