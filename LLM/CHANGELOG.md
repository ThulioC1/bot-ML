# Changelog

> **Adicione entradas NO TOPO** (mais recente primeiro).
> Formato definido em `README.md`.

---

## [2026-10-14 16:45] — Sessão 14: foto 3 — bot MORREU por `No module named 'websocket'`

**Objetivo:** o usuário mandou `E:\Pasta de erro\3.jpg` (log do Termux).

### Log transcrito

```
[14/10 16:06:31] >>> BOT VAGANTE PROMOÇÕES <<<
✅ Telegram conectado como @vagantepromo_bot
✅ Canal de destino: Vagante Promoções
📡 Canais monitorados: @linksBrazil, @xetdaspromocoes
✅ Instagram conectado como @vagantepromo (id 281222276434048679)
⚠️ proxy indisponivel (ProxyError) — PROXY desligado. Seguindo com a conexão direta...
🔍 Escutador do chat privado iniciado.
✅ Telethon conectado: @linksBrazil, @xetdaspromocoes        ← ✅ JÁ FUNCIONA
🤖 Ciclo do Telegram: planilha + raspagem
📊 Planilha: 0 produto(s) válido(s).
⊘ www.mercadolivre.com.br bloqueou o acesso (HTTP 200, pagina de verificacao).
⚠️ Selenium: selenium nao instalado (pip install selenium). Seguindo so com requests.
↪️ Selenium indisponível — tentando Chromium via CDP.
⚠️ Erro no ciclo principal: No module named 'websocket'     ← 💥 BOT MORREU
^C[14/10 16:06:55] Encerrado pelo usuário.

$ pip install selenium
  → Successfully installed ... selenium-4.51.0 websocket_client-1.9.2 ...

[14/10 16:07:29] (segunda execução — log cortado na foto)
```

### 🟢 O que deu certo

- **Telethon conectado** — a sessão expirada foi resolvida.
- A **escada de fallback funcionou**: HTTP → Selenium (falhou) → CDP.
- O `pip install selenium` **trouxe `websocket_client-1.9.2` como dependência**,
  então o módulo passou a existir.

### 🔴 O bug: dependência opcional derrubou o bot

`cdp_get` fazia `import websocket` **sem try/except**. Sem o módulo, a
exceção subia e matava o ciclo inteiro.

Pior: `browser_get` era chamado dentro de `fetch_mercado_livre_products`, que
é chamado por `telegram_cycle` — **um navegador ausente não pode parar o bot.**

### Correções aplicadas

1. **`cdp_get` virou casca + `_cdp_get`**: todo o corpo num `try/except` que
   devolve `None`. **Nenhum erro de navegador derruba mais o bot.**
2. **`import websocket` protegido** — se faltar, avisa com o comando exato e
   devolve `None` (o ciclo segue com `/social/<loja>`).
3. **`IS_ANDROID`** calculado uma vez; se Android, `USE_SELENIUM = False`
   automaticamente. Sem Selenium o `browser_get` vai direto pro CDP, sem
   perder tempo tentando (e sem imprimir erro vermelho).
4. **Diagnóstico no boot**: agora o Termux mostra, antes de qualquer ciclo:
   ```
   ✅ websocket-client OK — o /ofertas será lido via Chromium CDP.
   ℹ️ Navegador: /data/data/com.termux/files/usr/bin/chromium-browser
   ```
   ou, se faltar algo:
   ```
   ⚠️ websocket-client ausente: rode `pip install websocket-client`...
   ⚠️ Chromium NÃO ENCONTRADO (pkg install chromium-browser)
   ```
5. **`/status` no Telegram** ganhou duas linhas:
   - `Navegador: CDP — <estado>`
   - `Lojas ML: <lista>`

### Erro meu no caminho

A primeira edição do bloco de diagnóstico foi aplicada no `if PROXIES:` errado
(dentro do `except` do `proxy_health`) e quebrou a sintaxe. Corrigido —
`py_compile` passa e o arquivo tem **69 funções**.

