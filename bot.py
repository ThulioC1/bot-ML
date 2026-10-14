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


def log(msg):
    print(f"[{time.strftime('%d/%m %H:%M:%S')}] {msg}", flush=True)


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

FOOTER_TEXT = env("FOOTER", "🔗 Links afiliados. Gostou da oferta? Compartilhe nosso grupo: https://t.me/vagantepromo")

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

SEEN_FILE = BASE_DIR / "seen.json"
IG_SEEN_FILE = BASE_DIR / "ig_seen.json"
VITRINE_FILE = BASE_DIR / "vitrine.json"
OFFSET_FILE = BASE_DIR / "telegram_offset.json"
STORES_FILE = BASE_DIR / "lojas.json"
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


def store_catalog(store_url):
    """Le o catalogo da loja (/social/user) e devolve [{title, price, url, image}]."""
    if not store_url:
        return []
    cache_key = "cat::" + strip_params(store_url, list(ML_OWN_TAGS))
    cached = URL_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    resp = http_get(store_url, timeout=25)
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
                                  "url": product_url, "image": image})
            except Exception:
                continue
    URL_CACHE[cache_key] = (time.time(), items)
    log(f"📦 Catálogo da loja: {len(items)} produto(s)")
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


def affiliate_link(url, price=None, title=None):
    """Aplica o identificador de afiliado conforme o marketplace.

    Devolve (link, aviso). O aviso e preenchido quando o link foi expandido
    mas aponta para uma LOJA — que ignora a tag de afiliado, ou seja, nao
    gera comissao. Nesse caso `link` vem sem tag para naoIludir ninguem.
    """
    if not url:
        return url, ""
    url = url.rstrip(".,)")
    low = url.lower()
    aviso = ""

    # ---- Mercado Livre (inclui meli.la, amzn-like encurtado) ----
    if "meli.la" in low or "mercadolivre" in low or "mercadolibre" in low:
        tracking = ({"matt_word": ML_MATT_WORD, "matt_tool": ML_MATT_TOOL}
                    if (ML_MATT_WORD and ML_MATT_TOOL) else {})
        expanded = expand_url(url)
        if expanded != url:
            url = expanded
            low = url.lower()
        # tira a tag de afiliado de quem ja tinha sharing o link
        url = strip_params(url, list(ML_OWN_TAGS))
        low = url.lower()

        if is_store_link(url):
            item = resolve_store_link(url, price, title)
            if item:
                return append_query(item["url"], tracking), ""
            aviso = (f"⛔ link de LOJA do ML ({urllib.parse.urlparse(url).path}) "
                     f"ignora a tag de afiliado — nao gera comissao sua.")
            return url, aviso
        if not tracking:
            return url, "⛔ ML_MATT_WORD/ML_MATT_TOOL ausentes no .env."
        return append_query(url, tracking), aviso

    # ---- Shopee (inclui shope.ee / s.shopee.com) ----
    if "shopee" in low or "shope.ee" in low:
        expanded = expand_url(url)
        if expanded != url:
            url = expanded
        url = strip_params(url, list(SHOPEE_OWN_TAGS))
        if not SHOPEE_TAG:
            return url, "⛔ SHOPEE_TAG ausente no .env."
        return append_query(url, {"smtt": SHOPEE_TAG}), aviso

    # ---- Amazon (inclui amzn.to / a.co) ----
    if "amazon" in low or "amzn.to" in low or "a.co" in low:
        expanded = expand_url(url)
        if expanded != url:
            url = expanded
        url = strip_params(url, list(AMAZON_OWN_TAGS))
        if not AMAZON_TAG:
            return url, "⛔ AMAZON_TAG ausente no .env."
        return append_query(url, {"tag": AMAZON_TAG}), aviso

    return url, aviso


# --------------------------------------------------------------------------
# Vercel Blob
# --------------------------------------------------------------------------

def upload_to_blob(file_path, remote_name):
    if not BLOB_TOKEN or not Path(file_path).exists():
        return None
    try:
        with open(file_path, "rb") as fh:
            payload = fh.read()
        resp = requests.put(
            f"https://blob.vercel-storage.com/{remote_name}",
            data=payload,
            headers={"Authorization": f"Bearer {BLOB_TOKEN}"},
            timeout=45,
        )
        if resp.status_code == 200:
            return resp.json().get("url")
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


def send_message(text, chat_id=None, photo_url=None, reply_to=None):
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN or not chat_id:
        log("⚠️ Token ou Chat ID do Telegram ausentes.")
        return False

    if photo_url:
        payload = {"chat_id": chat_id, "caption": text[:1024]}
        if reply_to:
            payload["reply_to_message_id"] = reply_to

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
    return bool(tg_api("sendMessage", payload))


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


