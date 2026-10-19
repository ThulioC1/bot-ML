# Plano: rodar o bot no Android via Termux

> Objetivo definido pelo usuário: **"esse projeto vai rodar em um celular via
> Termux. Queria uma forma de fazer lá como no PC para que o scrap funcione."**
> Sessão de 2026-10-14.

---

## 0. ✅ ATUALIZADO — o bot JÁ está rodando no Termux (14/10 14:05)

Foto `E:\Pasta de erro\1.png` confirma:

| Item | Status |
|---|---|
| Pillow no Termux | ✅ **instalou** — o `import` da L27 não quebrou |
| Telegram | ✅ conectado |
| Instagram | ✅ conectado + **publicou** (id 18344077540253861) |
| Telethon | ✅ conectado nos canais monitorados |
| venv | ✅ em `~/.bot/bot` |
| fallback sem foto do produto | ✅ funcionou |

→ **As届 NÍVEL 1 do plano (Pillow compilado) foi atingido com sucesso.**
O `NÍVEL 0` (proxy/sem navegador) **também vale** — os erros da foto eram
100% culpa do proxy morto, corrigido na sessão 7.

### O proxy do `.env` está morto — ajuste importante

```
⚠️ proxy indisponivel (ProxyError) - a raspagem de ML/Shopee vai falhar.
```

Como o `http_get` aplicava o proxy em **todas** as URLs, o proxy morto
derrubou **inclusive o Google Sheets**. Corrigido: `proxy_health()` agora
faz `PROXIES = None` e o bot segue na conexão direta (IP residencial do
celular). Detalhes no `CHANGELOG.md` sessão 7.

**Ainda recomendo:** deixar `PROXY=` **vazio** no `.env` do celular, já que
o IP residencial não precisa dele e o proxy morto só causava problema.

---

## 1. Diagnóstico

### 1.1 O bloqueio nº 1 — o bot NÃO SOBE sem Pillow

`bot.py` linha 27:

```python
from PIL import Image, ImageDraw, ImageFilter, ImageFont   # ← INCONDICIONAL
```

Se o Pillow não instalar/compilar no Termux, o `import` estoura na hora e
**o bot inteiro morre no startup** — nem Telegram, nem planilha, nem nada.

Compare com o `curl_cffi`, que já é opcional (L30-35):
```python
try:
    from curl_cffi import requests as cureq
    HAVE_CURL_CFFI = True
except Exception:
    cureq = requests
    HAVE_CURL_CFFI = False
```

**A versão mais nova do `bot.py` (a que se perdeu) já corrigia isso** — o
bytecode mostra `HAVE_PIL` e o aviso:
> "⚠️ Pillow ausente (comum no Termux/Android) — o Telegram manda a foto do
> produto, mas a arte quadrada do Instagram fica desativada."

Ou seja: **isso estava sendo feito quando o arquivo sumiu.** É a primeira
coisa a portar.

### 1.2 A boa notícia: o resto já degrada bem

O fluxo do Instagram já está preparado para o Pillow faltar:

| Linha | Comportamento |
|---|---|
| 662 | `gerar_arte` → `except: return None` |
| 670 | `arte_para_publicar` → `if not path: return image_url` |

Ou seja, **sem Pillow o Telegram continua postando a foto do produto e o
Instagram posta a imagem original sem a arte.** Só perde o design.

→ **A correção do import resolve 90% do risco.**

### 1.3 O que NÃO vai funcionar igual no Android

| Recurso | No PC | No Termux |
|---|---|---|
| `curl_cffi` (impersonation TLS) | ✅ wheel pronto | ⚠️ **compilar localmente** |
| Pillow | ✅ wheel pronto | ⚠️ **compilar localmente** |
| Selenium + Chrome de janela real | ✅ | ❌ **impossível** |
| `telethon` | ✅ | ✅ funciona |
| `requests`, `bs4`, `dotenv` | ✅ | ✅ puro Python |
| Instagram / Telegram API | ✅ | ✅ só HTTPS |

