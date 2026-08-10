from __future__ import annotations

import sqlite3
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def get_fretes_db_path() -> Path:
    data_dir = _project_root() / "dados"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "fretes.db"

    if getattr(sys, "frozen", False) and not db_path.exists():
        bundle_db = Path(getattr(sys, "_MEIPASS", "")) / "dados" / "fretes.db"
        if bundle_db.exists():
            shutil.copy2(bundle_db, db_path)

    return db_path


@contextmanager
def _connect():
    conn = sqlite3.connect(get_fretes_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_fretes_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cotacoes_frete (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_cotacao TEXT NOT NULL,
                destino TEXT NOT NULL,
                valor_tonelada REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cotacoes_frete_destino
            ON cotacoes_frete (destino);

            CREATE INDEX IF NOT EXISTS idx_cotacoes_frete_data
            ON cotacoes_frete (data_cotacao);
            """
        )


def cadastrar_cotacao_frete(data_cotacao: str, destino: str, valor_tonelada: float) -> int:
    init_fretes_db()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO cotacoes_frete (
                data_cotacao,
                destino,
                valor_tonelada,
                created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                data_cotacao.strip(),
                destino.strip(),
                float(valor_tonelada),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)


def listar_cotacoes_frete(destino: str | None = None):
    init_fretes_db()
    query = """
        SELECT
            id,
            data_cotacao,
            destino,
            valor_tonelada,
            created_at
        FROM cotacoes_frete
    """
    params = []
    if destino:
        query += " WHERE UPPER(destino) = UPPER(?)"
        params.append(destino.strip())
    query += " ORDER BY substr(data_cotacao, 7, 4) DESC, substr(data_cotacao, 4, 2) DESC, substr(data_cotacao, 1, 2) DESC, id DESC"

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def buscar_ultima_cotacao_por_destino(destino: str):
    resultados = listar_cotacoes_frete(destino)
    return resultados[0] if resultados else None
