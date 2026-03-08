import discord
from discord.ext import commands
import asyncio
import re

from utils.helpers import (
    normalizar_texto, e_canal_gerencia, tem_permissao_gerencia,
    msg_canais_gerencia, msg_sucesso, msg_erro, msg_aviso
)
from utils.security import (
    sanitizar_texto, validar_nome, validar_emojis, validar_respostas
)

POR_PAGINA = 5  # Personagens por página (listar + editor)


# ================= Views de Listagem Paginada =================

class ListarView(discord.ui.View):
    """View paginada para listar personagens com botões de navegação."""

    def __init__(self, autor, db, pagina=0):
        super().__init__(timeout=120)
        self.autor = autor
        self.db = db
        self.pagina = pagina
        self._atualizar_botoes()

    def _personagens(self):
        return self.db.dados["personagens"]

    def _construir_paginas(self):
        paginas = []
        linhas = []
        for i, pers in enumerate(self._personagens(), 1):
            num_rotacoes = len(pers["emojis"])
            rotacoes_txt = []
            for idx_r, rot in enumerate(pers["emojis"], 1):
                rotacoes_txt.append(f">    R{idx_r}: {' '.join(rot)}")
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
            title=f"📋 Personagens Cadastrados ({len(self._personagens())} total)",
            description=conteudo,
            color=0x9B59B6
        )
        embed.set_footer(text=f"Página {self.pagina + 1}/{total_paginas}")
        return embed

    def _atualizar_botoes(self):
        total_paginas = max(1, (len(self._personagens()) + POR_PAGINA - 1) // POR_PAGINA)
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
        total_paginas = max(1, (len(self._personagens()) + POR_PAGINA - 1) // POR_PAGINA)
        self.pagina = min(total_paginas - 1, self.pagina + 1)
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.gerar_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ================= Views de Edição de Emojis =================

class EditEmojiView(discord.ui.View):
    """View principal: paginação + dropdown para selecionar personagem."""

    def __init__(self, autor, db, pagina=0):
        super().__init__(timeout=120)
        self.autor = autor
        self.db = db
        self.pagina = pagina
        self.total_paginas = max(1, (len(db.dados["personagens"]) + POR_PAGINA - 1) // POR_PAGINA)
        self._atualizar_componentes()

    def _atualizar_componentes(self):
        self.clear_items()
        personagens = self.db.dados["personagens"]
        inicio = self.pagina * POR_PAGINA
        fim = inicio + POR_PAGINA
        personagens_pagina = personagens[inicio:fim]

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

        dropdown = PersonagemSelect(opcoes, self.autor, self.db)
        self.add_item(dropdown)

        if self.pagina > 0:
            btn_voltar = discord.ui.Button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
            btn_voltar.callback = self._voltar_pagina
            self.add_item(btn_voltar)

        if self.pagina < self.total_paginas - 1:
            btn_avancar = discord.ui.Button(label="Próxima ▶", style=discord.ButtonStyle.secondary)
            btn_avancar.callback = self._avancar_pagina
            self.add_item(btn_avancar)

        btn_cancelar = discord.ui.Button(label="✖ Cancelar", style=discord.ButtonStyle.danger)
        btn_cancelar.callback = self._cancelar
        self.add_item(btn_cancelar)

    def _gerar_embed(self):
        personagens = self.db.dados["personagens"]
        inicio = self.pagina * POR_PAGINA
        fim = inicio + POR_PAGINA
        personagens_pagina = personagens[inicio:fim]

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

    def __init__(self, opcoes, autor, db):
        super().__init__(placeholder="Escolha o personagem para editar...", options=opcoes)
        self.autor = autor
        self.db = db

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return

        indice = int(self.values[0])
        pers = self.db.dados["personagens"][indice]

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

        view = EdicaoEmojiView(self.autor, self.db, indice)
        await interaction.response.edit_message(embed=embed, view=view)


class EdicaoEmojiView(discord.ui.View):
    """View com opções de edição dos emojis de um personagem específico."""

    def __init__(self, autor, db, indice_personagem):
        super().__init__(timeout=120)
        self.autor = autor
        self.db = db
        self.indice = indice_personagem

    def _pers(self):
        return self.db.dados["personagens"][self.indice]

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

            # Validação de segurança
            valido, erro = validar_emojis(novos_emojis)
            if not valido:
                await interaction.channel.send(embed=discord.Embed(description=f"❌ {erro}", color=0xE74C3C))
                return

            pers["emojis"][rotacao_idx] = novos_emojis
            await self.db.salvar()

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

            # Validação de segurança
            valido, erro = validar_emojis(novos)
            if not valido:
                await interaction.channel.send(embed=discord.Embed(description=f"❌ {erro}", color=0xE74C3C))
                return

            pers["emojis"].append(novos)
            await self.db.salvar()

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
            await self.db.salvar()

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
        view = EditEmojiView(self.autor, self.db)
        await interaction.response.edit_message(embed=view._gerar_embed(), view=view)


# ================= Views de Busca de Personagens =================

class SearchResultView(discord.ui.View):
    """View exibida ao encontrar um personagem: mostra detalhes + botões Editar/Deletar."""

    def __init__(self, autor, db, indice_personagem):
        super().__init__(timeout=120)
        self.autor = autor
        self.db = db
        self.indice = indice_personagem

    def _pers(self):
        return self.db.dados["personagens"][self.indice]

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
        view = EdicaoEmojiView(self.autor, self.db, self.indice)
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
        view = ConfirmarDeleteView(self.autor, self.db, self.indice)
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

    def __init__(self, autor, db, indice_personagem):
        super().__init__(timeout=30)
        self.autor = autor
        self.db = db
        self.indice = indice_personagem

    @discord.ui.button(label="✅ Sim, deletar", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        if self.indice >= len(self.db.dados["personagens"]):
            await interaction.response.edit_message(
                embed=discord.Embed(description="❌ Personagem já foi removido.", color=0xE74C3C), view=None)
            return
        pers = self.db.dados["personagens"].pop(self.indice)
        await self.db.salvar()
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
        view = SearchResultView(self.autor, self.db, self.indice)
        await interaction.response.edit_message(embed=view._gerar_embed(), view=view)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class SearchSelectView(discord.ui.View):
    """Dropdown para escolher entre múltiplos resultados de busca."""

    def __init__(self, autor, db, resultados):
        super().__init__(timeout=60)
        self.autor = autor
        self.db = db
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
        dropdown = SearchDropdown(opcoes, self.autor, self.db)
        self.add_item(dropdown)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class SearchDropdown(discord.ui.Select):
    """Dropdown de seleção dos resultados de busca."""

    def __init__(self, opcoes, autor, db):
        super().__init__(placeholder="Selecione o personagem...", options=opcoes)
        self.autor = autor
        self.db = db

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor.id:
            await interaction.response.send_message("Só quem usou o comando pode interagir.", ephemeral=True)
            return
        indice = int(self.values[0])
        view = SearchResultView(self.autor, self.db, indice)
        await interaction.response.edit_message(embed=view._gerar_embed(), view=view)


# ================= Cog de Administração =================

class AdminCog(commands.Cog, name="Administração"):
    """Cog com todos os comandos de gerenciamento do bot."""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db  # Atalho para o GerenciadorDados

    # ====== Gerência de Canais Admin ======

    @commands.command()
    async def addgerencia(self, ctx, canal_id: int):
        """(Admin) Adiciona um canal à lista de canais de gerência."""
        if not ctx.author.guild_permissions.administrator:
            await msg_erro(ctx, "Apenas **administradores do servidor** podem configurar canais de gerência.")
            return

        if canal_id not in self.db.dados["canais_gerencia"]:
            self.db.dados["canais_gerencia"].append(canal_id)
            await self.db.salvar()
            await msg_sucesso(ctx, f"Canal <#{canal_id}> adicionado como canal de gerência!")
        else:
            await msg_aviso(ctx, "Este canal já é um canal de gerência.")

    @commands.command()
    async def rmgerencia(self, ctx, canal_id: int):
        """(Admin) Remove um canal da lista de canais de gerência."""
        if not ctx.author.guild_permissions.administrator:
            await msg_erro(ctx, "Apenas **administradores do servidor** podem configurar canais de gerência.")
            return

        if canal_id in self.db.dados["canais_gerencia"]:
            self.db.dados["canais_gerencia"].remove(canal_id)
            await self.db.salvar()
            await msg_sucesso(ctx, f"Canal <#{canal_id}> removido dos canais de gerência.")
        else:
            await msg_aviso(ctx, "Este canal não está na lista de gerência.")

    # ====== Gerenciamento de Canais e Cargos ======

    @commands.command()
    async def addcanal(self, ctx, canal_id: int):
        """(Admin) Autoriza um canal a ter o bot funcionando."""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not tem_permissao_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return

        if canal_id not in self.db.dados["canais_permitidos"]:
            self.db.dados["canais_permitidos"].append(canal_id)
            await self.db.salvar()
            await msg_sucesso(ctx, f"Canal <#{canal_id}> adicionado aos canais permitidos.")
        else:
            await msg_aviso(ctx, "Este canal já está na lista.")

    @commands.command()
    async def rmcanal(self, ctx, canal_id: int):
        """(Admin) Remove um canal da lista de permitidos."""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not tem_permissao_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return

        if canal_id in self.db.dados["canais_permitidos"]:
            self.db.dados["canais_permitidos"].remove(canal_id)
            await self.db.salvar()
            await msg_sucesso(ctx, f"Canal <#{canal_id}> removido dos canais permitidos.")
        else:
            await msg_aviso(ctx, "Este canal não está na lista.")

    @commands.command()
    async def addcargo(self, ctx, cargo: discord.Role):
        """(Admin) Autoriza um cargo a adicionar personagens e canais."""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not ctx.author.guild_permissions.administrator:
            await msg_erro(ctx, "Apenas **administradores do servidor** podem adicionar cargos de gerência.")
            return

        if cargo.id not in self.db.dados["cargos_permitidos"]:
            self.db.dados["cargos_permitidos"].append(cargo.id)
            await self.db.salvar()
            await msg_sucesso(ctx, f"Cargo **{cargo.name}** adicionado! Quem tiver ele poderá gerenciar o jogo.")
        else:
            await msg_aviso(ctx, "Este cargo já tem permissão.")

    @commands.command()
    async def rmcargo(self, ctx, cargo: discord.Role):
        """(Admin) Remove a permissão de um cargo."""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not ctx.author.guild_permissions.administrator:
            await msg_erro(ctx, "Apenas **administradores do servidor** podem remover cargos de gerência.")
            return

        if cargo.id in self.db.dados["cargos_permitidos"]:
            self.db.dados["cargos_permitidos"].remove(cargo.id)
            await self.db.salvar()
            await msg_sucesso(ctx, f"Cargo **{cargo.name}** removido! Seus membros não terão mais permissões especiais.")
        else:
            await msg_aviso(ctx, "Este cargo não tinha permissão.")

    # ====== Gerenciamento de Personagens ======

    @commands.command()
    async def addpersonagem(self, ctx, nome: str, emojis: str, respostas: str):
        """
        (Admin) Adiciona um novo personagem.
        Uso: #addpersonagem "Nome" "🦇, 👨, 🌃" "batman, bruce wayne"
        """
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not tem_permissao_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return

        # Validação de segurança do nome
        nome_sanitizado = sanitizar_texto(nome, max_length=100)
        valido, erro = validar_nome(nome_sanitizado)
        if not valido:
            await msg_erro(ctx, erro)
            return

        # Processa emojis
        lista_emojis = [e.strip() for e in emojis.split(',') if e.strip()]
        valido, erro = validar_emojis(lista_emojis)
        if not valido:
            await msg_erro(ctx, erro)
            return

        # Processa respostas
        lista_respostas = [r.strip().lower() for r in respostas.split(',') if r.strip()]
        valido, erro = validar_respostas(lista_respostas)
        if not valido:
            await msg_erro(ctx, erro)
            return

        novo_pers = {
            "nome": nome_sanitizado,
            "emojis": [lista_emojis],  # Primeira rotação
            "respostas_aceitas": lista_respostas
        }

        self.db.dados["personagens"].append(novo_pers)
        await self.db.salvar()
        await msg_sucesso(ctx, f"O personagem **{nome_sanitizado}** foi salvo com sucesso! ({len(lista_emojis)} emojis na rotação 1, {len(lista_respostas)} respostas)")

    @commands.command()
    async def rmpersonagem(self, ctx, *, nome: str):
        """(Admin) Remove um personagem exato pelo nome."""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not tem_permissao_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return

        nome_procurado = nome.lower().strip()
        encontrado = None

        for pers in self.db.dados["personagens"]:
            if pers["nome"].lower() == nome_procurado:
                encontrado = pers
                break

        if encontrado:
            self.db.dados["personagens"].remove(encontrado)
            await self.db.salvar()
            await msg_sucesso(ctx, f"🗑️ O personagem **{encontrado['nome']}** foi permanentemente removido!")
        else:
            await msg_erro(ctx, f"Não encontrei nenhum personagem com o nome exato: **{nome}**")

    # ====== Help ======

    @commands.command()
    async def help(self, ctx):
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

    # ====== Listagem e Edição ======

    @commands.command()
    async def listar(self, ctx):
        """Lista todos os personagens cadastrados com seus emojis e respostas."""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not tem_permissao_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return

        if not self.db.dados["personagens"]:
            await msg_aviso(ctx, "Nenhum personagem cadastrado ainda! Use `#addpersonagem` para adicionar.")
            return

        view = ListarView(ctx.author, self.db)
        await ctx.send(embed=view.gerar_embed(), view=view)

    @commands.command()
    async def editemoji(self, ctx):
        """(Admin) Edita os emojis de um personagem com interface interativa."""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not tem_permissao_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return
        if not self.db.dados["personagens"]:
            await msg_aviso(ctx, "Nenhum personagem cadastrado! Use `#addpersonagem` primeiro.")
            return

        view = EditEmojiView(ctx.author, self.db)
        await ctx.send(embed=view._gerar_embed(), view=view)

    # ====== Busca ======

    @commands.command()
    async def search(self, ctx, *, nome: str = None):
        """(Admin) Busca um personagem por nome para editar ou deletar. Uso: #search klein"""
        if not e_canal_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, msg_canais_gerencia(self.db.dados))
            return
        if not tem_permissao_gerencia(ctx, self.db.dados):
            await msg_erro(ctx, "Você não tem permissão para usar este comando.")
            return

        if not nome or not nome.strip():
            await msg_aviso(ctx, "Digite o nome do personagem para buscar!\nUso: `#search Klein`")
            return

        if not self.db.dados["personagens"]:
            await msg_aviso(ctx, "Nenhum personagem cadastrado ainda!")
            return

        # Sanitização da busca
        nome_sanitizado = sanitizar_texto(nome, max_length=100)
        busca = normalizar_texto(nome_sanitizado)

        # Busca: match exato primeiro, depois parcial
        resultados = []
        for i, pers in enumerate(self.db.dados["personagens"]):
            nome_normalizado = normalizar_texto(pers["nome"])
            if busca == nome_normalizado:
                # Match exato — vai direto
                view = SearchResultView(ctx.author, self.db, i)
                await ctx.send(embed=view._gerar_embed(), view=view)
                return
            if busca in nome_normalizado or nome_normalizado in busca:
                resultados.append((i, pers))

        # Tenta match por palavra (ex: "klein" encontra "Klein Moretti")
        if not resultados:
            padrao = r'\b' + re.escape(busca) + r'\b'
            for i, pers in enumerate(self.db.dados["personagens"]):
                nome_normalizado = normalizar_texto(pers["nome"])
                if re.search(padrao, nome_normalizado):
                    resultados.append((i, pers))

        if not resultados:
            await msg_erro(ctx, f"Nenhum personagem encontrado com **{nome}**.")
            return

        if len(resultados) == 1:
            idx_global = resultados[0][0]
            view = SearchResultView(ctx.author, self.db, idx_global)
            await ctx.send(embed=view._gerar_embed(), view=view)
            return

        # Múltiplos resultados — mostra dropdown
        nomes_lista = "\n".join(f"**{i+1}.** {pers['nome']}" for i, (_, pers) in enumerate(resultados))
        embed = discord.Embed(
            title=f"🔍 Resultados para \"{nome}\"",
            description=f"Encontrei **{len(resultados)}** personagens:\n\n{nomes_lista}\n\nSelecione no menu abaixo:",
            color=0x9B59B6
        )
        view = SearchSelectView(ctx.author, self.db, resultados)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
