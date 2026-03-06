import discord
from discord.ext import commands
import asyncio
import random
import json
import os

# ================= Configurações Iniciais =================
DADOS_FILE = 'dados_jogo.json'

dados = {
    "canais_permitidos": [],
    "cargos_permitidos": [],
    "personagens": []
}

def carregar_dados():
    global dados
    if os.path.exists(DADOS_FILE):
        with open(DADOS_FILE, 'r', encoding='utf-8') as f:
            dados = json.load(f)
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

# ================= Comandos de Gerenciamento =================

@bot.command()
async def addcanal(ctx, canal_id: int):
    """(Admin) Autoriza um canal a ter o bot funcinando"""
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
    await ctx.send("📋 **Comandos disponíveis:**\n"
                "`#iniciar` - Inicia um novo jogo\n"
                "`#dica` - Solicita uma dica no jogo ativo\n"
                "\n⚙️ **Gerenciamento (Admins/Cargos):**\n"
                "`#addcanal <ID>` - Libera um canal\n"
                "`#rmcanal <ID>` - Bloqueia um canal\n"
                "`#addcargo @Cargo` - Dá permissão de gerência\n"
                "`#rmcargo @Cargo` - Tira permissão de gerência\n"
                "`#addpersonagem \"Nome\" \"emojis\" \"resp, resp2\"` - Cria personagem\n"
                "`#rmpersonagem Nome exato` - Deleta personagem\n"
                "`#help` - Exibe esta mensagem de ajuda")

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
            chute_do_usuario = message.content.lower().strip()
            
            if chute_do_usuario in jogo.personagem["respostas_aceitas"]:
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
