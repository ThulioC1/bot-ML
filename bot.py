# -*- coding: utf-8 -*-
"""
Bot de ofertas - Vagante Promoções

Fontes : Google Sheets (principal) | Mercado Livre | Shopee | Amazon | Canais Telegram | Chat privado
Saídas : Telegram (canal + chat privado) | Instagram (com arte personalizada e preço)

Execução:  python bot.py
"""

import csv
import hashlib
import io
import json
import os
from collections import deque
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Impersonação de TLS: alguns marketplaces bloqueiam requests comuns.
try:
    from curl_cffi import requests as cureq
    HAVE_CURL_CFFI = True
except Exception:
    cureq = requests
    HAVE_CURL_CFFI = False

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _setup_stdout():
    """O console do Windows usa cp1252 e estoura ao imprimir emoji."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_setup_stdout()


LOG_BUFFER = deque(maxlen=200)

_SECRET_NAMES = ("TELEGRAM_TOKEN", "IG_ACCESS_TOKEN", "BLOB_READ_WRITE_TOKEN",
                 "SHOPEE_SECRET", "API_HASH")


def _redact(text):
    """Evita que tokens vazem nos logs (inclusive dentro de URLs de erro)."""
    text = str(text)
    for name in _SECRET_NAMES:
        value = globals().get(name) or os.getenv(name, "")
        value = (value or "").strip().strip('"').strip("'")
        if len(value) >= 8:
            text = text.replace(value, "***")
    return text


def log(msg):
    line = f"[{time.strftime('%d/%m %H:%M:%S')}] {_redact(msg)}"
    print(line, flush=True)
    LOG_BUFFER.append(line)


# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------

def env(name, default=""):
    return (os.getenv(name, default) or "").strip().strip('"').strip("'").replace("\n", "").replace("\r", "")


TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID") or env("TARGET_CHAT_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN")
IG_USER_ID = env("IG_USER_ID")
BLOB_TOKEN = env("BLOB_READ_WRITE_TOKEN")

ML_MATT_WORD = env("ML_MATT_WORD") or env("ML_AFFILIATE_USERNAME")
ML_MATT_TOOL = env("ML_MATT_TOOL") or env("ML_AFFILIATE_TOOL_ID")
SHOPEE_TAG = env("SHOPEE_TAG") or env("SHOPEE_AFFILIATE_ID")
AMAZON_TAG = env("AMAZON_TAG")

# --- Geradores oficiais de link de afiliado --------------------------------
# O link publicado agora e SEMPRE o link curto produzido pelo gerador oficial
# de cada loja. O bot nao acrescenta mais ?tag / ?matt_word na URL.
#
# ML      : POST /affiliate-program/api/v2/affiliates/createLink (sessao do
#           navegador persistente + etiqueta da conta)
# Shopee  : Open API oficial generateShortLink (App ID + Secret)
# Amazon  : SiteStripe /associates/sitestripe/getShortUrl (sessao do navegador)
ML_AFFILIATE_TAG = (
    env("ML_AFFILIATE_TAG")
    or ML_MATT_WORD
    or env("ML_AFFILIATE_USERNAME")
    or env("ML_AFFILIATE")
)
SHOPEE_APP_ID = env("SHOPEE_APP_ID")
SHOPEE_SECRET = env("SHOPEE_SECRET")
SHOPEE_API_URL = "https://open-api.affiliate.shopee.com.br/graphql"
AMAZON_MARKETPLACE_ID = env("AMAZON_MARKETPLACE_ID", "A2Q3Y263D00KWC")

# Pastas persistentes: o login feito uma vez em cada portal fica salvo aqui.
_PROFILE_ENV = env("BROWSER_PROFILE_DIR")
BROWSER_PROFILE_DIR = Path(_PROFILE_ENV) if _PROFILE_ENV else (BASE_DIR / ".browser-profile")
if not BROWSER_PROFILE_DIR.is_absolute():
    BROWSER_PROFILE_DIR = BASE_DIR / BROWSER_PROFILE_DIR
BROWSER_SCRAPING = env("BROWSER_SCRAPING", "1").strip().lower() not in ("0", "false", "nao", "não")
try:
    LINK_GEN_TIMEOUT = max(15, int(env("LINK_GEN_TIMEOUT", "60") or 60))
except ValueError:
    LINK_GEN_TIMEOUT = 60
LINK_GEN_CACHE_FILE = BASE_DIR / "link_cache.json"
LINK_GEN_CACHE_TTL = 6 * 3600

ML_LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder"
SHOPEE_AFFILIATE_URL = "https://affiliate.shopee.com.br/"
SHOPEE_PRODUCT_OFFER_URL = "https://affiliate.shopee.com.br/offer/product_offer"
SHOPEE_CUSTOM_LINK_URL = "https://affiliate.shopee.com.br/offer/custom_link"
ML_COUPONS_URL = "https://mercadolivre.com.br/ofertas/cupons"
ML_PROMOS_URL = "https://mercadolivre.com.br/l/promocoes"
# Sinais da tela de anti-bot da Shopee (site publico).
SHOPEE_BOT_MARKERS = ("verify/traffic", "anti-bot", "antibot", "captcha",
                      "suspicious", "90309999")
AMAZON_HOME_URL = "https://www.amazon.com.br/"
try:
    SHOPEE_OFFER_LIMIT = max(1, int(env("SHOPEE_OFFER_LIMIT", "6") or 6))
except ValueError:
    SHOPEE_OFFER_LIMIT = 6
GENERATOR_STATE = {
    "ml": {"ok": None, "msg": "não usado ainda"},
    "shopee": {"ok": None, "msg": "não usado ainda"},
    "amazon": {"ok": None, "msg": "não usado ainda"},
}


def generator_label(store):
    state = GENERATOR_STATE.get(store) or {}
    if state.get("ok") is True:
        return "OK"
    return "falha" if state.get("ok") is False else "não testado"

FOOTER_TEXT = env("FOOTER", "Gostou da oferta? Compartilhe nosso grupo: https://t.me/vagantepromo")

SHEET_CSV_URL = env(
    "SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRKHrxu8OFtNtgj6Hs6IlPIhg-mhQbHXrQxi6uiSnoTZI_I3RGk26SE5fMoUz2nMU3X95w0_OmLxfOa/pub?output=csv",
)

SOURCE_CHANNELS = [c.strip() for c in env("SOURCE_CHANNELS").split(",") if c.strip()]
SEARCH_TERMS = [t.strip() for t in env("SEARCH_TERMS").split(",") if t.strip()]

# Lojas do ML usadas como fonte de ofertas. /ofertas e /lista/ estao atras do
# bot-wall do ML e NUNCA respondem (nem com sessao, cookie ou UA mobile).
# Ja /social/<loja> responde sempre e traz os produtos com preco e titulo.
# Deixe vazio no .env para o bot usar so as lojas que ele aprendeu nos canais.
ML_STORES = [s.strip().strip("/") for s in env("ML_STORES").split(",") if s.strip()]
ML_STORE_BASE = "https://www.mercadolivre.com.br/social/"

# O ML devolve "suspicious-traffic" para requests E para curl_cffi. So um Chrome
# de verdade que passa -- por isso o Selenium. Sem janela (headless) o ML tambem
# barra, entao o padrao e janela real escondida fora da tela.
USE_SELENIUM = env("USE_SELENIUM", "1").strip().lower() not in ("0", "false", "nao", "não")
SELENIUM_HEADLESS = env("SELENIUM_HEADLESS", "0").strip().lower() in ("1", "true", "sim")
IS_ANDROID = sys.platform == "android" or bool(os.getenv("TERMUX_VERSION"))

# No Android o Selenium nao funciona (selenium-manager nao e compilado para
# arm64), entao desligar por la evita ficar tentando e imprimindo erro.
if IS_ANDROID:
    USE_SELENIUM = False

_DRIVER = None
_DRIVER_LOCK = threading.Lock()
SELENIUM_STATE = {"ok": False, "msg": "não iniciado"}

# --- Backend CDP (Chrome DevTools Protocol) ---------------------------
# No Termux o Selenium nao funciona (selenium-manager nao existe para arm64),
# mas o Chromium do Termux conversa CDP direto. Serve tambem no PC.
CDP_PORT = int(env("CDP_PORT", "9222") or 9222)
CDP_HOST = env("CDP_HOST", "127.0.0.1")
CDP_WAIT = int(env("CDP_WAIT", "6") or 6)
_CDP = {"proc": None, "tried_at": 0, "msg": "não iniciado"}
NET_STATE = {"online": True, "since": 0.0}

# Mercado Livre e Shopee bloqueiam por IP (PolicyAgent / 403). Sem trocar o IP de
# saida, a raspagem direta nao funciona. Defina um proxy estavel aqui.
# Formatos aceitos:  http://usuario:senha@host:porta   |   http://host:porta
PROXY_URL = env("PROXY") or env("HTTPS_PROXY")
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
PROBE_AT = 0
PROBE_STATE = {"ok": None, "msg": ""}

INTERVAL_TELEGRAM = int(env("INTERVAL_TELEGRAM", "3600") or 3600)
INTERVAL_INSTAGRAM = int(env("INTERVAL_INSTAGRAM", "10800") or 10800)
POSTS_PER_CYCLE = int(env("POSTS_PER_CYCLE", "2") or 2)


def _num_env(nome, padrao):
    """Le um numero do .env; devolve o padrao se vier vazio/quebrado."""
    bruto = env(nome, "").replace(".", "").replace(",", ".")
    try:
        return float(bruto)
    except (TypeError, ValueError):
        return float(padrao)


# Filtro de oferta: sem isso passa shampoo de R$ 24.000 e console de R$ 5.000,
# que nao sao promocao de nada.
MIN_PRICE = _num_env("MIN_PRICE", 15)
MAX_PRICE = _num_env("MAX_PRICE", 3000)
MIN_DISCOUNT = _num_env("MIN_DISCOUNT", 0)      # 0 = nao exige desconto

# Filtro do Instagram: so entra na fila se o desconto real for >= esse valor.
# Sem preco antigo nao da para medir desconto, entao tambem fica de fora.
# Default 0 = desligado, igual ao MIN_DISCOUNT: a raspagem do ML e o portal
# Shopee quase nunca trazem preco antigo, e com 20 o IG ficava sem fila.
IG_MIN_DISCOUNT = _num_env("IG_MIN_DISCOUNT", 0)

# Instagram: quantos posts por ciclo (o ciclo roda a cada INTERVAL_INSTAGRAM,
# default 3h) e pausa em segundos entre um post e outro.
IG_POSTS_PER_CYCLE = max(1, int(_num_env("IG_POSTS_PER_CYCLE", 2)))
IG_POST_DELAY = _num_env("IG_POST_DELAY", 30)

# Hashtags sorteadas em cada legenda. O sorteio evita repetir sempre as mesmas
# tres tags e ajuda o alcance sem transformar a legenda numa parede de texto.
IG_HASHTAGS = (
    "#achados", "#ofertas", "#promocao", "#comprasonline", "#acheinashopee",
    "#achadinhosshopee", "#shopeebrasil", "#amazonfinds", "#mercadolivre",
    "#dicadeeconomia", "#comatlantico", "#achadinhos",
)
IG_HASHTAG_COUNT = max(1, min(int(_num_env("IG_HASHTAG_COUNT", 3)),
                              len(IG_HASHTAGS)))

# Cupons do Mercado Livre: quantos posts novos por ciclo e pausa entre eles.
CUPOM_POSTS_PER_CYCLE = max(1, int(_num_env("CUPOM_POSTS_PER_CYCLE", 3)))
CUPOM_DELAY = _num_env("CUPOM_DELAY", 5)

# Canais parceiros: fila e publicação de 3 ofertas a cada 30 min.
CHANNEL_BATCH_SIZE = max(1, int(_num_env("CHANNEL_BATCH_SIZE", 3)))
CHANNEL_BATCH_INTERVAL = max(60, int(_num_env("CHANNEL_BATCH_INTERVAL", 1800)))
CHANNEL_POST_DELAY = _num_env("CHANNEL_POST_DELAY", 8)
CHANNEL_QUEUE_MAX = max(10, int(_num_env("CHANNEL_QUEUE_MAX", 100)))

CONTROL_LOCK = threading.Lock()
CONTROL = {
    "channels": True,
    "sheet": True,
    "scrape": True,
    "coupons": True,
    "instagram": True,
    "telegram": True,
}

PANEL_STATE = {"last_telegram": 0.0, "last_instagram": 0.0, "last_listener": 0.0}

RUN_LOCK = threading.Lock()
RUN_NOW = {"telegram": False, "instagram": False}


def control_snapshot():
    with CONTROL_LOCK:
        return dict(CONTROL)


def control_enabled(name):
    with CONTROL_LOCK:
        return bool(CONTROL.get(name, True))


def apply_control_flags(flags):
    if not isinstance(flags, dict):
        return
    with CONTROL_LOCK:
        for name in CONTROL:
            value = flags.get(name)
            if isinstance(value, bool):
                CONTROL[name] = value


def request_run(cycle):
    with RUN_LOCK:
        if cycle in RUN_NOW:
            RUN_NOW[cycle] = True


def take_run(cycle):
    with RUN_LOCK:
        if RUN_NOW.get(cycle):
            RUN_NOW[cycle] = False
            return True
    return False


SEEN_FILE = BASE_DIR / "seen.json"
IG_SEEN_FILE = BASE_DIR / "ig_seen.json"
VITRINE_FILE = BASE_DIR / "vitrine.json"
VITRINE_LOCK = threading.Lock()
IG_QUEUE_FILE = BASE_DIR / "ig_queue.json"
IG_QUEUE_LOCK = threading.RLock()
OFFSET_FILE = BASE_DIR / "telegram_offset.json"
STORES_FILE = BASE_DIR / "lojas.json"
CUPONS_FILE = BASE_DIR / "cupons_enviados.json"
CHANNEL_QUEUE_FILE = BASE_DIR / "channel_queue.json"
CHANNEL_STATE_FILE = BASE_DIR / "channel_state.json"
CHANNEL_LOCK = threading.RLock()
TEMPLATE_FILE = BASE_DIR / "img" / "template.png"

# Geometria do template, medida em img/template.png (1024x217).
# O quadro de vidro a direita e onde o preco deve ficar.
TEMPLATE_W, TEMPLATE_H = 1024, 217
TEMPLATE_BOX = (576, 28, 951, 183)   # borda externa do quadro
TEMPLATE_BOX_PAD = 10                # margem de seguranca dentro do quadro
# Card final: produto em cima, banner com o preco embaixo (opcao C).
ART_W, ART_H = 1080, 1350
# Margem da foto do produto: quanto MENOR, mais o fundo vira so borda.
ART_BORDER = 34
# Fator entre as medidas do template (1024 de largura) e o card final (1080).
_TPL_SCALE = ART_W / TEMPLATE_W

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.mercadolivre.com.br/",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}

BLOCKED_SOURCES = set()


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def proxy_health():
    """Testa o proxy uma vez por ciclo. Morto = fallback para conexao direta.

    Sem proxy o ML ainda funciona no IP residencial do celular. Com proxy
    quebrado TODAS as requisicoes falhavam, ate a leitura da planilha do
    Google Sheets -- que nem precisa de proxy. Por isso, proxy morto e
    desligado em vez de só avisado.
    """
    global PROBE_AT, PROXIES
    if not PROXIES:
        return False
    if time.time() - PROBE_AT < 600:
        return PROBE_STATE["ok"]
    PROBE_AT = time.time()
    try:
        resp = requests.get("https://api.ipify.org?format=json", proxies=PROXIES, timeout=15)
        ip = resp.json().get("ip") if resp.status_code == 200 else None
        if ip:
            PROBE_STATE["ok"] = True
            PROBE_STATE["msg"] = f"proxy ativo, IP de saida {ip}"
            log(f"🌐 {PROBE_STATE['msg']}")
        else:
            PROBE_STATE["ok"] = False
            PROBE_STATE["msg"] = f"proxy respondeu HTTP {resp.status_code}"
    except Exception as exc:
        PROBE_STATE["ok"] = False
        PROBE_STATE["msg"] = f"proxy indisponivel ({type(exc).__name__})"
    if not PROBE_STATE["ok"]:
        log(f"⚠️ {PROBE_STATE['msg']} — PROXY desligado. Seguindo com a conexão direta: "
            f"Mercado Livre continua funcionando, Shopee pode bloquear.")
        PROXIES = None
    return PROBE_STATE["ok"]


def http_get(url, headers=None, timeout=20, referer=None):
    """GET com impersonação de navegador e proxy opcional (necessário no ML/Shopee)."""
    hdrs = dict(HEADERS)
    if headers:
        hdrs.update(headers)
    if referer:
        hdrs["Referer"] = referer
    try:
        if HAVE_CURL_CFFI:
            resp = cureq.get(url, headers=hdrs, impersonate="chrome131", timeout=timeout,
                             proxies=PROXIES)
        else:
            resp = requests.get(url, headers=hdrs, timeout=timeout, proxies=PROXIES)
        blocked = ("account-verification" in resp.text[:2000]
                   or "suspicious-traffic" in resp.text[:2000])
        if blocked or resp.status_code in (403, 429, 520):
            host = urllib.parse.urlparse(url).netloc
            if host not in BLOCKED_SOURCES:
                BLOCKED_SOURCES.add(host)
                log(f"🚫 {host} bloqueou o acesso (HTTP {resp.status_code}"
                    f"{', pagina de verificacao' if blocked else ''}).")
        return resp
    except Exception as exc:
        if PROXIES:
            PROBE_STATE["ok"] = False
            PROBE_STATE["msg"] = f"proxy falhou: {type(exc).__name__}"
        log(f"⚠️  Falha de rede em {url[:60]}: {type(exc).__name__}")
        return None


def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, type(default)):
                    return data
    except Exception:
        pass
    return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"⚠️ Não foi possível salvar {Path(path).name}: {exc}")


def parse_money(text):
    """Converte '1.234,56' / '1234.56' / 'R$ 89,90' em float."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    raw = str(text).strip()
    if not raw:
        return None
    raw = re.sub(r"[^\d.,]", "", raw.replace("\u00a0", " ").replace(" ", ""))
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    else:
        parts = raw.split(".")
        if len(parts) > 2:
            raw = "".join(parts)
        elif len(parts) == 2 and len(parts[1]) == 3:
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def brl(value):
    """Formata float no padrão brasileiro (1.234,56)."""
    if value is None:
        return ""
    formatted = f"{float(value):,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


BOT_WALL_MARKERS = ("account-verification", "suspicious-traffic", "recaptcha",
                    "/gz/", "/captcha", "challenge.oray")
URL_CACHE = {}

# Tags de afiliado que podem ja estar no link de origem (de outro afiliado).
ML_OWN_TAGS = ("matt_word", "matt_tool", "matt", "forceInApp", "ref")
SHOPEE_OWN_TAGS = ("smtt", "sp_atk", "is_from_webapp")
AMAZON_OWN_TAGS = ("tag", "ascsubtag", "th", "psc")

# Resolucao de link de LOJA do ML: /social/ ignora a tag, entao precisa achar
# o produto de verdade dentro do catalogo da loja.
RESOLVE_STORE_LINKS = env("RESOLVE_STORE_LINKS", "1").strip().lower() not in ("0", "false", "nao", "não")
STOP_WORDS = frozenset({
    "frete", "e", "do", "em", "original", "kit", "o", "das", "de", "a", "dos", "da",
    "oferta", "peca", "peças", "r$", "gratis", "grátis", "promocao", "promoção",
    "promo", "para", "com", "unidades", "un",
})
_ACCENTS = {ord(c): None for c in "áàâãäéêíìîóôõöúüçÁÀÂÃÄÉÊÍÌÎÓÔÕÖÚÜÇ"}
ML_PRODUCT_RE = re.compile(r"MLB-?(\d{6,})(?:-(.+))?", re.IGNORECASE)


def _is_bot_wall(text):
    low = (text or "").lower()
    return any(marker in low for marker in BOT_WALL_MARKERS)


def expand_url(url):
    """Resolve encurtadores (meli.la, shope.ee, amzn.to, a.co).

    IMPORTANTE: encurtador nao responde a HEAD. O meli.la devolve 405 e o
    shope.ee cai em pagina de erro; so o GET segue o redirecionamento.
    Por isso a ordem e GET primeiro e HEAD so como ultimo recurso.
    """
    if not url:
        return url
    cached = URL_CACHE.get(url)
    if cached and time.time() - cached[0] < 900:
        return cached[1]

    client = cureq if HAVE_CURL_CFFI else requests
    attempts = (("get", None), ("get", PROXIES), ("head", PROXIES))
    resolved = None
    for method, proxy in attempts:
        if proxy is None and PROXIES:
            continue  # com proxy configurado, nem tenta a conexao direta
        call = client.head if method == "head" else client.get
        try:
            resp = call(url, allow_redirects=True, timeout=10, stream=True,
                        headers={"User-Agent": BROWSER_UA}, proxies=proxy)
            final = resp.url or url
            try:
                resp.close()
            except Exception:
                pass
            if _is_bot_wall(final):
                continue
            if final != url and final.startswith("http"):
                resolved = final
                break
        except Exception:
            continue

    resolved = resolved or url
    URL_CACHE[url] = (time.time(), resolved)
    if resolved != url:
        log(f"🔗 Link expandido: {url[:42]} -> {resolved[:72]}")
    return resolved


