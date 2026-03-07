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

class JogoEmoji:
    def __init__(self, bot, canal, personagem):
        self.bot = bot
        self.canal = canal
        self.personagem = personagem
        self.indice_dica = 1 
        self.tempo_espera = 20 
        self.task_dica = bot.loop.create_task(self.loop_dicas())
        
    async def enviar_dica(self):
        emojis_atuais = "".join(self.personagem["emojis"][:self.indice_dica])
        embed = discord.Embed(
            title="🎯 Adivinhe o Personagem!",
            description=(
                f"**Dica {self.indice_dica} de {len(self.personagem['emojis'])}**\n\n"
                f"> ## {emojis_atuais}"
            ),
            color=0x00FF00 # Verde claro estilizado
        )
        embed.set_footer(text="Digite sua resposta no chat! • Use !dica para acelerar")
        await self.canal.send(embed=embed)

    async def loop_dicas(self):
        try:
            await self.enviar_dica()
            while self.indice_dica < len(self.personagem["emojis"]):
                await asyncio.sleep(self.tempo_espera)
                self.indice_dica += 1
                await self.enviar_dica()
            
            await asyncio.sleep(self.tempo_espera)
            embed_fim = discord.Embed(
                title="⏰ Tempo Esgotado!",
                description=f"Ninguém acertou dessa vez...\nO personagem era: **{self.personagem['nome']}**",
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
        "emojis": lista_emojis,
        "respostas_aceitas": lista_respostas
    }
    
    dados["personagens"].append(novo_pers)
    salvar_dados()
    await msg_sucesso(ctx, f"O personagem **{nome}** foi salvo com sucesso! ({len(lista_emojis)} emojis, {len(lista_respostas)} respostas)")

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
            "> `#dica` — Pula o timer e revela a próxima dica"
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

    paginas = []
    linhas = []
    for i, pers in enumerate(dados["personagens"], 1):
        emojis = " ".join(pers["emojis"])
        respostas = ", ".join(pers["respostas_aceitas"])
        linhas.append(f"**{i}. {pers['nome']}**\n> Emojis: {emojis}\n> Respostas: `{respostas}`")
        # A cada 10 personagens, cria uma nova página pra não estourar o limite do embed
        if i % 10 == 0:
            paginas.append("\n\n".join(linhas))
            linhas = []
    if linhas:
        paginas.append("\n\n".join(linhas))

    for idx, pagina in enumerate(paginas):
        embed = discord.Embed(
            title=f"📋 Personagens Cadastrados ({len(dados['personagens'])} total)",
            description=pagina,
            color=0x9B59B6
        )
        if len(paginas) > 1:
            embed.set_footer(text=f"Página {idx + 1}/{len(paginas)}")
        await ctx.send(embed=embed)

# ================= Sistema de Edição de Emojis (Paginado) =================

