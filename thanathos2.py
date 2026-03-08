import discord
from discord.ext import commands
import asyncio
import random
import json
import os
import unicodedata
import re

# ================= Configurações Iniciais =================
DADOS_FILE = 'dados_jogo.json'

dados = {
    "canais_gerencia": [],
    "canais_permitidos": [],
    "cargos_permitidos": [],
    "personagens": []
}

def carregar_dados():
    global dados
    if os.path.exists(DADOS_FILE):
        with open(DADOS_FILE, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        # Retrocompatibilidade: garante que a chave existe em JSONs antigos
        if "canais_gerencia" not in dados:
            dados["canais_gerencia"] = []
            salvar_dados()
        # Retrocompatibilidade: migra emojis de lista simples para lista de rotações
        migrou = False
        for pers in dados["personagens"]:
            if pers["emojis"] and not isinstance(pers["emojis"][0], list):
                pers["emojis"] = [pers["emojis"]]  # Envolve a lista única em uma rotação
                migrou = True
        if migrou:
            salvar_dados()
    else:
        salvar_dados()

def salvar_dados():
    with open(DADOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

carregar_dados() # Carrega os dados salvos quando o bot ligar

# Lendo o token de um txt
try:
    with open("token.txt", "r", encoding="utf-8") as f:
        TOKEN = f.read().strip()
except FileNotFoundError:
    print("❌ Arquivo token.txt não encontrado! Crie o arquivo e cole o token do bot dentro dele.")
    exit()

# ================= Configuração do Bot =================
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='#', intents=intents)
bot.remove_command('help') # Remove o comando de ajuda padrão do discord.py para o seu funcionar

jogos_ativos = {}

# ====== Sistema de Streaks (Combo de acertos consecutivos) ======
# Formato: { guild_id: { "user_id": int, "streak": int } }
streaks = {}

def registrar_streak(guild_id, user_id):
    """Registra um acerto e retorna o streak atual do jogador."""
    if guild_id in streaks and streaks[guild_id]["user_id"] == user_id:
        streaks[guild_id]["streak"] += 1
    else:
        streaks[guild_id] = {"user_id": user_id, "streak": 1}
    return streaks[guild_id]["streak"]

def gerar_texto_streak(streak):
    """Gera o texto visual do combo baseado na quantidade de acertos."""
    if streak < 2:
        return None  # Sem combo ainda
    if streak == 2:
        return "🔥 **Combo x2!** Dois acertos seguidos!"
    elif streak == 3:
        return "🔥🔥 **Combo x3!** Está pegando fogo!"
    elif streak == 4:
        return "🔥🔥🔥 **Combo x4!** Imparável!"
    elif streak == 5:
        return "⚡🔥 **Combo x5!** Cinco seguidos! Monstruoso!"
    elif streak <= 7:
        return f"⚡🔥🔥 **Combo x{streak}!** Ninguém para esse jogador!"
    elif streak <= 10:
        return f"💥⚡🔥 **Combo x{streak}!** Sequência lendária!"
    else:
        return f"👑💥⚡🔥 **COMBO x{streak}!!** Dominação absoluta!"

# ================= Sistema de Confronto (Duelo 1v1) =================

confrontos_ativos = {}  # { canal_id: Confronto }

class AceitarConfrontoView(discord.ui.View):
    """Botões para aceitar ou recusar um desafio de confronto."""
    def __init__(self, desafiante, desafiado, rodadas):
        super().__init__(timeout=60)
        self.desafiante = desafiante
        self.desafiado = desafiado
        self.rodadas = rodadas
        self.aceito = None

    @discord.ui.button(label="⚔️ Aceitar", style=discord.ButtonStyle.success)
    async def aceitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.desafiado.id:
            await interaction.response.send_message("Apenas o desafiado pode aceitar!", ephemeral=True)
            return
        self.aceito = True
        self.stop()
        embed = discord.Embed(
            title="⚔️ Desafio Aceito!",
            description=(
                f"{self.desafiado.mention} aceitou o confronto contra {self.desafiante.mention}!\n\n"
                "Preparem-se... O duelo vai começar!"
            ),
            color=0x2ECC71
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.desafiado.id:
            await interaction.response.send_message("Apenas o desafiado pode recusar!", ephemeral=True)
            return
        self.aceito = False
        self.stop()
        embed = discord.Embed(
            title="❌ Desafio Recusado",
            description=f"{self.desafiado.mention} recusou o confronto.",
            color=0xE74C3C
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        self.aceito = False
        self.stop()


class EscolherRodadasView(discord.ui.View):
    """Botões para o desafiante escolher a quantidade de rodadas."""
    def __init__(self, autor):
        super().__init__(timeout=30)
        self.autor = autor
        self.rodadas = None

    @discord.ui.button(label="⚔️ Melhor de 3", style=discord.ButtonStyle.primary)
    async def md3(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Apenas quem desafiou pode escolher!", ephemeral=True)
            return
        self.rodadas = 3
        self.stop()
        await interaction.response.edit_message(view=None)

    @discord.ui.button(label="⚔️ Melhor de 5", style=discord.ButtonStyle.primary)
    async def md5(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Apenas quem desafiou pode escolher!", ephemeral=True)
            return
        self.rodadas = 5
        self.stop()
        await interaction.response.edit_message(view=None)

    @discord.ui.button(label="⚔️ Melhor de 7", style=discord.ButtonStyle.primary)
    async def md7(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Apenas quem desafiou pode escolher!", ephemeral=True)
            return
        self.rodadas = 7
        self.stop()
        await interaction.response.edit_message(view=None)

    async def on_timeout(self):
        self.stop()


class Confronto:
    """Gerencia um duelo 1v1 entre dois jogadores."""
    def __init__(self, bot, canal, jogador1, jogador2, max_rodadas=3):
        self.bot = bot
        self.canal = canal
        self.jogador1 = jogador1  # desafiante
        self.jogador2 = jogador2  # desafiado
        self.placar = {jogador1.id: 0, jogador2.id: 0}
        self.rodada_atual = 0
        self.max_rodadas = max_rodadas
        self.vitorias_necessarias = (max_rodadas // 2) + 1  # 3→2, 5→3, 7→4
        self.max_rodadas_original = max_rodadas  # Para controlar extensão
        self.personagem_atual = None
        self.emojis_atual = []
        self.indice_dica = 1
        self.tempo_espera = 20
        self.rodada_ativa = False
        self.task_rodada = None
        self.terminado = False

    def e_jogador(self, user_id):
        return user_id in (self.jogador1.id, self.jogador2.id)

    def _barra_placar(self):
        p1 = self.placar[self.jogador1.id]
        p2 = self.placar[self.jogador2.id]
        return f"**{self.jogador1.display_name}** `{p1}` ⚔️ `{p2}` **{self.jogador2.display_name}**"

    async def iniciar(self):
        await asyncio.sleep(3)
        await self.proxima_rodada()

    async def proxima_rodada(self):
        if self.terminado:
            return

        # Checar se alguém já venceu
        for uid, pontos in self.placar.items():
            if pontos >= self.vitorias_necessarias:
                await self.finalizar(uid)
                return

        self.rodada_atual += 1

        # Após esgotar todas as rodadas sem vencedor — estende +2 rodadas
        if self.rodada_atual > self.max_rodadas:
            self.max_rodadas += 2
            self.vitorias_necessarias = (self.max_rodadas // 2) + 1
            embed = discord.Embed(
                title="🔄 Empate! Extensão!",
                description=(
                    f"O confronto continua! Agora é **melhor de {self.max_rodadas}** (primeiro a **{self.vitorias_necessarias}**)!\n\n"
                    f"{self._barra_placar()}"
                ),
                color=0xF1C40F
            )
            await self.canal.send(embed=embed)
            await asyncio.sleep(3)

        # Se já passou do limite estendido, quem tiver mais pontos vence
        if self.rodada_atual > self.max_rodadas:
            p1 = self.placar[self.jogador1.id]
            p2 = self.placar[self.jogador2.id]
            if p1 > p2:
                await self.finalizar(self.jogador1.id)
            elif p2 > p1:
                await self.finalizar(self.jogador2.id)
            else:
                await self.finalizar(None)
            return

        # Sorteia personagem para esta rodada
        personagem = random.choice(dados["personagens"])
        self.personagem_atual = personagem
        self.emojis_atual = escolher_emojis(personagem)
        self.indice_dica = 1
        self.rodada_ativa = True

        # Anúncio da rodada
        embed = discord.Embed(
            title=f"⚔️ Rodada {self.rodada_atual}",
            description=(
                f"{self._barra_placar()}\n\n"
                "Preparem-se... As dicas estão chegando!"
            ),
            color=0xE67E22
        )
        await self.canal.send(embed=embed)
        await asyncio.sleep(2)

        # Inícia as dicas
        self.task_rodada = self.bot.loop.create_task(self.loop_dicas_confronto())

    async def enviar_dica_confronto(self):
        emojis_atuais = "".join(self.emojis_atual[:self.indice_dica])
        total_emojis = len(self.emojis_atual)
        embed = discord.Embed(
            title="⚔️ Adivinhe o Personagem!",
            description=(
                f"**Dica {self.indice_dica} de {total_emojis}**\n\n"
                f"> ## {emojis_atuais}"
            ),
            color=0xE67E22
        )
        embed.set_footer(text=f"Rodada {self.rodada_atual} • Apenas {self.jogador1.display_name} e {self.jogador2.display_name} podem responder")
        await self.canal.send(embed=embed)

    async def loop_dicas_confronto(self):
        try:
            await self.enviar_dica_confronto()
            while self.indice_dica < len(self.emojis_atual):
                await asyncio.sleep(self.tempo_espera)
                if not self.rodada_ativa:
                    return
                self.indice_dica += 1
                await self.enviar_dica_confronto()

            await asyncio.sleep(self.tempo_espera)

            if self.rodada_ativa:
                self.rodada_ativa = False
                embed = discord.Embed(
                    title="⏰ Tempo Esgotado!",
                    description=f"Ninguém acertou nessa rodada! Nenhum ponto distribuído.\n\n{self._barra_placar()}",
                    color=0xFF0000
                )
                await self.canal.send(embed=embed)
                await asyncio.sleep(3)
                await self.proxima_rodada()
        except asyncio.CancelledError:
            pass

    async def processar_chute(self, message):
        """Processa um chute no modo confronto. Retorna True se foi consumido."""
        if not self.rodada_ativa or self.terminado:
            return False
        if not self.e_jogador(message.author.id):
            return False

        if chute_corresponde(message.content, self.personagem_atual["respostas_aceitas"]):
            self.rodada_ativa = False
            if self.task_rodada and not self.task_rodada.done():
                self.task_rodada.cancel()

            self.placar[message.author.id] += 1

            embed = discord.Embed(
                title="✅ Ponto!",
                description=(
                    f"{message.author.mention} acertou! **+1 ponto** 🎯\n\n"
                    f"{self._barra_placar()}"
                ),
                color=0x2ECC71
            )
            await message.reply(embed=embed)
            await asyncio.sleep(3)
            await self.proxima_rodada()
            return True

        return False

    async def finalizar(self, vencedor_id):
        """Encerra o confronto e anuncia o resultado."""
        self.terminado = True
        self.rodada_ativa = False
        if self.task_rodada and not self.task_rodada.done():
            self.task_rodada.cancel()
        confrontos_ativos.pop(self.canal.id, None)

        p1 = self.placar[self.jogador1.id]
        p2 = self.placar[self.jogador2.id]

        if vencedor_id is None:
            embed = discord.Embed(
                title="🤝 Empate Total!",
                description=(
                    f"O confronto terminou empatado!\n\n"
                    f"**Placar Final:**\n{self._barra_placar()}"
                ),
                color=0x95A5A6
            )
        else:
            vencedor = self.jogador1 if vencedor_id == self.jogador1.id else self.jogador2
            embed = discord.Embed(
                title="🏆 Fim do Confronto!",
                description=(
                    f"🌟 {vencedor.mention} **venceu o duelo!** 🌟\n\n"
                    f"**Placar Final:**\n{self._barra_placar()}"
                ),
                color=0xFFD700
            )

        await self.canal.send(embed=embed)


# ====== Handler de erros de comandos ======
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            description=f"⚠️ Faltou argumento: **{error.param.name}**\nUse `#help` para ver como usar o comando.",
            color=0xF1C40F
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignora comandos inexistentes
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            description="❌ Argumento inválido. Verifique o formato do comando.",
            color=0xE74C3C
        )
        await ctx.send(embed=embed)
    else:
        # Erro inesperado: mostra no Discord e no console
        print(f"❌ Erro no comando #{ctx.command}: {error}")
        embed = discord.Embed(
            description="❌ Ocorreu um erro ao executar o comando.",
            color=0xE74C3C
        )
        await ctx.send(embed=embed)

CHANCE_MIX_RARO = 0.15  # 15% de chance de misturar emojis de rotações diferentes
CHANCE_AMON = 0.01     # 1% de chance do evento Amon (o Enganador)

# ====== Dados sutis para o modo Amon ======
# Maioria dos títulos são normais — apenas alguns têm erros BEM sutis
AMON_TITULOS = [
    "🎯 Adivinhe o Personagem!",
    "🎯 Adivinhe o Personagem!",
    "🎯 Adivinhe o Personagem!",
    "🎯 Adivinhe o Personagem!",
    "🎯 Adivinhe o Personagen!",    # m→n (bem sutil)
    "🎯 Adivinhe o Pesonagem!",     # falta o 'r' (sutil)
]

# Footers quase todos normais
AMON_FOOTERS = [
    "Digite sua resposta no chat! • Use #dica para acelerar",
    "Digite sua resposta no chat! • Use #dica para acelerar",
    "Digite sua resposta no chat! • Use #dica para acelerar",
    "Digite sua resposta no chat! • Use #dica para acelerar",
    "Digite sua resposta no chat! • Use #dica para acelarar",   # sutil
]

AMON_FRASES_ESCAPE = [
    "*\"Você realmente achou que eu era tão simples de decifrar? Eu sou **Amon**, o Enganador. Cada pista que você seguiu... fui eu que coloquei lá.\"* 🧐😈",
    "*\"Pathético. Você olhou para as dicas e viu exatamente o que eu queria que você visse. Eu sou **Amon**... e você nunca me pegou.\"* 👁️",
    "*\"Oh, tão perto... e tão longe. A identidade que você acertou? Eu a roubei há tempos. Eu sou **Amon**, e este rosto nunca foi meu.\"* 🎭",
    "*\"Impressionante... que você caiu. Cada erro nas dicas era um aviso, e mesmo assim você escolheu o caminho errado. Eu sou **Amon**.\"* 🦇",
]
CHANCE_FRASE_AMON = 0.35  # 35% de chance da frase dramática aparecer (senão fica genérica)

def encontrar_amon():
    """Procura o personagem Amon na lista de personagens."""
    for pers in dados["personagens"]:
        if pers["nome"].lower() == "amon":
            return pers
    return None

def gerar_evento_amon(personagem_vitima):
    """
    Gera os emojis do evento Amon (parasita): pega os emojis de um personagem vítima
    e injeta 2 emojis do Amon em posições a partir da 2ª.
    O primeiro emoji é SEMPRE da vítima (o parasita se esconde atrás dela).
    Retorna a lista de emojis manipulados.
    """
    amon = encontrar_amon()
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
        # Posições disponíveis: 1 em diante (protege o índice 0)
        posicoes_disponiveis = list(range(1, len(emojis_vitima)))
        posicoes = random.sample(posicoes_disponiveis, min(2, len(posicoes_disponiveis)))
        for i, pos in enumerate(posicoes):
            emojis_vitima[pos] = amon_injecao[i % len(amon_injecao)]
    elif len(emojis_vitima) == 2:
        # Só pode injetar na posição 1
        emojis_vitima[1] = amon_injecao[0]
    else:
        # Se a vítima só tem 1 emoji, adiciona os do Amon depois
        emojis_vitima.extend(amon_injecao)
    
    return emojis_vitima

def escolher_emojis(personagem):
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

class JogoEmoji:
    def __init__(self, bot, canal, personagem, emojis_rodada, modo_amon=False, vitima_disfarce=None):
        self.bot = bot
        self.canal = canal
        self.personagem = personagem
        self.emojis = emojis_rodada
        self.modo_amon = modo_amon
        self.vitima_disfarce = vitima_disfarce  # Personagem que o Amon está imitando
        self.indice_dica = 1 
        self.tempo_espera = 20 
        self.task_dica = bot.loop.create_task(self.loop_dicas())
        
    async def enviar_dica(self):
        emojis_atuais = "".join(self.emojis[:self.indice_dica])
        total_emojis = len(self.emojis)

        if self.modo_amon:
            # Sutileza: título e footer quase sempre normais
            titulo = random.choice(AMON_TITULOS)
            footer = random.choice(AMON_FOOTERS)
            # Contagem: correta na maioria, ±1 de vez em quando
            erro_dica = random.choices([0, 0, 0, 0, 1, -1], k=1)[0]
            erro_total = random.choices([0, 0, 0, 0, 0, 1], k=1)[0]
            dica_falsa = max(1, self.indice_dica + erro_dica)
            total_falso = max(1, total_emojis + erro_total)
            texto_dica = f"**Dica {dica_falsa} de {total_falso}**"
            # Cor praticamente idêntica ao verde normal
            cor = random.choice([0x00FF00, 0x00FF00, 0x00FF00, 0x00FE01, 0x01FF00])
        else:
            titulo = "🎯 Adivinhe o Personagem!"
            footer = "Digite sua resposta no chat! • Use !dica para acelerar"
            texto_dica = f"**Dica {self.indice_dica} de {total_emojis}**"
            cor = 0x00FF00

        embed = discord.Embed(
            title=titulo,
            description=(
                f"{texto_dica}\n\n"
                f"> ## {emojis_atuais}"
            ),
            color=cor
        )
        embed.set_footer(text=footer)
        await self.canal.send(embed=embed)

    async def loop_dicas(self):
        try:
            await self.enviar_dica()
            while self.indice_dica < len(self.emojis):
                await asyncio.sleep(self.tempo_espera)
                self.indice_dica += 1
                await self.enviar_dica()
            
            await asyncio.sleep(self.tempo_espera)

            embed_fim = discord.Embed(
                title="⏰ Tempo Esgotado!",
                description="Ninguém acertou dessa vez... Quem será que era? 🤔",
                color=0xFF0000
            )
            await self.canal.send(embed=embed_fim)
            encerrar_jogo(self.canal.id)
            
        except asyncio.CancelledError:
            pass

def encerrar_jogo(canal_id):
    jogo = jogos_ativos.pop(canal_id, None)
    if jogo and not jogo.task_dica.done():
        jogo.task_dica.cancel()

# ====== Verificações ======

def normalizar_texto(texto):
    """Remove acentos, converte para minúsculo e limpa espaços extras."""
    texto = texto.lower().strip()
    # Remove acentos: é→e, ç→c, ã→a, etc.
    nfkd = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))

def chute_corresponde(chute, respostas_aceitas):
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
        # Ex: "eu acho que é o klein" casa com "klein", mas "kleiner" não
        padrao = r'\b' + re.escape(resposta_normalizada) + r'\b'
        if re.search(padrao, chute_normalizado):
            return True

    return False

def e_canal_permitido(ctx):
    if not dados["canais_permitidos"]:
        return True
    return ctx.channel.id in dados["canais_permitidos"]

def tem_permissao_gerencia(ctx):
    # O dono do servidor ou administrador sempre pode
    if ctx.author.guild_permissions.administrator:
        return True
    
    # Se o usuario tiver um dos cargos permitidos
    cargos_usuario = [role.id for role in ctx.author.roles]
    for cargo_id in dados["cargos_permitidos"]:
        if cargo_id in cargos_usuario:
            return True
            
    return False

async def msg_sucesso(ctx, mensagem):
    embed = discord.Embed(description=f"✅ {mensagem}", color=0x2ECC71) 
    await ctx.send(embed=embed)

async def msg_erro(ctx, mensagem):
    embed = discord.Embed(description=f"❌ {mensagem}", color=0xE74C3C) 
    await ctx.send(embed=embed)

async def msg_aviso(ctx, mensagem):
    embed = discord.Embed(description=f"⚠️ {mensagem}", color=0xF1C40F) 
    await ctx.send(embed=embed)

def e_canal_gerencia(ctx):
    """Retorna True se o comando foi usado em um dos canais de gerência."""
    return ctx.channel.id in dados["canais_gerencia"]

def msg_canais_gerencia():
    """Retorna texto com os canais de gerência formatados para exibir no erro."""
    if dados["canais_gerencia"]:
        mencoes = ", ".join(f"<#{cid}>" for cid in dados["canais_gerencia"])
        return f"Este comando só pode ser usado nos canais de gerência: {mencoes}"
    return "Nenhum canal de gerência configurado! Peça a um admin para usar `#addgerencia <ID>`."

# ================= Comandos de Gerência de Canais Admin =================

@bot.command()
async def addgerencia(ctx, canal_id: int):
    """(Admin) Adiciona um canal à lista de canais de gerência."""
    if not ctx.author.guild_permissions.administrator:
        await msg_erro(ctx, "Apenas **administradores do servidor** podem configurar canais de gerência.")
        return

    if canal_id not in dados["canais_gerencia"]:
        dados["canais_gerencia"].append(canal_id)
        salvar_dados()
        await msg_sucesso(ctx, f"Canal <#{canal_id}> adicionado como canal de gerência!")
    else:
        await msg_aviso(ctx, "Este canal já é um canal de gerência.")

@bot.command()
async def rmgerencia(ctx, canal_id: int):
    """(Admin) Remove um canal da lista de canais de gerência."""
    if not ctx.author.guild_permissions.administrator:
        await msg_erro(ctx, "Apenas **administradores do servidor** podem configurar canais de gerência.")
        return

    if canal_id in dados["canais_gerencia"]:
        dados["canais_gerencia"].remove(canal_id)
        salvar_dados()
        await msg_sucesso(ctx, f"Canal <#{canal_id}> removido dos canais de gerência.")
    else:
        await msg_aviso(ctx, "Este canal não está na lista de gerência.")

# ================= Comandos de Gerenciamento =================

@bot.command()
async def addcanal(ctx, canal_id: int):
    """(Admin) Autoriza um canal a ter o bot funcinando"""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return
        
    if canal_id not in dados["canais_permitidos"]:
        dados["canais_permitidos"].append(canal_id)
        salvar_dados()
        await msg_sucesso(ctx, f"Canal <#{canal_id}> adicionado aos canais permitidos.")
    else:
        await msg_aviso(ctx, "Este canal já está na lista.")

@bot.command()
async def addcargo(ctx, cargo: discord.Role):
    """(Admin) Autoriza um cargo a adicionar personagens e canais"""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not ctx.author.guild_permissions.administrator:
        await msg_erro(ctx, "Apenas **administradores do servidor** podem adicionar cargos de gerência.")
        return
        
    if cargo.id not in dados["cargos_permitidos"]:
        dados["cargos_permitidos"].append(cargo.id)
        salvar_dados()
        await msg_sucesso(ctx, f"Cargo **{cargo.name}** adicionado! Quem tiver ele poderá gerenciar o jogo.")
    else:
        await msg_aviso(ctx, "Este cargo já tem permissão.")

@bot.command()
async def addpersonagem(ctx, nome: str, emojis: str, respostas: str):
    """
    (Admin) Adiciona um novo personagem.
    Uso: #addpersonagem "Nome" "🦇, 👨, 🌃" "batman, bruce wayne"
    """
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return
        
    # Separação estrita por vírgula como antes
    emojis_sujos = emojis.split(',')

    # Limpa espaços vazios invisíveis e descarta itens em branco (pra caso de , , sem querer)
    lista_emojis = [e.strip() for e in emojis_sujos if e.strip()]
    
    lista_respostas = [r.strip().lower() for r in respostas.split(',')]
    
    if not lista_emojis:
        await msg_erro(ctx, "Não consegui identificar nenhum emoji. Digite pelo menos um.")
        return

    novo_pers = {
        "nome": nome,
        "emojis": [lista_emojis],  # Primeira rotação
        "respostas_aceitas": lista_respostas
    }
    
    dados["personagens"].append(novo_pers)
    salvar_dados()
    await msg_sucesso(ctx, f"O personagem **{nome}** foi salvo com sucesso! ({len(lista_emojis)} emojis na rotação 1, {len(lista_respostas)} respostas)")

@bot.command()
async def rmcanal(ctx, canal_id: int):
    """(Admin) Remove um canal da lista de permitidos"""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return
        
    if canal_id in dados["canais_permitidos"]:
        dados["canais_permitidos"].remove(canal_id)
        salvar_dados()
        await msg_sucesso(ctx, f"Canal <#{canal_id}> removido dos canais permitidos.")
    else:
        await msg_aviso(ctx, "Este canal não está na lista.")

@bot.command()
async def rmcargo(ctx, cargo: discord.Role):
    """(Admin) Remove a permissão de um cargo"""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not ctx.author.guild_permissions.administrator:
        await msg_erro(ctx, "Apenas **administradores do servidor** podem remover cargos de gerência.")
        return
        
    if cargo.id in dados["cargos_permitidos"]:
        dados["cargos_permitidos"].remove(cargo.id)
        salvar_dados()
        await msg_sucesso(ctx, f"Cargo **{cargo.name}** removido! Seus membros não terão mais permissões especiais.")
    else:
        await msg_aviso(ctx, "Este cargo não tinha permissão.")

@bot.command()
async def rmpersonagem(ctx, *, nome: str):
    """(Admin) Remove um personagem exato pelo nome"""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return
        
    nome_procurado = nome.lower().strip()
    encontrado = None
    
    for pers in dados["personagens"]:
        if pers["nome"].lower() == nome_procurado:
            encontrado = pers
            break
            
    if encontrado:
        dados["personagens"].remove(encontrado)
        salvar_dados()
        await msg_sucesso(ctx, f"🗑️ O personagem **{encontrado['nome']}** foi permanentemente removido!")
    else:
        await msg_erro(ctx, f"Não encontrei nenhum personagem com o nome exato: **{nome}**")

@bot.command()
async def help(ctx):
    """Exibe a lista de comandos disponíveis."""

    # --- Embed 1: Comandos do Jogo ---
    embed_jogo = discord.Embed(
        title="🎮 Thanathos Bot — Comandos",
        description="Bem-vindo ao jogo de adivinhar personagens por emojis!",
        color=0x3498DB
    )
    embed_jogo.add_field(
        name="🎯 Jogo",
        value=(
            "> `#iniciar` — Inicia um novo desafio\n"
            "> `#dica` — Pula o timer e revela a próxima dica\n"
            "> `#confronto @usuário` — Desafie alguém para um duelo 1v1"
        ),
        inline=False
    )

    # --- Embed 2: Gerência ---
    embed_gerencia = discord.Embed(
        title="⚙️ Gerenciamento",
        description="*Disponível apenas nos canais de gerência, para admins e cargos autorizados.*",
        color=0xE67E22
    )
    embed_gerencia.add_field(
        name="📝 Personagens",
        value=(
            "> `#addpersonagem \"Nome\" \"emojis\" \"respostas\"`\n"
            "> `#rmpersonagem Nome exato`\n"
            "> `#editemoji` — Editor interativo de emojis\n"
            "> `#search Nome` — Busca personagem (editar/deletar)\n"
            "> `#listar` — Lista todos os personagens"
        ),
        inline=False
    )
    embed_gerencia.add_field(
        name="📺 Canais",
        value=(
            "> `#addcanal <ID>` — Libera canal para jogar\n"
            "> `#rmcanal <ID>` — Bloqueia canal"
        ),
        inline=True
    )
    embed_gerencia.add_field(
        name="👥 Cargos",
        value=(
            "> `#addcargo @Cargo` — Dá permissão\n"
            "> `#rmcargo @Cargo` — Remove permissão"
        ),
        inline=True
    )

    # --- Embed 3: Administrador ---
    embed_admin = discord.Embed(
        title="🔒 Administrador do Servidor",
        description="*Comandos exclusivos para administradores. Funcionam em qualquer canal.*",
        color=0xE74C3C
    )
    embed_admin.add_field(
        name="🛡️ Canais de Gerência",
        value=(
            "> `#addgerencia <ID>` — Define canal de gerência\n"
            "> `#rmgerencia <ID>` — Remove canal de gerência"
        ),
        inline=False
    )
    embed_admin.set_footer(text="Prefixo: #  •  Thanathos Bot")

    await ctx.send(embeds=[embed_jogo, embed_gerencia, embed_admin])

# ================= Sistema de Listagem Paginada =================

POR_PAGINA = 5  # Quantos personagens por página (listar + editor)

class ListarView(discord.ui.View):
    """View paginada para listar personagens com botões de navegação."""
    def __init__(self, autor, pagina=0):
        super().__init__(timeout=120)
        self.autor = autor
        self.pagina = pagina
        self._atualizar_botoes()

    def _construir_paginas(self):
        paginas = []
        linhas = []
        for i, pers in enumerate(dados["personagens"], 1):
            num_rotacoes = len(pers["emojis"])
            rotacoes_txt = []
            for idx_r, rot in enumerate(pers["emojis"], 1):
                rotacoes_txt.append(f">    R{idx_r}: {' '.join(rot)}")
            respostas = ", ".join(pers["respostas_aceitas"])
            bloco_rotacoes = "\n".join(rotacoes_txt)
            linhas.append(f"**{i}. {pers['nome']}** ({num_rotacoes} rotações)\n{bloco_rotacoes}\n> Respostas: `{respostas}`")
            if i % POR_PAGINA == 0:
                paginas.append("\n\n".join(linhas))
                linhas = []
        if linhas:
            paginas.append("\n\n".join(linhas))
        return paginas

    def gerar_embed(self):
        paginas = self._construir_paginas()
        total_paginas = max(1, len(paginas))
        if self.pagina >= total_paginas:
            self.pagina = total_paginas - 1
        conteudo = paginas[self.pagina] if paginas else "Nenhum personagem cadastrado."
        embed = discord.Embed(
            title=f"📋 Personagens Cadastrados ({len(dados['personagens'])} total)",
            description=conteudo,
            color=0x9B59B6
        )
        embed.set_footer(text=f"Página {self.pagina + 1}/{total_paginas}")
        return embed

    def _atualizar_botoes(self):
        total_paginas = max(1, (len(dados["personagens"]) + POR_PAGINA - 1) // POR_PAGINA)
        self.btn_anterior.disabled = (self.pagina <= 0)
        self.btn_proximo.disabled = (self.pagina >= total_paginas - 1)

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
    async def btn_anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode navegar.", ephemeral=True)
            return
        self.pagina = max(0, self.pagina - 1)
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.gerar_embed(), view=self)

    @discord.ui.button(label="Próxima ▶", style=discord.ButtonStyle.secondary)
    async def btn_proximo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode navegar.", ephemeral=True)
            return
        total_paginas = max(1, (len(dados["personagens"]) + POR_PAGINA - 1) // POR_PAGINA)
        self.pagina = min(total_paginas - 1, self.pagina + 1)
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.gerar_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

@bot.command()
async def listar(ctx):
    """Lista todos os personagens cadastrados com seus emojis e respostas."""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return

    if not dados["personagens"]:
        await msg_aviso(ctx, "Nenhum personagem cadastrado ainda! Use `#addpersonagem` para adicionar.")
        return

    view = ListarView(ctx.author)
    await ctx.send(embed=view.gerar_embed(), view=view)

# ================= Sistema de Edição de Emojis (Paginado) =================

class EditEmojiView(discord.ui.View):
    """View principal: paginação + dropdown para selecionar personagem."""
    def __init__(self, autor, pagina=0):
        super().__init__(timeout=120)
        self.autor = autor
        self.pagina = pagina
        self.total_paginas = max(1, (len(dados["personagens"]) + POR_PAGINA - 1) // POR_PAGINA)
        self._atualizar_componentes()

    def _atualizar_componentes(self):
        self.clear_items()

        # --- Dropdown de personagens da página atual ---
        inicio = self.pagina * POR_PAGINA
        fim = inicio + POR_PAGINA
        personagens_pagina = dados["personagens"][inicio:fim]

        opcoes = []
        for i, pers in enumerate(personagens_pagina, start=inicio + 1):
            emojis_preview = " ".join(pers["emojis"][0][:3]) if pers["emojis"] else "?"
            num_rot = len(pers["emojis"])
            label = f"{i}. {pers['nome']}"
            if len(label) > 100:
                label = label[:97] + "..."
            opcoes.append(discord.SelectOption(
                label=label,
                description=f"{num_rot} rotações • {emojis_preview}"[:100],
                value=str(i - 1)
            ))

        dropdown = PersonagemSelect(opcoes, self.autor)
        self.add_item(dropdown)

        # --- Botão Voltar (só aparece se não for a primeira página) ---
        if self.pagina > 0:
            btn_voltar = discord.ui.Button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
            btn_voltar.callback = self._voltar_pagina
            self.add_item(btn_voltar)

        # --- Botão Avançar (só aparece se não for a última página) ---
        if self.pagina < self.total_paginas - 1:
            btn_avancar = discord.ui.Button(label="Próxima ▶", style=discord.ButtonStyle.secondary)
            btn_avancar.callback = self._avancar_pagina
            self.add_item(btn_avancar)

        # --- Botão Cancelar ---
        btn_cancelar = discord.ui.Button(label="✖ Cancelar", style=discord.ButtonStyle.danger)
        btn_cancelar.callback = self._cancelar
        self.add_item(btn_cancelar)

    def _gerar_embed(self):
        inicio = self.pagina * POR_PAGINA
        fim = inicio + POR_PAGINA
        personagens_pagina = dados["personagens"][inicio:fim]

        linhas = []
        for i, pers in enumerate(personagens_pagina, start=inicio + 1):
            rot_preview = " ".join(pers["emojis"][0]) if pers["emojis"] else "?"
            num_rot = len(pers["emojis"])
            linhas.append(f"**{i}.** {pers['nome']}  —  R1: {rot_preview}  ({num_rot} rot.)")

        embed = discord.Embed(
            title="✏️ Editar Emojis — Selecione o Personagem",
            description="\n".join(linhas),
            color=0xE67E22
        )
        embed.set_footer(text=f"Página {self.pagina + 1}/{self.total_paginas} • Selecione no menu abaixo")
        return embed

    async def _voltar_pagina(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        self.pagina -= 1
        self._atualizar_componentes()
        await interaction.response.edit_message(embed=self._gerar_embed(), view=self)

    async def _avancar_pagina(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        self.pagina += 1
        self._atualizar_componentes()
        await interaction.response.edit_message(embed=self._gerar_embed(), view=self)

    async def _cancelar(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        embed = discord.Embed(description="❌ Edição cancelada.", color=0xE74C3C)
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    async def on_timeout(self):
        pass  # A mensagem fica, mas os botões expiram silenciosamente


class PersonagemSelect(discord.ui.Select):
    """Dropdown para escolher qual personagem editar."""
    def __init__(self, opcoes, autor):
        super().__init__(placeholder="Escolha o personagem para editar...", options=opcoes)
        self.autor = autor

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        indice = int(self.values[0])
        pers = dados["personagens"][indice]

        rotacoes_txt = []
        for idx_r, rot in enumerate(pers["emojis"], 1):
            rotacoes_txt.append(f"> **R{idx_r}:** {' '.join(rot)}")
        embed = discord.Embed(
            title=f"✏️ Editando: {pers['nome']}",
            description=(
                f"**Rotações de emojis ({len(pers['emojis'])}):**\n"
                + "\n".join(rotacoes_txt) +
                "\n\nEscolha o que deseja fazer:"
            ),
            color=0xE67E22
        )

        view = EdicaoEmojiView(self.autor, indice)
        await interaction.response.edit_message(embed=embed, view=view)


class EdicaoEmojiView(discord.ui.View):
    """View com opções de edição dos emojis de um personagem específico."""
    def __init__(self, autor, indice_personagem):
        super().__init__(timeout=120)
        self.autor = autor
        self.indice = indice_personagem

    def _pers(self):
        return dados["personagens"][self.indice]

    @discord.ui.button(label="🔄 Substituir Rotação", style=discord.ButtonStyle.primary)
    async def substituir_todos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        pers = self._pers()
        num_rot = len(pers["emojis"])

        if num_rot == 1:
            rotacao_idx = 0
        else:
            rotacoes_txt = "\n".join(f"`{i+1}.` {' '.join(r)}" for i, r in enumerate(pers["emojis"]))
            embed_escolha = discord.Embed(
                title=f"🔄 Qual rotação substituir? ({pers['nome']})",
                description=f"{rotacoes_txt}\n\n📝 **Digite o número da rotação.**\n⏱️ 60 segundos.",
                color=0x3498DB
            )
            await interaction.response.edit_message(embed=embed_escolha, view=None)

            def check(m):
                return m.author.id == self.autor.id and m.channel.id == interaction.channel.id
            try:
                msg = await interaction.client.wait_for('message', check=check, timeout=60)
                if not msg.content.strip().isdigit() or int(msg.content.strip()) < 1 or int(msg.content.strip()) > num_rot:
                    await interaction.channel.send(embed=discord.Embed(description="❌ Número inválido. Operação cancelada.", color=0xE74C3C))
                    return
                rotacao_idx = int(msg.content.strip()) - 1
            except asyncio.TimeoutError:
                await interaction.channel.send(embed=discord.Embed(description="⏰ Tempo esgotado!", color=0xE74C3C))
                return

        antigos = " ".join(pers["emojis"][rotacao_idx])

        embed = discord.Embed(
            title=f"🔄 Substituir R{rotacao_idx+1} de: {pers['nome']}",
            description=(
                f"**Emojis atuais:** {antigos}\n\n"
                "📝 **Digite os novos emojis separados por vírgula.**\n"
                "Exemplo: `🦇, 👨, 🌃, 🏙️`\n\n"
                "⏱️ Você tem **60 segundos**."
            ),
            color=0x3498DB
        )
        if num_rot == 1:
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.channel.send(embed=embed)

        def check2(m):
            return m.author.id == self.autor.id and m.channel.id == interaction.channel.id

        try:
            msg = await interaction.client.wait_for('message', check=check2, timeout=60)
            novos_emojis = [e.strip() for e in msg.content.split(',') if e.strip()]

            if not novos_emojis:
                await interaction.channel.send(embed=discord.Embed(description="❌ Nenhum emoji detectado. Cancelado.", color=0xE74C3C))
                return

            pers["emojis"][rotacao_idx] = novos_emojis
            salvar_dados()

            await interaction.channel.send(embed=discord.Embed(
                title=f"✅ R{rotacao_idx+1} atualizada: {pers['nome']}",
                description=f"**Antes:** {antigos}\n**Agora:** {' '.join(novos_emojis)}",
                color=0x2ECC71
            ))
        except asyncio.TimeoutError:
            await interaction.channel.send(embed=discord.Embed(description="⏰ Tempo esgotado!", color=0xE74C3C))

    @discord.ui.button(label="➕ Nova Rotação", style=discord.ButtonStyle.success)
    async def adicionar_rotacao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        pers = self._pers()
        embed = discord.Embed(
            title=f"➕ Nova rotação para: {pers['nome']}",
            description=(
                f"Este personagem já tem **{len(pers['emojis'])}** rotação(s).\n\n"
                "📝 **Digite os emojis da nova rotação, separados por vírgula.**\n"
                "Exemplo: `🗡️, 🛡️, 🎭, 🔥`\n\n"
                "⏱️ Você tem **60 segundos**."
            ),
            color=0x2ECC71
        )
        await interaction.response.edit_message(embed=embed, view=None)

        def check(m):
            return m.author.id == self.autor.id and m.channel.id == interaction.channel.id

        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60)
            novos = [e.strip() for e in msg.content.split(',') if e.strip()]

            if not novos:
                await interaction.channel.send(embed=discord.Embed(description="❌ Nenhum emoji detectado. Cancelado.", color=0xE74C3C))
                return

            pers["emojis"].append(novos)
            salvar_dados()

            await interaction.channel.send(embed=discord.Embed(
                title=f"✅ Rotação {len(pers['emojis'])} adicionada: {pers['nome']}",
                description=f"**Nova R{len(pers['emojis'])}:** {' '.join(novos)}",
                color=0x2ECC71
            ))
        except asyncio.TimeoutError:
            await interaction.channel.send(embed=discord.Embed(description="⏰ Tempo esgotado!", color=0xE74C3C))

    @discord.ui.button(label="🗑️ Remover Rotação", style=discord.ButtonStyle.danger)
    async def remover_rotacao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        pers = self._pers()
        if len(pers["emojis"]) <= 1:
            await interaction.response.send_message("O personagem precisa ter pelo menos 1 rotação!", ephemeral=True)
            return

        rotacoes_txt = "\n".join(f"`{i+1}.` {' '.join(r)}" for i, r in enumerate(pers["emojis"]))
        embed = discord.Embed(
            title=f"🗑️ Remover rotação de: {pers['nome']}",
            description=f"**Rotações atuais:**\n{rotacoes_txt}\n\n📝 **Digite o número da rotação a remover.**\n⏱️ 60 segundos.",
            color=0xE74C3C
        )
        await interaction.response.edit_message(embed=embed, view=None)

        def check(m):
            return m.author.id == self.autor.id and m.channel.id == interaction.channel.id

        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60)
            if not msg.content.strip().isdigit():
                await interaction.channel.send(embed=discord.Embed(description="❌ Digite apenas o número.", color=0xE74C3C))
                return
            num = int(msg.content.strip())
            if num < 1 or num > len(pers["emojis"]):
                await interaction.channel.send(embed=discord.Embed(description=f"❌ Número inválido (1-{len(pers['emojis'])}).", color=0xE74C3C))
                return
            if len(pers["emojis"]) <= 1:
                await interaction.channel.send(embed=discord.Embed(description="❌ Não posso remover a única rotação!", color=0xE74C3C))
                return

            removida = pers["emojis"].pop(num - 1)
            salvar_dados()

            await interaction.channel.send(embed=discord.Embed(
                title=f"✅ Rotação removida: {pers['nome']}",
                description=f"**Removida:** {' '.join(removida)}\n**Rotações restantes:** {len(pers['emojis'])}",
                color=0x2ECC71
            ))
        except asyncio.TimeoutError:
            await interaction.channel.send(embed=discord.Embed(description="⏰ Tempo esgotado!", color=0xE74C3C))

    @discord.ui.button(label="↩ Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        view = EditEmojiView(self.autor)
        await interaction.response.edit_message(embed=view._gerar_embed(), view=view)


@bot.command()
async def editemoji(ctx):
    """(Admin) Edita os emojis de um personagem com interface interativa."""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return
    if not dados["personagens"]:
        await msg_aviso(ctx, "Nenhum personagem cadastrado! Use `#addpersonagem` primeiro.")
        return

    view = EditEmojiView(ctx.author)
    await ctx.send(embed=view._gerar_embed(), view=view)

# ================= Sistema de Busca de Personagens =================

class SearchResultView(discord.ui.View):
    """View exibida ao encontrar um personagem: mostra detalhes + botões Editar/Deletar."""
    def __init__(self, autor, indice_personagem):
        super().__init__(timeout=120)
        self.autor = autor
        self.indice = indice_personagem

    def _pers(self):
        return dados["personagens"][self.indice]

    def _gerar_embed(self):
        pers = self._pers()
        rotacoes_txt = []
        for idx_r, rot in enumerate(pers["emojis"], 1):
            rotacoes_txt.append(f"> **R{idx_r}:** {' '.join(rot)}")
        respostas = ", ".join(pers["respostas_aceitas"])
        embed = discord.Embed(
            title=f"🔍 {pers['nome']}",
            description=(
                f"**Rotações de emojis ({len(pers['emojis'])}):**\n"
                + "\n".join(rotacoes_txt) +
                f"\n\n**Respostas aceitas:** `{respostas}`\n\n"
                "Escolha o que deseja fazer:"
            ),
            color=0x9B59B6
        )
        return embed

    @discord.ui.button(label="✏️ Editar Emojis", style=discord.ButtonStyle.primary)
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        view = EdicaoEmojiView(self.autor, self.indice)
        pers = self._pers()
        rotacoes_txt = []
        for idx_r, rot in enumerate(pers["emojis"], 1):
            rotacoes_txt.append(f"> **R{idx_r}:** {' '.join(rot)}")
        embed = discord.Embed(
            title=f"✏️ Editando: {pers['nome']}",
            description=(
                f"**Rotações de emojis ({len(pers['emojis'])}):**\n"
                + "\n".join(rotacoes_txt) +
                "\n\nEscolha o que deseja fazer:"
            ),
            color=0xE67E22
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🗑️ Deletar", style=discord.ButtonStyle.danger)
    async def deletar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        pers = self._pers()
        view = ConfirmarDeleteView(self.autor, self.indice)
        embed = discord.Embed(
            title=f"⚠️ Confirmar exclusão",
            description=(
                f"Tem certeza que deseja **deletar permanentemente** o personagem **{pers['nome']}**?\n\n"
                f"Esta ação não pode ser desfeita!"
            ),
            color=0xE74C3C
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="↩ Voltar", style=discord.ButtonStyle.secondary)
    async def voltar_busca(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🔍 Buscar Personagem",
            description="Busca encerrada.",
            color=0x95A5A6
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class ConfirmarDeleteView(discord.ui.View):
    """View de confirmação para deletar personagem."""
    def __init__(self, autor, indice_personagem):
        super().__init__(timeout=30)
        self.autor = autor
        self.indice = indice_personagem

    @discord.ui.button(label="✅ Sim, deletar", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        if self.indice >= len(dados["personagens"]):
            await interaction.response.edit_message(
                embed=discord.Embed(description="❌ Personagem já foi removido.", color=0xE74C3C), view=None)
            return
        pers = dados["personagens"].pop(self.indice)
        salvar_dados()
        embed = discord.Embed(
            title="🗑️ Personagem Removido",
            description=f"O personagem **{pers['nome']}** foi deletado permanentemente.",
            color=0xE74C3C
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        # Volta pra tela do personagem
        view = SearchResultView(self.autor, self.indice)
        await interaction.response.edit_message(embed=view._gerar_embed(), view=view)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class SearchSelectView(discord.ui.View):
    """Dropdown para escolher entre múltiplos resultados de busca."""
    def __init__(self, autor, resultados):
        super().__init__(timeout=60)
        self.autor = autor
        # resultados = lista de (indice_global, personagem)
        opcoes = []
        for idx_global, pers in resultados[:25]:  # Discord limita a 25 opções
            emojis_preview = " ".join(pers["emojis"][0][:3]) if pers["emojis"] else "?"
            label = pers["nome"]
            if len(label) > 100:
                label = label[:97] + "..."
            opcoes.append(discord.SelectOption(
                label=label,
                description=f"{len(pers['emojis'])} rotações • {emojis_preview}"[:100],
                value=str(idx_global)
            ))
        dropdown = SearchDropdown(opcoes, self.autor)
        self.add_item(dropdown)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class SearchDropdown(discord.ui.Select):
    """Dropdown de seleção dos resultados de busca."""
    def __init__(self, opcoes, autor):
        super().__init__(placeholder="Selecione o personagem...", options=opcoes)
        self.autor = autor

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        indice = int(self.values[0])
        view = SearchResultView(self.autor, indice)
        await interaction.response.edit_message(embed=view._gerar_embed(), view=view)


@bot.command()
async def search(ctx, *, nome: str = None):
    """(Admin) Busca um personagem por nome para editar ou deletar.
    Uso: #search klein
    """
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return

    if not nome or not nome.strip():
        await msg_aviso(ctx, "Digite o nome do personagem para buscar!\nUso: `#search Klein`")
        return

    if not dados["personagens"]:
        await msg_aviso(ctx, "Nenhum personagem cadastrado ainda!")
        return

    busca = normalizar_texto(nome)

    # Busca: match exato primeiro, depois parcial
    resultados = []
    for i, pers in enumerate(dados["personagens"]):
        nome_normalizado = normalizar_texto(pers["nome"])
        if busca == nome_normalizado:
            # Match exato — vai direto
            view = SearchResultView(ctx.author, i)
            await ctx.send(embed=view._gerar_embed(), view=view)
            return
        if busca in nome_normalizado or nome_normalizado in busca:
            resultados.append((i, pers))

    # Tenta match por palavra (ex: "klein" encontra "Klein Moretti")
    if not resultados:
        padrao = r'\b' + re.escape(busca) + r'\b'
        for i, pers in enumerate(dados["personagens"]):
            nome_normalizado = normalizar_texto(pers["nome"])
            if re.search(padrao, nome_normalizado):
                resultados.append((i, pers))

    if not resultados:
        await msg_erro(ctx, f"Nenhum personagem encontrado com **{nome}**.")
        return

    if len(resultados) == 1:
        # Só um resultado — vai direto
        idx_global = resultados[0][0]
        view = SearchResultView(ctx.author, idx_global)
        await ctx.send(embed=view._gerar_embed(), view=view)
        return

    # Múltiplos resultados — mostra dropdown
    nomes_lista = "\n".join(f"**{i+1}.** {pers['nome']}" for i, (_, pers) in enumerate(resultados))
    embed = discord.Embed(
        title=f"🔍 Resultados para \"{nome}\"",
        description=f"Encontrei **{len(resultados)}** personagens:\n\n{nomes_lista}\n\nSelecione no menu abaixo:",
        color=0x9B59B6
    )
    view = SearchSelectView(ctx.author, resultados)
    await ctx.send(embed=embed, view=view)

# ================= Comandos do Jogo =================

ultimo_personagem = None # Guarda o último sorteado pra evitar repetição

@bot.event
async def on_ready():
    print(f'🤖 Bot logado e pronto como {bot.user}')
    print(f'✅ Carregados {len(dados["personagens"])} personagens!')

@bot.command()
async def iniciar(ctx):
    global ultimo_personagem
    if not e_canal_permitido(ctx):
        await msg_erro(ctx, "Este comando não está permitido neste canal.")
        return

    if ctx.channel.id in jogos_ativos:
        await msg_aviso(ctx, "Já existe um jogo rolando neste canal! Adivinhe ou espere acabar.")
        return

    if not dados["personagens"]:
        await msg_erro(ctx, "Nenhum personagem cadastrado! Use o comando `#addpersonagem` primeiro.")
        return

    opcoes_validas = dados["personagens"]
    # Se tiver mais de 1 personagem, remove o que acabou de cair da urna do sorteio atual
    if len(dados["personagens"]) > 1 and ultimo_personagem:
        opcoes_validas = [p for p in dados["personagens"] if p["nome"] != ultimo_personagem]

    personagem_sorteado = random.choice(opcoes_validas)
    ultimo_personagem = personagem_sorteado["nome"]

    # ====== Evento Amon (1% de chance) ======
    amon = encontrar_amon()
    modo_amon = False
    if amon and personagem_sorteado["nome"].lower() != "amon" and random.random() < CHANCE_AMON:
        # Amon se disfarça! Pega emojis da vítima + injeta os do Amon
        emojis_rodada = gerar_evento_amon(personagem_sorteado)
        if emojis_rodada:
            modo_amon = True
            vitima = personagem_sorteado  # Guarda a vítima antes de trocar
            personagem_sorteado = amon
    
    if not modo_amon:
        # Escolhe a rotação de emojis normalmente (com chance de mix raro)
        emojis_rodada = escolher_emojis(personagem_sorteado)
    
    jogo = JogoEmoji(bot, ctx.channel, personagem_sorteado, emojis_rodada, 
                     modo_amon=modo_amon, 
                     vitima_disfarce=vitima if modo_amon else None)
    jogos_ativos[ctx.channel.id] = jogo
    
    embed = discord.Embed(
        title="🎮 O Jogo Começou!",
        description="Um novo personagem foi sorteado. Prepare-se para as dicas!",
        color=0x3498DB
    )
    await ctx.send(embed=embed)

@bot.command()
async def call_amon(ctx):
    """(Teste) Força o evento Amon para testar o sistema."""
    if not e_canal_gerencia(ctx):
        await msg_erro(ctx, msg_canais_gerencia())
        return
    if not tem_permissao_gerencia(ctx):
        await msg_erro(ctx, "Você não tem permissão para usar este comando.")
        return

    if ctx.channel.id in jogos_ativos:
        await msg_aviso(ctx, "Já existe um jogo rolando neste canal! Encerre ou espere acabar.")
        return

    amon = encontrar_amon()
    if not amon:
        await msg_erro(ctx, "O personagem **Amon** não está cadastrado! Adicione-o com `#addpersonagem`.")
        return

    # Escolhe uma vítima aleatória (qualquer um que não seja o Amon)
    vitimas = [p for p in dados["personagens"] if p["nome"].lower() != "amon"]
    if not vitimas:
        await msg_erro(ctx, "Não há outros personagens para o Amon se disfarçar!")
        return

    vitima = random.choice(vitimas)
    emojis_rodada = gerar_evento_amon(vitima)
    if not emojis_rodada:
        await msg_erro(ctx, "Erro ao gerar evento Amon. Verifique os emojis do Amon e da vítima.")
        return

    jogo = JogoEmoji(bot, ctx.channel, amon, emojis_rodada,
                     modo_amon=True, vitima_disfarce=vitima)
    jogos_ativos[ctx.channel.id] = jogo

    embed = discord.Embed(
        title="🎮 O Jogo Começou!",
        description=(
            "Um novo personagem foi sorteado. Prepare-se para as dicas!\n"
            f"||🔧 **TESTE AMON** — vítima: {vitima['nome']}||"
        ),
        color=0x3498DB
    )
    await ctx.send(embed=embed)

@bot.command()
async def confronto(ctx, oponente: discord.Member = None):
    """Desafia outro usuário para um duelo 1v1. Uso: #confronto @usuário"""
    if not e_canal_permitido(ctx):
        await msg_erro(ctx, "Este comando não está permitido neste canal.")
        return

    if not oponente:
        await msg_aviso(ctx, "Mencione quem você quer desafiar!\nUso: `#confronto @usuário`")
        return

    if oponente.bot:
        await msg_erro(ctx, "Você não pode desafiar um bot!")
        return

    if oponente.id == ctx.author.id:
        await msg_erro(ctx, "Você não pode se desafiar!")
        return

    if ctx.channel.id in jogos_ativos:
        await msg_aviso(ctx, "Já existe um jogo rolando neste canal! Espere acabar.")
        return

    if ctx.channel.id in confrontos_ativos:
        await msg_aviso(ctx, "Já existe um confronto rolando neste canal! Espere acabar.")
        return

    if not dados["personagens"] or len(dados["personagens"]) < 3:
        await msg_erro(ctx, "São necessários pelo menos **3 personagens** cadastrados para o modo confronto.")
        return

    # Escolher quantidade de rodadas
    embed_rodadas = discord.Embed(
        title="⚔️ Escolha o Formato do Duelo",
        description=(
            f"{ctx.author.mention}, escolha quantas rodadas terá o confronto contra {oponente.mention}:\n\n"
            "• **Melhor de 3** — primeiro a 2 vence\n"
            "• **Melhor de 5** — primeiro a 3 vence\n"
            "• **Melhor de 7** — primeiro a 4 vence\n\n"
            "*Em caso de empate, rodadas extras serão adicionadas.*"
        ),
        color=0x3498DB
    )
    view_rodadas = EscolherRodadasView(ctx.author)
    msg_rodadas = await ctx.send(embed=embed_rodadas, view=view_rodadas)
    await view_rodadas.wait()

    if not view_rodadas.rodadas:
        embed_cancel = discord.Embed(description="⏰ Tempo esgotado! Confronto cancelado.", color=0x95A5A6)
        await msg_rodadas.edit(embed=embed_cancel, view=None)
        return

    rodadas = view_rodadas.rodadas
    vitorias = (rodadas // 2) + 1

    # Enviar convite
    embed = discord.Embed(
        title="⚔️ Desafio de Confronto!",
        description=(
            f"{ctx.author.mention} desafiou {oponente.mention} para um **duelo 1v1**!\n\n"
            f"🏆 **Melhor de {rodadas}** — primeiro a {vitorias} acertos vence!\n"
            "🔄 Em caso de empate, rodadas extras serão adicionadas.\n\n"
            f"{oponente.mention}, você aceita o desafio?"
        ),
        color=0xE67E22
    )

    view = AceitarConfrontoView(ctx.author, oponente, rodadas)
    msg = await ctx.send(embed=embed, view=view)

    # Espera a resposta
    await view.wait()

    if not view.aceito:
        if view.aceito is None:  # Timeout
            embed_timeout = discord.Embed(
                title="⏰ Tempo Esgotado",
                description=f"{oponente.mention} não respondeu ao desafio a tempo.",
                color=0x95A5A6
            )
            await msg.edit(embed=embed_timeout, view=None)
        return

    # Desafio aceito! Criar o confronto
    duelo = Confronto(bot, ctx.channel, ctx.author, oponente, max_rodadas=view.rodadas)
    confrontos_ativos[ctx.channel.id] = duelo

    # Iniciar o confronto em background
    bot.loop.create_task(duelo.iniciar())


@bot.command()
async def dica(ctx):
    if not e_canal_permitido(ctx):
        return

    if ctx.channel.id not in jogos_ativos:
        await msg_aviso(ctx, "Não há nenhum jogo rolando. Digite `#iniciar` para começar.")
        return

    jogo = jogos_ativos[ctx.channel.id]
    
    if jogo.indice_dica >= len(jogo.emojis):
        await msg_aviso(ctx, "Todas as dicas já foram dadas! Tentem adivinhar no chat.")
        return

    jogo.task_dica.cancel()
    jogo.indice_dica += 1
    jogo.task_dica = bot.loop.create_task(jogo.loop_dicas())

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Processa comandos primeiro
    await bot.process_commands(message)

    # Checa se há um confronto ativo neste canal (prioridade sobre jogo normal)
    if message.channel.id in confrontos_ativos:
        duelo = confrontos_ativos[message.channel.id]
        await duelo.processar_chute(message)
        return  # No confronto, só os duelistas respondem

    # Depois checa se a mensagem é um chute em um jogo ativo
    if message.channel.id in jogos_ativos:
        if e_canal_permitido(message): 
            jogo = jogos_ativos[message.channel.id]
            chute_do_usuario = message.content
            
            # === Modo Amon: checar se a pessoa chutou a vítima (disfarce) ===
            if jogo.modo_amon and jogo.vitima_disfarce:
                if chute_corresponde(chute_do_usuario, jogo.vitima_disfarce["respostas_aceitas"]):
                    # Caiu na armadilha! Encerra o jogo e Amon escapa
                    jogo_encerrado = jogos_ativos.pop(message.channel.id, None)
                    if jogo_encerrado is None:
                        return
                    if not jogo_encerrado.task_dica.done():
                        jogo_encerrado.task_dica.cancel()

                    # Amon escapa silenciosamente — jogador não sabe que foi enganado
                    embed_errou = discord.Embed(
                        title="❌ Resposta Incorreta!",
                        description=f"{message.author.mention}, **{jogo_encerrado.vitima_disfarce['nome']}** não era a resposta certa...",
                        color=0xE74C3C
                    )
                    embed_errou.set_footer(text="Tente novamente na próxima rodada!")
                    await message.reply(embed=embed_errou)
                    return

            if chute_corresponde(chute_do_usuario, jogo.personagem["respostas_aceitas"]):
                # Pega o jogo e remove da lista DE UMA VEZ de forma atômica
                jogo_encerrado = jogos_ativos.pop(message.channel.id, None)
                
                # Se alguém já "poppou" milissegundos antes (ganhador duplo), interrompe e sai
                if jogo_encerrado is None:
                    return 
                    
                # Se fomos o primeiro, cancelamos o tempo restante pra mandar a dica
                if not jogo_encerrado.task_dica.done():
                    jogo_encerrado.task_dica.cancel()

                # Registra streak
                streak = registrar_streak(message.guild.id, message.author.id)
                texto_streak = gerar_texto_streak(streak)

                if jogo_encerrado.modo_amon:
                    embed_vitoria = discord.Embed(
                        title="🧐😈 Amon foi Descoberto!",
                        description=(
                            f"Parabéns {message.author.mention}!\n\n"
                            f"Você percebeu que o **Amon** estava se passando por outro personagem! 🏆\n"
                            f"||Os emojis estavam misturados e as dicas tinham erros... mas você não caiu! 👁️||"
                        ),
                        color=0x9B30FF
                    )
                else:
                    embed_vitoria = discord.Embed(
                        title="🎉 Temos um Vencedor!",
                        description=(
                            f"Parabéns {message.author.mention}!\n\n"
                            f"Você acertou o personagem: **{jogo_encerrado.personagem['nome']}**! 🏆"
                        ),
                        color=0xFFD700 
                    )

                if texto_streak:
                    embed_vitoria.add_field(name="\u200b", value=texto_streak, inline=False)

                await message.reply(embed=embed_vitoria)
                return

bot.run(TOKEN)