def strip_params(url, keys):
    """Remove params de afiliado que ja estavam no link de origem."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    for key in keys:
        params.pop(key, None)
    query = urllib.parse.urlencode(params, doseq=True)
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)
    )


def is_store_link(url):
    """Link de LOJA do ML (/social/, /loja/, /store/) ignora a tag de afiliado."""
    low = (url or "").lower()
    return any(p in low for p in ("/social/", "/loja/", "/store/", "linksbrazil"))


def _keywords(text):
    """Palavras-chave do titulo, sem acento e sem palavra de parada."""
    clean = (text or "").lower().translate(_ACCENTS)
    return {w for w in re.findall(r"[a-z0-9]{3,}", clean) if w not in STOP_WORDS}


def _ml_price(card):
    """Preco atual de um card da listagem. Recebe o ELEMENTO, nao o texto."""
    if card is None:
        return None
    try:
        el = card.select_one(".andes-money-amount__fraction, .poly-price__current")
        if not el:
            return None
        frac = el.get_text(strip=True).replace(".", "").replace(",", "")
        cents_el = card.select_one(".andes-money-amount__cents")
        cents = cents_el.get_text(strip=True).replace(",", ".") if cents_el else "00"
        return parse_money(f"{frac}.{cents}")
    except Exception:
        return None


def _ml_product_url(href):
    """Link canonico de produto /<slug>/p/MLB<id>, preservando os params do ML."""
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = "https://www.mercadolivre.com.br" + href
    match = ML_PRODUCT_RE.search(href)
    if not match:
        return None
    catalog = match.group(1)
    slug = re.sub(r"[^a-z0-9-]+", "-", (match.group(2) or "produto").lower()).strip("-")
    slug = (slug[:60] or "produto")
    parsed = urllib.parse.urlparse(href)
    url = f"https://www.mercadolivre.com.br/{slug}/p/MLB{catalog}"
    if parsed.query:
        # preserva o que o proprio ML usa (pdp_filters, searchVariation...)
        # mas joga fora QUALQUER rastreamento de afiliado, inclusive matt_*
        keep = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()
                if k not in ML_OWN_TAGS and not k.lower().startswith("matt")}
        if keep:
            url = append_query(url, keep)
    return url


def store_nome(url):
    """Extrai o nome da loja de uma URL /social/<loja>."""
    m = re.search(r"mercadolivre\.com\.br/social/([^/?#]+)", url or "", re.I)
    return m.group(1).strip("/").lower() if m else (url or "?")


def store_catalog(store_url):
    """Le o catalogo da loja (/social/user) e devolve [{title, price, url, image}]."""
    if not store_url:
        return []
    cache_key = "cat::" + strip_params(store_url, list(ML_OWN_TAGS))
    cached = URL_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    resp = browser_get(store_url, wait=2)
    items = []
    if resp is not None and resp.status_code == 200 and not _is_bot_wall(resp.text[:3000]):
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select(".poly-card"):
            try:
                anchor = card.select_one("a.poly-card__title-anchor, h2 a[href], a[href]")
                if not anchor:
                    continue
                href = (anchor.get("href") or "").split("#")[0]
                product_url = _ml_product_url(href)
                if not product_url:
                    continue
                title_el = card.select_one(".poly-component__title, h2")
                title = title_el.get_text(strip=True) if title_el else anchor.get("title", "")
                price = _ml_price(card)
                img = card.select_one("img")
                image = ""
                if img:
                    image = (img.get("data-src") or img.get("data-zoom") or img.get("src") or "")
                if title and price:
                    items.append({"title": title, "price": price,
                                  "url": product_url, "image": image,
                                  "loja": store_nome(store_url)})
            except Exception:
                continue
    URL_CACHE[cache_key] = (time.time(), items)
    nome = store_nome(store_url)
    log(f"📦 Catálogo da loja {nome}: {len(items)} produto(s)")
    return items


def resolve_store_link(store_url, price=None, title=None):
    """Acha o produto da loja que bate com o preco/titulo da oferta.

    Sem isso o link encurtado leva o visitante para a LOJA de outro afiliado e
    a sua tag nao e creditada - por isso a busca.
    """
    if not RESOLVE_STORE_LINKS:
        return None
    items = store_catalog(store_url)
    if not items:
        return None

    wanted = _keywords(title)
    best, best_score = None, 0.0
    for item in items:
        words = _keywords(item.get("title"))
        title_score = 0.0
        if wanted and words:
            common = len(wanted & words)
            if common:
                title_score = common / max(len(wanted), 1)

        price_ok = False
        if price and item.get("price"):
            price_ok = abs(item["price"] - price) / price <= 0.08   # 8% de folga

        if price_ok:
            score = 2.0 + title_score          # preco manda; titulo desempata
        elif title_score >= 0.5:
            score = 2.0 * title_score          # so titulo: 100% de match aprova
        else:
            continue
        if score > best_score:
            best, best_score = item, score

    if best is None or best_score < 2:
        return None
    if price and best.get("price"):
        log(f"🔗 Link de loja resolvido para o produto: {best['title'][:50]} "
            f"(R$ {brl(best['price'])} | bateu {best_score:.2f})")
    else:
        log(f"🔗 Link de loja resolvido por título: {best['title'][:60]}")
    return best


# --------------------------------------------------------------------------
# Links de afiliado
# --------------------------------------------------------------------------

def clean_params(url, drop_keys):
    """Remove as chaves de afiliado existentes e devolve apenas os params de tracking."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    for key in drop_keys:
        params.pop(key, None)
    return parsed, params


def append_query(url, tracking):
    """Acrescenta params de afiliado preservando os que já existiam na URL."""
    parsed, params = clean_params(url, list(tracking.keys()))
    for key, value in tracking.items():
        params[key] = [value]
    query = urllib.parse.urlencode(params, doseq=True)
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)
    )


MARKETPLACES = ("mercadolivre", "mercadolibre", "meli.la", "shopee", "shope.ee",
                "amazon", "amzn.to", "a.co", "magazineluiza", "buscape", "submarino")


def is_product_url(url):
    """True se o link for de um marketplace (ignora t.me, instagram, etc.)."""
    return any(domain in url.lower() for domain in MARKETPLACES)


SHORT_LINK_RE = re.compile(
    r"https?://(?:meli\.la|mercadolivre\.com(?:\.br)?/sec|shope\.ee|"
    r"s\.shopee\.com(?:\.br)?|amzn\.to|a\.co)/[^\s\"'<>\\]+",
    re.I,
)
AMAZON_ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|d)/([A-Z0-9]{10})", re.I)


def _short_link_from_text(text):
    if not text:
        return ""
    text = str(text).replace("\\/", "/")
    match = SHORT_LINK_RE.search(text)
    return match.group(0).rstrip(".,);") if match else ""


def _extract_short_link(payload):
    """Procura um link curto de afiliado em qualquer lugar da resposta."""
    if isinstance(payload, dict):
        for key in ("shortUrl", "short_url", "shortLink", "short_link",
                    "link", "url", "permalink"):
            value = payload.get(key)
            if isinstance(value, str):
                found = _short_link_from_text(value)
                if found:
                    return found
        for value in payload.values():
            found = _extract_short_link(value)
            if found:
                return found
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            found = _extract_short_link(value)
            if found:
                return found
    elif isinstance(payload, str):
        return _short_link_from_text(payload)
    return ""


def _normalize_affiliate_url(url, store):
    expanded = expand_url(url)
    if expanded and expanded != url:
        url = expanded
    if store == "ml":
        return strip_params(url, list(ML_OWN_TAGS))
    if store == "shopee":
        return strip_params(url, list(SHOPEE_OWN_TAGS))
    if store == "amazon":
        return strip_params(url, list(AMAZON_OWN_TAGS))
    return url


def _is_short_affiliate_url(url):
    return bool(re.match(
        r"https?://(?:meli\.la|shope\.ee|s\.shopee\.com(?:\.br)?|amzn\.to|a\.co)/",
        url or "", re.I))


def _short_input_error(store, url):
    if not _is_short_affiliate_url(url):
        return None
    msg = (f"não foi possível expandir o link curto de origem ({url[:60]}) "
           f"— gere o link a partir da URL do produto")
    _set_generator_state(store, False, msg)
    return None, msg


def _link_cache_get(key):
    cache = load_json(LINK_GEN_CACHE_FILE, {})
    entry = cache.get(key)
    if not isinstance(entry, dict):
        return ""
    try:
        fresh = time.time() - float(entry.get("ts", 0)) < LINK_GEN_CACHE_TTL
    except (TypeError, ValueError):
        fresh = False
    link = entry.get("link") if fresh else ""
    return link if isinstance(link, str) else ""


def _link_cache_set(key, link):
    cache = load_json(LINK_GEN_CACHE_FILE, {})
    cache[key] = {"link": link, "ts": int(time.time())}
    if len(cache) > 300:
        for old in list(cache)[:-300]:
            cache.pop(old, None)
    save_json(LINK_GEN_CACHE_FILE, cache)


def _set_generator_state(store, ok, msg):
    GENERATOR_STATE[store] = {"ok": ok, "msg": msg[:300]}


def _ml_dom_link(url):
    script = r"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const scan = () => {
      for (const node of document.querySelectorAll('textarea, input')) {
        const val = (node.value || '').trim();
        if (/meli\.la|mercadolivre\.com.*\/sec\//.test(val)) return val;
      }
      for (const a of document.querySelectorAll('a[href]')) {
        if (/meli\.la|mercadolivre\.com.*\/sec\//.test(a.href)) return a.href;
      }
      return '';
    };
    let link = scan();
    if (!link) {
      const btn = document.querySelector(
        '#P0-2, [data-testid="affiliate-link"], button[aria-label*="afiliad" i]');
      if (btn) {
        btn.click();
        await sleep(2500);
        link = scan();
      }
    }
    return link;
    """
    result = browser_eval(url, script, wait=3, timeout=LINK_GEN_TIMEOUT,
                          await_promise=True)
    if not result or not result.get("ok"):
        return ""
    return _short_link_from_text(result.get("value"))


def generate_ml_affiliate_link(url):
    """Gera o link curto no portal de afiliados do Mercado Livre."""
    if not ML_AFFILIATE_TAG:
        msg = "ML_AFFILIATE_TAG/ML_MATT_WORD ausente no .env"
        _set_generator_state("ml", False, msg)
        return None, msg
    url = _normalize_affiliate_url(url, "ml")
    short_error = _short_input_error("ml", url)
    if short_error:
        return short_error
    if is_store_link(url):
        msg = f"link de LOJA do ML ({urllib.parse.urlparse(url).path}) não gera comissão"
        _set_generator_state("ml", False, msg)
        return None, msg

    script = """
    const target = %s;
    const tag = %s;
    const meta = document.querySelector('meta[name="csrf-token"], meta[name="_csrf"]');
    const cookie = (document.cookie.match(/(?:^|; )_csrf=([^;]+)/) || [])[1] || '';
    const csrf = (meta && meta.content) || decodeURIComponent(cookie);
    const endpoint = 'https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink';
    const attempts = [];
    const bodies = [
      {urls: [target], tag: tag},
      {url: target, tag: tag}
    ];
    for (const body of bodies) {
      try {
        const resp = await fetch(endpoint, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-csrf-token': csrf
          },
          body: JSON.stringify(body)
        });
        const text = await resp.text();
        attempts.push({status: resp.status, text: text.slice(0, 5000)});
        if (resp.ok) return {ok: true, attempts: attempts};
      } catch (e) {
        attempts.push({status: 0, text: String(e)});
      }
    }
    return {ok: false, attempts: attempts};
    """ % (json.dumps(url, ensure_ascii=False), json.dumps(ML_AFFILIATE_TAG))

    result = browser_eval(ML_LINKBUILDER_URL, script, wait=2,
                          timeout=LINK_GEN_TIMEOUT, await_promise=True)
    if result and result.get("ok"):
        value = result.get("value")
        link = _extract_short_link(value)
        if link:
            _set_generator_state("ml", True, f"link gerado para {url[:60]}")
            return link, None
        detail = ""
        if isinstance(value, dict) and value.get("attempts"):
            try:
                detail = str(value["attempts"][0].get("text", ""))[:200]
            except Exception:
                detail = ""
        msg = f"createLink não devolveu link curto {detail}".strip()
    else:
        msg = (result or {}).get("error") or "navegador indisponível"

    link = _ml_dom_link(url)
    if link:
        _set_generator_state("ml", True, "link gerado pela pagina do produto")
        return link, None
    _set_generator_state("ml", False, msg)
    return None, f"ML: {msg}"


def _shopee_authorization(body, timestamp=None):
    """Header Authorization da Open API (SHA256 appId+ts+body+secret)."""
    timestamp = int(timestamp or time.time())
    raw_signature = f"{SHOPEE_APP_ID}{timestamp}{body}{SHOPEE_SECRET}"
    signature = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
    header = (f"SHA256 Credential={SHOPEE_APP_ID}, Timestamp={timestamp}, "
              f"Signature={signature}")
    return timestamp, header


def generate_shopee_affiliate_link(url):
    """Gera o link curto pela Open API oficial da Shopee."""
    if not SHOPEE_APP_ID or not SHOPEE_SECRET:
        msg = "SHOPEE_APP_ID/SHOPEE_SECRET ausentes no .env"
        _set_generator_state("shopee", False, msg)
        return None, msg
    url = _normalize_affiliate_url(url, "shopee")
    short_error = _short_input_error("shopee", url)
    if short_error:
        return short_error
    query = ('mutation { generateShortLink(input: {originUrl: "%s"}) '
             '{ shortLink } }' % url.replace('"', '\\"'))
    body = json.dumps({"query": query}, ensure_ascii=False, separators=(",", ":"))
    _, authorization = _shopee_authorization(body)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": authorization,
    }
    try:
        resp = requests.post(SHOPEE_API_URL, data=body.encode("utf-8"),
                             headers=headers, timeout=LINK_GEN_TIMEOUT)
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        _set_generator_state("shopee", False, msg)
        return None, f"Shopee: {msg}"
    if resp.status_code != 200:
        msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
        _set_generator_state("shopee", False, msg)
        return None, f"Shopee: {msg}"
    try:
        data = resp.json()
    except Exception:
        data = resp.text
    link = _extract_short_link(data)
    if link:
        _set_generator_state("shopee", True, f"link gerado para {url[:60]}")
        return link, None
    msg = f"resposta sem shortLink: {str(data)[:200]}"
    _set_generator_state("shopee", False, msg)
    return None, f"Shopee: {msg}"


def generate_shopee_portal_link(url):
    """Gera o link pela Open API; portal logado entra como reserva.

    A Open API não passa pelo anti-bot do site/portal. O portal só é usado
    quando não há SHOPEE_APP_ID/SHOPEE_SECRET ou quando a API falha.
    """
    url = _normalize_affiliate_url(url, "shopee")
    short_error = _short_input_error("shopee", url)
    if short_error:
        return short_error
    api_error = None
    if SHOPEE_APP_ID and SHOPEE_SECRET:
        link, api_error = generate_shopee_affiliate_link(url)
        if link:
            return link, None
        log(f"↪️ Shopee Open API falhou ({api_error}); tentando o portal logado.")
    if not BROWSER_SCRAPING:
        if SHOPEE_APP_ID and SHOPEE_SECRET:
            return None, api_error or "Open API indisponível"
        return generate_shopee_affiliate_link(url)

    script = r"""
    const target = __TARGET__;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
    const text = (el) => norm(el && (el.innerText || el.textContent || ""));
    const visible = (el) => {
      if (!el) return false;
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden";
    };
    const setValue = (el, value) => {
      const proto = el.tagName === "TEXTAREA"
        ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      setter.call(el, value);
      el.dispatchEvent(new Event("input", {bubbles: true}));
      el.dispatchEvent(new Event("change", {bubbles: true}));
    };
    const readLink = (root) => {
      if (!root) return "";
      for (const node of root.querySelectorAll("textarea, input")) {
        for (const part of String(node.value || "").split(/\s+/)) {
          if (/^https?:\/\/(?:shope\.ee|s\.shopee\.com\.br)\//i.test(part)) {
            return part.replace(/[.,);]+$/, "");
          }
        }
      }
      const m = text(root).match(
        /https?:\/\/(?:shope\.ee|s\.shopee\.com\.br)\/[^\s"'<>]+/i);
      return m ? m[0].replace(/[.,);]+$/, "") : "";
    };
    const api = async () => {
      try {
        const resp = await fetch("/api/v3/gql?q=batchCustomLink", {
          method: "POST",
          credentials: "include",
          headers: {"Content-Type": "application/json", "Accept": "application/json"},
          body: JSON.stringify({
            operationName: "batchGetCustomLink",
            query: "query batchGetCustomLink($linkParams: [CustomLinkParam!], $sourceCaller: SourceCaller){ batchCustomLink(linkParams: $linkParams, sourceCaller: $sourceCaller){ shortLink longLink failCode } }",
            variables: {
              linkParams: [{originalLink: target, advancedLinkParams: null}],
              sourceCaller: "CUSTOM_LINK_CALLER"
            }
          })
        });
        const data = await resp.json();
        const item = ((data.data || {}).batchCustomLink || [])[0] || {};
        return item.shortLink || item.longLink || "";
      } catch (e) {
        return "";
      }
    };

    if (/\/auth(?:\/|$)/.test(location.pathname)) {
      return {ok: false, error: "login necessário em " + location.href,
              url: location.href, preview: text(document.body).slice(0, 400)};
    }

    let ta = null;
    for (let i = 0; i < 24 && !ta; i++) {
      ta = document.querySelector(".custom-textarea textarea, textarea");
      if (!ta) await sleep(500);
    }
    if (ta) {
      ta.focus();
      setValue(ta, target);
      await sleep(400);
      const submit = Array.from(
        document.querySelectorAll('button[type="submit"], button, [role="button"]')
      ).find((b) => visible(b) && /^obter link$/i.test(text(b)));
      if (submit) {
        submit.click();
        for (let i = 0; i < 40; i++) {
          await sleep(500);
          const modal = Array.from(
            document.querySelectorAll(".success-modal, .ant-modal-content")
          ).find(visible);
          if (modal) {
            const link = readLink(modal);
            if (link) return {ok: true, link: link, source: "portal"};
          }
        }
      }
    }

    const link = await api();
    if (link) return {ok: true, link: link, source: "api"};
    return {ok: false, error: "portal não devolveu link (login?)",
            url: location.href, preview: text(document.body).slice(0, 400)};
    """
    script = script.replace("__TARGET__", json.dumps(url, ensure_ascii=False))
    result = browser_eval(SHOPEE_CUSTOM_LINK_URL, script, wait=8,
                          timeout=max(120, LINK_GEN_TIMEOUT + 60))
    value = (result or {}).get("value") or {}
    link = value.get("link") if isinstance(value, dict) else ""
    if link:
        _set_generator_state("shopee", True, f"link gerado para {url[:60]}")
        return link, None

    detail = ""
    if isinstance(value, dict):
        detail = value.get("error") or value.get("preview") or ""
    if not detail:
        detail = (result or {}).get("error") or "navegador indisponível"
    portal_error = f"Shopee portal: {str(detail)[:200]}"
    fallback, api_error = generate_shopee_affiliate_link(url)
    if fallback:
        return fallback, None
    _set_generator_state("shopee", False, portal_error)
    return None, f"{portal_error}; {api_error or 'Open API indisponível'}"


def _amazon_asin(url):
    match = AMAZON_ASIN_RE.search(url or "")
    if match:
        return match.group(1).upper()
    match = re.search(r"[?&]asin=([A-Z0-9]{10})", url or "", re.I)
    return match.group(1).upper() if match else ""


def _amazon_dom_link(url):
    script = r"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const scan = () => {
      for (const node of document.querySelectorAll(
          '#amzn-ss-text-shortlink-textarea, #amzn-ss-shortlink-textarea, textarea, input')) {
        const val = (node.value || '').trim();
        if (/amzn\.to|a\.co/.test(val)) return val;
      }
      for (const a of document.querySelectorAll('a[href]')) {
        if (/amzn\.to|a\.co/.test(a.href)) return a.href;
      }
      return '';
    };
    let link = scan();
    if (!link) {
      const btn = document.querySelector(
        '#amzn-ss-get-link-button, #amzn-ss-text-link, [data-action="ss-get-link"]');
      if (btn) {
        btn.click();
        await sleep(2500);
        link = scan();
      }
    }
    return link;
    """
    result = browser_eval(url, script, wait=4, timeout=LINK_GEN_TIMEOUT,
                          await_promise=True)
    if not result or not result.get("ok"):
        return ""
    return _short_link_from_text(result.get("value"))


