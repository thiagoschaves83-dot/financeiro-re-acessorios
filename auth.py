"""Login simples de senha única — necessário porque o app deixou de ser só localhost.
Senha fica só como hash local, nunca em texto puro, e nunca passa por mim (o Thiago
define direto no navegador dele).

Hash via werkzeug.security (PBKDF2 salgado) — não é SHA-256 puro. SHA-256 sozinho é
rápido demais (bilhões de tentativas/segundo em GPU comum) pra resistir a força bruta
se o hash vazar; PBKDF2 é deliberadamente lento pra isso, e já vem junto do Flask,
sem dependência nova."""
import secrets
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

SENHA_HASH_PATH = Path(__file__).parent / "senha.hash"
SECRET_KEY_PATH = Path(__file__).parent / "secret.key"


def senha_definida() -> bool:
    return SENHA_HASH_PATH.exists()


def definir_senha(senha: str):
    SENHA_HASH_PATH.write_text(generate_password_hash(senha), encoding="utf-8")


def verificar_senha(senha: str) -> bool:
    if not senha_definida():
        return False
    return check_password_hash(SENHA_HASH_PATH.read_text(encoding="utf-8").strip(), senha)


# ---------- Bloqueio de tentativas erradas ----------
# Em memória (zera se o servidor reiniciar) — suficiente pra um app de usuário único.
# Importa porque, na nuvem, a senha deixa de estar blindada por rede privada.
MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 300  # 5 minutos

_tentativas = 0
_bloqueado_ate = 0.0


def pode_tentar_login() -> tuple[bool, int]:
    """(pode_tentar, segundos_restantes_se_bloqueado)"""
    import time

    agora = time.time()
    if agora < _bloqueado_ate:
        return False, int(_bloqueado_ate - agora)
    return True, 0


def registrar_falha_login():
    import time

    global _tentativas, _bloqueado_ate
    _tentativas += 1
    if _tentativas >= MAX_TENTATIVAS:
        _bloqueado_ate = time.time() + BLOQUEIO_SEGUNDOS
        _tentativas = 0


def registrar_sucesso_login():
    global _tentativas, _bloqueado_ate
    _tentativas = 0
    _bloqueado_ate = 0.0


def obter_secret_key() -> str:
    """Chave persistente pra sessão de login sobreviver a reinícios do servidor —
    gerada uma vez e guardada localmente, nunca é uma string fixa no código."""
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
    chave = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(chave, encoding="utf-8")
    return chave
