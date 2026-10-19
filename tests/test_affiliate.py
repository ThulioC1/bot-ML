# -*- coding: utf-8 -*-
"""Testes offline dos geradores de link de afiliado e do publish."""

import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot


def tearDownModule():
    bot.quit_driver()
    bot.cdp_close()


class StoreOfUrlTests(unittest.TestCase):
    def test_magazineluiza_nao_e_amazon(self):
        self.assertEqual(
            bot._store_of_url("https://www.magazineluiza.com.br/produto/p/123"), "")

    def test_amazon(self):
        self.assertEqual(
            bot._store_of_url("https://www.amazon.com.br/dp/B0CXF5TCLK"), "amazon")
        self.assertEqual(bot._store_of_url("https://amzn.to/3abcDEF"), "amazon")
        self.assertEqual(bot._store_of_url("https://a.co/d/abc"), "amazon")

    def test_ml_shopee(self):
        self.assertEqual(bot._store_of_url("https://meli.la/2AbCdEf"), "ml")
        self.assertEqual(
            bot._store_of_url("https://www.mercadolivre.com.br/produto/p/MLB1"), "ml")
        self.assertEqual(bot._store_of_url("https://shope.ee/abc"), "shopee")


class ExtractShortLinkTests(unittest.TestCase):
    def test_ml_json(self):
        payload = {"urls": [{"short_url": "https://meli.la/2AbCdEf"}]}
        self.assertEqual(bot._extract_short_link(payload), "https://meli.la/2AbCdEf")

    def test_escaped_slashes(self):
        raw = '{"shortUrl": "https:\\/\\/amzn.to\\/3abcDEF"}'
        self.assertEqual(bot._extract_short_link(raw), "https://amzn.to/3abcDEF")

    def test_shopee_graphql(self):
        data = {"data": {"generateShortLink": {"shortLink": "https://shope.ee/9abcXYZ"}}}
        self.assertEqual(bot._extract_short_link(data), "https://shope.ee/9abcXYZ")

    def test_no_link(self):
        self.assertEqual(bot._extract_short_link({"errors": [{"message": "nope"}]}), "")


class AmazonAsinTests(unittest.TestCase):
    def test_dp(self):
        self.assertEqual(
            bot._amazon_asin("https://www.amazon.com.br/Nome/dp/B0CXF5TCLK/ref=x"),
            "B0CXF5TCLK")

    def test_gp_product(self):
        self.assertEqual(
            bot._amazon_asin("https://www.amazon.com.br/gp/product/b0cxf5tclk"),
            "B0CXF5TCLK")

    def test_query_asin(self):
        self.assertEqual(
            bot._amazon_asin("https://www.amazon.com.br/oferta?asin=B0CXF5TCLK"),
            "B0CXF5TCLK")

    def test_sem_asin(self):
        self.assertEqual(bot._amazon_asin("https://www.amazon.com.br/ofertas"), "")


