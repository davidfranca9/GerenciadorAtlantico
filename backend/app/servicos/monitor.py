"""Quanto cada rotina automatica demorou, pra achar quem trava a API.

Em 25/09/2026 a API passou a engasgar em ondas (chamadas de meio segundo
virando 20 s por uns dois minutos). As rotinas rodam escondidas, entao sem
isto so dava pra adivinhar qual delas estava segurando o servidor.
"""
from __future__ import annotations

import contextlib
import itertools
import os
import time
from datetime import datetime
from threading import Lock

_lock = Lock()
_tarefas: dict[str, dict] = {}
_em_andamento: dict[int, tuple[str, float]] = {}
_sequencia = itertools.count(1)
LIGADO_EM = datetime.utcnow()


@contextlib.contextmanager
def executando(nome: str):
    """Marca a tarefa como em andamento enquanto ela roda: numa travada, e o
    que diz quem esta segurando o servidor."""
    chave = next(_sequencia)
    comecou = time.monotonic()
    with _lock:
        _em_andamento[chave] = (nome, comecou)
    try:
        yield comecou
    finally:
        with _lock:
            _em_andamento.pop(chave, None)


def registrar(nome: str, comecou_em: float, resultado=None, erro: str = "") -> None:
    """comecou_em e um time.monotonic() de antes da tarefa."""
    duracao = round(time.monotonic() - comecou_em, 2)
    agora = datetime.utcnow()
    with _lock:
        anterior = _tarefas.get(nome) or {}
        _tarefas[nome] = {
            "ultima": agora,
            "duracao_s": duracao,
            "resultado": resultado,
            "erro": (erro or "")[:300],
            "execucoes": (anterior.get("execucoes") or 0) + 1,
            "falhas": (anterior.get("falhas") or 0) + (1 if erro else 0),
            "pior_duracao_s": max(duracao, anterior.get("pior_duracao_s") or 0),
        }


def memoria_mb() -> float | None:
    """Memoria do processo (so Linux, que e onde ele roda)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as arquivo:
            for linha in arquivo:
                if linha.startswith("VmRSS:"):
                    return round(int(linha.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


def carga() -> list[float] | None:
    try:
        return [round(v, 2) for v in os.getloadavg()]
    except (AttributeError, OSError):
        return None


def estado() -> dict:
    agora = time.monotonic()
    with _lock:
        tarefas = {nome: dict(dados) for nome, dados in _tarefas.items()}
        rodando = [
            {"tarefa": nome, "ha_segundos": round(agora - comecou, 1)}
            for nome, comecou in _em_andamento.values()
        ]
    return {
        "ligado_em": LIGADO_EM,
        "agora": datetime.utcnow(),
        "memoria_mb": memoria_mb(),
        "carga": carga(),
        "rodando_agora": sorted(rodando, key=lambda t: -t["ha_segundos"]),
        "tarefas": tarefas,
    }
