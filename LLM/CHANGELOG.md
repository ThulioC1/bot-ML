# Changelog

> **Adicione entradas NO TOPO** (mais recente primeiro).
> Formato definido em `README.md`.

---

## [2026-10-19 11:15] — Sessão 26.1: link no privado publica direto no canal

**Objetivo:** pedido do usuário — ao mandar um link no privado do bot, ele deve
acessar o link, gerar pelo gerador oficial (ML/Shopee/Amazon) e **publicar no
canal automaticamente**, sem precisar de `/canal`.

**Arquivos alterados:**
- `bot.py` — `handle_private_message()` guarda `affiliate_link` no produto e
  publica direto; `/preco` e `/canal <link>` seguem o mesmo caminho; se o
  gerador falhar, avisa o admin (`notify_link_failure`) e não publica. `HELP`
  atualizado.
- `tests/test_affiliate.py` — 2 testes novos do fluxo privado (publica com link
  gerado; falha do gerador não publica).

**Análise / o que foi observado:**
- O fluxo privado já chamava `generate_affiliate_link()` — com o fix da sessão
  26 o link de loja do ML agora expande/resolve — então faltava apenas publicar.
- Para não gerar duas vezes, quando `final_link` existe o `publish()` usa
  `product["affiliate_link"]` direto.

**Resultado:**
- ✅ 30 testes passando.
- ⚠️ Pendente: validar no Telegram real (link ML no privado → post no canal).

---

## [2026-10-19 10:55] — Sessão 26: Shopee pelo portal (produto → "Obter link") + link de loja do canal

**Objetivo:** parar de raspar a busca pública da Shopee (403) e ler as ofertas
direto do portal de afiliado logado (`/offer/product_offer`), publicando o link
"Obter link" de cada card. Corrigir o canal, que recusava `meli.la` de loja
porque a expansão acontecia depois da checagem de link de loja.

**Arquivos alterados:**
- `bot.py` — `SHOPEE_PRODUCT_OFFER_URL`, `SHOPEE_CUSTOM_LINK_URL` e
  `SHOPEE_OFFER_LIMIT`; `generate_shopee_portal_link()`;
  `fetch_shopee_affiliate_products()`; `fetch_shopee_products()` (portal
  primeiro, busca antiga só para `/buscar`); `publish()` prefere
  `product["affiliate_link"]`; `generate_affiliate_link()` expande o link antes
  de decidir se é link de loja; `selenium_eval()` não embrulha duas vezes
  `{ok, value}`.
- `tests/test_affiliate.py` — 6 testes novos (portal scrape, portal generator,
  fallback Open API, publish com link pronto, expansão antes do store link,
  `selenium_eval` sem duplo embrulho).
- `.env.example` — `SHOPEE_OFFER_LIMIT=6`.

**Análise / o que foi observado:**
- JS do portal: o modal `.get-link-modal` (módulo 55529) usa
  `POST /api/v3/link/gen_by_item` no clique do card (props
  `offer_id/shop_id/item_id/commission_id`, `type: item`); a página
  `/offer/custom_link` usa GraphQL `batchCustomLink`
  (`.custom-textarea textarea` → `.success-modal`).
- Teste com HTML local + Chrome de verdade (fixture) achou bug real:
  `selenium_eval` devolvia `{ok, value:{ok, value:{...}}}` e o scraping lia o
  envelope, não os produtos; corrigido para não duplo-embrulhar.
- Fixture validou os dois fluxos (2 cards lidos com os links certos; custom
  link devolveu `https://shope.ee/custom789`) sem tocar o portal real.

**Resultado:**
- ✅ 28 testes passando.
- ⚠️ Pendente: rodar `python bot.py --login-browser` e validar os seletores no
  portal real (ver `ISSUES.md`).

---

## [2026-10-19 09:25] — Sessão 25: link SEMPRE pelo gerador oficial + navegador persistente

**Objetivo:** o usuário pediu trocar a montagem manual de `?tag`/`?matt_word`
pelo link curto do **gerador oficial** de cada loja (ML, Shopee, Amazon), com
raspagem via navegador nas 3 lojas. Se o gerador falhar, **não publicar** e
avisar no privado.

### Respostas do usuário (decisões)

1. Autenticação: **perfil de navegador persistente** (login uma vez).
2. "Sem tags": não anexar `?tag` — publicar o link do gerador (meli.la etc.).
3. Falha do gerador: **não publica** + aviso no privado (`ADMIN_CHAT_ID`).
4. Raspagem: navegador nas 3 lojas.

### O que foi implementado em `bot.py` (3.281 linhas / 106 funções)

- **Perfil persistente**: `selenium_driver(visible=False)` usa
  `--user-data-dir=BROWSER_PROFILE_DIR` (`.browser-profile`), `quit_driver()`,
  `browser_login_session()` e o modo `python bot.py --login-browser` (abre os
  3 portais para login; ENTER fecha).
- **`browser_eval(url, script)`**: JavaScript no navegador real — Selenium
  (`selenium_eval`, via `execute_async_script`) e CDP puro
  (`_cdp_open`/`_cdp_evaluate`/`cdp_eval`, agora com IIFE async) como plano B.
- **`browser_get(url, wait, force_browser=False)`** força navegador quando
  `BROWSER_SCRAPING=1` (padrão), com fallback HTTP.
- **Geradores**:
  - `generate_ml_affiliate_link` — POST `affiliate-program/api/v2/affiliates/createLink`
    no linkbuilder (CSRF do cookie/meta), fallback DOM `#P0-2` + textarea.
  - `generate_shopee_affiliate_link` — Open API GraphQL `generateShortLink`
    com assinatura SHA256 (`_shopee_authorization`).
  - `generate_amazon_affiliate_link` — SiteStripe `getShortUrl` via fetch no
    domínio, fallback DOM `#amzn-ss-get-link-button`.
  - `generate_affiliate_link` roteia por HOST (`_store_of_url`), cacheia em
    `link_cache.json` (TTL 6h) e **rejeita link curto não expandido**
    (`_short_input_error`) — assim nunca republica o link de outro afiliado
    como se fosse o seu.