class ShopeeAuthorizationTests(unittest.TestCase):
    def test_signature_matches_manual_sha256(self):
        body = '{"query":"x"}'
        with mock.patch.object(bot, "SHOPEE_APP_ID", "123"), \
                mock.patch.object(bot, "SHOPEE_SECRET", "sec"):
            _, header = bot._shopee_authorization(body, timestamp=1700000000)
        expected = hashlib.sha256(b"1231700000000" + body.encode() + b"sec").hexdigest()
        self.assertIn(f"Signature={expected}", header)
        self.assertIn("Credential=123", header)
        self.assertIn("Timestamp=1700000000", header)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cache = mock.patch.object(bot, "LINK_GEN_CACHE_FILE",
                                  Path(self.tmp.name) / "cache.json")
        cache.start()
        self.addCleanup(cache.stop)
        expand = mock.patch.object(bot, "expand_url", side_effect=lambda u: u)
        expand.start()
        self.addCleanup(expand.stop)

    def test_ml_api(self):
        value = {"ok": True, "attempts": [
            {"status": 200, "text": json.dumps(
                {"urls": [{"short_url": "https://meli.la/abc123"}]})}]}
        with mock.patch.object(bot, "ML_AFFILIATE_TAG", "minhatag"), \
                mock.patch.object(bot, "browser_eval",
                                  return_value={"ok": True, "value": value}) as be:
            link, error = bot.generate_ml_affiliate_link(
                "https://www.mercadolivre.com.br/produto/p/MLB123")
        self.assertEqual(link, "https://meli.la/abc123")
        self.assertIsNone(error)
        self.assertEqual(be.call_args[0][0], bot.ML_LINKBUILDER_URL)

    def test_ml_requires_tag(self):
        with mock.patch.object(bot, "ML_AFFILIATE_TAG", ""):
            link, error = bot.generate_ml_affiliate_link(
                "https://produto.mercadolivre.com.br/MLB-123-produto")
        self.assertIsNone(link)
        self.assertIn("ML_AFFILIATE_TAG", error)

    def test_ml_rejects_store_link(self):
        with mock.patch.object(bot, "ML_AFFILIATE_TAG", "tag"):
            link, error = bot.generate_ml_affiliate_link(
                "https://www.mercadolivre.com.br/social/minhaloja")
        self.assertIsNone(link)

    def test_ml_rejects_unexpanded_short_link(self):
        with mock.patch.object(bot, "ML_AFFILIATE_TAG", "tag"):
            link, error = bot.generate_ml_affiliate_link("https://meli.la/2AbCdEf")
        self.assertIsNone(link)
        self.assertIn("expandir", error)

    def test_shopee_api(self):
        data = {"data": {"generateShortLink": {"shortLink": "https://shope.ee/abc"}}}
        resp = mock.Mock(status_code=200)
        resp.json.return_value = data
        with mock.patch.object(bot, "SHOPEE_APP_ID", "app"), \
                mock.patch.object(bot, "SHOPEE_SECRET", "secret"), \
                mock.patch("requests.post", return_value=resp) as post:
            link, error = bot.generate_shopee_affiliate_link(
                "https://shopee.com.br/product/1/2")
        self.assertEqual(link, "https://shope.ee/abc")
        self.assertIsNone(error)
        body = post.call_args.kwargs["data"].decode("utf-8")
        self.assertIn("generateShortLink", body)
        self.assertIn("Authorization", post.call_args.kwargs["headers"])

    def test_amazon_sitestripe(self):
        text = '{"shortUrl": "https://amzn.to/3abc"}'
        value = {"ok": True, "attempts": [{"status": 200, "mid": "x", "text": text}]}
        with mock.patch.object(bot, "AMAZON_TAG", "minhatag-20"), \
                mock.patch.object(bot, "browser_eval",
                                  return_value={"ok": True, "value": value}):
            link, error = bot.generate_amazon_affiliate_link(
                "https://www.amazon.com.br/dp/B0CXF5TCLK?tag=outro")
        self.assertEqual(link, "https://amzn.to/3abc")
        self.assertIsNone(error)

    def test_router_unsupported_store(self):
        url = "https://www.magazineluiza.com.br/produto/p/123"
        link, error = bot.generate_affiliate_link(url)
        self.assertEqual(link, url)
        self.assertIsNone(error)

    def test_router_expands_before_store_detection(self):
        short = "https://meli.la/2AbCdEf"
        store = "https://www.mercadolivre.com.br/social/minhaloja"
        resolved = "https://www.mercadolivre.com.br/produto/p/MLB123"
        with mock.patch.object(bot, "expand_url", return_value=store), \
                mock.patch.object(bot, "resolve_store_link",
                                  return_value={"url": resolved}) as resolve, \
                mock.patch.object(bot, "generate_ml_affiliate_link",
                                  return_value=("https://meli.la/ok", None)) as gen:
            link, error = bot.generate_affiliate_link(short, 10.0, "Produto")
        self.assertEqual(link, "https://meli.la/ok")
        self.assertIsNone(error)
        resolve.assert_called_once()
        gen.assert_called_once_with(resolved)

    def test_router_uses_cache(self):
        calls = []

        def fake(_url):
            calls.append(_url)
            return "https://meli.la/cache", None

        url = "https://www.mercadolivre.com.br/produto/p/MLB999"
        with mock.patch.object(bot, "ML_AFFILIATE_TAG", "tag"), \
                mock.patch.object(bot, "generate_ml_affiliate_link",
                                  side_effect=fake):
            first, _ = bot.generate_affiliate_link(url)
            second, _ = bot.generate_affiliate_link(url)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)


