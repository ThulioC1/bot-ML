import csv
import hashlib
import io
import json
import os
import random
import re
import time
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests as cureq
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import requests

load_dotenv()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip().strip('"').strip("'")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip().strip('"').strip("'")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip().strip('"').strip("'")
IG_USER_ID = os.getenv("IG_USER_ID", "").strip().strip('"').strip("'")
BLOB_TOKEN = os.getenv("BLOB_READ_WRITE_TOKEN", "").strip().strip('"').strip("'")

ML_AFFILIATE_USERNAME = os.getenv("ML_AFFILIATE_USERNAME", "").strip().strip('"').strip("'")
ML_AFFILIATE_TOOL_ID = os.getenv("ML_AFFILIATE_TOOL_ID", "").strip().strip('"').strip("'")
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "").strip().strip('"').strip("'")
AMAZON_TAG = os.getenv("AMAZON_TAG", "").strip().strip('"').strip("'")

FOOTER_TEXT = os.getenv("FOOTER", "🔗 Links afiliados. Gostou da oferta? Compartilhe nosso grupo: https://t.me/vagantepromo")

SEEN_FILE = "seen.json"
IG_SEEN_FILE = "ig_seen.json"
VITRINE_FILE = "vitrine.json"
TEMPLATE_FILE = "template.png"

# URL direta da planilha publicada na web (exportação CSV oficial)
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRKHrxu8OFtNtgj6Hs6IlPIhg-mhQbHXrQxi6uiSnoTZI_I3RGk26SE5fMoUz2nMU3X95w0_OmLxfOa/pub?output=csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.mercadolivre.com.br/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}

def save_json(filepath, data_dict, max_limit=1000):
    if len(data_dict) > max_limit:
        keys = list(data_dict.keys())[:-max_limit]
        for k in keys:
            del data_dict[k]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data_dict, f, ensure_ascii=False, indent=4)

def generate_affiliate_link(original_url):
    log(f"🔗 [DEBUG] generate_affiliate_link called: {original_url}")
    log(f"   USER={ML_AFFILIATE_USERNAME!r} TOOL={ML_AFFILIATE_TOOL_ID!r}")
    if not ML_AFFILIATE_USERNAME or not ML_AFFILIATE_TOOL_ID:
        log("   ⚠️ Variáveis vazias, retornando original")
        return original_url
    clean_url = original_url.split("?")[0]
    result = f"{clean_url}?matt_word={ML_AFFILIATE_USERNAME}&matt_tool={ML_AFFILIATE_TOOL_ID}"
    log(f"   ✅ Resultado: {result}")
    return result

def generate_shopee_affiliate_link(original_url):
    clean_url = original_url.split("?")[0]
    if SHOPEE_AFFILIATE_ID:
        return f"{clean_url}?smtt={SHOPEE_AFFILIATE_ID}"
    return clean_url

def generate_amazon_affiliate_link(original_url):
    clean_url = original_url.split("?")[0]
    if AMAZON_TAG:
        return f"{clean_url}?tag={AMAZON_TAG}"
    return clean_url

def send_telegram_message(caption, photo_url=None, reply_to_message_id=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("⚠ Token ou Chat ID do Telegram ausentes no ambiente.")
        return False
        
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    sent_success = False

    # Tenta enviar com Foto
    if photo_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        payload["photo"] = photo_url
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                sent_success = True
            else:
                log(f"⚠ Telegram recusou foto ({resp.status_code}). Reenviando apenas como texto...")
        except Exception as e:
            log(f"⚠️ Falha ao enviar imagem ao Telegram: {e}")

    # Fallback: Envia apenas texto caso a foto falhe ou não exista
    if not sent_success:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        text_payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": caption
        }
        if reply_to_message_id:
            text_payload["reply_to_message_id"] = reply_to_message_id
        try:
            resp = requests.post(url, json=text_payload, timeout=10)
            if resp.status_code == 200:
                sent_success = True
            else:
                log(f"⚠️ Erro do Telegram ({resp.status_code}): {resp.text}")
        except Exception as e:
            log(f"⚠️ Exceção ao enviar texto para o Telegram: {e}")

    return sent_success