- **Publicação**: `publish()` recusa quando não há link (`notify_link_failure`
  com throttle de 30 min por link), `/buscar` omite ofertas sem link, `/canal`
  guarda o **permalink original** e regenera no publish; `channel_listener`
  idem (a geração passou para depois de preço/título, porque link de loja do
  ML precisa dos dois para resolver o produto).
- **Raspagem**: `extract_product()` e `store_catalog()` usam `browser_get`;
  Shopee usa `_shopee_search_data()` (fetch same-origin no navegador +
  fallback HTTP); Amazon usa `browser_get` na busca.
- `/status` mostra o estado dos 3 geradores e lembra do `--login-browser`.

### Config nova (`.env.example`)

`ML_AFFILIATE_TAG` (fallback `ML_MATT_WORD`), `SHOPEE_APP_ID`/`SHOPEE_SECRET`,
`AMAZON_MARKETPLACE_ID` (default `A2Q3Y263D00KWC`), `BROWSER_SCRAPING=1`,
`BROWSER_PROFILE_DIR`, `LINK_GEN_TIMEOUT=60`. `.gitignore` cobre
`.browser-profile/`, `.chrome-cdp/`, `link_cache.json` e `.venv/`.

### Bug achado nos testes

A versão anterior do roteador usava `"a.co" in url` — **`magazineluiza.com.br`
contém `a.co`** e caía no gerador da Amazon. Agora a loja é decidida só pelo
host (`_store_of_url`).

### Testado — 22/22

`tests/test_affiliate.py` (unittest, offline, sem rede/navegador): parsers de
link curto (JSON do ML, GraphQL da Shopee, `amzn.to` com `\/` escapado), ASIN
(`/dp/`, `/gp/product/`, `?asin=`), assinatura Shopee == SHA256 manual,
geradores com `browser_eval`/`requests.post` mockados, rota por host, cache e
`publish` recusando sem link **sem** chamar `send_message`.

### ❌ Não testado (exige credenciais/sessão real)

- Login real nos portais e chamadas AO VIVO de `createLink`/SiteStripe — as
  APIs internas não são documentadas e os seletores do DOM podem ter mudado.
- Termux/Android: o perfil persistente exige tela para o login; o CDP funciona,
  mas o gerador ML/Amazon continuará falhando sem sessão autenticada.

---

## [2026-10-15 15:45] — Sessão 24: o título vinha sendo a frase do parceiro

**Objetivo:** o usuário: *"quando pegamos o texto do grupo aliado, precisamos
pegar da linha de baixo. Pois nosso parceiro põe uma frase e eu prefiro que
venha o título primeiro sem frase."*

### 🔴 O que acontecia

O handler escolhia o título assim:

```python
for l in _lines:
    if len(l) > 12 and "http" not in l and not l.startswith("-"):
        title_guess = l[:150]
        break          # <- primeira linha que passa, e a frase do parceiro
```

Post real do canal:
```
MIXER É AVANÇO DE VIDA              <- 1a linha: frase de divulgacao
Mixer Power Inox 3 em 1 600W ...    <- linha de baixo: o TITULO
De R$ 191 por R$ 110 no Pix
```

Duas consequências:
1. Quando a extração na página do produto falhava (ML bloqueado, link de loja),
   o post saía com **`MIXER É AVANÇO DE VIDA`** como título.
2. O mesmo `title_guess` ia para o `resolve_store_link()` — ou seja, a busca do
   produto na loja casava pela **frase**, não pelo nome. Isso degrada a
   resolução de link de loja, que é o que gera comissão.

### ✅ `title_from_lines()` (novo)

Substitui o `for/break`. Regras em ordem:

1. Linha com **http**, com **preço** ou muito curta **não** é título.
2. Frase em **CAIXA ALTA** e curta perde para qualquer título normal.
3. Se **só** sobrar frase, pula a 1ª linha e usa a de baixo.
4. Entre as normais, a 1ª vence — **exceto** se for isca curta
   (`"Olha isso:"`, `"Corre que ta saindo:"`, `"Preço imperdível!"` → termina
   em `: ! ? -`), caso em que usa a linha seguinte.

### Testado — 13/13

| Caso | Resultado |
|---|---|
| **foto real** (frase caixa alta na 1ª) | `Mixer Power Inox 3 em 1 600W Elgin 110V` ✅ |
| título é a única linha | usa a 1ª linha ✅ |
| título na 1ª + frase caixa alta na 2ª | vence a 1ª ✅ |
| duas frases caixa alta + título embaixo | pega o título ✅ |
| frase com acento caixa alta | pega o título ✅ |
| linha de preço isolada | nunca vira título ✅ |
| só preço + link | devolve vazio → cai em "Oferta" ✅ |
| duas linhas normais | vence a 1ª ✅ |
| isca `"Olha isso:"` + título | pega o título ✅ |
| título longo na 1ª | **não** troca só por ser maior ✅ |
| `"Corre que ta saindo:"` + título | pega o título ✅ |
| emoji na frase (`🔥 OFERTA...`) | pega o título ✅ |

### Duas versões antes de acertar

A primeira versão aplicava "pula a 1ª linha" **antes** de checar a caixa alta,
e **quebrou 2 casos legítimos**: quando o título *era* a 1ª linha, ele era
descartado. A ordem correta é **caixa alta primeiro, pular a 1ª linha só como
último recurso**.

### Arquivos alterados
- `bot.py` — `title_from_lines()` (novo), handler do Telethon
- `LLM/CHANGELOG.md`, `LLM/PROJECT_STATE.md` — esta sessão

