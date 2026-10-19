# Estado do Projeto

> Última atualização: **2026-10-19 (sessão 26 — Shopee pelo portal + correção do link de loja no canal)**

## 🆕 Sessão 26 — Shopee pelo portal de afiliado (19/10)

**Fonte Shopee:** a busca pública (403) foi trocada pelo portal logado
`affiliate.shopee.com.br/offer/product_offer`. Para cada card o bot clica em
"Obter link" (`.get-link-btn`), lê o `shope.ee`/`s.shopee.com.br` no
`.get-link-modal` e publica **esse** link (campo `affiliate_link` do produto).
`SHOPEE_OFFER_LIMIT` (default `6`) limita os cards por ciclo.

**Publish:** `publish()` usa `product["affiliate_link"]` direto quando existe;
só chama o gerador quando o produto não veio com link pronto.

**Privado:** o link que o dono manda no privado **já é o link de afiliado
dele** — o bot entra no link apenas para ler título/preço/imagem e publica o
link **como veio** (sem gerador/desembrulho) no canal e na fila do Instagram
(`announce_instagram=True`, quando há imagem). `/preco` e `/canal` idem; sem
preço lido, só sugere o `/preco` e não publica. `/buscar` continua usando o
gerador (ofertas raspadas, não são links do dono).

**Canal:** `generate_affiliate_link()` agora **expande o link curto antes** de
decidir se é link de loja — `meli.la` de `/social/` deixa de ser recusado.
Shopee no canal passa pelo portal (`generate_shopee_portal_link`), com a Open
API (`generateShortLink`) como reserva.

**Instagram:** `IG_MIN_DISCOUNT` (default `20`) — a oferta só entra na fila do
IG se tiver preço antigo e desconto real ≥ 20%. `0` desliga o filtro (posta
tudo que tem imagem). O ciclo do IG roda a cada `INTERVAL_INSTAGRAM` (3h) e
publica até `IG_POSTS_PER_CYCLE` (default `2`), com pausa de `IG_POST_DELAY`
(30s) entre um post e outro; se um post falha, o item fica na fila. Outros
filtros (teto diário, faixa de preço, dedup, `/ig` manual) ficaram como opção
futura.

**Bug de infra corrigido:** `selenium_eval()` devolvia
`{ok, value:{ok, value:{...}}}` (duplo embrulho); agora devolve o envelope do
próprio script, como o CDP. Descoberto com fixture HTML no Chrome real.

**Pendência:** validar seletores/sessão no portal real com
`python bot.py --login-browser` (ver `ISSUES.md`).

## 🆕 Sessão 25 — o link sai do GERADOR OFICIAL (19/10)

**Regra nova:** o bot **não anexa mais** `?matt_word` / `?smtt` / `?tag` na URL.
Ele abre o portal de afiliado no Chrome (perfil persistente) e publica o link
curto que o gerador devolve (`meli.la`, `shope.ee`, `amzn.to`). Se o gerador
falhar, a oferta **não é publicada** e o dono recebe aviso no privado
(`ADMIN_CHAT_ID`, throttle de 30 min por link).

| Loja | Como gera | Requer |
|---|---|---|
| Mercado Livre | POST `affiliate-program/api/v2/affiliates/createLink` (fallback DOM `#P0-2`) | login no linkbuilder |
| Shopee | portal logado (`/offer/product_offer` → "Obter link"; `/offer/custom_link`); Open API como reserva | login no portal Shopee |
| Amazon | SiteStripe `getShortUrl` (fallback DOM `#amzn-ss-get-link-button`) | login no Amazon Associados |

**Login (uma vez):** `python bot.py --login-browser` — abre os 3 portais; o
perfil fica em `BROWSER_PROFILE_DIR` (`.browser-profile/`, fora do git).

**Infra de navegador:**
- `selenium_driver(visible)` / `quit_driver()` / `browser_login_session()`
- `browser_eval()` = JavaScript no Chrome real: Selenium no PC, CDP no Android
- `browser_get(force_browser)` força navegador quando `BROWSER_SCRAPING=1`

**Roteamento por host (`_store_of_url`), cache em `link_cache.json` (6h) e
rejeição de link curto não expandido** — evita publicar link de outro afiliado.

**Pendência real:** sem sessão logada, os geradores ML/Amazon falham; no
Termux o login exige tela. Ver `ISSUES.md`.

## ✅ O código principal voltou

`bot.py` está na pasta: **~1.290 linhas / 50+ funções** (-era 1.261 / 47 na
sessão 14; cresceu com as sessões 21–23).

Já tem backup em `bot.py.backup`.

