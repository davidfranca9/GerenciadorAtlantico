"""Leitura da caixa de entrada do Gmail via IMAP.

Usa o mesmo app password ja previsto em config.py (GMAIL_APP_PASSWORD_IMAP)
para logar via IMAP e listar/ler as mensagens do INBOX, sem precisar de
OAuth/credenciais do Google Cloud Console.
"""
from __future__ import annotations

import base64
import email
import html
import imaplib
import logging
import socket
import time
import re
import threading
from email.header import decode_header
from datetime import timezone
from email.utils import parsedate_to_datetime

from ..config import settings

IMAP_HOST = "imap.gmail.com"

_lock = threading.Lock()
_conexao_ativa: imaplib.IMAP4_SSL | None = None


class InboxIndisponivel(Exception):
    pass


def credenciais_limpas() -> tuple[str, str]:
    usuario = re.sub(r"\s+", "", settings.gmail_sender_email or "")
    senha = re.sub(r"\s+", "", settings.gmail_app_password_imap or "")
    return usuario, senha


def _logar(usuario: str, senha: str) -> imaplib.IMAP4_SSL:
    conexao = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        conexao.login(usuario, senha)
    except imaplib.IMAP4.error as exc:
        raise InboxIndisponivel(
            "Login IMAP falhou. Confira: (1) a senha de app em GMAIL_APP_PASSWORD_IMAP esta correta e sem "
            "espacos, (2) o IMAP esta habilitado nas configuracoes do Gmail (Config. > Encaminhamento e "
            f"POP/IMAP > Ativar IMAP) da conta {usuario}. Erro original: {exc}"
        ) from exc
    return conexao


def _obter_conexao() -> imaplib.IMAP4_SSL:
    """Reaproveita uma unica conexao IMAP entre requisicoes (evita repetir o
    handshake TLS + login a cada acao, que era o principal motivo da lentidao).
    Verifica com NOOP se ainda esta viva antes de reusar; reconecta se nao."""
    global _conexao_ativa

    if _conexao_ativa is not None:
        try:
            _conexao_ativa.noop()
            return _conexao_ativa
        except Exception:
            try:
                _conexao_ativa.logout()
            except Exception:
                pass
            _conexao_ativa = None

    usuario, senha = credenciais_limpas()
    if not usuario or not senha:
        raise InboxIndisponivel("GMAIL_SENDER_EMAIL / GMAIL_APP_PASSWORD_IMAP nao configurados")
    _conexao_ativa = _logar(usuario, senha)
    return _conexao_ativa


def _decodificar(valor: str | None) -> str:
    if not valor:
        return ""
    texto = ""
    for parte, codificacao in decode_header(valor):
        if isinstance(parte, bytes):
            texto += parte.decode(codificacao or "utf-8", errors="replace")
        else:
            texto += parte
    return texto


def _extrair_remetente(msg: email.message.Message) -> dict:
    bruto = _decodificar(msg.get("From", ""))
    if "<" in bruto and ">" in bruto:
        nome, endereco = bruto.rsplit("<", 1)
        return {"nome": nome.strip().strip('"'), "email": endereco.strip(">").strip()}
    return {"nome": bruto, "email": bruto}


def _extrair_data(msg: email.message.Message) -> str:
    bruto = msg.get("Date")
    if not bruto:
        return ""
    try:
        return parsedate_to_datetime(bruto).isoformat()
    except (TypeError, ValueError):
        return bruto


def _consulta_gmail(busca: str) -> str:
    """Monta a expressao de busca do Gmail. Sem termo, mantem o filtro
    padrao (fora de promocoes). Com termo, o usuario pode usar a sintaxe do
    proprio Gmail (from:, subject:, has:attachment, newer_than:7d...)."""
    termo = (busca or "").strip()
    if not termo:
        return '"-category:promotions"'
    # Aspas duplas quebrariam a string da consulta IMAP.
    return '"{}"'.format(termo.replace('"', " "))


PASTAS = ("recebidos", "enviados")
_caixas_especiais: dict[str, str] = {}
# (conexao, pasta, so_leitura) da ultima selecao: abrir uma conversa le
# varias mensagens seguidas e nao precisa reabrir a pasta a cada uma.
_selecao_atual: tuple | None = None


