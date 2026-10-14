# LLM — Pasta de Memória do Projeto

> **LEIA ISSO PRIMEIRO, IA.** Esta pasta existe para que qualquer sessão de IA
> consiga entender o estado do projeto sem precisar ler tudo do zero.

## Ordem de leitura obrigatória

1. `README.md` (este arquivo) — o protocolo.
2. `PROJECT_STATE.md` — o que o projeto É, arquivos, arquitetura, decisões.
3. `ISSUES.md` — problemas abertos / pendências conhecidas.
4. `TERMUX.md` — **se a tarefa for rodar no Android/Termux.** Setup, o que
   funciona, o que não funciona, e as mudanças de código necessárias.
5. `TEMPLATE.md` — **medidas de `img/template.png`** e onde o preço deve ser
   desenhado. Leia antes de mexer em `gerar_arte()`.
6. `RECOVERY_bot_py.md` — **spec de uma versão do `bot.py` mais nova que a
   que está na pasta.** Leia se a tarefa tocar em Selenium, bloqueio do
   Mercado Livre, ou link de loja do ML.
7. `CHANGELOG.md` — histórico cronológico, **do mais recente para o mais antigo**.

## Protocolo de trabalho (obrigatório para toda IA)

**AO INICIAR uma sessão:**
1. Ler `PROJECT_STATE.md` e `ISSUES.md`.
2. Ler as últimas entradas do `CHANGELOG.md`.
3. Não repetir trabalho já feito. Não "descobrir" bugs já documentados.

**DURANTE a sessão:**
- Toda alteração de código, decisão de arquitetura, bug encontrado ou hipótese
  testada deve ser registrada em `CHANGELOG.md` com uma nova entrada no topo.
- Bugs / tarefas em aberto entram em `ISSUES.md`.
- Se a alteração mudou o Understanding do projeto (estrutura, fluxo, decisões),
  atualizar `PROJECT_STATE.md`.

**AO ENCERRAR uma sessão:**
- Escrever no `CHANGELOG.md` o que foi FEITO e o que NÃO foi concluído.
- Atualizar `ISSUES.md` com o que ficou pendente.
- Nunca terminar sem registrar o estado final.

## Formato de entrada do CHANGELOG.md

```markdown
## [YYYY-MM-DD HH:MM] — <Título curto da sessão>

**Objetivo:** o que a IA tentava fazer.

**Arquivos alterados:**
- `caminho/arquivo.py` — o que mudou

**Análise / o que foi observado:**
- achados, hipóteses testadas, logs relevantes

**Resultado:**
- ✅ feito / ❌ falhou / ⏳ parcial — com detalhes do porquê
```

## Regra de ouro

> Se não está escrito nesta pasta, a próxima IA não vai saber.
> Na dúvida, **escreva mais**. Custa 10 segundos.

## ⚠️ Segurança — nunca quebrar

O projeto tem um `.gitignore` já configurado. **Não remover**, e não criar
commit com `-f` nos arquivos ignorados.

**Nunca ler, imprimir ou versionar o conteúdo do `.env`** (32 chaves com
tokens reais do Telegram, Instagram, Vercel Blob e tags de afiliado).
Para conferir se uma variável existe, ver só o **nome** da chave.

Os `*.session` são sessões autenticadas do Telethon — **equivalam a senha
da conta do Telegram**. Nunca compartilhar.

Se um segredo for commitado por engano, **não basta apagar o arquivo**:
o git guarda o histórico. Precisa rodar `git filter-repo` e trocar as
credenciais no Telegram/Instagram/Vercel.