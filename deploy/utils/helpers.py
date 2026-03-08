import discord
import unicodedata
import re
import random

# ====== Constantes ======
CHANCE_MIX_RARO = 0.15  # 15% de chance de misturar emojis de rotações diferentes


# ====== Normalização e Matching ======

def normalizar_texto(texto: str) -> str:
    """Remove acentos, converte para minúsculo e limpa espaços extras."""
    texto = texto.lower().strip()
    nfkd = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def chute_corresponde(chute: str, respostas_aceitas: list) -> bool:
    """
    Verifica se o chute do usuário bate com alguma resposta aceita.
    - Case insensitive
    - Ignora acentos
    - Aceita a resposta mesmo dentro de uma frase
    """
    chute_normalizado = normalizar_texto(chute)

    # Ignora mensagens muito curtas (1 caractere) para evitar falsos positivos
    if len(chute_normalizado) < 2:
        return False

    for resposta in respostas_aceitas:
        resposta_normalizada = normalizar_texto(resposta)
        # Match exato
        if chute_normalizado == resposta_normalizada:
            return True
        # Match dentro de frase: usa word boundary para não pegar pedaços de palavras
        padrao = r'\b' + re.escape(resposta_normalizada) + r'\b'
        if re.search(padrao, chute_normalizado):
            return True

    return False


# ====== Emojis e Amon ======

def escolher_emojis(personagem: dict) -> list:
    """
    Escolhe quais emojis usar para a rodada.
    - Se só tem 1 rotação, usa ela.
    - Se tem várias, sorteia uma. Com 15% de chance, cria um mix raro.
    """
    rotacoes = personagem["emojis"]

    if len(rotacoes) == 1:
        return list(rotacoes[0])  # Cópia para não alterar o original

    # Mix raro: mistura emojis de rotações diferentes e embaralha a ordem
    if random.random() < CHANCE_MIX_RARO:
        todos_emojis = []
        for rot in rotacoes:
            todos_emojis.extend(rot)
        # Remove duplicatas mantendo a ordem, depois pega a quantidade da maior rotação
        vistos = set()
        unicos = []
        for e in todos_emojis:
            if e not in vistos:
                vistos.add(e)
                unicos.append(e)
        tamanho = max(len(r) for r in rotacoes)
        amostra = random.sample(unicos, min(tamanho, len(unicos)))
        random.shuffle(amostra)
        return amostra

    # Caso normal: sorteia uma rotação
    return list(random.choice(rotacoes))


def encontrar_amon(personagens: list):
    """Procura o personagem Amon na lista de personagens."""
    for pers in personagens:
        if pers["nome"].lower() == "amon":
            return pers
    return None


def gerar_evento_amon(personagem_vitima: dict, personagens: list):
    """
    Gera os emojis do evento Amon (parasita): pega os emojis de um personagem vítima
    e injeta 2 emojis do Amon em posições a partir da 2ª.
    O primeiro emoji é SEMPRE da vítima (o parasita se esconde atrás dela).
    Retorna a lista de emojis manipulados.
    """
    amon = encontrar_amon(personagens)
    if not amon:
        return None

    # Pega emojis da vítima (rotação aleatória)
    emojis_vitima = list(random.choice(personagem_vitima["emojis"]))

    # Pega emojis do Amon (rotação aleatória)
    emojis_amon = list(random.choice(amon["emojis"]))

    # Seleciona 2 emojis do Amon para injetar
    amon_injecao = random.sample(emojis_amon, min(2, len(emojis_amon)))

    # Substitui posições aleatórias, MAS NUNCA a posição 0 (primeiro emoji sempre da vítima)
    if len(emojis_vitima) >= 3:
        posicoes_disponiveis = list(range(1, len(emojis_vitima)))
        posicoes = random.sample(posicoes_disponiveis, min(2, len(posicoes_disponiveis)))
        for i, pos in enumerate(posicoes):
            emojis_vitima[pos] = amon_injecao[i % len(amon_injecao)]
    elif len(emojis_vitima) == 2:
        emojis_vitima[1] = amon_injecao[0]
    else:
        emojis_vitima.extend(amon_injecao)

    return emojis_vitima


# ====== Verificações de Permissão ======

def e_canal_permitido(obj, dados: dict) -> bool:
    """Verifica se o canal é permitido. Aceita ctx ou message."""
    if not dados["canais_permitidos"]:
        return True
    return obj.channel.id in dados["canais_permitidos"]


def tem_permissao_gerencia(ctx, dados: dict) -> bool:
    """Verifica se o usuário tem permissão de gerência."""
    if ctx.author.guild_permissions.administrator:
        return True
    cargos_usuario = [role.id for role in ctx.author.roles]
    for cargo_id in dados["cargos_permitidos"]:
        if cargo_id in cargos_usuario:
            return True
    return False


def e_canal_gerencia(ctx, dados: dict) -> bool:
    """Retorna True se o comando foi usado em um dos canais de gerência."""
    return ctx.channel.id in dados["canais_gerencia"]


def msg_canais_gerencia(dados: dict) -> str:
    """Retorna texto com os canais de gerência formatados para exibir no erro."""
    if dados["canais_gerencia"]:
        mencoes = ", ".join(f"<#{cid}>" for cid in dados["canais_gerencia"])
        return f"Este comando só pode ser usado nos canais de gerência: {mencoes}"
    return "Nenhum canal de gerência configurado! Peça a um admin para usar `#addgerencia <ID>`."


# ====== Mensagens Utilitárias ======

async def msg_sucesso(ctx, mensagem: str):
    embed = discord.Embed(description=f"✅ {mensagem}", color=0x2ECC71)
    await ctx.send(embed=embed)


async def msg_erro(ctx, mensagem: str):
    embed = discord.Embed(description=f"❌ {mensagem}", color=0xE74C3C)
    await ctx.send(embed=embed)


async def msg_aviso(ctx, mensagem: str):
    embed = discord.Embed(description=f"⚠️ {mensagem}", color=0xF1C40F)
    await ctx.send(embed=embed)