---

## 2. A grande vantagem do celular: o IP

O código já assume isso (`bot.py` L87-88):

> "Mercado Livre e Shopee bloqueiam por IP (PolicyAgent / 403). Sem trocar o
> IP de saida, a raspagem direta nao funciona."

**No PC o IP é de datacenter/VPN — é por isso que o ML devolve
`suspicious-traffic` e o bot precisou de Selenium com janela real.**

**No celular o IP é residencial e móvel**, que o ML trata com muito mais
folga. Isso muda a estratégia inteira:

> **No Termux o proxy e o Selenium podem não ser necessários.**
> `curl_cffi` + IP residencial provavelmente basta.

Se isso se confirmar, o bot roda no celular **sem navegador nenhum** —
bem mais leve e mais estável do que no PC.

---

## 3. Caminho recomendado (3 níveis, do mais simples ao mais complexo)

### NÍVEL 0 — Pilotar sem nada nativo (teste de 5 minutos)

Objetivo: descobrir se o IP residencial já resolve o bloqueio.

```bash
pkg update -y && pkg upgrade -y
pkg install -y python python-pip clang make libcurl libandroid-support
pip install requests python-dotenv beautifulsoup4

# teste do curl_cffi nativo (compila, 1-3 min)
pip install curl-cffi

# teste
python -c "from curl_cffi import requests; print(requests.get('https://api.ipify.org?format=json', impersonate='chrome131').text)"
```

Se o teste acima imprimir um IP → **o `curl_cffi` compilou**. Rode:

```bash
python bot.py --once
```

E veja o log. Se aparecer `✅ [Mercado Livre] Produtos válidos: N` com N > 0,
**o nível 0 resolveu e não precisa de mais nada.**

### NÍVEL 1 — Bot completo com Pillow

```bash
# Pillow compila a partir do fonte (sem wheel Android no PyPI)
pkg install -y ndk-sysroot libjpeg-turbo libpng libwebp
pip install Pillow --no-binary :all:

pip install -r requirements.txt
python bot.py --once
```

Se o Pillow compilar, o bot roda **idêntico ao PC**.

### NÍVEL 2 — Fallback de navegador (só se o NÍVEL 0 falhar)

Se ainda assim o ML bloquear, é preciso renderizar a página. **Selenium
padrão não funciona no Termux** (o `selenium-manager` não é compilado para
arm64). Duas saídas:

**2A — `cdriv` (recomendado).** Pacote do PyPI feito **especificamente**
para Termux, controlando Chromium via ChromeDriver:

```bash
pkg install -y chromium-browser chromedriver
pip install cdrv
```
→ Precisa trocar `selenium_driver()`/`browser_get()` (linhas 219/276 da
versão perdida) por um cliente CDP. A spec está em `RECOVERY_bot_py.md`.

**2B — CDP puro, sem Selenium.** Termux roda Chromium headless direto:

```bash
pkg install -y chromium-browser
chromium-browser --no-zygote --single-process --headless \
                 --remote-debugging-port=9222 &
```
→ Fala CDP por WebSocket em `:9222`. Mais leve, sem dependência de driver.
Requer `LD_PRELOAD=libtermux-exec.so` (o Termux bloqueia `ET_DYN` sem isso).

**⚠️ Em qualquer um dos dois é preciso reimplementar `browser_get()`,
`selenium_driver()` e `selenium_get()` — as 3 funções que se perderam.**
A assinatura é conhecida (ver `RECOVERY_bot_py.md`, linhas 219–276).

---

## 4. Mudanças necessárias no `bot.py`

### 4.1 Obrigatória — tornar o Pillow opcional

```python
try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False
```

E em `main()`, avisar (o texto já existe na versão perdida):
> "⚠️ Pillow ausente — o Telegram manda a foto do produto, mas a arte
> quadrada do Instagram fica desativada."

