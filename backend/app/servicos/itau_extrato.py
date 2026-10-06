"""Extrato de conta corrente do Itau pela API oficial (devportal).

Hoje o extrato entra na mao: o dono baixa o OFX no internet banking e sobe na
tela de Caixa. Aqui o sistema busca o MESMO extrato direto no banco e devolve
os lancamentos no formato que `financeiro_importacao.ler_ofx` produz - a
previa, a deduplicacao, o "linha de saldo nao e lancamento" e a conferencia
continuam sendo os de `financeiro_importacao.gravar_extrato`. De proposito nao
existe um segundo caminho de importacao: se um dia a regra de deduplicacao
mudar, muda nos dois.

Como o banco autentica (documentacao que o Itau mandou):

1. client_id + client_secret gerados no devportal (o secret aparece UMA vez).
2. Certificado dinamico (mTLS): gera-se um CSR com OpenSSL, o Itau devolve o
   .crt assinado, e toda chamada vai com o par .crt + .key.
3. `POST https://sts.itau.com.br/api/oauth/token` (form-urlencoded,
   grant_type=client_credentials) devolve um access_token que vale
   `expires_in: 300` - CINCO minutos. Guardamos em memoria e renovamos com
   folga, senao a paginacao morre no meio.
4. `GET .../account-statement/v1/statements/{CONTA}` com `Authorization:
   Bearer` e o mesmo certificado. {CONTA} = agencia(4) + "00" + conta(5) +
   DAC(1) (exemplo da doc: 816100994788).

NADA de credencial entra em log: nem o secret, nem o token, nem o conteudo do
certificado. O que o log registra e quantidade de evento e numero de pagina.

=== O QUE A DOCUMENTACAO NAO MOSTRA (e por isso nao esta chutado aqui) ======

O print que o banco mandou esta cortado e **nao mostra o campo do VALOR** do
lancamento nem o nome do campo de SALDO. Em vez de fixar um nome e fingir que
esta certo:

- o valor e procurado entre os nomes plausiveis das APIs do Itau/Open Finance
  (`amount`, `value`, `transaction_amount`...), soltos ou dentro de um objeto;
  ver NOMES_DE_VALOR e `_valor_do_evento`. Se nao achar, a importacao FALHA
  com o evento inteiro na mensagem, pra ajustar o nome na primeira resposta
  real em vez de gravar lancamento errado no caixa.
- o saldo do extrato fica como None: sem o nome do campo nao tem como
  conferir "banco x sistema" como o OFX faz. A previa aparece sem a linha de
  conferencia; o resto funciona igual.
"""
from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
import time
import uuid
from collections import Counter
from contextlib import suppress
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ContaBancaria
from . import financeiro as fin
from .financeiro_importacao import _numero, eh_linha_de_saldo, gravar_extrato

logger = logging.getLogger(__name__)

# Fonte do lancamento dentro do id_externo. Separada do "ofx:" de proposito:
# e o que deixa a mesma movimentacao vinda das duas fontes cair na
# conferencia de "parecidos" em vez de entrar duas vezes (ver gravar_extrato).
PREFIXO_ID = "itau:"
FONTE = "itau_api"

# O token vale 300s. Renovamos 60s antes pra nenhuma pagina pegar token morto.
FOLGA_DO_TOKEN = 60
MAX_PAGINAS = 50

# Nomes plausiveis do campo de valor - o print da doc esta cortado nessa
# coluna. A ordem e a da aposta mais provavel pra menos provavel. So entramos
# DENTRO de um objeto cujo proprio nome esta nesta lista ("amount": {"value":
# ...}): assim um eventual "balance": {"amount": ...} de saldo nunca e
# confundido com o valor do lancamento.
NOMES_DE_VALOR = ("amount", "transaction_amount", "value", "event_amount", "valor", "transaction_value")


class ErroItau(Exception):
    """Falha falando com a API do Itau (rede, HTTP, credencial recusada)."""


class CredencialItauAusente(ErroItau):
    """Falta preencher client id/secret, certificado ou a conta."""


class PayloadItauDesconhecido(ErroItau):
    """A resposta veio com campo que a documentacao nao mostrava."""