def nome_da_caixa_especial(linhas_do_list: list, atributo: str) -> str:
    """Nome da pasta pelo atributo do Gmail (\\Sent, \\All): o nome muda com
    o idioma da conta ("[Gmail]/E-mails enviados", "[Gmail]/Sent Mail")."""
    for linha in linhas_do_list or []:
        texto = linha.decode("utf-8", errors="replace") if isinstance(linha, bytes) else str(linha)
        bandeiras = re.match(r"\((.*?)\)", texto)
        if not bandeiras or atributo.lower() not in bandeiras.group(1).lower().split():
            continue
        nome = re.search(r'"((?:[^"\\]|\\.)*)"\s*$', texto) or re.search(r"(\S+)\s*$", texto)
        if nome:
            return nome.group(1)
    return ""


def _selecionar(conexao: imaplib.IMAP4_SSL, pasta: str, readonly: bool = True) -> None:
    """recebidos = INBOX; enviados = pasta de enviados; todas = "Todos os e-mails"
    (onde uma conversa tem o que chegou e o que saiu)."""
    if pasta == "recebidos":
        nome = "INBOX"
    else:
        atributo = "\\Sent" if pasta == "enviados" else "\\All"
        nome = _caixas_especiais.get(atributo, "")
        if not nome:
            status, linhas = conexao.list()
            nome = nome_da_caixa_especial(linhas if status == "OK" else [], atributo)
            if not nome:
                raise InboxIndisponivel(f"Pasta {pasta} nao encontrada no Gmail")
            _caixas_especiais[atributo] = nome
    global _selecao_atual
    if _selecao_atual is not None and _selecao_atual[0] is conexao and _selecao_atual[1:] == (nome, readonly):
        return
    _selecao_atual = None
    if conexao.select(f'"{nome}"', readonly=readonly)[0] != "OK":
        raise InboxIndisponivel(f"Nao foi possivel abrir a pasta {pasta}")
    _selecao_atual = (conexao, nome, readonly)


def consulta_da_pasta(busca: str, pasta: str) -> str:
    """Termo de busca do Gmail pra pasta. Recebidos nao mostra o que a propria
    conta mandou: o sistema se copia nos envios e a caixa ficava misturada."""
    termo = (busca or "").strip()
    if pasta == "recebidos":
        termo = f"{termo or '-category:promotions'} -from:me"
    return termo


def _numero_pelo_id(conexao: imaplib.IMAP4_SSL, msg_id: str) -> bytes:
    """Posicao da mensagem na pasta ja selecionada, pelo id do Gmail (X-GM-MSGID).

    O id do Gmail nao muda de pasta pra pasta; a posicao muda. Por isso a
    lista devolve o id e quem abre procura a posicao na hora."""
    if not re.fullmatch(r"\d+", str(msg_id or "")):
        raise InboxIndisponivel("Mensagem nao encontrada")
    status, dados = conexao.search(None, "X-GM-MSGID", str(msg_id))
    if status != "OK" or not dados or not dados[0]:
        raise InboxIndisponivel("Mensagem nao encontrada")
    return dados[0].split()[0]