⚠️ **Mas não é a versão mais recente.** Existiu uma versão maior
(~2.150 linhas / 74 funções, de 14/10 11:43:32) com Selenium, resolução
de link de loja e Chroma. Ela **continua perdida**, mas está integralmente
documentada:

→ **`RECOVERY_bot_py.md`** — spec completa (o que falta)
→ **`RECOVERY_bot_py_from_pyc.txt`** — disassembly bruto (636 KB)
→ `bot.py.pyc-backup` — cópia do bytecode fora do `__pycache__`

## 🆕 Sessão 23 — Como o Telegram publica hoje (15/10)

**Post do canal (Telethon) e post do ciclo — mesmo formato:**

```
🔥 OFERTA EM DESTAQUE

📦 <título>

📉 De R$ 191,00
🔥 Por R$ 110,00

Gostou da oferta? Compartilhe nosso grupo: https://t.me/vagantepromo

      [ 💗 Ver Oferta ]        ← inline keyboard com o link de afiliado
```

**Regras que valem:**
- A **URL não aparece no texto** — só no botão.
- O post é **montado do zero**: o texto cru do canal **não** é repostado
  (era o que duplicava o título).
- Preço antigo e atual são lidos do **texto do canal** (`prices_from_text`),
  com fallback para a página do produto.

### ⚠️ Armadilha conhecida — não repetir

`tg_api()` muda a forma de serialização:

| caminho | chamada do `requests` | dict aninhado |
|---|---|---|
| com arquivo (`sendPhoto`) | `data=payload` (multipart) | ❌ vira `str(dict)` com **aspas simples** → Telegram 400 |
| sem arquivo (`sendMessage`) | `json=payload` | ✅ JSON válido |

→ **Sempre `json.dumps()` em `reply_markup`**, e **teste o caminho com foto**.

**Funções novas destas sessões:** `prices_from_text()` + `_MONEY_RE` (sessão 23)
e `title_from_lines()` (sessão 24).

## 🆕 Sessão 24 — De onde vem o título do post (15/10)

O canal manda **frase de divulgação primeiro, título depois**:
```
MIXER É AVANÇO DE VIDA              <- frase, NÃO é o título
Mixer Power Inox 3 em 1 600W Elgin  <- título (linha de baixo)
De R$ 191 por R$ 110 no Pix
```

`title_from_lines()` escolhe a linha certa. Ordem das regras:

1. linha com **http**, com **preço** ou curta demais não é título;
2. frase em **CAIXA ALTA** e curta perde para o título normal;
3. se só sobrar frase, pula a 1ª linha;
4. entre as normais, a 1ª vence — **exceto** isca curta terminado em
   `: ! ? -` (`"Olha isso:"`), aí usa a linha seguinte.

> **Ordem importa:** testar "caixa alta" **antes** de "pular a 1ª linha".
> Na ordem invertida, quando o título *era* a 1ª linha ele era descartado
> (erro cometido e corrigido na Sessão 24).

O `title_guess` também alimenta o `resolve_store_link()` — ou seja, escolher
a linha certa **melhora a comissão**, porque a busca na loja passa a casar pelo
nome do produto em vez da frase.

## O que é

Bot de ofertas/afiliados da **Vagante Promoções**. Coleta produtos de várias
fontes, gera o link no portal oficial de afiliados de cada loja, cria arte e
publica em Telegram e Instagram. Oferta sem link de afiliado não é publicada.

## Estrutura de arquivos

```
bot ML/
├── bot.py               # ✅ CÓDIGO PRINCIPAL (1.261 linhas, 47 funções)
├── bot.py.backup        # cópia de segurança do fonte
├── bot.py.pyc-backup    # bytecode preservado (124 KB)
├── bot antigo.py        # versão muito mais antiga (673 linhas) — histórica
├── requirements.txt
├── .env                 # 32 chaves — NÃO compartilhar, NÃO imprimir valores
├── .env.example         # 26 chaves — desatualizado
├── seen.json            # {id: {price, at}} — 2 itens
├── ig_queue.json        # fila do Instagram — 1 item
├── vitrine.json         # 8 itens publicados
├── telegram_offset.json # 165745876 (inteiro cru)
├── session_promos.session # sessão Telethon autenticada
└── LLM/                 # memória do projeto
    ├── README.md
    ├── PROJECT_STATE.md
    ├── ISSUES.md
    ├── CHANGELOG.md
    ├── RECOVERY_bot_py.md
    └── RECOVERY_bot_py_from_pyc.txt
```

## Fatos críticos

1. **A versão mais nova do `bot.py` (11:43) nunca foi salva em disco.**
   Só existe como bytecode. Faltam 27 funções — principalmente
   **Selenium** e **resolução de link de loja do ML**.
2. **O processo `python.exe bot.py` (PID 10536) continua rodando** desde
   11:34:25.
