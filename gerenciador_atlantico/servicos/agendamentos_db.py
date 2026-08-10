from __future__ import annotations

import sqlite3
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


STATUS_AGENDAMENTO = (
    "Aguardando Agendamento",
    "Agendado",
    "Cancelado",
    "Carregou",
)


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def get_agendamentos_db_path() -> Path:
    data_dir = _project_root() / "dados"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "agendamentos.db"

    if getattr(sys, "frozen", False) and not db_path.exists():
        bundle_db = Path(getattr(sys, "_MEIPASS", "")) / "dados" / "agendamentos.db"
        if bundle_db.exists():
            shutil.copy2(bundle_db, db_path)

    return db_path


@contextmanager
def _connect():
    conn = sqlite3.connect(get_agendamentos_db_path())
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_columns(conn, table_name: str, columns: dict[str, str]):
    existing = {
        str(row["name"]).strip()
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, definition in columns.items():
        if column_name in existing:
            continue
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_agendamentos_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                supplier TEXT NOT NULL,
                loading_date TEXT,
                driver_name TEXT,
                driver_cpf TEXT,
                driver_phone TEXT,
                cnh TEXT,
                plate_cavalo TEXT,
                plate_carreta1 TEXT,
                plate_carreta2 TEXT,
                total_items INTEGER NOT NULL DEFAULT 0,
                total_tons REAL NOT NULL DEFAULT 0,
                pedidos TEXT,
                clientes TEXT,
                produtos TEXT,
                roteiro TEXT,
                localizador TEXT,
                contato_cliente TEXT,
                email_subject TEXT,
                email_recipients TEXT,
                oc_pdf_path TEXT,
                planilha_path TEXT
            );

            CREATE TABLE IF NOT EXISTS agendamento_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agendamento_id INTEGER NOT NULL,
                pedido TEXT,
                cliente TEXT,
                produto TEXT,
                cidade TEXT,
                embalagem TEXT,
                toneladas REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_agendamentos_status
            ON agendamentos (status);

            CREATE INDEX IF NOT EXISTS idx_agendamentos_loading_date
            ON agendamentos (loading_date);

            CREATE INDEX IF NOT EXISTS idx_agendamentos_plate
            ON agendamentos (plate_cavalo);
            """
        )
        _ensure_columns(
            conn,
            "agendamentos",
            {
                "roteiro": "TEXT",
                "localizador": "TEXT",
                "contato_cliente": "TEXT",
            },
        )


def _safe_float(value) -> float:
    try:
        if value in ("", None):
            return 0.0
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _join_unique(items):
    ordered = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ", ".join(ordered)


def registrar_agendamento_email(data: dict) -> int:
    init_agendamentos_db()

    items = list(data.get("items") or [])
    created_at = datetime.now().isoformat(timespec="seconds")
    total_tons = sum(_safe_float(item.get("toneladas")) for item in items)

    pedidos = _join_unique(item.get("pedido") or item.get("contrato") for item in items)
    clientes = _join_unique(item.get("cliente") for item in items)
    produtos = _join_unique(item.get("produto") for item in items)

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agendamentos (
                created_at,
                updated_at,
                status,
                supplier,
                loading_date,
                driver_name,
                driver_cpf,
                driver_phone,
                cnh,
                plate_cavalo,
                plate_carreta1,
                plate_carreta2,
                total_items,
                total_tons,
                pedidos,
                clientes,
                produtos,
                roteiro,
                localizador,
                contato_cliente,
                email_subject,
                email_recipients,
                oc_pdf_path,
                planilha_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                created_at,
                "Aguardando Agendamento",
                str(data.get("supplier") or "").strip() or "Fertimax",
                str(data.get("loading_date") or "").strip(),
                str(data.get("driver_name") or "").strip(),
                str(data.get("driver_cpf") or "").strip(),
                str(data.get("driver_phone") or "").strip(),
                str(data.get("cnh") or "").strip(),
                str(data.get("plate_cavalo") or "").strip(),
                str(data.get("plate_carreta1") or "").strip(),
                str(data.get("plate_carreta2") or "").strip(),
                len(items),
                total_tons,
                pedidos,
                clientes,
                produtos,
                str(data.get("roteiro") or "").strip(),
                str(data.get("localizador") or "").strip(),
                str(data.get("contato_cliente") or "").strip(),
                str(data.get("email_subject") or "").strip(),
                ", ".join(data.get("email_recipients") or []),
                str(data.get("oc_pdf_path") or "").strip(),
                str(data.get("planilha_path") or "").strip(),
            ),
        )
        agendamento_id = int(cursor.lastrowid)

        if items:
            conn.executemany(
                """
                INSERT INTO agendamento_itens (
                    agendamento_id,
                    pedido,
                    cliente,
                    produto,
                    cidade,
                    embalagem,
                    toneladas
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        agendamento_id,
                        str(item.get("pedido") or item.get("contrato") or "").strip(),
                        str(item.get("cliente") or "").strip(),
                        str(item.get("produto") or "").strip(),
                        str(item.get("cidade") or "").strip(),
                        str(item.get("embalagem") or "").strip(),
                        _safe_float(item.get("toneladas")),
                    )
                    for item in items
                ],
            )

        return agendamento_id


def listar_agendamentos():
    init_agendamentos_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                created_at,
                updated_at,
                status,
                supplier,
                loading_date,
                driver_name,
                driver_cpf,
                driver_phone,
                cnh,
                plate_cavalo,
                plate_carreta1,
                plate_carreta2,
                total_items,
                total_tons,
                pedidos,
                clientes,
                produtos,
                roteiro,
                localizador,
                contato_cliente,
                email_subject,
                email_recipients,
                oc_pdf_path,
                planilha_path
            FROM agendamentos
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def listar_itens_agendamento(agendamento_id: int):
    init_agendamentos_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                pedido,
                cliente,
                produto,
                cidade,
                embalagem,
                toneladas
            FROM agendamento_itens
            WHERE agendamento_id = ?
            ORDER BY id
            """,
            (agendamento_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def atualizar_status_agendamento(agendamento_id: int, status: str):
    if status not in STATUS_AGENDAMENTO:
        raise ValueError(f"Status invalido: {status}")

    init_agendamentos_db()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE agendamentos
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, datetime.now().isoformat(timespec="seconds"), agendamento_id),
        )


def atualizar_dados_internos_agendamento(
    agendamento_id: int,
    roteiro: str = "",
    contato_cliente: str = "",
):
    init_agendamentos_db()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE agendamentos
            SET roteiro = ?, contato_cliente = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(roteiro or "").strip(),
                str(contato_cliente or "").strip(),
                datetime.now().isoformat(timespec="seconds"),
                agendamento_id,
            ),
        )
