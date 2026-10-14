# Issues / Pendências Conhecidas

> Backlog. Status: `ABERTA` / `EM ANDAMENTO` / `RESOLVIDA`.
> Issues resolvidas vão para o fim, com a data, e a mudança entra no `CHANGELOG.md`.

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