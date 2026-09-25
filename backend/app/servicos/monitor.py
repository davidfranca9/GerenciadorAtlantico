"""Quanto cada rotina automatica demorou, pra achar quem trava a API.

Em 25/09/2026 a API passou a engasgar em ondas (chamadas de meio segundo
virando 20 s por uns dois minutos). As rotinas rodam escondidas, entao sem
isto so dava pra adivinhar qual delas estava segurando o servidor.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from threading import Lock

_lock = Lock()
_tarefas: dict[str, dict] = {}
LIGADO_EM = datetime.utcnow()


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
    with _lock:
        tarefas = {nome: dict(dados) for nome, dados in _tarefas.items()}
    return {
        "ligado_em": LIGADO_EM,
        "agora": datetime.utcnow(),
        "memoria_mb": memoria_mb(),
        "carga": carga(),
        "tarefas": tarefas,
    }
