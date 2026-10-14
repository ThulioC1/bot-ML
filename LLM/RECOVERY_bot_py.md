# Recuperação do `bot.py` a partir do bytecode

> **Este arquivo é a referência mais importante da pasta LLM.**
> O código-fonte do `bot.py` foi perdido do disco, mas o bytecode
> (`__pycache__/bot.cpython-311.pyc`) sobreviveu e foi disassembly completo.
> Dump bruto de 636 KB: **`RECOVERY_bot_py_from_pyc.txt`**.

## O que aconteceu

| Item | Valor |
|---|---|
| Fonte original | `bot.py` |
| Tamanho | **85.872 bytes (~2.150 linhas)** |
| Última alteração | **14/10/2026 11:43:32** |
| Compilado | 14/10/2026 11:43:39 |
| Python | 3.11.9 |
| Status | **ARQUIVO AUSENTE NO DISCO** (busca em todo o `C:\` não achou) |

- O processo `python.exe bot.py` (PID **10536**) **continua rodando** desde
  11:34:25 com a versão antiga carregada em memória.
- O IDE **Antigravity** tem `bot.py` aberto
  (`bot ML - Antigravity - bot.py`) → **outra IA está trabalhando neste
  projeto agora.** Ver `ISSUES.md`.
- O bytecode prova que o `bot.py` rodou com sucesso: `seen.json` tem 2 itens
  com carimbo `14/10 11:34`, `ig_queue.json` tem 1 item, `vitrine.json` tem 8.

## Docstring original (recuperada)

```
Bot de ofertas - Vagante Promoções

Fontes : Google Sheets (principal) | Mercado Livre | Shopee | Amazon | Canais Telegram | Chat privado
Saídas : Telegram (canal + chat privado) | Instagram (com arte personalizada e preço)

Execução:  python bot.py
```

## Escala da evolução (comparado ao `bot antigo.py`)

| | `bot antigo.py` | `bot.py` (recuperado) |
|---|---|---|
| Linhas | 673 | **~2.150** |
| Funções/métodos | 20 | **63** |
| Fontes | Sheet, ML, Shopee | Sheet, ML, Shopee, **Amazon**, **canais TG**, **chat privado** |
| Saídas | Telegram, Instagram | Telegram (canal + privado), Instagram |
| Threads | 0 | **3** (main, `private_listener`, `channel_listener`) |
| asyncio | não | sim (Telethon) |

---

## Mapa completo de funções (com linha original)

### Infraestrutura / rede
| Linha | Função | O que faz |
|---|---|---|
| 51 | `_setup_stdout()` | força UTF-8 no stdout (Windows cp1252 estoura com emoji) |
| 71 | `env(name, default)` | wrapper de `os.getenv` com strip |
| 147 | `proxy_health()` | testa o proxy 1x por ciclo via `api.ipify.org`; marca `PROBE_STATE` ok/msg |
| 180 | `http_get(url, headers, timeout, referer)` | GET com `curl_cffi` (impersonate) + proxy; cai para `requests` se faltar curl_cffi; detecta bot-wall e registra host em `BLOCKED_SOURCES` |
| 219 | `selenium_driver()` | Chrome real (não headless por padrão), singleton protegido por `_DRIVER_LOCK`, `SELENIUM_STATE` |
| 257 | `selenium_get(url, wait, timeout)` | navega e devolve `page_source` |
| 276 | `browser_get(url, wait)` | tenta HTTP; se o host cair em `BLOCKED_SOURCES`, escala pro Selenium |

### Utilidades
| Linha | Função | O que faz |
|---|---|---|
| 291 | `load_json(path, default)` | leitura segura |
| 305 | `save_json(path, data)` | escrita segura com log de erro |
| 313 | `parse_money(text)` | "R$ 1.234,56" → float |
| 341 | `brl(value)` | formata pt-BR |
| 356 | `_is_bot_wall(url)` | detecta `suspicious-traffic`, `recaptcha`, `/captcha`, `challenge.oray`… |
| 361 | `expand_url(url)` | resolve redirecionadores (shope.ee, amzn.to, a.co, meli.la) com cache `URL_CACHE` |
| 411 | `clean_params(url, drop_keys)` | remove params |
| 420 | `strip_params(url, keys)` | remove params específicos (tags próprias) |
| 434 | `append_query(url, tracking)` | acrescenta tag preservando as outras |
| 449 | `is_product_url(url)` |recognize ML, Shopee, Amazon, Magalu, Buscapé, Submarino |
| 462 | `_warn_once(key, msg)` | avisa 1x por chave (`AFF_WARNED`) |

### Link de loja do Mercado Livre (feature mais complexa)
| Linha | Função | O que faz |
|---|---|---|
| 468 | `is_store_link(url)` | detecta `/social/`, `/loja/`, `/store/` |
| 473 | `_ml_product_url(href)` | converte href de vitrine em URL de produto via regex `MLB-?\d{6,}` |
| 507 | `_ml_price(card)` | extrai preço do card |
| 519 | `store_catalog(store_url)` | lê o catálogo da loja (com cache e Selenium se precisar) |
| 556 | `_keywords(text)` | tokeniza, remove stopwords (`STOP_WORDS`) |
| 560 | `resolve_store_link(store_url, price, title)` | casa o item por **preço + similaridade de título**; respeita `RESOLVE_STORE_LINKS` |

### Links de afiliado
| Linha | Função | O que faz |
|---|---|---|
| 599 | `_ml_link(url, price, title)` | expande, resolve loja, aplica `ML_MATT_WORD`/`ML_MATT_TOOL`, remove tags próprias (`matt`, `forceInApp`, `ref`) |
| 623 | `affiliate_link(url, price, title)` | roteia para ML / Shopee (`smtt`, `sp_atk`) / Amazon (`tag`, `ascsubtag`, `th`, `psc`) |
| 660 | `affiliate_status()` | status de cada tag |
| 673 | `upload_to_blob(file_path, remote_name)` | Vercel Blob |
| 697 | `tg_api(method, payload, files, timeout)` | wrapper da Bot API |

### Telegram
| Linha | Função | O que faz |
|---|---|---|
| 720 | `_image_to_jpeg(data)` | converte/normaliza imagem (WebP/AVIF → JPEG), limita lado maior a 1280 |
| 743 | `_image_candidates(url)` | variantes http/https e de CDN |
| 752 | `download_image(url, timeout)` | baixa com fallback de candidatos |
| 766 | `tg_typing(chat_id)` | mostra "digitando…" |
| 773 | `notify_admin(text)` | avisa o dono no privado (usa `ADMIN_CHAT_ID`) |
| 784 | `send_message(...)` | **ordem: upload local → URL → só texto** |
| 825 | `get_chat_name(chat_id)` | |
| 830 | `bot_can_post(chat_id)` | checa permissão de admin |
| 853 | `check_affiliate_config()` | alerta por marketplace se falta tag |
| 862 | `check_credentials()` | valida token/chat/permissão na inicialização |
| 1867 | `private_listener()` | long-polling em thread; offset persistido em `telegram_offset.json`; enfileira em `queue.Queue`; `worker()` consome |
| 1649 | `handle_private_message(message)` | **toda a lógica de comandos** (ver abaixo) |

### Instagram e arte
| Linha | Função | O que faz |
|---|---|---|
| 892 | `resolve_ig_user_id()` | corrige `IG_USER_ID` errado consultando `/me` |
| 924 | `post_to_instagram(image_url, caption)` | container + `media_publish` (v18.0) |
| 969 | `load_font(size, bold)` | **caminhos Windows + Linux** (`C:\Windows\Fonts\ariblk.ttf` …) |
| 984 | `gradient(size, top, bottom)` | |
| 993 | `text_block(...)` | texto com `stroke` e centralização |
| 1002 | `gerar_arte(...)` | **arte completa**: fundo gradiente, título com quebra automática, foto com sombra/desfoque, badge de desconto, bloco de preço |
| 1122 | `arte_para_publicar(...)` | gera + sobe no Blob |
| 1146 | `price_block(preco, preco_original)` | "De / Por" |
| 1154 | `discount_pct(preco, preco_original)` | |

### Coleta de produtos
| Linha | Função | O que faz |
|---|---|---|
| 1164 | `fetch_sheet_products()` | CSV do Google Sheets, com detecção de coluna flexível (`pick()`) |
| 1223 | `fetch_mercado_livre_products(query)` | via `browser_get` (Selenium se bloqueado) |
| 1280 | `fetch_shopee_products(query)` | API v4 |
| 1323 | `fetch_amazon_products(query)` | **novo** — busca na Amazon BR |
| 1367 | `collect_products(include_scrape, search_query)` | junta tudo e embaralha |
| 1381 | `_json_ld_products(soup)` | extrai `application/ld+json` |
| 1400 | `extract_from_html(html, url)` | título/preço/preço antigo/imagem via JSON-LD + meta tags |
| 1485 | `extract_product(url)` | pipeline completo de um link colado |

### Publicação e ciclos
| Linha | Função | O que faz |
|---|---|---|
| 1506 | `save_to_vitrine(item)` | insere no topo, limita a 15, **não duplica** |
| 1527 | `build_post_photo(product)` | baixa a thumbnail para enviar |
| 1543 | `publish(product, chat_id, reply_to, announce_instagram)` | monta texto, envia, grava `seen.json`, `vitrine.json`, enfileira no Instagram |
| 1578/1590 | `schedule_instagram(...)` | ⚠️ **definida 2 vezes** (ver `ISSUES.md`) |
| 2072 | `telegram_cycle()` | zera `BLOCKED_SOURCES`, testa proxy, posts novos da planilha + `POSTS_PER_CYCLE` da raspagem, `sleep(8)` entre posts |
| 2098 | `instagram_cycle()` | consome **1 item da `ig_queue.json`**; se o post falhar, **mantém na fila** |
| 1937 | `channel_listener()` | Telethon, espelha os `SOURCE_CHANNELS` |
| 2113 | `main()` | ver abaixo |

---

## Comandos privados do bot (recuperados do texto de ajuda)

```
🤖 *Vagante Promoções*

Envie um link de produto (Mercado Livre, Shopee, Amazon) que eu extraio
o preço e monto o post.

Comandos:
/start — esta ajuda
/canal <link> — publica direto no canal
/canal — publica o último link que você enviou
/preco <valor> <link> — monta o post com preço manual
/buscar <termo> — busca ofertas do termo
/status — diagnóstico das fontes e das tags
/ajuda — esta ajuda
```

Aliases aceitos:
`start, ajuda, help, canal, post, publicar, preco, preço, price, buscar, search, busca, status, diag`

Regex:
- `CMD_RE  = ^/\s*([a-zA-ZÀ-ÿ_]+)(?:@\w+)?(?:\s+(.*))?$`
- `URL_RE  = https?://\S+`
- `PRICE_RE = (?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:[.,]\d{1,2})?)`

---

## `main()` (L2113) — fluxo de inicialização

1. Banner `>>> BOT VAGANTE PROMOÇÕES <<<`.
2. Se `--login` no argv → entra no `channel_listener()` só para autenticar o Telethon.
3. `check_credentials()` — aborta se o Telegram não estiver ok.
4. `resolve_ig_user_id()`.
5. Avisa se faltar `curl_cffi` / `Pillow`.
6. `proxy_health()` se houver `PROXY`, senão avisa que ML/Shopee vão bloquear.
7. Avisa se não houver `template.png`.
8. Se `--once` → roda um ciclo de Telegram + Instagram e sai.
9. Senão: sobe as **duas threads** (`private_listener`, `channel_listener`, ambas `daemon=True`).
10. Loop: `sleep(15)`, Telegram a cada `INTERVAL_TELEGRAM`, Instagram a cada `INTERVAL_INSTAGRAM`, `try/except Exception`.

---

## Variáveis de ambiente lidas por `bot.py`

**Aceita os DOIS padrões de nome** (por isso a divergência entre `.env` e
`.env.example` não quebra nada):

```
ML_MATT_WORD  ou  ML_AFFILIATE_USERNAME
ML_MATT_TOOL  ou  ML_AFFILIATE_TOOL_ID
SHOPEE_TAG    ou  SHOPEE_AFFILIATE_ID
```

Demais: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `TARGET_CHAT_ID`,
`ADMIN_CHAT_ID`, `IG_ACCESS_TOKEN`, `IG_USER_ID`, `BLOB_READ_WRITE_TOKEN`,
`AMAZON_TAG`, `FOOTER`, `SHEET_CSV_URL`, `SOURCE_CHANNELS`, `SEARCH_TERMS`,
`PROXY`/`HTTPS_PROXY`, `INTERVAL_TELEGRAM`, `INTERVAL_INSTAGRAM`,
`POSTS_PER_CYCLE`, `RESOLVE_STORE_LINKS`, `USE_SELENIUM`,
`SELENIUM_HEADLESS`.

Defaults: `INTERVAL_TELEGRAM=3600`, `INTERVAL_INSTAGRAM=10800`,
`POSTS_PER_CYCLE=2`, `RESOLVE_STORE_LINKS=1`, `SELENIUM_HEADLESS=0`.
`RESOLVE_STORE_LINKS` e `SELENIUM_HEADLESS` aceitam `0/false/nao/não` e
`1/true/sim` (case-insensitive).

Tags próprias removidas antes de aplicar a de afiliado:
- ML: `matt_word`, `matt_tool`, `matt`, `forceInApp`, `ref`
- Shopee: `smtt`, `sp_atk`, `is_from_webapp`
- Amazon: `tag`, `ascsubtag`, `th`, `psc`

---

## Como reconstruir o fonte (para quem for reimplementar)

O arquivo `RECOVERY_bot_py_from_pyc.txt` tem, nesta ordem:

1. Header do `.pyc`
2. Docstring do módulo
3. Índice de funções com linha, argumentos,locais e atributos usados
4. Constantes globais (inclui todas as regex, listas de tags, URLs e o HELP)
5. Strings por função
6. **Disassembly completo** (todas as instruções, com linha e offset)

Dá para reconstruir 100% do comportamento, mas não os comentários nem
os nomes de variáveis intermediários. Alternativas:
- Procurar o arquivo no histórico do Antigravity (Ctrl+Shift+P → Local History).
- Reconstruir a partir desta spec, reaproveitando `bot antigo.py` como base.

**Atenção:** o `.pyc` é a única cópia. **Não delete `__pycache__/`.**