# --------------------------------------------------------------------------
# Credenciais (tudo por variavel de ambiente)
# Pasta do processo pros certificados colados em variavel de ambiente: some
# junto com o container, e nao fica nada no repositorio.
_PASTA_CERT = Path(tempfile.gettempdir()) / "itau-extrato"
_PASTA_CERT.mkdir(parents=True, exist_ok=True)


def _faltando() -> list[str]:
    pendencias = []
    if not (settings.itau_client_id or "").strip():
        pendencias.append("ITAU_CLIENT_ID")
    if not (settings.itau_client_secret or "").strip():
        pendencias.append("ITAU_CLIENT_SECRET")
    if not ((settings.itau_cert_path or "").strip() or (settings.itau_cert_pem or "").strip()):
        pendencias.append("ITAU_CERT_PATH (ou ITAU_CERT_PEM)")
    if not ((settings.itau_cert_key_path or "").strip() or (settings.itau_cert_key_pem or "").strip()):
        pendencias.append("ITAU_CERT_KEY_PATH (ou ITAU_CERT_KEY_PEM)")
    if not (settings.itau_agencia or "").strip():
        pendencias.append("ITAU_AGENCIA")
    if not (settings.itau_conta or "").strip():
        pendencias.append("ITAU_CONTA")
    return pendencias


def _arquivo_do_pem(conteudo: str, nome: str) -> str:
    """Grava num arquivo so do processo o PEM que veio colado na variavel.

    O requests so aceita caminho de arquivo no mTLS. No servidor nao ha onde
    largar arquivo com seguranca, entao o certificado vem colado na variavel
    de ambiente e e escrito aqui, uma vez, numa pasta temporaria so do
    processo e sem permissao pra mais ninguem."""
    destino = _PASTA_CERT / nome
    if not destino.exists() or destino.read_text(encoding="utf-8") != conteudo:
        destino.write_text(conteudo, encoding="utf-8")
        with suppress(OSError):  # Windows nao tem o mesmo modelo de permissao
            destino.chmod(0o600)
    return str(destino)


def _certificado() -> tuple[str, str]:
    """Par (.crt, .key) do certificado dinamico, pro mTLS.

    O caminho do arquivo vence o conteudo colado: quem tem o arquivo no
    servidor nao precisa mexer em mais nada."""
    crt = (settings.itau_cert_path or "").strip()
    key = (settings.itau_cert_key_path or "").strip()
    if not crt:
        crt = _arquivo_do_pem((settings.itau_cert_pem or "").strip() + "\n", "itau.crt")
    if not key:
        key = _arquivo_do_pem((settings.itau_cert_key_pem or "").strip() + "\n", "itau.key")
    return (crt, key)


def _exigir_credenciais() -> None:
    pendencias = _faltando()
    if pendencias:
        raise CredencialItauAusente(
            "Configure as credenciais do Itaú para puxar o extrato automaticamente. "
            f"Falta preencher no servidor: {', '.join(pendencias)}."
        )


def conta_formatada() -> str:
    """agencia(4) + conta(7, com zeros a esquerda) + DAC(1), como a
    especificacao do Itau manda: "Ag. 1500 - CC. 0123456 - VD. 7" vira
    150001234567.

    E por isso que conta de 5 digitos aparece com dois zeros na frente no
    material do banco (8161 + 00 + 99478 + 8): sao os zeros do preenchimento,
    nao um pedaco fixo. Montar isso na mao erra facil, entao cada pedaco vem
    em sua variavel e a conferencia de tamanho e feita aqui.
    """
    _exigir_credenciais()
    agencia = re.sub(r"\D", "", settings.itau_agencia or "")
    conta = re.sub(r"\D", "", settings.itau_conta or "")
    dac = re.sub(r"\D", "", settings.itau_conta_dac or "")
    # Quem copia a conta do extrato costuma copiar com o digito ("99478-8"):
    # sem ITAU_CONTA_DAC preenchido, o ultimo digito e o DAC.
    if not dac and len(conta) == 6:
        conta, dac = conta[:5], conta[5]
    if not dac and len(conta) == 8:
        conta, dac = conta[:7], conta[7]
    agencia, conta = agencia.zfill(4), conta.zfill(7)
    if len(agencia) != 4 or len(conta) != 7 or len(dac) != 1:
        raise CredencialItauAusente(
            "Conta do Itaú configurada errado: ITAU_AGENCIA tem 4 dígitos, ITAU_CONTA até 7 e "
            f"ITAU_CONTA_DAC 1 (hoje está agência={agencia or '?'}, conta={conta or '?'}, dac={dac or '?'})."
        )
    return f"{agencia}{conta}{dac}"


