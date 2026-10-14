# Changelog

> **Adicione entradas NO TOPO** (mais recente primeiro).
> Formato definido em `README.md`.

---

## [2026-10-14 14:35] — Sessão 8: `.gitignore` criado para subir ao GitHub

**Objetivo:** o usuário avisou que vai publicar o projeto no GitHub.

**Arquivos criados:**
- `.gitignore` — novo

**Arquivos alterados:**
- `LLM/CHANGELOG.md`, `LLM/ISSUES.md`, `LLM/README.md` — esta sessão

### Situação do repositório

- Já existe um repo git em `E:/projetos/bot ML`, branch `main`.
- **Zero commits ainda** e **sem remote** → nada vazou. O `.gitignore` foi
  criado antes de qualquer commit, então está seguro.
- `.env` (32 chaves com tokens reais) está corretamente ignorado.

### O que o `.gitignore` bloqueia

| Categoria | Itens |
|---|---|
| Segredos | `.env`, `.env.*` (mantém `.env.example`), `*.pem`, `*.key` |
| **Sessão Telethon** | `*.session`, `*.session-journal` |
| Backups/bytecode | `*.backup`, `*.pyc-backup`, `__pycache__/`, `*.py[cod]` |
| **Estado de runtime** | `seen.json`, `vitrine.json`, `ig_queue.json`, `telegram_offset.json` |
| Gerados | `arte_*.jpg`, `*.log`, `nohup.out` |
| SO/editor | `.DS_Store`, `Thumbs.db`, `.idea/`, `.vscode/` |

> ⚠️ Os JSONs de runtime são ignorados **de propósito**: `vitrine.json`
> guarda links de afiliado com as tags embutidas. Não versionar isso.

### O que será commitado

```
.gitignore
.env.example
requirements.txt
bot.py
bot antigo.py
img/template.png
LLM/*.md  (7 arquivos)
LLM/RECOVERY_bot_py_from_pyc.txt   (636 KB)
```

### Varredura de segredo

Rodei regex de token do Telegram, token do Instagram, token da Vercel Blob,
API hash e senha de proxy em todos os arquivos que entram no commit.

Resultado: **1 falso positivo** — `bot.py` L89, que é só o comentário
explicando o formato `http://usuario:senha@host:porta`. Nenhum segredo real.

**Resultado:**
- ✅ `.gitignore` criado e validado com `git add --dry-run`
- ✅ Nenhum segredo vai para o commit
- ⏳ **Nada foi commitado** — o usuário decide quando fazer

**Comandos sugeridos ao usuário:**
```bash
git add -A
git commit -m "Bot de ofertas Vagante Promoções"
git remote add origin <url>
git push -u origin main
```

---

## [2026-10-14 14:20] — Sessão 7: erro no celular diagnosticado e corrigido (PROXY morto)

**Objetivo:** o usuário mandou uma foto (`E:\Pasta de erro\1.png`) do Termux
rodando o bot com vários erros.

**Arquivos alterados:**
- `bot.py` — `proxy_health()` agora **desliga o proxy** quando ele está morto
- `LLM/CHANGELOG.md`, `LLM/ISSUES.md`, `LLM/TERMUX.md` — esta sessão

### O que a foto mostra (log transcrito)

```
(venv) ~/.bot/bot $ python bot.py
>>> BOT VAGANTE PROMOÇÕES <<<
✅ Telegram conectado como @vagantepromo_bot
✅ Canal de destino: Vagante Promoções
📡 Canais monitorados: @linksBrazil, @xetdaspromocoes
✅ Instagram conectado como @vagantepromo (id 281222276434048679)
⚠️ proxy indisponivel (ProxyError) - a raspagem de ML/Shopee vai falhar.
🔍 Escutador do chat privado iniciado.
✅ Telethon conectado: @linksBrazil, @xetdaspromocoes
🤖 Ciclo do Telegram: planilha + raspagem
⚠️ Falha de rede em https://docs.google.com/spreadsheets/... : ConnectionError
⚠️ Planilha indisponivel (HTTP erro).
⚠️ Falha de rede em https://www.mercadolivre.com.br/ofertas?page=2 : ConnectionError
⚠️ Mercado Livre: 0 produtos (provavel bloqueio anti-bot).
⚠️ Falha de rede em https://shopee.com.br/api/v4/search/... : ConnectionError
⚠️ Shopee bloqueada (HTTP erro).
📋 Nenhum produto novo na planilha.
✅ Ciclo concluído: 0 oferta(s) da raspagem publicada(s).
⚠️ Falha de rede em https://http2.mlstatic.com/... : ConnectionError
✅ Instagram publicado: 18344077540253861
```