def generate_amazon_affiliate_link(url):
    """Gera o link curto no SiteStripe da Amazon."""
    if not AMAZON_TAG:
        msg = "AMAZON_TAG ausente no .env"
        _set_generator_state("amazon", False, msg)
        return None, msg
    url = _normalize_affiliate_url(url, "amazon")
    short_error = _short_input_error("amazon", url)
    if short_error:
        return short_error
    asin = _amazon_asin(url)
    canonical = f"https://www.amazon.com.br/dp/{asin}" if asin else url

    script = """
    const target = %s;
    const tag = %s;
    const mids = %s;
    const longUrl = target + '?tag=' + encodeURIComponent(tag)
      + '&linkCode=sl1&ref_=as_li_ss_tl';
    const attempts = [];
    for (const mid of mids) {
      const endpoint = '/associates/sitestripe/getShortUrl?longUrl='
        + encodeURIComponent(longUrl)
        + '&tag=' + encodeURIComponent(tag)
        + '&marketplaceId=' + encodeURIComponent(mid);
      try {
        const resp = await fetch(endpoint, {
          credentials: 'include',
          headers: {'Accept': 'application/json, text/plain, */*'}
        });
        const text = await resp.text();
        attempts.push({status: resp.status, mid: mid, text: text.slice(0, 5000)});
        if (resp.ok && (/amzn\\.to|a\\.co/.test(text))) {
          return {ok: true, attempts: attempts};
        }
      } catch (e) {
        attempts.push({status: 0, mid: mid, text: String(e)});
      }
    }
    return {ok: false, attempts: attempts};
    """ % (json.dumps(canonical, ensure_ascii=False),
           json.dumps(AMAZON_TAG),
           json.dumps([AMAZON_MARKETPLACE_ID, "526970", "12", ""]))

    result = browser_eval(AMAZON_HOME_URL, script, wait=2,
                          timeout=LINK_GEN_TIMEOUT, await_promise=True)
    if result and result.get("ok"):
        value = result.get("value")
        link = _extract_short_link(value)
        if link:
            _set_generator_state("amazon", True, f"link gerado para {canonical[:60]}")
            return link, None
        detail = ""
        if isinstance(value, dict) and value.get("attempts"):
            try:
                detail = str(value["attempts"][0].get("text", ""))[:200]
            except Exception:
                detail = ""
        msg = f"getShortUrl não devolveu link curto {detail}".strip()
    else:
        msg = (result or {}).get("error") or "navegador indisponível"

    link = _amazon_dom_link(canonical)
    if link:
        _set_generator_state("amazon", True, "link gerado pela pagina do produto")
        return link, None
    _set_generator_state("amazon", False, msg)
    return None, f"Amazon: {msg}"


def _store_of_url(url):
    """Loja dona do link, olhando só o HOST (evita 'a.co' dentro de magazineluiza.com)."""
    host = urllib.parse.urlparse(url or "").netloc.lower()
    host = host.split("@")[-1].split(":")[0]
    if "meli.la" in host or "mercadolivre" in host or "mercadolibre" in host:
        return "ml"
    if "shopee" in host or "shope.ee" in host:
        return "shopee"
    if "amazon" in host or "amzn.to" in host or host == "a.co" or host.endswith(".a.co"):
        return "amazon"
    return ""


def generate_affiliate_link(url, price=None, title=None):
    """Devolve (link_curto, erro). Nunca inventa um link com ?tag."""
    if not url:
        return None, "URL vazia"
    url = url.rstrip(".,)")
    store = _store_of_url(url)
    if store:
        url = expand_url(url)
        store = _store_of_url(url)

    if store == "ml":
        generator = generate_ml_affiliate_link
    elif store == "shopee":
        generator = generate_shopee_portal_link
    elif store == "amazon":
        generator = generate_amazon_affiliate_link
    else:
        return url, None

    cache_key = f"{store}:{url}"
    cached = _link_cache_get(cache_key)
    if cached:
        return cached, None

    if store == "ml" and is_store_link(url):
        item = resolve_store_link(url, price, title)
        if not item:
            msg = (f"link de LOJA do ML ({urllib.parse.urlparse(url).path}) "
                   f"sem produto equivalente — não gera comissão")
            _set_generator_state("ml", False, msg)
            return None, msg
        url = item["url"]

    link, error = generator(url)
    if link:
        _link_cache_set(cache_key, link)
        return link, None
    return None, error or f"{store}: falha ao gerar o link"


def affiliate_link(url, price=None, title=None):
    """Compatibilidade: devolve (link, aviso). `link` é None quando falhou."""
    link, error = generate_affiliate_link(url, price, title)
    return link, error or ""


# --------------------------------------------------------------------------
# Vercel Blob
# --------------------------------------------------------------------------

def upload_to_blob(file_path, remote_name, stable=True):
    """Sobe um arquivo para o Vercel Blob.

    `stable=True` manda `x-add-random-suffix: 0`, e isso e OBRIGATORIO para o
    vitrine.json: a pagina da bio tem o endereco fixo no HTML. Sem essa flag o
    blob cria um arquivo com sufixo aleatorio a cada upload
    (vitrine-A1b2C3.txt) e a pagina continua lendo o old vitrine.json para
    sempre.
    """
    if not BLOB_TOKEN or not Path(file_path).exists():
        return None
    try:
        with open(file_path, "rb") as fh:
            payload = fh.read()
        headers = {"Authorization": f"Bearer {BLOB_TOKEN}"}
        if stable:
            headers["x-add-random-suffix"] = "0"
        resp = requests.put(
            f"https://blob.vercel-storage.com/{remote_name}",
            data=payload,
            headers=headers,
            timeout=45,
        )
        if resp.status_code == 200:
            data = resp.json()
            url = data.get("url", "")
            # o blob devolve minusculo; a pagina usa a forma com maiusculas
            url = url.replace("rzd48c84t8k2zcdu", "rzd48c84T8k2zCDu")
            log(f"☁️ Blob: {remote_name} atualizado")
            return url
        log(f"⚠️ Blob: status {resp.status_code} ao enviar {remote_name}")
    except Exception as exc:
        log(f"⚠️ Blob: {exc}")
    return None


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

def tg_api(method, payload=None, files=None, timeout=60):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    try:
        if files:
            resp = requests.post(url, data=payload, files=files, timeout=timeout)
        else:
            resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code != 200:
            log(f"⚠️ Telegram {method}: {resp.status_code} {resp.text[:180]}")
            return None
        return resp.json().get("result")
    except Exception as exc:
        log(f"⚠️ Telegram {method}: {exc}")
        return None


def download_image(url, timeout=25):
    """Baixa a imagem localmente. O Telegram recusa CDNs que ele não consegue ler."""
    if not url or not str(url).lower().startswith(("http://", "https://")):
        return None
    try:
        resp = http_get(url, headers={"Accept": "image/*,*/*"}, timeout=timeout)
        if resp is None or resp.status_code != 200:
            return None
        data = resp.content
        if len(data) < 2000:
            return None
        content = (resp.headers.get("Content-Type") or "image/jpeg").lower()
        ext = ".png" if "png" in content else (".webp" if "webp" in content else ".jpg")
        path = BASE_DIR / f"img_{int(time.time()*1000)}{random.randint(100,999)}{ext}"
        path.write_bytes(data)
        return path
    except Exception:
        return None


def notify_admin(text):
    """Avisa o dono no privado (ADMIN_CHAT_ID). Silencioso se nao configurado."""
    chat_id = env("ADMIN_CHAT_ID")
    if not chat_id:
        return
    try:
        tg_api("sendMessage", {"chat_id": chat_id, "text": f"🤖 {text}"})
    except Exception:
        pass


def send_message(text, chat_id=None, photo_url=None, reply_to=None, reply_markup=None):
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN or not chat_id:
        log("⚠️ Token ou Chat ID do Telegram ausentes.")
        return False

    if photo_url:
        payload = {"chat_id": chat_id, "caption": text[:1024]}
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        if reply_markup:
            # TEM de ir como string JSON. No envio com arquivo o requests usa
            # multipart (data=) e um dict aninhado viraria texto com aspas
            # simples -> Telegram responde 400 e recusa a FOTO.
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

        local = download_image(photo_url)
        if local:
            try:
                with open(local, "rb") as fh:
                    result = tg_api("sendPhoto", payload,
                                    files={"photo": (local.name, fh)}, timeout=90)
            finally:
                Path(local).unlink(missing_ok=True)
            if result:
                return True
        else:
            result = tg_api("sendPhoto", dict(payload, photo=photo_url), timeout=90)
            if result:
                return True
        log("⚠️ Telegram recusou a foto; enviando apenas texto.")

    payload = {"chat_id": chat_id, "text": text}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return bool(tg_api("sendMessage", payload))


def send_document(path, chat_id=None, caption=""):
    """Envia um arquivo no Telegram (ex.: HTML de diagnóstico)."""
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN or not chat_id:
        log("⚠️ Token ou Chat ID do Telegram ausentes.")
        return False
    path = Path(path)
    try:
        with open(path, "rb") as fh:
            result = tg_api("sendDocument",
                            {"chat_id": chat_id, "caption": caption[:1024]},
                            files={"document": (path.name, fh)}, timeout=120)
        return bool(result)
    except Exception as exc:
        log(f"⚠️ Telegram sendDocument: {exc}")
        return False


def get_chat_name(chat_id):
    result = tg_api("getChat", {"chat_id": chat_id}, timeout=15)
    return result.get("title") or result.get("username") or str(chat_id) if result else str(chat_id)


def check_credentials():
    if not TELEGRAM_TOKEN:
        log("❌ TELEGRAM_TOKEN ausente no .env — o bot não pode funcionar.")
        return False
    me = tg_api("getMe", timeout=20)
    if not me:
        log("❌ Token do Telegram recusado pela API.")
        return False
    log(f"✅ Telegram conectado como @{me.get('username')}")

    if TELEGRAM_CHAT_ID:
        log(f"✅ Canal de destino: {get_chat_name(TELEGRAM_CHAT_ID)}")
    if SOURCE_CHANNELS:
        log(f"👂 Canais monitorados: {', '.join(SOURCE_CHANNELS)}")
    return True


# --------------------------------------------------------------------------
# Instagram
# --------------------------------------------------------------------------

def resolve_ig_user_id():
    """Corrige automaticamente o IG_USER_ID quando o .env está com o valor errado."""
    global IG_USER_ID
    if not IG_ACCESS_TOKEN:
        log("⚠️ IG_ACCESS_TOKEN ausente — Instagram desativado.")
        return False
    try:
        resp = requests.get(
            f"https://graph.instagram.com/v18.0/me",
            params={"fields": "id,username", "access_token": IG_ACCESS_TOKEN},
            timeout=25,
        )
        data = resp.json()
    except Exception as exc:
        log(f"⚠️ Instagram: {exc}")
        return False

    if "id" not in data:
        log(f"❌ Token do Instagram inválido: {str(data)[:180]}")
        return False

    real_id = data["id"]
    log(f"✅ Instagram conectado como @{data.get('username')} (id {real_id})")
    if not IG_USER_ID or str(IG_USER_ID) != str(real_id):
        if IG_USER_ID:
            log(f"⚠️ IG_USER_ID do .env ({IG_USER_ID}) está incorreto. Usando o id real {real_id}.")
        else:
            log(f"⚠️ IG_USER_ID ausente no .env. Adicione: IG_USER_ID={real_id}")
        IG_USER_ID = real_id
    return True


def ig_hashtags():
    """Sorteia as hashtags da legenda (sem repetir)."""
    return " ".join(random.sample(IG_HASHTAGS, IG_HASHTAG_COUNT))


def post_instagram_comment(media_id, message):
    """Publica o primeiro comentário do post (usado para o link da oferta)."""
    if not IG_ACCESS_TOKEN or not media_id or not message:
        return False
    try:
        resp = requests.post(
            f"https://graph.instagram.com/v18.0/{media_id}/comments",
            data={"message": message, "access_token": IG_ACCESS_TOKEN},
            timeout=30,
        ).json()
        if "id" in resp:
            log(f"💬 Instagram: link no primeiro comentário ({resp['id']}).")
            return True
        log(f"⚠️ Instagram comentário: {str(resp)[:220]}")
    except Exception as exc:
        log(f"⚠️ Instagram comentário: {type(exc).__name__}: {exc}")
    return False


def instagram_diagnostico():
    """Confere token e permissão de comentários sem publicar nada."""
    if not IG_ACCESS_TOKEN:
        return "❌ IG_ACCESS_TOKEN ausente no .env."
    base = "https://graph.instagram.com/v18.0"
    linhas = []
    try:
        me = requests.get(
            base + "/me",
            params={"fields": "id,username", "access_token": IG_ACCESS_TOKEN},
            timeout=25,
        ).json()
    except Exception as exc:
        return f"❌ Instagram: {type(exc).__name__}: {exc}"
    if not isinstance(me, dict) or "error" in me:
        erro = (me or {}).get("error") or me
        return f"❌ Token inválido: {str(erro)[:220]}"
    linhas.append(f"✅ Token válido: @{me.get('username')} (id {me.get('id')})")

    media_id = ""
    try:
        media = requests.get(
            base + "/me/media",
            params={"fields": "id,timestamp", "limit": 1,
                    "access_token": IG_ACCESS_TOKEN},
            timeout=25,
        ).json()
        dados = (media or {}).get("data") or []
        if dados:
            media_id = dados[0].get("id") or ""
            linhas.append(f"🖼️ Último post: {media_id} ({dados[0].get('timestamp', '')})")
    except Exception as exc:
        linhas.append(f"⚠️ Não consegui ler a mídia: {type(exc).__name__}: {exc}")

    if not media_id:
        linhas.append("⚠️ Sem post para testar a leitura de comentários.")
        return "\n".join(linhas)

    try:
        resp = requests.get(
            f"{base}/{media_id}/comments",
            params={"fields": "id", "limit": 1, "access_token": IG_ACCESS_TOKEN},
            timeout=25,
        ).json()
    except Exception as exc:
        linhas.append(f"❌ Comentários: {type(exc).__name__}: {exc}")
        return "\n".join(linhas)

    erro = (resp or {}).get("error") if isinstance(resp, dict) else None
    if erro:
        linhas.append(f"❌ Comentários: código {erro.get('code')} — "
                      f"{erro.get('message')}")
        linhas.append("   Falta a permissão instagram_business_manage_comments "
                      "no app/token.")
    else:
        linhas.append("✅ Autorização de comentários OK (leitura funcionou).")
    return "\n".join(linhas)


def post_to_instagram(image_url, caption, comment=None):
    if not IG_ACCESS_TOKEN or not IG_USER_ID or not image_url:
        log("⏭️ Instagram ignorado: sem token, id ou imagem pública.")
        return False
    try:
        container = requests.post(
            f"https://graph.instagram.com/v18.0/{IG_USER_ID}/media",
            data={"image_url": image_url, "caption": caption, "access_token": IG_ACCESS_TOKEN},
            timeout=60,
        ).json()
        if "id" not in container:
            log(f"❌ Instagram container: {str(container)[:220]}")
            return False

        time.sleep(6)
        published = requests.post(
            f"https://graph.instagram.com/v18.0/{IG_USER_ID}/media_publish",
            data={"creation_id": container["id"], "access_token": IG_ACCESS_TOKEN},
            timeout=60,
        ).json()
        if "id" in published:
            log(f"✅ Instagram publicado: {published['id']}")
            if comment:
                post_instagram_comment(published["id"], comment)
            return True
        log(f"❌ Instagram publish: {str(published)[:220]}")
    except Exception as exc:
        log(f"⚠️ Instagram: {exc}")
    return False


# --------------------------------------------------------------------------
# Arte personalizada
# --------------------------------------------------------------------------

FONT_BOLD = [
    r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\calibrib.ttf",
    r"C:\Windows\Fonts\DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_REGULAR = [
    r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size, bold=True):
    for path in (FONT_BOLD if bold else FONT_REGULAR):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def gradient(size, top=(6, 16, 44), bottom=(14, 34, 78)):
    """Fundo azul-marinho escuro. Sem roxo: o fundo é só moldura do produto."""
    width, height = size
    ramp = Image.new("RGBA", (1, height))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        ramp.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)) + (255,))
    return ramp.resize(size, Image.Resampling.BILINEAR)


def text_block(draw, xy, text, font, fill, anchor_center_x=None, stroke=0, stroke_fill=(0, 0, 0, 255)):
    if anchor_center_x is not None:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        xy = (anchor_center_x - (bbox[2] - bbox[0]) / 2 - bbox[0], xy[1])
    draw.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return bbox[3] - bbox[1]


def _fit_font(draw, text, max_w, max_h, start, bold=True, minimum=16):
    """Maior tamanho de fonte em que `text` cabe dentro de max_w x max_h."""
    size = start
    while size > minimum:
        font = load_font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_w and (bbox[3] - bbox[1]) <= max_h:
            return font, bbox
        size -= 2
    font = load_font(minimum, bold=bold)
    return font, draw.textbbox((0, 0), text, font=font)


def _draw_price_in_box(draw, box, preco, preco_original):
    """Escreve o preco DENTRO do quadro de vidro. box = (x1, y1, x2, y2)."""
    bx1, by1, bx2, by2 = box
    inner_w = (bx2 - bx1) - 2 * TEMPLATE_BOX_PAD * _TPL_SCALE
    inner_h = (by2 - by1) - 2 * TEMPLATE_BOX_PAD * _TPL_SCALE
    cx = (bx1 + bx2) / 2

    tem_de = bool(preco_original and preco and preco_original > preco)
    if tem_de:
        de_text = f"DE R$ {brl(preco_original)}"
        por_text = f"POR R$ {brl(preco)}"
    elif preco:
        de_text, por_text = None, f"R$ {brl(preco)}"
    else:
        de_text, por_text = None, "Confira na bio"

    if de_text:
        de_font, de_bbox = _fit_font(draw, de_text, inner_w, inner_h * 0.34, 46, bold=False)
        por_font, por_bbox = _fit_font(draw, por_text, inner_w, inner_h * 0.60, 62)
        gap = 10 * _TPL_SCALE
        h_de = de_bbox[3] - de_bbox[1]
        h_por = por_bbox[3] - por_bbox[1]
        top = (by1 + by2) / 2 - (h_de + gap + h_por) / 2
        draw.text((cx, top), de_text, font=de_font, fill=(226, 240, 252), anchor="ma",
                  stroke_width=2, stroke_fill=(18, 52, 92, 200))
        draw.text((cx, top + h_de + gap), por_text, font=por_font, fill=(255, 255, 255),
                  anchor="ma", stroke_width=3, stroke_fill=(16, 48, 88, 255))
    else:
        por_font, por_bbox = _fit_font(draw, por_text, inner_w, inner_h, 62)
        h_por = por_bbox[3] - por_bbox[1]
        top = (by1 + by2) / 2 - h_por / 2
        draw.text((cx, top), por_text, font=por_font, fill=(255, 255, 255), anchor="ma",
                  stroke_width=3, stroke_fill=(16, 48, 88, 255))


def _fit_contain(img, max_size):
    """Escala a imagem para CABER em max_size — AMPLIANDO se ela for menor.

    Image.thumbnail() so reduz, e era por isso que a foto do produto saia
    pequena na arte: o ML devolve a imagem no tamanho original e ela nunca
    crescia para preencher o quadro.
    """
    max_w, max_h = max_size
    if not max_w or not max_h:
        return img
    escala = min(max_w / img.width, max_h / img.height)
    escala = min(escala, 4.0)                       # evita pixelar demais
    if abs(escala - 1.0) < 0.01:
        return img
    return img.resize((max(1, round(img.width * escala)),
                       max(1, round(img.height * escala))),
                      Image.Resampling.LANCZOS)


