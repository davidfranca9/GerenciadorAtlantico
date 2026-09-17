from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


STATUS_AGENDAMENTO = (
    "Aguardando Agendamento",
    "Agendado",
    "Cancelado",
    "Carregou",
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="user")  # "user" | "admin"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    paginas_bloqueadas: Mapped[str] = mapped_column(String(1000), default="")  # rotas (ex: "/pedidos,/whatsapp") escondidas pro usuario
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(255), index=True)
    cnpj_cpf: Mapped[str] = mapped_column(String(32), default="")
    cidade: Mapped[str] = mapped_column(String(255), default="")
    uf: Mapped[str] = mapped_column(String(2), default="")
    contato: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    telefone: Mapped[str] = mapped_column(String(64), default="")
    roteiro: Mapped[str] = mapped_column(String(2000), default="")
    observacoes: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Cidade(Base):
    __tablename__ = "cidades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(255), index=True)
    uf: Mapped[str] = mapped_column(String(2), index=True)
    ibge: Mapped[str] = mapped_column(String(16), default="")


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(40), default=STATUS_AGENDAMENTO[0])
    supplier: Mapped[str] = mapped_column(String(255), default="")
    # loading_date = data solicitada (o que pedimos ao fornecedor).
    # data_agendada = data confirmada por ele, que nem sempre e a mesma e
    # costuma chegar depois, por e-mail.
    loading_date: Mapped[str] = mapped_column(String(32), default="")
    data_agendada: Mapped[str] = mapped_column(String(32), default="")
    agendamento_confirmado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    agendamento_confirmado_por: Mapped[str] = mapped_column(String(255), default="")
    driver_name: Mapped[str] = mapped_column(String(255), default="")
    driver_cpf: Mapped[str] = mapped_column(String(32), default="")
    driver_phone: Mapped[str] = mapped_column(String(64), default="")
    cnh: Mapped[str] = mapped_column(String(64), default="")
    plate_cavalo: Mapped[str] = mapped_column(String(16), default="")
    plate_carreta1: Mapped[str] = mapped_column(String(16), default="")
    plate_carreta2: Mapped[str] = mapped_column(String(16), default="")
    # Carroceria que a Fertimaxi pede na autorizacao: GRANELEIRO, GRADE BAIXA, SIDER.
    modelo_veiculo: Mapped[str] = mapped_column(String(40), default="")
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    total_tons: Mapped[float] = mapped_column(Float, default=0)
    pedidos: Mapped[str] = mapped_column(String(2000), default="")
    clientes: Mapped[str] = mapped_column(String(2000), default="")
    produtos: Mapped[str] = mapped_column(String(2000), default="")
    roteiro: Mapped[str] = mapped_column(String(2000), default="")
    localizador: Mapped[str] = mapped_column(String(255), default="")
    contato_cliente: Mapped[str] = mapped_column(String(255), default="")
    email_subject: Mapped[str] = mapped_column(String(500), default="")
    email_recipients: Mapped[str] = mapped_column(String(1000), default="")
    oc_pdf_path: Mapped[str] = mapped_column(String(500), default="")
    planilha_path: Mapped[str] = mapped_column(String(500), default="")
    observacoes: Mapped[str] = mapped_column(String(2000), default="")

    itens: Mapped[list["AgendamentoItem"]] = relationship(
        back_populates="agendamento", cascade="all, delete-orphan"
    )
    emails: Mapped[list["AgendamentoEmail"]] = relationship(
        back_populates="agendamento", cascade="all, delete-orphan", order_by="AgendamentoEmail.created_at"
    )
    # Message-ID dos e-mails que sairam deste agendamento, separados por
    # espaco: a resposta da fabrica cita um deles e e assim que ela e ligada.
    email_message_ids: Mapped[str] = mapped_column(Text, default="")
    respostas: Mapped[list["RespostaFabrica"]] = relationship(
        back_populates="agendamento", cascade="all, delete-orphan", order_by="RespostaFabrica.recebido_em"
    )


class AgendamentoItem(Base):
    __tablename__ = "agendamento_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agendamento_id: Mapped[int] = mapped_column(ForeignKey("agendamentos.id", ondelete="CASCADE"))
    pedido: Mapped[str] = mapped_column(String(255), default="")
    cliente: Mapped[str] = mapped_column(String(255), default="")
    produto: Mapped[str] = mapped_column(String(255), default="")
    cidade: Mapped[str] = mapped_column(String(255), default="")
    embalagem: Mapped[str] = mapped_column(String(255), default="")
    toneladas: Mapped[float] = mapped_column(Float, default=0)
    pedido_ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)

    agendamento: Mapped[Agendamento] = relationship(back_populates="itens")