# --------------------------------------------------------------------------
# Token (vale 5 minutos)
# --------------------------------------------------------------------------

_TOKEN: dict = {"valor": "", "vale_ate": 0.0}
_TRAVA = threading.Lock()


def _agora() -> float:
    """Relogio monotonico num lugar so - o teste adianta o tempo por aqui."""
    return time.monotonic()


def limpar_token() -> None:
    """Esquece o token guardado (uso: 401 do banco e testes)."""
    with _TRAVA:
        _TOKEN["valor"], _TOKEN["vale_ate"] = "", 0.0


def _resumo_http(resposta) -> str:
    texto = (getattr(resposta, "text", "") or "").strip()
    return texto[:300] if texto else "(sem corpo)"


def token() -> str:
    """Access token valido, do cache ou novo.

    O token do Itau dura 300 segundos: pedir um por chamada seria desperdicio
    e deixar o mesmo guardado "pra sempre" quebraria no meio da paginacao. A
    trava evita duas requisicoes pedirem token ao mesmo tempo (as rotas sync
    do FastAPI rodam em threads).
    """
    with _TRAVA:
        if _TOKEN["valor"] and _TOKEN["vale_ate"] > _agora():
            return _TOKEN["valor"]
        _exigir_credenciais()
        try:
            resposta = requests.post(
                settings.itau_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.itau_client_id,
                    "client_secret": settings.itau_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                cert=_certificado(),
                timeout=settings.itau_timeout_segundos,
            )
        except requests.exceptions.RequestException as exc:
            raise ErroItau(f"Não consegui falar com o STS do Itaú: {type(exc).__name__}") from exc
        if resposta.status_code != 200:
            # Sem secret e sem token na mensagem: so o que o banco respondeu.
            raise ErroItau(
                f"O Itaú não liberou o acesso (HTTP {resposta.status_code}): {_resumo_http(resposta)}. "
                "Confira client id/secret e se o certificado é o que o banco assinou."
            )
        try:
            dados = resposta.json()
        except ValueError as exc:
            raise ErroItau("O STS do Itaú respondeu algo que não é JSON") from exc
        valor = str((dados or {}).get("access_token") or "").strip()
        if not valor:
            raise ErroItau("O STS do Itaú respondeu sem access_token")
        segundos = _numero((dados or {}).get("expires_in")) or 300
        _TOKEN["valor"] = valor
        _TOKEN["vale_ate"] = _agora() + max(int(segundos) - FOLGA_DO_TOKEN, 30)
        logger.info("Itaú: token novo, vale %ss", int(segundos))
        return valor


# --------------------------------------------------------------------------
# Leitura do extrato
# --------------------------------------------------------------------------


def _buscar_pagina(conta: str, inicio: date, fim: date, pagina: int) -> dict:
    url = f"{(settings.itau_extrato_base_url or '').rstrip('/')}/statements/{conta}"
    params = {
        "type": "current_account",
        "start_date": inicio.isoformat(),
        "end_date": fim.isoformat(),
        "page_size": settings.itau_page_size,
        "page": pagina,
    }
    for tentativa in (1, 2):
        cabecalhos = {
            "Authorization": f"Bearer {token()}",
            "Accept": "application/json",
            # Obrigatorio na especificacao: um id novo por chamada, pro banco
            # conseguir rastrear a requisicao quando a gente abrir chamado.
            "x-itau-correlationid": str(uuid.uuid4()),
        }
        try:
            resposta = requests.get(
                url, params=params, headers=cabecalhos, cert=_certificado(),
                timeout=settings.itau_timeout_segundos,
            )
        except requests.exceptions.RequestException as exc:
            raise ErroItau(f"Não consegui falar com a API de extrato do Itaú: {type(exc).__name__}") from exc
        if resposta.status_code in (401, 403) and tentativa == 1:
            # Token de 5 minutos pode morrer entre duas paginas: pega outro e
            # tenta uma unica vez (GET e seguro de repetir).
            limpar_token()
            continue
        if resposta.status_code != 200:
            raise ErroItau(f"O Itaú não devolveu o extrato (HTTP {resposta.status_code}): {_resumo_http(resposta)}")
        try:
            return resposta.json() or {}
        except ValueError as exc:
            raise ErroItau("O Itaú respondeu algo que não é JSON no extrato") from exc
    raise ErroItau("O Itaú recusou o token duas vezes seguidas ao buscar o extrato")