def post_to_instagram(image_url, caption):
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


def selenium_driver():
    """Sobe um Chrome FORA DA TELA. Sem janela o ML devolve a parede anti-bot."""
    global _DRIVER
    if not USE_SELENIUM:
        return None
    with _DRIVER_LOCK:
        if _DRIVER is not None:
            return _DRIVER
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except Exception:
            SELENIUM_STATE["msg"] = "selenium nao instalado (pip install selenium)"
            log(f"⚠️ Selenium: {SELENIUM_STATE['msg']}. Seguindo so com requests.")
            return None
        try:
            opts = Options()
            if SELENIUM_HEADLESS:
                opts.add_argument("--headless=new")
            opts.add_argument("--lang=pt-BR")
            opts.add_argument("--window-size=1400,1000")
            opts.add_argument("--window-position=-32000,-32000")  # real, so fora da vista
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_experimental_option("excludeSwitches", ["enable-automation",
                                                             "useAutomationExtension"])
            opts.add_experimental_option("useAutomationExtension", False)
            _DRIVER = webdriver.Chrome(options=opts)
            _DRIVER.set_page_load_timeout(45)
            SELENIUM_STATE["ok"] = True
            SELENIUM_STATE["msg"] = "Chrome ativo"
            log("✅ Chrome (Selenium) iniciado — o Mercado Livre volta a responder.")
            return _DRIVER
        except Exception as exc:
            SELENIUM_STATE["ok"] = False
            SELENIUM_STATE["msg"] = f"falhou ({type(exc).__name__})"
            log(f"⚠️ Selenium: {SELENIUM_STATE['msg']}. Seguindo so com requests.")
            return None


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


def cdp_get(url, wait=None, timeout=90):
    """Baixa a pagina por CDP e devolve o HTML renderizado, ou None.

    Passos: abre uma aba -> espera o JS rodar -> le document.outerHTML.
    Nunca levanta excecao: devolve None e o ciclo segue com /social/<loja>.
    """
    try:
        return _cdp_get(url, wait, timeout)
    except Exception as exc:
        log(f"⚠️ CDP falhou em {url[:55]}: {type(exc).__name__}: {exc}")
        _CDP["msg"] = f"{type(exc).__name__}"
        return None


def _cdp_get(url, wait=None, timeout=90):
    try:
        import websocket  # websocket-client (python puro, instala no Termux)
    except Exception:
        _CDP["msg"] = "websocket-client ausente (pip install websocket-client)"
        log(f"⚠️ CDP: {_CDP['msg']} — /ofertas indisponível, usando /social/<loja>.")
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

    ws_url = target["webSocketDebuggerUrl"]
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout,
                                         origin=f"http://{CDP_HOST}:{CDP_PORT}")
    except Exception as exc:
        log(f"⚠️ CDP: WebSocket falhou ({type(exc).__name__}). "
            f"Verifique se o Chromium subiu com --remote-allow-origins=*")
        return None

    try:
        ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        ws.send(json.dumps({"id": 2, "method": "Page.navigate",
                            "params": {"url": url}}))

        # Espera o load: o evaluate so faz sentido depois que a pagina montou.
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

        ws.send(json.dumps({
            "id": 3, "method": "Runtime.evaluate",
            "params": {"expression": "document.documentElement.outerHTML",
                       "returnByValue": True},
        }))
        html, deadline = None, time.time() + 45
        while time.time() < deadline:
            try:
                ws.settimeout(10)
                raw = ws.recv()
            except Exception:
                continue                      # segue tentando ate o deadline
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("id") == 3:
                value = ((msg.get("result") or {}).get("result") or {}).get("value")
                if value:
                    html = value
                break
        if not html:
            log(f"⚠️ CDP: JS não devolveu HTML de {url[:55]}")
            return None
        if _is_bot_wall(html[:2500]):
            log(f"⚠️ CDP: o ML bloqueou o Chromium em {url[:55]}")
            return None
        return _Page(html, url)
    finally:
        try:
            ws.close()
        except Exception:
            pass


def cdp_close():
    proc = _CDP.get("proc")
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass
        _CDP["proc"] = None