### 🟢 BOAS NOTÍCIAS — o bot JÁ FUNCIONA NO ANDROID

- ✅ **Pillow instalou no Termux** (o `import` da L27 não quebrou)
- ✅ Telegram, Instagram e **Telethon** conectaram
- ✅ **Publicou no Instagram** (id 18344077540253861)
- ✅ Rodando com **venv** em `~/.bot/bot`
- ✅ A foto do produto falhou, mas o post **saiu mesmo assim** — o fallback
  `arte_para_publicar → image_url` funcionou como previsto

### 🔴 CAUSA RAIZ DE TODOS OS ERROS: uma só

**O proxy do `.env` está morto**, e `http_get` aplica `proxies=PROXIES` em
**todas** as requisições — inclusive no Google Sheets, que **não precisa de
proxy**. Resultado: `ProxyError` → `PROXIES` continua configurado → tudo
vira `ConnectionError`, até a planilha que nunca precisaria do proxy.

### Correção aplicada

`proxy_health()` agora **desliga o proxy** em vez de só avisar
(esta é a **linha 176** da versão que se perdeu — recuperada do bytecode):

```python
global PROBE_AT, PROXIES          # <- PROXIES novo no global
...
if not PROBE_STATE["ok"]:
    log(f"⚠️ {PROBE_STATE['msg']} — PROXY desligado. Seguindo com a conexão "
        f"direta: Mercado Livre continua funcionando, Shopee pode bloquear.")
    PROXIES = None                # <- a correção
return PROBE_STATE["ok"]
```

O próprio `http_get` da versão perdida usava o mesmo `PROXIES` global —
ou seja, **essa era a única diferença**.

### Testado

| Cenário | Resultado |
|---|---|
| proxy morto → `proxy_health()` | ✅ `PROXIES` vira `None` |
| 2ª chamada (cache de 600s) | ✅ não reativa o proxy morto |
| sem proxy configurado | ✅ retorna `False` sem tentar nada |
| `http_get` com `PROXIES=None` | ✅ envia `proxies=None` (direto) |

**Sintaxe validada** com `py_compile`.

### ⚠️ O que NÃO é resolvido por essa correção

- **Shopee** pode continuar bloqueando mesmo direto — o `PROXIES=None`
  garante a conexão, mas o bloqueio do Shopee é do próprio IP.
- O `PROXY` do `.env` precisa ser **trocado por um que funcione** ou
  **deixado vazio** no celular. Hoje ele está lá, morto.
- A mensagem "Planilha indisponivel (HTTP erro)" é enganosa: não foi erro
  HTTP, foi `ConnectionError` do proxy.

**Resultado:**
- ✅ Causa raiz identificada e corrigida (1 linha).
- ✅ O bot deve voltar a ler a planilha e raspar o ML no celular.
- ⏳ **O `bot.py` novo precisa ser copiado para o celular.**

**Próximo passo sugerido:** copiar o `bot.py` atualizado para `~/.bot/bot` no
Termux e rodar `python bot.py --once` para confirmar.

---

## [2026-10-14 13:55] — Sessão 6: `gerar_arte` reescrito com o template (opção C)

**Objetivo:** o usuário escolheu a **opção C** (produto em cima, banner com
o preço embaixo) e pediu: *"não poe o titulo na arte. Ela ja esta na
descrição"*.

**Arquivos alterados:**
- `bot.py` — `gerar_arte()` reescrito + 3 funções novas + constantes do
  template + `TEMPLATE_FILE` corrigido (era **58.847 → 61.693 bytes**)
- `LLM/TEMPLATE.md` — atualizado com o que foi implementado
- `LLM/CHANGELOG.md` — esta entrada

**Backup:** `bot.py.backup` continua com a versão anterior à sessão 5.

### Correções aplicadas

