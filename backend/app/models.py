from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, LargeBinary, String, DateTime, Boolean, UniqueConstraint
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
    loading_date: Mapped[str] = mapped_column(String(32), default="")
    driver_name: Mapped[str] = mapped_column(String(255), default="")
    driver_cpf: Mapped[str] = mapped_column(String(32), default="")
    driver_phone: Mapped[str] = mapped_column(String(64), default="")
    cnh: Mapped[str] = mapped_column(String(64), default="")
    plate_cavalo: Mapped[str] = mapped_column(String(16), default="")
    plate_carreta1: Mapped[str] = mapped_column(String(16), default="")
    plate_carreta2: Mapped[str] = mapped_column(String(16), default="")
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
    status: Mapped[str] = mapped_column(String(20), default="")  # "enviada" | "erro"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