3. **Outra IA (Antigravity) está no projeto**, com `bot.py` aberto.
   Risco de sobrescrita.
4. O `.env` já está preparado: tem **as duas convenções de nome** das tags
   (`ML_MATT_WORD` **e** `ML_AFFILIATE_USERNAME`, `SHOPEE_TAG` **e**
   `SHOPEE_AFFILIATE_ID`), e o `bot.py` aceita ambas (L72–74).
5. O bot rodou com sucesso: `seen.json` com 2 itens às 11:34,
   `ig_queue.json` com 1 item, `vitrine.json` com 8.

## Arquitetura do `bot.py` atual

**50 funções** (47 originais + 3 da sessão 6), 2 threads + main. Fontes:
Google Sheets (principal) · Mercado Livre · Shopee · Amazon · canais
Telegram (Telethon) · links colados no chat privado. Saídas: Telegram
(canal + privado) · Instagram (**arte 1080×1350** com banner `img/template.png`
e o preço dentro do quadro de vidro — ver `TEMPLATE.md`).

| Linha | Função |
|---|---|
| 42 | `_setup_stdout` — UTF-8 no stdout |
| 125 | `proxy_health` — testa o proxy 1x/ciclo |
| 151 | `http_get` — `curl_cffi` com impersonation + proxy |
| 181/195 | `load_json` / `save_json` |
| 203/231 | `parse_money` / `brl` |
| 239 | `expand_url` — resolve shope.ee, amzn.to, a.co, meli.la |
| 257/266 | `clean_params` / `append_query` |
| 281 | `is_product_url` |
| 286 | `affiliate_link` — ML / Shopee / Amazon |
| 334/358 | `upload_to_blob` (Vercel) / `tg_api` |
| 374/394 | `download_image` / `send_message` |
| 432 | `check_credentials` — valida token/permissão no boot |
| 453/485 | `resolve_ig_user_id` / `post_to_instagram` |
| 530–540 | `load_font` |
| 543/552 | `gradient` / `text_block` |
| **569** | **`gerar_arte` — REESCRITA na sessão 6** (card 1080×1350, opção C) |
| **~620** | **`_fit_font` / `_draw_price_in_box` / `_draw_discount_badge` (novas)** |
| 722 | `arte_para_publicar` — gera + sobe no Blob |
| 737/745 | `price_block` / `discount_pct` |
| 755–972 | `fetch_sheet/mercado_livre/shopee/amazon` + `collect_products` |
| 972–1075 | `_json_ld_products`, `extract_from_html`, `extract_product` |
| 1075–1130 | `save_to_vitrine`, `publish`, `schedule_instagram` |
| 1164 | `handle_private_message` — comandos `/start` `/canal` `/preco` `/buscar` `/status` |
| 1290 | `private_listener` — long-polling em thread, offset persistido |
| 1340 | `channel_listener` — Telethon |
| 1448/1474 | `telegram_cycle` / `instagram_cycle` |
| 1489 | `main` |

## O que a versão perdida fazia a mais

| Feature | Situação atual |
|---|---|
| Selenium com Chrome real (destrava o ML) | ❌ **ausente** |
| Detecção de bot-wall (`suspicious-traffic`, captcha) | ❌ ausente |
| Resolução de link de loja do ML (evita comissão perdida) | ❌ ausente |
| `notify_admin` via `ADMIN_CHAT_ID` | ❌ ausente |
| `bot_can_post` / `check_affiliate_config` (diagnóstico) | ❌ ausente |
| Remoção de tags próprias antes de aplicar a de afiliado | ❌ ausente |

## `.env` — 32 chaves

Chaveadas sem nenhum código que as leia (vestígio de uma **terceira**
versão ainda maior):

`SOURCE` · `CHANNEL` · `ML_AFFILIATE` · `SHOPEE_APP_ID` · `SHOPEE_SECRET` ·
`MAGAZINE_AFFILIATE` · `AMERICANAS_AFFILIATE` · `NOTION_DATABASE_ID` ·
`BLOB_STORE_ID` · `TARGET_CHAT_ID`

## Como rodar

```bash
pip install -r requirements.txt
python bot.py              # ciclo normal
python bot.py --login      # autentica o Telethon (uma vez)
python bot.py --once       # roda um ciclo e sai
```

O `bot.py` é **tolerante a falhas**: `curl_cffi`, `Pillow`, `selenium` e
`telethon` são importados sob demanda dentro de `try/except`.

Defaults: `INTERVAL_TELEGRAM=3600` · `INTERVAL_INSTAGRAM=10800` ·
`POSTS_PER_CYCLE=2` · `IG_POSTS_PER_CYCLE=2` · `IG_POST_DELAY=30`.