1. **Bug A — caminho do template (crítico, silencioso).**
   `TEMPLATE_FILE` apontava para `template.png` na raiz; o arquivo está em
   `img/template.png`. `.exists()` era **False** → o template **nunca era
   usado** e o bot caía no gradiente sem nenhum erro.

2. **Bug B — geometria de card quadrado num template panorâmico.**
   `resize((1080, 1080))` num template de 1024×217 (distorção ~5x), e todos
   os elementos em coordenadas de 1080² — inclusive o preço em `y=790`,
   **fora** dos 217px do template.

3. **Bug C — placeholder branco sólido.**
   `ImageDraw` sobrescreve o pixel, não faz alpha-blend. O retângulo
   translúcido `fill=(255,255,255,22)` virava **branco sólido** ao converter
   para JPEG (o alpha era descartado). Corrigido com overlay separado +
   `alpha_composite`.

4. **Bug D — emoji 🛍️ virava bloco branco.**
   Sem TTF disponível, `load_font` cai em `load_default()` (fonte bitmap),
   que não tem emoji. Substituído pelo texto "sem imagem".

### Implementado

- Card **1080×1350** (4:5 nativo do Instagram).
- Banner `img/template.png` colado em baixo (1080×229, ratio preservado).
- **Preço dentro do quadro de vidro** — 2 linhas (`DE R$` / `POR R$`) quando
  há desconto, 1 linha quando não.
- **Fonte auto-ajustada** (`_fit_font`): `R$ 1.299,00` reduz a fonte sozinho.
- Selo `-N%` fora do quadro, no gelo à esquerda (evita colidir com "DE R$").
- **Título removido da arte** (continua na caption, L1485).
- Barra "VAGANTE PROMOÇÕES" removida (o banner já tem o yeti de marca).
- Fallback sem template preservado (cartão escuro com pílula de preço).
- Novas constantes: `TEMPLATE_W/H`, `TEMPLATE_BOX`, `TEMPLATE_BOX_PAD`,
  `ART_W/ART_H`, `_TPL_SCALE`.

### Testado (arte real gerada, 1080×1350 em todos)

| Caso | Resultado |
|---|---|
| `46,90` de `96,00` (-51%) | ✅ |
| só `46,90` | ✅ |
| `1.299,00` de `2.499,00` (-48%) | ✅ fonte reduzida sozinha |
| `9,90` | ✅ |
| sem preço | ✅ "Confira na bio" |
| sem foto | ✅ placeholder translúcido |
| sem template | ✅ fallback escuro |

**Sintaxe validada** com `py_compile`. Nada foi publicado no Instagram/Telegram.

**Resultado:**
- ✅ Template agora é realmente usado, sem distorção.
- ✅ Preço dentro do quadro, com auto-ajuste de fonte.
- ✅ Sem título na arte, como pedido.

**Próximo passo sugerido:** rodar `python bot.py --once` num ambiente com
acesso à rede para ver o post real. nesta máquina o download das fotos do ML
falha (proxy do `.env` está fora do ar).

---

## [2026-10-14 12:50] — Sessão 5: template `img/template.png` analisado

**Objetivo:** o usuário pediu para verificar a pasta `img`, que tem o template
a ser usado, com o preço dentro do quadrado.

**Arquivos criados:**
- `LLM/TEMPLATE.md` — medidas do template e onde o preço deve entrar (novo)

**Arquivos alterados:**
- `LLM/README.md` — `TEMPLATE.md` entrou na ordem de leitura
- `LLM/CHANGELOG.md` — esta entrada

**Análise / o que foi observado:**

1. **O template é `img/template.png`** — PNG, **1024×217 px**, ratio 4.72:1.
   **Não é quadrado**, é uma faixa panorâmica: monstro/gelado à esquerda,
   quadro de vidro à direita.

2. **Medidas do quadrado do preço** (detectadas por análise de brilho da
   borda de gelo):
   - tamanho original: x 576→951, y 28→183 · área útil interna 355×135
   - a 1080px de largura: **x 608→1003, y 30→193** · útil **374×142**
   - **centro (805, 111)**

3. **🔴 BUG A — caminho errado, o template nunca é usado:**
   `bot.py` L102 tem `TEMPLATE_FILE = BASE_DIR / "template.png"`, mas o
   arquivo está em `img/template.png`. `TEMPLATE_FILE.exists()` → False →
   o código **cai silenciosamente no gradiente**. Não há erro, só um
   fallback invisível — por isso nunca foi notado.

