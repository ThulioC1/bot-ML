# Issues / Pendências Conhecidas

> Backlog. Status: `ABERTA` / `EM ANDAMENTO` / `RESOLVIDA`.
> Issues resolvidas vão para o fim, com a data, e a mudança entra no `CHANGELOG.md`.

---

## [ABERTA · 2026-10-19] Portal Shopee (product_offer) ainda não rodou AO VIVO

O scraping do portal Shopee e o gerador de link do portal foram validados só
com **fixture local** (Chrome real + HTML falso), não contra o portal logado.
Sem `python bot.py --login-browser` não dá para garantir que:

- o seletor `.get-link-btn` e o wrapper `product_offer_<offer_id>` continuam
  iguais na página real;
- a sessão do perfil (`.browser-profile`) está válida e o portal não redireciona
  para `/auth`;
- o modal `.get-link-modal` entrega o `standard_short_link` em um `TextArea`
  (módulo 55529) dentro do loop de espera;
- o `POST /api/v3/gql?q=batchCustomLink` de reserva passa pelos cookies/CSRF
  reais do portal (e o `sourceCaller` segue `CUSTOM_LINK_CALLER`).

**Como validar:** `python bot.py --login-browser` → subir o bot com
`SHOPEE_OFFER_LIMIT=2` → conferir os posts e o `/status`.

## [ABERTA · 2026-10-19] Geradores oficiais nunca rodaram AO VIVO

A Sessão 25 implementou `createLink` (ML), `generateShortLink` (Shopee) e
`getShortUrl` (Amazon), mas os testes rodaram **só com mocks**. Sem uma sessão
logada (`python bot.py --login-browser`) não dá para garantir que:

- `POST /affiliate-program/api/v2/affiliates/createLink` continua no ar e aceita
  `{"urls":[url],"tag":tag}` (e que o `_csrf` do cookie/meta é o exigido);
- o SiteStripe continua em `/associates/sitestripe/getShortUrl` e aceita
  `marketplaceId=A2Q3Y263D00KWC`;
- o DOM de fallback (`#P0-2`, `#amzn-ss-get-link-button`) não mudou;
- a Open API da Shopee aceita a assinatura como implementada (o teste confere
  contra SHA256 manual, mas não contra o servidor).

**Como validar:** `python bot.py --login-browser` (logar nos 3 portais) →
subir o bot → publicar uma oferta de cada loja → `/status` mostra o estado dos
geradores (`GENERATOR_STATE`).

## [ABERTA · 2026-10-19] Login do navegador não roda no Termux (headless)

O perfil persistente (`.browser-profile`) exige tela para o login interativo.
No Android/Termux o CDP até avalia JS, mas sem os cookies de sessão dos portais
os geradores ML/Amazon falham — e a oferta **não é publicada** (comportamento
proposital: melhor não postar do que postar sem comissão). Opções: copiar o
perfil do PC para o Termux, ou aceitar que no Android só a Shopee (Open API)
gera link.

## [RESOLVIDA · 2026-10-19] Roteador confundia magazineluiza.com.br com a Amazon

O teste do roteador pegou: `"a.co" in url` casa com `magazineluiza.com.br`.
A loja agora é decidida **pelo host** em `_store_of_url()` — e o teste
`test_router_unsupported_store` garante que Magazine Luiza devolve o link
original, sem gerador.

## [RESOLVIDA · 2026-10-15] Botão do Telegram quebrou o envio de fotos

**Sintoma:** depois da Sessão 22, o Telegram parou de aceitar as fotos. O texto
continuava saindo (sem botão), a foto não.

**Causa:** `tg_api()` usa `data=payload` quando há arquivo (multipart) e
`json=payload` quando não há. Com `data=`, o `requests` **stringifica** o
`reply_markup` e um dict aninhado sai com **aspas simples** — o Telegram
responde `400 can't parse reply keyboard markup`.

**Correção:** `json.dumps(reply_markup, ensure_ascii=False)` nos dois caminhos
de `send_message()`. Provado: `str(dict)` → `JSONDecodeError`; `json.dumps` → OK.

> **Regra:** dict aninhado para a API do Telegram **sempre** via `json.dumps()`.
> E testar o caminho **com arquivo**, não só o com JSON.

## [RESOLVIDA · 2026-10-15] Título duplicado nos posts do canal

**Causa:** o handler fazia `text = raw` e reenviava a mensagem inteira do canal
depois de acrescentar o título no topo. O título saía duas vezes, e junto iam a
frase de marketing e o link gigante.