class AgendamentoEmail(Base):
    """E-mail de inclusao ou substituicao de motorista enviado pra fabrica.

    Fica como historico: quem entrou, quem saiu, pra quem foi e se foi teste.
    """

    __tablename__ = "agendamento_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agendamento_id: Mapped[int] = mapped_column(ForeignKey("agendamentos.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="")  # inclusao | substituicao
    assunto: Mapped[str] = mapped_column(String(500), default="")
    destinatarios: Mapped[str] = mapped_column(String(1000), default="")
    teste: Mapped[bool] = mapped_column(Boolean, default=False)
    motorista: Mapped[str] = mapped_column(String(255), default="")
    motorista_anterior: Mapped[str] = mapped_column(String(255), default="")
    enviado_por: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agendamento: Mapped[Agendamento] = relationship(back_populates="emails")


class RespostaFabrica(Base):
    """Resposta da fabrica a um e-mail de agendamento, lida da caixa.

    Confirmou (com data) -> o agendamento vira Agendado sozinho. Perguntou
    ("confirma?") ou apontou problema -> so aparece na tela. Uma resposta que
    nao deu pra ligar a um agendamento fica gravada sem ele, so pra nao ser
    lida de novo.
    """

    __tablename__ = "respostas_fabrica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(500), index=True)
    agendamento_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agendamentos.id", ondelete="CASCADE"), nullable=True, index=True
    )
    conversa: Mapped[str] = mapped_column(String(40), default="")  # X-GM-THRID do Gmail
    recebido_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remetente: Mapped[str] = mapped_column(String(255), default="")
    assunto: Mapped[str] = mapped_column(String(500), default="")
    texto: Mapped[str] = mapped_column(String(4000), default="")
    tipo: Mapped[str] = mapped_column(String(20), default="outro")  # confirmado | aguardando | problema | outro
    data: Mapped[str] = mapped_column(String(10), default="")  # dd/mm/aaaa
    como_ligou: Mapped[str] = mapped_column(String(20), default="")  # resposta | horario | conversa
    aplicada: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agendamento: Mapped[Optional[Agendamento]] = relationship(back_populates="respostas")


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    contrato: Mapped[str] = mapped_column(String(255), default="")
    produto: Mapped[str] = mapped_column(String(255), default="")
    embalagem: Mapped[str] = mapped_column(String(255), default="")
    cidade: Mapped[str] = mapped_column(String(255), default="")
    cliente: Mapped[str] = mapped_column(String(255), default="")
    supplier: Mapped[str] = mapped_column(String(20), default="AFL")
    toneladas_total: Mapped[float] = mapped_column(Float, default=0)
    toneladas_usadas: Mapped[float] = mapped_column(Float, default=0)
    # Quando a leitura do PDF nao decide a cidade (nenhuma ou mais de uma),
    # as possiveis ficam aqui em JSON ("Nome-UF") pra tela sugerir. Antes
    # elas eram descartadas e o pedido ficava sem cidade, calado.
    cidades_candidatas: Mapped[str] = mapped_column(String(1000), default="")
    # Pedido com todo o saldo agendado continua na lista, marcado como
    # carregamento fechado. Sai so quando alguem tira na mao (enquanto o
    # sistema nao sabe sozinho que tudo ja carregou).
    retirado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)


class WhatsAppMensagem(Base):
    __tablename__ = "whatsapp_mensagens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(32), index=True)
    direcao: Mapped[str] = mapped_column(String(10))  # "entrada" | "saida"
    tipo: Mapped[str] = mapped_column(String(20), default="texto")  # "texto" | "documento" | "imagem"
    conteudo: Mapped[str] = mapped_column(String(4000), default="")
    nome_arquivo: Mapped[str] = mapped_column(String(255), default="")
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    midia: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="")  # "" | "erro" | "enviada"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WhatsAppContato(Base):
    __tablename__ = "whatsapp_contatos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CotacaoFrete(Base):
    __tablename__ = "cotacoes_frete"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_cotacao: Mapped[str] = mapped_column(String(32))
    destino: Mapped[str] = mapped_column(String(255), index=True)
    fabrica: Mapped[str] = mapped_column(String(255), default="")
    valor_tonelada: Mapped[float] = mapped_column(Float)
    cliente_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    cliente_nome: Mapped[str] = mapped_column(String(255), default="")
    observacoes: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


