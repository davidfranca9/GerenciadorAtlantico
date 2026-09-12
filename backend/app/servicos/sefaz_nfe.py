"""Baixa XML de NF-e direto da SEFAZ, com o certificado A1 da empresa.

Hoje as notas chegam por e-mail e o sistema depende disso pra emitir CT-e.
Aqui a fonte passa a ser o proprio servico de distribuicao da Receita
(NFeDistribuicaoDFe), que entrega os documentos de interesse do CNPJ.

O servico e SOAP com autenticacao mutua: o certificado nao vai no corpo,
ele autentica a conexao TLS. Por isso o .pfx precisa virar PEM em disco
por alguns instantes - escrito com permissao restrita e apagado depois.

Nada aqui assina documento nem emite: e so leitura.
"""
from __future__ import annotations

import base64
import gzip
import os
import re
import tempfile
from contextlib import contextmanager
from xml.etree import ElementTree

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from ..config import settings

# Ambiente nacional de producao. O de homologacao nao devolve documentos
# reais, entao nao serve nem pra conferir.
URL_DISTRIBUICAO = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
ACAO_SOAP = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
UF_AUTOR = "29"  # Bahia, onde a Atlantico esta estabelecida
AMBIENTE_PRODUCAO = "1"


class SefazIndisponivel(Exception):
    pass


class CertificadoAusente(SefazIndisponivel):
    pass