**Correção:** o post é montado do zero — título, preço e footer. O texto do
canal não é repostado.

## [RESOLVIDA · 2026-10-15] Preço antigo nunca aparecia no Telegram

**Causa:** o regex `r"R\$\s*([\d\.]+,\d{2})"` **exigia centavos**. Os canais
publicam `De R$ 191 por R$ 110` (sem centavos) → o preço atual vinha do
`extract_product` e o antigo nunca era lido.

**Correção:** `prices_from_text()` devolve `(atual, antigo)` e entende
`"De R$ X por R$ Y"`, `"R$ 1.234,56"`, `"R$ 110"`, `"R$ 1.234"`. 11/11 testes.

## [RESOLVIDA · 2026-10-15] Emoji `🔗` saía como `ðŸ"`

Era **mojibake**: o emoji decodificado como cp1252. O `FOOTER_TEXT` novo não tem
emoji nenhum, então não há o que quebrar.

---

## [PARCIAL · 2026-10-14] `bot.py` foi apagado do disco

**Status mudou:** o usuário recuperou o fonte, **mas uma versão mais antiga.**

| | `bot.py` (recuperado) | bytecode (versão nova) |
|---|---|---|
| Linhas | 1.261 | ~2.150 |
| Bytes | 58.847 | 85.872 |
| Funções | 47 | 74 |
| Origem | em memória, 11:34:25 | fonte de 11:43:32 |

O fonte recuperado é um **ancestral estrito** — todas as 47 funções dele
existem na versão nova. Faltam 27 funções (todas documentadas em
`RECOVERY_bot_py.md`):

- **Selenium com Chrome real** (`selenium_driver`, `selenium_get`, `browser_get`)
  → sem isso, quando o ML devolve `suspicious-traffic` a raspagem **para**.
- **Resolução de link de loja** (`is_store_link`, `store_catalog`,
  `resolve_store_link`, `_ml_product_url`, `_ml_price`, `_keywords`)
  → sem isso, ofertas cujo link é a loja do ML saem **sem comissão**.
- `_is_bot_wall`, `strip_params`, `_warn_once`, `affiliate_status`,
  `_image_to_jpeg`, `_image_candidates`, `tg_typing`, `notify_admin`,
  `bot_can_post`, `check_affiliate_config`, `pick`, `build_post_photo`,
  `split_price_and_url`, `destination_label`, `worker`, `run`, `handler`

**Já feito:**
- ✅ Backup do fonte: `bot.py.backup`
- ✅ Backup do bytecode: `bot.py.pyc-backup` (fora do `__pycache__`)
- ✅ Spec completa das 27 funções: `RECOVERY_bot_py.md`
- ✅ Disassembly completo: `RECOVERY_bot_py_from_pyc.txt`

**Ainda possível:**
- Tentar o *Local History* do Antigravity para achar a versão das 11:43.
- Reimplementar as 27 funções a partir da spec (trabalho viável, ~900 linhas).

---

## [RESOLVIDA · 2026-10-14] Template nunca era usado

`TEMPLATE_FILE` apontava para `template.png` na raiz; o arquivo está em
`img/template.png`. `.exists()` era False e o bot caía silenciosamente no
gradiente. **Corrigido na sessão 6.**

## [RESOLVIDA · 2026-10-14] Geometria da arte incompatível com o template

`gerar_arte` era escrito para 1080×1080; o template é 1024×217. O preço era
desenhado em `y=790`, fora da imagem. **Corrigido na sessão 6** (opção C,
card 1080×1350).

## [RESOLVIDA · 2026-10-14] Placeholder branco sólido + emoji em bloco

`ImageDraw` sobrescreve o pixel em vez de fazer alpha-blend, então o
retângulo translúcido virava branco sólido no JPEG. O emoji 🛍️ virava bloco
branco porque `load_default()` é fonte bitmap. **Ambos corrigidos.**

---

---

## [RESOLVIDA · 2026-10-14] PROXY morto derrubava TODAS as requisições

Visto na foto `E:\Pasta de erro\1.png` (14/10 14:05, rodando no Termux):
`http_get` aplicava `proxies=PROXIES` em todas as URLs. Com o proxy morto,
**inclusive o Google Sheets** (que não precisa de proxy) retornava
`ConnectionError`.

**Corrigido na sessão 7:** `proxy_health()` agora faz `PROXIES = None`
quando o probe falha (era a linha 176 da versão perdida, recuperada do
bytecode).

