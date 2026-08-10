from __future__ import annotations

import html
import os
import re
import smtplib
import subprocess
import traceback

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..servicos.agendamentos_db import registrar_agendamento_email
from ..servicos.comunicacao import send_email_message
from ..servicos.documentos import (
    criar_planilha_especifica_motorista_data,
    gerar_oc_docx,
    open_file_path,
)
from ..servicos.ocr import (
    extrair_dados_cnh_com_azure_api,
    extrair_dados_crlv_com_azure_api,
    obter_texto_do_arquivo_com_azure,
)
from ..shared import TEMPLATE_OC, TEMPLATE_OC_HERINGER, convert
from .widgets import ActionTile, MetricItem, apply_shadow


class _BaseScrollPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

    def _panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        apply_shadow(panel, blur=28, y_offset=9, alpha=52)
        return panel

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
            widget.setFixedHeight(90)
            wrapper.setMinimumHeight(118)
        else:
            widget = QLineEdit()
            widget.setFixedHeight(46)
            wrapper.setMinimumHeight(70)
        widget.setObjectName("TextField")
        widget.setPlaceholderText(placeholder)
        layout.addWidget(widget)
        return wrapper, widget


class OrdemColetaPage(_BaseScrollPage):
    agendamento_registrado = Signal()

    def __init__(self, contrato_page=None, clients_page=None, parent=None):
        super().__init__(parent)
        self.contrato_page = contrato_page
        self.clients_page = clients_page
        self.ultimo_pdf_gerado = None
        self.ultima_planilha_gerada = None
        self.ultimo_agendamento_id = None
        self.summary_values = {}

        layout = self.layout()
        layout.setSpacing(16)

        self.driver_panel = self._build_driver_vehicle_panel()
        self.actions_panel = self._build_actions_panel()

        layout.addWidget(self.driver_panel)
        layout.addWidget(self.actions_panel)
        layout.addStretch(1)

        if self.contrato_page is not None:
            self.contrato_page.state_changed.connect(self._sync_contract_state)

        self._sync_contract_state()

    def _build_driver_vehicle_panel(self):
        panel = self._panel()
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 14, 22, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Dados do Motorista e Veiculo")
        title.setObjectName("PanelTitle")
        dots = QLabel("...")
        dots.setObjectName("Dots")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(dots)
        layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        layout.addWidget(self._build_overview_strip())

        content = QHBoxLayout()
        content.setSpacing(24)
        content.addLayout(self._build_driver_column(), 1)

        middle_divider = QFrame()
        middle_divider.setObjectName("Divider")
        middle_divider.setFixedWidth(1)
        middle_divider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        content.addWidget(middle_divider)

        content.addLayout(self._build_vehicle_column(), 1)
        layout.addLayout(content)

        self.document_status = QLabel("Importe os documentos e revise os dados antes de gerar a O.C.")
        self.document_status.setObjectName("MetaLabel")
        self.document_status.setWordWrap(True)
        layout.addWidget(self.document_status)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.btn_import_cnh = self._build_import_button("Importar Dados da CNH", self._import_cnh)
        self.btn_import_crlv = self._build_import_button("Importar Dados do CRLV", self._import_crlv)
        buttons.addWidget(self.btn_import_cnh)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_import_crlv)
        layout.addLayout(buttons)
        panel.setMinimumHeight(panel.sizeHint().height())
        return panel

    def _build_driver_column(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        nome_box, self.entry_nome = self._field("Nome do Motorista", placeholder="Nome completo")
        cpf_box, self.entry_cpf = self._field("CPF", placeholder="000.000.000-00")
        cnh_box, self.entry_cnh = self._field("CNH", placeholder="Numero da CNH")
        fone_box, self.entry_fone = self._field("Telefone", placeholder="(00) 00000-0000")

        layout.addWidget(nome_box)
        layout.addWidget(cpf_box)
        layout.addWidget(cnh_box)
        layout.addWidget(fone_box)
        layout.addStretch(1)
        return layout

    def _build_vehicle_column(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        placa1_box, self.entry_placa1 = self._field("Placa Cavalo", placeholder="ABC1D23")
        placa2_box, self.entry_placa2 = self._field("Placa Carreta 1", placeholder="ABC1D23")
        placa3_box, self.entry_placa3 = self._field("Placa Carreta 2", placeholder="ABC1D23")

        layout.addWidget(placa1_box)
        layout.addWidget(placa2_box)
        layout.addWidget(placa3_box)
        layout.addStretch(1)
        return layout

    def _build_overview_strip(self):
        strip = QFrame()
        strip.setObjectName("MetricsBar")
        strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        strip.setMinimumHeight(68)
        strip.setMaximumHeight(68)

        layout = QHBoxLayout(strip)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(16)
        layout.addWidget(self._build_snapshot_value("Fornecedor", "supplier"), 1)
        layout.addWidget(self._build_snapshot_value("Data", "date"), 1)
        layout.addWidget(self._build_snapshot_value("Pedidos", "orders", accent=True), 1)
        layout.addWidget(self._build_snapshot_value("Produtos", "products", accent=True), 1)
        return strip

    def _build_snapshot_value(self, label_text, key, accent=False):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        label = QLabel(label_text)
        label.setObjectName("PanelMinor")

        value = QLabel("-")
        value.setObjectName("MetaValueAccent" if accent else "MetaValue")
        value.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(value)
        self.summary_values[key] = value
        return wrapper

    def _build_import_button(self, text, callback):
        button = QPushButton(text)
        button.setObjectName("SecondaryButton")
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(42)
        button.setMinimumWidth(210)
        button.clicked.connect(callback)
        return button

    def _build_metrics_bar(self):
        bar = QFrame()
        bar.setObjectName("MetricsBar")
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bar.setMinimumHeight(86)
        bar.setMaximumHeight(86)
        apply_shadow(bar, blur=18, y_offset=6, alpha=24)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(14)

        self.metric_loads = MetricItem("C", "0", "Cargas Selecionadas")
        self.metric_tons = MetricItem("T", "0", "Toneladas Totais", accent=True)
        self.metric_orders = MetricItem("P", "0", "Pedidos")
        self.metric_clients = MetricItem("U", "0", "Clientes Unicos")

        metrics = [self.metric_loads, self.metric_tons, self.metric_orders, self.metric_clients]
        for index, metric in enumerate(metrics):
            layout.addWidget(metric, 1)
            if index < len(metrics) - 1:
                divider = QFrame()
                divider.setObjectName("Divider")
                divider.setFixedHeight(48)
                layout.addWidget(divider)
        return bar

    def _build_actions_panel(self):
        panel = self._panel()
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(12)

        title = QLabel("Acoes Operacionais")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.action_status = QLabel("Aguardando dados da aba CONTRATO para gerar a ordem de coleta.")
        self.action_status.setObjectName("MetaLabel")
        self.action_status.setWordWrap(True)
        layout.addWidget(self.action_status)

        row = QHBoxLayout()
        row.setSpacing(14)

        generate = ActionTile("+", "Gerar Ordem de Coleta", variant="primary")
        email = ActionTile("@", "Enviar O.C. por E-mail", variant="secondary")
        clear = ActionTile("X", "Limpar os Campos", variant="secondary")

        generate.clicked.connect(self._generate_oc)
        email.clicked.connect(self._send_oc_email)
        clear.clicked.connect(self._clear_fields)

        row.addWidget(generate, 1)
        row.addWidget(email, 1)
        row.addWidget(clear, 1)
        layout.addLayout(row)
        panel.setMinimumHeight(panel.sizeHint().height())
        return panel

    def _selected_contracts(self):
        if self.contrato_page is None:
            return []
        getter = getattr(self.contrato_page, "get_selected_contracts", None)
        if callable(getter):
            return getter()
        return []

    def _current_loading_date(self):
        if self.contrato_page is None:
            return ""
        getter = getattr(self.contrato_page, "get_loading_date", None)
        if callable(getter):
            return getter()
        return ""

    def _current_supplier(self):
        if self.contrato_page is None:
            return "Fertimax"
        getter = getattr(self.contrato_page, "get_supplier", None)
        if callable(getter):
            return getter()
        return "Fertimax"

    def _sync_contract_state(self):
        selected = self._selected_contracts()
        supplier = self._current_supplier()
        loading_date = self._current_loading_date()

        total_tons = sum(self._safe_ton(item.get("toneladas")) for item in selected)
        orders = sorted({str(item.get("contrato", "")).strip() for item in selected if str(item.get("contrato", "")).strip()})
        products = sorted({str(item.get("produto", "")).strip() for item in selected if str(item.get("produto", "")).strip()})
        clients = sorted({str(item.get("cliente", "")).strip() for item in selected if str(item.get("cliente", "")).strip()})

        self.summary_values["supplier"].setText(supplier or "-")
        self.summary_values["date"].setText(loading_date or "-")
        self.summary_values["orders"].setText(str(len(orders)))
        self.summary_values["products"].setText(str(len(products)))

        if not selected:
            self.document_status.setText("Nenhum contrato selecionado na aba CONTRATO.")
            self.action_status.setText("Selecione os contratos na aba CONTRATO para gerar a ordem de coleta.")
            return

        preview_lines = []
        for item in selected[:3]:
            pedido = str(item.get("contrato", "")).strip() or "-"
            produto = str(item.get("produto", "")).strip() or "Produto sem nome"
            toneladas = self._format_ton_value(self._safe_ton(item.get("toneladas")))
            cidade = str(item.get("cidade", "")).strip()
            suffix = f" | {cidade}" if cidade else ""
            preview_lines.append(f"Pedido {pedido} - {produto} - {toneladas} t{suffix}")
        if len(selected) > 3:
            preview_lines.append(f"... e mais {len(selected) - 3} item(ns)")
        self.document_status.setText(" | ".join(preview_lines))
        self.action_status.setText(
            f"{len(selected)} item(ns) pronto(s) para O.C. em {loading_date or 'sem data'} - fornecedor {supplier}."
        )

    def _import_cnh(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o PDF ou imagem da CNH",
            "",
            "Arquivos de CNH (*.pdf *.jpg *.jpeg *.png *.bmp);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        try:
            text = obter_texto_do_arquivo_com_azure(file_path)
            data = extrair_dados_cnh_com_azure_api(text)
        except Exception as exc:
            QMessageBox.critical(self, "Erro na CNH", f"Nao foi possivel ler a CNH.\n\n{exc}")
            return

        if not data:
            QMessageBox.warning(self, "CNH", "Nenhum dado foi extraido da CNH selecionada.")
            return

        self.entry_nome.setText(self._clean_ocr_value(data.get("nome")))
        self.entry_cpf.setText(self._clean_ocr_value(data.get("cpf")))
        self.entry_cnh.setText(self._clean_ocr_value(data.get("numero")))
        self.document_status.setText(f"CNH importada com sucesso de {os.path.basename(file_path)}.")

    def _import_crlv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o PDF ou imagem do CRLV",
            "",
            "Arquivos de CRLV (*.pdf *.jpg *.jpeg *.png *.bmp);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        try:
            text = obter_texto_do_arquivo_com_azure(file_path)
            data = extrair_dados_crlv_com_azure_api(text)
        except Exception as exc:
            QMessageBox.critical(self, "Erro no CRLV", f"Nao foi possivel ler o CRLV.\n\n{exc}")
            return

        if not data:
            QMessageBox.warning(self, "CRLV", "Nenhum dado foi extraido do CRLV selecionado.")
            return

        plate = self._clean_ocr_value(data.get("placa"))
        categoria = self._clean_ocr_value(data.get("categoria_veiculo")).upper()
        if not plate:
            QMessageBox.warning(self, "CRLV", "Nenhuma placa foi encontrada no documento.")
            return

        if categoria in {"CAVALO", "TRUCK"}:
            self.entry_placa1.setText(plate)
            destino = "Placa Cavalo"
        elif not self.entry_placa2.text().strip():
            self.entry_placa2.setText(plate)
            destino = "Placa Carreta 1"
        else:
            self.entry_placa3.setText(plate)
            destino = "Placa Carreta 2"

        self.document_status.setText(f"CRLV importado com sucesso para o campo {destino}.")

    def _generate_oc(self):
        products = self._selected_contracts()
        if not products:
            QMessageBox.warning(self, "Ordem de Coleta", "Selecione os contratos na aba CONTRATO antes de gerar a O.C.")
            return

        driver_name = self.entry_nome.text().strip()
        if not driver_name:
            QMessageBox.warning(self, "Ordem de Coleta", "O nome do motorista e obrigatorio.")
            return

        supplier = self._current_supplier()
        loading_date = self._current_loading_date()
        template_path = TEMPLATE_OC_HERINGER if supplier == "Heringer" else TEMPLATE_OC
        file_prefix = "OC_Heringer_" if supplier == "Heringer" else "OC_"

        safe_name = re.sub(r'[\\/*?:"<>|]', "", driver_name) or "Motorista"
        default_name = f"{file_prefix}{safe_name}.docx"
        save_path_docx, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Ordem de Coleta",
            default_name,
            "Documento do Word (*.docx)",
        )
        if not save_path_docx:
            return
        if not save_path_docx.lower().endswith(".docx"):
            save_path_docx += ".docx"

        save_path_pdf = os.path.splitext(save_path_docx)[0] + ".pdf"

        try:
            gerar_oc_docx(
                template_path,
                save_path_docx,
                products,
                self.entry_cpf.text().strip(),
                driver_name,
                self.entry_cnh.text().strip(),
                self.entry_fone.text().strip(),
                self.entry_placa1.text().strip(),
                self.entry_placa2.text().strip(),
                self.entry_placa3.text().strip(),
                loading_date,
            )

            subprocess.run(
                ["taskkill", "/F", "/IM", "WINWORD.EXE"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            convert(save_path_docx, save_path_pdf)

            self.ultimo_pdf_gerado = save_path_pdf
            self.ultima_planilha_gerada = None

            if supplier != "Heringer":
                excel_name = f"Autorizacao de carregamento {safe_name}.xlsx"
                excel_path = os.path.join(os.path.dirname(save_path_docx), excel_name)
                criar_planilha_especifica_motorista_data(
                    excel_path,
                    products,
                    loading_date,
                    driver_name,
                    self.entry_placa1.text().strip(),
                )
                self.ultima_planilha_gerada = excel_path

            open_file_path(save_path_pdf)
            self.action_status.setText(f"O.C. gerada com sucesso: {os.path.basename(save_path_pdf)}")
            QMessageBox.information(self, "Sucesso", "Ordem de coleta gerada com sucesso.")
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(self, "Erro ao gerar O.C.", f"Nao foi possivel gerar a ordem de coleta.\n\n{exc}")

    def _send_oc_email(self):
        if not self.ultimo_pdf_gerado or not os.path.exists(self.ultimo_pdf_gerado):
            QMessageBox.warning(self, "Enviar O.C.", "Gere a ordem de coleta antes de enviar o e-mail.")
            return

        supplier = self._current_supplier()
        if supplier == "Heringer":
            recipients = [
                "expedicao.candeias@heringer.com.br",
                "faturamento.candeias@heringer.com.br",
            ]
        else:
            recipients = [
                "agendamento@fertimaxi.com.br",
                "luan.santos@fertimaxi.com.br",
                "paulo.moura@fertimaxi.com.br",
            ]

        driver_name = self.entry_nome.text().strip() or "Motorista"
        placa_cavalo = self.entry_placa1.text().strip() or "N/A"
        loading_date = self._current_loading_date()
        client_context = self._current_client_context()
        roteiro = client_context["roteiro"]
        localizador = client_context["localizador"]
        contato_cliente = client_context["contato_cliente"]
        subject = f"Autorizacao de {driver_name} - Placa {placa_cavalo}"

        detail_blocks = []
        if roteiro:
            detail_blocks.append(f"<p><b>Roteiro:</b><br>{self._to_html_lines(roteiro)}</p>")
        if contato_cliente:
            detail_blocks.append(f"<p><b>Contato do Cliente:</b> {self._to_html_lines(contato_cliente)}</p>")

        body = f"""
        <html><body>
        <p>Favor agendar motorista para {html.escape(loading_date)}.</p>
        {''.join(detail_blocks)}
        <p>Atenciosamente,<br><b>Setor - Expedicao</b><br>ATLANTICO FERTLOG SERVICOS & TRANSPORTES</p>
        </body></html>
        """

        attachments = [self.ultimo_pdf_gerado]
        if self.ultima_planilha_gerada and os.path.exists(self.ultima_planilha_gerada):
            attachments.append(self.ultima_planilha_gerada)

        try:
            send_email_message(recipients, subject, body, attachments)
        except smtplib.SMTPAuthenticationError:
            QMessageBox.critical(
                self,
                "Erro de autenticacao",
                "Nao foi possivel fazer login no servidor SMTP. Verifique a senha de app configurada.",
            )
            return
        except Exception as exc:
            QMessageBox.critical(self, "Erro de envio", f"Nao foi possivel enviar o e-mail.\n\n{exc}")
            return

        try:
            agendamento_id = registrar_agendamento_email(
                {
                    "supplier": supplier,
                    "loading_date": loading_date,
                    "driver_name": driver_name,
                    "driver_cpf": self.entry_cpf.text().strip(),
                    "driver_phone": self.entry_fone.text().strip(),
                    "cnh": self.entry_cnh.text().strip(),
                    "plate_cavalo": placa_cavalo,
                    "plate_carreta1": self.entry_placa2.text().strip(),
                    "plate_carreta2": self.entry_placa3.text().strip(),
                    "roteiro": roteiro,
                    "localizador": localizador,
                    "contato_cliente": contato_cliente,
                    "email_subject": subject,
                    "email_recipients": recipients,
                    "oc_pdf_path": self.ultimo_pdf_gerado,
                    "planilha_path": self.ultima_planilha_gerada or "",
                    "items": self._selected_contracts(),
                }
            )
            self.ultimo_agendamento_id = agendamento_id
            self.action_status.setText(
                f"E-mail enviado e agendamento #{agendamento_id} registrado no banco."
            )
            self.agendamento_registrado.emit()
            QMessageBox.information(
                self,
                "Sucesso",
                f"E-mail enviado com sucesso.\n\nAgendamento #{agendamento_id} salvo no banco.",
            )
        except Exception as exc:
            traceback.print_exc()
            self.action_status.setText("E-mail enviado, mas houve erro ao registrar o agendamento no banco.")
            QMessageBox.warning(
                self,
                "E-mail enviado com ressalva",
                f"O e-mail foi enviado, mas nao foi possivel gravar o agendamento no banco.\n\n{exc}",
            )

    def _clear_fields(self):
        for field in [
            self.entry_nome,
            self.entry_cpf,
            self.entry_cnh,
            self.entry_fone,
            self.entry_placa1,
            self.entry_placa2,
            self.entry_placa3,
        ]:
            field.clear()

        self.ultimo_pdf_gerado = None
        self.ultima_planilha_gerada = None
        self.document_status.setText("Campos limpos. Importe novamente CNH e CRLV se necessario.")
        self._sync_contract_state()

    def refresh_theme(self):
        pass

    def _safe_ton(self, value):
        try:
            if value in ("", None):
                return 0.0
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    def _format_ton_value(self, value):
        if not value:
            return "0"
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.1f}".rstrip("0").rstrip(".")

    def _clean_ocr_value(self, value):
        text = str(value or "").strip()
        lowered = text.lower()
        if lowered in {"nao encontrado", "não encontrado", "nao encontrada", "não encontrada"}:
            return ""
        return text


    def _current_client_context(self):
        if self.clients_page is None:
            return {
                "roteiro": "",
                "localizador": "",
                "contato_cliente": "",
            }

        getter = getattr(self.clients_page, "get_route_details", None)
        if not callable(getter):
            return {
                "roteiro": "",
                "localizador": "",
                "contato_cliente": "",
            }

        details = getter() or {}
        return {
            "roteiro": str(details.get("roteiro") or "").strip(),
            "localizador": str(details.get("localizador") or "").strip(),
            "contato_cliente": str(details.get("contato_cliente") or "").strip(),
        }

    def _to_html_lines(self, value):
        return html.escape(str(value or "").strip()).replace("\n", "<br>")


class CartaFretePage(_BaseScrollPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = self.layout()
        layout.addWidget(self._build_fields_panel())
        layout.addWidget(self._build_delivery_panel())
        layout.addStretch(1)

    def _build_fields_panel(self):
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Carta Frete")
        title.setObjectName("PanelTitle")
        subtitle = QLabel("Geracao e envio da autorizacao de abastecimento.")
        subtitle.setObjectName("MetaLabel")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)

        value_box, self.valor_field = self._field("Valor do Frete (R$)", placeholder="0,00")
        cte_box, self.cte_field = self._field("Numero do CTe", placeholder="000000")
        email_box, self.email_field = self._field(
            "E-mails (separados por virgula)",
            multiline=True,
            placeholder="financeiro@atlanticofertlog.com.br, ...",
        )

        grid.addWidget(value_box, 0, 0)
        grid.addWidget(cte_box, 0, 1)
        grid.addWidget(email_box, 1, 0, 1, 2)
        layout.addLayout(grid)
        return panel

    def _build_delivery_panel(self):
        panel = self._panel()
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)

        title = QLabel("Acoes Operacionais")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(14)

        generate = ActionTile("+", "Gerar Carta Frete", variant="primary")
        send = ActionTile("@", "Enviar por E-mail", variant="secondary")
        correction = ActionTile(">", "Enviar Correcao", variant="secondary")

        generate.clicked.connect(lambda: self._show_info("Gerar Carta Frete"))
        send.clicked.connect(lambda: self._show_info("Enviar Carta Frete"))
        correction.clicked.connect(lambda: self._show_info("Enviar Correcao"))

        row.addWidget(generate, 1)
        row.addWidget(send, 1)
        row.addWidget(correction, 1)
        layout.addLayout(row)
        return panel

    def _show_info(self, action):
        QMessageBox.information(self, action, f"A acao '{action}' sera ligada a logica PySide desta pagina.")