def _eventos(payload) -> list[dict]:
    """Os lancamentos de uma pagina: {"data": [{"events": [...]}]}.

    Tolerante de proposito: `data` pode vir como objeto em vez de lista e
    `events` tambem - a doc so mostra um exemplo de cada.
    """
    dados = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(dados, dict):
        dados = [dados]
    achados: list[dict] = []
    for bloco in dados or []:
        if not isinstance(bloco, dict):
            continue
        lista = bloco.get("events")
        if isinstance(lista, dict):
            lista = [lista]
        achados.extend([e for e in (lista or []) if isinstance(e, dict)])
    return achados


def _valor_do_evento(evento: dict) -> Optional[float]:
    """Valor do lancamento, sem chutar um nome unico de campo.

    O print da documentacao esta cortado exatamente na coluna do valor. Aqui
    procuramos os nomes que aparecem nas APIs do Itau e do Open Finance,
    soltos ("amount": "123.45") ou dentro de um objeto ("amount": {"value":
    "123.45", "currency": "BRL"}). So descemos pra dentro de objeto cujo nome
    tambem e de valor, pra nunca pegar o "amount" de um saldo por engano.
    """
    for nome in NOMES_DE_VALOR:
        if nome not in evento:
            continue
        bruto = evento[nome]
        if isinstance(bruto, dict):
            for interno in NOMES_DE_VALOR:
                numero = _numero(bruto.get(interno))
                if numero is not None:
                    return numero
            continue
        numero = _numero(bruto)
        if numero is not None:
            return numero
    return None


def _dia_iso(texto, *, instante_utc: bool = False) -> Optional[date]:
    bruto = str(texto or "").strip()
    achou = re.match(r"(\d{4})-(\d{2})-(\d{2})", bruto)
    if not achou:
        return None
    dia = date(int(achou.group(1)), int(achou.group(2)), int(achou.group(3)))
    if instante_utc and "T" in bruto and bruto.upper().endswith("Z"):
        try:
            return (datetime.strptime(bruto[:19], "%Y-%m-%dT%H:%M:%S") - timedelta(hours=3)).date()
        except ValueError:
            return dia
    return dia


def _data_do_evento(evento: dict) -> Optional[date]:
    """A data do lancamento e a CONTABIL (`date.accounting`).

    No proprio exemplo da documentacao o evento e "2024-08-06T02:59:00Z" e a
    data contabil e 2024-08-05: 02h59 em UTC e 23h59 do dia 5 em Brasilia. Se
    lancassemos pelo instante do evento, o dinheiro cairia no dia seguinte e o
    fechamento do dia nunca bateria com o extrato - o saldo do banco anda pela
    data contabil, e e ela que a tela de Caixa mostra.

    So caimos no `date.event` (convertido de UTC pra Brasilia) se a contabil
    nao vier.
    """
    bloco = evento.get("date")
    if isinstance(bloco, dict):
        return _dia_iso(bloco.get("accounting")) or _dia_iso(bloco.get("event"), instante_utc=True)
    return _dia_iso(bloco, instante_utc=True)


def _descricao_do_evento(evento: dict) -> str:
    """Historico do lancamento ("SISPAG FIDC L CON MOVIM").

    O `literal.tip` NAO entra: e o texto de ajuda do banco ("Lançamento
    referente a pagamento de boletos..."), igual pra todo lancamento do mesmo
    codigo, e poluiria a descricao do caixa.
    """
    literal = evento.get("literal")
    if isinstance(literal, dict):
        texto = str(literal.get("complete") or literal.get("shortened") or "").strip()
        if texto:
            return texto
        codigo = str(literal.get("code") or "").strip()
        return f"Lançamento {codigo}" if codigo else ""
    return str(literal or evento.get("description") or "").strip()