## [ABERTA] `PROXY` do `.env` está morto

O bot agora se recovers sozinho (cai para conexão direta), mas o valor no
`.env` continua sendo lixo. **Trocar por um que funcione ou deixar vazio**,
principalmente para o celular.

## [ABERTA] Shopee pode bloquear mesmo sem proxy

O `PROXIES=None` garante a conexão, mas o bloqueio da Shopee é do próprio IP
e do fingerprint. No celular (IP residencial) é mais provável passar — ainda
não foi testado de verdade.

## [ABERTA] Mensagem "Planilha indisponivel (HTTP erro)" é enganosa

Não foi erro HTTP, foi `ConnectionError` de proxy. A mensagem mente sobre a
causa. Baixa prioridade.

---

---

## [RESOLVIDA · 2026-10-14] Link encurtado nunca era expandido

`expand_url()` usava `requests.head()`, e o encurtador do ML responde
**HTTP 405** a HEAD. Como 405 não é exceção, o fallback para GET era código
morto. → `meli.la` continuava curto e a tag ia por cima dele.

**Corrigido na sessão 10:** `GET` direto → `GET` via proxy → `HEAD` via proxy.

## [RESOLVIDA · 2026-10-14] Tag de outro afiliado não era removida

Links de origem já traziam `matt_word=linksbr&matt_tool=17783195`.
**Corrigido:** `strip_params()` remove `matt_word`, `matt_tool`, `matt`,
`forceInApp`, `ref` (e equivalentes de Shopee/Amazon) antes de aplicar a
nossa tag.

## [RESOLVIDA · 2026-10-14] `resolve_store_link` — link de loja vira link de produto

Link `meli.la` dos canais monitorados expande para
`www.mercadolivre.com.br/social/linksbrazil` — link de LOJA, que ignora
tag de afiliado.

**Implementado na sessão 11.** 6 funções portadas do bytecode, testadas
contra a loja real (`/social/linksbrazil`, 19 produtos, não é bloqueada).
4/4 testes passaram. O link agora sai como
`/produto/p/MLB72006876?matt_word=...&matt_tool=...`.

**Limites:** só a primeira página do catálogo (19 itens); cache de 5 min.
Se não achar, a oferta é descartada e o dono avisado.

---

## [ABERTA · CRÍTICA] Mercado Livre bloqueia o IP residencial (bot-wall)

14/10 14:35, no celular:
```
⊘ www.mercadolivre.com.br bloqueou o acesso (HTTP 200, pagina de verificacao).
⚠️ Mercado Livre: 0 produtos (provável bloqueio anti-bot).
```
Mesmo com `curl_cffi` + `impersonate="chrome131"` e IP residencial.
Shopee também bloqueia (403).

**Opções (ver `TERMUX.md` seção 3):**
- **Preencher a planilha** — fonte confiável, nunca é bloqueada. Atalho.
- **Proxy residencial BR funcionando** — o antigo está morto.
- **CDP/Chromium no Termux** — NÍVEL 2, exige reimplementar `browser_get()`.

---

## [ABERTA] Telethon precisa de `--login` no celular

A sessão do PC não vai no clone (`.session` está no `.gitignore`, e é uma
credencial). Rodar `python bot.py --login` no Termux.

---

## [RESOLVIDA · 2026-10-14] Selenium não funciona no Termux — resolvido com CDP

`selenium-manager` não é compilado para arm64. Implementado o backend **CDP**
(Chrome DevTools Protocol) na sessão 13: sobe o Chromium com
`--remote-debugging-port` e lê a página por WebSocket. Sem driver, sem Selenium.

**Validado no PC com Chrome e `USE_SELENIUM=False`** (o mesmo caminho do
celular): 49 produtos do `/ofertas`, 727 KB de HTML, sem parede anti-bot.

**Falta testar em hardware Android** — o Chromium do Termux pode ter quirks.

## [ABERTA · CRÍTICA] Chromium ainda não instalado no celular

Comando **errado** na sessão 13 (minha culpa): `pkg install chromium-browser`
não existe — esse é o nome do binário.

**Comando certo:**
```bash
pkg update -y
pkg install x11-repo
pkg update -y
pkg install chromium
```

Instala em `$PREFIX/bin/chromium-browser` (symlink) e
`$PREFIX/lib/chromium/chrome` (binário real). O `chromium_binary()` já
procura os dois.

