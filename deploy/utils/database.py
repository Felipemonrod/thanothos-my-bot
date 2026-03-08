import json
import os
import shutil
from datetime import datetime
import aiofiles

DADOS_FILE = 'dados_jogo.json'

DADOS_PADRAO = {
    "canais_gerencia": [],
    "canais_permitidos": [],
    "cargos_permitidos": [],
    "personagens": []
}


class GerenciadorDados:
    """Gerencia o carregamento e salvamento assíncrono dos dados do jogo."""

    def __init__(self, arquivo: str = DADOS_FILE):
        self.arquivo = arquivo
        self.dados = {k: list(v) for k, v in DADOS_PADRAO.items()}

    async def carregar(self):
        """Carrega os dados do arquivo JSON de forma assíncrona."""
        if not os.path.exists(self.arquivo):
            print(f"📁 Arquivo {self.arquivo} não encontrado. Criando com dados padrão...")
            await self.salvar()
            return

        try:
            async with aiofiles.open(self.arquivo, 'r', encoding='utf-8') as f:
                conteudo = await f.read()

            if not conteudo.strip():
                raise json.JSONDecodeError("Arquivo vazio", conteudo, 0)

            self.dados = json.loads(conteudo)

        except json.JSONDecodeError as e:
            print(f"⚠️ Arquivo {self.arquivo} corrompido ou vazio: {e}")
            await self._fazer_backup()
            self.dados = {k: list(v) for k, v in DADOS_PADRAO.items()}
            await self.salvar()
            print("✅ Dados padrão restaurados.")
            return

        except Exception as e:
            print(f"❌ Erro inesperado ao carregar {self.arquivo}: {e}")
            await self._fazer_backup()
            self.dados = {k: list(v) for k, v in DADOS_PADRAO.items()}
            await self.salvar()
            return

        # Retrocompatibilidade: garante que todas as chaves existem
        alterou = False
        for chave in DADOS_PADRAO:
            if chave not in self.dados:
                self.dados[chave] = list(DADOS_PADRAO[chave])
                alterou = True

        # Migração: emojis de lista simples para lista de rotações
        for pers in self.dados.get("personagens", []):
            if pers.get("emojis") and not isinstance(pers["emojis"][0], list):
                pers["emojis"] = [pers["emojis"]]
                alterou = True

        if alterou:
            await self.salvar()

    async def salvar(self):
        """Salva os dados no arquivo JSON de forma assíncrona."""
        async with aiofiles.open(self.arquivo, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(self.dados, indent=4, ensure_ascii=False))

    async def _fazer_backup(self):
        """Cria um backup do arquivo corrompido antes de sobrescrever."""
        if not os.path.exists(self.arquivo):
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_nome = f"{self.arquivo}.backup_{timestamp}"
            shutil.copy2(self.arquivo, backup_nome)
            print(f"📦 Backup do arquivo corrompido criado: {backup_nome}")
        except Exception as e:
            print(f"⚠️ Não foi possível criar backup: {e}")
