from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..servicos.agendamentos_db import (
    STATUS_AGENDAMENTO,
    atualizar_dados_internos_agendamento,
    atualizar_status_agendamento,
    listar_agendamentos,
    listar_itens_agendamento,
)
from .widgets import apply_shadow


class AgendamentosPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_records = []
        self.records = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 6)
        layout.setSpacing(14)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_table_panel(), 1)
        layout.addWidget(self._build_details_panel())

        self.reload_data()

    def _panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        apply_shadow(panel, blur=28, y_offset=9, alpha=52)
        return panel

    def _build_toolbar(self):
        panel = self._panel()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        title = QLabel("Agendamentos")
        title.setObjectName("PanelTitle")
        subtitle = QLabel("Acompanhe os agendamentos e ajuste os dados internos sem mexer na O.C.")
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)

        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        layout.addLayout(title_col, 1)

        self.search_field = QLineEdit()
        self.search_field.setObjectName("TextField")
        self.search_field.setPlaceholderText("Buscar motorista, placa, pedido ou cliente")
        self.search_field.setMinimumWidth(320)
        self.search_field.setFixedHeight(46)
        self.search_field.textChanged.connect(self._apply_filters)

        self.status_combo = QComboBox()
        self.status_combo.setObjectName("TextField")
        self.status_combo.addItems(STATUS_AGENDAMENTO)
        self.status_combo.setMinimumWidth(220)

        refresh_btn = QPushButton("Recarregar")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.clicked.connect(self.reload_data)

        update_btn = QPushButton("Salvar Status")
        update_btn.setObjectName("PrimaryButton")
        update_btn.clicked.connect(self._save_selected_status)

        layout.addWidget(self.search_field, 0, Qt.AlignVCenter)
        layout.addWidget(self.status_combo, 0, Qt.AlignVCenter)
        layout.addWidget(refresh_btn, 0, Qt.AlignVCenter)
        layout.addWidget(update_btn, 0, Qt.AlignVCenter)
        return panel

    def _build_table_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.table = QTableWidget(0, 10)
        self.table.setObjectName("AgendamentosTable")
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Enviado em",
                "Motorista",
                "Placa",
                "Data Carga",
                "Fornecedor",
                "Pedidos",
                "Produtos",
                "Total Ton.",
                "Status",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(False)
        self.table.itemSelectionChanged.connect(self._sync_details_from_selection)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        widths = [60, 150, 210, 110, 110, 110, 150, 220, 100, 180]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

        layout.addWidget(self.table)
        return panel

    def _build_details_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Detalhes do Agendamento")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.details_label = QLabel("Selecione um agendamento para ver os itens da carga.")
        self.details_label.setObjectName("MetaLabel")
        self.details_label.setWordWrap(True)
        layout.addWidget(self.details_label)

        internal_title = QLabel("Dados Internos")
        internal_title.setObjectName("PanelMinor")
        layout.addWidget(internal_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

        contato_label = QLabel("Contato do Cliente")
        contato_label.setObjectName("FieldLabel")
        self.contato_field = QLineEdit()
        self.contato_field.setObjectName("TextField")
        self.contato_field.setFixedHeight(46)
        self.contato_field.setPlaceholderText("Nome / telefone / e-mail")

        roteiro_label = QLabel("Roteiro")
        roteiro_label.setObjectName("FieldLabel")
        self.roteiro_field = QTextEdit()
        self.roteiro_field.setObjectName("TextField")
        self.roteiro_field.setFixedHeight(90)
        self.roteiro_field.setPlaceholderText("Observacoes internas e roteiro da viagem")

        grid.addWidget(contato_label, 0, 0)
        grid.addWidget(self.contato_field, 1, 0)
        grid.addWidget(roteiro_label, 2, 0)
        grid.addWidget(self.roteiro_field, 3, 0)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addStretch(1)

        save_internal_btn = QPushButton("Salvar Dados Internos")
        save_internal_btn.setObjectName("PrimaryButton")
        save_internal_btn.clicked.connect(self._save_internal_data)
        actions.addWidget(save_internal_btn)
        layout.addLayout(actions)

        self.details_text = QTextEdit()
        self.details_text.setObjectName("TextField")
        self.details_text.setReadOnly(True)
        self.details_text.setFixedHeight(150)
        layout.addWidget(self.details_text)
        return panel

    def reload_data(self):
        selected_id = self._selected_agendamento_id()
        self.all_records = listar_agendamentos()
        self._apply_filters(selected_id=selected_id)

    def refresh_theme(self):
        pass

    def _selected_agendamento_id(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return None
        return selected_items[0].data(Qt.UserRole)

    def _apply_filters(self, *_args, selected_id=None):
        self.records = self._filter_records(self.all_records)
        self.table.clearContents()
        self.table.setRowCount(len(self.records))

        for row_index, record in enumerate(self.records):
            self.table.setRowHeight(row_index, 42)
            values = [
                str(record.get("id", "")),
                self._format_datetime(record.get("created_at")),
                record.get("driver_name", ""),
                record.get("plate_cavalo", ""),
                record.get("loading_date", ""),
                record.get("supplier", ""),
                record.get("pedidos", ""),
                record.get("produtos", ""),
                self._format_tons(record.get("total_tons")),
                record.get("status", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(record.get("id", 0)))
                align = Qt.AlignCenter if col in {0, 1, 3, 4, 5, 8, 9} else Qt.AlignLeft
                item.setTextAlignment(Qt.AlignVCenter | align)
                self.table.setItem(row_index, col, item)

        if self.records:
            if selected_id is not None and self._select_agendamento(int(selected_id)):
                return
            self.table.selectRow(0)
            return

        search_term = self.search_field.text().strip()
        if search_term:
            self.details_label.setText("Nenhum agendamento encontrado para o filtro informado.")
        else:
            self.details_label.setText("Nenhum agendamento registrado ainda.")
        self.details_text.clear()
        self._clear_internal_fields()

    def _filter_records(self, records):
        term = self.search_field.text().strip().casefold()
        if not term:
            return list(records)

        filtered = []
        for record in records:
            searchable = " ".join(
                [
                    str(record.get("driver_name") or ""),
                    str(record.get("plate_cavalo") or ""),
                    str(record.get("clientes") or ""),
                    str(record.get("pedidos") or ""),
                    str(record.get("supplier") or ""),
                    str(record.get("loading_date") or ""),
                ]
            ).casefold()
            if term in searchable:
                filtered.append(record)
        return filtered

    def _sync_details_from_selection(self):
        agendamento_id = self._selected_agendamento_id()
        if agendamento_id is None:
            self.details_label.setText("Selecione um agendamento para ver os itens da carga.")
            self.details_text.clear()
            self._clear_internal_fields()
            return

        record = next((item for item in self.records if int(item.get("id", 0)) == int(agendamento_id)), None)
        if record is None:
            self.details_text.clear()
            self._clear_internal_fields()
            return

        self.status_combo.setCurrentText(record.get("status", STATUS_AGENDAMENTO[0]))
        self._fill_internal_fields(record)

        resumo = [
            f"Motorista: {record.get('driver_name', '-')}",
            f"Placa Cavalo: {record.get('plate_cavalo', '-')}",
            f"Data de Carga: {record.get('loading_date', '-')}",
            f"Clientes: {record.get('clientes', '-')}",
        ]
        self.details_label.setText(" | ".join(resumo))

        itens = listar_itens_agendamento(int(agendamento_id))
        linhas = []
        if record.get("roteiro"):
            linhas.append(f"Roteiro: {record.get('roteiro')}")
        if record.get("contato_cliente"):
            linhas.append(f"Contato do Cliente: {record.get('contato_cliente')}")
        if record.get("email_recipients"):
            linhas.append(f"E-mail enviado para: {record.get('email_recipients')}")
        if linhas and itens:
            linhas.append("")

        if not itens and not linhas:
            self.details_text.setPlainText("Nenhum item detalhado encontrado para este agendamento.")
            return

        for item in itens:
            linhas.append(
                f"Pedido {item.get('pedido', '-')}: {item.get('produto', '-')}"
                f" | Cliente: {item.get('cliente', '-')}"
                f" | Cidade: {item.get('cidade', '-')}"
                f" | Embalagem: {item.get('embalagem', '-')}"
                f" | Toneladas: {self._format_tons(item.get('toneladas'))}"
            )
        self.details_text.setPlainText("\n".join(linhas))

    def _save_selected_status(self):
        agendamento_id = self._selected_agendamento_id()
        if agendamento_id is None:
            QMessageBox.warning(self, "Agendamentos", "Selecione um agendamento para alterar o status.")
            return

        novo_status = self.status_combo.currentText()
        try:
            atualizar_status_agendamento(int(agendamento_id), novo_status)
        except Exception as exc:
            QMessageBox.critical(self, "Agendamentos", f"Nao foi possivel salvar o status.\n\n{exc}")
            return

        self.reload_data()
        self._select_agendamento(int(agendamento_id))
        QMessageBox.information(self, "Agendamentos", "Status atualizado com sucesso.")

    def _save_internal_data(self):
        agendamento_id = self._selected_agendamento_id()
        if agendamento_id is None:
            QMessageBox.warning(self, "Agendamentos", "Selecione um agendamento para salvar os dados internos.")
            return

        roteiro = self.roteiro_field.toPlainText().strip()
        contato_cliente = self.contato_field.text().strip()

        try:
            atualizar_dados_internos_agendamento(
                int(agendamento_id),
                roteiro=roteiro,
                contato_cliente=contato_cliente,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Agendamentos", f"Nao foi possivel salvar os dados internos.\n\n{exc}")
            return

        self.reload_data()
        self._select_agendamento(int(agendamento_id))
        QMessageBox.information(self, "Agendamentos", "Dados internos salvos com sucesso.")

    def _fill_internal_fields(self, record):
        self.contato_field.setText(str(record.get("contato_cliente") or "").strip())
        self.roteiro_field.setPlainText(str(record.get("roteiro") or "").strip())

    def _clear_internal_fields(self):
        self.contato_field.clear()
        self.roteiro_field.clear()

    def _select_agendamento(self, agendamento_id: int):
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item is not None and int(item.data(Qt.UserRole)) == int(agendamento_id):
                self.table.selectRow(row_index)
                return True
        return False

    def _format_datetime(self, value):
        text = str(value or "").strip()
        if not text:
            return "-"
        try:
            return datetime.fromisoformat(text).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return text

    def _format_tons(self, value):
        try:
            tons = float(value or 0)
        except (TypeError, ValueError):
            return "0"
        if tons.is_integer():
            return str(int(tons))
        return f"{tons:.3f}".rstrip("0").rstrip(".")