@contextmanager
def _certificado_em_pem():
    """Converte o .pfx em par de arquivos PEM temporarios.

    O `requests` so faz TLS mutuo com arquivos em disco. Eles sao criados
    com permissao 0600 e removidos no fim, mesmo se a chamada falhar.
    """
    caminho = settings.certificado_pfx_path
    if not caminho or not os.path.exists(caminho):
        raise CertificadoAusente(
            "Certificado A1 nao configurado (CERTIFICADO_PFX_PATH) ou arquivo nao encontrado"
        )

    with open(caminho, "rb") as arquivo:
        chave, certificado, cadeia = pkcs12.load_key_and_certificates(
            arquivo.read(), (settings.certificado_senha or "").encode()
        )
    if chave is None or certificado is None:
        raise CertificadoAusente("Nao foi possivel ler o certificado com a senha informada")

    pasta = tempfile.mkdtemp()
    arquivo_cert = os.path.join(pasta, "cert.pem")
    arquivo_chave = os.path.join(pasta, "chave.pem")
    try:
        blocos = [certificado.public_bytes(serialization.Encoding.PEM)]
        blocos += [c.public_bytes(serialization.Encoding.PEM) for c in (cadeia or [])]
        with open(os.open(arquivo_cert, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as f:
            f.write(b"".join(blocos))
        with open(os.open(arquivo_chave, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as f:
            f.write(chave.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        yield arquivo_cert, arquivo_chave
    finally:
        for caminho_temp in (arquivo_cert, arquivo_chave):
            try:
                os.remove(caminho_temp)
            except OSError:
                pass
        try:
            os.rmdir(pasta)
        except OSError:
            pass


def _envelope(cnpj: str, ultimo_nsu: str) -> str:
    """Monta o SOAP da consulta por NSU.

    O NSU e um contador sequencial da SEFAZ: pedindo a partir do ultimo
    conhecido, ela devolve so o que chegou depois - por isso vale guardar
    onde parou entre uma consulta e outra.
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body>"
        '<nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
        "<nfeDadosMsg>"
        f'<distDFeInt xmlns="{NS_NFE}" versao="1.01">'
        f"<tpAmb>{AMBIENTE_PRODUCAO}</tpAmb>"
        f"<cUFAutor>{UF_AUTOR}</cUFAutor>"
        f"<CNPJ>{cnpj}</CNPJ>"
        f"<distNSU><ultNSU>{ultimo_nsu.zfill(15)}</ultNSU></distNSU>"
        "</distDFeInt>"
        "</nfeDadosMsg>"
        "</nfeDistDFeInteresse>"
        "</soap12:Body>"
        "</soap12:Envelope>"
    )


def _envelope_por_chave(cnpj: str, chave: str) -> str:
    """Monta o SOAP da consulta de UMA nota, pela chave de acesso.

    Diferente da consulta por NSU, esta pode ser feita quando se quiser:
    nao consome a esteira sequencial nem cai na regra de uma hora.
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body>"
        '<nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
        "<nfeDadosMsg>"
        f'<distDFeInt xmlns="{NS_NFE}" versao="1.01">'
        f"<tpAmb>{AMBIENTE_PRODUCAO}</tpAmb>"
        f"<cUFAutor>{UF_AUTOR}</cUFAutor>"
        f"<CNPJ>{cnpj}</CNPJ>"
        f"<consChNFe><chNFe>{chave}</chNFe></consChNFe>"
        "</distDFeInt>"
        "</nfeDadosMsg>"
        "</nfeDistDFeInteresse>"
        "</soap12:Body>"
        "</soap12:Envelope>"
    )


def _descompactar(conteudo_base64: str) -> str:
    """Cada documento vem em base64 sobre gzip."""
    return gzip.decompress(base64.b64decode(conteudo_base64)).decode("utf-8", errors="replace")


def consultar_documentos(ultimo_nsu: str = "0", cnpj: str = "") -> dict:
    """LEITURA. Pede a SEFAZ os documentos de interesse do CNPJ.

    Devolve os XML ja descompactados. Documentos completos (procNFe) vem
    junto dos resumos (resNFe); o resumo e o que a SEFAZ entrega quando o
    documento completo ainda nao foi liberado pra este CNPJ.
    """
    cnpj = re.sub(r"\D", "", cnpj or settings.certificado_cnpj or "")
    if len(cnpj) != 14:
        raise SefazIndisponivel("Informe o CNPJ (14 digitos) do titular do certificado")

    return _enviar(_envelope(cnpj, str(ultimo_nsu)))


def consultar_por_chave(chave: str, cnpj: str = "") -> dict:
    """LEITURA. Baixa UMA nota pela chave de acesso, a qualquer momento.

    E a consulta sob demanda: nao mexe no ponteiro da esteira por NSU nem
    esbarra na regra de uma hora. Serve pra quando a chave ja e conhecida -
    pelo e-mail, pelo agendamento ou pelo proprio Bsoft.
    """
    chave = re.sub(r"\D", "", chave or "")
    if len(chave) != 44:
        raise SefazIndisponivel("Informe a chave de acesso da NF-e (44 digitos)")
    cnpj = re.sub(r"\D", "", cnpj or settings.certificado_cnpj or "")
    return _enviar(_envelope_por_chave(cnpj, chave))


def _enviar(corpo: str) -> dict:
    with _certificado_em_pem() as (cert, chave):
        try:
            resposta = requests.post(
                URL_DISTRIBUICAO,
                data=corpo.encode("utf-8"),
                headers={"Content-Type": f'application/soap+xml; charset=utf-8; action="{ACAO_SOAP}"'},
                cert=(cert, chave),
                timeout=settings.sefaz_timeout_segundos,
            )
        except requests.exceptions.RequestException as exc:
            raise SefazIndisponivel(f"Falha de rede ao consultar a SEFAZ: {exc}") from exc

    if resposta.status_code >= 400:
        raise SefazIndisponivel(f"SEFAZ respondeu {resposta.status_code}: {resposta.text[:300]}")

    raiz = ElementTree.fromstring(resposta.content)
    def texto(tag: str) -> str:
        achado = raiz.find(f".//{{{NS_NFE}}}{tag}")
        return (achado.text or "").strip() if achado is not None else ""

    documentos = []
    for doc in raiz.iter(f"{{{NS_NFE}}}docZip"):
        try:
            xml = _descompactar(doc.text or "")
        except Exception:
            continue
        documentos.append({
            "nsu": doc.attrib.get("NSU", ""),
            "schema": doc.attrib.get("schema", ""),
            "xml": xml,
        })

    return {
        "status": texto("cStat"),
        "motivo": texto("xMotivo"),
        "ultimo_nsu": texto("ultNSU"),
        "maximo_nsu": texto("maxNSU"),
        "documentos": documentos,
    }