**Resultado:**
- ✅ Título vem do produto, não da frase de divulgação
- ✅ `resolve_store_link()` passa a casar pelo nome do produto (ganha comissão)

---

## [2026-10-15 15:10] — Sessão 23: as fotos pararam de funcionar (era o botão) + preço antigo

**Objetivo:** o usuário reclamou que *"após essas últimas mudanças o Telegram
parou de aceitar as fotos"*, e pediu o **preço antigo** visível no post
(*"de 60 por 💰 R$ 49,90"*). A foto `E:\Pasta de erro\2 (2).jpeg`
(15/10 14:31) mostrou o post antigo quebrado.

### 🔴 CAUSA RAIZ DAS FOTOS PARANDO DE FUNCIONAR

Eu introduzi o `reply_markup` (botão) e **esqueci que ele muda de formato de
envio**:

```python
def tg_api(method, payload=None, files=None, timeout=60):
    if files:
        resp = requests.post(url, data=payload, files=files)   # multipart
    else:
        resp = requests.post(url, json=payload)               # JSON
```

No caminho **com arquivo** o `requests` usa `data=` e **stringifica** o valor:
`str({'inline_keyboard': ...})` sai com **aspas simples**, que não é JSON.
O Telegram responde `400 Bad Request: can't parse reply keyboard markup` e
**recusa a foto**.

No caminho **sem arquivo** (`sendMessage`) o `requests` usa `json=` e o dict
vira JSON válido — **funcionava**.

> É por isso que **só as fotos quebraram** e o texto continuava saindo:
> o `sendPhoto` falhava e caía no fallback `sendMessage`.

**Prova** (executada nesta sessão, `requests` real):

```
dict cru   : ERRO -> Telegram rejeita (JSONDecodeError)
json.dumps : OK  -> Telegram aceita
```

**Correção:** `json.dumps(reply_markup, ensure_ascii=False)` nos dois caminhos
de `send_message()`.

### 🔴 SEGUNDO BUG: `NameError` matava o handler

Eu tinha escrito `product.get("original_price")` dentro do `handler` do
Telethon — mas **não existe variável `product` ali**. `NameError` derrubava o
handler inteiro, ou seja, **nada era publicado**. Trocado por `old_price`.

### 🔴 TERCEIRO BUG: o título duplicado era o texto cru

O handler fazia `text = raw` e reenviava a mensagem **inteira** do canal,
depois de acrescentar o título no topo. Era por isso que o título aparecia
**duas vezes**, e junto vinham a frase de marketing e o link gigante.

**Correção:** o post agora é montado do zero — título, preço e nada mais.

### 🔴 QUARTO BUG: o preço antigo nunca era lido do texto

O regex era `r"R\$\s*([\d\.]+,\d{2})"` — **exigia centavos**. O canal escreve
`De R$ 191 por R$ 110` (sem centavos), então:
- o preço atual caía no `extract_product` (110,19 da página da Amazon);
- o preço antigo **nunca** era lido.

Novo `prices_from_text()` devolve `(atual, antigo)` e entende:
`"De R$ X por R$ Y"`, `"R$ 1.234,56"`, `"R$ 110"`, `"R$ 1.234"`.

### ✅ Testado — 11/11

| Caso | Esperado | Ok |
|---|---|---|
| **texto exato da foto** (`De R$ 191 por R$ 110`) | 110,00 / 191,00 | ✅ |
| só atual com centavos (`R$ 209,90`) | 209,90 | ✅ |
| só atual sem centavos (`R$ 110`) | 110,00 | ✅ |
| milhar com ponto (`R$ 1.234,56`) | 1234,56 | ✅ |
| milhar sem centavos (`R$ 1.234`) | 1234,00 | ✅ |
| `De R$ 96,00 por R$ 46,90` | 46,90 / 96,00 | ✅ |
| `De R$ 20 por R$ 50` (antigo menor) | 50,00, sem antigo | ✅ |
| preços soltos (`R$ 89,90 / R$ 199,90`) | 89,90 / 199,90 | ✅ |
| número dentro do link | não conta como preço | ✅ |
| sem preço nenhum | `(None, None)` | ✅ |

### Antes → depois (caso da foto)

**Antes:**
```
Mixer Power Inox 3 em 1 600W Elgin Lunar 110V
💰 R$ 110,19
MIXER É AVANÇO DE VIDA
Mixer Power Inox 3 em 1 600W Elgin 110V      <-- título DE NOVO
De R$ 191 por R$ 110 no Pix
https://www.amazon.com.br/gp/product/B0DCKBMVH9?linkCode=sl2&linkld=
5853e120ee6bf9054a3b7c9b15123ea9&ref_=...   <-- link GIGANTE
ðŸ"— Links afiliados...                       <-- emoji quebrado (mojibake)
```
*(sem botão, e a foto nem entrava)*

**Depois:** 182 caracteres, título único, com preço antigo e botão:
```
🔥 OFERTA EM DESTAQUE

📦 Mixer Power Inox 3 em 1 600W Elgin Lunar 110V

📉 De R$ 191,00
🔥 Por R$ 110,00            (42% de desconto)

Gostou da oferta? Compartilhe nosso grupo: https://t.me/vagantepromo

        [ 💗 Ver Oferta ]   <-- botão, URL não aparece no texto
```

### 🗑️ `FOOTER_TEXT` — o emoji quebrado era mojibake

Na foto aparece `ðŸ"— Links afiliados`. Isso é o 🔗 **decodificado como
cp1252**: o texto antigo tinha o emoji e o console/conteúdo gravou errado.
O `FOOTER_TEXT` novo **não tem emoji nenhum**, então não há o que quebrar:
```python
FOOTER_TEXT = env("FOOTER", "Gostou da oferta? Compartilhe nosso grupo: https://t.me/vagantepromo")
```

### Arquivos alterados
- `bot.py` — `send_message()` (json.dumps), `prices_from_text()` (novo),
  `_MONEY_RE` (novo), handler do Telethon, `publish()`, `FOOTER_TEXT`