**Resultado:**
- ✅ Bot não morre mais por dependência de navegador ausente
- ✅ No Android o Selenium é desligado sozinho (vai direto pro CDP)
- ✅ O log agora diz na hora o que está faltando
- ⏳ **Falta ver o log da 2ª execução** (cortado na foto) — era o teste real do CDP

---

## [2026-10-14 16:10] — Sessão 13: CDP no Termux — `/ofertas` funciona no celular (SEM Selenium)

**Objetivo:** o usuário escolheu a opção 3 — "a prioridade é rodar no celular".
Precisava de um backend de navegador que funcione no Termux, já que o Selenium
não existe para arm64.

### Por que CDP e não Selenium

Selenium no Termux é inviável: o `selenium-manager` não é compilado para arm64
e o ChromeDriver oficial não existe para Android. Mas o Chromium do Termux
fala **Chrome DevTools Protocol** direto por WebSocket — sem driver, sem
Selenium, sem Java.

### Implementado no `bot.py`

| Função | O que faz |
|---|---|
| `chromium_binary()` | acha `chromium-browser` (Termux), `chromium`, `chrome`… ou `CHROMIUM_BIN` |
| `cdp_server()` | sobe o Chromium com `--remote-debugging-port=9222` e espera a porta abrir |
| `cdp_get(url, wait, timeout)` | abre aba → espera `Page.loadEventFired` → `Runtime.evaluate` de `document.outerHTML` |
| `cdp_close()` | encerra o Chromium |
| `browser_get()` | agora é a escada: **requests → Selenium → CDP** |

Config nova: `CDP_PORT` (9222), `CDP_HOST` (127.0.0.1), `CDP_WAIT` (6),
`CHROMIUM_BIN`.

**Argumentos usados no Termux** (detectados por `sys.platform == "android"`):
```
--single-process --no-zygote
LD_PRELOAD=libtermux-exec.so
--remote-allow-origins=* --no-sandbox --disable-dev-shm-usage
--disable-blink-features=AutomationControlled --lang=pt-BR
```
> `--single-process` é obrigatório: o `LD_PRELOAD` do Termux quebra o zygote
> do Android, então o Chromium precisa rodar sem forks.

### Dois bugs meus no caminho

1. **Loop de leitura do WebSocket**: eu fazia `break` no primeiro timeout do
   `recv`. A resposta do `Runtime.evaluate` chega depois (mls 30) — então
   eu saía antes. Agora `continue` até o deadline.
2. **Aba aberta 2x**: eu criava a aba já com a URL e ainda mandava
   `Page.navigate`, gerando navegações duplicadas (msgs 12 e 18). Agora a aba
   abre em `about:blank` e só depois navega.

### ✅ PROVADO, com Selenium desligado (o mesmo caminho do celular)

```
3) cdp_get() em /ofertas   (USE_SELENIUM = False)
   ✅ HTML 727.898 bytes | cards: 49 | MLB-ids: 119 | parede anti-bot: False
      Kit 10 Cuecas Boxer Sem Costura Polo Wear So       149
      Ar Condicionado Inverter Philco 9000 Btus Fr   1.749
      Smartphone Motorola Moto G17 4g - 256gb 4gb        966
      Creatina Growth Supplements Monohidratada em        64

4) fetch_mercado_livre_products() completo
   🚫 www.mercadolivre.com.br bloqueou o acesso (HTTP 200, pagina de verificacao).
   ↪️ Selenium indisponível — tentando Chromium via CDP.
   📦 Catálogo da loja: 19 produto(s)
   ✅ Mercado Livre: 48 produto(s).
      R$   165,78  Mala de Bordo Rígida Sweet Studio...        [raspagem]
      R$    96,00  Mochila Tática Imperpeável Militar...        [raspagem]
      R$   418,00  Microsoft 365 Family 1 Ano + Kaspersky      [raspagem]
```