STATUS_OPERACAO_FISCAL = (
    "RASCUNHO",
    "ENVIANDO_CTE",
    "CTE_CRIADO",
    "CTE_PROCESSANDO",
    "CTE_AUTORIZADO",
    "CTE_REJEITADO",
    "CRIANDO_CONTRATO",
    "CONTRATO_CRIADO",
    "CIOT_PROCESSANDO",
    "CIOT_AUTORIZADO",
    "CIOT_REJEITADO",
    "MDFE_PROCESSANDO",
    "MDFE_AUTORIZADO",
    "MDFE_REJEITADO",
    "ENCERRADO",
    "CANCELADO",
)


class OperacaoFiscal(Base):
    """Uma operacao fiscal completa (NF-e -> CT-e -> contrato de frete ->
    CIOT -> MDF-e) de um agendamento, com o estado e o rastro de auditoria.

    A unicidade e por (agendamento + chave da NF-e): e o que impede emitir
    dois CT-e para a mesma carga em caso de clique duplo ou retry."""

    __tablename__ = "operacoes_fiscais"
    __table_args__ = (UniqueConstraint("agendamento_id", "chave_nfe", name="uq_operacao_agendamento_nfe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agendamento_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="RASCUNHO", index=True)

    # Execucao: quem de fato transporta muda as regras de CIOT.
    tipo_execucao: Mapped[str] = mapped_column(String(20), default="")  # "terceiro" | "frota_propria"
    categoria_transportador: Mapped[str] = mapped_column(String(10), default="")  # TAC | ETC | CTC

    # NF-e da carga
    chave_nfe: Mapped[str] = mapped_column(String(44), default="")
    cod_nfe_bsoft: Mapped[str] = mapped_column(String(32), default="")

    # CT-e
    cod_conhecimento_bsoft: Mapped[str] = mapped_column(String(32), default="")
    cte_numero: Mapped[str] = mapped_column(String(32), default="")
    cte_chave: Mapped[str] = mapped_column(String(44), default="")
    cte_protocolo: Mapped[str] = mapped_column(String(64), default="")
    cte_motivo_rejeicao: Mapped[str] = mapped_column(String(500), default="")

    # Contrato de frete / CIOT
    contrato_frete_id_bsoft: Mapped[str] = mapped_column(String(32), default="")
    ciot: Mapped[str] = mapped_column(String(30), default="")
    ciot_status_operadora: Mapped[str] = mapped_column(String(40), default="")
    operadora_credito: Mapped[str] = mapped_column(String(80), default="")

    # MDF-e
    mdfe_id_bsoft: Mapped[str] = mapped_column(String(32), default="")
    mdfe_chave: Mapped[str] = mapped_column(String(44), default="")

    # Auditoria
    ultimo_payload: Mapped[str] = mapped_column(String(4000), default="")
    ultima_resposta: Mapped[str] = mapped_column(String(4000), default="")
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[str] = mapped_column(String(1000), default="")
    solicitado_por: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CartaFreteEnviada(Base):
    __tablename__ = "cartas_frete_enviadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[str] = mapped_column(String(32), default="")
    condutor: Mapped[str] = mapped_column(String(255), default="")
    cpf: Mapped[str] = mapped_column(String(32), default="")
    placa_cavalo: Mapped[str] = mapped_column(String(16), default="")
    valor_frete: Mapped[str] = mapped_column(String(32), default="")
    autorizacao_num: Mapped[str] = mapped_column(String(64), default="")
    destinatarios: Mapped[str] = mapped_column(String(500), default="")
    # agendada | enviando | enviada | erro | cancelada
    status: Mapped[str] = mapped_column(String(20), default="")
    # Envio agendado: guarda os DADOS (JSON), nao o arquivo - o documento e
    # gerado na hora de mandar. Horarios em UTC, como o resto do banco.
    agendada_para: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    enviada_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dados: Mapped[str] = mapped_column(Text, default="")
    erro: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EstadoSefaz(Base):
    """Onde a leitura da SEFAZ parou.

    O servico de distribuicao entrega documentos por NSU, um contador
    sequencial. Pedir desde o zero e recusado como "consumo indevido" e
    ainda bloqueia por uma hora, entao onde paramos precisa sobreviver a
    reinicio e a deploy - dai estar no banco e nao em memoria.
    """

    __tablename__ = "estado_sefaz"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True)
    ultimo_nsu: Mapped[str] = mapped_column(String(15), default="0")
    maximo_nsu: Mapped[str] = mapped_column(String(15), default="0")
    ultima_consulta: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ultimo_status: Mapped[str] = mapped_column(String(200), default="")
    documentos_baixados: Mapped[int] = mapped_column(Integer, default=0)


class NotaFiscalRecebida(Base):
    """NF-e disponivel pra virar CT-e, venha de onde vier.

    Duas fontes alimentam esta tabela: o anexo do e-mail do fornecedor
    (chega na hora, quando ele manda) e a esteira da SEFAZ (de hora em
    hora, pega o que ninguem mandou). A chave e unica, entao a mesma nota
    chegando pelos dois caminhos nao duplica.
    """

    __tablename__ = "notas_fiscais_recebidas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(44), unique=True, index=True)
    origem: Mapped[str] = mapped_column(String(20), default="sefaz")  # sefaz | email
    numero: Mapped[str] = mapped_column(String(20), default="")
    serie: Mapped[str] = mapped_column(String(10), default="")
    emissao: Mapped[str] = mapped_column(String(10), default="")
    emitente_nome: Mapped[str] = mapped_column(String(255), default="")
    destinatario_nome: Mapped[str] = mapped_column(String(255), default="")
    municipio_destino: Mapped[str] = mapped_column(String(120), default="")
    uf_destino: Mapped[str] = mapped_column(String(2), default="")
    valor_nota: Mapped[str] = mapped_column(String(20), default="")
    peso_bruto: Mapped[str] = mapped_column(String(20), default="")
    destinatario_doc: Mapped[str] = mapped_column(String(14), default="")
    xml: Mapped[str] = mapped_column(Text, default="")
    tem_cte: Mapped[bool] = mapped_column(Boolean, default=False)
    cte_numero: Mapped[str] = mapped_column(String(20), default="")
    # Casamento com o agendamento, feito sozinho quando so um encaixa.
    # `casamento` guarda o motivo - tanto do sim quanto do nao - pra tela
    # explicar em vez de so mostrar um campo vazio.
    agendamento_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    casamento: Mapped[str] = mapped_column(String(300), default="")
    # O que aconteceu na tentativa de rascunho automatico (ver
    # servicos/rascunho_automatico.py): vazio = nao tentou.
    rascunho_resultado: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------
# Financeiro: caixa dos bancos, resultado dos carregamentos e contas a pagar.
# Substitui as planilhas "Fluxo Caixa" e "Controle de carregamentos".
# Dinheiro em Numeric (centavo exato no banco), lido como float.
# --------------------------------------------------------------------------

def _dinheiro():
    return Numeric(14, 2, asdecimal=False)


class ContaBancaria(Base):
    __tablename__ = "contas_bancarias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))  # "Nubank"
    instituicao: Mapped[str] = mapped_column(String(120), default="")  # "Nu Pagamentos"
    cor: Mapped[str] = mapped_column(String(9), default="")
    # Saldo no COMECO do dia `saldo_inicial_em`: lancamentos desse dia em
    # diante mexem no saldo; os de antes sao historia (ja estao nele).
    saldo_inicial: Mapped[float] = mapped_column(_dinheiro(), default=0)
    saldo_inicial_em: Mapped[date] = mapped_column(Date)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LancamentoCaixa(Base):
    __tablename__ = "lancamentos_caixa"
    # O mesmo FITID do extrato (ou a mesma linha da planilha) nao entra duas vezes.
    __table_args__ = (UniqueConstraint("conta_id", "id_externo", name="uq_lancamento_conta_externo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas_bancarias.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(10))  # entrada | saida
    forma: Mapped[str] = mapped_column(String(20), default="OUTRO")  # PIX, TRANSFERENCIA, BOLETO...
    descricao: Mapped[str] = mapped_column(String(255), default="")
    valor: Mapped[float] = mapped_column(_dinheiro())  # sempre positivo; o tipo da o sinal
    # Transferencia entre contas proprias: o mesmo codigo nas duas pontas.
    transferencia: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    origem: Mapped[str] = mapped_column(String(20), default="manual")  # manual | planilha | extrato | agenda
    id_externo: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    criado_por: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MetaMensal(Base):
    __tablename__ = "metas_mensais"

    competencia: Mapped[str] = mapped_column(String(7), primary_key=True)  # "2026-09"
    meta_toneladas: Mapped[float] = mapped_column(Float, default=0)


class CarregamentoFinanceiro(Base):
    """Uma linha da aba LUCRO BRUTO: quanto a carga rendeu.

    Cada parte do frete pode vir por tonelada (multiplica pelo peso) ou ja
    como total fechado - o total, quando existe, manda."""

    __tablename__ = "carregamentos_financeiros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competencia: Mapped[str] = mapped_column(String(7), index=True)
    ctes: Mapped[str] = mapped_column(String(120), default="")
    data_emissao: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    motorista: Mapped[str] = mapped_column(String(255), default="")
    fabrica: Mapped[str] = mapped_column(String(120), default="")
    destino: Mapped[str] = mapped_column(String(160), default="")
    contratante: Mapped[str] = mapped_column(String(120), default="")
    peso: Mapped[float] = mapped_column(Float, default=0)
    frete_empresa_ton: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    frete_empresa_total: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    frete_motorista_ton: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    frete_motorista_total: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    agenciamento_ton: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    agenciamento_total: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    comissao_ton: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    comissao_total: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    cancelado: Mapped[bool] = mapped_column(Boolean, default=False)
    observacao: Mapped[str] = mapped_column(String(500), default="")
    # manual | planilha | bsoft. A do Bsoft e atualizada sozinha; as outras
    # nunca tem valor trocado pela sincronizacao.
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    cliente: Mapped[str] = mapped_column(String(255), default="")
    contrato_frete: Mapped[str] = mapped_column(String(40), default="")
    # Valor do contrato de frete no Bsoft. So referencia: em setembro/2026 nao
    # bateu com o pago ao motorista em nenhuma carga (a carta frete bateu).
    valor_contrato_frete: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Despesa(Base):
    """Conta fixa do mes (abas GASTOS EMPRESA / GASTOS PESSOAIS).

    Parcelada: `parcela_inicial` e a parcela de `competencia_inicio`; nos
    meses seguintes a parcela anda sozinha e some depois da ultima."""

    __tablename__ = "despesas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    escopo: Mapped[str] = mapped_column(String(10), index=True)  # empresa | pessoal
    grupo: Mapped[str] = mapped_column(String(80), default="")
    descricao: Mapped[str] = mapped_column(String(160))
    dia_vencimento: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valor: Mapped[float] = mapped_column(_dinheiro(), default=0)
    parcela_inicial: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parcelas_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    competencia_inicio: Mapped[str] = mapped_column(String(7))
    # Entra no "lucro real" do mes. Seguros e Buonny, por exemplo, so
    # entram na precificacao do CT-e.
    conta_no_resultado: Mapped[bool] = mapped_column(Boolean, default=True)
    entra_precificacao: Mapped[bool] = mapped_column(Boolean, default=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContaAvulsa(Base):
    """Pagamento que nao se repete: posto, cheque, acerto."""

    __tablename__ = "contas_avulsas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    escopo: Mapped[str] = mapped_column(String(10), default="empresa")
    data: Mapped[date] = mapped_column(Date, index=True)
    descricao: Mapped[str] = mapped_column(String(160))
    valor: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)  # vazio = valor a definir
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PagamentoAgenda(Base):
    __tablename__ = "pagamentos_agenda"
    __table_args__ = (UniqueConstraint("origem", "origem_id", "competencia", name="uq_pagamento_agenda"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origem: Mapped[str] = mapped_column(String(10))  # despesa | avulsa
    origem_id: Mapped[int] = mapped_column(Integer)
    competencia: Mapped[str] = mapped_column(String(7), index=True)
    valor: Mapped[float] = mapped_column(_dinheiro())
    pago_em: Mapped[date] = mapped_column(Date)
    conta_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lancamento_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Divida(Base):
    __tablename__ = "dividas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credor: Mapped[str] = mapped_column(String(120))
    valor_total: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)  # vazio = a organizar
    parcelas_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parcelas_pagas: Mapped[int] = mapped_column(Integer, default=0)
    valor_parcela: Mapped[Optional[float]] = mapped_column(_dinheiro(), nullable=True)
    # Quando sera pago. Registrar uma parcela paga empurra pro mes seguinte.
    proximo_pagamento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    observacao: Mapped[str] = mapped_column(String(300), default="")
    quitada: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