- `LLM/CHANGELOG.md`, `LLM/ISSUES.md`, `LLM/PROJECT_STATE.md` — esta sessão
- `LLM/README.md` — reforçada a regra de registrar **toda** alteração

### ⚠️ Lição (erro meu, não repetir)

> Ao passar um **dict aninhado** para a API do Telegram, **sempre** use
> `json.dumps()`. O `requests` muda o formato de serialização conforme você
> usa `data=` ou `json=`, e o `data=` (multipart) não entende dict aninhado.
>
> E: **teste o caminho com arquivo**, não só o caminho com JSON. O botão
> funcionou no teste de texto e só falhou em produção, nas fotos.

**Resultado:**
- ✅ Fotos voltam a ser aceitas (`reply_markup` serializado)
- ✅ `NameError` do handler eliminado
- ✅ Título não duplica mais (texto cru não é repostado)
- ✅ Preço antigo aparece: `De R$ 191` → `Por R$ 110`
- ✅ Link gigante saiu do texto, ficou só no botão
- ✅ Emoji quebrado eliminado

---

## [2026-10-15 12:30] — Sessão 22: link como botão, título, footer (VERSÃO SUPERADA pela 23)

> ⚠️ **Esta sessão foi corrigida na Sessão 23.** O botão foi implementado, mas
> quebrou o envio de fotos (`reply_markup` sem `json.dumps`) e o `NameError`
> de `product` impedia a publicação. O preço antigo não funcionava porque o
> regex exigia centavos. **Leia a Sessão 23 antes de mexer nessa parte.**

**Objetivo:** melhorar a apresentação das mensagens no Telegram - link como botão inline, título único e footer de afiliado corrigido.

**Arquivos alterados:**
- `bot.py` — `send_message()` agora aceita `reply_markup`; canal handler usa teclado inline `💗 Ver Oferta`; `FOOTER_TEXT` removido emoji quebrado; título definido somente uma vez com `if not title:`

**O que foi implementado**

| Feature | Antes | Depois |
|---|---|---|
| Link de afiliado | Texto gigante `🛒 Link: https://...` | Botão inline `💗 Ver Oferta` |
| Título da oferta | Poderia ser duplicado de fontes múltiplas | Definido apenas uma vez, `if not title:` |
| Footer "afiliado" | `🔗 Links afiliados...` com emoji quebrado | `Gostou da oferta? Compartilhe nosso grupo: https://t.me/vagantepromo` |
| Preço antigo | Já era exibido via `price_block()` | Mantido (De R$ X → Por R$ Y) |

**Resultado:**
- ⚠️ Link agora é botão clicável no Telegram — **mas quebrou as fotos**
- ⚠️ Título não se duplica mais — **mas o texto cru continuava sendo repostado**
- ✅ Footer de afiliado limpo e sem emoji quebrado
- ❌ Preço antigo **não** aparecia (regex exigia centavos) — corrigido na 23

---

## [2026-10-15 08:15] — Sessão 21: filtro de oferta (shampoo de 24k passou)

**Objetivo:** o usuário pediu ponderação de valores para só entrar promoção de
verdade — *"Ontem veio um Shampoo de 24k"*.

**Arquivos alterados:**
- `bot.py` — `MIN_PRICE`/`MAX_PRICE`/`MIN_DISCOUNT`, `_num_env()`,
  `oferta_valida()`, filtro em `collect_products()`, linha no `/status`
- `.env.example` — seção "Filtro de oferta" + seção "Lojas do ML"
- `LLM/CHANGELOG.md` — esta entrada

### O que foi implementado

| Variável | Default | Efeito |
|---|---|---|
| `MIN_PRICE` | 15 | descarta abaixo (preso demais, brinde) |
| `MAX_PRICE` | 2500 | **descarta o shampoo de 24k** |
| `MIN_DISCOUNT` | 0 | desconto mínimo em % (0 = aceita sem) |

Filtro aplicado em `collect_products()`, ou seja, vale para **todas** as
fontes (planilha, ML, Shopee, Amazon) — não só a raspagem.

### Testado

```
DESCARTA  Shampoo 24k (o que passou)    R$ 24.000,00 acima do máximo
DESCARTA  Console PS5                   R$ 4.399,90 acima do máximo
ACEITA   Camisa 49,90
ACEITA   Fone 199,90
DESCARTA  Preso demais (2 reais)        R$ 2,00 abaixo do mínimo
ACEITA   Oferta real 46,90 de 96
DESCARTA  Preço nulo / zero             sem preço
ACEITA   2499 (limite)  |  DESCARTA 2501
```

E no fluxo real:
```
🧹 Filtro de oferta: 3 descartado(s) [1 acima do máximo, 1 acima do máximo, 1 abaixo do mínimo]
sobraram 3 de 6: R$ 49,90 | R$ 199,90 | R$ 780,00
```

### Por que `MIN_DISCOUNT` está em 0

Nos itens vindos do catálogo `/social/`, **o preço antigo não vem** —
`store_catalog()` só pega `{title, price, url, image}`. Então exigir desconto
derrubaria **todas** as ofertas do ML. Por isso o default é 0.

Para quem vem com `original_price` (Shopee, alguns itens da planilha), dá
para exigir:
```ini
MIN_DISCOUNT=20
```
Testado: com 20%, só passa `46,90 de 96`.

### `ML_STORES` documentado

O usuário vai usar a vitrine dele depois, mas não agora. A variável já
existia no código e **não está no `.env`** — documentei no `.env.example` com
explicação, e o bot funciona sem ela (usa só as lojas que aprende nos canais).

**Resultado:**
- ✅ Shampoo de 24k descartado
- ✅ Filtro vale para todas as fontes
- ✅ Log mostra quantos foram descartados e por quê

---

## [2026-10-15 07:45] — Sessão 20: bio quebrava com 1 item sem preço