**48 produtos — sendo 29 do `/ofertas` via CDP e 19 do catálogo `/social/`.**

### O que o usuário precisa fazer no Termux

```bash
pkg install chromium-browser
pip install websocket-client        # python puro, instala sem compilar
```

E ter `termux-wake-lock` ativo, porque o Chromium é pesado.

**Resultado:**
- ✅ `/ofertas` funciona no celular, sem Selenium
- ✅ Escada de 3 níveis: requests → Selenium (PC) → CDP (Android)
- ✅ `/social/<loja>` continua como reserva
- ⏳ **Não testado em hardware Android** — validado no PC com Chrome, forçando o
  caminho CDP. O Chromium do Termux pode ter quirks.

---

## [2026-10-14 15:45] — Sessão 12: `/ofertas` volta a funcionar com Chrome real (Selenium)

**Objetivo:** o usuárioukes Year質問ou: *"Não tem como o bot fazer scrap
nessa pagina não? Eu tinha uma versão dele que sorteava uma das paginas
dessa sessão do mercado livre e trazia os produtos normalmente."*

### 🔴 EU ESTAVA ERRADO na sessão 11

Na sessão 11 eu concluí que `/ofertas` era "impossível" e substituí a fonte
por `/social/<loja>`. **Isso estava errado.** Eu tinha testado **só HTTP**
(`requests` e `curl_cffi`) e concluí que o ML bloqueia tudo.

O usuário tinha razão: a versão anterior dele funcionava. Investigando o
bytecode da versão perdida, achei a diferença — e ela é **uma função**:

```
L1223 fetch_mercado_livre_products → usava browser_get(), NÃO http_get()
L276  browser_get(url, wait)  "HTML de uma pagina, com o plano B ja
                              aplicado (requests -> Chrome)"
```

`browser_get` tenta HTTP; se vier `account-verification` ou
`suspicious-traffic`, **sobe um Chrome de verdade**. Era isso.

### Por que o Chrome passa e o HTTP não

O `selenium_driver` da versão perdida tem o comentário exato:
> *"Sobe um Chrome fora da tela. Sem janela o ML devolve a parede anti-bot."*

Argumentos porteados:
`--window-position=-32000,-32000` (janela **real**, fora da tela — headless
também é barrado), `--disable-blink-features=AutomationControlled`,
`excludeSwitches: [enable-automation, useAutomationExtension]`,
`--lang=pt-BR`, `--window-size=1400,1000`.

### ✅ PROVADO nesta máquina

```
1) http_get em /ofertas
   🚫 www.mercadolivre.com.br bloqueou o acesso (HTTP 200, pagina de verificacao).
   parede anti-bot: True

2) browser_get em /ofertas  (mesma URL)
   ✅ Chrome (Selenium) iniciado — o Mercado Livre volta a responder.
   -> HTML de 673.099 bytes | cards: 49 | parede anti-bot: False
      Tênis Fila Corrida Caminhada Heating Treino        333
      Combo Teclado e Mouse sem fio Logitech MK235       169
      Furadeira Parafusadeira A Bateria 12V 3/8" 1       209

3) fallback /social/<loja>
   📦 Catálogo da loja: 19 produto(s)
   📦 Catálogo da loja: 10 produto(s)
   ✅ Mercado Livre: 48 produto(s).
```

**Mesma URL, mesmo momento: HTTP devolve a parede; Chrome devolve 49 produtos.**

### O que foi implementado no `bot.py`

