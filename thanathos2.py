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

CHANCE_MIX_RARO = 0.15  # 15% de chance de misturar emojis de rotações diferentes
CHANCE_AMON = 0.01     # 1% de chance do evento Amon (o Enganador)

# ====== Erros propositais para o modo Amon ======
AMON_TITULOS = [
    "🎯 Adivnihe o Personagem!",
    "🎯 Adivineh o Presonagem!",
    "🎯 Advinhe o Personajem!",
    "🎯 Adivinhe o Pesonagem!",
    "🎯 Advinhne o Persongem!",
    "🎯 Adivinhe o Prsonagem!",
]

AMON_FOOTERS = [
    "Diigite sua resposta no chat! • Use !dica para acelerar",
    "Digite sua reposta no chat! • Use !dica para aceelrar",
    "Digte sua resposta no caht! • Use !dica para acelrar",
    "Digite sua resposta no chat! • Use !dcia para acelerar",
    "Digtie sua resposta no chat! • Use !dic para aceelrar",
]

def encontrar_amon():
    """Procura o personagem Amon na lista de personagens."""
    for pers in dados["personagens"]:
        if pers["nome"].lower() == "amon":
            return pers
    return None

def gerar_evento_amon(personagem_vitima):
    """
    Gera os emojis do evento Amon: pega os emojis de um personagem vítima
    e injeta 2 emojis do Amon em posições aleatórias.
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
    
    # Substitui 2 posições aleatórias dos emojis da vítima
    if len(emojis_vitima) >= 2:
        posicoes = random.sample(range(len(emojis_vitima)), 2)
        for i, pos in enumerate(posicoes):
            emojis_vitima[pos] = amon_injecao[i % len(amon_injecao)]
    else:
        # Se a vítima só tem 1 emoji, adiciona os do Amon
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
    def __init__(self, bot, canal, personagem, emojis_rodada, modo_amon=False):
        self.bot = bot
        self.canal = canal
        self.personagem = personagem
        self.emojis = emojis_rodada
        self.modo_amon = modo_amon  # Se True, o Amon está se passando por outro
        self.indice_dica = 1 
        self.tempo_espera = 20 
        self.task_dica = bot.loop.create_task(self.loop_dicas())
        
    async def enviar_dica(self):
        emojis_atuais = "".join(self.emojis[:self.indice_dica])
        total_emojis = len(self.emojis)

        if self.modo_amon:
            # Erros propositais: título com typo, contagem errada, footer bugado
            titulo = random.choice(AMON_TITULOS)
            footer = random.choice(AMON_FOOTERS)
            # Contagem mentirosa: mostra número errado (+1, -1, ou totalmente errado)
            dica_falsa = self.indice_dica + random.choice([-1, 0, 1, 2])
            total_falso = total_emojis + random.choice([-1, 0, 1, 2, 3])
            if dica_falsa < 1:
                dica_falsa = 1
            if total_falso < 1:
                total_falso = total_emojis
            texto_dica = f"**Dica {dica_falsa} de {total_falso}**"
            # Cor levemente diferente (verde com toque estranho) — sutil
            cor = random.choice([0x00FF00, 0x00FF44, 0x22FF00, 0x00EE11, 0x11FF33])
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

            if self.modo_amon:
                embed_fim = discord.Embed(
                    title="⏰ Tmpo Esgotado!",
                    description=(
                        f"Ninguém acertou dessa vez...\n"
                        f"O personagem era: **{self.personagem['nome']}**\n\n"
                        f"🧐 ...ou será que era? O **Amon** estava se passando por outro esse tempo todo! 😈"
                    ),
                    color=0xFF4500
                )
            else:
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
        num_rotacoes = len(pers["emojis"])
        rotacoes_txt = []
        for idx_r, rot in enumerate(pers["emojis"], 1):
            rotacoes_txt.append(f">    R{idx_r}: {' '.join(rot)}")
        respostas = ", ".join(pers["respostas_aceitas"])
        bloco_rotacoes = "\n".join(rotacoes_txt)
        linhas.append(f"**{i}. {pers['nome']}** ({num_rotacoes} rotações)\n{bloco_rotacoes}\n> Respostas: `{respostas}`")
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
            # O personagem "real" pra fins de resposta é o Amon
            personagem_sorteado = amon
    
    if not modo_amon:
        # Escolhe a rotação de emojis normalmente (com chance de mix raro)
        emojis_rodada = escolher_emojis(personagem_sorteado)
    
    jogo = JogoEmoji(bot, ctx.channel, personagem_sorteado, emojis_rodada, modo_amon=modo_amon)
    jogos_ativos[ctx.channel.id] = jogo
    
    embed = discord.Embed(
        title="🎮 O Jogo Começou!",
        description="Um novo personagem foi sorteado. Prepare-se para as dicas!",
        color=0x3498DB
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

                if jogo_encerrado.modo_amon:
                    # Vitória especial do Amon!
                    embed_vitoria = discord.Embed(
                        title="🧐😈 Amon foi Descoberto!",
                        description=(
                            f"Parabéns {message.author.mention}!\n\n"
                            f"Você percebeu que o **Amon** estava se passando por outro personagem! 🏆\n"
                            f"Os emojis estavam misturados e as dicas tinham erros... mas você não caiu! 👁️"
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
                await message.reply(embed=embed_vitoria)
                return

bot.run(TOKEN)