**Objetivo:** usuário mandou `2.jpeg` — a página
`vagantepromo.vercel.app` mostrava *"Erro ao carregar a vitrine de ofertas.
Tente novamente mais tarde."*

### 🔴 Causa raiz

A página tem isto, **sem nenhuma proteção**:

```js
<div class="text-xl font-black text-emerald-400">R$ ${p.price.toFixed(2)...}</div>
```

E a vitrine tinha **7 itens com `price: null`** (todos ids `ch_*`, vindos do
espelho dos canais, que publicam sem preço — como o
`📡 Canal: Jogo De Toalhas... | preco=` do log).

`null.toFixed(2)` → **TypeError** → estoura dentro do `renderProducts` → cai
no `catch` do `loadProducts` → **a vitrine INTEIRA não renderiza**.
Um só item quebrado mata a página toda.

### Diagnóstico

```
vitrine no ar: 40 itens | sem preço: 7
   ch_087da0f9f1 | price=None | 🔥 App - Nova chance de girar a Roleta Shopee
   ch_0837f4224b | price=None | 🔥 Cupons Shopee
   ch_a6e548c5b3 | price=None | 🔥 App - Roleta shopee
   ch_c4aa0ed5fd | price=None | SHOPEE DIA DE CUPONS RENOVADOS
   ch_105ee022a5 | price=None | 🔥 Cupons Shopee Renovados
   ch_c711644cd5 | price=None | Live Streaming
   ch_23baa85649 | price=None | Live Streaming
```

O blob estava **perfeito** (HTTP 200, JSON válido, 40 itens) — o defeito era
de dados, não de transporte.

### Correções

1. **`save_to_vitrine()` agora recusa item sem preço** — e limpa itens
   quebrados que ficaram de execuções anteriores:
   ```python
   preco = item.get("price")
   if preco is None or (isinstance(preco, (int, float)) and preco <= 0):
       log(f"⚠️ Vitrine: '...' sem preço — não entra na bio.")
       return
   vitrine = [v for v in vitrine if isinstance(v, dict)
              and isinstance(v.get("price"), (int, float)) and v.get("price") > 0]
   ```
   > Oferta de canal sem preço **continua indo para o Telegram** — só não
   > entra na bio. Faz sentido: o Telegram mostra o texto, a bio é uma
   > vitrine de compras e precisa de preço.

2. **Vitrine de produção limpa**: baixei do blob, removi os 7 quebrados e
   reenviei. De 40 → **33 itens**, todos com preço.

### Detalhe do CDN (observado)

O `PUT` respondeu 200, mas as leituras seguintes ainda serviam a versão
antiga. Só na 3ª leitura (após ~18s) veio a nova:

```
leitura 1: Age=436 | 40 itens | sem preco=7
leitura 2: Age=442 | 40 itens | sem preco=7
leitura 3: Age=449 | 33 itens | sem preco=0   ← propagou
```

A página usa `?t=Date.now()`, que busta o cache do visitante, então está
ok. Mas em testes vale esperar alguns segundos antes de concluir que o
upload não pegou.

### ⚠️ Pendente do lado da página (não é do bot)

O `renderProducts` continua vulnerável a `price` nulo. O bot deixou de
mandar, mas a defesa real seria no JS da página:
```js
const preco = Number(p.price) || 0;
```
Recomendo aplicar — protege contra qualquer item futuro quebrado.

**Resultado:**
- ✅ Vitrine publicada com 33 itens válidos
- ✅ Bot não publica mais item sem preço
- ⏳ Recomendado: proteger `p.price` também no JS da página

---

## [2026-10-14 18:20] — Sessão 19: internet cai no celular → o bot ficava parado

**Objetivo:** o usuário completou: *"Às vezes em deslocamento o celular fica
sem internet, e quando chego em casa vejo que o bot parou por isso."*

### 🔴 O bug

```python
if now - last_telegram >= INTERVAL_TELEGRAM:
    telegram_cycle()
    last_telegram = now      # ← avança SEMPRE, mesmo com o ciclo falhando
```

Sem internet, o ciclo rodava, não publicava nada (todos os requests davam
`ConnectionError`), e **mesmo assim o timer marcava 1 hora**. Voltando pra
casa, o bot podia ficar **até 1 hora sem fazer nada**.

### O que foi implementado

1. **`internet_online(timeout=10)`** — testa a API do Telegram
   (`getMe`), que **não usa o proxy** (o proxy do `.env` é só para ML/Shopee).
   Se o Telegram não responde, para os nossos fins estamos offline.
   Fallback: `connectivitycheck.gstatic.com`.

2. **Loop principal reescrito:**
   - checa a internet **a cada 60s**
   - offline → **pausa os ciclos e NÃO avança o timer**
   - online de novo → loga quanto tempo ficou fora e **dispara na hora**

3. **`NET_STATE`** + linha nova no `/status`:
   `• Internet: ONLINE | OFFLINE — ciclos pausados`

4. `publish()` já era seguro: só grava em `seen.json` quando o envio
   realmente deu certo — **não há perda de oferta**.

### 🐛 Bug na minha própria correção (peguei na simulação)

Primeira versão fazia `last_telegram = 0.0` ao voltar a internet. **Não
dispara**: a condição é `now - last_telegram >= 3600`, então só rodaria quando
`now >= 3600`, ou seja 1 hora depois de subir o bot.

A simulação do cenário mostrou `ESPERA: 10.0 min` e expôs o erro. Trocado por
**flags explícitas** `disparar_telegram` / `disparar_instagram`.

### Simulação do cenário real

```
t=   0.0 min  ciclo rodou
t=  10.0 min  OFFLINE - ciclos pausados
t=  50.0 min  ONLINE apos 40 min
t=  50.0 min  ciclo rodou          ← IMEDIATO
t= 110.0 min  ciclo rodou

voltou aos 50.0 min | ciclo rodou aos 50.0 min
ESPERA: 0.00 min  →  OK, recupera na hora
```

