import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.database import GerenciadorDados

# Carrega variáveis de ambiente do arquivo .env (desenvolvimento local)
load_dotenv()

COGS = ['cogs.admin', 'cogs.game']


class ThanathosBot(commands.Bot):
    """Bot principal do Thanathos — jogo de adivinhar personagens por emojis."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='#', intents=intents)
        self.remove_command('help')  # Remove o help padrão do discord.py
        self.db = GerenciadorDados()

    async def setup_hook(self):
        """Carrega dados e extensões (Cogs) antes do bot conectar."""
        await self.db.carregar()
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"  ✅ Cog carregada: {cog}")
            except Exception as e:
                print(f"  ❌ Erro ao carregar {cog}: {e}")


bot = ThanathosBot()


# ====== Eventos Globais ======

@bot.event
async def on_ready():
    print(f'🤖 Bot logado e pronto como {bot.user}')
    print(f'✅ Carregados {len(bot.db.dados["personagens"])} personagens!')


@bot.event
async def on_command_error(ctx, error):
    """Handler global de erros de comandos."""
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


# ====== Inicialização ======

token = os.getenv('DISCORD_TOKEN')
if not token:
    print("❌ Token não encontrado!")
    print("   Configure a variável de ambiente DISCORD_TOKEN ou crie um arquivo .env com:")
    print("   DISCORD_TOKEN=seu_token_aqui")
    exit()

bot.run(token)