4. **🔴 BUG B — geometria quadrada vs template panorâmico:**
   `gerar_arte` foi escrito para 1080×1080. Com o template real:
   - L567 estica 1024×217 para 1080×1080 → **distorção de ~5x na vertical**
   - Nenhum dos elementos cabe: título y≈155, badge (600,250),
     foto (300,240,780,720), **preço y=790** (fora da imagem de 217px!),
     barra "VAGANTE PROMOÇÕES" y 1022–1080.

5. **Fonte que cabe no quadrado** (medido com `ariblk.ttf`, área útil 374×142):
   - `R$ 46,90` → máx 78px
   - `POR R$ 46,90` → máx 50px
   - `R$ 1.299,00` → máx 56px
   → **layout de 2 linhas obrigatório** (`DE R$` 46px + `POR R$` 50px).
   **Um mock foi gerado e o preço cabe com folga dentro do quadro.**

6. **Decisão de design pendente:** o Instagram feed é 4:5 (1080×1350) ou
   1:1; um banner 4.72:1 ficaria minúsculo. Três opções registradas em
   `TEMPLATE.md` seção 5.

**Resultado:**
- ✅ Template medido, quadrado do preço localizado com precisão.
- ✅ Dois bugs confirmados e documentados (um deles faz o template ser
  ignorado silenciosamente hoje).
- ✅ Mock gerado comprovando que o preço cabe dentro do quadro.
- ⏳ **Nada foi alterado no `bot.py`.**
- ⏳ Aguardando o usuário escolher o layout (A / B / C).

---

## [2026-10-14 12:30] — Sessão 4: plano para rodar no Android via Termux

**Objetivo:** o usuário revelou o propósito real do projeto — **rodar num
celular via Termux**, com o scrap funcionando como no PC.

**Arquivos criados:**
- `LLM/TERMUX.md` — plano completo (novo)

**Arquivos alterados:**
- `LLM/ISSUES.md` — 3 issues novas de compatibilidade Android
- `LLM/README.md` — `TERMUX.md` entrou na ordem de leitura
- `LLM/CHANGELOG.md` — esta entrada

**Análise / o que foi observado:**

1. **BLOQUEIO CRÍTICO achado no código:** `bot.py` L27 faz
   `from PIL import Image, ImageDraw, ImageFilter, ImageFont`
   **incondicionalmente**. Sem Pillow no Android o bot **morre no startup**.
   O `curl_cffi` (L30-35) já é opcional — o Pillow ficou de fora.

2. **A versão perdida do `bot.py` já tinha esse guard** (`HAVE_PIL` + aviso
   "Pillow ausente (comum no Termux/Android)"). A correção foi perdida junto
   com o arquivo — ou seja, **isso estava sendo feito quando sumiu**.

3. **O resto já degrada bem:** `gerar_arte` (L662) devolve `None` no except e
   `arte_para_publicar` (L670) cai para a `image_url` original. Então só o
   guard do import é necessário — Telegram continua, Instagram posta sem arte.

4. **INSIGHT PRINCIPAL — o IP do celular é a vantagem.** O código (L87-88)
   assume que ML/Shopee bloqueiam por IP. No PC o IP é datacenter/VPN, e por
   isso o bot precisou de Selenium com janela real. **No celular o IP é
   residencial e móvel**, que o ML trata com muito mais folga.
   → No Termux, `curl_cffi` + IP residencial provavelmente **basta**, sem
   proxy e sem navegador nenhum.

5. **Pesquisa (estado de 2026-10):**
   - **curl_cffi**: sem wheel Android no PyPI; compila nativamente no Termux
     com `pkg install clang make libcurl libandroid-support`. O
     `scripts/build.py` do curl_cffi já tem `is_android_env()` (suporte
     Android a partir da 0.16.x). Alternativa com wheels prontas:
     `pip install -i https://pypi.flet.dev/curl-cffi curl-cffi`.
     **32-bit não tem build** — Termux tem que ser `aarch64`.
   - **Pillow**: compila com
     `pkg install ndk-sysroot clang make libjpeg-turbo` +
     `pip install Pillow --no-binary :all:` (documentação oficial do Pillow).
   - **Selenium**: **não funciona** no Termux — o `selenium-manager` não é
     compilado para arm64. Saídas: `cdriv` (PyPI, feito para Termux) ou
     CDP puro com `chromium-browser --no-zygote --single-process`.
     Precisa de `LD_PRELOAD=libtermux-exec.so`.
   - `telethon`, `requests`, `bs4`, `dotenv`: funcionam normalmente.