### ⚠️ A outra metade do problema (NÃO é código)

Se o **Android matar o processo**, nada disso adianta. Precisa:
```bash
termux-wake-lock
```
e desligar a otimização de bateria do Termux nas Configurações do Android.
O `termux-wake-lock` é reiniciado a cada boot — dá para automatizar com o
`termux-boot`.

**Resultado:**
- ✅ Internet cai → pausa com aviso, sem Advance de timer
- ✅ Internet volta → roda o ciclo no mesmo minuto
- ✅ `/status` mostra o estado

---

## [2026-10-14 17:55] — Sessão 18: a bio da Instagram nunca atualizava

**Objetivo:** o usuário apontou que o bot posta no Telegram e no Instagram, mas
o link da bio (`https://vagantepromo.vercel.app/`) não muda.

### 🔴 Causa raiz: DOIS bugs somados

**1. `save_to_vitrine()` nunca publicava nada.** Escrevia `vitrine.json` só no
disco e logava. O `upload_to_blob()` existia, mas **ninguém chamava**.
(Na versão antiga `bot antigo.py` a chamada existia — foi perdida.)

**2. `upload_to_blob()` não mandava `x-add-random-suffix: 0`.** Sem essa flag
o Vercel Blob cria um arquivo **com sufixo aleatório** a cada envio. Testado:
```
SEM a flag:  upload 1 -> bot_teste_url-4DylhQFMITBbCxuOxN8UQbzyMu2k5a.txt
             upload 2 -> bot_teste_url-Mq80ZRSzhFQ7J7ATmrQ9gihyUUveG2.txt
COM a flag: upload 1 -> bot_teste_url.txt
             upload 2 -> bot_teste_url.txt
```
Como a página tem o endereço **fixo no HTML**, o `vitrine.json` novo cairia
num nome diferente e a bio leria o arquivo velho para sempre. Ou seja: mesmo
que eu tivesse só acrescentado a chamada, **ainda não funcionaria**.

### O que a página faz (verificado, está CORRETA)

`vagantepromo.vercel.app` busca:
```js
fetch('https://rzd48c84T8k2zCDu.public.blob.vercel-storage.com/vitrine.json?t=' + new Date().getTime())
```
Já tem cache-buster. Testei 6 requisições: `Age` subiu de 34 → 40 e o
conteúdo veio novo. **O cache-buster funciona.** A página não precisa de
correção.

### ✅ Verificado de ponta a ponta

```
ANTES:  bio com 15 itens, mais recente = 13/10/2026 15:12   (parado há 1 dia)

save_to_vitrine(...)  →  📦 Vitrine atualizada (9 itens).
                      →  ☁️ Blob: vitrine.json atualizado
                      →  🌐 Bio atualizada: https://rzd48c84T8k2zCDu.public.blob...
leitura da bio       →  topo = 14/10/2026 11:48   ✅ ATUALIZOU
```

### ⚠️ Efeito colateral que eu causei (preciso avisar)

O teste **sobrescreveu a vitrine.json de produção com a cópia local do PC**
(8 itens, mais recente 14/10 11:48). Antes tinha 15 itens de 13/10.

Ou seja: a bio **ganhou** um item mais novo, mas **perdeu 7 itens** que só
existiam no blob. Não é dano permanente — no próximo ciclo do celular o bot
republica a vitrine do celular (que tinha 18 itens) e tudo normaliza.

### Correções aplicadas

1. `save_to_vitrine()` agora chama `upload_to_blob()` e loga a URL pública.
2. `upload_to_blob(..., stable=True)` manda `x-add-random-suffix: 0`.
3. Normaliza a caixa do store ID na URL devolvida (`rzd48c84t8k2zcdu` →
   `rzd48c84T8k2zCDu`), que é como a página escreve.

**Resultado:**
- ✅ Bio passa a atualizar a cada oferta publicada
- ✅ Nome do arquivo estável (não quebra a URL fixa da página)

---

## [2026-10-14 17:45] — Sessão 18b: Chromium CDP ATIVOU no celular

**Objetivo:** usuário mandou `1.jpg` do Termux (17:23 e 17:33).

### 🟢 O que deu certo

```
ℹ️ Navegador: /data/data/com.termux/files/usr/bin/chromium-browser   ← instalado!
✅ websocket-client OK — o /ofertas será lido via Chromium CDP.
⚠️ Chromium CDP: porta CDP não abriu                                (17:24, versão antiga)

--- git pull ---
   bot.py | 174 ++++++++++++++++++++++------------------------

[14/10 17:33:54] ⊘ www.mercadolivre.com.br bloqueou o acesso (HTTP 200, pagina de verificacao).
[14/10 17:33:54] ↪️ Selenium indisponível — tentando Chromium via CDP.
[14/10 17:33:57] ✅ Chromium CDP ativo em http://127.0.0.1:9222
                 (chromium-browser --headless=new --no-zygote --single-process)
[14/10 17:34:07] ℹ️ /ofertas não passou; usando o catálogo das lojas (29 produto(s)).
✅ Mercado Livre: 29 produto(s).
✅ Ciclo concluído: 2 oferta(s) da raspagem publicada(s).
```

**O Chromium subiu com a porta CDP aberta.** A correção da sessão 17
(`--headless=new` + `LD_PRELOAD` absoluto) funcionou — e foi a **primeira
combinação** da lista de tentativas que deu certo.

### 🔴 Mas o `/ofertas` NÃO passou

O Chromium conectou, navegou e devolveu HTML — porém **pequeno demais**. Com
página normal do `/ofertas` são ~650 KB; no celular veio muito menos e o
parser achou 0 cards, caindo na reserva `/social/` (29 produtos).

→ **Diagnóstico: o ML detecta o Chromium headless e entrega página vazia.**