def browser_get(url, wait=3):
    """HTML de uma pagina, com o plano B ja aplicado.

    requests/curl_cffi -> Chrome de verdade. No PC usa Selenium; no Android
    (onde o Selenium nao existe para arm64) usa CDP direto no Chromium.
    """
    resp = http_get(url)
    head = resp.text[:2000] if resp is not None else ""
    if resp is None or "account-verification" in head or "suspicious-traffic" in head:
        page = selenium_get(url, wait)
        if page is not None:
            return page
        log("↪️ Selenium indisponível — tentando Chromium via CDP.")
        return cdp_get(url, wait=(wait + 3 if wait else CDP_WAIT))
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


def fetch_shopee_products(search_query=None):
    products = []
    keyword = search_query or "ofertas"
    url = (f"https://shopee.com.br/api/v4/search/search_items?by=relevancy"
           f"&keyword={urllib.parse.quote(keyword)}&limit=30&newest=0")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://shopee.com.br/",
        "x-api-source": "pc",
        "x-shopee-language": "pt",
        "x-requested-with": "XMLHttpRequest",
    }
    resp = http_get(url, headers=headers, timeout=20, referer="https://shopee.com.br/")
    if resp is not None and resp.status_code == 200:
        try:
            data = resp.json()
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
    else:
        status = getattr(resp, "status_code", "erro")
        log(f"⚠️ Shopee bloqueada (HTTP {status}). A planilha é a fonte confiável.")

    if products:
        random.shuffle(products)
        log(f"✅ Shopee: {len(products)} produto(s).")
    return products


def fetch_amazon_products(search_query=None):
    products = []
    keyword = search_query or "eletronicos ofertas"
    url = f"https://www.amazon.com.br/s?k={urllib.parse.quote(keyword)}"
    resp = http_get(url, timeout=25, referer="https://www.amazon.com.br/")
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


def collect_products(include_scrape=True, search_query=None):
    products = fetch_sheet_products()
    if search_query:
        products += fetch_mercado_livre_products(search_query) + fetch_shopee_products(search_query) + fetch_amazon_products(search_query)
    elif include_scrape:
        products += fetch_mercado_livre_products() + fetch_shopee_products()
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
    resp = http_get(url, timeout=25)
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
    vitrine = load_json(VITRINE_FILE, [])
    if any(v.get("link") == item.get("link") for v in vitrine[:20]):
        return
    vitrine.insert(0, {
        "id": item["id"],
        "title": item["title"],
        "price": item.get("price"),
        "original_price": item.get("original_price"),
        "link": item["link"],
        "image": item.get("image") or "",
        "time": time.strftime("%d/%m/%Y %H:%M"),
    })
    save_json(VITRINE_FILE, vitrine[:40])
    log(f"📦 Vitrine atualizada ({len(vitrine[:40])} itens).")


# --------------------------------------------------------------------------
# Publicação
# --------------------------------------------------------------------------

def publish(product, chat_id=None, reply_to=None, announce_instagram=False):
    price = product.get("price")
    old = product.get("original_price")
    link, aviso = affiliate_link(product["permalink"], price, product.get("title"))
    title = product.get("title") or "Oferta Especial"

    lines = ["🔥 OFERTA EM DESTAQUE", "", f"📦 {title}", ""]
    block = price_block(price, old)
    if block:
        lines += block.split("\n") + [""]
    if aviso:
        lines += [aviso, ""]
    lines += [f"🛒 Link: {link}"]
    if chat_id is None:
        lines += ["", FOOTER_TEXT]

    text = "\n".join(lines)
    ok = send_message(text, chat_id=chat_id, photo_url=product.get("thumbnail") or None, reply_to=reply_to)

    if ok:
        seen = load_json(SEEN_FILE)
        seen[product["id"]] = {"price": price, "at": time.strftime("%d/%m %H:%M")}
        save_json(SEEN_FILE, seen)
        save_to_vitrine({
            "id": product["id"], "title": title, "price": price,
            "original_price": old, "link": link, "image": product.get("thumbnail") or "",
        })

    if announce_instagram:
        schedule_instagram(product, title, price, old)
    return ok


def schedule_instagram(product, title, price, old):
    pct = discount_pct(price, old)
    image = product.get("thumbnail")
    if not image:
        log("⏭️ Instagram: produto sem imagem.")
        return
    queue = load_json(BASE_DIR / "ig_queue.json", [])
    queue.append({"title": title, "price": price, "old": old, "image": image, "pct": pct})
    save_json(BASE_DIR / "ig_queue.json", queue[-10:])
    log(f"🖼️ Arte do post '{title[:32]}' entrou na fila do Instagram.")


# --------------------------------------------------------------------------
# Chat privado
# --------------------------------------------------------------------------