6. **Risco operacional no Android:** sem `termux-wake-lock` + desativar
   otimização de bateria, o SO mata o processo em ~15 min.

**Resultado:**
- ✅ Diagnóstico completo e plano de 3 níveis escrito em `TERMUX.md`.
- ✅ 3 issues novas registradas em `ISSUES.md`.
- ⏳ **Nada foi alterado no `bot.py`** — só análise e pesquisa.

**Próximos passos sugeridos ao usuário:**
1. Rodar o **NÍVEL 0** do `TERMUX.md` (5 min) para ver se o IP residencial
   já resolve o bloqueio. Se resolver, não precisa de Selenium nem proxy.
2. Aplicar a correção 4.1 (Pillow opcional) — hoje o bot **não sobe** no
   Android sem ela.

---

## [2026-10-14 12:05] — `bot.py` RECUPERADO (versão mais antiga) — sessão 3

**Objetivo:** o usuário salvou na pasta a versão do `bot.py` que estava
rodando em memória.

**O que foi feito:**
- Backup imediato antes de qualquer análise:
  - `bot.py.backup` (58.847 bytes)
  - `bot.py.pyc-backup` (124.236 bytes) — cópia do bytecode fora do `__pycache__`
- Comparação entre o fonte recuperado e o bytecode.

**Resultado da comparação — ATENÇÃO:**

| | `bot.py` recuperado | bytecode (versão nova) |
|---|---|---|
| Linhas | **1.261** | **~2.150** |
| Bytes | **58.847** | **85.872** |
| Funções | **47** | **74** |
| Origem | versão em memória (11:34:25) | fonte de 14/10 **11:43:32** |

**O fonte recuperado é um ancestral estrito da versão nova:**
todas as 47 funções dele existem na versão do bytecode
(`SO NO FONTE RECUPERADO: 0`). A versão nova tem **27 funções a mais**,
que **continua perdida**:

- `selenium_driver`, `selenium_get`, `browser_get` — **Selenium com Chrome real**
- `is_store_link`, `_ml_product_url`, `_ml_price`, `store_catalog`,
  `_keywords`, `resolve_store_link` — **resolução de link de loja do ML**
- `_ml_link`, `affiliate_status`, `_warn_once` — camada de tag de afiliado
- `_is_bot_wall` — detecção de `suspicious-traffic` / captcha
- `strip_params` — remoção de tags próprias
- `_image_to_jpeg`, `_image_candidates` — download de imagem mais robusto
- `tg_typing`, `notify_admin`, `bot_can_post`, `check_affiliate_config`
- `pick` — detecção flexível de colunas do CSV
- `build_post_photo`, `split_price_and_url`, `destination_label`
- `worker`, `run`, `handler` — nested functions

> Ou seja: a versão nova é a que **corrige o bloqueio do ML** (Selenium +
> bot-wall) e **resolve link de loja**. Sem ela, o bot funciona, mas
> pode raspar de menos e pode descartar comissão em link de loja.

**Arquivos alterados:**
- `bot.py.backup` — novo (cópia de segurança)
- `bot.py.pyc-backup` — novo (cópia de segurança do bytecode)
- `LLM/PROJECT_STATE.md`, `LLM/ISSUES.md` — atualizados
- `LLM/CHANGELOG.md` — esta entrada

**Análise / o que foi observado:**
- `bot.py` recuperado **é sintaticamente válido** e está pronto para rodar.
- Tem o fallback de nomes de tag (L72–74): `ML_MATT_WORD` **ou**
  `ML_AFFILIATE_USERNAME` — o `.env` atual tem os dois.
- Usa `PROXY`/`HTTPS_PROXY`, `telethon` (sob demanda, L1299) e
  `BASE_DIR / "ig_queue.json"`.