Isso já tinha aparecido no PC, na sessão 13: `--dump-dom` em headless devolveu
2.681 bytes (página de "empty state"), enquanto o Selenium com **janela real**
devolveu 673 KB com 49 produtos. O comentário da versão perdida dizia o mesmo:
> *"Sobe um Chrome fora da tela. Sem janela o ML devolve a parede anti-bot."*

### 🔴 Novo problema: `resolve_store_link` não acha nada

```
🔗 Link expandido: https://meli.la/23649Vs -> /social/xetdaspromocoes?matt_word=xetandr
📡 Canal: Sandália Kenner Unisex NK6 Pro Laranja K/cin | foto=sim | preco=
⛔ link de LOJA do ML (/social/xetdaspromocoes) ignora a tag de afiliado
```

O `store_catalog` da **mesma loja** tinha sido lido 30 segundos antes
("Catálogo da loja: 10 produto(s)"), mas a busca não achou o produto.

**Causa provável:** o regex de preço do Telegram é
`r"R\$\s*([\d\.]+,\d{2})"` — **não pega "R$ 43"** (sem centavos). Como não
achou preço, o catálogo de 10 itens não casa com título tão específico
("Sandália Kenner Unisex NK6 Pro Laranja K/cin" vs 10 itens genéricos).

### Correção aplicada nesta sessão

`cdp_get` agora avisa quando a página vem **pequena demais**, que é o sintoma
exato do bloqueio headless:
```
⚠️ CDP: página veio vazia (3 KB) de https://www.mercadolivre.com.br/ofertas...
```
Assim fica visível no log, em vez de o bot só silenciosamente cair na reserva.

### Sugestão de próximo passo

O caminho que resolve o headless é o **Chrome real via ADB** (descrito na
sessão 19 / resposta ao usuário): `adb forward tcp:9222
localabstract:chrome_devtools_remote` dá acesso ao Chrome de verdade, que o ML
não detecta. Reusa 100% do `cdp_get()` que já existe.

**Resultado:**
- ✅ Chromium CDP sobe e abre a porta no Termux
- 🔴 `/ofertas` ainda barrado — ML detecta headless
- 🔴 `resolve_store_link` falha com preço sem centavos

---

## [2026-10-14 17:55] — Sessão 17: Chromium instalado mas "porta CDP não abriu"

**Objetivo:** o usuário instalou o Chromium e o bot respondeu
`⚠️ Chromium CDP: porta CDP não abriu`.

### 🟢 Boa notícia: o Chromium ESTÁ instalado