POR_PAGINA = 10  # Quantos personagens por página no editor

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
            emojis_preview = " ".join(pers["emojis"][:3])
            label = f"{i}. {pers['nome']}"
            if len(label) > 100:
                label = label[:97] + "..."
            opcoes.append(discord.SelectOption(
                label=label,
                description=emojis_preview[:100],
                value=str(i - 1)  # índice real no array
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
            emojis = " ".join(pers["emojis"])
            linhas.append(f"**{i}.** {pers['nome']}  —  {emojis}")

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

        emojis_atuais = " ".join(pers["emojis"])
        embed = discord.Embed(
            title=f"✏️ Editando: {pers['nome']}",
            description=(
                f"**Emojis atuais:** {emojis_atuais}\n\n"
                f"Escolha o que deseja fazer:"
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

    @discord.ui.button(label="🔄 Substituir Todos", style=discord.ButtonStyle.primary)
    async def substituir_todos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        pers = self._pers()
        embed = discord.Embed(
            title=f"🔄 Substituir emojis de: {pers['nome']}",
            description=(
                f"**Emojis atuais:** {' '.join(pers['emojis'])}\n\n"
                "📝 **Digite os novos emojis separados por vírgula no chat.**\n"
                "Exemplo: `🦇, 👨, 🌃, 🏙️`\n\n"
                "⏱️ Você tem **60 segundos** para responder."
            ),
            color=0x3498DB
        )
        await interaction.response.edit_message(embed=embed, view=None)

        def check(m):
            return m.author.id == self.autor.id and m.channel.id == interaction.channel.id

        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60)
            novos_emojis = [e.strip() for e in msg.content.split(',') if e.strip()]

            if not novos_emojis:
                embed_err = discord.Embed(description="❌ Nenhum emoji detectado. Edição cancelada.", color=0xE74C3C)
                await interaction.channel.send(embed=embed_err)
                return

            antigos = " ".join(pers["emojis"])
            pers["emojis"] = novos_emojis
            salvar_dados()

            embed_ok = discord.Embed(
                title=f"✅ Emojis atualizados: {pers['nome']}",
                description=(
                    f"**Antes:** {antigos}\n"
                    f"**Agora:** {' '.join(novos_emojis)}"
                ),
                color=0x2ECC71
            )
            await interaction.channel.send(embed=embed_ok)

        except asyncio.TimeoutError:
            embed_timeout = discord.Embed(description="⏰ Tempo esgotado! Edição cancelada.", color=0xE74C3C)
            await interaction.channel.send(embed=embed_timeout)

    @discord.ui.button(label="➕ Adicionar Emoji", style=discord.ButtonStyle.success)
    async def adicionar_emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        pers = self._pers()
        embed = discord.Embed(
            title=f"➕ Adicionar emoji a: {pers['nome']}",
            description=(
                f"**Emojis atuais:** {' '.join(pers['emojis'])}\n\n"
                "📝 **Digite o(s) emoji(s) para adicionar, separados por vírgula.**\n"
                "Exemplo: `🗡️, 🛡️`\n\n"
                "⏱️ Você tem **60 segundos** para responder."
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
                embed_err = discord.Embed(description="❌ Nenhum emoji detectado. Operação cancelada.", color=0xE74C3C)
                await interaction.channel.send(embed=embed_err)
                return

            pers["emojis"].extend(novos)
            salvar_dados()

            embed_ok = discord.Embed(
                title=f"✅ Emojis adicionados: {pers['nome']}",
                description=f"**Emojis agora:** {' '.join(pers['emojis'])}",
                color=0x2ECC71
            )
            await interaction.channel.send(embed=embed_ok)

        except asyncio.TimeoutError:
            embed_timeout = discord.Embed(description="⏰ Tempo esgotado! Operação cancelada.", color=0xE74C3C)
            await interaction.channel.send(embed=embed_timeout)

    @discord.ui.button(label="🗑️ Remover Emoji", style=discord.ButtonStyle.danger)
    async def remover_emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        pers = self._pers()
        if len(pers["emojis"]) <= 1:
            await interaction.response.send_message("O personagem precisa ter pelo menos 1 emoji!", ephemeral=True)
            return

        emojis_lista = "\n".join(f"`{i+1}.` {e}" for i, e in enumerate(pers["emojis"]))
        embed = discord.Embed(
            title=f"🗑️ Remover emoji de: {pers['nome']}",
            description=(
                f"**Emojis atuais:**\n{emojis_lista}\n\n"
                "📝 **Digite o número do emoji que deseja remover.**\n"
                "⏱️ Você tem **60 segundos** para responder."
            ),
            color=0xE74C3C
        )
        await interaction.response.edit_message(embed=embed, view=None)

        def check(m):
            return m.author.id == self.autor.id and m.channel.id == interaction.channel.id

        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60)

            if not msg.content.strip().isdigit():
                embed_err = discord.Embed(description="❌ Digite apenas o número. Operação cancelada.", color=0xE74C3C)
                await interaction.channel.send(embed=embed_err)
                return

            numero = int(msg.content.strip())
            if numero < 1 or numero > len(pers["emojis"]):
                embed_err = discord.Embed(description=f"❌ Número inválido. Escolha entre 1 e {len(pers['emojis'])}.", color=0xE74C3C)
                await interaction.channel.send(embed=embed_err)
                return

            emoji_removido = pers["emojis"].pop(numero - 1)
            salvar_dados()

            embed_ok = discord.Embed(
                title=f"✅ Emoji removido: {pers['nome']}",
                description=(
                    f"**Removido:** {emoji_removido}\n"
                    f"**Emojis agora:** {' '.join(pers['emojis'])}"
                ),
                color=0x2ECC71
            )
            await interaction.channel.send(embed=embed_ok)

        except asyncio.TimeoutError:
            embed_timeout = discord.Embed(description="⏰ Tempo esgotado! Operação cancelada.", color=0xE74C3C)
            await interaction.channel.send(embed=embed_timeout)

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
    
    jogo = JogoEmoji(bot, ctx.channel, personagem_sorteado)
    jogos_ativos[ctx.channel.id] = jogo
    
    embed = discord.Embed(
        title="🎮 O Jogo Começou!",
        description="Um novo personagem foi sorteado. Prepare-se para as dicas!",
        color=0x3498DB # Azul bonito
    )
    await ctx.send(embed=embed)

@bot.command()
async def dica(ctx):
    if not e_canal_permitido(ctx):
        return

    if ctx.channel.id not in jogos_ativos:
        await msg_aviso(ctx, "Não há nenhum jogo rolando. Digite `#iniciar` para começar.")
        return

    jogo = jogos_ativos[ctx.channel.id]
    
    if jogo.indice_dica >= len(jogo.personagem["emojis"]):
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

    # Depois checa se a mensagem é um chute em um jogo ativo
    if message.channel.id in jogos_ativos:
        if e_canal_permitido(message): 
            jogo = jogos_ativos[message.channel.id]
            chute_do_usuario = message.content
            
            if chute_corresponde(chute_do_usuario, jogo.personagem["respostas_aceitas"]):
                # Pega o jogo e remove da lista DE UMA VEZ de forma atômica
                jogo_encerrado = jogos_ativos.pop(message.channel.id, None)
                
                # Se alguém já "poppou" milissegundos antes (ganhador duplo), interrompe e sai
                if jogo_encerrado is None:
                    return 
                    
                # Se fomos o primeiro, cancelamos o tempo restante pra mandar a dica
                if not jogo_encerrado.task_dica.done():
                    jogo_encerrado.task_dica.cancel()

                embed_vitoria = discord.Embed(
                    title="🎉 Temos um Vencedor!",
                    description=(
                        f"Parabéns {message.author.mention}!\n\n"
                        f"Você acertou o personagem: **{jogo_encerrado.personagem['nome']}**! 🏆"
                    ),
                    color=0xFFD700 
                )
                await message.reply(embed=embed_vitoria)
                return

bot.run(TOKEN)