class ShopeePortalTests(unittest.TestCase):
    def test_portal_scrape_uses_modal_link(self):
        value = {
            "ok": True,
            "products": [
                {"ok": True, "title": "Fone Shopee", "price": "R$ 89,90",
                 "image": "https://img/x.jpg", "offer_id": "999",
                 "affiliate_link": "https://shope.ee/abc", "error": ""},
                {"ok": False, "title": "Sem link", "price": "R$ 10,00",
                 "image": "", "offer_id": "1", "affiliate_link": "",
                 "error": "modal sem link"},
            ],
        }
        with mock.patch.object(bot, "BROWSER_SCRAPING", True), \
                mock.patch.object(bot, "browser_eval",
                                  return_value={"ok": True, "value": value}) as be:
            products = bot.fetch_shopee_affiliate_products()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["affiliate_link"], "https://shope.ee/abc")
        self.assertEqual(products[0]["permalink"], "https://shope.ee/abc")
        self.assertEqual(products[0]["price"], 89.9)
        self.assertEqual(be.call_args[0][0], bot.SHOPEE_PRODUCT_OFFER_URL)

    def test_portal_link_generation(self):
        with mock.patch.object(bot, "SHOPEE_APP_ID", ""), \
                mock.patch.object(bot, "SHOPEE_SECRET", ""), \
                mock.patch.object(bot, "BROWSER_SCRAPING", True), \
                mock.patch.object(bot, "expand_url", side_effect=lambda u: u), \
                mock.patch.object(bot, "browser_eval",
                                  return_value={"ok": True,
                                                "value": {"ok": True,
                                                          "link": "https://shope.ee/ok"}}):
            link, error = bot.generate_shopee_portal_link(
                "https://shopee.com.br/product/1/2")
        self.assertEqual(link, "https://shope.ee/ok")
        self.assertIsNone(error)

    def test_portal_link_prefers_open_api(self):
        with mock.patch.object(bot, "SHOPEE_APP_ID", "app"), \
                mock.patch.object(bot, "SHOPEE_SECRET", "secret"), \
                mock.patch.object(bot, "BROWSER_SCRAPING", True), \
                mock.patch.object(bot, "expand_url", side_effect=lambda u: u), \
                mock.patch.object(bot, "generate_shopee_affiliate_link",
                                  return_value=("https://shope.ee/api", None)) as api, \
                mock.patch.object(bot, "browser_eval") as be:
            link, error = bot.generate_shopee_portal_link(
                "https://shopee.com.br/product/1/2")
        self.assertEqual(link, "https://shope.ee/api")
        self.assertIsNone(error)
        api.assert_called_once()
        be.assert_not_called()

    def test_portal_link_falls_back_to_open_api(self):
        with mock.patch.object(bot, "SHOPEE_APP_ID", ""), \
                mock.patch.object(bot, "SHOPEE_SECRET", ""), \
                mock.patch.object(bot, "BROWSER_SCRAPING", True), \
                mock.patch.object(bot, "expand_url", side_effect=lambda u: u), \
                mock.patch.object(bot, "browser_eval",
                                  return_value={"ok": True,
                                                "value": {"ok": False,
                                                          "error": "sem login"}}), \
                mock.patch.object(bot, "generate_shopee_affiliate_link",
                                  return_value=("https://shope.ee/api", None)) as api:
            link, error = bot.generate_shopee_portal_link(
                "https://shopee.com.br/product/1/2")
        self.assertEqual(link, "https://shope.ee/api")
        self.assertIsNone(error)
        api.assert_called_once()