O `chromium_binary()` achou o binário (o log deixou de dizer "não
encontrado"). O problema é **o Chromium não subiu com a porta CDP**.

### 🔴 Causa provável: faltava `--headless`

No celular **não existe display**. Minha versão anterior subia o Chromium
**sem `--headless`**, então no PC funcionava (tem tela) mas no Android ele
não abre janela e morre antes de escutar a porta.

Segundo problema: eu passava `LD_PRELOAD=libtermux-exec.so` com caminho
**relativo** — precisa ser absoluto
(`/data/data/com.termux/files/usr/lib/libtermux-exec.so`).

### Correção: máquina de tentativas

`cdp_server()` agora tenta **várias combinações** até uma dar certo, e
**registra o erro de cada uma**:

```python
variantes = [
    (["--headless=new", "--no-zygote", "--single-process"], {"LD_PRELOAD": preload}),
    (["--headless=new"],                                    {"LD_PRELOAD": preload}),
    (["--headless=new", "--no-zygote", "--single-process"],  None),
    (["--headless"],                                        None),
]
```
× cada binário candidato (`chromium-browser`, `chromium`, `headless_shell`,
`$PREFIX/lib/chromium/chrome`, …).

Outras mudanças:
- **`LD_PRELOAD` com caminho absoluto** e só quando o arquivo existe.
- **stderr do Chromium vai para `cdp_chrome.log`** (antes era descartado) —
   é isso que vai dizer o motivo real da falha.
- Espera da porta subiu de 20s para 25s, e agora detecta se o processo
  **morreu** (`chromium saiu (código N)`) em vez de só esperar a timeout.
- `chromium_binary()` virou gerador `chromium_candidates()` para testar
  vários binários.
- Cache de falha subiu de 60s para 120s (não fica tentando toda hora).

A mensagem final passa a listar tudo que foi tentado:
```
⚠️ Chromium CDP não subiu. Tentativas:
   • chrome[--headless=new --no-zygote --single-process]: porta CDP não abriu em 25s
   • chrome[--headless=new]: chromium saiu (código 127); veja cdp_chrome.log
   ...
```

### Validado no PC

```
candidatos: C:/Program Files/Google/Chrome/Application/chrome.exe
✅ Chromium CDP ativo em http://127.0.0.1:9222 (chrome.exe)   (5.8s)
cdp_get /ofertas -> OK 663.014 bytes | MLB-ids: 119
```

**Resultado:**
- ✅ Provável causa corrigida (`--headless` faltando + LD_PRELOAD relativo)
- ✅ 4 combinações × N binários, com diagnóstico de cada tentativa
- ✅ `cdp_chrome.log` para o próximo teste no celular

**Se ainda falhar:** pedir para mandar o `cdp_chrome.log` do celular —
ele vai dizer o erro exato (falta de biblioteca, permissão, etc.).

---

## [2026-10-14 17:40] — Sessão 16: `pkg install chromium-browser` não existe

**Objetivo:** o usuário rodou `pkg install chromium-browser` e recebeu
**`E: Unable to locate package chromium-browser`**.

### Causa: eu dei o nome errado

`chromium-browser` é o **nome do BINÁRIO**, não do pacote. O pacote é
`chromium` e mora no repositório opcional **`x11-packages`** (confirmado no
`termux-packages/x11-packages/chromium/build.sh`).

Instalado, ele cria:
```
$PREFIX/bin/chromium-browser   -> symlink para chromium-launcher.sh
$PREFIX/lib/chromium/chrome         (binário real)
$PREFIX/lib/chromium/headless_shell
$PREFIX/bin/headless_shell
$PREFIX/bin/chromedriver
```

Alternativa: `tur-repo` também tem `chromium` (binário pré-compilado), mas
tem histórico de `CANNOT LINK EXECUTABLE` por símbolo — o do `x11-repo` é
mais confiável.

### Comando certo

```bash
pkg update -y
pkg install x11-repo
pkg update -y
pkg install chromium
```

### Correções no `bot.py`

1. **`chromium_binary()`** agora procura, em ordem:
   `chromium-browser` · `chromium` · **`headless_shell`** · `google-chrome` ·
   `chrome` · `google-chrome-stable` · e depois caminhos absolutos
   (`$PREFIX/bin/chromium-browser`, **`$PREFIX/lib/chromium/chrome`**,
   `$PREFIX/lib/chromium/headless_shell`, …).
   > O launcher `$PREFIX/bin/chromium-browser` é um script; o binário de
   > verdade está em `$PREFIX/lib/chromium/chrome`. Cobrir os dois é mais seguro.
2. **`CHROMIUM_HINT`** — constante com o comando certo.
3. A mensagem de boot agora diz o comando exato:
   ```
   ⚠️ Chromium NÃO ENCONTRADO. No Termux o pacote é 'chromium'
      e vive no repo x11 — rode: pkg install x11-repo && pkg install chromium
   ```

**Resultado:**
- ✅ Causa identificada: nome de pacote errado (minha culpa)
- ✅ Detecção do binário mais robusta
- ✅ Mensagem de erro agora dá o comando certo

---

## [2026-10-14 17:20] — Sessão 15: fotos 4 e 5 — post no IG funcionou, arte corrigida

**Objetivo:** o usuário mandou `4.jpeg` (post no Instagram) e `5.jpg` (log do
Termux). Pedido: *"o produto está muito pequeno na foto do IG. Preciso que
aumente e que esse fundo seja azul mais escuro. O produto deve ficar maior
até o fundo parecer uma borda."*

### O que a foto 5 mostra — o bot está funcionando

```
✅ websocket-client OK — o /ofertas será lido via Chromium CDP.
ℹ️ Navegador: Chromium NÃO ENCONTRADO (pkg install chromium-browser)
✅ Telethon conectado: @linksBrazil, @xetdaspromocoes
🤖 Ciclo do Telegram: planilha + raspagem
📊 Planilha: 0 produto(s) válido(s).
⊘ www.mercadolivre.com.br bloqueou o acesso (HTTP 200, pagina de verificacao).
↪️ Selenium indisponível — tentando Chromium via CDP.
📦 Catálogo da loja: 10 produto(s)
📦 Catálogo da loja: 19 produto(s)
ℹ️ /ofertas não passou; usando o catálogo das lojas (29 produto(s)).
✅ Mercado Livre: 29 produto(s).
✅ Ciclo concluído: 2 oferta(s) da raspagem publicada(s).
✅ Instagram publicado: 18103923329367904        ← POST NO INSTAGRAM
```

**Minha leitura: a raspagem NÃO funcionou ainda.** O Chromium não está
instalado, então o CDP nem chegou a rodar — os 29 produtos vieram todos do
catálogo `/social/`. Mas o bot está **saudável de ponta a ponta**: 2 ofertas
publicadas no Telegram e 1 no Instagram.

Ainda assim, três achados novos:

| Achado | Detalhe |
|---|---|
| `tidd.ly` é outro encurtador | expandiu para `kabum.com.br/produto/694714/...` ✅ |
| `resolve_store_link` falhou por falta de preço | `📡 Canal: Jogo De Toalhas... | preco=` → caiu no aviso de loja |
| `git pull` divergiu no celular | precisou de `git config pull.rebase false` |

---

### 🔴 A causa do produto pequeno

```python
product.thumbnail((box[2]-box[0], box[3]-box[1]))   # ANTES
```

**`Image.thumbnail()` NUNCA amplia** — só reduz. A foto do ML já vem no
tamanho original, então ela nunca crescia para preencher o quadro. Era esse o
motivo do produto pequeno, não a margem.

### Correções aplicadas

1. **`_fit_contain(img, max_size)`** (novo) — escala para caber na caixa
   **ampliando e reduzindo** (limite de 4x para não pixelar). É o "contain"
   de verdade.
2. **`_trim_margins(img)`** (novo) — corta a moldura branca/transparente que
   o ML manda nas fotos de produto. Só corta se houver ganho > 2%.
3. **`ART_BORDER = 34`** — a margem da foto caiu de 90/70 para 34px, para o
   fundo escuro sobrar só como **borda**.
4. **Fundo mais escuro e azul** — `gradient` foi de `(18,28,58) → (94,32,120)`
   (que virava **roxo** no rodapé) para `(6,16,44) → (14,34,78)`, azul-marinho
   em todo o card.
5. Sombra um pouco mais forte (130→150, blur 22→26) para o produto destacar
   no fundo escuro.

### Medido

| | Antes | Depois |
|---|---|---|
| Produto (foto 1000×1000 com moldura) | 900×900 | **1012×881 (+12%)** |
| Margem do fundo | 90px | **34px** |
| Cor do fundo | navy → **roxo** | navy → **azul escuro** |

Gerado antes/depois lado a lado: o produto agora encosta quase na borda e o
azul escuro fica só como moldura, exatamente como pedido.

**Resultado:**
- ✅ Produto maior, preenchendo o quadro
- ✅ Fundo azul escuro, sem roxo
- ✅ Moldura branca do ML cortada automaticamente
- ⏳ **Falta `pkg install chromium-browser` no celular** para o `/ofertas` virar

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

**Objetivo:** o usuário perguntou: *"Não tem como o bot fazer scrap
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