| Item | Detalhe |
|---|---|
| `selenium_driver()` | Chrome de janela real fora da tela, singleton com lock |
| `selenium_get(url, wait, timeout)` | baixa a página; se o ML barrar até o Chrome, devolve `None` |
| `class _Page` | shim com `.text`/`.url`/`.status_code` para a mesma interface do `requests.Response` |
| `browser_get(url, wait)` | HTTP → se parede anti-bot → Chrome |
| `fetch_mercado_livre_products()` | voltou a usar `/ofertas?page=N` via `browser_get`; mantém `/social/<loja>` como **reserva** |
| Config | `USE_SELENIUM` (default `1`), `SELENIUM_HEADLESS` (default `0` = janela real) |

Ainda da sessão 11, que continuam válidos:
- `remember_store(url)` — aprende lojas `/social/<user>` dos links de canal
- `known_stores()` — lojas do `.env` (`ML_STORES`) + as aprendidas
- `lojas.json` — persistência

### Nota importante sobre o celular

**Selenium não funciona no Termux** (o `selenium-manager` não é compilado
para arm64). Então no celular o `/ofertas` via Chrome fica indisponível e o
bot cai na reserva `/social/<loja>` — que funciona (48 produtos no teste).

Para `/ofertas` no celular seria preciso **CDP** (Chrome DevTools Protocol)
em vez de Selenium. Ver `TERMUX.md`.

**Resultado:**
- ✅ Corrigido um erro meu: `/ofertas` **é** raspável, com Chrome de verdade
- ✅ Provado com 49 produtos na mesma URL que o HTTP bloqueia
- ✅ `/social/<loja>` mantido como reserva (funciona em qualquer lugar)

---

## [2026-10-14 15:10] — Sessão 11: `resolve_store_link` implementado (link de loja vira link de produto)

**Objetivo:** o usuário aprovou ("se isso for resolver, sim") implementar a
resolução de link de loja do ML, que faltava desde a sessão 10.

**Arquivos alterados:**
- `bot.py` — 6 funções novas + `affiliate_link` integrado + handler do
  Telethon reordenado
- `LLM/CHANGELOG.md`, `LLM/ISSUES.md`, `LLM/PROJECT_STATE.md` — esta sessão

### O que foi implementado

Portado do bytecode da versão perdida (`RECOVERY_bot_py.md`):

| Função | O que faz |
|---|---|
| `_keywords(text)` | tokeniza, tira acento (`_ACCENTS`) e remove `STOP_WORDS` |
| `_ml_price(card)` | preço do card via `.andes-money-amount__fraction` + `__cents` |
| `_ml_product_url(href)` | canônico `/<slug>/p/MLB<id>`, preserva `pdp_filters`/`searchVariation`, joga fora **todo** rastreamento (`matt*`) |
| `store_catalog(url)` | lê `/social/<user>`, cache 5 min, retorna `[{title, price, url, image}]` |
| `resolve_store_link(url, price, title)` | casa o produto por **preço (8% de folga) + similaridade de título** |

Novas constantes: `RESOLVE_STORE_LINKS` (default `1`), `STOP_WORDS`,
`_ACCENTS`, `ML_PRODUCT_RE`.

### Ajuste no handler do Telethon

O preço e o título agora são lidos **antes** de montar os links (antes eram
depois). Sem isso o `resolve_store_link` receberia `price=None, title=None`
e nunca acharia o produto — justamente o caso dos canais `@linksBrazil` e
`@xetdaspromocoes`, que mandam encurtado de loja.

### Scoring

```python
price_ok = abs(item.price - price) / price <= 0.08
title_score = |palavras em comum| / |palavras do título|
score = 2.0 + title_score   se preço bateu
      = 2.0 * title_score   se só o título (100% de match aprova)
aceita se best_score >= 2
```

> A primeira versão dava no máximo 1.5 ponto sem preço, ou seja **só título
> nunca aprovava**. Corrigido no teste (c).

### ✅ Verificado contra a loja REAL

`https://www.mercadolivre.com.br/social/linksbrazil` — **não é bloqueada**
(HTTP 200, sem bot-wall, 19 `.poly-card`).