class ShopeeOpenApiTests(unittest.TestCase):
    def _resp(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"data": {"productOfferV2": {"nodes": [
            {"productName": "Fone X", "itemId": 1, "shopId": 2,
             "price": "R$ 80,00", "priceMin": "R$ 80,00",
             "priceDiscountRate": "20%", "imageUrl": "https://img/x.jpg",
             "productLink": "https://shopee.com.br/product/2/1",
             "offerLink": "https://shope.ee/xyz"},
        ]}}}
        return resp

    def test_products_from_open_api(self):
        with mock.patch.object(bot, "SHOPEE_APP_ID", "app"), \
                mock.patch.object(bot, "SHOPEE_SECRET", "secret"), \
                mock.patch.object(bot, "SHOPEE_OFFER_LIMIT", 6), \
                mock.patch("requests.post", return_value=self._resp()) as post:
            products = bot.fetch_shopee_products_api("fone")
        self.assertEqual(len(products), 1)
        product = products[0]
        self.assertEqual(product["price"], 80.0)
        self.assertAlmostEqual(product["original_price"], 100.0)
        self.assertEqual(product["affiliate_link"], "https://shope.ee/xyz")
        body = post.call_args.kwargs["data"].decode("utf-8")
        self.assertIn("productOfferV2", body)

    def test_missing_credentials_returns_empty(self):
        with mock.patch.object(bot, "SHOPEE_APP_ID", ""), \
                mock.patch.object(bot, "SHOPEE_SECRET", ""):
            self.assertEqual(bot.fetch_shopee_products_api("fone"), [])

    def test_products_fall_back_to_api_before_scraping(self):
        with mock.patch.object(bot, "fetch_shopee_affiliate_products",
                               return_value=[]), \
                mock.patch.object(bot, "SHOPEE_APP_ID", "app"), \
                mock.patch.object(bot, "SHOPEE_SECRET", "secret"), \
                mock.patch.object(bot, "fetch_shopee_products_api",
                                  return_value=[{"id": "x", "title": "t",
                                                 "price": 1.0}]) as api, \
                mock.patch.object(bot, "_shopee_search_data") as scrape:
            products = bot.fetch_shopee_products("fone")
        self.assertEqual(len(products), 1)
        api.assert_called_once()
        scrape.assert_not_called()


class ShopeeAntiBotTests(unittest.TestCase):
    def test_public_search_detects_bot_wall(self):
        with mock.patch.object(bot, "BROWSER_SCRAPING", True), \
                mock.patch.object(bot, "browser_eval",
                                  return_value={"ok": True,
                                                "value": "<html>verify/traffic</html>"}), \
                mock.patch.object(bot, "http_get") as http:
            self.assertIsNone(bot._shopee_search_data("fone"))
        http.assert_not_called()


class SeleniumEvalTests(unittest.TestCase):
    def test_script_value_is_not_double_wrapped(self):
        driver = mock.Mock()
        driver.execute_async_script.return_value = {
            "__selenium_eval__": True,
            "ok": True,
            "value": {"ok": True, "products": [1]},
        }
        with mock.patch.object(bot, "selenium_driver", return_value=driver):
            result = bot.selenium_eval("https://example.com", "return 1;", wait=0)
        self.assertEqual(result, {"ok": True, "value": {"ok": True, "products": [1]}})


class PublishTests(unittest.TestCase):
    def setUp(self):
        bot.LINK_FAIL_NOTICE.clear()

    def _product(self, pid="pv_test"):
        return {
            "id": pid, "title": "Fone Bluetooth", "price": 99.0,
            "original_price": 199.0,
            "permalink": "https://www.mercadolivre.com.br/produto/p/MLB1",
            "thumbnail": "",
        }

    def test_publish_refuses_without_link(self):
        product = self._product()
        with mock.patch.object(bot, "generate_affiliate_link",
                               return_value=(None, "sem login")), \
                mock.patch.object(bot, "send_message") as send, \
                mock.patch.object(bot, "notify_admin") as adm:
            ok = bot.publish(product)
        self.assertFalse(ok)
        send.assert_not_called()
        adm.assert_called_once()

    def test_publish_sends_generated_link(self):
        product = self._product("pv_test_2")
        with mock.patch.object(bot, "generate_affiliate_link",
                               return_value=("https://meli.la/ok", None)), \
                mock.patch.object(bot, "send_message", return_value=True) as send, \
                mock.patch.object(bot, "save_to_vitrine") as vitrine, \
                mock.patch.object(bot, "load_json", return_value={}), \
                mock.patch.object(bot, "save_json"):
            ok = bot.publish(product)
        self.assertTrue(ok)
        keyboard = send.call_args.kwargs["reply_markup"]
        self.assertEqual(keyboard["inline_keyboard"][0][0]["url"],
                         "https://meli.la/ok")
        vitrine.assert_called_once()
        self.assertEqual(vitrine.call_args[0][0]["link"], "https://meli.la/ok")

    def test_publish_prefers_affiliate_link(self):
        product = self._product("pv_test_3")
        product["affiliate_link"] = "https://shope.ee/ja"
        with mock.patch.object(bot, "generate_affiliate_link") as gen, \
                mock.patch.object(bot, "send_message", return_value=True) as send, \
                mock.patch.object(bot, "save_to_vitrine"), \
                mock.patch.object(bot, "load_json", return_value={}), \
                mock.patch.object(bot, "save_json"):
            ok = bot.publish(product)
        self.assertTrue(ok)
        gen.assert_not_called()
        keyboard = send.call_args.kwargs["reply_markup"]
        self.assertEqual(keyboard["inline_keyboard"][0][0]["url"],
                         "https://shope.ee/ja")


