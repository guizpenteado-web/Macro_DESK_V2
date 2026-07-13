"""Gerencia usuarios do login do Hub (admin/usuario) — mesma logica de
TestCarlao/scripts/manage_users.py, adaptada pra SQLite (o Hub nao usa MySQL).

Uso:
    python scripts/manage_hub_users.py add <username> [--role admin|user] [--nome "Nome"]
    python scripts/manage_hub_users.py deactivate <username>
    python scripts/manage_hub_users.py list
"""
import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bcrypt

from auth.schema import DB_PATH, init_db


def _connect() -> sqlite3.Connection:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_user(username: str, role: str, nome: str | None) -> None:
    password = getpass.getpass("Senha: ")
    confirm = getpass.getpass("Confirme a senha: ")
    if password != confirm:
        print("Senhas nao coincidem.")
        return
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = _connect()
    conn.execute(
        "INSERT INTO users (username, password_hash, nome, role, ativo) VALUES (?,?,?,?,1) "
        "ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, "
        "nome=excluded.nome, role=excluded.role, ativo=1",
        (username, pw_hash, nome or username, role),
    )
    conn.commit()
    conn.close()
    print(f"Usuario '{username}' criado/atualizado (role={role}).")


def deactivate_user(username: str) -> None:
    conn = _connect()
    conn.execute("UPDATE users SET ativo=0 WHERE username=?", (username,))
    conn.commit()
    conn.close()
    print(f"Usuario '{username}' desativado.")


def list_users() -> None:
    conn = _connect()
    rows = conn.execute(
        "SELECT username, nome, role, ativo, criado_em, ultimo_login FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    if not rows:
        print("Nenhum usuario cadastrado.")
        return
    for r in rows:
        status = "ativo" if r["ativo"] else "inativo"
        print(f"{r['username']:20} {r['role']:6} {status:8} ultimo_login={r['ultimo_login'] or '-'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("username")
    p_add.add_argument("--role", choices=["admin", "user"], default="user")
    p_add.add_argument("--nome", default=None)

    p_deact = sub.add_parser("deactivate")
    p_deact.add_argument("username")

    sub.add_parser("list")

    args = parser.parse_args()
    if args.action == "add":
        add_user(args.username, args.role, args.nome)
    elif args.action == "deactivate":
        deactivate_user(args.username)
    elif args.action == "list":
        list_users()
