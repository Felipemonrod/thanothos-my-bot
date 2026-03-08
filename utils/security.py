import re
import unicodedata

# ====== Limites de Segurança ======
MAX_NOME_LENGTH = 100
MAX_EMOJI_LENGTH = 50
MAX_RESPOSTA_LENGTH = 200
MAX_EMOJIS_POR_ROTACAO = 20
MAX_RESPOSTAS = 20
MAX_CHUTE_LENGTH = 500

# ====== Padrões Perigosos ======

# Menções do Discord que podem pingam todos
DISCORD_MENTION_PATTERN = re.compile(
    r'@(everyone|here)', re.IGNORECASE
)

# Padrões de injeção de código e scripts
INJECTION_PATTERN = re.compile(
    r'(<script|javascript:|data:text/html|eval\s*\(|exec\s*\(|__import__\s*\('
    r'|os\.system|subprocess|import\s+os)',
    re.IGNORECASE
)


def _remover_controle(texto: str) -> str:
    """Remove caracteres de controle Unicode perigosos (mantém espaço, newline, tab)."""
    return ''.join(
        c for c in texto
        if unicodedata.category(c)[0] != 'C' or c in ('\n', '\t', ' ')
    )


def sanitizar_texto(texto: str, max_length: int = 200) -> str:
    """Remove caracteres perigosos e limita o tamanho do texto."""
    if not texto or not isinstance(texto, str):
        return ""
    texto = texto.replace('\x00', '')  # Remove null bytes
    texto = _remover_controle(texto)
    return texto[:max_length].strip()


def sanitizar_chute(chute: str) -> str:
    """Sanitiza entrada de chute do usuário (limita a 500 caracteres)."""
    return sanitizar_texto(chute, max_length=MAX_CHUTE_LENGTH)


def validar_nome(nome: str) -> tuple:
    """
    Valida nome de personagem.
    Retorna (valido: bool, mensagem_erro: str).
    """
    if not nome or not nome.strip():
        return False, "Nome não pode ser vazio."

    nome = nome.strip()

    if len(nome) > MAX_NOME_LENGTH:
        return False, f"Nome muito longo (máx. {MAX_NOME_LENGTH} caracteres)."

    if DISCORD_MENTION_PATTERN.search(nome):
        return False, "Nome não pode conter menções como `@everyone` ou `@here`."

    if INJECTION_PATTERN.search(nome):
        return False, "Nome contém padrões não permitidos."

    return True, ""


def validar_respostas(respostas: list) -> tuple:
    """
    Valida lista de respostas aceitas.
    Retorna (valido: bool, mensagem_erro: str).
    """
    if not respostas:
        return False, "É necessário ao menos uma resposta."

    if len(respostas) > MAX_RESPOSTAS:
        return False, f"Muitas respostas (máx. {MAX_RESPOSTAS})."

    for r in respostas:
        if not r.strip():
            continue
        if len(r) > MAX_RESPOSTA_LENGTH:
            return False, f"Resposta muito longa: `{r[:30]}...` (máx. {MAX_RESPOSTA_LENGTH} caracteres)."
        if DISCORD_MENTION_PATTERN.search(r):
            return False, "Respostas não podem conter menções como `@everyone` ou `@here`."
        if INJECTION_PATTERN.search(r):
            return False, "Resposta contém padrões não permitidos."

    return True, ""


def validar_emojis(emojis: list) -> tuple:
    """
    Valida lista de emojis.
    Retorna (valido: bool, mensagem_erro: str).
    """
    if not emojis:
        return False, "É necessário ao menos um emoji."

    if len(emojis) > MAX_EMOJIS_POR_ROTACAO:
        return False, f"Muitos emojis por rotação (máx. {MAX_EMOJIS_POR_ROTACAO})."

    for e in emojis:
        if len(e) > MAX_EMOJI_LENGTH:
            return False, f"Item muito longo para ser um emoji: `{e[:20]}...`"
        if INJECTION_PATTERN.search(e):
            return False, "Emoji contém padrões não permitidos."
        if DISCORD_MENTION_PATTERN.search(e):
            return False, "Emojis não podem conter menções."

    return True, ""