class PrivateLinkTests(unittest.TestCase):
    def test_private_link_uses_own_link_and_announces_instagram(self):
        url = "https://meli.la/2AbCdEf"
        message = {"chat": {"id": 123, "type": "private"}, "message_id": 9,
                   "text": url}
        product_data = {"title": "Fone", "price": 89.9, "original_price": 120.0,
                        "image": "https://img/1.jpg",
                        "link": "https://www.mercadolivre.com.br/produto/p/MLB1"}
        with mock.patch.object(bot, "extract_product", return_value=product_data), \
                mock.patch.object(bot, "generate_affiliate_link") as gen, \
                mock.patch.object(bot, "publish", return_value=True) as pub, \
                mock.patch.object(bot, "send_message"):
            bot.handle_private_message(message)
        gen.assert_not_called()
        pub.assert_called_once()
        product = pub.call_args[0][0]
        self.assertEqual(product["affiliate_link"], url)
        self.assertEqual(product["permalink"], url)
        self.assertTrue(pub.call_args[1].get("announce_instagram"))

    def test_private_link_without_price_does_not_publish(self):
        url = "https://meli.la/2AbCdEg"
        message = {"chat": {"id": 123, "type": "private"}, "message_id": 10,
                   "text": url}
        product_data = {"title": "Fone", "price": None, "original_price": None,
                        "image": "", "link": url}
        with mock.patch.object(bot, "extract_product", return_value=product_data), \
                mock.patch.object(bot, "generate_affiliate_link") as gen, \
                mock.patch.object(bot, "publish") as pub, \
                mock.patch.object(bot, "send_message") as send:
            bot.handle_private_message(message)
        gen.assert_not_called()
        pub.assert_not_called()
        sent = " ".join(str(c) for c in send.call_args_list)
        self.assertIn(url, sent)


class BuscaTests(unittest.TestCase):
    def test_rank_puts_biggest_discount_first(self):
        items = [
            {"title": "C", "price": 10.0, "original_price": None},
            {"title": "A", "price": 50.0, "original_price": 100.0},
            {"title": "B", "price": 80.0, "original_price": 100.0},
        ]
        self.assertEqual([p["title"] for p in bot.rank_ofertas(items)],
                         ["A", "B", "C"])

    def test_rank_uses_lowest_price_without_discount(self):
        items = [{"title": "caro", "price": 200.0},
                 {"title": "barato", "price": 100.0}]
        self.assertEqual([p["title"] for p in bot.rank_ofertas(items)],
                         ["barato", "caro"])

    def test_relevante_matches_word_without_accent(self):
        product = {"title": "Fone de Ouvido Bluetooth"}
        self.assertTrue(bot.busca_relevante(product, "fone bluetooth"))
        self.assertFalse(bot.busca_relevante(product, "panela"))