```
R$  199,90  Proteína Black Skull Whey 100% Hd Em Pó Sabor Baunil
R$  329,40  Headset Gamer Wireless Warrior - Ph704 Preto
R$  100,00  Valorant R$100 (digital)
R$  150,00  Uber Gift Card R$150 (digital)
R$   86,00  Colônia Natura #urbano Masculino 100ml
R$  88,22  Kit 3 Fans Tgt Striker Rainbow 120mm
```

| Teste | Resultado |
|---|---|
| (a) preço + título exatos | ✅ achou o produto certo |
| (b) preço perturbado +3% | ✅ achou |
| (c) só título, sem preço | ✅ achou |
| (d) título sem relação | ✅ não achou (não inventa) |

### O resultado final, com o link da foto

**Antes:**
```
https://meli.la/1w4qNk3?matt_word=coth8154082&matt_tool=20122674
```
→ link curto, vai para a loja do outro afiliado, **não paga**.

**Agora:**
```
https://www.mercadolivre.com.br/produto/p/MLB72006876?matt_word=coth8154082&matt_tool=20122674
```
→ link de **produto** com a tag do usuário. **Paga comissão.**

**Sintaxe validada** com `py_compile`. Nada foi publicado.

### ⚠️ Limites conhecidos

- Só a **primeira página** do catálogo da loja é lida (19 itens). Lojas com
  mais produtos podem precisar de paginação.
- Se o preço do canal não bater com nenhum item e o título não for
  conclusivo, a oferta é descartada e o dono é avisado (comportamento
  seguro — melhor que postar link quebrado).
- A loja é cacheada por 5 min; se o canal mandar o mesmo link várias vezes
  em sequência, o custo cai bastante.

**Resultado:**
- ✅ Link de loja agora vira link de produto que paga comissão
- ✅ Tag de outro afiliado removida em todos os caminhos
- ✅ Testado contra a loja real, 4/4

---

## [2026-10-14 14:55] — Sessão 10: link encurtado não era expandido (bug de método HTTP)

**Objetivo:** o usuário mandou a 2ª foto (`E:\Pasta de erro\2.jpeg`, 14:43)
mostrando posts no canal com:
```
https://meli.la/1w4qNk3?matt_word=coth8154082&matt_tool=20122674
```
e reclamando: *"o link não esta sendo decifrado novamente. Esta pegando o
link encurtado e pondo minhas tags. o que não adianta pois envia o link de
outra loja"*.

### 🔴 CAUSA RAIZ — não é bloqueio de IP. É método HTTP.

`expand_url()` usava **`requests.head()`**. O encurtador do ML **não responde
a HEAD**:

| URL | HEAD | GET |
|---|---|---|
| `https://meli.la/1w4qNk3` | **HTTP 405** (não expande) | **HTTP 200 → expande** |
| `https://shope.ee/2VdqXs` | HTTP 200 mas cai em `/error_page` | — |
| `https://a.co/d/abc123` | HTTP 404 | — |

E como 405 **não é exceção**, o `except` que fazia o fallback para GET
**nunca era executado** — era código morto. Resultado: `expand_url` devolvia
o próprio link curto, o `affiliate_link` caía no fallback e colocava a tag em
cima do `meli.la`.

### 🔴 E o link expandido é uma LOJA (confirma a complaint)

`GET` em `meli.la/1w4qNk3` dá:
```
https://www.mercadolivre.com.br/social/linksbrazil
  ?matt_word=linksbr&matt_tool=17783195&forceInApp=true&...
```

Duas coisas:
1. É `/social/` = **link de LOJA**, que **ignora tag de afiliado**.
2. Traz a tag de **outro afiliado** (`matt_word=linksbr`) — precisa ser removida.

É literalmente "envia o link de outra loja". É o caso que a versão perdida
tratava com `is_store_link` + `resolve_store_link`.

### Correções aplicadas no `bot.py`