HELP = (
    "🤖 *Vagante Promoções*\n\n"
    "Envie um link de produto (Mercado Livre, Shopee, Amazon) que eu extraio "
    "o preço e monto o post.\n\n"
    "Comandos:\n"
    "/start — esta ajuda\n"
    "/canal <link> — publica direto no canal\n"
    "/canal — publica o último link que você enviou\n"
    "/preco <valor> <link> — monta o post com preço manual\n"
    "/buscar <termo> — busca ofertas do termo\n"
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
            f"• Planilha (Sheets): {sheet_state}",
            f"• Proxy: {PROBE_STATE['msg'] if PROXIES else 'não configurado (ML/Shopee ficam bloqueados)'}",
            f"• Navegador: {'CDP' if IS_ANDROID else ('Selenium' if USE_SELENIUM else 'desligado')}"
            f" — {_CDP['msg'] if IS_ANDROID else SELENIUM_STATE['msg']}",
            f"• Lojas ML: {', '.join(known_stores()) or 'nenhuma (defina ML_STORES)'}",
            f"• Mercado Livre: {'BLOQUEADO' if 'www.mercadolivre.com.br' in BLOCKED_SOURCES else 'liberado'}",
            f"• Shopee: {'BLOQUEADO' if 'shopee.com.br' in BLOCKED_SOURCES else 'liberado'}",
            f"• Amazon: {'BLOQUEADO' if 'www.amazon.com.br' in BLOCKED_SOURCES else 'liberado'}",
            f"• Instagram: {'OK' if IG_ACCESS_TOKEN else 'sem token'}",
            f"• Canal: {get_chat_name(TELEGRAM_CHAT_ID)}",
        ]
        send_message("\n".join(lines), chat_id=chat_id, reply_to=message_id)
        return

    if text.startswith("/buscar"):
        query = text.split(" ", 1)[1].strip() if " " in text else ""
        if not query:
            send_message("Uso: /buscar <termo>", chat_id=chat_id, reply_to=message_id)
            return
        send_message(f"🔎 Buscando '{query}'...", chat_id=chat_id, reply_to=message_id)
        results = collect_products(include_scrape=True, search_query=query)[:5]
        if not results:
            send_message("❌ Nenhuma oferta encontrada. Os sites podem estar bloqueando o acesso "
                         "automático — nesse caso use a planilha.", chat_id=chat_id, reply_to=message_id)
            return
        blocks = []
        for p in results:
            block = price_block(p.get("price"), p.get("original_price")) or "💰 ver preço no link"
            blocks.append(f"📦 {p['title'][:80]}\n{block}\n🔗 {affiliate_link(p['permalink'])[0]}")
        send_message("\n\n".join(blocks), chat_id=chat_id, reply_to=message_id)
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
        publish({**last, "permalink": affiliate_link(last["permalink"])[0]})
        send_message(f"✅ Publicado no canal: {last['title'][:60]}",
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
    final_link, link_aviso = affiliate_link(data.get("link") or url, price, title)

    if price is None:
        send_message(
            f"⚠️ Não consegli ler o preço de *{title}* automaticamente.\n\n"
            "O marketplace está bloqueando acesso automatizado (anti-bot). "
            "Verifique o proxy no /status.\n\n"
            "Use o comando manual:\n"
            f"`/preco 89,90 {final_link}`",
            chat_id=chat_id, reply_to=message_id,
        )
        return

    lines = [f"📦 *{title}*", ""]
    block = price_block(price, old)
    if block:
        lines += block.split("\n") + [""]
    lines += [f"🔗 {final_link}", "", f"✅ Preço encontrado: **R$ {brl(price)}**"]
    send_message("\n".join(lines), chat_id=chat_id, photo_url=image or None, reply_to=message_id)

    product = {"id": "pv_" + hashlib.md5(final_link.encode()).hexdigest()[:10],
               "title": title, "price": price, "original_price": old,
               "permalink": final_link, "thumbnail": image, "source": "privado"}
    LAST_PRODUCT[chat_id] = product

    if text.startswith("/canal"):
        publish(product)
        send_message("✅ Publicado no canal.", chat_id=chat_id, reply_to=message_id)
    else:
        send_message("💡 Use `/canal` para publicar este produto no canal.",
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

    while True:
        try:
            resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                                params={"offset": offset, "timeout": 30}, timeout=60)
            if resp.status_code != 200:
                time.sleep(5)
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
        except Exception as exc:
            log(f"⚠️ Listener privado: {type(exc).__name__}: {exc}")
            time.sleep(5)


# --------------------------------------------------------------------------
# Monitoramento de canais
# --------------------------------------------------------------------------

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

            urls = re.findall(r"https?://[^\s]+", raw)
            for u in urls:
                remember_store(expand_url(u.rstrip(".,)")))
            product_urls = [u for u in urls if is_product_url(u)]
            if not product_urls:
                return
            link_aviso = ""

            # 1. Preco e titulo sao lidos ANTES de montar os links: o link de
            # loja so vira link de produto se a busca souber o que procurar.
            match = re.search(r"R\$\s*([\d\.]+,\d{2})", raw)
            price = parse_money(match.group(1)) if match else None
            _lines = [l.strip() for l in raw.split("\n") if l.strip()]
            title_guess = ""
            for l in _lines:
                if len(l) > 12 and "http" not in l and not l.startswith("-"):
                    title_guess = l[:150]
                    break

            # 2. Substitui TODOS os links pelos links com o seu codigo de afiliado
            affiliate_urls = {}
            for u in urls:
                tagged, av = affiliate_link(u.rstrip(".,)"), price, title_guess)
                affiliate_urls[u] = tagged
                if av and u.rstrip(".,)") == product_urls[0].rstrip(".,)"):
                    link_aviso = av
            text = raw
            for original, tagged in affiliate_urls.items():
                text = text.replace(original, tagged)
            link = affiliate_urls[product_urls[0].rstrip(".,)")]

            # 3. Foto: usa a do post, senao extrai da pagina do produto
            image = None
            if event.photo:
                try:
                    path = await event.download_media()
                    if path:
                        image = upload_to_blob(path, f"canal_{int(time.time())}.jpg")
                        Path(path).unlink(missing_ok=True)
                except Exception:
                    pass

            title = ""
            if not image or not price:
                data = extract_product(product_urls[0])
                title = data.get("title") or ""
                image = image or (data.get("image") or "")
                price = price or data.get("price")

            if not title:
                title = title_guess or (_lines[0][:150] if _lines else "Oferta")

            # 4. Monta o post com o preco quando ele nao veio no texto original
            if price and not match:
                text = f"{title}\n\n{price_block(price, None)}\n\n{text}"

            log(f"📡 Canal: {title[:45]} | foto={'sim' if image else 'nao'} | preco={brl(price)}")
            if link_aviso:
                log(f"⚠️ {link_aviso}")
                notify_admin(f"⚠️ Oferta do canal ignorada por comissao: "
                             f"{link_aviso}\n{title[:70]}")
                return
            send_message(f"{text}\n\n{FOOTER_TEXT}", photo_url=image)
            save_to_vitrine({"id": "ch_" + hashlib.md5(link.encode()).hexdigest()[:10],
                             "title": title, "price": price, "original_price": None,
                             "link": link, "image": image or ""})

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
    log("\n🤖 Ciclo do Telegram: planilha + raspagem")
    BLOCKED_SOURCES.clear()
    proxy_health()
    seen = load_json(SEEN_FILE)
    products = collect_products(include_scrape=True)

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


def instagram_cycle():
    queue = load_json(BASE_DIR / "ig_queue.json", [])
    if not queue:
        log("📸 Instagram: fila vazia.")
        return
    item = queue[0]
    pct = item.get("pct")
    caption = f"🔥 {item['title']}\n\n{price_block(item.get('price'), item.get('old'))}\n\n🔗 Link na bio!"
    public_url = arte_para_publicar(item.get("image"), item.get("price"), item.get("old"), pct, item.get("title"))
    if post_to_instagram(public_url, caption):
        save_json(BASE_DIR / "ig_queue.json", queue[1:])
    else:
        log("⏭️ Post do Instagram não concluído; item mantido na fila.")


def main():
    log("=" * 52)
    log(">>> BOT VAGANTE PROMOÇÕES <<<")
    log("=" * 52)

    if "--login" in sys.argv:
        log("🔐 Modo de autenticação do Telethon — informe telefone e código quando solicitado.")
        channel_listener()
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

    last_telegram = 0.0
    last_instagram = 0.0
    time.sleep(5)

    while True:
        try:
            now = time.time()
            if now - last_telegram >= INTERVAL_TELEGRAM:
                telegram_cycle()
                last_telegram = now
            if now - last_instagram >= INTERVAL_INSTAGRAM:
                instagram_cycle()
                last_instagram = now
        except Exception as exc:
            log(f"⚠️ Erro no ciclo principal: {exc}")
        time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Encerrado pelo usuário.")
        sys.exit(0)
