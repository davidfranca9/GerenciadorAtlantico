"""Cria (ou atualiza) o primeiro usuario admin.

Uso: python -m app.seed_admin email@exemplo.com senha123 "Nome Completo"
"""
from __future__ import annotations

import sys

from .auth import hash_password
from .database import Base, SessionLocal, engine
from .models import User


def main():
    if len(sys.argv) < 3:
        print("Uso: python -m app.seed_admin <email> <senha> [nome]")
        raise SystemExit(1)

    email, password = sys.argv[1], sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else email

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, name=name, role="admin")
            db.add(user)
        user.hashed_password = hash_password(password)
        user.role = "admin"
        user.is_active = True
        db.commit()
        print(f"Usuario admin '{email}' criado/atualizado com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