1. **`expand_url` reescrito** — tenta `GET` direto → `GET` via proxy → `HEAD`
   via proxy. Usa `curl_cffi` quando disponível, cache de 15 min (`URL_CACHE`)
   e detecção de bot-wall (`_is_bot_wall`).
2. **`strip_params(url, keys)`** — novo. Remove tags de quem já tinha
   compartilhado o link:
   - ML: `matt_word`, `matt_tool`, `matt`, `forceInApp`, `ref`
   - Shopee: `smtt`, `sp_atk`, `is_from_webapp`
   - Amazon: `tag`, `ascsubtag`, `th`, `psc`
3. **`is_store_link(url)`** — novo. Detecta `/social/`, `/loja/`, `/store/`,
   `linksbrazil`.
4. **`affiliate_link` agora devolve `(link, aviso)`** — quando o link é de
   loja, **não coloca a tag** (seria mentira) e devolve um aviso.
5. **`notify_admin()`** — nova (usa `ADMIN_CHAT_ID`). O espelho de canal
   agora **descarta** a oferta de loja e avisa o dono em vez de postar link
   quebrado.
6. Call sites atualizados: `publish`, `/buscar`, `/canal`, link solto e o
   handler do Telethon.

### Testado com os links reais da foto

| Caso | Antes | Depois |
|---|---|---|
| `meli.la/1w4qNk3` | `meli.la/1w4qNk3?matt_word=...` (não paga) | expandido → detectado como loja → **descartado com aviso** |
| `meli.la/2JGUTrm` | idem | idem |
| ML direto `/produto/MLB…` | ✅ | ✅ com tag |
| link com tag de outro afiliado | mantinha `matt_word=linksbr` | **tag removida** |

**Sintaxe validada** com `py_compile`.

### ⚠️ Impacto no comportamento — ATENÇÃO

Os canais monitorados são `@linksBrazil` e `@xetdaspromocoes`. Os links
`meli.la` deles apontam para a **loja** `/social/linksbrazil`. Com esta
correção o bot vai **parar de postar** essas ofertas (por enquanto), porque
não há como gerar comissão nelas.

**Falta a Fase 2:** reimplementar `resolve_store_link()` (da versão perdida)
— lê o catálogo da loja e acha o produto por **preço + similaridade de
título**, aí sim gerando o link de produto que paga. São ~120 linhas e a
spec está em `RECOVERY_bot_py.md`.

**Resultado:**
- ✅ Por que o link não era decifrado: identificado e corrigido
- ✅ Tag de outro afiliado removida
- ✅ O bot não posta mais link que não paga — avisa o dono
- ⏳ `resolve_store_link` (achar o produto dentro da loja) ainda falta

---

## [2026-10-14 14:50] — Sessão 9: 2ª foto do Termux — correção do proxy funcionou, 3 pendências

**Objetivo:** o usuário mandou nova foto (`E:\Pasta de erro\1.jpeg`, 14/10 14:35)
do Termux rodando o `bot.py` novo, já clonado do GitHub.

### Log transcrito

```
note: Total 18 (delta 0), reused 18 ... 254.46 KiB   ← clone do GitHub OK
(venv) ~/ML/bot-ML $ ls
LLM  'bot antigo.py'  bot.py  img  requirements.txt
(venv) ~/ML/bot-ML $ nano .env
(venv) ~/ML/bot-ML $ python bot.py
>>> BOT VAGANTE PROMOÇÕES <<<
✅ Telegram conectado como @vagantepromo_bot
✅ Canal de destino: Vagante Promoções
📡 Canais monitorados: @linksBrazil, @xetdaspromocoes
✅ Instagram conectado como @vagantepromo (id 281222276434048679)
⚠️ proxy indisponivel (ProxyError) — PROXY desligado. Seguindo com a conexão
   direta: Mercado Livre continua funcionando, Shopee pode bloquear.
🔍 Escutador do chat privado iniciado.
🤖 Ciclo do Telegram: planilha + raspagem
⚠️ Telethon: sessão expirada. Rode python bot.py --login novamente.
📊 Planilha: 0 produto(s) válido(s).
⊘ www.mercadolivre.com.br bloqueou o acesso (HTTP 200, pagina de verificacao).
⚠️ Mercado Livre: 0 produtos (provável bloqueio anti-bot).
⊘ shopee.com.br bloqueou o acesso (HTTP 403).
⚠️ Shopee bloqueada (HTTP 403).
📋 Nenhum produto novo na planilha.
✅ Ciclo concluído: 0 oferta(s) da raspagem publicada(s).
📸 Instagram: fila vazia.
```