- **Não tem** Selenium, resolução de loja, `notify_admin` nem `ADMIN_CHAT_ID`.
- O `.pyc` só é criado quando o módulo é **importado** — nunca por
  `python bot.py`. Portanto a versão das 11:43 veio de um `import bot`
  (provavelmente o debugador/language server do Antigravity).
- **O processo PID 10536 continua rodando** `bot.py` desde 11:34:25.

**Resultado:**
- ✅ Fonte recuperado e com backup feito.
- ✅ Projeto voltou a ter código-fonte executável.
- ⏳ A versão das 11:43 (a melhor) continua perdida — mas está 100%
  documentada em `RECOVERY_bot_py.md` + disassembly.
- ⏳ Nada foi alterado no `bot.py` nesta sessão.

**Próximo passo sugerido:** decidir se vale reimplementar as 27 funções
perdidas (principalmente Selenium + resolução de loja), já que a spec
completa está disponível.

---

## [2026-10-14 11:55] — Sessão 2: recuperação do `bot.py` via bytecode — CRÍTICO

**Objetivo:** reanalisar o projeto com mais profundidade.

**Resultado principal:** o código principal do projeto (`bot.py`,
~2.150 linhas / 85.872 bytes) **não está na pasta**. Foi apagado do disco.
Só restou o bytecode em `__pycache__/bot.cpython-311.pyc`, do qual foi
extraída a estrutura completa.

**Arquivos criados:**
- `LLM/RECOVERY_bot_py.md` — spec completa do `bot.py` recuperado (novo)
- `LLM/RECOVERY_bot_py_from_pyc.txt` — dump de 636 KB com disassembly
  completo (novo)

**Arquivos alterados:**
- `LLM/PROJECT_STATE.md` — reescrito com a arquitetura real do `bot.py`
- `LLM/ISSUES.md` — reescrito; issues da sessão 1 corrigidas/marcadas
- `LLM/CHANGELOG.md` — esta entrada

**Método:** o `.pyc` foi carregado com `marshal` + `dis` no mesmo Python
3.11 que o compilou, produzindo: header (tamanho/data do original), docstring
do módulo, índice das 63 funções com argumentos/locais/atributos, constantes
globais (regex, listas de tags, HELP) e disassembly completo.

**Análise / o que foi observado:**