Nada mais precisa mudar: `gerar_arte` (L662) e `arte_para_publicar` (L670)
já caem no fallback sozinhos.

### 4.2 Recomendada — detecção de plataforma

```python
IS_ANDROID = sys.platform == "android" or bool(os.getenv("TERMUX_VERSION"))
```

Usar para escolher o backend de browser (Selenium no PC, CDP/`cdriv` no
Android) em vez de sempre Selenium.

### 4.3 Recomendada — `load_font` já foi tratada

`bot.py` L530-540 já tem a lista de fontes com caminhos Windows **e** Linux
(veja a spec da versão perdida). ⚠️ **Falta o caminho Android/Termux.**
Verificar e acrescentar, ex.:
`$PREFIX/share/fonts/TTF/DejaVuSans-Bold.ttf` e
`/system/fonts/Roboto-Bold.ttf`.

### 4.4 Opcional — `.env` diferente no celular

```ini
# No celular, se o IP residencial resolver:
PROXY=              # deixa VAZIO de propósito
USE_SELENIUM=0
SELENIUM_HEADLESS=1
```

---

## 5. Operação no Android (o que faz o bot não morrer)

```bash
# 1. Impedir o Android de matar o processo
termux-wake-lock

# 2. Desligar otimização de bateria do Termux
#    Configurações → Bateria → otimização → Termux → Não otimizar
#    (sem isso o SO mata o processo em ~15 min)

# 3. Iniciar junto com o boot (requer o app Termux:Boot)
pkg install -y termux-boot
# criar em ~/.termux/boot/start-bot.sh:
#   #!/data/data/com.termux/files/usr/bin/sh
#   termux-wake-lock
#   cd ~/bot && python bot.py >> ~/bot.log 2>&1

# 4. Rodar em background, sobrevive ao fechar o Termux
nohup python bot.py >> ~/bot.log 2>&1 &
```

Sempre olhar o log com `tail -f ~/bot.log`.

---

## 6. Armadilhas conhecidas

| Armadilha | Detalhe |
|---|---|
| **Termux 32-bit** | `uname -m` deve dar `aarch64`. Se der `armv8l`, o curl_cffi **não tem** build de 32-bit (`Unsupported arch`). |
| `pip install curl-cffi` falha | Não há wheel Android no PyPI → compila. Faltando `libcurl`/`libandroid-support`, dá erro. Alternativa: `pip install -i https://pypi.flet.dev/curl-cffi curl-cffi` (wheels Android prontas do Flet, 0.16.2+). |
| Pillow falha | Precisa de `--no-binary :all:` + `ndk-sysroot` + `libjpeg-turbo`. |
| `selenium-manager` | Não existe para arm64 → `OSError: Exec format error`. Pin `selenium==4.9.1` ou use o NÍVEL 2. |
| Chrome headless trava | Termux exige `--no-zygote --single-process` + `LD_PRELOAD=libtermux-exec.so`. |
| Termux foi movido | `com.termux` no Google Play está desatualizado — use **F-Droid**. |
| Permissões de pasta | `termux-setup-storage` para ler `~/bot`. |
| **Login dos portais (Sessão 25)** | O perfil `.browser-profile` exige tela para o `python bot.py --login-browser`. No Termux: copie o perfil já logado do PC ou conte só com a Shopee (Open API) para gerar link. |

---

## 7. Status

- ⏳ **Nada foi alterado no `bot.py` nesta sessão** — só análise e pesquisa.
- A mudança 4.1 (Pillow opcional) é pequena e urgentemente recommendada:
  hoje, sem Pillow no Android, **o bot não inicia**.
- 🆕 Sessão 25 (19/10): o bot agora gera o link no portal oficial e só publica
  com esse link. No Termux o CDP continua raspando, mas sem perfil logado os
  geradores ML/Amazon falham e a oferta **não é publicada** (de propósito).
  A Shopee funciona pela Open API (app id/secret no `.env`).