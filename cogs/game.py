import discord
from discord.ext import commands
import asyncio
import random

from utils.helpers import (
    e_canal_permitido, tem_permissao_gerencia, e_canal_gerencia,
    msg_canais_gerencia, msg_sucesso, msg_erro, msg_aviso,
    chute_corresponde, escolher_emojis,
    encontrar_amon, gerar_evento_amon
)
from utils.security import sanitizar_chute

# ====== Constantes do Amon ======
CHANCE_AMON = 0.01     # 1% de chance do evento Amon (o Enganador)

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
CHANCE_FRASE_AMON = 0.35  # 35% de chance da frase dramática aparecer


# ====== Views do Confronto ======

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


# ====== Classes do Jogo ======

class JogoEmoji:
    """Gerencia uma rodada do jogo de adivinhar personagem por emojis."""

    def __init__(self, cog, canal, personagem, emojis_rodada, modo_amon=False, vitima_disfarce=None):
        self.cog = cog
        self.bot = cog.bot
        self.canal = canal
        self.personagem = personagem
        self.emojis = emojis_rodada
        self.modo_amon = modo_amon
        self.vitima_disfarce = vitima_disfarce  # Personagem que o Amon está imitando
        self.indice_dica = 1
        self.tempo_espera = 20
        self.task_dica = self.bot.loop.create_task(self.loop_dicas())

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
            footer = "Digite sua resposta no chat! • Use #dica para acelerar"
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
            self.cog.encerrar_jogo(self.canal.id)

        except asyncio.CancelledError:
            pass


class Confronto:
    """Gerencia um duelo 1v1 entre dois jogadores."""

    def __init__(self, cog, canal, jogador1, jogador2, max_rodadas=3):
        self.cog = cog
        self.bot = cog.bot
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
        personagem = random.choice(self.bot.db.dados["personagens"])
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

        # Inicia as dicas
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

        chute = sanitizar_chute(message.content)
        if chute_corresponde(chute, self.personagem_atual["respostas_aceitas"]):
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
        self.cog.confrontos_ativos.pop(self.canal.id, None)

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


# ====== Cog do Jogo ======

