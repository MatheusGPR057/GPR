
import sqlite3
import hashlib
import secrets
import hmac
import json

from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gpr.db"

ITERACOES = 310_000


def conectar():
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def inicializar_seguranca():
    with conectar() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS credenciais (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                usuario TEXT NOT NULL,
                salt TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                iteracoes INTEGER NOT NULL,
                criado_em TEXT NOT NULL
            )
        """)

        conexao.execute("""
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                responsavel TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                acao TEXT NOT NULL,
                entidade TEXT NOT NULL,
                registro_id INTEGER,
                parceria_id INTEGER,
                antes_json TEXT,
                depois_json TEXT,
                detalhes TEXT
            )
        """)


def existe_credencial():
    with conectar() as conexao:
        resultado = conexao.execute(
            "SELECT id FROM credenciais WHERE id = 1"
        ).fetchone()

    return resultado is not None


def criar_credencial(usuario, senha):
    usuario = usuario.strip()

    if not usuario:
        raise ValueError("Informe um nome de usuário.")

    if len(senha) < 12:
        raise ValueError("A senha deve possuir pelo menos 12 caracteres.")

    salt = secrets.token_bytes(32)

    senha_hash = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt,
        ITERACOES
    )

    with conectar() as conexao:
        existente = conexao.execute(
            "SELECT id FROM credenciais WHERE id = 1"
        ).fetchone()

        if existente:
            raise ValueError("Já existe uma credencial cadastrada.")

        conexao.execute("""
            INSERT INTO credenciais
            (id, usuario, salt, senha_hash, iteracoes, criado_em)
            VALUES (1, ?, ?, ?, ?, ?)
        """, (
            usuario,
            salt.hex(),
            senha_hash.hex(),
            ITERACOES,
            datetime.now().isoformat(timespec="seconds")
        ))


def verificar_login(usuario, senha):
    with conectar() as conexao:
        credencial = conexao.execute("""
            SELECT usuario, salt, senha_hash, iteracoes
            FROM credenciais
            WHERE id = 1
        """).fetchone()

    if not credencial:
        return False

    if not hmac.compare_digest(
        usuario.strip(),
        credencial["usuario"]
    ):
        return False

    salt = bytes.fromhex(credencial["salt"])

    tentativa = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt,
        credencial["iteracoes"]
    )

    return hmac.compare_digest(
        tentativa.hex(),
        credencial["senha_hash"]
    )


def registrar_auditoria(
    responsavel,
    acao,
    entidade,
    registro_id=None,
    parceria_id=None,
    antes=None,
    depois=None,
    detalhes=None
):
    if not responsavel or not responsavel.strip():
        raise ValueError("Informe o responsável pela operação.")

    antes_json = (
        json.dumps(antes, ensure_ascii=False, default=str)
        if antes is not None else None
    )

    depois_json = (
        json.dumps(depois, ensure_ascii=False, default=str)
        if depois is not None else None
    )

    with conectar() as conexao:
        conexao.execute("""
            INSERT INTO auditoria (
                responsavel,
                data_hora,
                acao,
                entidade,
                registro_id,
                parceria_id,
                antes_json,
                depois_json,
                detalhes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            responsavel.strip(),
            datetime.now().isoformat(timespec="seconds"),
            acao,
            entidade,
            registro_id,
            parceria_id,
            antes_json,
            depois_json,
            detalhes
        ))


def consultar_auditoria(parceria_id=None, limite=500):
    with conectar() as conexao:
        if parceria_id is None:
            resultado = conexao.execute("""
                SELECT * FROM auditoria
                ORDER BY id DESC
                LIMIT ?
            """, (limite,)).fetchall()
        else:
            resultado = conexao.execute("""
                SELECT * FROM auditoria
                WHERE parceria_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (parceria_id, limite)).fetchall()

    return [dict(linha) for linha in resultado]