> Alternativa pelo `tur-repo` tem histórico de `CANNOT LINK EXECUTABLE`.

Sem isso o `/ofertas` não abre e o bot usa só `/social/` (29 produtos em vez
de ~48).

## [ABERTA] `resolve_store_link` falha quando o canal não manda preço

```
📡 Canal: Jogo De Toalhas Buddemeyer Bella Extra Soft B | foto=sim | preco=
⛔ link de LOJA do ML ... nao gera comissao sua.
```

Sem preço **e** sem título conclusivo, não há como achar o produto na loja.
Comportamento seguro (não posta link quebrado), mas perde a oferta.

**Ideia:** quando o preço não vem no texto, tenta extrair da imagem do post
ou usar o título inteiro como match. Falta implementar.

## [RESOLVIDA · 2026-10-14] Produto pequeno na arte

`Image.thumbnail()` nunca amplia — só reduz. Substituído por `_fit_contain()`
(amplia até 4x) + `_trim_margins()` (corta moldura branca do ML) + margem
reduzida de 90 para 34px. Fundo trocado de navy→roxo para navy→azul escuro.

---

## [ABERTA] `websocket-client` é dependência nova

`pip install websocket-client` (python puro, compila em qualquer lugar).
Precisa entrar no `requirements.txt`.

## [ABERTA] Chromium no Termux é pesado

Rodar Chromium dentro do Termux consome bastante bateria/memória. Manter
`termux-wake-lock` e a otimização de bateria desligada, senão o SO mata.

---

## [RESOLVIDA · 2026-10-14] `/ofertas` — eu tinha concluído errado

Na sessão 11 concluí que `/ofertas` era impossível e troquei a fonte por
`/social/<loja>`. **Estava errado:** só testei HTTP. Com Chrome de verdade
(Selenium, janela real fora da tela) a mesma URL devolve 49 produtos —
provado na sessão 12.

**Corrigido:** `browser_get()` + `selenium_driver()` + `selenium_get()`
portados do bytecode. `/social/<loja>` ficou como reserva.

## [ABERTA] Selenium não funciona no Termux — `/ofertas` no celular

`selenium-manager` não é compilado para arm64. No celular o `/ofertas` via
Chrome fica indisponível e o bot usa a reserva `/social/<loja>` (funciona).

Para `/ofertas` no celular é preciso **CDP** (Chrome DevTools Protocol) no
lugar do Selenium. Ver `TERMUX.md` seção 3 (NÍVEL 2).

## [ABERTA · CRÍTICA] Mercado Livre bloqueia HTTP — mesmo no IP residencial

Testado no PC (IP datacenter) e no celular (IP residencial): **o mesmo
resultado.**

| URL | Resultado |
|---|---|
| `/ofertas?page=N` | HTTP 200 + `suspicious-traffic` → parede |
| `lista.mercadolivre.com.br/*` | HTTP 200 + parede |
| página de produto | HTTP 200 + parede |
| `api.mercadolibre.com` | HTTP 403 |
| **`/social/<loja>`** | ✅ **200, 243–297 KB, produtos com preço** |
| home `/` | ✅ 545 KB |

Não adianta trocar cookie, User-Agent mobile ou sessão — testado, nenhum
dos três destrava. **Só o Chrome de verdade passa.**

---

## [ABERTA] A planilha do Google está VAZIA (verificado 14/10 14:50)

CSV público retorna HTTP 200 com cabeçalho `['Link', 'Preço', 'Titulo', 'Foto']`
e **0 linhas de dados**. As colunas batem com o que o código procura — só
falta cadastrar produto.

---

## [ABERTA] `SEARCH_TERMS` é carregado do `.env` e nunca usado

`bot.py` L85 é a **única ocorrência** da variável no arquivo inteiro.
O ciclo automático só chama `fetch_mercado_livre_products()` sem argumento
→ sempre vai em `/ofertas?page=N`.

O modo por termo (`lista.mercadolivre.com.br/<termo>`) só é alcançado pelo
comando `/buscar`. O `.env.example` documenta `SEARCH_TERMS` como se
funcionasse no ciclo — **não funciona**.

**Impacto:** é uma fonte de produtos pronta e não utilizada. Além disso
`/ofertas` é justamente a URL mais protegida do ML, então habilitar o modo
por termo pode ajudar no bloqueio.

---

## [ABERTA · CRÍTICA] `bot.py` não sobe no Android — import do Pillow é incondicional