### ✅ A correção da sessão 7 FUNCIONOU

- "**PROXY desligado. Seguindo com a conexão direta**" — o `PROXIES = None`
  entrou em vigor.
- **Toda a cascata de `ConnectionError` acabou.** Agora o bot recebe
  respostas HTTP de verdade (200 e 403) em vez de erro de socket.
- ✅ `curl_cffi` **está instalado** no celular (o aviso de L1514 não apareceu).
- ✅ `Pillow` funciona.
- ✅ O clone do GitHub funcionou (`LLM/` e `img/` estão no celular).

### 🔴 Pendência 1 — Telethon: sessão expirada

`⚠️ Telethon: sessão expirada. Rode python bot.py --login novamente.`

**Causa:** o arquivo `session_promos.session` **não veio no clone** — está no
`.gitignore`, corretamente. Além disso a sessão do PC não é transferível
para o Android.

**Solução:** rodar `python bot.py --login` no Termux e autenticar de novo.

### 🔴 Pendência 2 — a PLANILHA ESTÁ VAZIA (verificado)

Testei o CSV público daqui:

```
HTTP 200 | 22 bytes
CABECALHO: ['Link', 'Preço', 'Titulo', 'Foto']
LINHAS DE DADOS: 0        ← vazia
```

**Não é bug.** As colunas batem exatamente com o que `fetch_sheet_products`
procura (`link`, `preço`, `titulo`, `foto`) — o problema é que **não há
nenhum produto cadastrado**.

**Solução:** preencher a planilha. Ela é a fonte principal e a única que
nunca é bloqueada.

### 🔴 Pendência 3 — ML e Shopee bloqueiam o IP residencial

- ML: `HTTP 200, pagina de verificacao` — o bot-wall do ML, apesar do
  `impersonate="chrome131"` do curl_cffi.
- Shopee: `HTTP 403` — bloqueio agressivo conhecido.

Isso é o **NÍVEL 2** do `TERMUX.md`: precisa de navegador de verdade (CDP
no Termux) ou de um proxy residencial BR que funcione.

### 🟡 Achado extra — `SEARCH_TERMS` é carregado e NUNCA usado

```python
L85: SEARCH_TERMS = [t.strip() for t in env("SEARCH_TERMS").split(",") if t.strip()]
```

É a **única ocorrência** no arquivo. O ciclo automático só chama
`fetch_mercado_livre_products()` sem argumento, que vai sempre em
`/ofertas?page=N`. O modo `lista.mercadolivre.com.br/<termo>` só é
alcançado pelo comando `/buscar`.

→ **O `SEARCH_TERMS` do `.env` não faz nada.** É um buraco de
funcionalidade (o `.env.example` documenta como se funcionasse).

**Resultado:**
- ✅ Correção do proxy validada em campo
- ✅ 3 pendências isoladas e com causa identificada
- ⏳ Nenhuma alteração de código nesta sessão

**Próximos passos sugeridos:**
1. `python bot.py --login` no Termux (Telethon)
2. Preencher a Google Sheet (fonte confiável, destrava o bot)
3. Decidir a estratégia para ML/Shopee (proxy novo, ou CDP no Termux)

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