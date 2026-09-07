"""Roda o espelho e a emissao do CT-e contra o sistema em producao.

Existe pra tirar o trabalho manual: em vez de alguem preencher a tela a
cada tentativa, o agente roda isto e le a resposta do Bsoft direto.

Autenticacao: token de sessao lido de --token-file. Quando ele vence (12
horas), --credenciais aponta um JSON com usuario e senha pra renovar
sozinho. Os dois arquivos ficam FORA do repositorio e nada disso e
versionado.

Uso:
    python backend/scripts/cte.py espelho --xml nota.xml --tarifa 300 \
        --aliquota 12 --km 850 --agendamento 12
    python backend/scripts/cte.py emitir  --xml nota.xml ... [--definitivo]

Sem --definitivo, a emissao sai como RASCUNHO.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

API_PADRAO = "https://k13u69whhom0qhrvq180yckc.188.245.98.251.sslip.io"


def montar_campos(args) -> dict:
    campos = {
        "agendamento_id": args.agendamento,
        "tarifa_por_tonelada": args.tarifa,
        "aliquota_icms": args.aliquota,
        "km": args.km,
        "embalagem": args.embalagem,
        "forma_pagamento": args.forma_pagamento,
    }
    if args.especie:
        campos["especie_id"] = args.especie
    if args.endereco_remetente:
        campos["endereco_remetente_id"] = args.endereco_remetente
    if args.endereco_destinatario:
        campos["endereco_destinatario_id"] = args.endereco_destinatario
    if args.motorista:
        campos["motorista_id"] = args.motorista
    if args.conjunto:
        campos["conjunto_veiculos_id"] = args.conjunto
    for nome, valor in (("placa_cavalo", args.placa_cavalo),
                        ("placa_carreta1", args.placa_carreta1),
                        ("placa_carreta2", args.placa_carreta2)):
        if valor:
            campos[nome] = valor
    return {k: v for k, v in campos.items() if v not in (None, "")}


def token_expirado(token: str) -> bool:
    """Le o 'exp' do JWT sem validar assinatura, so pra saber se vale a pena
    tentar. Token vence em 12 horas."""
    import base64
    import time
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))["exp"] < time.time() + 60
    except Exception:
        return True


def fazer_login(args) -> str:
    """Troca usuario e senha por um token novo e o guarda no token-file.

    As credenciais ficam num arquivo fora do repositorio, informado por
    --credenciais. Sem ele, o script so usa o token que ja existir.
    """
    dados = json.loads(Path(args.credenciais).read_text(encoding="utf-8"))
    corpo = {"username": dados["usuario"], "password": dados["senha"]}
    resposta = requests.post(f"{args.api}/auth/login", data=corpo, timeout=args.timeout)
    resposta.raise_for_status()
    token = resposta.json()["access_token"]
    Path(args.token_file).write_text(token, encoding="utf-8")
    print("token renovado", file=sys.stderr)
    return token


def obter_token(args) -> str:
    caminho = Path(args.token_file)
    token = caminho.read_text(encoding="utf-8").strip() if caminho.exists() else ""
    if (not token or token_expirado(token)) and args.credenciais:
        return fazer_login(args)
    return token


def chamar(args, caminho: str, extras: dict) -> dict:
    token = obter_token(args)
    with open(args.xml, "rb") as arquivo:
        resposta = requests.post(
            f"{args.api}{caminho}",
            headers={"Authorization": f"Bearer {token}"},
            files={"arquivo": (Path(args.xml).name, arquivo, "text/xml")},
            data={**montar_campos(args), **extras},
            timeout=args.timeout,
        )
    print(f"HTTP {resposta.status_code}", file=sys.stderr)
    try:
        return resposta.json()
    except ValueError:
        return {"resposta_crua": resposta.text[:2000]}


def mostrar_espelho(dados: dict) -> None:
    if "detail" in dados:
        print("ERRO:", json.dumps(dados["detail"], ensure_ascii=False)[:800])
        return

    print("\n-- pendencias (bloqueiam) --")
    for item in dados.get("pendencias") or ["(nenhuma)"]:
        print("  *", item)
    print("\n-- avisos (nao bloqueiam) --")
    for item in dados.get("avisos") or ["(nenhum)"]:
        print("  *", item)

    print("\n-- partes --")
    for lado in ("remetente", "destinatario"):
        parte = (dados.get("partes") or {}).get(lado) or {}
        print(f"  {lado}: pessoa={parte.get('pessoa_id')} endereco={parte.get('endereco_id')} "
              f"{parte.get('aviso') or ''}")
        # Quando o endereco nao resolve, sao estas as opcoes pra escolher.
        if not parte.get("endereco_id"):
            for opcao in parte.get("enderecos") or []:
                print(f"      id={opcao.get('id')}  {opcao.get('descricao')}")
    print("  veiculos:", json.dumps(dados.get("veiculos"), ensure_ascii=False))

    print("\n-- payload --")
    print(json.dumps(dados.get("payload"), ensure_ascii=False, indent=1))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("acao", choices=["espelho", "emitir", "agendamentos", "configuracoes",
                                    "nfes", "baixar-nfe"])
    p.add_argument("--cadastro", default="", help="filtra a acao configuracoes")
    p.add_argument("--de", default="", help="dataInicio (AAAA-MM-DD) da acao nfes")
    p.add_argument("--ate", default="", help="dataFim da acao nfes, no maximo 3 meses depois")
    p.add_argument("--chave", default="", help="chave da NF-e da acao baixar-nfe")
    p.add_argument("--saida", default="", help="arquivo onde gravar o XML baixado")
    p.add_argument("--xml", default="", help="XML da NF-e")
    p.add_argument("--token-file", required=True, help="arquivo com o token da sessao")
    p.add_argument("--credenciais", default="",
                   help="JSON com usuario e senha, fora do repositorio; "
                        "usado pra renovar o token quando ele vence")
    p.add_argument("--agendamento", default="")
    p.add_argument("--tarifa", default="")
    p.add_argument("--aliquota", default="12")
    p.add_argument("--km", default="")
    p.add_argument("--embalagem", default="BIG BAG")
    p.add_argument("--especie", default="")
    p.add_argument("--forma-pagamento", dest="forma_pagamento", default="1")
    p.add_argument("--endereco-remetente", default="")
    p.add_argument("--endereco-destinatario", default="")
    p.add_argument("--motorista", default="")
    p.add_argument("--placa-cavalo", dest="placa_cavalo", default="")
    p.add_argument("--placa-carreta1", dest="placa_carreta1", default="")
    p.add_argument("--placa-carreta2", dest="placa_carreta2", default="")
    p.add_argument("--conjunto", default="",
                   help="id do conjunto de veiculos; a API exige valor, vazio nao passa")
    p.add_argument("--definitivo", action="store_true",
                   help="emite documento definitivo em vez de rascunho")
    p.add_argument("--api", default=API_PADRAO)
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()

    if args.acao == "nfes":
        # Acha uma NF-e que ainda nao virou CT-e: o Bsoft recusa a segunda
        # emissao sobre a mesma nota.
        resposta = requests.get(
            f"{args.api}/fiscal/nfes-recebidas",
            headers={"Authorization": f"Bearer {obter_token(args)}"},
            params={"data_inicio": args.de, "data_fim": args.ate},
            timeout=args.timeout,
        )
        print(json.dumps(resposta.json(), ensure_ascii=False, indent=1)[:3000])
        return 0

    if args.acao == "baixar-nfe":
        resposta = requests.get(
            f"{args.api}/fiscal/nfe-xml",
            headers={"Authorization": f"Bearer {obter_token(args)}"},
            params={"chave": args.chave},
            timeout=args.timeout,
        )
        dados = resposta.json()
        if not args.saida:
            print(json.dumps(dados, ensure_ascii=False)[:2000])
            return 0
        # O XML inteiro nao cabe na saida do terminal, entao vai pra arquivo
        # e o que se imprime e so a confirmacao.
        xml = dados["xml"][0]["xml"]["autorizacao"]
        Path(args.saida).write_text(xml, encoding="utf-8")
        print(f"XML gravado em {args.saida} ({len(xml)} caracteres)")
        return 0

    if args.acao == "configuracoes":
        # Le os cadastros do Bsoft que o CT-e referencia por id.
        resposta = requests.get(
            f"{args.api}/bsoft/configuracoes-cte",
            headers={"Authorization": f"Bearer {obter_token(args)}"},
            timeout=args.timeout,
        )
        dados = resposta.json()
        alvo = args.cadastro
        for nome, conteudo in (dados or {}).items():
            if alvo and alvo not in nome:
                continue
            print(f"\n== {nome} ==")
            print(json.dumps(conteudo, ensure_ascii=False, indent=1)[:2500])
        return 0

    if args.acao == "agendamentos":
        # Emitir exige um agendamento; esta acao existe pra achar o id.
        resposta = requests.get(
            f"{args.api}/agendamentos",
            headers={"Authorization": f"Bearer {obter_token(args)}"},
            timeout=args.timeout,
        )
        for item in (resposta.json() or [])[:15]:
            data = item.get("data_agendada") or item.get("loading_date") or "sem data"
            print(f"#{item.get('id')} {data} {item.get('driver_name') or 'sem motorista'} "
                  f"{item.get('plate_cavalo') or ''} {item.get('status') or ''}")
        return 0

    if not args.xml:
        p.error("--xml e obrigatorio para espelho e emitir")

    if args.acao == "espelho":
        dados = chamar(args, "/fiscal/espelho", {"buscar_partes": "true"})
        mostrar_espelho(dados)
        return 0

    extras = {"confirmar_emissao_real": "true"} if args.definitivo else {}
    dados = chamar(args, "/fiscal/emitir", extras)
    print(json.dumps(dados, ensure_ascii=False, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