`bot.py` L27: `from PIL import Image, ImageDraw, ImageFilter, ImageFont`

Se o Pillow não compilar no Termux, o bot **morre no startup**. Não é
degradação parcial — é morte total.

**Correção (1 linha + guard):** envolver em `try/except` com `HAVE_PIL`,
igual já é feito com o `curl_cffi` (L30-35). O resto do fluxo já degrada
sozinho: `gerar_arte` (L662) devolve `None` e `arte_para_publicar` (L670)
cai para a `image_url` original.

A versão **perdida** do `bot.py` já tinha esse guard (`HAVE_PIL`) e o aviso
"Pillow ausente (comum no Termux/Android)". A correção foi perdida com ela.

→ Detalhes completos em `TERMUX.md`.

---

## [ABERTA] Fontes do Android não estão na lista do `load_font`

`load_font` (L530-540) tem caminhos Windows e Linux, mas **nenhum do
Android/Termux** (`$PREFIX/share/fonts/...`, `/system/fonts/Roboto-Bold.ttf`).
Sem isso, a arte sai com a fonte padrão do bitmap.

---

## [ABERTA] Selenium não funciona no Termux — precisa de backend alternativo

O `selenium-manager` não é compilado para arm64. Se o bot precisar de
renderização de página no Android, `browser_get()` tem que falar **CDP**
(Chrome DevTools Protocol) ou usar o pacote `cdriv`, em vez de Selenium.

A assinatura das 3 funções necessárias está em `RECOVERY_bot_py.md`
(linhas 219–276). Ver `TERMUX.md` seção 3.

---

## [ABERTA] Backup do `bot.py` em local seguro

`bot.py.backup` e `bot.py.pyc-backup` estão na **mesma pasta** do original —
se a pasta for apagada, some tudo junto.

**Próximos passos:** copiar para outro disco/nuvem, ou
inicializar git com `.gitignore` (`.env`, `__pycache__/`, `*.session*`).

---

## [ABERTA · CRÍTICA] Outra IA pode estar editando o projeto ao mesmo tempo

O IDE **Antigravity** tem a janela `bot ML - Antigravity - bot.py` aberta,
e foi ele que lançou o processo Python (variável `BUNDLED_DEBUGPY_PATH`
aponta para as extensões de debug do Antigravity).

**Risco:** duas IAs escrevendo `bot.py` ao mesmo tempo = sobrescrita mútua
e perda de trabalho. Foi exatamente assim que o arquivo pode ter sumido.

**Próximos passos:** o usuário precisa escolher **uma** IA para trabalhar
neste projeto e parar a outra.

---

## [ABERTA] Bug: `schedule_instagram` definida duas vezes no `bot.py`

Aparece em L1578 e em L1590, com corpo e strings idênticos. A segunda
definição sobrescreve a primeira — a primeira é **código morto**.

**Impacto:** nenhum funcional (são iguais), mas indica merge/refactor mal
feito e confunde a leitura.

---

## [ABERTA] Bug: fonte da arte do Instagram quebra no Windows (`bot antigo.py`)

`gerar_arte_produto` (linha 247) só procura fontes em caminhos Linux/Android:

```python
"/system/fonts/Roboto-Bold.ttf"
"/data/data/com.termux/files/usr/share/fonts/..."
```

No Windows nenhum existe → cai em `ImageFont.load_default()`, que é uma
fonte bitmap minúscula. **O preço sai ilegível ou invisível no post.**

O `bot.py` já corrigia isso, com:
```python
'C:\\Windows\\Fonts\\ariblk.ttf', 'C:\\Windows\\Fonts\\arialbd.ttf',
'C:\\Windows\\Fonts\\segoeuib.ttf', 'C:\\Windows\\Fonts\\calibrib.ttf'
```
→ Copiar essa lista ao reconstruir.

---

## [ABERTA] `bot antigo.py` ignora o `.env` em vários pontos

Se for usado como fallback, saber estes limites:

- `INTERVAL_TELEGRAM=3600` e `INTERVAL_INSTAGRAM=10800` estão **hardcoded**
  nas linhas 649–650, ignorando o `.env`.
- Só existe o comando `/produto`. Faltam `/start`, `/canal`, `/preco`,
  `/buscar`, `/status`.
- Não tem proxy, Selenium, Telethon, Amazon nem `ig_queue.json`.
- Usa caminhos **relativos** — depende do diretório atual. O `bot.py` usava
  `BASE_DIR / ...`.