def listar_mensagens(pagina: int = 1, tamanho_pagina: int = 25, busca: str = "", pasta: str = "recebidos") -> dict:
    if pasta not in PASTAS:
        raise InboxIndisponivel("Pasta invalida")
    with _lock:
        conexao = _obter_conexao()
        _selecionar(conexao, pasta)

        termo = consulta_da_pasta(busca, pasta)
        if termo:
            status, dados = conexao.search(None, "X-GM-RAW", _consulta_gmail(termo))
        else:
            status, dados = conexao.search(None, "ALL")
        if status != "OK":
            raise InboxIndisponivel("Nao foi possivel listar as mensagens")

        todos_ids = dados[0].split()
        todos_ids.reverse()
        total = len(todos_ids)
        inicio = (pagina - 1) * tamanho_pagina
        pagina_ids = todos_ids[inicio : inicio + tamanho_pagina]

        if not pagina_ids:
            return {"mensagens": [], "total": total, "pagina": pagina, "tamanho_pagina": tamanho_pagina}

        # Busca todas as mensagens da pagina numa unica chamada FETCH (uma
        # unica ida-e-volta ao servidor) em vez de uma chamada por mensagem.
        status, dados_msg = conexao.fetch(b",".join(pagina_ids), "(X-GM-MSGID FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
        if status != "OK":
            raise InboxIndisponivel("Nao foi possivel buscar as mensagens")

        por_id: dict[bytes, dict] = {}
        for item in dados_msg:
            if not isinstance(item, tuple):
                continue
            linha_info, cabecalho_bruto = item
            correspondencia = re.match(rb"(\d+) \(", linha_info)
            if not correspondencia:
                continue
            msg_id = correspondencia.group(1)
            id_gmail = re.search(rb"X-GM-MSGID (\d+)", linha_info)
            msg = email.message_from_bytes(cabecalho_bruto)
            flags = imaplib.ParseFlags(linha_info)
            por_id[msg_id] = {
                "id": id_gmail.group(1).decode() if id_gmail else msg_id.decode(),
                "remetente": _extrair_remetente(msg),
                "para": _decodificar(msg.get("To", "")),
                "assunto": _decodificar(msg.get("Subject", "")) or "(sem assunto)",
                "data": _extrair_data(msg),
                "lida": b"\\Seen" in flags,
            }

        mensagens = [por_id[mid] for mid in pagina_ids if mid in por_id]
        return {"mensagens": mensagens, "total": total, "pagina": pagina, "tamanho_pagina": tamanho_pagina, "pasta": pasta}


def obter_mensagem(msg_id: str) -> dict:
    with _lock:
        conexao = _obter_conexao()
        # Abrir marca como lida, igual no Gmail: por isso nao e so leitura.
        _selecionar(conexao, "todas", readonly=False)
        numero = _numero_pelo_id(conexao, msg_id)

        status, dados_msg = conexao.fetch(numero, "(BODY[])")
        if status != "OK" or not dados_msg or not isinstance(dados_msg[0], tuple):
            raise InboxIndisponivel("Mensagem nao encontrada")

        msg = email.message_from_bytes(dados_msg[0][1])

        corpo_html = ""
        corpo_texto = ""
        anexos: list[dict] = []
        imagens_inline: dict[str, str] = {}

        if msg.is_multipart():
            for parte in msg.walk():
                content_type = parte.get_content_type()
                disposicao = str(parte.get("Content-Disposition", ""))
                content_id = (parte.get("Content-ID") or "").strip().strip("<>")

                if content_type.startswith("image/") and (content_id or "inline" in disposicao):
                    payload = parte.get_payload(decode=True)
                    if payload and content_id:
                        imagens_inline[content_id] = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
                    continue

                if "attachment" in disposicao:
                    conteudo = parte.get_payload(decode=True) or b""
                    anexos.append({
                        "indice": len(anexos),
                        "nome": _decodificar(parte.get_filename()) or "arquivo",
                        "tipo": parte.get_content_type(),
                        "tamanho": len(conteudo),
                    })
                    continue

                payload = parte.get_payload(decode=True)
                if payload is None:
                    continue
                texto = payload.decode(parte.get_content_charset() or "utf-8", errors="replace")
                if content_type == "text/html" and not corpo_html:
                    corpo_html = texto
                elif content_type == "text/plain" and not corpo_texto:
                    corpo_texto = texto
        else:
            payload = msg.get_payload(decode=True)
            texto = payload.decode(msg.get_content_charset() or "utf-8", errors="replace") if payload else ""
            if msg.get_content_type() == "text/html":
                corpo_html = texto
            else:
                corpo_texto = texto

        if corpo_html and imagens_inline:
            def _substituir_cid(match: re.Match) -> str:
                cid = match.group(1).strip("'\"")
                return f"cid:{cid}" if cid not in imagens_inline else imagens_inline[cid]

            corpo_html = re.sub(r"cid:([^\"'\)\s]+)", _substituir_cid, corpo_html)

        return {
            "id": msg_id,
            "remetente": _extrair_remetente(msg),
            "para": _decodificar(msg.get("To", "")),
            "assunto": _decodificar(msg.get("Subject", "")) or "(sem assunto)",
            "data": _extrair_data(msg),
            "corpo_html": corpo_html,
            "corpo_texto": corpo_texto,
            "anexos": anexos,
        }


def _partes_anexas(msg) -> list:
    """Anexos de uma mensagem, na ordem em que aparecem.

    Imagem embutida na assinatura (com Content-ID) nao conta: ela ja vai
    inline no corpo e poluiria a lista com logotipos.
    """
    encontrados = []
    if not msg.is_multipart():
        return encontrados
    for parte in msg.walk():
        disposicao = str(parte.get("Content-Disposition", ""))
        if "attachment" not in disposicao:
            continue
        conteudo = parte.get_payload(decode=True)
        encontrados.append({
            "nome": _decodificar(parte.get_filename()) or "arquivo",
            "tipo": parte.get_content_type(),
            "tamanho": len(conteudo or b""),
            "conteudo": conteudo or b"",
        })
    return encontrados


def obter_anexo(msg_id: str, indice: int) -> dict:
    """Devolve um anexo com o conteudo, pra download."""
    with _lock:
        conexao = _obter_conexao()
        _selecionar(conexao, "todas")
        status, dados = conexao.fetch(_numero_pelo_id(conexao, msg_id), "(BODY.PEEK[])")
        if status != "OK" or not dados or not isinstance(dados[0], tuple):
            raise InboxIndisponivel("Mensagem nao encontrada")

    anexos = _partes_anexas(email.message_from_bytes(dados[0][1]))
    if indice < 0 or indice >= len(anexos):
        raise InboxIndisponivel("Anexo nao encontrado")
    return anexos[indice]


def obter_thread(msg_id: str) -> list:
    """Ids de todas as mensagens da mesma conversa, da mais antiga pra mais
    recente.

    Usa a extensao X-GM-THRID do Gmail: uma resposta trocada varias vezes
    fica num unico thread, e sem isso a tela mostrava so a mensagem aberta.
    """
    with _lock:
        conexao = _obter_conexao()
        # Em "Todos os e-mails" a conversa tem o que chegou e o que saiu.
        _selecionar(conexao, "todas")
        numero = _numero_pelo_id(conexao, msg_id)

        status, dados = conexao.fetch(numero, "(X-GM-THRID)")
        if status != "OK" or not dados:
            return [msg_id]
        achado = re.search(rb"X-GM-THRID (\d+)", dados[0] if isinstance(dados[0], bytes) else dados[0][0] or b"")
        if not achado:
            return [msg_id]

        status, resultado = conexao.search(None, "X-GM-THRID", achado.group(1).decode())
        if status != "OK" or not resultado or not resultado[0]:
            return [msg_id]
        status, ids = conexao.fetch(b",".join(resultado[0].split()), "(X-GM-MSGID)")
        encontrados = []
        for item in ids if status == "OK" else []:
            linha = item[0] if isinstance(item, tuple) else item
            id_gmail = re.search(rb"X-GM-MSGID (\d+)", linha or b"")
            if id_gmail:
                encontrados.append(id_gmail.group(1).decode())
        return encontrados or [msg_id]


def _texto_simples(msg) -> str:
    """Corpo em texto: o text/plain quando existe, senao o HTML sem tags."""
    texto_plano, texto_html = "", ""
    partes = msg.walk() if msg.is_multipart() else [msg]
    for parte in partes:
        if "attachment" in str(parte.get("Content-Disposition", "")):
            continue
        tipo = parte.get_content_type()
        if tipo not in ("text/plain", "text/html"):
            continue
        payload = parte.get_payload(decode=True)
        if payload is None:
            continue
        conteudo = payload.decode(parte.get_content_charset() or "utf-8", errors="replace")
        if tipo == "text/plain" and not texto_plano:
            texto_plano = conteudo
        elif tipo == "text/html" and not texto_html:
            texto_html = conteudo
    if texto_plano.strip():
        return texto_plano
    semi = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", texto_html)
    semi = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</td>|</h\d>", "\n", semi)
    return html.unescape(re.sub(r"<[^>]+>", " ", semi))


def mensagens_para_ler(busca: str, ja_lidas: set[str], limite: int = 60) -> list[dict]:
    """Mensagens da busca que ainda nao foram lidas pelo sistema, completas.

    Pra leitura automatica (respostas da fabrica). BODY.PEEK nao marca como
    lida na caixa de quem usa o Gmail. `ja_lidas` sao Message-IDs ja
    processados: esses nem tem o corpo baixado.
    """
    with _lock:
        conexao = _obter_conexao()
        _selecionar(conexao, "recebidos")
        status, dados = conexao.search(None, "X-GM-RAW", _consulta_gmail(busca))
        if status != "OK":
            raise InboxIndisponivel("Nao foi possivel buscar as mensagens")
        ids = (dados[0] or b"").split()[-limite:]
        if not ids:
            return []

        status, cabecalhos = conexao.fetch(b",".join(ids), "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
        novos = []
        for item in cabecalhos if status == "OK" else []:
            if not isinstance(item, tuple):
                continue
            numero = re.match(rb"(\d+) \(", item[0])
            message_id = (email.message_from_bytes(item[1]).get("Message-ID") or "").strip()
            if numero and message_id and message_id not in ja_lidas:
                novos.append(numero.group(1))

        mensagens = []
        for numero in novos:
            status, partes = conexao.fetch(numero, "(X-GM-THRID BODY.PEEK[])")
            if status != "OK":
                continue
            bruto = next((p for p in partes if isinstance(p, tuple)), None)
            if bruto is None:
                continue
            conversa = re.search(rb"X-GM-THRID (\d+)", bruto[0])
            msg = email.message_from_bytes(bruto[1])
            try:
                recebido = parsedate_to_datetime(msg.get("Date"))
                if recebido.tzinfo is not None:
                    recebido = recebido.astimezone(timezone.utc).replace(tzinfo=None)
            except (TypeError, ValueError):
                recebido = None
            mensagens.append({
                "message_id": (msg.get("Message-ID") or "").strip(),
                "in_reply_to": msg.get("In-Reply-To") or "",
                "references": msg.get("References") or "",
                "conversa": conversa.group(1).decode() if conversa else "",
                "remetente": _extrair_remetente(msg).get("email", ""),
                "assunto": _decodificar(msg.get("Subject", "")),
                "recebido_em": recebido,
                "texto": _texto_simples(msg),
            })
        return mensagens


def contar_desde(epoch: int) -> int:
    """Quantas mensagens chegaram depois do instante informado.

    O Gmail aceita 'after:' com epoch em segundos na busca X-GM-RAW, entao
    da pra contar sem baixar mensagem nenhuma.
    """
    with _lock:
        conexao = _obter_conexao()
        _selecionar(conexao, "recebidos")
        # O que a propria conta mandou nao e mensagem nova pra ler.
        status, resultado = conexao.search(None, "X-GM-RAW", f'"after:{int(epoch)} -from:me"')
        if status != "OK" or not resultado or not resultado[0]:
            return 0
        return len(resultado[0].split())


def anexos_xml_recentes(dias: int = 7, limite_mensagens: int = 20) -> list[str]:
    """Conteudo dos anexos .xml das mensagens recentes.

    E o caminho rapido pra pegar a NF-e: quando o fornecedor manda o
    arquivo, ele chega aqui antes de aparecer na esteira da SEFAZ.
    """
    encontrados: list[str] = []
    listagem = listar_mensagens(1, limite_mensagens, f"has:attachment newer_than:{dias}d")

    for resumo in listagem.get("mensagens", []):
        with _lock:
            conexao = _obter_conexao()
            try:
                _selecionar(conexao, "todas")
                numero = _numero_pelo_id(conexao, resumo["id"])
            except InboxIndisponivel:
                continue
            status, dados = conexao.fetch(numero, "(BODY.PEEK[])")
        if status != "OK" or not dados or not isinstance(dados[0], tuple):
            continue

        for anexo in _partes_anexas(email.message_from_bytes(dados[0][1])):
            if not anexo["nome"].lower().endswith(".xml"):
                continue
            try:
                encontrados.append(anexo["conteudo"].decode("utf-8", errors="replace"))
            except Exception:
                continue
    return encontrados


# Tempo maximo de uma sessao IDLE. O servidor derruba por volta de 30
# minutos, entao renovamos antes disso.
IDLE_RENOVAR_SEGUNDOS = 25 * 60


def escutar_novas_mensagens(ao_chegar, parar=None) -> None:
    """Fica ouvindo a caixa e avisa quando chega mensagem nova.

    Usa IMAP IDLE: em vez de perguntar de tempos em tempos, o servidor
    empurra o aviso assim que a mensagem entra. A conexao e exclusiva
    porque em IDLE ela nao aceita outro comando.

    `ao_chegar` e chamado sem argumentos; quem decide o que fazer com a
    caixa e quem chamou. `parar` e uma funcao que, devolvendo True,
    encerra a escuta.
    """
    usuario, senha = credenciais_limpas()

    while not (parar and parar()):
        conexao = None
        try:
            conexao = _logar(usuario, senha)
            conexao.select("INBOX")
            # imaplib nao expoe IDLE; a conversa e simples o suficiente pra
            # falar na mao: manda IDLE, espera aviso, manda DONE.
            etiqueta = conexao._new_tag()
            conexao.send(b"%s IDLE\r\n" % etiqueta)
            conexao.readline()  # "+ idling"

            inicio = time.time()
            conexao.sock.settimeout(60)
            while not (parar and parar()):
                try:
                    linha = conexao.readline()
                except socket.timeout:
                    linha = b""
                # EXISTS e RECENT sao os avisos de mensagem nova.
                if b"EXISTS" in linha or b"RECENT" in linha:
                    conexao.send(b"DONE\r\n")
                    try:
                        conexao.readline()
                    except Exception:
                        pass
                    ao_chegar()
                    break
                if time.time() - inicio > IDLE_RENOVAR_SEGUNDOS:
                    conexao.send(b"DONE\r\n")
                    break
        except Exception as exc:
            logging.getLogger(__name__).info("escuta de e-mail caiu: %s", str(exc)[:150])
            time.sleep(30)
        finally:
            if conexao is not None:
                try:
                    conexao.logout()
                except Exception:
                    pass