class InstagramFilterTests(unittest.TestCase):
    def _schedule(self, price, old, ig_min):
        with mock.patch.object(bot, "IG_MIN_DISCOUNT", ig_min), \
                mock.patch.object(bot, "load_json", return_value=[]), \
                mock.patch.object(bot, "save_json") as save:
            queued = bot.schedule_instagram({"thumbnail": "https://img/1.jpg"},
                                            "Fone", price, old)
        return queued, save

    def test_skips_without_min_discount(self):
        queued, save = self._schedule(100.0, None, 20)
        self.assertFalse(queued)
        save.assert_not_called()
        queued, save = self._schedule(100.0, 105.0, 20)
        self.assertFalse(queued)
        save.assert_not_called()

    def test_queues_with_enough_discount(self):
        queued, save = self._schedule(80.0, 100.0, 20)
        self.assertTrue(queued)
        save.assert_called_once()

    def test_zero_disables_filter(self):
        queued, save = self._schedule(100.0, None, 0)
        self.assertTrue(queued)
        save.assert_called_once()


class InstagramCycleTests(unittest.TestCase):
    def _queue_item(self, title):
        return {"title": title, "price": 80.0, "old": 100.0,
                "image": "https://img/1.jpg", "pct": 20.0}

    def test_posts_two_per_cycle(self):
        queue = [self._queue_item(t) for t in ("a", "b", "c")]
        with mock.patch.object(bot, "IG_POSTS_PER_CYCLE", 2), \
                mock.patch.object(bot, "IG_POST_DELAY", 0), \
                mock.patch.object(bot, "load_json", return_value=queue), \
                mock.patch.object(bot, "save_json") as save, \
                mock.patch.object(bot, "arte_para_publicar",
                                  return_value="https://img/arte.jpg"), \
                mock.patch.object(bot, "post_to_instagram",
                                  return_value=True) as post:
            bot.instagram_cycle()
        self.assertEqual(post.call_count, 2)
        self.assertEqual(len(save.call_args_list[-1][0][1]), 1)

    def test_failure_keeps_item_and_stops(self):
        queue = [self._queue_item("a"), self._queue_item("b")]
        with mock.patch.object(bot, "IG_POSTS_PER_CYCLE", 2), \
                mock.patch.object(bot, "IG_POST_DELAY", 0), \
                mock.patch.object(bot, "load_json", return_value=queue), \
                mock.patch.object(bot, "save_json") as save, \
                mock.patch.object(bot, "arte_para_publicar",
                                  return_value="https://img/arte.jpg"), \
                mock.patch.object(bot, "post_to_instagram",
                                  return_value=False) as post:
            bot.instagram_cycle()
        self.assertEqual(post.call_count, 1)
        save.assert_not_called()


def _coupon_json(cid="1", status="ACTIVE", **extra):
    coupon = {
        "campaign_id": cid,
        "icon": "https://http2.mlstatic.com/cupom.jpg",
        "title": {"text": "R$ 20 OFF"},
        "category": "Loja X",
        "amount": {"min_amount": "Compra mínima R$ 50",
                   "cap_amount": "Limite de desconto R$ 20"},
        "benefit_mode": "FIXED",
        "action": {"text": "Conferir produtos", "type": "link",
                   "value": "https://lista.mercadolivre.com.br/_CustId_1"
                            "?coupon_campaign_id=1"},
        "status": {"id": status},
        "expiration_date": "2026-12-31T02:59:59Z",
        "segmentations": {"has_items": True, "total_items": 10},
    }
    coupon.update(extra)
    return coupon


def _coupon_page(coupons):
    data = {"appProps": {"pageProps": {"floxPreloadedState": {
        "@meli/web/flox/FLOX_STATE": {"brickStack": {
            "carousel_1": {"data": {"coupons": coupons}},
            "carousel_2": {"data": {"coupons": coupons}},
        }}}}}}
    return ('<html><body><script id="__NORDIC_RENDERING_CTX__">'
            "_n.ctx.r=" + json.dumps(data) + ";</script></body></html>")