def _tipo_do_evento(evento: dict, valor: float) -> str:
    """C = credito (entrada), D = debito (saida).

    `reversal: true` diz que a linha E UM ESTORNO - e o `operation` dela ja vem
    com o sinal do estorno (o estorno de um debito chega como credito). Por
    isso o estorno NAO inverte nada: inverter aqui seria inverter duas vezes e
    o caixa fecharia errado. O que fazemos e marcar "Estorno" na descricao,
    pra quem confere reconhecer a linha na hora.
    """
    operacao = str(evento.get("operation") or "").strip().upper()[:1]
    if operacao == "C":
        return "entrada"
    if operacao == "D":
        return "saida"
    # Sem `operation` sobra o sinal do proprio valor (debito negativo), como
    # no OFX.
    return "saida" if valor < 0 else "entrada"


# O saldo do dia vem num bloco proprio (data.balances), fora dos lancamentos.
# "saldo_disponivel" e o que o extrato mostra como saldo do dia; "saldo_total"
# entra como segunda opcao porque conta sem aplicacao automatica traz os dois
# iguais.
SALDOS_PREFERIDOS = ("saldo_disponivel", "saldo_total")


def _saldo_do_payload(payload) -> Optional[float]:
    """O saldo que o banco informa pra pagina, pra conferencia "banco x sistema"."""
    dados = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(dados, dict):
        dados = [dados]
    por_tipo: dict[str, float] = {}
    for bloco in dados or []:
        if not isinstance(bloco, dict):
            continue
        for saldo in bloco.get("balances") or []:
            if not isinstance(saldo, dict):
                continue
            valor = _numero(((saldo.get("amount") or {}) if isinstance(saldo.get("amount"), dict) else {}).get("value"))
            if valor is None:
                valor = _numero(saldo.get("amount"))
            if valor is not None:
                por_tipo.setdefault(str(saldo.get("type") or "").strip().lower(), valor)
    for tipo in SALDOS_PREFERIDOS:
        if tipo in por_tipo:
            return por_tipo[tipo]
    return next(iter(por_tipo.values()), None)


def _total_de_paginas(payload) -> Optional[int]:
    """Quantas paginas a API diz ter - evita adivinhar pelo tamanho da pagina."""
    dados = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(dados, dict):
        dados = [dados]
    for bloco in dados or []:
        if isinstance(bloco, dict):
            paginacao = bloco.get("pagination")
            if isinstance(paginacao, dict):
                total = _numero(paginacao.get("total_pages"))
                if total:
                    return int(total)
    return None


def _erro_de_valor(evento: dict) -> PayloadItauDesconhecido:
    return PayloadItauDesconhecido(
        "Não achei o valor do lançamento na resposta do Itaú. A documentação que o banco mandou está "
        "cortada e não mostra esse campo, então o nome tem que ser confirmado na primeira resposta real. "
        f"Procurei por: {', '.join(NOMES_DE_VALOR)}. O lançamento veio assim: "
        f"{json.dumps(evento, ensure_ascii=False, default=str)[:600]}"
    )