1. **CRÍTICO — `bot.py` apagado.** Compilado 14/10 11:43:32. Busca em todo o
   `C:\` não achou o fonte. O `bot.py` rodava com sucesso (2 produtos
   publicados às 11:34, `vitrine.json` com 8 itens, sessão Telethon
   autenticada).

2. **CRÍTICO — processo ainda vivo.** PID **10536** roda
   `python.exe bot.py` desde 11:34:25 com a versão em memória.
   **Matar = perder o fonte para sempre.**

3. **CRÍTICO — outra IA no projeto.** O IDE **Antigravity** tem `bot.py`
   aberto (`bot ML - Antigravity - bot.py`) e foi quem lançou o processo
   (variável `BUNDLED_DEBUGPY_PATH` → extensões de debug do Antigravity).
   Duas IAs no mesmo arquivo foi provavelmente **a causa da perda**.
   → O usuário precisa eleger **uma** IA para este projeto.

4. **CORREÇÃO da sessão 1:** a divergência de nomes de tag
   (`ML_MATT_WORD` vs `ML_AFFILIATE_USERNAME`) **não quebra o bot**. As
   constantes do bytecode mostram que o `bot.py` aceitava **as duas formas**,
   e o `.env` tem ambas. Issue fechada.

5. **O `.env` já está preparado** para o `bot.py`: 32 chaves, incluindo
   `SOURCE_CHANNELS`, `PROXY`, `API_ID`/`API_HASH` (Telethon) e as quatro
   tags em duplicidade.

6. **`.env` tem 10 chaves lidas por nenhum código nosso** — `NOTION_DATABASE_ID`,
   `MAGAZINE_AFFILIATE`, `AMERICANAS_AFFILIATE`, `SHOPEE_APP_ID`,
   `SHOPEE_SECRET`, `SOURCE`, `CHANNEL`, `ML_AFFILIATE`, `BLOB_STORE_ID`,
   `TARGET_CHAT_ID`. → Existiu uma **terceira versão** ainda maior do bot
   (Notion + Magalu + Americanas + Shopee Open Platform).

7. **Bug achado:** `schedule_instagram` é **definida duas vezes** no `bot.py`
   (L1578 e L1590, corpos idênticos). A segunda sobrescreve a primeira —
   código morto.

8. **Bug achado no `bot antigo.py`:** `gerar_arte_produto` (L247) só procura
   fontes em caminhos Linux/Android. No Windows cai em
   `ImageFont.load_default()` → **preço ilegível na arte do Instagram**.
   O `bot.py` já tinha a lista correta (`C:\Windows\Fonts\ariblk.ttf` etc.).

9. **Bug potencial:** `telegram_offset.json` contém o inteiro cru
   `165745876`, mas `load_json` parece aceitar só dict. Se
   `private_listener` fizer `int(load_json(...))` sobre `{}`, o offset zera a
   cada restart. **Precisa confirmar no disassembly.**

10. **Instagram mudou de arquitetura:** o `bot.py` não lê mais `vitrine.json`;
    usa a fila `ig_queue.json` e, se o post falhar, **mantém o item na fila**.

**Resultado:**
- ✅ Estrutura completa do `bot.py` recuperada e documentada (63 funções).
- ✅ Comportamento é reconstruível a partir da spec + disassembly.
- ✅ Issues da sessão 1 revisadas: 1 resolvida, 3 refinadas.
- ⏳ **O fonte em si continua perdido.** Prioridade: recuperar pelo
  *Local History* do Antigravity antes de qualquer outra coisa.

**Próximo passo sugerido:** pedir ao usuário para tentar
*Local History* no Antigravity (`bot.py` aberto) **antes** de encerrar
qualquer instância dele.

---

## [2026-10-14] — Criação da pasta LLM e análise inicial do projeto

**Objetivo:** criar a pasta `LLM/` para registrar alterações e o que foi feito
em cada sessão, para que a próxima IA leia e saiba o estado do projeto.

**Arquivos alterados:**
- `LLM/README.md` — protocolo de leitura/escrita (novo)
- `LLM/PROJECT_STATE.md` — mapa do projeto, arquitetura, arquivos (novo)
- `LLM/ISSUES.md` — backlog de pendências (novo)
- `LLM/CHANGELOG.md` — este arquivo (novo)

**Análise / o que foi observado:**
- O projeto tem **um único arquivo de código**: `bot antigo.py` (673 linhas).
  O nome "antigo" é enganoso — é o script principal em uso.
- Dependências em `requirements.txt`: `requests`, `python-dotenv`,
  `beautifulsoup4`, `Pillow`, `curl_cffi`, `telethon`, `selenium`.
- **`telethon` e `selenium` estão no requirements mas NÃO são importados** pelo
  código. Assim como `session_promos.session`, `ig_queue.json` e
  `telegram_offset.json`, que existem na pasta mas não são usados.
- **Divergência grave:** o `.env.example` documenta variáveis
  (`ML_MATT_WORD`, `ML_MATT_TOOL`, `SHOPEE_TAG`, `ADMIN_CHAT_ID`,
  `SOURCE_CHANNELS`, `SEARCH_TERMS`, `RESOLVE_STORE_LINKS`, `USE_SELENIUM`,
  `SELENIUM_HEADLESS`, `PROXY`) que **não existem** no código, e vice-versa
  (`ML_AFFILIATE_USERNAME`, `ML_AFFILIATE_TOOL_ID`, `SHOPEE_AFFILIATE_ID`).
  → Conclusão: houve uma versão mais evoluída do bot que não está nesta pasta.
- Loop principal: `while True` com `sleep(10)`. Telegram a cada 1h, Instagram
  a cada 3h, polling de comandos a cada 10s.
- Fontes: Google Sheets CSV → ML → Shopee. Instagram consome `vitrine.json`
  (1 post por ciclo).
- `ig_seen.json` é lido pelo código mas não existe na pasta.

**Resultado:**
- ✅ Pasta `LLM/` criada com 4 arquivos de documentação.
- ✅ Projeto mapeado e pendências registradas em `ISSUES.md`.
- ⏳ Nada foi alterado no código — sessão apenas de análise/documentação.

**Próximo passo sugerido:** confirmar com o usuário se existe outra versão do
bot (Telethon + Selenium) em outro lugar antes de reimplementar do zero.