class CupomParserTests(unittest.TestCase):
    def test_extrai_ativos_e_remove_duplicados(self):
        coupons = [_coupon_json("1"), _coupon_json("2", status="INACTIVE"),
                   _coupon_json("1"), _coupon_json("3", category="Loja Y")]
        found = bot.extract_ml_coupons(_coupon_page(coupons))
        self.assertEqual([c["id"] for c in found], ["1", "3"])
        self.assertEqual(found[0]["seller"], "Loja X")
        self.assertEqual(found[0]["title"], "R$ 20 OFF")
        self.assertEqual(found[0]["expiration"], "31/12")
        self.assertEqual(found[0]["min_amount"], "Compra mínima R$ 50")
        self.assertEqual(found[0]["total_items"], 10)
        self.assertTrue(found[0]["link"].startswith("https://lista."))

    def test_ignora_cupom_sem_itens(self):
        coupon = _coupon_json("9", segmentations={"has_items": False})
        self.assertEqual(bot.extract_ml_coupons(_coupon_page([coupon])), [])

    def test_reserva_pelos_cards_html(self):
        html = """
        <article class="smart-coupon smart-coupon--highlight">
          <p class="smart-coupon-highlight__category">Loja X</p>
          <span class="smart-coupon-highlight__title-text">R$ 10 OFF</span>
          <img src="https://img/x.jpg">
        </article>
        <article class="smart-coupon smart-coupon--highlight">
          <span class="smart-coupon-highlight__title-text">sem vendedor</span>
        </article>
        """
        found = bot.extract_ml_coupons(html)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["seller"], "Loja X")
        self.assertEqual(found[0]["title"], "R$ 10 OFF")
        self.assertEqual(found[0]["link"], "")
        self.assertEqual(found[0]["icon"], "https://img/x.jpg")

    def test_pagina_de_erro_nao_quebra(self):
        self.assertEqual(
            bot.extract_ml_coupons(
                "<html>Hubo un error accediendo a esta pagina</html>"), [])


class CupomPostTests(unittest.TestCase):
    def setUp(self):
        bot.LINK_FAIL_NOTICE.clear()

    def test_publica_com_link_e_botao(self):
        coupon = bot.extract_ml_coupons(_coupon_page([_coupon_json()]))[0]
        with mock.patch.object(bot, "generate_affiliate_link",
                               return_value=("https://meli.la/cupom", None)) as gen, \
                mock.patch.object(bot, "send_message", return_value=True) as send:
            ok = bot.post_coupon(coupon)
        self.assertTrue(ok)
        gen.assert_called_once()
        keyboard = send.call_args.kwargs["reply_markup"]
        self.assertEqual(keyboard["inline_keyboard"][0][0]["url"],
                         "https://meli.la/cupom")
        self.assertIn("Loja X", send.call_args[0][0])
        self.assertIn("R$ 20 OFF", send.call_args[0][0])

    def test_sem_link_nao_publica(self):
        coupon = bot.extract_ml_coupons(_coupon_page([_coupon_json()]))[0]
        with mock.patch.object(bot, "generate_affiliate_link",
                               return_value=(None, "sem login")), \
                mock.patch.object(bot, "send_message") as send, \
                mock.patch.object(bot, "notify_admin") as adm:
            ok = bot.post_coupon(coupon)
        self.assertFalse(ok)
        send.assert_not_called()
        adm.assert_called_once()


class CupomCycleTests(unittest.TestCase):
    def test_envia_so_os_novos_e_grava_estado(self):
        coupons = bot.extract_ml_coupons(_coupon_page(
            [_coupon_json("1"), _coupon_json("2")]))
        page = mock.Mock()
        page.text = "<html></html>"
        page.url = bot.ML_COUPONS_URL
        with mock.patch.object(bot, "browser_get", return_value=page), \
                mock.patch.object(bot, "extract_ml_coupons",
                                  return_value=coupons), \
                mock.patch.object(bot, "load_json",
                                  return_value={"1": {"at": time.time()}}), \
                mock.patch.object(bot, "save_json") as save, \
                mock.patch.object(bot, "post_coupon",
                                  return_value=True) as post:
            enviados = bot.cupons_cycle()
        self.assertEqual(enviados, 1)
        post.assert_called_once()
        self.assertEqual(post.call_args[0][0]["id"], "2")
        self.assertEqual(save.call_args[0][1]["2"]["seller"], "Loja X")


if __name__ == "__main__":
    unittest.main()