class GameCog(commands.Cog, name="Jogo"):
    """Cog com toda a lógica do jogo de emojis, confrontos e streaks."""

    def __init__(self, bot):
        self.bot = bot
        self.jogos_ativos = {}           # { canal_id: JogoEmoji }
        self.confrontos_ativos = {}      # { canal_id: Confronto }
        self.streaks = {}                # { guild_id: { "user_id": int, "streak": int } }
        self.ultimo_personagem = None    # Evita repetição consecutiva

    # ====== Sistema de Streaks ======

    def registrar_streak(self, guild_id, user_id):
        """Registra um acerto e retorna o streak atual do jogador."""
        if guild_id in self.streaks and self.streaks[guild_id]["user_id"] == user_id:
            self.streaks[guild_id]["streak"] += 1
        else:
            self.streaks[guild_id] = {"user_id": user_id, "streak": 1}
        return self.streaks[guild_id]["streak"]

    @staticmethod
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

    # ====== Utilitário ======

    def encerrar_jogo(self, canal_id):
        """Remove um jogo ativo e cancela a task de dicas."""
        jogo = self.jogos_ativos.pop(canal_id, None)
        if jogo and not jogo.task_dica.done():
            jogo.task_dica.cancel()

    # ====== Comandos do Jogo ======

    @commands.command()
    async def iniciar(self, ctx):
        """Inicia um novo desafio de adivinhar personagem."""
        dados = self.bot.db.dados

        if not e_canal_permitido(ctx, dados):
            await msg_erro(ctx, "Este comando não está permitido neste canal.")
            return

        if ctx.channel.id in self.jogos_ativos:
            await msg_aviso(ctx, "Já existe um jogo rolando neste canal! Adivinhe ou espere acabar.")
            return

        if not dados["personagens"]:
            await msg_erro(ctx, "Nenhum personagem cadastrado! Use o comando `#addpersonagem` primeiro.")
            return

        opcoes_validas = dados["personagens"]
        # Se tiver mais de 1 personagem, remove o que acabou de cair da urna do sorteio atual
        if len(dados["personagens"]) > 1 and self.ultimo_personagem:
            opcoes_validas = [p for p in dados["personagens"] if p["nome"] != self.ultimo_personagem]

        personagem_sorteado = random.choice(opcoes_validas)
        self.ultimo_personagem = personagem_sorteado["nome"]

        # ====== Evento Amon (1% de chance) ======
        amon = encontrar_amon(dados["personagens"])
        modo_amon = False
        vitima = None
        if amon and personagem_sorteado["nome"].lower() != "amon" and random.random() < CHANCE_AMON:
            emojis_rodada = gerar_evento_amon(personagem_sorteado, dados["personagens"])
            if emojis_rodada:
                modo_amon = True
                vitima = personagem_sorteado
                personagem_sorteado = amon

        if not modo_amon:
            emojis_rodada = escolher_emojis(personagem_sorteado)

        jogo = JogoEmoji(self, ctx.channel, personagem_sorteado, emojis_rodada,
                         modo_amon=modo_amon, vitima_disfarce=vitima)
        self.jogos_ativos[ctx.channel.id] = jogo

        embed = discord.Embed(
            title="🎮 O Jogo Começou!",
            description="Um novo personagem foi sorteado. Prepare-se para as dicas!",
            color=0x3498DB
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def call_amon(self, ctx):
        """(Teste) Força o evento Amon para testar o sistema."""
        dados = self.bot.db.dados

        if not e_canal_gerencia(ctx, dados):
            await msg_erro(ctx, msg_canais_gerencia(dados))
            return
        if not tem_permissao_gerencia(ctx, dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return

        if ctx.channel.id in self.jogos_ativos:
            await msg_aviso(ctx, "Já existe um jogo rolando neste canal! Encerre ou espere acabar.")
            return

        amon = encontrar_amon(dados["personagens"])
        if not amon:
            await msg_erro(ctx, "O personagem **Amon** não está cadastrado! Adicione-o com `#addpersonagem`.")
            return

        # Escolhe uma vítima aleatória (qualquer um que não seja o Amon)
        vitimas = [p for p in dados["personagens"] if p["nome"].lower() != "amon"]
        if not vitimas:
            await msg_erro(ctx, "Não há outros personagens para o Amon se disfarçar!")
            return

        vitima = random.choice(vitimas)
        emojis_rodada = gerar_evento_amon(vitima, dados["personagens"])
        if not emojis_rodada:
            await msg_erro(ctx, "Erro ao gerar evento Amon. Verifique os emojis do Amon e da vítima.")
            return

        jogo = JogoEmoji(self, ctx.channel, amon, emojis_rodada,
                         modo_amon=True, vitima_disfarce=vitima)
        self.jogos_ativos[ctx.channel.id] = jogo

        embed = discord.Embed(
            title="🎮 O Jogo Começou!",
            description=(
                "Um novo personagem foi sorteado. Prepare-se para as dicas!\n"
                f"||🔧 **TESTE AMON** — vítima: {vitima['nome']}||"
            ),
            color=0x3498DB
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def confronto(self, ctx, oponente: discord.Member = None):
        """Desafia outro usuário para um duelo 1v1. Uso: #confronto @usuário"""
        dados = self.bot.db.dados

        if not e_canal_permitido(ctx, dados):
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

        if ctx.channel.id in self.jogos_ativos:
            await msg_aviso(ctx, "Já existe um jogo rolando neste canal! Espere acabar.")
            return

        if ctx.channel.id in self.confrontos_ativos:
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
        duelo = Confronto(self, ctx.channel, ctx.author, oponente, max_rodadas=view.rodadas)
        self.confrontos_ativos[ctx.channel.id] = duelo

        # Iniciar o confronto em background
        self.bot.loop.create_task(duelo.iniciar())

    @commands.command()
    async def dica(self, ctx):
        """Pula o timer e revela a próxima dica imediatamente."""
        if not e_canal_permitido(ctx, self.bot.db.dados):
            return

        if ctx.channel.id not in self.jogos_ativos:
            await msg_aviso(ctx, "Não há nenhum jogo rolando. Digite `#iniciar` para começar.")
            return

        jogo = self.jogos_ativos[ctx.channel.id]

        if jogo.indice_dica >= len(jogo.emojis):
            await msg_aviso(ctx, "Todas as dicas já foram dadas! Tentem adivinhar no chat.")
            return

        jogo.task_dica.cancel()
        jogo.indice_dica += 1
        jogo.task_dica = self.bot.loop.create_task(jogo.loop_dicas())

    # ====== Listener: processar chutes via on_message ======

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Checa se há um confronto ativo neste canal (prioridade sobre jogo normal)
        if message.channel.id in self.confrontos_ativos:
            duelo = self.confrontos_ativos[message.channel.id]
            await duelo.processar_chute(message)
            return  # No confronto, só os duelistas respondem

        # Depois checa se a mensagem é um chute em um jogo ativo
        if message.channel.id in self.jogos_ativos:
            if e_canal_permitido(message, self.bot.db.dados):
                jogo = self.jogos_ativos[message.channel.id]
                chute_do_usuario = sanitizar_chute(message.content)

                # === Modo Amon: se chutou a vítima (disfarce), ignora silenciosamente ===
                if jogo.modo_amon and jogo.vitima_disfarce:
                    if chute_corresponde(chute_do_usuario, jogo.vitima_disfarce["respostas_aceitas"]):
                        return  # Caiu na armadilha do Amon, mas sem feedback

                if chute_corresponde(chute_do_usuario, jogo.personagem["respostas_aceitas"]):
                    # Pega o jogo e remove da lista de forma atômica
                    jogo_encerrado = self.jogos_ativos.pop(message.channel.id, None)

                    # Se alguém já "poppou" milissegundos antes, interrompe e sai
                    if jogo_encerrado is None:
                        return

                    if not jogo_encerrado.task_dica.done():
                        jogo_encerrado.task_dica.cancel()

                    # Registra streak
                    streak = self.registrar_streak(message.guild.id, message.author.id)
                    texto_streak = self.gerar_texto_streak(streak)

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


async def setup(bot):
    await bot.add_cog(GameCog(bot))