- Importa `curl_cffi` e `Pillow` incondicionalmente (o `bot.py` era opcional).
- `post_to_instagram_feed` chama `.json()` sem checar `status_code`.
- `save_json` trunca mutando o dict recebido.
- Lê `ML_AFFILIATE_USERNAME`/`SHOPEE_AFFILIATE_ID` — que **existem** no
  `.env` atual, então os links de afiliado funcionam nesse arquivo.

---

## [ABERTA] `.env.example` está desatualizado

4 chaves que o `bot.py` lê **não** estão no `.env.example`:
`ADMIN_CHAT_ID`, `RESOLVE_STORE_LINKS`, `USE_SELENIUM`, `SELENIUM_HEADLESS`
→ o bot usa defaults e não avisa.

10 chaves do `.env` não estão no `.env.example`:
`SOURCE`, `CHANNEL`, `ML_AFFILIATE`, `SHOPEE_APP_ID`, `SHOPEE_SECRET`,
`MAGAZINE_AFFILIATE`, `AMERICANAS_AFFILIATE`, `NOTION_DATABASE_ID`,
`BLOB_STORE_ID`, `TARGET_CHAT_ID`.

Além disso o `.env.example` não menciona que `bot.py` aceita **os dois**
nomes de tag (`ML_MATT_WORD` **ou** `ML_AFFILIATE_USERNAME`).

**Nota:** a divergência de nomes que a sessão 1 tratou como "crítica" **não
quebra o bot** — `bot.py` aceitava as duas formas. Corrigido no PROJECT_STATE.

---

## [ABERTA] Vestígios de uma terceira versão do bot (Notion / Magalu / Americanas)

10 chaves no `.env` não são lidas por nenhum código que temos:
`NOTION_DATABASE_ID`, `MAGAZINE_AFFILIATE`, `AMERICANAS_AFFILIATE`,
`SHOPEE_APP_ID`, `SHOPEE_SECRET`, `SOURCE`, `CHANNEL`, `ML_AFFILIATE`,
`BLOB_STORE_ID`, `TARGET_CHAT_ID`.

→ Existiu (ou existe no editor de outro agente) um bot com **Notion**,
**Magazine Luiza**, **Americanas** e **Shopee Open Platform**.

**Próximos passos:** verificar o histórico do Antigravity por um `bot.py`
ainda maior que o bytecode não reflete.

---

## [ABERTA] `telegram_offset.json` é um inteiro cru

O arquivo contém `165745876`, mas `load_json` historicamente só devolvia
`isinstance(data, dict)`. Se `private_listener` fizer `int(load_json(...))`
com `{}`, o offset zera a cada restart e **todas as mensagens antigas são
reprocessadas**.

**Próximo passo:** confirmar no disassembly (`RECOVERY_bot_py_from_pyc.txt`,
seção `private_listener`) se `load_json` aceita escalar.

---

## [ABERTA] Link de loja do Mercado Livre (já implementado no `bot.py` perdido)

`RESOLVE_STORE_LINKS=1` (default) fazia `resolve_store_link()` ler o
catálogo da loja e casar o item por **preço + similaridade de título**. Se
não achasse, o bot avisava o dono no privado e **descartava a oferta**,
porque link de loja não gera comissão.

Ao reconstruir, essa feature tem 6 funções (~120 linhas) — é a parte mais
delicada do código.

---

## [ABERTA] `.env` com segredos reais na pasta

`.env` contém token do Telegram, token do Instagram, token da Vercel Blob,
API ID/hash do Telegram e tags de afiliado.

- Nunca imprimir valores em sessão nenhuma.
- Nunca commitar.
- Se o repositório um dia for git, adicionar `.gitignore` com
  `.env`, `__pycache__/`, `*.session`, `*.session-journal`.

---

## [RESOLVIDA · 2026-10-14] Estrutura do `bot.py` recuperada

O bytecode foi disassembly completo e a spec está em `RECOVERY_bot_py.md`
+ `RECOVERY_bot_py_from_pyc.txt` (636 KB). O comportamento pode ser
reconstruído; só os comentários e nomes de variáveis intermediários se perderam.

## [RESOLVIDA · 2026-10-14] Divergência de nomes de tag do afiliado

Não é bug: o `bot.py` aceitava `ML_MATT_WORD` **e** `ML_AFFILIATE_USERNAME`,
`SHOPEE_TAG` **e** `SHOPEE_AFFILIATE_ID`. O `.env` tem ambas.