def upload_to_vercel_blob(local_path, remote_name):
    if not BLOB_TOKEN or not os.path.exists(local_path):
        return None
    try:
        with open(local_path, "rb") as f:
            file_data = f.read()

        url = f"https://blob.vercel-storage.com/{remote_name}"
        headers = {
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "x-add-random-suffix": "0"
        }

        resp = requests.put(url, data=file_data, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            public_url = data.get("url")
            log(f"☁️ [Vercel Blob] {remote_name} atualizado! URL pública: {public_url}")
            return public_url
        else:
            log(f"⚠ [Vercel Blob] Erro ao enviar {remote_name}: {resp.text}")
    except Exception as e:
        log(f"⚠ [Vercel Blob] Exceção em {remote_name}: {e}")
    return None

def upload_temp_image_to_blob(local_path):
    if not BLOB_TOKEN or not os.path.exists(local_path):
        return None
    try:
        filename = f"art_{int(time.time())}_{random.randint(1000,9999)}.jpg"
        url = f"https://blob.vercel-storage.com/{filename}"
        headers = {
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "x-add-random-suffix": "1"
        }
        with open(local_path, "rb") as f:
            resp = requests.put(url, data=f, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("url")
    except Exception as e:
        log(f"⚠️ [Vercel Blob Image] Erro ao hospedar arte: {e}")
    return None

def update_vitrine_json(p, final_link):
    vitrine = []
    if os.path.exists(VITRINE_FILE):
        try:
            with open(VITRINE_FILE, "r", encoding="utf-8") as f:
                vitrine = json.load(f)
        except:
            vitrine = []

    novo_produto = {
        "id": p["id"],
        "title": p["title"],
        "price": p["price"],
        "original_price": p.get("original_price"),
        "link": final_link,
        "image": p["thumbnail"] if p["thumbnail"] else "https://via.placeholder.com/150",
        "time": time.strftime("%d/%m/%Y %H:%M")
    }

    vitrine.insert(0, novo_produto)
    vitrine = vitrine[:15]

    with open(VITRINE_FILE, "w", encoding="utf-8") as f:
        json.dump(vitrine, f, ensure_ascii=False, indent=4)
    log(f"📦 [Vitrine] {VITRINE_FILE} atualizado (Total de itens: {len(vitrine)})")
    
    upload_to_vercel_blob(VITRINE_FILE, "vitrine.json")

def gerar_arte_produto(image_url, preco_texto):
    try:
        canvas = Image.new("RGBA", (1080, 1080), (12, 22, 38, 255))

        prod_resp = requests.get(image_url, timeout=10)
        prod_img = Image.open(io.BytesIO(prod_resp.content)).convert("RGBA")
        
        prod_size = 720
        prod_img = prod_img.resize((prod_size, prod_size), Image.Resampling.LANCZOS)
        
        prod_x = (1080 - prod_size) // 2
        prod_y = 40
        canvas.paste(prod_img, (prod_x, prod_y), prod_img)

        if os.path.exists(TEMPLATE_FILE):
            template_img = Image.open(TEMPLATE_FILE).convert("RGBA")
            tw, th = template_img.size
            
            new_w = 1080
            new_h = int(th * (new_w / tw))
            template_img = template_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            template_y = 1080 - new_h
            canvas.paste(template_img, (0, template_y), template_img)
            
            box_x1 = int(new_w * 0.53)
            box_y1 = template_y + int(new_h * 0.15)
            box_x2 = int(new_w * 0.97)
            box_y2 = template_y + int(new_h * 0.85)
        else:
            box_x1, box_y1, box_x2, box_y2 = 540, 900, 1025, 1020

        draw = ImageDraw.Draw(canvas)

        font_preco = None
        font_paths = [
            "/system/fonts/Roboto-Bold.ttf",
            "/system/fonts/Roboto-Regular.ttf",
            "/system/fonts/DroidSans.ttf",
            "/data/data/com.termux/files/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                try:
                    font_preco = ImageFont.truetype(path, 64)
                    break
                except:
                    continue
                    
        if not font_preco:
            font_preco = ImageFont.load_default()

        preco_formatado = f"R$ {preco_texto}"
        bbox = draw.textbbox((0, 0), preco_formatado, font=font_preco)
        tw_text = bbox[2] - bbox[0]
        th_text = bbox[3] - bbox[1]
        tx = box_x1 + ((box_x2 - box_x1) - tw_text) / 2
        ty = box_y1 + ((box_y2 - box_y1) - th_text) / 2

        draw.text((tx, ty), preco_formatado, fill=(255, 255, 255), font=font_preco)
        
        output_path = "arte_produto_temp.jpg"
        canvas.convert("RGB").save(output_path, "JPEG", quality=95)
        return output_path
    except Exception as e:
        log(f"⚠️ Erro ao gerar arte com template: {e}")
        return None

def post_to_instagram_feed(caption, image_url, preco_str):
    if not IG_ACCESS_TOKEN or not IG_USER_ID or not image_url:
        return
    try:
        log("🎨 [Instagram] Aplicando template e injetando preço...")
        caminho_arte = gerar_arte_produto(image_url, preco_str)
        
        final_image_url = image_url
        if caminho_arte:
            blob_url = upload_temp_image_to_blob(caminho_arte)
            if blob_url:
                final_image_url = blob_url

        log("📸 [Instagram] Publicando no Feed...")
        container_url = f"https://graph.instagram.com/v18.0/{IG_USER_ID}/media"
        resp = requests.post(container_url, data={
            "image_url": final_image_url,
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        }, timeout=15)
        data = resp.json()
        if "id" not in data:
            log(f"⚠️ [Instagram Feed] Erro no container: {data}")
            return
            
        creation_id = data["id"]
        pub_resp = requests.post(f"https://graph.instagram.com/v18.0/{IG_USER_ID}/media_publish", data={
            "creation_id": creation_id,
            "access_token": IG_ACCESS_TOKEN
        }, timeout=15)
        pub_data = pub_resp.json()
        
        if "id" in pub_data:
            log(f"✅ [Instagram] Publicado com sucesso! ID: {pub_data['id']}")
    except Exception as e:
        log(f"⚠ [Instagram Feed] Erro: {e}")

def fetch_sheet_products():
    products = []
    log("📊 [Planilha] Consultando dados do Google Sheets...")
    try:
        resp = requests.get(SHEET_CSV_URL, timeout=10)
        if resp.status_code == 200:
            lines = resp.text.splitlines()
            reader = csv.reader(lines)
            header = next(reader, None)  # Pula o cabeçalho
            
            for row in reader:
                if len(row) >= 4:
                    raw_link = row[0].replace('"', '').strip()
                    raw_price = row[1].replace('"', '').strip()
                    title = row[2].replace('"', '').strip()
                    photo = row[3].replace('"', '').strip()
                    
                    if not raw_link or not title:
                        continue
                        
                    try:
                        price_clean = raw_price.replace("R$", "").replace(".", "").replace(",", ".").strip()
                        price = float(price_clean)
                    except:
                        price = 0.0
                        
                    item_id = "sheet_" + hashlib.md5(raw_link.encode('utf-8')).hexdigest()[:12]
                    
                    products.append({
                        "id": item_id,
                        "title": title,
                        "price": price,
                        "original_price": None,
                        "permalink": raw_link,
                        "thumbnail": photo,
                        "source": "planilha"
                    })
            log(f"✅ [Planilha] {len(products)} produtos válidos importados.")
        else:
            log(f"⚠ [Planilha] Erro ao acessar CSV: HTTP {resp.status_code}")
    except Exception as e:
        log(f"⚠️ [Planilha] Erro na requisição: {e}")
        
    return products

def fetch_mercado_libre_products(search_query=None):
    all_products = []
    if search_query:
        urls = [f"https://lista.mercadolivre.com.br/{urllib.parse.quote(search_query)}"]
    else:
        page_num = random.randint(1, 30)
        url = "https://www.mercadolivre.com.br/ofertas" if page_num == 1 else f"https://www.mercadolivre.com.br/ofertas?page={page_num}"
        urls = [url]
        log(f"🎲 [Mercado Livre] Sorteada a página {page_num} de ofertas.")

    url = urls[0]
    log(f"🔍 [Mercado Livre] Acessando URL: {url}")
    try:
        response = cureq.get(url, headers=HEADERS, impersonate="chrome120", timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("li.ui-search-layout__item, div.poly-card, .andes-card, .promotion-item, .ui-search-result, .poly-box")
            
            for item in items:
                try:
                    title_elem = item.select_one(".poly-component__title, .ui-search-item__title, h2, .promotion-item__title, a[title]")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True) or title_elem.get("title", "")
                    
                    link_elem = item.select_one("a")
                    if not link_elem:
                        continue
                    permalink = link_elem.get("href", "").split("#")[0]
                    if not permalink.startswith("http"):
                        continue
                        
                    item_id = "ml_" + (permalink.split("/")[-1].split("?")[0] or str(hash(title)))
                    
                    original_price = None
                    orig_container = item.select_one(".andes-money-amount--previous, .price-tag-old, .poly-price__old")
                    if orig_container:
                        orig_frac = orig_container.select_one(".andes-money-amount__fraction, .price-tag-fraction")
                        if orig_frac:
                            try:
                                orig_cents = orig_container.select_one(".andes-money-amount__cents, .price-tag-cents")
                                cents_val = orig_cents.get_text(strip=True) if orig_cents else "00"
                                original_price = float(orig_frac.get_text(strip=True).replace(".", "") + "." + cents_val)
                            except:
                                pass
                                
                    price = 0.0
                    current_container = item.select_one(".poly-price__current, .andes-money-amount:not(.andes-money-amount--previous), .price-tag")
                    if current_container:
                        frac_elem = current_container.select_one(".andes-money-amount__fraction, .price-tag-fraction")
                        if frac_elem:
                            cents_elem = current_container.select_one(".andes-money-amount__cents, .price-tag-cents")
                            cents_val = cents_elem.get_text(strip=True) if cents_elem else "00"
                            price = float(frac_elem.get_text(strip=True).replace(".", "") + "." + cents_val)
                        else:
                            match_text = re.search(r"([\d\.,]+)", current_container.get_text())
                            if match_text:
                                try:
                                    price = float(match_text.group(1).replace(".", "").replace(",", "."))
                                except:
                                    pass
                                    
                    img_elem = item.select_one("img")
                    thumbnail = img_elem.get("data-src") or img_elem.get("src", "") if img_elem else ""
                    
                    if title and permalink and price > 0:
                        if not any(p['id'] == item_id for p in all_products):
                            all_products.append({
                                "id": item_id,
                                "title": title,
                                "price": price,
                                "original_price": original_price,
                                "permalink": permalink,
                                "thumbnail": thumbnail,
                                "source": "raspagem"
                            })
                except:
                    continue
    except Exception as e:
        log(f"⚠ [Mercado Livre] Erro ao buscar: {e}")
        
    random.shuffle(all_products)
    log(f"✅ [Mercado Livre] Produtos válidos: {len(all_products)}")
    return all_products

def fetch_shopee_products(search_query=None):
    all_products = []
    keyword = search_query if search_query else "ofertas"
    url = f"https://shopee.com.br/api/v4/search/search_items?by=relevancy&keyword={urllib.parse.quote(keyword)}&limit=30&newest=0"
    
    log(f"🔍 [Shopee API] Consultando ofertas para: '{keyword}'")
    try:
        shopee_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://shopee.com.br/",
            "x-api-source": "pc",
            "x-shopee-language": "pt",
            "x-requested-with": "XMLHttpRequest"
        }
        
        response = cureq.get(url, headers=shopee_headers, impersonate="chrome120", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", []) or data.get("data", {}).get("items", [])
            log(f"📦 [Shopee] Itens JSON recebidos: {len(items)}")
            
            for entry in items:
                try:
                    item_basic = entry.get("item_basic") or entry
                    if not item_basic:
                        continue
                        
                    item_id_num = item_basic.get("itemid")
                    shop_id_num = item_basic.get("shopid")
                    title = item_basic.get("name")
                    
                    if not item_id_num or not shop_id_num:
                        continue
                        
                    price_raw = item_basic.get("price", 0)
                    price = float(price_raw) / 100000.0 if price_raw else 0.0
                    
                    price_before_raw = item_basic.get("price_before_discount", 0)
                    original_price = float(price_before_raw) / 100000.0 if price_before_raw > price_raw else None
                    
                    image_hash = item_basic.get("image")
                    thumbnail = f"https://down-br.img.susercontent.com/file/{image_hash}" if image_hash else ""
                    
                    permalink = f"https://shopee.com.br/product-i.{shop_id_num}.{item_id_num}"
                    item_id = f"shopee_{shop_id_num}_{item_id_num}"
                    
                    if title and permalink and price > 0:
                        if not any(p['id'] == item_id for p in all_products):
                            all_products.append({
                                "id": item_id,
                                "title": title,
                                "price": price,
                                "original_price": original_price,
                                "permalink": permalink,
                                "thumbnail": thumbnail,
                                "source": "raspagem"
                            })
                except Exception:
                    continue
        elif response.status_code == 403:
            log("⚠️ [Shopee] Bloqueio 403 do Cloudflare. Seguindo com ofertas do Mercado Livre.")
        else:
            log(f"⚠️ [Shopee] Status HTTP diferente de 200: {response.status_code}")
            
    except Exception as e:
        log(f"⚠️ [Shopee] Erro ao consultar API JSON: {e}")
        
    random.shuffle(all_products)
    log(f"✅ [Shopee] Produtos válidos processados: {len(all_products)}")
    return all_products

def post_product(p, seen):
    link_lower = p["permalink"].lower()
    if "shopee" in link_lower or "shope.ee" in link_lower:
        final_link = generate_shopee_affiliate_link(p["permalink"])
    elif "mercadolivre" in link_lower or "mercadolibre" in link_lower or "meli.la" in link_lower:
        final_link = generate_affiliate_link(p["permalink"])
    elif "amazon" in link_lower or "amzn.to" in link_lower or "a.co" in link_lower:
        final_link = generate_amazon_affiliate_link(p["permalink"])
    else:
        final_link = p["permalink"]

    original_price = p.get("original_price")
    price_line = f"📉 De R$ {original_price:.2f}\n🔥 Por R$ {p['price']:.2f}" if (original_price and original_price > p["price"]) else f"💰 R$ {p['price']:.2f}"
    
    msg = f"🔥 OFERTA EM DESTAQUE\n\n📦 {p['title']}\n\n{price_line}\n\n🛒 Link: {final_link}\n\n{FOOTER_TEXT}"
    log(f"🚀 [Telegram] Publicando ({p.get('source', 'raspagem')}): {p['title'][:30]}...")
    
    success = send_telegram_message(msg, photo_url=p["thumbnail"] if p["thumbnail"] else None)
    
    if success:
        update_vitrine_json(p, final_link)
        seen[p["id"]] = {"price": p["price"]}
        save_json(SEEN_FILE, seen)
        return True
    return False

def process_telegram_batch():
    log("\n🤖 [Telegram] Iniciando ciclo de ofertas (Planilha + Raspagem)...")
    seen = load_json(SEEN_FILE)
    
    # 1. EXCEÇÃO: Checa se existem produtos novos na planilha
    sheet_products = fetch_sheet_products()
    unseen_sheet_products = [p for p in sheet_products if p["id"] not in seen]

    if unseen_sheet_products:
        log(f"📊 [Planilha] Encontrados {len(unseen_sheet_products)} produto(s) novo(s) na planilha. Postando junto...")
        for p in unseen_sheet_products:
            if post_product(p, seen):
                time.sleep(30)
    else:
        log("📊 [Planilha] Nenhum produto novo na planilha.")

    # 2. FLUXO NORMAL: Posta 2 ofertas da raspagem (Mercado Livre + Shopee)
    log("🕵️ [Raspagem] Buscando ofertas no Mercado Livre e Shopee...")
    ml_products = fetch_mercado_libre_products()
    shopee_products = fetch_shopee_products()
    
    scraped_products = ml_products + shopee_products
    random.shuffle(scraped_products)
    
    sent_scraped = 0
    for p in scraped_products:
        if sent_scraped >= 2:
            break
        if p["id"] in seen:
            continue
            
        if post_product(p, seen):
            sent_scraped += 1
            if sent_scraped < 2:
                time.sleep(30)
            
    log("🤖 [Telegram] Ciclo finalizado.")

def process_instagram_batch():
    log("\n🤖 [Instagram] Iniciando ciclo de postagem na Vitrine Unificada...")
    if not os.path.exists(VITRINE_FILE):
        return

    try:
        with open(VITRINE_FILE, "r", encoding="utf-8") as f:
            vitrine = json.load(f)
    except:
        vitrine = []

    ig_seen = load_json(IG_SEEN_FILE)
    for p in vitrine:
        p_id = p.get("id")
        if not p_id or p_id in ig_seen:
            continue
            
        price = p["price"]
        original_price = p.get("original_price")
        price_line = f"📉 De R$ {original_price:.2f}\n🔥 Por R$ {price:.2f}" if (original_price and original_price > price) else f"💰 R$ {price:.2f}"
        
        msg = f"🔥 {p['title']}\n\n{price_line}\n\n🔗 Confira o link na BIO!"
        log(f"🚀 [Instagram] Publicando: {p['title'][:30]}...")
        
        if p.get("image"):
            post_to_instagram_feed(msg, p["image"], f"{price:.2f}".replace(".", ","))
            
        ig_seen[p_id] = {"price": price}
        save_json(IG_SEEN_FILE, ig_seen)
        break

    log("🤖 [Instagram] Ciclo finalizado.\n")

def check_telegram_commands(last_update_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={last_update_id}&timeout=1"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            for update in response.json().get("result", []):
                last_update_id = update["update_id"] + 1
                message = update.get("message")
                if message and message.get("text", "").lower().startswith("/produto"):
                    parts = message["text"].split(" ", 1)
                    if len(parts) > 1:
                        query = parts[1].strip()
                        send_telegram_message(f"🔎 Pesquisando por '{query}' no Mercado Livre e Shopee...", reply_to_message_id=message["message_id"])
                        
                        products = fetch_mercado_libre_products(search_query=query) + fetch_shopee_products(search_query=query)
                        if products:
                            p = products[0]
                            final_link = generate_shopee_affiliate_link(p["permalink"]) if "shopee" in p["id"] else generate_affiliate_link(p["permalink"])
                            original_price = p.get("original_price")
                            p_line = f"📉 De R$ {original_price:.2f}\n🔥 Por R$ {p['price']:.2f}" if (original_price and original_price > p["price"]) else f"💰 R$ {p['price']:.2f}"
                                
                            msg = f"🎯 RESULTADO PARA: {query.upper()}\n\n📦 {p['title']}\n\n{p_line}\n\n🛒 Link: {final_link}"
                            send_telegram_message(msg, photo_url=p["thumbnail"], reply_to_message_id=message["message_id"])
    except Exception as e:
        log(f"⚠️ [Telegram Cmd] Erro: {e}")
    return last_update_id

if __name__ == "__main__":
    log(">>> BOT VITRINE UNIFICADA ATIVO <<<")

    INTERVAL_TELEGRAM = 3600   # 1 hora
    INTERVAL_INSTAGRAM = 10800 # 3 horas

    last_telegram_time = 0
    last_instagram_time = 0
    last_update_id = 0

    while True:
        try:
            current_time = time.time()

            if current_time - last_telegram_time >= INTERVAL_TELEGRAM:
                process_telegram_batch()
                last_telegram_time = current_time

            if current_time - last_instagram_time >= INTERVAL_INSTAGRAM:
                process_instagram_batch()
                last_instagram_time = current_time

            last_update_id = check_telegram_commands(last_update_id)

        except Exception as e:
            log(f"⚠️ Erro no loop principal: {e}")

        time.sleep(10)