def _trim_margins(img, min_gain=0.02):
    """Corta a borda branca/transparenta das fotos de marketplace.

    Foto de ML costuma vir com moldura branca em volta do produto; cortar essa
    moldura faz o produto ocupar a arte inteira.
    """
    try:
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        if alpha.getextrema()[0] < 250:             # tem transparencia = ja e recortada
            return rgba
        # varre por fora ate achar pixel que nao seja branco
        w, h = rgba.size
        px = rgba.load()

        def branco(x, y):
            r, g, b, a = px[x, y]
            return a > 250 and r > 243 and g > 243 and b > 243

        top = 0
        while top < h - 1 and all(branco(x, top) for x in range(0, w, max(1, w // 60))):
            top += 1
        bottom = h - 1
        while bottom > top and all(branco(x, bottom) for x in range(0, w, max(1, w // 60))):
            bottom -= 1
        left = 0
        while left < w - 1 and all(branco(left, y) for y in range(0, h, max(1, h // 60))):
            left += 1
        right = w - 1
        while right > left and all(branco(right, y) for y in range(0, h, max(1, h // 60))):
            right -= 1
        ganho_x = (right - left + 1) / w
        ganho_y = (bottom - top + 1) / h
        if ganho_x > min_gain and ganho_y > min_gain:
            return rgba.crop((left, top, right + 1, bottom + 1))
        return rgba
    except Exception:
        return img


def _draw_discount_badge(draw, box, desconto_pct):
    """Selo -N% no gelo vazio a esquerda do quadro (fora do quadro do preco)."""
    badge = f"-{int(desconto_pct)}%"
    font = load_font(46, bold=True)
    bbox = draw.textbbox((0, 0), badge, font=font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 26, 14
    right = box[0] - 24 * _TPL_SCALE
    left = right - bw - 2 * pad_x
    top = (box[1] + box[3]) / 2 - bh / 2
    draw.rounded_rectangle((left, top - pad_y, right, top + bh + pad_y),
                           radius=16, fill=(34, 197, 94, 255))
    draw.text((left + pad_x, top), badge, font=font, fill=(255, 255, 255), anchor="la")


def gerar_arte(image_url, preco, preco_original=None, titulo="", desconto_pct=None, usar_template=True):
    """Card 1080x1350: foto do produto em cima, banner img/template.png embaixo
    com o preco dentro do quadro de vidro. O titulo NAO vai na arte (fica na
    descricao do post)."""
    output = BASE_DIR / f"arte_{int(time.time())}_{random.randint(1000, 9999)}.jpg"
    try:
        has_template = bool(usar_template and TEMPLATE_FILE.exists())
        canvas = gradient((ART_W, ART_H))

        product = None
        if image_url:
            try:
                resp = http_get(image_url, headers={"Referer": "https://www.mercadolivre.com.br/"}, timeout=20)
                if resp is not None and resp.status_code == 200 and len(resp.content) > 1500:
                    product = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    product = _trim_margins(product)
            except Exception:
                product = None

        # --- Faixa do banner (opção C: banner na parte de baixo) ---
        banner_h = round(ART_W * TEMPLATE_H / TEMPLATE_W) if has_template else 0
        banner_top = ART_H - banner_h
        if has_template:
            banner = Image.open(TEMPLATE_FILE).convert("RGBA")
            if banner.size != (ART_W, banner_h):
                banner = banner.resize((ART_W, banner_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(banner, (0, banner_top))

        # --- Foto do produto, na area de cima ---
        # Margem curta de propósito: o fundo escuro deve sobrar só como borda.
        borda = ART_BORDER
        box = (borda, borda, ART_W - borda, (banner_top - borda) if has_template else ART_H - 110)
        draw = ImageDraw.Draw(canvas)
        if product is not None:
            product = _fit_contain(product, (box[2] - box[0], box[3] - box[1]))
            shadow = Image.new("RGBA", product.size, (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 150), (0, 0), product)
            shadow = shadow.filter(ImageFilter.GaussianBlur(26))
            px = box[0] + (box[2] - box[0] - product.width) // 2
            py = box[1] + (box[3] - box[1] - product.height) // 2
            canvas.alpha_composite(shadow, (px + 10, py + 18))
            canvas.paste(product, (px, py), product)
        else:
            # ImageDraw sobrescreve o pixel (nao faz alpha-blend): o retangulo
            # translucido precisa ir num overlay separado.
            overlay = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            odraw.rounded_rectangle(box, radius=32, fill=(255, 255, 255, 26),
                                    outline=(255, 255, 255, 70), width=3)
            odraw.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2 - 30),
                       "sem imagem", font=load_font(46, bold=False),
                       fill=(255, 255, 255, 150), anchor="mm")
            canvas = Image.alpha_composite(canvas, overlay)
            draw = ImageDraw.Draw(canvas)

        # --- Preco dentro do quadro de vidro do banner ---
        if has_template:
            price_box = tuple(
                v * _TPL_SCALE + (banner_top if i % 2 else 0)
                for i, v in enumerate(TEMPLATE_BOX)
            )
            if desconto_pct and desconto_pct >= 5:
                _draw_discount_badge(draw, price_box, desconto_pct)
            _draw_price_in_box(draw, price_box, preco, preco_original)
        else:
            # Sem template: cartao escuro com o preco embaixo.
            y = ART_H - banner_h - 210 if banner_h else ART_H - 200
            if preco_original and preco and preco_original > preco:
                draw.text((ART_W / 2, y), f"DE R$ {brl(preco_original)}",
                          font=load_font(52), fill=(255, 255, 255, 180), anchor="mm")
                price_text = f"POR R$ {brl(preco)}"
            elif preco:
                price_text = f"R$ {brl(preco)}"
            else:
                price_text = "Confira o preço na bio"
            font_price, bbox = _fit_font(draw, price_text, ART_W - 200, 150, 104)
            pw, ph = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pad = 34
            draw.rounded_rectangle((ART_W / 2 - pw / 2 - pad, y + 110 - pad / 2,
                                    ART_W / 2 + pw / 2 + pad, y + 110 + ph + pad),
                                   radius=30, fill=(255, 255, 255, 235))
            draw.text((ART_W / 2, y + 110 + ph / 2 - 3), price_text, font=font_price,
                      fill=(18, 28, 58, 255), anchor="mm")

        canvas.convert("RGB").save(output, "JPEG", quality=94)
        return output
    except Exception as exc:
        log(f"⚠️ Erro ao gerar a arte: {exc}")
        return None


def arte_para_publicar(image_url, preco, preco_original=None, desconto=None, titulo=""):
    """Gera a arte e devolve a URL pública (upload no Vercel Blob)."""
    path = gerar_arte(image_url, preco, preco_original, titulo=titulo, desconto_pct=desconto)
    if not path:
        return image_url
    url = upload_to_blob(path, Path(path).name)
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
    return url or image_url


# --------------------------------------------------------------------------
# Formatação
# --------------------------------------------------------------------------

_MONEY_RE = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+(?:,\d{2})?|\d+)", re.I
)


def prices_from_text(text):
    """Le o preco atual e o preco "de R$ X" de um texto de oferta.

    Devolve (atual, antigo). O texto dos canais e livre: vem "R$ 1.234,00"
    e tambem "De R$ 191 por R$ 110 no Pix". O regex antigo exigia centavos
    (\\d{2}), entao "R$ 110" nao era reconhecido e o preco antigo nunca
    aparecia.
    """
    if not text:
        return None, None
    limpo = re.sub(r"https?://\S+", " ", text)      # link nao e preco
    limpo = re.sub(r"\d{1,2}/\d{1,2}", " ", limpo)  # data tipo 10/10 tambem nao

    valores = []
    for m in _MONEY_RE.finditer(limpo):
        v = parse_money(m.group(1))
        if v and v > 0:
            valores.append(v)

    atual = antigo = None
    m_por = re.search(r"por\s*R\$\s*(\d[\d.,]*)", limpo, re.I)
    m_de = re.search(r"\bde\s*R\$\s*(\d[\d.,]*)", limpo, re.I)
    if m_por:
        atual = parse_money(m_por.group(1))
    elif valores:
        atual = valores[0]
    if m_de:
        antigo = parse_money(m_de.group(1))
    if antigo is None and len(valores) > 1:
        maior = max(valores)
        if atual and maior > atual:
            antigo = maior

    # so vale como preco antigo se for MAIOR que o atual
    if atual and antigo and antigo <= atual:
        antigo = None
    if not atual and antigo:
        atual, antigo = antigo, None
    return atual, antigo


def title_from_lines(lines):
    """Escolhe a linha que e o TITULO do produto, ignorando a frase do parceiro.

    Os canais comecam com uma frase de divulgacao e so depois vem o nome:
        MIXER E AVANCO DE VIDA          <- frase (1a linha, nao e o titulo)
        Mixer Power Inox 3 em 1 600W    <- titulo (linha de baixo)

    Ordem das regras:
      1. linhas com http, preco ou muito curtas nao sao titulo;
      2. frase em CAIXA ALTA e curta perde para qualquer titulo normal;
      3. se SOBRAR so frase, pula a 1a linha e usa a de baixo;
      4. dentro das normais, a primeira vence — a menos que ela seja um
         isca bem curta e a seguinte seja bem mais longa (titulo partido).
    """
    candidatas = []
    for i, l in enumerate(lines):
        if "http" in l.lower() or len(l) < 8:
            continue
        if re.search(r"R\$\s*\d", l):          # linha de preco
            continue
        letras = [c for c in l if c.isalpha()]
        if not letras:
            continue
        caixa_alta = sum(1 for c in letras if c.isupper()) / len(letras)
        propaganda = caixa_alta > 0.85 and len(l) < 70
        candidatas.append((i, l, propaganda))

    if not candidatas:
        return ""

    normais = [c for c in candidatas if not c[2]]      # regra 2
    if normais:
        melhor = normais[0]                           # regra 4
        # isca curta de divulgacao: "Olha isso:", "Corre que ta saindo:",
        # "Preço imperdível!" — a pontuação entrega que nao e o titulo.
        isca = (len(melhor[1]) < 30
                and melhor[1].rstrip().endswith((":", "!", "?", "-", "—")))
        if not isca and len(melhor[1]) < 25:
            mais_longo = max(normais, key=lambda c: len(c[1]))
            if len(mais_longo[1]) > len(melhor[1]) * 2:
                melhor = mais_longo
        elif isca and len(normais) > 1:
            melhor = normais[1]
        return melhor[1][:150]

    abaixo = [c for c in candidatas if c[0] > 0]      # regra 3
    escolhido = (abaixo or candidatas)[0]
    return escolhido[1][:150]


def price_block(preco, preco_original):
    if preco_original and preco and preco_original > preco:
        return f"📉 De R$ {brl(preco_original)}\n🔥 Por R$ {brl(preco)}"
    if preco:
        return f"💰 R$ {brl(preco)}"
    return ""


def discount_pct(preco, preco_original):
    if preco and preco_original and preco_original > preco:
        return (preco_original - preco) / preco_original * 100
    return None


# --------------------------------------------------------------------------
# Fontes de produtos
# --------------------------------------------------------------------------

def fetch_sheet_products():
    """Lê os produtos da planilha publicada do Google Sheets (fonte principal)."""
    products = []
    resp = http_get(SHEET_CSV_URL, headers={"Accept": "text/csv,*/*"}, timeout=20)
    if resp is None or resp.status_code != 200:
        log(f"⚠️ Planilha indisponível (HTTP {getattr(resp, 'status_code', 'erro')}).")
        return products

    try:
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader, None)
        if not header:
            return products
        header = [c.strip().lower().lstrip("\ufeff") for c in header]
        cols = {name: idx for idx, name in enumerate(header)}

        def pick(*names):
            for name in names:
                if name in cols:
                    return cols[name]
            return None

        c_link = pick("link", "url", "produto")
        c_price = pick("preço", "preco", "price", "valor")
        c_title = pick("titulo", "título", "title", "nome")
        c_photo = pick("foto", "imagem", "image", "thumb")
        c_old = pick("preço antigo", "preco antigo", "preço original", "de", "original")

        if c_link is None:
            c_link = 0

        for row in reader:
            if not row or len(row) <= c_link:
                continue
            raw_link = row[c_link].replace('"', "").strip()
            title = row[c_title].strip().replace('"', "") if c_title is not None and len(row) > c_title else ""
            photo = row[c_photo].strip().replace('"', "") if c_photo is not None and len(row) > c_photo else ""
            if not raw_link.lower().startswith("http") or not title:
                continue

            price = parse_money(row[c_price]) if c_price is not None and len(row) > c_price else None
            old = parse_money(row[c_old]) if c_old is not None and len(row) > c_old else None

            products.append({
                "id": "sheet_" + hashlib.md5(raw_link.encode()).hexdigest()[:12],
                "title": title,
                "price": price,
                "original_price": old,
                "permalink": raw_link,
                "thumbnail": photo,
                "source": "planilha",
            })

        log(f"📊 Planilha: {len(products)} produto(s) válido(s).")
    except Exception as exc:
        log(f"⚠️ Erro ao ler a planilha: {exc}")
    return products


def selenium_driver(visible=False):
    """Sobe um Chrome com PERFIL PERSISTENTE. Sem janela o ML devolve a parede.

    O perfil fica em BROWSER_PROFILE_DIR: o login feito uma vez nos portais de
    afiliado (ML, Shopee e Amazon) e reaproveitado nas execucoes seguintes.
    `visible=True` abre a janela na tela para o usuario fazer o login.
    """
    global _DRIVER
    if not USE_SELENIUM and not visible:
        return None
    with _DRIVER_LOCK:
        if _DRIVER is not None:
            if visible:
                try:
                    _DRIVER.set_window_position(40, 40)
                    _DRIVER.maximize_window()
                except Exception:
                    pass
            return _DRIVER
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except Exception:
            SELENIUM_STATE["msg"] = "selenium nao instalado (pip install selenium)"
            log(f"⚠️ Selenium: {SELENIUM_STATE['msg']}. Seguindo so com requests.")
            return None
        try:
            BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            opts = Options()
            if SELENIUM_HEADLESS and not visible:
                opts.add_argument("--headless=new")
            opts.add_argument("--lang=pt-BR")
            opts.add_argument("--window-size=1400,1000")
            # Perfil fixo: sem isso o Selenium cria um perfil temporario a cada
            # execucao e o login dos portais de afiliado se perde.
            opts.add_argument(f"--user-data-dir={BROWSER_PROFILE_DIR}")
            opts.add_argument("--profile-directory=Default")
            if visible:
                opts.add_argument("--start-maximized")
                opts.add_argument("--window-position=40,40")
            else:
                opts.add_argument("--window-position=-32000,-32000")  # real, so fora da vista
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_experimental_option("excludeSwitches", ["enable-automation",
                                                             "useAutomationExtension"])
            opts.add_experimental_option("useAutomationExtension", False)
            driver = webdriver.Chrome(options=opts)
            driver.set_page_load_timeout(max(45, LINK_GEN_TIMEOUT))
            if not visible:
                _DRIVER = driver
            SELENIUM_STATE["ok"] = True
            SELENIUM_STATE["msg"] = "Chrome ativo"
            log(f"✅ Chrome (Selenium) iniciado — perfil: {BROWSER_PROFILE_DIR.name}")
            return driver
        except Exception as exc:
            SELENIUM_STATE["ok"] = False
            SELENIUM_STATE["msg"] = f"falhou ({type(exc).__name__})"
            log(f"⚠️ Selenium: {SELENIUM_STATE['msg']}. Seguindo so com requests.")
            return None


def quit_driver():
    """Fecha o Chrome compartilhado (usado antes do modo de login)."""
    global _DRIVER
    with _DRIVER_LOCK:
        if _DRIVER is not None:
            try:
                _DRIVER.quit()
            except Exception:
                pass
            _DRIVER = None


def browser_login_session():
    """Abre os 3 portais de afiliado para o usuario logar uma unica vez.

    Uso: python bot.py --login-browser
    O perfil e o mesmo usado na operacao normal, entao o login persiste.
    """
    if IS_ANDROID:
        log("⚠️ O login pelo navegador precisa de um ambiente com tela. "
            "No Termux use um perfil ja autenticado ou o cookie no .env.")
        return
    if not USE_SELENIUM:
        log("⚠️ USE_SELENIUM=0 — o gerador de links do ML/Amazon precisa do Chrome.")
        return
    quit_driver()
    driver = selenium_driver(visible=True)
    if driver is None:
        log("⚠️ Não foi possível abrir o Chrome para o login.")
        return
    portais = [
        ("Mercado Livre Afiliados", ML_LINKBUILDER_URL),
        ("Shopee Afiliados", SHOPEE_AFFILIATE_URL),
        ("Shopee (site público)", "https://shopee.com.br/"),
        ("Amazon Associados", AMAZON_HOME_URL),
    ]
    log("🔐 Abrindo os portais de afiliado. Faça login em cada aba.")
    for nome, url in portais:
        try:
            if driver.current_url == "data:,":
                driver.get(url)
            else:
                driver.execute_script("window.open(arguments[0], '_blank');", url)
            log(f"   • {nome}: {url}")
        except Exception as exc:
            log(f"   ⚠️ {nome}: {type(exc).__name__}")
    log("Quando terminar, volte ao terminal e pressione ENTER para fechar o Chrome.")
    try:
        input()
    except Exception:
        try:
            time.sleep(600)
        except Exception:
            pass
    try:
        driver.quit()
    except Exception:
        pass
    log("🔒 Chrome de login fechado. O perfil está salvo.")


class _Page:
    """Shim para o selenium_get devolver a mesma interface do requests.Response."""

    def __init__(self, text, url):
        self.text = text or ""
        self.url = url
        self.status_code = 200 if text else 0
        self.headers = {"Content-Type": "text/html"}


def selenium_get(url, wait=3, timeout=45):
    """Baixa a pagina pelo Chrome de verdade. Devolve o HTML ou None."""
    driver = selenium_driver()
    if driver is None:
        return None
    with _DRIVER_LOCK:
        try:
            driver.get(url)
            if wait:
                time.sleep(wait)
            html = driver.page_source
            if _is_bot_wall(html[:2500]):
                log("⚠️ Selenium não conseguiu abrir " + url[:60] + " (ML bloqueou o Chrome).")
                return None
            return _Page(html, driver.current_url)
        except Exception as exc:
            log(f"⚠️ Selenium: {type(exc).__name__}: {exc}")
            return None


def selenium_eval(url, script, wait=3, timeout=None, await_promise=True):
    """Navega e executa JavaScript no Chrome real.

    Devolve {"ok": True, "value": ...} ou {"ok": False, "error": "..."}.
    `script` pode usar await quando await_promise=True.
    """
    driver = selenium_driver()
    if driver is None:
        return None
    timeout = timeout or LINK_GEN_TIMEOUT
    with _DRIVER_LOCK:
        try:
            driver.get(url)
            if wait:
                time.sleep(wait)
            driver.set_script_timeout(max(10, timeout))
            if await_promise:
                wrapper = (
                    "const done = arguments[arguments.length - 1];"
                    "(async () => {"
                    "  try {"
                    "    const value = await (async () => {" + script + "})();"
                    "    done({__selenium_eval__: true, ok: true, value: value});"
                    "  } catch (e) {"
                    "    done({__selenium_eval__: true, ok: false, error: String(e)});"
                    "  }"
                    "})();"
                )
                raw = driver.execute_async_script(wrapper)
            else:
                raw = driver.execute_script(script)
            if isinstance(raw, dict) and raw.pop("__selenium_eval__", None):
                return raw
            return {"ok": True, "value": raw}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

def chromium_candidates():
    """Binarios do Chromium em ordem de preferencia, com duplicados removidos."""
    visto, lista = set(), []
    achado = env("CHROMIUM_BIN")
    if achado and os.path.exists(achado):
        lista.append(achado)
    for nome in ("chromium-browser", "chromium", "headless_shell"):
        caminho = shutil.which(nome)
        if caminho:
            lista.append(caminho)
    prefixo = os.getenv("PREFIX") or "/data/data/com.termux/files/usr"
    for caminho in (f"{prefixo}/bin/chromium-browser",
                    f"{prefixo}/lib/chromium/chrome",
                    f"{prefixo}/lib/chromium/headless_shell",
                    f"{prefixo}/bin/headless_shell",
                    "/data/data/com.termux/files/usr/bin/chromium-browser",
                    "/system/bin/chromium-browser",
                    "C:/Program Files/Google/Chrome/Application/chrome.exe",
                    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"):
        if os.path.exists(caminho):
            lista.append(caminho)
    for caminho in lista:
        if caminho not in visto:
            visto.add(caminho)
            yield caminho


def chromium_binary():
    for caminho in chromium_candidates():
        return caminho
    return None


CHROMIUM_HINT = "pkg install x11-repo && pkg install chromium"


def _cdp_tentar(binary, perfil, extra_args, env_extra):
    """Sobe o Chromium e devolve (proc, url_base, motivo_da_falha)."""
    base = f"http://{CDP_HOST}:{CDP_PORT}"
    args = [binary,
            "--remote-debugging-port=%d" % CDP_PORT,
            "--remote-allow-origins=*",
            f"--user-data-dir={perfil}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
            "--lang=pt-BR", "--window-size=1400,1000",
            ] + extra_args + ["about:blank"]

    envp = None
    if env_extra:
        envp = dict(os.environ)
        envp.update(env_extra)

    log_arq = BASE_DIR / "cdp_chrome.log"
    try:
        fh = open(log_arq, "ab")
    except Exception:
        fh = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=fh, env=envp)
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {exc}"

    for _ in range(50):                       # ~25s esperando a porta
        if proc.poll() is not None:
            return None, None, f"chromium saiu (código {proc.returncode}); veja cdp_chrome.log"
        try:
            if requests.get(f"{base}/json/version", timeout=2).status_code == 200:
                return proc, base, ""
        except Exception:
            pass
        time.sleep(0.5)
    try:
        proc.terminate()
    except Exception:
        pass
    return None, None, "porta CDP não abriu em 25s; veja cdp_chrome.log"


def cdp_server():
    """Sobe o Chromium escutando CDP na porta e devolve a URL base (ou None)."""
    base = f"http://{CDP_HOST}:{CDP_PORT}"
    try:
        if requests.get(f"{base}/json/version", timeout=3).status_code == 200:
            return base
    except Exception:
        pass

    if _CDP["proc"] is not None and time.time() - _CDP["tried_at"] < 120:
        return None                      # ja tentou e falhou, nao fica tentando
    _CDP["tried_at"] = time.time()

    binarios = list(chromium_candidates())
    if not binarios:
        _CDP["msg"] = "Chromium não encontrado"
        log(f"⚠️ {CHROMIUM_HINT}")
        return None

    perfil = BASE_DIR / ".chrome-cdp"
    try:
        perfil.mkdir(exist_ok=True)
    except Exception:
        perfil = None

    no_android = bool(sys.platform == "android" or os.getenv("TERMUX_VERSION"))
    prefixo = os.getenv("PREFIX") or "/data/data/com.termux/files/usr"
    preload = f"{prefixo}/lib/libtermux-exec.so"
    tem_preload = os.path.exists(preload)

    # No Android nao existe display: Chromium sobe em headless. E como binario
    # em app-data e ET_DYN, precisa do LD_PRELOAD para rodar; o --single-process
    # existe porque o LD_PRELOAD quebra o zygote. Tentamos varias combinacoes.
    if no_android:
        variantes = [
            (["--headless=new", "--no-zygote", "--single-process"],
             {"LD_PRELOAD": preload} if tem_preload else None),
            (["--headless=new"], {"LD_PRELOAD": preload} if tem_preload else None),
            (["--headless=new", "--no-zygote", "--single-process"], None),
            (["--headless"], None),
        ]
    else:
        variantes = [([], None)]

    try:
        (BASE_DIR / "cdp_chrome.log").unlink(missing_ok=True)
    except Exception:
        pass

    motivos = []
    for binary in binarios:
        for extra, env_extra in variantes:
            proc, url, motivo = _cdp_tentar(binary, perfil, extra, env_extra)
            if url:
                _CDP["proc"] = proc
                _CDP["msg"] = "Chromium CDP ativo"
                log(f"✅ Chromium CDP ativo em {url} "
                    f"({os.path.basename(binary)}{' ' + ' '.join(extra) if extra else ''})")
                return url
            motivos.append(f"{os.path.basename(binary)}[{' '.join(extra) or 's/tela'}]: {motivo}")

    _CDP["msg"] = motivos[0] if motivos else "não subiu"
    log("⚠️ Chromium CDP não subiu. Tentativas:")
    for motivo in motivos[:6]:
        log(f"   • {motivo}")
    return None


def _cdp_open(url, wait=None, timeout=90):
    """Abre uma aba no Chromium, navega e devolve o WebSocket pronto."""
    try:
        import websocket  # websocket-client (python puro, instala no Termux)
    except Exception:
        _CDP["msg"] = "websocket-client ausente (pip install websocket-client)"
        log(f"⚠️ CDP: {_CDP['msg']} — recurso de navegador indisponível.")
        return None

    base = cdp_server()
    if not base:
        return None
    wait = CDP_WAIT if wait is None else wait

    target = None
    try:
        resp = requests.put(f"{base}/json/new?about:blank", timeout=10)
        if resp.status_code not in (200, 201):
            resp = requests.get(f"{base}/json/new?about:blank", timeout=10)
        target = resp.json()
    except Exception as exc:
        log(f"⚠️ CDP: não consegui abrir aba ({type(exc).__name__})")
        return None
    if not isinstance(target, dict) or not target.get("webSocketDebuggerUrl"):
        log("⚠️ CDP: resposta inesperada ao abrir aba.")
        return None

    try:
        ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=timeout,
            origin=f"http://{CDP_HOST}:{CDP_PORT}")
    except Exception as exc:
        log(f"⚠️ CDP: WebSocket falhou ({type(exc).__name__}). "
            f"Verifique se o Chromium subiu com --remote-allow-origins=*")
        return None

    try:
        ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        ws.send(json.dumps({"id": 2, "method": "Page.navigate",
                            "params": {"url": url}}))
        loaded = False
        deadline = time.time() + timeout
        while time.time() < deadline and not loaded:
            try:
                ws.settimeout(5)
                msg = json.loads(ws.recv())
            except Exception:
                continue                      # timeout aqui e normal: o JS roda
            if msg.get("method") == "Page.loadEventFired":
                loaded = True
        time.sleep(max(wait, 0))               # deixa o JS de listagem montar
        return ws
    except Exception as exc:
        try:
            ws.close()
        except Exception:
            pass
        log(f"⚠️ CDP: falha ao navegar em {url[:55]} ({type(exc).__name__})")
        return None


def _cdp_evaluate(ws, expression, await_promise=False, timeout=60):
    """Runtime.evaluate no WebSocket já aberto. Devolve o valor bruto."""
    if await_promise:
        expression = f"(async () => {{ {expression} }})()"
    eval_id = int(time.time() * 1000) % 1000000 + 3
    ws.send(json.dumps({
        "id": eval_id, "method": "Runtime.evaluate",
        "params": {"expression": expression, "returnByValue": True,
                   "awaitPromise": bool(await_promise)},
    }))
    deadline = time.time() + max(10, timeout)
    while time.time() < deadline:
        try:
            ws.settimeout(10)
            raw = ws.recv()
        except Exception:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if msg.get("id") != eval_id:
            continue
        result = msg.get("result") or {}
        if result.get("exceptionDetails"):
            detail = result["exceptionDetails"]
            text = ((detail.get("exception") or {}).get("description")
                    or detail.get("text") or "erro de JavaScript")
            raise RuntimeError(text[:300])
        return (result.get("result") or {}).get("value")
    raise TimeoutError("Runtime.evaluate não respondeu")


def cdp_get(url, wait=None, timeout=90):
    """Baixa a pagina por CDP e devolve o HTML renderizado, ou None."""
    ws = _cdp_open(url, wait, timeout)
    if ws is None:
        return None
    try:
        html = _cdp_evaluate(ws, "document.documentElement.outerHTML",
                             await_promise=False, timeout=45) or ""
        if _is_bot_wall(html[:2500]):
            log(f"⚠️ CDP: o site bloqueou o Chromium em {url[:55]}")
            return None
        if len(html) < 20000:
            log(f"⚠️ CDP: página veio Vazia ({len(html)} bytes) de {url[:55]} — "
                f"o site pode estar detectando o Chromium headless.")
        return _Page(html, url)
    except Exception as exc:
        log(f"⚠️ CDP falhou em {url[:55]}: {type(exc).__name__}: {exc}")
        _CDP["msg"] = f"{type(exc).__name__}"
        return None
    finally:
        try:
            ws.close()
        except Exception:
            pass


def cdp_eval(url, expression, wait=None, timeout=90, await_promise=True):
    """Executa JavaScript no Chromium via CDP e devolve {ok, value/error}."""
    ws = _cdp_open(url, wait, timeout)
    if ws is None:
        return {"ok": False, "error": "CDP indisponível"}
    try:
        value = _cdp_evaluate(ws, expression, await_promise=await_promise,
                              timeout=timeout)
        return {"ok": True, "value": value}
    except Exception as exc:
        log(f"⚠️ CDP eval em {url[:55]}: {type(exc).__name__}: {exc}")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            ws.close()
        except Exception:
            pass


def browser_eval(url, script, wait=3, timeout=None, await_promise=True):
    """Roda JavaScript no navegador real (Selenium no PC, CDP no Android).

    Devolve {"ok": True, "value": ...} ou {"ok": False, "error": "..."}.
    É a base dos geradores de link e da raspagem via navegador.
    """
    result = selenium_eval(url, script, wait=wait, timeout=timeout,
                           await_promise=await_promise)
    if result is not None and result.get("ok"):
        return result
    cdp_result = cdp_eval(url, script, wait=(wait + 3 if wait else CDP_WAIT),
                          timeout=timeout or 90, await_promise=await_promise)
    if cdp_result is not None and cdp_result.get("ok"):
        return cdp_result
    return result or cdp_result or {"ok": False,
                                    "error": "nenhum navegador disponível"}


def cdp_close():
    proc = _CDP.get("proc")
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass
        _CDP["proc"] = None


def browser_get(url, wait=3, force_browser=False):
    """HTML de uma pagina, com o plano B ja aplicado.

    Com BROWSER_SCRAPING=1 (padrao) as lojas sao abertas no Chrome real. No PC
    usa Selenium; no Android usa CDP direto no Chromium. Se o navegador falhar,
    ainda tenta o HTTP para nao perder a fonte por completo.
    """
    resp = None
    if not force_browser and not BROWSER_SCRAPING:
        resp = http_get(url)
        head = resp.text[:2000] if resp is not None else ""
        if resp is not None and "account-verification" not in head and "suspicious-traffic" not in head:
            return resp

    page = selenium_get(url, wait)
    if page is not None:
        return page
    log("↪️ Selenium indisponível — tentando Chromium via CDP.")
    page = cdp_get(url, wait=(wait + 3 if wait else CDP_WAIT))
    if page is not None:
        return page

    if resp is None:
        resp = http_get(url)
    return resp


def remember_store(url):
    """Guarda a loja (/social/<user>) vista num link de canal para usar como fonte."""
    match = re.search(r"mercadolivre\.com\.br/social/([^/?#]+)", url or "", re.I)
    if not match:
        return
    store = match.group(1).strip("/").lower()
    if not store:
        return
    known = load_json(STORES_FILE, [])
    if store in known:
        return
    known.append(store)
    known = known[-40:]
    save_json(STORES_FILE, known)
    log(f"🏪 Loja do ML aprendida: /social/{store} (vira fonte de ofertas)")


def known_stores():
    """Lojas do .env + as aprendidas nos canais."""
    stores = list(ML_STORES)
    for s in load_json(STORES_FILE, []):
        if s and s not in stores:
            stores.append(s)
    return stores


def fetch_mercado_livre_products(search_query=None):
    """Produtos do ML.

    Duas fontes, porque /ofertas e /social/ se comportam de jeito diferente:

    1. /ofertas?page=N — a pagina de ofertas de verdade. requests/curl_cffi
       nela recebem SEMPRE a parede anti-bot (HTTP 200 com "suspicious-traffic"),
       no PC e no celular, com cookie ou sem. Sai apenas pelo Chrome de verdade
       (Selenium), que e o que a versao anterior fazia e funcionava.
    2. /social/<loja> — o catalogo das lojas. NUNCA e bloqueado, entao sempre
       devolve produto com preco e titulo. Serve de reserva quando o Chrome
       nao estiver disponivel (celular sem Selenium).
    """
    products = []
    page = random.randint(1, 20)
    page_html = browser_get(f"https://www.mercadolivre.com.br/ofertas?page={page}", wait=3)
    if page_html is not None:
        soup = BeautifulSoup(page_html.text, "html.parser")
        for item in soup.select("li.ui-search-layout__item, div.poly-card, .andes-card, .promotion-item, .ui-search-result"):
            try:
                title_el = item.select_one(".poly-component__title, .ui-search-item__title, h2, a[title]")
                if not title_el:
                    continue
                title = (title_el.get("title") or title_el.get_text(strip=True)).strip()
                link_el = item.select_one("a[href]")
                permalink = (link_el.get("href") if link_el else "").split("#")[0]
                if not title or not permalink.startswith("http"):
                    continue
                current = item.select_one(".andes-money-amount:not(.andes-money-amount--previous), .price-tag")
                price = None
                if current:
                    frac = current.select_one(".andes-money-amount__fraction, .price-tag-fraction")
                    cents = current.select_one(".andes-money-amount__cents, .price-tag-cents")
                    if frac:
                        price = parse_money(f"{frac.get_text(strip=True).replace('.', '')}."
                                            f"{(cents.get_text(strip=True) if cents else '00')}")
                    else:
                        price = parse_money(current.get_text())
                if price:
                    products.append({
                        "id": "ml_" + hashlib.md5(permalink.encode()).hexdigest()[:12],
                        "title": title, "price": price, "original_price": None,
                        "permalink": permalink,
                        "thumbnail": ((item.select_one("img").get("data-src")
                                       or item.select_one("img").get("src") or "")
                                      if item.select_one("img") else ""),
                        "source": "raspagem",
                    })
            except Exception:
                continue

    # Reserva: catalogo das lojas /social/ (nunca bloqueado)
    wanted = _keywords(search_query) if search_query else set()
    fallback = []
    for store in known_stores():
        for item in store_catalog(ML_STORE_BASE + store):
            if wanted:
                words = _keywords(item.get("title"))
                if not words or not (words & wanted):
                    continue
            fallback.append({
                "id": "ml_" + hashlib.md5(item["url"].encode()).hexdigest()[:12],
                "title": item["title"], "price": item["price"],
                "original_price": None, "permalink": item["url"],
                "thumbnail": item.get("image") or "", "source": "loja",
            })
    if not products and fallback:
        products = fallback
        log(f"ℹ️ /ofertas não passou; usando o catálogo das lojas ({len(fallback)} produto(s)).")

    if not products:
        log("⚠️ Mercado Livre: 0 produtos. Use USE_SELENIUM=1 no PC, ML_STORES no .env, "
            "ou a planilha, que nunca é bloqueada.")
    else:
        random.shuffle(products)
        log(f"✅ Mercado Livre: {len(products)} produto(s).")
    return products


def _shopee_search_data(keyword):
    """Busca da Shopee pelo navegador (fetch same-origin) com fallback HTTP."""
    api_path = (f"/api/v4/search/search_items?by=relevancy"
                f"&keyword={urllib.parse.quote(keyword)}&limit=30&newest=0")
    if BROWSER_SCRAPING:
        script = """
        const resp = await fetch(%s, {
          credentials: 'include',
          headers: {'x-api-source': 'pc', 'x-requested-with': 'XMLHttpRequest',
                    'x-shopee-language': 'pt'}
        });
        const text = await resp.text();
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return text;
        """ % json.dumps(api_path)
        result = browser_eval("https://shopee.com.br/", script, wait=3,
                              timeout=LINK_GEN_TIMEOUT)
        if result and result.get("ok") and result.get("value"):
            raw = result["value"]
            low = raw.lower() if isinstance(raw, str) else ""
            if any(m in low for m in SHOPEE_BOT_MARKERS):
                log("⚠️ Shopee: tela anti-bot na busca pública. Configure "
                    "SHOPEE_APP_ID/SHOPEE_SECRET (Open API) ou resolva o desafio "
                    "no --login-browser.")
                return None
            try:
                return json.loads(raw)
            except Exception as exc:
                log(f"⚠️ Shopee (navegador): JSON inválido ({type(exc).__name__}).")

    resp = http_get("https://shopee.com.br" + api_path, timeout=20,
                    referer="https://shopee.com.br/",
                    headers={"Accept": "application/json, text/plain, */*",
                             "x-api-source": "pc", "x-shopee-language": "pt",
                             "x-requested-with": "XMLHttpRequest"})
    if resp is not None and resp.status_code == 200:
        low = (resp.text or "")[:4000].lower()
        if any(m in low for m in SHOPEE_BOT_MARKERS):
            log("⚠️ Shopee: anti-bot na busca HTTP. Use a Open API ou o portal.")
            return None
        try:
            return resp.json()
        except Exception as exc:
            log(f"⚠️ Shopee: {exc}")
    else:
        status = getattr(resp, "status_code", "erro")
        log(f"⚠️ Shopee bloqueada (HTTP {status}). A planilha é a fonte confiável.")
    return None


def fetch_shopee_affiliate_products(search_query=None):
    """Le as ofertas do portal logado e copia o link de cada modal."""
    if not BROWSER_SCRAPING:
        return []
    script = r"""
    const LIMIT = __LIMIT__;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
    const text = (el) => norm(el && (el.innerText || el.textContent || ""));
    const visible = (el) => {
      if (!el) return false;
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden";
    };
    const readLink = (root) => {
      if (!root) return "";
      for (const node of root.querySelectorAll("textarea, input")) {
        for (const part of String(node.value || "").split(/\s+/)) {
          if (/^https?:\/\/(?:shope\.ee|s\.shopee\.com\.br)\//i.test(part)) {
            return part.replace(/[.,);]+$/, "");
          }
        }
      }
      const m = text(root).match(
        /https?:\/\/(?:shope\.ee|s\.shopee\.com\.br)\/[^\s"'<>]+/i);
      return m ? m[0].replace(/[.,);]+$/, "") : "";
    };
    const cardOf = (btn) => {
      const card = btn.closest("a") || btn.parentElement;
      if (card && card.querySelector(".product-name")) return card;
      let node = btn.parentElement;
      for (let i = 0; i < 8 && node; i++) {
        if (node.querySelector(".product-name")
            && node.querySelectorAll(".get-link-btn").length === 1) {
          return node;
        }
        node = node.parentElement;
      }
      return card;
    };
    const imageOf = (card) => {
      const img = card && card.querySelector(".img-warpper img, img");
      return img ? (img.currentSrc || img.src || img.getAttribute("data-src") || "") : "";
    };
    const priceOf = (card) => {
      const el = card && card.querySelector(".product-price");
      return el ? text(el) : "";
    };
    const offerOf = (btn, card) => {
      const box = btn.closest('[id^="product_offer_"]');
      if (box && box.id) return box.id.replace("product_offer_", "");
      const input = card && card.querySelector('input[type="checkbox"]');
      return input ? String(input.value || "") : "";
    };

    let buttons = [];
    for (let i = 0; i < 40 && !buttons.length; i++) {
      buttons = Array.from(document.querySelectorAll(".get-link-btn"))
        .filter((b) => visible(b) && !b.disabled
                && !/massa|lote|batch/i.test(text(b)));
      if (!buttons.length) await sleep(500);
    }
    if (!buttons.length) {
      return {
        ok: false,
        error: /\/auth(?:\/|$)/.test(location.pathname)
          ? "login necessário" : "nenhum botão .get-link-btn na página",
        url: location.href,
        title: document.title,
        preview: text(document.body).slice(0, 500)
      };
    }

    const products = [];
    for (const btn of buttons.slice(0, LIMIT)) {
      const card = cardOf(btn);
      const item = {
        ok: false,
        title: text(card && card.querySelector(".product-name")),
        price: priceOf(card),
        image: imageOf(card),
        offer_id: offerOf(btn, card),
        affiliate_link: "",
        error: ""
      };
      try {
        btn.scrollIntoView({block: "center"});
        btn.click();
        let modal = null;
        let link = "";
        for (let i = 0; i < 50 && !link; i++) {
          await sleep(300);
          modal = document.querySelector(".get-link-modal");
          if (visible(modal)) link = readLink(modal);
        }
        if (!link && modal) {
          const longTab = Array.from(
            modal.querySelectorAll('[role="tab"], .ant-tabs-tab, button')
          ).find((el) => /link longo|long link/i.test(text(el)));
          if (longTab) {
            longTab.click();
            await sleep(700);
            link = readLink(modal);
          }
        }
        item.ok = !!link;
        item.affiliate_link = link;
        item.error = link ? "" : "modal sem link";
      } catch (e) {
        item.error = String(e);
      }
      products.push(item);
      const modal = document.querySelector(".get-link-modal");
      const close = modal && modal.querySelector(".ant-modal-close");
      if (close) close.click();
      else document.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Escape", keyCode: 27, which: 27, bubbles: true
      }));
      await sleep(500);
    }
    return {ok: true, products: products, url: location.href,
            count: buttons.length, preview: text(document.body).slice(0, 300)};
    """
    script = script.replace("__LIMIT__", str(SHOPEE_OFFER_LIMIT))
    result = browser_eval(SHOPEE_PRODUCT_OFFER_URL, script, wait=10,
                          timeout=max(180, LINK_GEN_TIMEOUT * 3))
    value = (result or {}).get("value") or {}
    if not isinstance(value, dict) or not value.get("ok"):
        detail = ""
        if isinstance(value, dict):
            detail = value.get("error") or value.get("preview") or ""
        if not detail:
            detail = (result or {}).get("error") or "navegador indisponível"
        log(f"⚠️ Shopee portal: {str(detail)[:220]}")
        return []

    products = []
    for item in value.get("products", []):
        link = str(item.get("affiliate_link") or "").strip()
        title = str(item.get("title") or "").strip()
        price = parse_money(item.get("price"))
        if not link or not title or not price:
            if not link:
                log(f"⚠️ Shopee oferta sem link: {title[:50] or item.get('offer_id')}")
            continue
        offer_id = str(item.get("offer_id") or "")
        products.append({
            "id": "shopee_" + (offer_id or hashlib.md5(link.encode()).hexdigest()[:12]),
            "title": title[:180],
            "price": price,
            "original_price": None,
            "permalink": link,
            "affiliate_link": link,
            "thumbnail": item.get("image") or "",
            "source": "shopee_portal",
        })

    if search_query and products:
        wanted = _keywords(search_query)
        products = [p for p in products if _keywords(p["title"]) & wanted]
    return products


def fetch_shopee_products_api(search_query=None):
    """Ofertas pela Open API oficial (sem navegador, sem anti-bot)."""
    if not SHOPEE_APP_ID or not SHOPEE_SECRET:
        return []
    keyword = (search_query or "ofertas").replace('"', '\\"')
    query = ('{ productOfferV2(keyword: "%s", sortType: 1, page: 1, limit: %d) '
             '{ nodes { productName itemId shopId price priceMin priceMax '
             'priceDiscountRate imageUrl productLink offerLink sales } '
             'pageInfo { page limit hasNextPage } } }'
             % (keyword, SHOPEE_OFFER_LIMIT))
    body = json.dumps({"query": query}, ensure_ascii=False, separators=(",", ":"))
    _, authorization = _shopee_authorization(body)
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "Authorization": authorization}
    try:
        resp = requests.post(SHOPEE_API_URL, data=body.encode("utf-8"),
                             headers=headers, timeout=LINK_GEN_TIMEOUT)
    except Exception as exc:
        log(f"⚠️ Shopee Open API: {type(exc).__name__}: {exc}")
        return []
    if resp.status_code != 200:
        log(f"⚠️ Shopee Open API: HTTP {resp.status_code}: {resp.text[:160]}")
        return []
    try:
        data = resp.json()
    except Exception as exc:
        log(f"⚠️ Shopee Open API: JSON inválido ({type(exc).__name__}).")
        return []
    if data.get("errors"):
        log(f"⚠️ Shopee Open API: {str(data['errors'])[:200]}")
        return []

    nodes = (((data.get("data") or {}).get("productOfferV2") or {}).get("nodes") or [])
    products = []
    for node in nodes:
        title = str(node.get("productName") or "").strip()
        price = parse_money(node.get("price")) or parse_money(node.get("priceMin"))
        link = str(node.get("offerLink") or node.get("productLink") or "").strip()
        if not title or not price or not link:
            continue
        try:
            pct = float(str(node.get("priceDiscountRate") or "0")
                        .replace("%", "").replace(",", ".").strip())
        except ValueError:
            pct = 0.0
        old = price / (1 - pct / 100) if pct > 0 and price else None
        item_id, shop_id = node.get("itemId"), node.get("shopId")
        products.append({
            "id": (f"shopee_{shop_id}_{item_id}" if item_id and shop_id
                   else "shopee_" + hashlib.md5(link.encode()).hexdigest()[:12]),
            "title": title[:180],
            "price": price,
            "original_price": old,
            "permalink": link,
            "affiliate_link": str(node.get("offerLink") or ""),
            "thumbnail": str(node.get("imageUrl") or ""),
            "source": "shopee_api",
        })
    if search_query and products:
        wanted = _keywords(search_query)
        products = [p for p in products if _keywords(p["title"]) & wanted]
    if products:
        log(f"✅ Shopee (Open API): {len(products)} produto(s).")
    return products


def fetch_shopee_products(search_query=None):
    products = fetch_shopee_affiliate_products(search_query)
    if products:
        random.shuffle(products)
        log(f"✅ Shopee (portal): {len(products)} produto(s).")
        return products

    # Portal vazio (ou sem login): tenta a Open API antes de encostar no site
    # público, que é onde aparece a tela de anti-bot.
    if SHOPEE_APP_ID and SHOPEE_SECRET:
        products = fetch_shopee_products_api(search_query)
        if products:
            random.shuffle(products)
            return products

    if not search_query:
        return []

    products = []
    keyword = search_query or "ofertas"
    data = _shopee_search_data(keyword)
    if data:
        try:
            for entry in data.get("items", []) or (data.get("data", {}) or {}).get("items", []):
                basic = entry.get("item_basic") or entry
                item_id, shop_id = basic.get("itemid"), basic.get("shopid")
                title, raw = basic.get("name"), basic.get("price", 0)
                if not (item_id and shop_id and title and raw):
                    continue
                price = float(raw) / 100000.0
                old_raw = basic.get("price_before_discount", 0)
                old = float(old_raw) / 100000.0 if old_raw and old_raw > raw else None
                thumb = f"https://down-br.img.susercontent.com/file/{basic.get('image')}" if basic.get("image") else ""
                products.append({
                    "id": f"shopee_{shop_id}_{item_id}", "title": title, "price": price,
                    "original_price": old, "permalink": f"https://shopee.com.br/product-i.{shop_id}.{item_id}",
                    "thumbnail": thumb, "source": "raspagem",
                })
        except Exception as exc:
            log(f"⚠️ Shopee: {exc}")

    if products:
        random.shuffle(products)
        log(f"✅ Shopee: {len(products)} produto(s).")
    return products


def fetch_amazon_products(search_query=None):
    products = []
    keyword = search_query or "eletronicos ofertas"
    url = f"https://www.amazon.com.br/s?k={urllib.parse.quote(keyword)}"
    resp = browser_get(url, wait=3)
    if resp is None or resp.status_code != 200:
        log("⚠️ Amazon: página de busca indisponível (bloqueio anti-bot).")
        return products

    soup = BeautifulSoup(resp.text, "html.parser")
    for card in soup.select("div[data-component-type='s-search-result']"):
        try:
            asin = card.get("data-asin")
            link = card.select_one("h2 a, a.a-link-normal")
            title_el = card.select_one("h2 span, h2")
            if not asin or not title_el:
                continue
            price_el = card.select_one(".a-price .a-offscreen")
            old_el = card.select_one(".a-text-price .a-offscreen")
            price = parse_money(price_el.get_text()) if price_el else None
            if not price:
                continue
            href = (link.get("href") if link else f"/dp/{asin}") or ""
            href = href.split("?")[0]
            if href.startswith("/"):
                href = "https://www.amazon.com.br" + href
            img = card.select_one("img.s-image")
            products.append({
                "id": f"amz_{asin}", "title": title_el.get_text(strip=True), "price": price,
                "original_price": parse_money(old_el.get_text()) if old_el else None,
                "permalink": href,
                "thumbnail": img.get("src") if img else "", "source": "raspagem",
            })
        except Exception:
            continue

    if products:
        random.shuffle(products)
        log(f"✅ Amazon: {len(products)} produto(s).")
    else:
        log("⚠️ Amazon: 0 produtos (provável bloqueio anti-bot).")
    return products


def oferta_valida(product):
    """A oferta presta? Devolve (ok, motivo) para o log mostrar o descarte."""
    preco = product.get("price")
    if not isinstance(preco, (int, float)) or preco <= 0:
        return False, "sem preço"
    if MIN_PRICE > 0 and preco < MIN_PRICE:
        return False, f"R$ {brl(preco)} abaixo do mínimo"
    if MAX_PRICE > 0 and preco > MAX_PRICE:
        return False, f"R$ {brl(preco)} acima do máximo"
    if MIN_DISCOUNT > 0:
        antigo = product.get("original_price")
        if not isinstance(antigo, (int, float)) or not antigo or antigo <= preco:
            return False, "sem desconto real"
        desconto = (antigo - preco) / antigo * 100
        if desconto < MIN_DISCOUNT:
            return False, f"desconto de só {desconto:.0f}%"
    return True, ""


def busca_relevante(product, query):
    """O produto tem a ver com o termo buscado? (sem acento, por palavra)"""
    wanted = _keywords(query)
    return not wanted or bool(wanted & _keywords(product.get("title", "")))


def rank_ofertas(products):
    """Melhor oferta primeiro: maior desconto; sem desconto, menor preço."""
    def chave(p):
        pct = discount_pct(p.get("price"), p.get("original_price")) or 0
        preco = p.get("price")
        if not isinstance(preco, (int, float)):
            preco = float("inf")
        return (-pct, preco)

    return sorted(products, key=chave)


def collect_products(include_scrape=True, search_query=None, include_sheet=True):
    products = fetch_sheet_products() if include_sheet else []
    if search_query:
        products += (fetch_mercado_livre_products(search_query)
                     + fetch_shopee_products(search_query)
                     + fetch_amazon_products(search_query))
    elif include_scrape:
        products += fetch_mercado_livre_products() + fetch_shopee_products()

    # Filtro de oferta: descarta preco absurdo (shampoo de 24k, console de 5k)
    # e, se pedido, exige desconto real.
    if MIN_PRICE > 0 or MAX_PRICE > 0 or MIN_DISCOUNT > 0:
        bons, descartados = [], {}
        for p in products:
            ok, motivo = oferta_valida(p)
            if ok:
                bons.append(p)
            else:
                chave = motivo.split(" R$")[0].split(" só")[0]
                descartados[chave] = descartados.get(chave, 0) + 1
        if descartados:
            resumo = ", ".join(f"{v} {k}" for k, v in
                               sorted(descartados.items(), key=lambda x: -x[1])[:4])
            log(f"🧹 Filtro de oferta: {len(products) - len(bons)} descartado(s) [{resumo}]")
        products = bons

    random.shuffle(products)
    return products


# --------------------------------------------------------------------------
# Extração de metadados (link solto no chat privado)
# --------------------------------------------------------------------------

def _json_ld_products(soup):
    found = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.text or "{}")
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        for item in stack:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Product":
                found.append(item)
            graph = item.get("@graph")
            if isinstance(graph, list):
                found.extend(n for n in graph if isinstance(n, dict) and n.get("@type") == "Product")
    return found


def _amazon_image(soup):
    """Imagem principal da Amazon.

    A pagina de produto da Amazon nao traz og:image nem JSON-LD Product: a
    imagem fica em #landingImage/#imgTagWrapperId, em data-old-hires (maior
    resolucao) ou data-a-dynamic-image (JSON com varios tamanhos).
    """
    def from_node(node):
        for attr in ("data-old-hires", "src"):
            value = (node.get(attr) or "").strip()
            if value.startswith(("http://", "https://")):
                return value
        try:
            sizes = json.loads(node.get("data-a-dynamic-image") or "")
        except (TypeError, ValueError):
            sizes = {}
        if isinstance(sizes, dict) and sizes:
            def area(item):
                dims = item[1]
                if isinstance(dims, list) and len(dims) >= 2:
                    return dims[0] * dims[1]
                return 0
            best = max(sizes.items(), key=area)[0]
            if best.startswith(("http://", "https://")):
                return best
        return ""

    for selector in ("#landingImage", "#imgTagWrapperId img",
                     "#main-image-container img", "[data-old-hires]"):
        node = soup.select_one(selector)
        if node is not None:
            found = from_node(node)
            if found:
                return found
    return ""


def extract_from_html(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title, price, old_price, image = "", None, None, ""

    og_title = soup.find("meta", property="og:title")
    if og_title:
        title = og_title.get("content", "")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content", "")

    for product in _json_ld_products(soup):
        if not title and product.get("name"):
            title = product["name"]
        image = image or product.get("image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""
        if not image:
            for prop in product.get("additionalProperty", []) or []:
                if prop.get("name") in ("image", "thumbnailUrl"):
                    image = prop.get("value") or ""
                    break
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            price = price or parse_money(offers.get("price") or offers.get("lowPrice") or offers.get("highPrice"))
            old_price = old_price or parse_money(offers.get("original_price") or offers.get("listPrice"))
        break

    if not image:
        image = _amazon_image(soup)

    if price is None:
        for prop, setter in (("product:price:amount", "p"), ("og:price:amount", "p"), ("twitter:data1", "p")):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                price = parse_money(meta.get("content"))
                if price:
                    break

    if price is None:
        current = (soup.select_one(".andes-money-amount--current .andes-money-amount__fraction")
                   or soup.select_one(".price-tag-fraction")
                   or soup.select_one("#priceblock_ourprice")
                   or soup.select_one("#corePrice_feature_div .a-offscreen")
                   or soup.select_one(".a-price .a-offscreen"))
        if current:
            price = parse_money(current.get_text(strip=True))
        else:
            match = re.search(r"R\$\s?([\d\.]+,\d{2})", soup.get_text(" ", strip=True)[:20000])
            if match:
                price = parse_money(match.group(1))

    if old_price is None:
        old_el = (soup.select_one(".andes-money-amount--previous .andes-money-amount__fraction")
                  or soup.select_one("s .price-tag-fraction")
                  or soup.select_one(".a-text-price .a-offscreen"))
        if old_el:
            old_price = parse_money(old_el.get_text(strip=True))

    title = re.split(r"\s*[|\-–]\s*", title)[0].strip() if title else ""
    return title[:180], price, (old_price if old_price and price and old_price > price else None), image


def extract_product(url):
    """Extrai título, preço e imagem de um link de marketplace."""
    url = expand_url(url)
    resp = browser_get(url, wait=3)
    if resp is None or resp.status_code != 200:
        return {"title": "", "price": None, "original_price": None, "image": "", "link": url}

    if "account-verification" in resp.text[:2000] or "suspicious-traffic" in resp.text[:2000]:
        return {"title": "", "price": None, "original_price": None, "image": "", "link": url,
                "blocked": True}

    try:
        title, price, old_price, image = extract_from_html(resp.text, url)
    except Exception as exc:
        log(f"⚠️ Extração falhou: {exc}")
        title, price, old_price, image = "", None, None, ""

    return {"title": title, "price": price, "original_price": old_price, "image": image, "link": url}


# --------------------------------------------------------------------------
# Vitrine
# --------------------------------------------------------------------------

def save_to_vitrine(item):
    """Grava na vitrine local E publica na bio (vagantepromo.vercel.app).

    Item sem preço é DESCARTADO: a página da bio faz `p.price.toFixed(2)` sem
    nenhuma proteção, então um único item com price=null quebra a vitrine
    INTEIRA na tela do visitante. Ofertas de canal sem preço continuam indo
    para o Telegram, só não entram na bio.
    """
    preco = item.get("price")
    if preco is None or (isinstance(preco, (int, float)) and preco <= 0):
        log(f"⚠️ Vitrine: '{str(item.get('title'))[:40]}' sem preço — não entra na bio.")
        return
    with VITRINE_LOCK:
        vitrine = load_json(VITRINE_FILE, [])
        # limpa qualquer item quebrado que tenha ficado de execuções antigas
        vitrine = [v for v in vitrine if isinstance(v, dict)
                   and isinstance(v.get("price"), (int, float)) and v.get("price") > 0]
        if any(v.get("link") == item.get("link") for v in vitrine[:20]):
            return
        vitrine.insert(0, {
            "id": item["id"],
            "title": item["title"],
            "price": preco,
            "original_price": item.get("original_price"),
            "link": item["link"],
            "image": item.get("image") or "",
            "time": time.strftime("%d/%m/%Y %H:%M"),
        })
        save_json(VITRINE_FILE, vitrine[:40])
        total = len(vitrine[:40])
        log(f"📦 Vitrine atualizada ({total} itens).")
        # Sem isto a pagina da bio (vagantepromo.vercel.app) NUNCA muda: ela le o
        # vitrine.json do Vercel Blob e o bot so escrevia no disco do celular.
        url = upload_to_blob(VITRINE_FILE, "vitrine.json")
        if url:
            log(f"🌐 Bio atualizada: {url[:78]}")
        else:
            log("⚠️ Vitrine não foi publicada na bio (falha no Vercel Blob).")


def delete_from_vitrine(item_id, remove_from_seen=False):
    """Remove um item da vitrine, do arquivo local e do Vercel Blob."""
    item_id = str(item_id or "").strip()
    if not item_id:
        return False, "id não informado"
    with VITRINE_LOCK:
        vitrine = load_json(VITRINE_FILE, [])
        if not isinstance(vitrine, list):
            return False, "vitrine inválida"
        restantes = [v for v in vitrine
                     if not (isinstance(v, dict) and str(v.get("id")) == item_id)]
        if len(restantes) == len(vitrine):
            return False, "item não encontrado"
        save_json(VITRINE_FILE, restantes)
        url = upload_to_blob(VITRINE_FILE, "vitrine.json")
        if not url:
            return False, "salvo no disco, mas falhou publicar no Blob"
        if remove_from_seen:
            vistos = load_json(SEEN_FILE, [])
            if isinstance(vistos, list):
                save_json(SEEN_FILE, [s for s in vistos if str(s) != item_id])
        log(f"🗑️ Vitrine: item {item_id} removido ({len(restantes)} restantes).")
        return True, f"removido; {len(restantes)} itens restantes"


# --------------------------------------------------------------------------
# Publicação
# --------------------------------------------------------------------------

LINK_FAIL_NOTICE = {}


def notify_link_failure(permalink, title, error):
    """Avisa o dono que a oferta NAO foi publicada (com throttle por link)."""
    key = permalink or title
    now = time.time()
    if now - LINK_FAIL_NOTICE.get(key, 0) < 1800:
        return
    LINK_FAIL_NOTICE[key] = now
    log(f"⛔ Oferta não publicada: gerador de link falhou para {str(permalink)[:70]}")
    notify_admin(
        "⛔ *Oferta NÃO publicada* — o gerador de link falhou.\n\n"
        f"📦 {str(title or 'Oferta')[:90]}\n"
        f"🔗 {str(permalink or '')[:150]}\n"
        f"⚠️ {str(error or 'erro desconhecido')[:300]}"
    )


def publish(product, chat_id=None, reply_to=None, announce_instagram=False):
    price = product.get("price")
    old = product.get("original_price")
    title = product.get("title") or "Oferta Especial"
    permalink = product.get("permalink") or product.get("link") or ""
    link = product.get("affiliate_link") or ""
    aviso = ""
    if not link:
        link, aviso = generate_affiliate_link(permalink, price, title)

    if not link:
        notify_link_failure(permalink, title, aviso)
        return False

    lines = ["🔥 OFERTA EM DESTAQUE", "", f"📦 {title}", ""]
    block = price_block(price, old)
    if block:
        lines += block.split("\n") + [""]
    # A URL nao vai no texto: fica so no botao, que e o que o usuario pediu
    # (link gigante em texto deixa o post feio).
    keyboard = {
        "inline_keyboard": [[{"text": "💗 Ver Oferta", "url": link}]]
    }
    if chat_id is None:
        lines += [FOOTER_TEXT]
    text = "\n".join(lines)

    ok = send_message(text, chat_id=chat_id, photo_url=product.get("thumbnail") or None, reply_to=reply_to, reply_markup=keyboard)

    if ok:
        seen = load_json(SEEN_FILE)
        seen[product["id"]] = {"price": price, "at": time.strftime("%d/%m %H:%M")}
        save_json(SEEN_FILE, seen)
        save_to_vitrine({
            "id": product["id"], "title": title, "price": price,
            "original_price": old, "link": link, "image": product.get("thumbnail") or "",
        })

    if announce_instagram:
        product["ig_queued"] = schedule_instagram(product, title, price, old,
                                                  link=link)
    return ok


def _ig_queue_qid(item):
    """Identificador estável para o painel remover um item da fila."""
    if not isinstance(item, dict):
        return ""
    qid = str(item.get("qid") or "").strip()
    if qid:
        return qid
    base = "|".join(str(item.get(k) or "") for k in ("id", "title", "image", "price"))
    return "q_" + hashlib.md5(base.encode()).hexdigest()[:12]


def _ig_queue_publica():
    """Versão enxuta da fila para o painel (sem quebrar se o JSON estiver sujo)."""
    with IG_QUEUE_LOCK:
        fila = load_json(IG_QUEUE_FILE, [])
    if not isinstance(fila, list):
        return []
    saida = []
    for item in fila[:10]:
        if not isinstance(item, dict):
            continue
        saida.append({
            "qid": _ig_queue_qid(item),
            "id": str(item.get("id") or "")[:80],
            "title": str(item.get("title") or "")[:120],
            "price": item.get("price"),
            "old": item.get("old"),
            "image": str(item.get("image") or ""),
            "link": str(item.get("link") or ""),
        })
    return saida


def delete_from_ig_queue(qid):
    """Remove um item da fila do Instagram sem tocar na vitrine."""
    qid = str(qid or "").strip()
    if not qid:
        return False, "item não informado"
    with IG_QUEUE_LOCK:
        fila = load_json(IG_QUEUE_FILE, [])
        if not isinstance(fila, list):
            return False, "fila inválida"
        restantes = [item for item in fila
                     if not (isinstance(item, dict) and _ig_queue_qid(item) == qid)]
        if len(restantes) == len(fila):
            return False, "item não encontrado"
        save_json(IG_QUEUE_FILE, restantes)
    log(f"🗑️ Fila do Instagram: {qid} removido ({len(restantes)} restantes).")
    return True, f"removido; {len(restantes)} item(ns) restante(s)"


def schedule_instagram(product, title, price, old, link=""):
    """Enfileira o post do Instagram. Devolve True se entrou na fila."""
    if not control_enabled("instagram"):
        log("⏸️ Instagram desligado no painel; arte não enfileirada.")
        return False
    pct = discount_pct(price, old)
    if IG_MIN_DISCOUNT > 0:
        if pct is None:
            log(f"⏭️ Instagram: '{title[:40]}' sem preço antigo para medir desconto.")
            return False
        if pct < IG_MIN_DISCOUNT:
            log(f"⏭️ Instagram: '{title[:40]}' com {pct:.0f}% de desconto "
                f"(mínimo {IG_MIN_DISCOUNT:.0f}%).")
            return False
    image = product.get("thumbnail")
    if not image:
        log("⏭️ Instagram: produto sem imagem.")
        return False
    qid = "q_" + hashlib.md5(
        f"{product.get('id') or ''}|{title}|{image}|{time.time()}".encode()
    ).hexdigest()[:12]
    with IG_QUEUE_LOCK:
        queue = load_json(IG_QUEUE_FILE, [])
        if not isinstance(queue, list):
            queue = []
        queue.append({"qid": qid, "id": product.get("id") or "", "title": title,
                      "price": price, "old": old, "image": image, "pct": pct,
                      "link": link or ""})
        save_json(IG_QUEUE_FILE, queue[-10:])
    log(f"🖼️ Arte do post '{title[:32]}' entrou na fila do Instagram.")
    return True


def _ig_queue_link(item):
    """Link para o 1º comentário; recupera itens antigos pela vitrine.

    A fila antiga era gravada sem `link`. Para não perder o comentário desses
    posts, procura o mesmo item na vitrine por id, imagem ou título+preço.
    """
    link = (item.get("link") or "").strip()
    if link:
        return link
    pid = str(item.get("id") or "").strip()
    titulo = (item.get("title") or "").strip().casefold()
    imagem = (item.get("image") or "").strip()
    preco = item.get("price")
    vitrine = load_json(VITRINE_FILE, [])
    if not isinstance(vitrine, list):
        return ""
    for v in vitrine:
        if not isinstance(v, dict) or not v.get("link"):
            continue
        if pid and str(v.get("id")) == pid:
            return v["link"]
        if imagem and v.get("image") == imagem:
            return v["link"]
        if titulo and (v.get("title") or "").strip().casefold() == titulo:
            try:
                if preco is None or abs(float(v.get("price")) - float(preco)) < 0.01:
                    return v["link"]
            except (TypeError, ValueError):
                return v["link"]
    return ""


# --------------------------------------------------------------------------
# Cupons do Mercado Livre
# --------------------------------------------------------------------------

COUPON_LOCK = threading.Lock()


def _coupon_expiry(value):
    if not value:
        return ""
    try:
        return time.strftime("%d/%m", time.strptime(str(value)[:10], "%Y-%m-%d"))
    except Exception:
        return str(value)[:10]


def _coupon_from_json(raw):
    """Normaliza um cupom do JSON __NORDIC_RENDERING_CTX__."""
    if not isinstance(raw, dict):
        return None
    if ((raw.get("status") or {}).get("id") or "").upper() != "ACTIVE":
        return None
    title = ((raw.get("title") or {}).get("text") or "").strip()
    seller = (raw.get("category") or "").strip()
    if not title or not seller:
        return None
    seg = raw.get("segmentations") or {}
    if seg.get("has_items") is False:
        return None
    action = raw.get("action") or {}
    link = action.get("value") if action.get("type") == "link" else ""
    if not str(link or "").startswith("http"):
        link = ""
    amount = raw.get("amount") or {}
    campaign = str(raw.get("campaign_id") or "").strip()
    if not campaign:
        campaign = "cupom_" + hashlib.md5(
            f"{seller}|{title}|{link}".encode()).hexdigest()[:12]
    return {
        "id": campaign,
        "title": title,
        "seller": seller,
        "link": link,
        "icon": raw.get("icon") or "",
        "min_amount": (amount.get("min_amount") or "").strip(),
        "cap_amount": (amount.get("cap_amount") or "").strip(),
        "benefit_mode": raw.get("benefit_mode") or "",
        "expiration": _coupon_expiry(raw.get("expiration_date")),
        "scarcity": ((raw.get("scarcity") or {}).get("text") or "").strip(),
        "total_items": seg.get("total_items") or 0,
    }


def _coupons_from_cards(html):
    """Reserva: lê os cards HTML, que não trazem link nem validade."""
    soup = BeautifulSoup(html, "html.parser")
    coupons = []
    for card in soup.select("article.smart-coupon"):
        seller_el = card.select_one(".smart-coupon-highlight__category")
        title_el = card.select_one(".smart-coupon-highlight__title-text")
        if not seller_el or not title_el:
            continue
        seller = seller_el.get_text(" ", strip=True)
        title = title_el.get_text(" ", strip=True)
        if not seller or not title:
            continue
        icon = card.select_one("img")
        coupons.append({
            "id": "html_" + hashlib.md5(f"{seller}|{title}".encode()).hexdigest()[:12],
            "title": title,
            "seller": seller,
            "link": "",
            "icon": (icon.get("src") if icon else "") or "",
            "min_amount": "",
            "cap_amount": "",
            "benefit_mode": "",
            "expiration": "",
            "scarcity": "",
            "total_items": 0,
        })
    return coupons


def extract_ml_coupons(html):
    """Cupons ACTIVE da página /ofertas/cupons do Mercado Livre.

    O HTML do ML (Nordic) carrega os cupons completos no JSON
    __NORDIC_RENDERING_CTX__: campanha, vendedor, mínimo, limite, link e
    validade. Os cards HTML só servem de reserva.
    """
    if not html:
        return []
    if "hubo un error accediendo" in html.lower():
        log("⚠️ Cupons: o ML devolveu a página de erro/bloqueio.")
        return []

    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NORDIC_RENDERING_CTX__")
    coupons = []
    json_ok = False
    if script is not None:
        raw = (script.string or script.get_text() or "").strip()
        if raw.startswith("_n.ctx.r="):
            raw = raw[len("_n.ctx.r="):]
        try:
            data, _ = json.JSONDecoder().raw_decode(raw)
        except Exception as exc:
            log(f"⚠️ Cupons: JSON da página inválido ({type(exc).__name__}).")
            data = None
        if data is not None:
            json_ok = True
            found = []

            def walk(node):
                if isinstance(node, dict):
                    if isinstance(node.get("coupons"), list):
                        found.extend(node["coupons"])
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for value in node:
                        walk(value)

            walk(data)
            for raw_coupon in found:
                coupon = _coupon_from_json(raw_coupon)
                if coupon:
                    coupons.append(coupon)

    if not json_ok:
        coupons = _coupons_from_cards(html)

    unique, seen = [], set()
    for coupon in coupons:
        if coupon["id"] in seen:
            continue
        seen.add(coupon["id"])
        unique.append(coupon)
    return unique


def coupon_text(coupon):
    lines = ["🎟️ CUPOM MERCADO LIVRE", "",
             f"🏪 {coupon.get('seller')}",
             f"💸 {coupon.get('title')}"]
    if coupon.get("min_amount"):
        lines.append(f"🛒 {coupon['min_amount']}")
    if coupon.get("expiration"):
        lines.append(f"📅 Válido até {coupon['expiration']}")
    if coupon.get("scarcity"):
        lines.append(f"⏳ {coupon['scarcity']}")
    if coupon.get("total_items"):
        lines.append(f"📦 {coupon['total_items']} produto(s) elegível(is)")
    return "\n".join(lines)


def post_coupon(coupon, chat_id=None):
    target = coupon.get("link") or ML_COUPONS_URL
    link, error = generate_affiliate_link(
        target, None, f"Cupom {coupon.get('seller')} {coupon.get('title')}")
    if not link:
        notify_link_failure(target, f"Cupom {coupon.get('seller')}", error)
        return False
    keyboard = {"inline_keyboard": [[{"text": "🎟️ Ativar cupom", "url": link}]]}
    ok = send_message(coupon_text(coupon), chat_id=chat_id,
                      photo_url=coupon.get("icon") or None, reply_markup=keyboard)
    if ok:
        log(f"🎟️ Cupom publicado: {coupon.get('seller')} {coupon.get('title')}")
    return bool(ok)


def cupons_cycle(chat_id=None):
    """Publica no grupo os cupons ativos que ainda não foram enviados."""
    if not control_enabled("coupons"):
        log("⏸️ Cupons desligados no painel.")
        return 0
    with COUPON_LOCK:
        page = browser_get(ML_COUPONS_URL, wait=6)
        if page is None:
            log("⚠️ Cupons: não consegui abrir a página do ML.")
            return 0
        html = page.text or ""
        final_url = getattr(page, "url", "") or ""
        low = html.lower()
        if ("login/identification" in final_url.lower()
                or "digite seu e-mail" in low):
            log("⚠️ Cupons: a página pediu login — rode --login-browser no Kali.")
            return 0
        coupons = extract_ml_coupons(html)
        if not coupons:
            log("🎟️ Cupons: nenhum cupom ativo encontrado.")
            return 0

        state = load_json(CUPONS_FILE, {})
        limite = time.time() - 90 * 86400
        for key in list(state):
            entry = state.get(key) or {}
            if float(entry.get("at") or 0) < limite:
                state.pop(key, None)

        novos = [c for c in coupons if c["id"] not in state]
        if not novos:
            log(f"🎟️ Cupons: {len(coupons)} ativo(s), nenhum novo.")
            return 0

        enviados = 0
        for coupon in novos[:CUPOM_POSTS_PER_CYCLE]:
            if not post_coupon(coupon, chat_id=chat_id or TELEGRAM_CHAT_ID):
                log(f"⏭️ Cupom não publicado: {coupon.get('seller')}.")
                break
            state[coupon["id"]] = {
                "seller": coupon.get("seller"),
                "title": coupon.get("title"),
                "at": int(time.time()),
                "exp": coupon.get("expiration", ""),
            }
            save_json(CUPONS_FILE, state)
            enviados += 1
            if enviados < CUPOM_POSTS_PER_CYCLE and CUPOM_DELAY > 0:
                time.sleep(CUPOM_DELAY)
        log(f"🎟️ Cupons: {enviados} novo(s) publicado(s) de {len(coupons)} ativo(s).")
        return enviados


# --------------------------------------------------------------------------
# Chat privado
# --------------------------------------------------------------------------

HELP = (
    "🤖 *Vagante Promoções*\n\n"
    "Envie o link JÁ com seu código de afiliado: eu leio título, preço e imagem "
    "e publico no canal e na fila do Instagram — o link vai como veio, sem "
    "passar pelo gerador.\n\n"
    "Comandos:\n"
    "/start — esta ajuda\n"
    "/canal <link> — publica direto no canal\n"
    "/canal — publica o último link que você enviou\n"
    "/preco <valor> <link> — monta o post com preço manual\n"
    "/buscar <termo> — busca ofertas do termo (essas sim usam o gerador)\n"
    "/cupons — busca cupons ativos no ML e publica os novos no grupo\n"
    "/igcheck — (dono) confere token e permissão de comentários do Instagram\n"
    "/diagcupons — (dono) captura o HTML da página de cupons do ML\n"
    "/lojas — quais lojas do ML o bot está usando\n"
    "/status — diagnóstico das fontes\n"
    "/ajuda — esta ajuda"
)

# Ultimo produto tratado por chat, para permitir /canal sem link
LAST_PRODUCT = {}


def handle_private_message(message):
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id"))
    text = (message.get("text") or message.get("caption") or "").strip()
    if not text:
        return
    message_id = message.get("message_id")
    log(f"💬 Privado: {text[:70]}")

    if text.startswith("/start") or text.startswith("/ajuda"):
        send_message(HELP, chat_id=chat_id, reply_to=message_id)
        return

    if text.startswith("/status"):
        sheet_state = "OK" if fetch_sheet_products() else "sem itens"
        lines = [
            "📡 *Status das fontes*",
            f"• Internet: {'ONLINE' if NET_STATE.get('online', True) else 'OFFLINE — ciclos pausados'}",
            f"• Planilha (Sheets): {sheet_state}",
            f"• Proxy: {PROBE_STATE['msg'] if PROXIES else 'não configurado (ML/Shopee ficam bloqueados)'}",
            f"• Navegador: {'CDP' if IS_ANDROID else ('Selenium' if USE_SELENIUM else 'desligado')}"
            f" — {_CDP['msg'] if IS_ANDROID else SELENIUM_STATE['msg']}",
            f"• Gerador ML: {generator_label('ml')} | Shopee: {generator_label('shopee')} | "
            f"Amazon: {generator_label('amazon')}",
            "• Login dos portais: `python bot.py --login-browser`",
            f"• Filtro: R$ {brl(MIN_PRICE)}–{brl(MAX_PRICE)}"
            f"{f' | desconto mín. {MIN_DISCOUNT:.0f}%' if MIN_DISCOUNT > 0 else ''}",
            f"• Lojas ML: {', '.join(known_stores()) or 'nenhuma (defina ML_STORES)'}",
            f"• Mercado Livre: {'BLOQUEADO' if 'www.mercadolivre.com.br' in BLOCKED_SOURCES else 'liberado'}",
            f"• Shopee: {'BLOQUEADO' if 'shopee.com.br' in BLOCKED_SOURCES else 'liberado'}",
            f"• Amazon: {'BLOQUEADO' if 'www.amazon.com.br' in BLOCKED_SOURCES else 'liberado'}",
            f"• Instagram: {'OK' if IG_ACCESS_TOKEN else 'sem token'}",
            f"• Canal: {get_chat_name(TELEGRAM_CHAT_ID)}",
        ]
        send_message("\n".join(lines), chat_id=chat_id, reply_to=message_id)
        return

    if text.startswith("/lojas"):
        aprendidas = load_json(STORES_FILE, [])
        linhas = ["🏬 *Lojas do Mercado Livre em uso*", ""]
        if not ML_STORES and not aprendidas:
            linhas.append("Nenhuma loja configurada.")
            linhas.append("Defina `ML_STORES=seuloja` no .env, ou mande um link")
            linhas.append("de loja no canal que o bot aprende sozinho.")
        else:
            todas = list(ML_STORES) + [s for s in aprendidas if s not in ML_STORES]
            for loja in todas:
                origem = "✅ sua (do .env)" if loja in ML_STORES else "🔎 aprendida no canal"
                itens = store_catalog(ML_STORE_BASE + loja)
                dentro = [i for i in itens if oferta_valida(i)[0]]
                linhas.append(f"• /social/{loja}  — {origem}")
                linhas.append(f"   {len(itens)} produto(s) na vitrine, "
                              f"{len(dentro)} passam no filtro")
                amostra = ", ".join(p["title"][:22] for p in itens[:2])
                if amostra:
                    linhas.append(f"   ex.: {amostra}")
        send_message("\n".join(linhas), chat_id=chat_id, reply_to=message_id)
        return

    if text.startswith("/buscar"):
        query = text.split(" ", 1)[1].strip() if " " in text else ""
        if not query:
            send_message("Uso: /buscar <termo>", chat_id=chat_id, reply_to=message_id)
            return
        send_message(f"🔎 Buscando '{query}'...", chat_id=chat_id, reply_to=message_id)
        found = collect_products(include_scrape=True, search_query=query)
        found = [p for p in found if busca_relevante(p, query)]
        results = rank_ofertas(found)[:5]
        if not results:
            send_message("❌ Nenhuma oferta encontrada. Os sites podem estar bloqueando o acesso "
                         "automático — nesse caso use a planilha.", chat_id=chat_id, reply_to=message_id)
            return
        blocks, falhas = [], 0
        for p in results:
            block = price_block(p.get("price"), p.get("original_price")) or "💰 ver preço no link"
            link, error = generate_affiliate_link(p["permalink"], p.get("price"), p.get("title"))
            if not link:
                falhas += 1
                log(f"⛔ /buscar: sem link de afiliado para {p['title'][:50]} ({error})")
                continue
            blocks.append(f"📦 {p['title'][:80]}\n{block}\n🔗 {link}")
        if not blocks:
            send_message("❌ Encontrei ofertas, mas o gerador de link falhou. "
                         "Confira o login dos portais (python bot.py --login-browser).",
                         chat_id=chat_id, reply_to=message_id)
            return
        texto = "\n\n".join(blocks)
        if falhas:
            texto += f"\n\n⚠️ {falhas} oferta(s) sem link de afiliado foram omitidas."
        send_message(texto, chat_id=chat_id, reply_to=message_id)
        return

    if text.startswith("/cupons"):
        send_message("🎟️ Buscando cupons ativos no Mercado Livre...",
                     chat_id=chat_id, reply_to=message_id)
        enviados = cupons_cycle()
        if enviados:
            resposta = f"✅ {enviados} cupom(ns) novo(s) publicado(s) no grupo."
        else:
            resposta = ("ℹ️ Nenhum cupom novo. Se a página pedir login, rode "
                        "`python bot.py --login-browser` e tente de novo.")
        send_message(resposta, chat_id=chat_id, reply_to=message_id)
        return

    if text.startswith("/igcheck"):
        admin = env("ADMIN_CHAT_ID")
        if admin and str(chat_id) != str(admin):
            send_message("⛔ Comando restrito ao dono.", chat_id=chat_id, reply_to=message_id)
            return
        send_message(instagram_diagnostico(), chat_id=chat_id, reply_to=message_id)
        return

    if text.startswith("/diagcupons"):
        admin = env("ADMIN_CHAT_ID")
        if admin and str(chat_id) != str(admin):
            send_message("⛔ Comando restrito ao dono.", chat_id=chat_id, reply_to=message_id)
            return
        send_message("🔎 Abrindo as páginas de cupons no navegador do bot...",
                     chat_id=chat_id, reply_to=message_id)
        enviados = 0
        for nome, url in (("ofertas_cupons", ML_COUPONS_URL),
                          ("promocoes", ML_PROMOS_URL)):
            page = browser_get(url, wait=6)
            if page is None:
                send_message(f"❌ Não consegui abrir {url}.", chat_id=chat_id,
                             reply_to=message_id)
                continue
            html = page.text or ""
            path = BASE_DIR / f"cupons_debug_{nome}.html"
            path.write_text(html, encoding="utf-8", errors="replace")
            low = html.lower()
            url_final = getattr(page, "url", "") or ""
            login = ("login/identification" in url_final.lower()
                     or "digite seu e-mail" in low
                     or "iniciar sessão" in low or "iniciar sessao" in low)
            bloqueio = "hubo un error accediendo" in low
            resumo = (f"📄 Página de cupons capturada\n"
                      f"• URL: {url_final}\n"
                      f"• Tamanho: {len(html)} caracteres\n"
                      f"• Login: {'SIM — entre no ML pelo --login-browser' if login else 'parece logado'}\n"
                      f"{'• ML devolveu página de ERRO/bloqueio' + chr(10) if bloqueio else ''}"
                      f"• Arquivo: {path.name}")
            if send_document(path, chat_id=chat_id, caption=resumo):
                enviados += 1
            else:
                send_message(resumo + f"\n\n⚠️ Não consegui enviar o arquivo; copie {path} do servidor.",
                             chat_id=chat_id, reply_to=message_id)
        send_message(f"📎 {enviados} arquivo(s) enviado(s). Me mande o(s) HTML(s) "
                     "para eu escrever o parser dos cupons.", chat_id=chat_id,
                     reply_to=message_id)
        return

    urls = re.findall(r"https?://[^\s]+", text)
    url = urls[0].rstrip(".,)") if urls else None

    forced_price = None
    manual = re.match(r"^/preco\s+([\d\.,]+)\s+(https?://.+)$", text, re.S)
    if manual:
        forced_price = parse_money(manual.group(1))
        url = manual.group(2).strip()

    # /canal sem link republica o ultimo produto guardado na sessao
    if url is None and text.startswith("/canal"):
        last = LAST_PRODUCT.get(chat_id)
        if not last:
            send_message("❓ Envie primeiro um link de produto. Depois use `/canal` "
                         "sozinho para publicar o ultimo.",
                         chat_id=chat_id, reply_to=message_id)
            return
        if publish(last, announce_instagram=True):
            send_message(f"✅ Publicado no canal: {last['title'][:60]}",
                         chat_id=chat_id, reply_to=message_id)
        else:
            send_message("⛔ Não publiquei: o gerador de link de afiliado falhou.\n"
                         "Rode `python bot.py --login-browser` para renovar a sessão.",
                         chat_id=chat_id, reply_to=message_id)
        return

    if url is None:
        send_message("❓ Envie um link de produto ou use /ajuda.", chat_id=chat_id, reply_to=message_id)
        return

    if not is_product_url(url) and forced_price is None:
        send_message("⚠️ Esse link não é de Mercado Livre, Shopee ou Amazon.\n"
                     "Envie um link de produto ou use /buscar <termo>.",
                     chat_id=chat_id, reply_to=message_id)
        return

    send_message("🔍 Extraindo preço...", chat_id=chat_id, reply_to=message_id)
    data = extract_product(url)

    price = forced_price if forced_price is not None else data.get("price")
    old = None if forced_price is not None else data.get("original_price")
    title = data.get("title") or "Oferta Especial"
    image = data.get("image") or ""
    # O link que o dono manda ja e o link de afiliado dele: entra no link so
    # para ler titulo/preco/imagem e publica o link COMO VEIO, sem
    # desembrulhar nem passar pelo gerador.
    permalink = url

    if price is None:
        send_message(
            f"⚠️ Não consegui ler o preço de *{title}* automaticamente.\n\n"
            "O marketplace está bloqueando acesso automatizado (anti-bot). "
            "Verifique o proxy no /status.\n\n"
            "Use o comando manual:\n"
            f"`/preco 89,90 {permalink}`",
            chat_id=chat_id, reply_to=message_id,
        )
        return

    lines = [f"📦 *{title}*", ""]
    block = price_block(price, old)
    if block:
        lines += block.split("\n") + [""]
    lines += [f"🔗 {permalink}", "",
              f"✅ Preço encontrado: **R$ {brl(price)}**"]
    send_message("\n".join(lines), chat_id=chat_id, photo_url=image or None, reply_to=message_id)

    product = {"id": "pv_" + hashlib.md5(permalink.encode()).hexdigest()[:10],
               "title": title, "price": price, "original_price": old,
               "permalink": permalink, "affiliate_link": permalink,
               "thumbnail": image, "source": "privado"}
    LAST_PRODUCT[chat_id] = product

    # Link no privado publica direto no canal e tenta entrar na fila do Instagram.
    if publish(product, announce_instagram=True):
        if product.get("ig_queued"):
            extra = " e na fila do Instagram"
        elif image:
            extra = " (Instagram: fora do filtro)"
        else:
            extra = " (sem imagem; IG ignorado)"
        send_message(f"✅ Publicado no canal{extra}.", chat_id=chat_id, reply_to=message_id)
    else:
        send_message("⛔ Não publiquei no canal. Confira o /status e os logs.",
                     chat_id=chat_id, reply_to=message_id)


def _handle_private_async(message):
    """Roda o tratamento numa thread para não travar o long polling."""
    try:
        handle_private_message(message)
    except Exception as exc:
        log(f"⚠️ Erro ao tratar mensagem privada: {type(exc).__name__}: {exc}")


def private_listener():
    """Escuta o chat privado via long polling da Bot API."""
    if not TELEGRAM_TOKEN:
        return
    log("👂 Escutador do chat privado iniciado.")
    offset = load_json(OFFSET_FILE, 0)
    offset = int(offset or 0)

    if not offset:
        try:
            pending = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                                   params={"offset": 0, "limit": 1, "timeout": 0},
                                   timeout=25).json().get("result", [])
            offset = pending[-1]["update_id"] + 1 if pending else 0
        except Exception:
            offset = 0
        if offset:
            save_json(OFFSET_FILE, offset)
            log(f"   Offset inicial: {offset} (mensagens antigas ignoradas)")

    falhas = 0
    ultimo_aviso = 0.0
    while True:
        if not NET_STATE.get("online", True):
            time.sleep(15)
            continue
        try:
            resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                                params={"offset": offset, "timeout": 30}, timeout=60)
            if resp.status_code != 200:
                falhas += 1
                agora = time.time()
                if falhas == 1 or agora - ultimo_aviso >= 300:
                    detalhe = _redact(resp.text)[:120]
                    log(f"⚠️ Listener privado: HTTP {resp.status_code} {detalhe}")
                    ultimo_aviso = agora
                time.sleep(min(60, 5 * (2 ** min(falhas - 1, 4))))
                continue

            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                chat = message.get("chat") or {}
                if chat.get("type") != "private":
                    continue
                threading.Thread(target=_handle_private_async, args=(message,),
                                 daemon=True).start()

            if offset:
                save_json(OFFSET_FILE, offset)
            if falhas:
                log("✅ Listener privado: conexão restabelecida.")
                falhas = 0
                ultimo_aviso = 0.0
        except Exception as exc:
            falhas += 1
            agora = time.time()
            if falhas == 1 or agora - ultimo_aviso >= 300:
                detalhe = _redact(str(exc))[:200]
                log(f"⚠️ Listener privado: {type(exc).__name__}: {detalhe}")
                ultimo_aviso = agora
            time.sleep(min(60, 5 * (2 ** min(falhas - 1, 4))))


# --------------------------------------------------------------------------
# Monitoramento de canais
# --------------------------------------------------------------------------

def _channel_enqueue(item):
    key = str(item.get("key") or "")
    if not key:
        return False
    titulo = str(item.get("title") or "")
    with CHANNEL_LOCK:
        queue = load_json(CHANNEL_QUEUE_FILE, [])
        if not isinstance(queue, list):
            queue = []
        queue = [q for q in queue if isinstance(q, dict) and q.get("key")]
        if any(q.get("key") == key for q in queue):
            return False
        queue.append(item)
        queue = queue[-CHANNEL_QUEUE_MAX:]
        save_json(CHANNEL_QUEUE_FILE, queue)
        posicao = len(queue)
    log(f"📥 Canal: '{titulo[:40]}' na fila (posição {posicao}).")
    return True


def _post_channel_offer(item):
    titulo = str(item.get("title") or "Oferta")
    linhas = ["🔥 OFERTA EM DESTAQUE", "", f"📦 {titulo}", ""]
    bloco = price_block(item.get("price"), item.get("old"))
    if bloco:
        linhas += bloco.split("\n") + [""]
    linhas += [FOOTER_TEXT]
    keyboard = {
        "inline_keyboard": [[{"text": "💗 Ver Oferta", "url": item.get("link")}]]
    }
    ok = send_message("\n".join(linhas), photo_url=item.get("image") or None,
                      reply_markup=keyboard)
    if not ok:
        return False
    save_to_vitrine({
        "id": item.get("id") or ("ch_" + str(item.get("key"))),
        "title": titulo,
        "price": item.get("price"),
        "original_price": item.get("old"),
        "link": item.get("link"),
        "image": item.get("image") or "",
    })
    return True


def publish_channel_batch():
    if not control_enabled("channels"):
        return 0
    with CHANNEL_LOCK:
        queue = load_json(CHANNEL_QUEUE_FILE, [])
        if not isinstance(queue, list):
            queue = []
        queue = [q for q in queue if isinstance(q, dict) and q.get("key")
                 and q.get("link")]
    lote = queue[:CHANNEL_BATCH_SIZE]
    if not lote:
        return 0
    enviados = 0
    for indice, item in enumerate(lote):
        titulo = str(item.get("title") or "")[:40]
        try:
            ok = _post_channel_offer(item)
        except Exception as exc:
            log(f"⚠️ Canal: falha ao publicar '{titulo}': {type(exc).__name__}: {exc}")
            ok = False
        if ok:
            enviados += 1
            with CHANNEL_LOCK:
                atual = load_json(CHANNEL_QUEUE_FILE, [])
                if not isinstance(atual, list):
                    atual = []
                atual = [q for q in atual if not (isinstance(q, dict)
                                                  and q.get("key") == item.get("key"))]
                save_json(CHANNEL_QUEUE_FILE, atual)
            log(f"✅ Canal: '{titulo}' publicado.")
        else:
            log(f"⏭️ Canal: '{titulo}' mantido na fila.")
        if indice < len(lote) - 1 and CHANNEL_POST_DELAY > 0:
            time.sleep(CHANNEL_POST_DELAY)
    return enviados


def _channel_schedule():
    """Le a agenda do publicador: (estado, ultimo lote, proximo lote)."""
    with CHANNEL_LOCK:
        state = load_json(CHANNEL_STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}

    def _ts(nome):
        try:
            return float(state.get(nome) or 0)
        except (TypeError, ValueError):
            return 0.0

    ultimo = _ts("last_batch_at")
    proximo = _ts("next_batch_at")
    if not proximo and ultimo:
        proximo = ultimo + CHANNEL_BATCH_INTERVAL
    return state, ultimo, proximo


def channel_publisher_loop():
    if not SOURCE_CHANNELS:
        return
    minutos = int(CHANNEL_BATCH_INTERVAL // 60) or 1
    log(f"📤 Canal: até {CHANNEL_BATCH_SIZE} oferta(s) a cada {minutos} min.")
    time.sleep(5)
    while True:
        if not control_enabled("channels"):
            time.sleep(15)
            continue
        _, ultimo, proximo = _channel_schedule()
        agora = time.time()
        if proximo and proximo > agora:
            time.sleep(min(proximo - agora, CHANNEL_BATCH_INTERVAL))
            continue
        try:
            publicados = publish_channel_batch()
        except Exception as exc:
            log(f"⚠️ Canal: publicador falhou: {type(exc).__name__}: {exc}")
            publicados = 0
        agora = time.time()
        estado = {"last_batch_at": agora if publicados else ultimo,
                  "next_batch_at": agora + CHANNEL_BATCH_INTERVAL}
        with CHANNEL_LOCK:
            save_json(CHANNEL_STATE_FILE, estado)


def channel_listener():
    """Espelha ofertas de canais do Telegram. Opcional: requer telethon + sessão já autenticada."""
    api_id, api_hash = env("API_ID"), env("API_HASH")
    if not SOURCE_CHANNELS:
        return
    if not (api_id.isdigit() and api_hash):
        log("⏭️  Monitoramento de canais desativado (API_ID/API_HASH ausentes ou inválidos).")
        return
    try:
        import asyncio
        from telethon import TelegramClient, events
    except Exception:
        log("⏭️  Telethon não instalado — monitoramento de canais desativado.")
        return

    session_path = str(BASE_DIR / "session_promos")
    session_file = Path(session_path + ".session")

    async def run():
        client = TelegramClient(session_path, int(api_id), api_hash)

        if "--login" in sys.argv or not session_file.exists():
            if not session_file.exists() and "--login" not in sys.argv:
                log("⚠️ Telethon: sem sessão local. Rode  python bot.py --login  uma vez "
                    "para habilitar o monitoramento dos canais.")
                return
            log("🔐 Autenticando no Telethon (informe o telefone e o código)…")
            await client.start()
            log("✅ Sessão criada. Reinicie o bot para usar o monitoramento.")
            await client.disconnect()
            return

        await client.connect()
        if not await client.is_user_authorized():
            log("⚠️ Telethon: sessão expirada. Rode  python bot.py --login  novamente.")
            await client.disconnect()
            return

        @client.on(events.NewMessage(chats=SOURCE_CHANNELS))
        async def handler(event):
            raw = event.raw_text or ""
            if len(raw) < 15:
                return
            if not control_enabled("channels"):
                return
            PANEL_STATE["last_listener"] = time.time()

            urls = re.findall(r"https?://[^\s]+", raw)
            for u in urls:
                remember_store(expand_url(u.rstrip(".,)")))
            product_urls = [u for u in urls if is_product_url(u)]
            if not product_urls:
                return
            product_url = product_urls[0].rstrip(".,)")

            # 1. Preco (atual e o "de") sao lidos ANTES de montar o link: o link
            # de loja so vira link de produto se a busca souber o que procurar.
            price, old_price = prices_from_text(raw)
            _lines = [l.strip() for l in raw.split("\n") if l.strip()]
            # O parceiro escreve uma frase de divulgacao na 1a linha; o titulo
            # vem na linha de baixo. title_from_lines() pula a frase.
            title_guess = title_from_lines(_lines)

            # 3. Foto: so usa a oficial da pagina do produto. A foto do post
            #    do parceiro costuma vir com marca d'agua da loja; se a pagina
            #    nao devolver imagem, a oferta e descartada em vez de publicar
            #    a marca d'agua de terceiros.
            data = extract_product(product_url)
            title = data.get("title") or ""
            image = data.get("image") or ""
            price = price or data.get("price")
            old_price = old_price or data.get("original_price")
            canonical = data.get("link") or product_url

            if not image and event.photo:
                log("⏭️ Canal: sem imagem oficial; oferta descartada para não "
                    "publicar a foto com marca d'água do parceiro.")
                return

            if not title:
                # ultimo recurso: qualquer linha util, senao um placeholder
                title = title_guess or (_lines[0][:150] if _lines else "Oferta")

            log(f"📡 Canal: {title[:45]} | foto={'sim' if image else 'nao'} "
                f"| preco={brl(price)} | de={brl(old_price)}")

            # 2. Gera o link no portal oficial. Sem link de afiliado a oferta
            #    NÃO é publicada: melhor perder a oferta do que divulgar de graça.
            link, link_aviso = generate_affiliate_link(product_url, price, title)
            if not link:
                log(f"⛔ Canal: sem link de afiliado ({link_aviso})")
                notify_link_failure(product_url, title, link_aviso)
                return

            key = hashlib.md5(canonical.split("?")[0].encode()).hexdigest()[:12]
            _channel_enqueue({
                "key": key,
                "id": "ch_" + key,
                "title": title,
                "price": price,
                "old": old_price,
                "image": image or "",
                "link": link,
                "url": canonical,
                "queued_at": int(time.time()),
            })

        log(f"👂 Telethon conectado: {', '.join(SOURCE_CHANNELS)}")
        try:
            await client.run_until_disconnected()
        finally:
            await client.disconnect()

    try:
        asyncio.run(run())
    except Exception as exc:
        log(f"⚠️ Telethon: {exc}")


# --------------------------------------------------------------------------
# Ciclos programados
# --------------------------------------------------------------------------

def telegram_cycle():
    if not control_enabled("telegram"):
        log("⏸️ Ciclo do Telegram desligado no painel.")
        return
    PANEL_STATE["last_telegram"] = time.time()
    log("\n🤖 Ciclo do Telegram: planilha + raspagem")
    BLOCKED_SOURCES.clear()
    proxy_health()
    seen = load_json(SEEN_FILE)
    products = collect_products(include_scrape=control_enabled("scrape"),
                                include_sheet=control_enabled("sheet"))

    new_sheet = [p for p in products if p["source"] == "planilha" and p["id"] not in seen]
    if new_sheet:
        log(f"📊 {len(new_sheet)} produto(s) novo(s) da planilha.")
        for product in new_sheet:
            publish(product, announce_instagram=True)
            time.sleep(8)
    else:
        log("📊 Nenhum produto novo na planilha.")

    sent = 0
    for product in [p for p in products if p["id"] not in seen]:
        if sent >= POSTS_PER_CYCLE:
            break
        if publish(product, announce_instagram=True):
            sent += 1
            time.sleep(8)
    log(f"✅ Ciclo concluído: {sent} oferta(s) da raspagem publicada(s).\n")

    try:
        cupons_cycle()
    except Exception as exc:
        log(f"⚠️ Ciclo de cupons: {type(exc).__name__}: {exc}")


def instagram_cycle():
    if not control_enabled("instagram"):
        log("⏸️ Instagram desligado no painel.")
        return
    PANEL_STATE["last_instagram"] = time.time()
    enviados = 0
    while enviados < IG_POSTS_PER_CYCLE:
        # Relê a fila a cada post: se o painel excluir um item enquanto o bot
        # espera entre publicações, ele não deve ser postado mesmo assim.
        with IG_QUEUE_LOCK:
            queue = load_json(IG_QUEUE_FILE, [])
        if not isinstance(queue, list) or not queue:
            if not enviados:
                log("📸 Instagram: fila vazia.")
            break
        item = queue[0]
        qid = _ig_queue_qid(item)
        pct = item.get("pct")
        link = _ig_queue_link(item)
        linhas = [f"🔥 {item['title']}", ""]
        bloco = price_block(item.get("price"), item.get("old"))
        if bloco:
            linhas += [bloco, ""]
        linhas.append("🔗 Link no primeiro comentário ou na BIO!" if link else "🔗 Link na bio!")
        linhas += ["", ig_hashtags()]
        caption = "\n".join(linhas)
        public_url = arte_para_publicar(item.get("image"), item.get("price"), item.get("old"), pct, item.get("title"))
        if not post_to_instagram(public_url, caption, comment=link or None):
            log("⏭️ Post do Instagram não concluído; item mantido na fila.")
            break
        with IG_QUEUE_LOCK:
            atual = load_json(IG_QUEUE_FILE, [])
            if not isinstance(atual, list):
                atual = []
            atual = [x for x in atual
                     if not (isinstance(x, dict) and _ig_queue_qid(x) == qid)]
            save_json(IG_QUEUE_FILE, atual)
        enviados += 1
        if atual and enviados < IG_POSTS_PER_CYCLE and IG_POST_DELAY > 0:
            time.sleep(IG_POST_DELAY)
    if enviados:
        log(f"📸 Instagram: {enviados} post(s) publicado(s) neste ciclo.")


def internet_online(timeout=10):
    """Internet utilizavel? Testa o Telegram (que nao usa o proxy do ML).

    O proxy do .env existe para o Mercado Livre; o Telegram e a API do
    Instagram saem direto. Se o Telegram nao responde, para os nossos
    propositos estamos sem internet.
    """
    if TELEGRAM_TOKEN:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe",
                             timeout=timeout)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    for url in ("https://connectivitycheck.gstatic.com/generate_204",
                "https://www.google.com/generate_204"):
        try:
            if requests.get(url, timeout=timeout).status_code in (200, 204):
                return True
        except Exception:
            continue
    return False


def _vitrine_publica():
    vitrine = load_json(VITRINE_FILE, [])
    if not isinstance(vitrine, list):
        return []
    saida = []
    for item in vitrine[:40]:
        if not isinstance(item, dict):
            continue
        saida.append({
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or "")[:120],
            "price": item.get("price"),
            "link": str(item.get("link") or ""),
            "image": str(item.get("image") or ""),
            "time": str(item.get("time") or ""),
        })
    return saida


def _proximo_ciclo(ultimo, intervalo, ativo, agora):
    """Horario do proximo ciclo; None quando a funcao esta desligada."""
    if not ativo:
        return None
    try:
        ultimo = float(ultimo or 0)
    except (TypeError, ValueError):
        ultimo = 0.0
    return ultimo + intervalo if ultimo else agora


def panel_status():
    fila = _ig_queue_publica()
    vistos = load_json(SEEN_FILE, [])
    flags = control_snapshot()
    agora = time.time()
    _, _, proximo_lote = _channel_schedule()
    return {
        "updated_at": int(agora),
        "online": bool(NET_STATE.get("online", True)),
        "net": NET_STATE.get("msg", ""),
        "flags": flags,
        "last_telegram": PANEL_STATE.get("last_telegram", 0.0),
        "last_instagram": PANEL_STATE.get("last_instagram", 0.0),
        "last_listener": PANEL_STATE.get("last_listener", 0.0),
        "next_telegram": _proximo_ciclo(
            PANEL_STATE.get("last_telegram", 0.0), INTERVAL_TELEGRAM,
            flags.get("telegram", True), agora),
        "next_instagram": _proximo_ciclo(
            PANEL_STATE.get("last_instagram", 0.0), INTERVAL_INSTAGRAM,
            flags.get("instagram", True), agora),
        "next_channels": ((proximo_lote or agora)
                          if flags.get("channels", True) and SOURCE_CHANNELS
                          else None),
        "seen": len(vistos) if isinstance(vistos, list) else 0,
        "ig_queue": len(fila),
        "ig_queue_items": fila,
        "vitrine": _vitrine_publica(),
        "logs": list(LOG_BUFFER)[-60:],
    }


def panel_execute(kind, payload):
    payload = payload if isinstance(payload, dict) else {}
    if kind in ("run_telegram", "run_cycle"):
        request_run("telegram")
        return "ciclo do Telegram agendado"
    if kind == "run_instagram":
        request_run("instagram")
        return "ciclo do Instagram agendado"
    if kind in ("delete_vitrine", "vitrine_delete"):
        ok, msg = delete_from_vitrine(payload.get("id"),
                                      bool(payload.get("remove_from_seen")))
        return ("ok: " if ok else "erro: ") + msg
    if kind in ("delete_ig_queue", "ig_queue_delete"):
        ok, msg = delete_from_ig_queue(payload.get("qid"))
        return ("ok: " if ok else "erro: ") + msg
    if kind == "set_flags":
        apply_control_flags(payload.get("flags") or payload)
        return "flags aplicadas"
    raise ValueError(f"comando desconhecido: {kind}")


def main():
    log("=" * 52)
    log(">>> BOT VAGANTE PROMOÇÕES <<<")
    log("=" * 52)

    if "--login" in sys.argv:
        log("🔐 Modo de autenticação do Telethon — informe telefone e código quando solicitado.")
        channel_listener()
        return

    if "--login-browser" in sys.argv:
        browser_login_session()
        return

    if not check_credentials():
        return
    resolve_ig_user_id()
    if not HAVE_CURL_CFFI:
        log("⚠️ curl_cffi ausente — a raspagem pode ser bloqueada. Instale com: pip install curl_cffi")
    if not USE_SELENIUM and not IS_ANDROID:
        log("⚠️ Sem Selenium — o /ofertas do ML vai ficar bloqueado (o ML só abre para Chrome).")
    if IS_ANDROID:
        try:
            import websocket  # noqa: F401
            log("✅ websocket-client OK — o /ofertas será lido via Chromium CDP.")
        except Exception:
            log("⚠️ websocket-client ausente: rode `pip install websocket-client`, "
                "senão o /ofertas do ML não abre e o bot usa só /social/<loja>.")
        _bin = chromium_binary()
        if _bin:
            log(f"ℹ️ Navegador: {_bin}")
        else:
            log(f"⚠️ Chromium NÃO ENCONTRADO. No Termux o pacote é 'chromium' "
                f"e vive no repo x11 — rode: {CHROMIUM_HINT}")
    if PROXIES:
        proxy_health()
    else:
        log("⚠️ Sem PROXY no .env — Mercado Livre e Shopee bloqueiam este IP e não retornam produtos.")
    if not TEMPLATE_FILE.exists():
        log("ℹ️  Sem template.png — será usado o card gerado automaticamente.")

    if "--once" in sys.argv:
        telegram_cycle()
        instagram_cycle()
        log("✅ Execução única concluída.")
        return

    threading.Thread(target=private_listener, daemon=True).start()
    threading.Thread(target=channel_listener, daemon=True).start()
    threading.Thread(target=channel_publisher_loop, daemon=True).start()

    try:
        from panel_sync import start_panel_sync
        start_panel_sync(apply_control_flags, panel_execute, panel_status, log)
    except Exception as exc:
        log(f"⚠️ Painel: não iniciou ({type(exc).__name__}: {exc})")

    last_telegram = 0.0
    last_instagram = 0.0
    last_net_check = 0.0
    online = True
    offline_since = 0.0
    disparar_telegram = True          # primeiro ciclo logo apos subir
    disparar_instagram = False
    time.sleep(5)

    while True:
        try:
            now = time.time()

            # --- Internet: quando ela volta, os ciclos rodam na hora ---
            # Sem isso o timer avancava mesmo com o ciclo falhando, e o bot
            # ficava ate 1 hora sem fazer nada depois que a rede voltava.
            if now - last_net_check >= 60:
                last_net_check = now
                try:
                    agora_online = internet_online()
                except Exception:
                    agora_online = online
                NET_STATE["online"] = agora_online
                if not agora_online and online:
                    offline_since = now
                    log("📴 Sem internet — ciclos pausados. Vou retomar assim que voltar.")
                elif agora_online and not online:
                    log(f"📶 Internet voltou depois de {int((now - offline_since) / 60)} min. "
                        f"Rodando o ciclo agora mesmo.")
                    disparar_telegram = True       # compensa o tempo perdido
                    disparar_instagram = True
                online = agora_online

            if online:
                if take_run("telegram"):
                    disparar_telegram = True
                if take_run("instagram"):
                    disparar_instagram = True
                if control_enabled("telegram") and (disparar_telegram or
                                                    now - last_telegram >= INTERVAL_TELEGRAM):
                    telegram_cycle()
                    last_telegram = now
                    disparar_telegram = False
                if control_enabled("instagram") and (disparar_instagram or
                                                     now - last_instagram >= INTERVAL_INSTAGRAM):
                    instagram_cycle()
                    last_instagram = now
                    disparar_instagram = False
        except Exception as exc:
            log(f"⚠️ Erro no ciclo principal: {exc}")
        time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Encerrado pelo usuário.")
        sys.exit(0)
