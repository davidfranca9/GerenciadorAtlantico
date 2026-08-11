"""Importa dados/CIDADES E UF.xlsx para a tabela cidades do Postgres.

Uso: python -m app.import_cidades
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from .database import Base, SessionLocal, engine
from .models import Cidade

XLSX_PATH = Path(__file__).resolve().parents[1] / "dados" / "CIDADES E UF.xlsx"


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Cidade).count() > 0:
            print("Tabela cidades ja possui dados, nada a fazer.")
            return

        wb = load_workbook(XLSX_PATH, read_only=True, data_only=True)
        ws = wb.active
        total = 0
        for row in ws.iter_rows(min_row=1, values_only=True):
            if not row or not row[0]:
                continue
            nome = str(row[0]).strip()
            uf = str(row[1]).strip().upper() if len(row) > 1 and row[1] else ""
            if not nome or not uf or len(uf) != 2:
                continue
            db.add(Cidade(nome=nome, uf=uf))
            total += 1
        db.commit()
        print(f"{total} cidades importadas com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
