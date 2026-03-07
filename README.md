# 🎮 Thanathos Bot

Bot para Discord de adivinhação de personagens por emojis, inspirado no universo de **Lord of the Mysteries**.

Os jogadores recebem dicas em forma de emojis e precisam adivinhar qual personagem está sendo representado. O bot conta com sistema de rotações de emojis, evento secreto do Amon, gerenciamento completo de personagens e canais, e interface interativa com botões e menus.

---

## ⚙️ Requisitos

- **Python** 3.10+
- **discord.py** 2.7+
- Arquivo `token.txt` na raiz do projeto contendo o token do bot

## 🚀 Como Rodar

```bash
pip install discord.py
```

Crie um arquivo `token.txt` com o token do seu bot Discord e execute:

```bash
py thanathos2.py
```

---

## 📁 Estrutura

| Arquivo | Descrição |
|---|---|
| `thanathos2.py` | Código principal do bot |
| `dados_jogo.json` | Dados persistentes (personagens, canais, cargos) |
| `token.txt` | Token do bot (não versionado) |

---

## 🎯 Comandos do Jogo

| Comando | Descrição | Onde funciona |
|---|---|---|
| `#iniciar` | Inicia uma nova rodada de adivinhação | Canais permitidos |
| `#dica` | Pula o timer e revela a próxima dica imediatamente | Canais permitidos |

### Como funciona o jogo

1. Um jogador digita `#iniciar` em um canal permitido.
2. O bot sorteia um personagem e começa a exibir emojis como dicas, um por vez, a cada 20 segundos.
3. Os jogadores digitam seus chutes diretamente no chat.
4. O bot reconhece respostas mesmo com acentos diferentes, maiúsculas/minúsculas, ou dentro de frases (ex: *"eu acho que é o Klein"*).
5. Quem acertar primeiro vence! Se ninguém acertar, o tempo esgota e o personagem é revelado.

---

## 📝 Comandos de Gerenciamento

> Disponíveis apenas nos **canais de gerência**, para administradores e cargos autorizados.

### Personagens

| Comando | Descrição |
|---|---|
| `#addpersonagem "Nome" "🦇, 👨, 🌃" "batman, bruce wayne"` | Adiciona um novo personagem com emojis e respostas aceitas |
| `#rmpersonagem Nome exato` | Remove um personagem pelo nome exato |
| `#editemoji` | Abre o editor interativo de emojis com interface paginada |
| `#search Nome` | Busca um personagem por nome com opções de editar ou deletar |
| `#listar` | Lista todos os personagens cadastrados (paginado com botões ◀ ▶) |

### Canais

| Comando | Descrição |
|---|---|
| `#addcanal <ID>` | Autoriza um canal para o jogo funcionar |
| `#rmcanal <ID>` | Remove um canal da lista de permitidos |

### Cargos

| Comando | Descrição |
|---|---|
| `#addcargo @Cargo` | Dá permissão de gerenciamento a um cargo |
| `#rmcargo @Cargo` | Remove a permissão de gerenciamento de um cargo |

---

## 🔒 Comandos de Administrador

> Exclusivos para administradores do servidor. Funcionam em **qualquer canal**.

| Comando | Descrição |
|---|---|
| `#addgerencia <ID>` | Define um canal como canal de gerência |
| `#rmgerencia <ID>` | Remove um canal da lista de gerência |

---

## 🧪 Comandos de Teste

| Comando | Descrição | Onde funciona |
|---|---|---|
| `#call_amon` | Força o evento Amon para testar o sistema | Canais de gerência |

---

## 🔧 Funcionalidades do Bot

### 🎰 Sistema de Rotações de Emojis

Cada personagem pode ter **múltiplas rotações** de emojis (R1, R2, R3...). A cada rodada, o bot sorteia uma rotação aleatória. Com **15% de chance**, cria um **mix raro** que mistura emojis de rotações diferentes — tornando a adivinhação mais difícil e imprevisível.

### 🎭 Evento Amon (1% de chance)

A cada `#iniciar`, há **1% de chance** do personagem **Amon** (o Enganador) se disfarçar de outro personagem:

- O bot pega os emojis de uma "vítima" e **injeta 2 emojis do Amon** em posições aleatórias.
- Títulos e footers podem conter **erros sutis** (ex: "Personagen!" sem o *m*, "acelarar" sem um *e*).
- A contagem de dicas pode estar levemente errada (±1).
- A cor do embed é *quase* idêntica ao verde normal, mas com variação imperceptível.

**3 cenários possíveis:**
- 🧐 **Amon Descoberto** — jogador chuta "Amon" corretamente.
- 🎭 **Enganado** — jogador chuta a vítima do disfarce, e Amon escapa com uma frase dramática (35% de chance, em spoiler tags).
- ⏰ **Timeout** — ninguém acerta e Amon é revelado.

### 🔍 Sistema de Busca (#search)

O comando `#search` permite encontrar personagens e agir sobre eles:

- **Match exato** → vai direto para a ficha do personagem
- **Match parcial** → encontra personagens que contêm o termo
- **Match por palavra** → usa regex com word boundary para buscas mais inteligentes
- **Múltiplos resultados** → exibe um dropdown para selecionar

A ficha do personagem mostra botões: **✏️ Editar Emojis**, **🗑️ Deletar** (com confirmação), e **↩ Voltar**.

### ✏️ Editor Interativo de Emojis (#editemoji)

Interface paginada com dropdown para selecionar personagens e botões de ação:

- **🔄 Substituir Rotação** — substitui os emojis de uma rotação existente
- **➕ Nova Rotação** — adiciona uma nova rotação de emojis
- **🗑️ Remover Rotação** — remove uma rotação (mantém no mínimo 1)
- **↩ Voltar** — retorna à lista de personagens

### 📋 Listagem Paginada (#listar)

Exibe todos os personagens com suas rotações, emojis e respostas aceitas, organizados em páginas de 5 personagens com botões **◀ Anterior** e **Próxima ▶**.

### 🛡️ Sistema de Permissões

- **Canais de gerência** — onde comandos administrativos funcionam (`#addgerencia`)
- **Canais permitidos** — onde o jogo pode rodar (`#addcanal`)
- **Cargos permitidos** — cargos que podem gerenciar o bot sem ser admin (`#addcargo`)
- **Administradores** — acesso total a todos os comandos

### ❌ Handler de Erros

O bot captura erros de comandos automaticamente e exibe mensagens amigáveis no Discord:

- Argumento faltando → aviso com instrução de uso
- Comando inexistente → ignorado silenciosamente
- Argumento inválido → mensagem de erro
- Erro inesperado → mensagem genérica + log no console

### 💾 Persistência de Dados

Todos os dados são salvos em `dados_jogo.json`:

- Lista de personagens com emojis (rotações) e respostas aceitas
- IDs dos canais permitidos e de gerência
- IDs dos cargos com permissão

O bot possui **retrocompatibilidade automática** — migra dados de versões anteriores (emojis em lista simples → formato de rotações).

---

## 📊 Dados Técnicos

| Configuração | Valor |
|---|---|
| Prefixo de comandos | `#` |
| Tempo entre dicas | 20 segundos |
| Personagens por página | 5 |
| Chance de mix raro | 15% |
| Chance do evento Amon | 1% |
| Chance de frase dramática Amon | 35% |
| Timeout de views interativas | 60–120 segundos |

---

## 📜 Licença

Projeto pessoal — Thanathos Bot.