def buscar_extrato(inicio: date, fim: date) -> dict:
    """Extrato do periodo, no MESMO formato que `ler_ofx` devolve.

    Pagina ate a API parar de mandar coisa nova. Sem `page_size` garantido na
    documentacao, a parada e por pagina incompleta, pagina vazia ou pagina
    toda repetida - nenhum dos tres depende de campo que nao conhecemos.
    """
    conta = conta_formatada()
    transacoes: list[dict] = []
    linhas_de_saldo: list[dict] = []
    saldo_anterior = None
    tipos: Counter = Counter()
    vistos: set[str] = set()
    eventos_lidos = 0
    tamanho = max(int(settings.itau_page_size or 100), 1)
    paginas = 0

    saldo = None
    total_de_paginas = None

    for pagina in range(1, MAX_PAGINAS + 1):
        payload = _buscar_pagina(conta, inicio, fim, pagina)
        eventos = _eventos(payload)
        paginas = pagina
        if saldo is None:
            saldo = _saldo_do_payload(payload)
        total_de_paginas = _total_de_paginas(payload) or total_de_paginas
        if not eventos:
            break
        novos = 0
        for posicao, evento in enumerate(eventos):
            eventos_lidos += 1
            identificador = str(evento.get("id") or "").strip()
            if identificador:
                if identificador in vistos:
                    continue
                vistos.add(identificador)
            novos += 1
            tipos[str(evento.get("type") or "")] += 1
            dia = _data_do_evento(evento)
            descricao = _descricao_do_evento(evento)
            bruto = _valor_do_evento(evento)

            if eh_linha_de_saldo(descricao):
                # Mesma regra do OFX: o Itau manda "SALDO TOTAL DISPONIVEL DIA"
                # e "SALDO ANTERIOR" junto dos lancamentos. Lancar isso dobraria
                # o caixa. Linha de saldo sem valor reconhecido nao e erro - ela
                # nao vira lancamento de qualquer forma.
                registro = {"data": dia, "valor": fin.dinheiro(bruto or 0), "descricao": descricao}
                linhas_de_saldo.append(registro)
                if "ANTERIOR" in descricao.upper() and dia is not None:
                    saldo_anterior = {"data": dia, "valor": fin.dinheiro(bruto or 0)}
                continue

            if bruto is None:
                # Nao da pra adivinhar: falha dizendo o que veio, pra ajustar
                # NOMES_DE_VALOR quando a primeira resposta real aparecer.
                raise _erro_de_valor(evento)
            if dia is None:
                raise PayloadItauDesconhecido(
                    "Não achei a data contábil do lançamento na resposta do Itaú. O lançamento veio assim: "
                    f"{json.dumps(evento, ensure_ascii=False, default=str)[:600]}"
                )
            if fin.dinheiro(bruto) == 0:
                continue

            tipo = _tipo_do_evento(evento, bruto)
            if evento.get("reversal") is True and not descricao.upper().startswith("ESTORNO"):
                descricao = f"Estorno: {descricao}".strip()
            # Sem id do banco o jeito e montar uma chave estavel com o que
            # temos; a doc mostra "id" em todo evento, isso e so a rede.
            fitid = identificador or f"{dia.isoformat()}:{tipo}:{abs(bruto):.2f}:{pagina}:{posicao}"
            transacoes.append({
                "fitid": fitid, "data": dia, "valor": abs(fin.dinheiro(bruto)), "tipo": tipo,
                "descricao": descricao,
            })
        if total_de_paginas is not None:
            if pagina >= total_de_paginas:
                break
        elif len(eventos) < tamanho or not novos:
            break
        if not novos:
            break

    logger.info("Itaú: extrato de %s a %s - %s eventos em %s página(s)", inicio, fim, eventos_lidos, paginas)
    return {
        "transacoes": transacoes,
        # Saldo informado pelo banco: e o que liga a conferencia "banco x
        # sistema" na previa, igual ao OFX.
        "saldo": fin.dinheiro(saldo) if saldo is not None else None,
        "linhas_de_saldo": linhas_de_saldo,
        "saldo_anterior": saldo_anterior,
        # Diagnostico pra primeira chamada de verdade (quais "type" o banco
        # manda). Nao tem dado sensivel: so a contagem por tipo.
        "eventos_lidos": eventos_lidos,
        "paginas": paginas,
        "tipos_de_evento": dict(tipos),
    }


def importar_extrato(db: Session, conta_id: int, inicio: date, fim: date, *, aplicar: bool = False,
                     usuario: str = "") -> dict:
    """Puxa o extrato no Itau e entrega pro fluxo do OFX (previa inclusa).

    Sem `aplicar`, `gravar_extrato` faz tudo numa transacao e desfaz: a tela
    mostra o que entraria antes de gravar, igual ao arquivo OFX.
    """
    if db.get(ContaBancaria, conta_id) is None:
        # Antes de acordar o banco: conta errada na tela nao gasta chamada.
        raise fin.ErroFinanceiro("Conta bancária não encontrada")
    lido = buscar_extrato(inicio, fim)
    resumo = gravar_extrato(db, conta_id, lido, prefixo=PREFIXO_ID, fonte=FONTE, aplicar=aplicar, usuario=usuario)
    resumo["periodo_pedido"] = {"inicio": inicio.isoformat(), "fim": fim.isoformat()}
    resumo["eventos_lidos"] = lido["eventos_lidos"]
    resumo["tipos_de_evento"] = lido["tipos_de_evento"]
    return resumo
