# -*- coding: utf-8 -*-
"""Testes offline dos geradores de link de afiliado e do publish."""

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot
import panel_sync


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


class AmazonImageTests(unittest.TestCase):
    def test_landing_image_usa_data_old_hires(self):
        html = """
        <html><head><title>Echo Dot | Amazon.com.br</title></head><body>
          <div id="imgTagWrapperId">
            <img data-old-hires="https://m.media-amazon.com/images/I/6182._AC_SL1000_.jpg"
                 src="https://m.media-amazon.com/images/I/6182._AC_SY300_.jpg">
          </div>
          <span class="a-price"><span class="a-offscreen">R$ 329,00</span></span>
        </body></html>
        """
        title, price, _, image = bot.extract_from_html(
            html, "https://www.amazon.com.br/dp/B07FZ8S74R")
        self.assertEqual(image, "https://m.media-amazon.com/images/I/6182._AC_SL1000_.jpg")
        self.assertEqual(price, 329.0)
        self.assertEqual(title, "Echo Dot")

    def test_dynamic_image_escolhe_o_maior(self):
        html = """
        <html><head><title>Produto</title></head><body>
        <img id="landingImage" data-a-dynamic-image='{
            "https://m.media-amazon.com/images/I/a._AC_SY355_.jpg": [355, 355],
            "https://m.media-amazon.com/images/I/a._AC_SL1000_.jpg": [1000, 1000]}'>
        <span class="a-price"><span class="a-offscreen">R$ 99,90</span></span>
        </body></html>
        """
        _, _, _, image = bot.extract_from_html(
            html, "https://www.amazon.com.br/dp/B0CXF5TCLK")
        self.assertEqual(image, "https://m.media-amazon.com/images/I/a._AC_SL1000_.jpg")


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

    def test_fecha_abas_abertas_pelo_script(self):
        driver = mock.Mock()
        driver.current_window_handle = "A"
        driver.window_handles = ["A", "B", "C"]
        driver.execute_async_script.return_value = {
            "__selenium_eval__": True, "ok": True, "value": "ok",
        }
        with mock.patch.object(bot, "selenium_driver", return_value=driver):
            bot.selenium_eval("https://example.com", "return 1;", wait=0)
        fechadas = [c.args[0] for c in driver.switch_to.window.call_args_list]
        self.assertEqual(fechadas.count("B"), 1)
        self.assertEqual(fechadas.count("C"), 1)
        self.assertEqual(driver.close.call_count, 2)
        self.assertEqual(fechadas[-1], "A")


class CdpTabTests(unittest.TestCase):
    def setUp(self):
        bot._CDP["target_id"] = None

    def tearDown(self):
        bot._CDP["target_id"] = None

    def _lista(self, ids):
        return [{"id": i, "type": "page", "webSocketDebuggerUrl": f"ws://{i}"}
                for i in ids]

    def test_reaproveita_aba_e_fecha_as_extras(self):
        resposta = mock.Mock(status_code=200)
        resposta.json.return_value = self._lista(["A", "B"])
        with mock.patch.object(bot.requests, "get", return_value=resposta) as get, \
                mock.patch.object(bot.requests, "put") as put:
            aba = bot._cdp_aba("http://127.0.0.1:9222")
        self.assertEqual(aba["id"], "A")
        self.assertEqual(bot._CDP["target_id"], "A")
        put.assert_not_called()
        fechadas = [c.args[0] for c in get.call_args_list
                    if "/json/close/" in c.args[0]]
        self.assertEqual(fechadas, ["http://127.0.0.1:9222/json/close/B"])

    def test_reusa_a_aba_ja_escolhida(self):
        bot._CDP["target_id"] = "B"
        resposta = mock.Mock(status_code=200)
        resposta.json.return_value = self._lista(["A", "B"])
        with mock.patch.object(bot.requests, "get", return_value=resposta) as get, \
                mock.patch.object(bot.requests, "put") as put:
            aba = bot._cdp_aba("http://127.0.0.1:9222")
        self.assertEqual(aba["id"], "B")
        put.assert_not_called()
        fechadas = [c.args[0] for c in get.call_args_list
                    if "/json/close/" in c.args[0]]
        self.assertEqual(fechadas, ["http://127.0.0.1:9222/json/close/A"])

    def test_so_cria_aba_se_nao_houver_nenhuma(self):
        lista = mock.Mock(status_code=200)
        lista.json.return_value = []
        nova = mock.Mock(status_code=200)
        nova.json.return_value = {"id": "N", "type": "page",
                                  "webSocketDebuggerUrl": "ws://N"}
        with mock.patch.object(bot.requests, "get", return_value=lista), \
                mock.patch.object(bot.requests, "put", return_value=nova) as put:
            aba = bot._cdp_aba("http://127.0.0.1:9222")
        self.assertEqual(aba["id"], "N")
        self.assertEqual(bot._CDP["target_id"], "N")
        self.assertEqual(put.call_count, 1)


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

    def test_publish_sends_link_to_instagram_queue(self):
        product = self._product("pv_test_ig")
        product["affiliate_link"] = "https://meli.la/ig"
        with mock.patch.object(bot, "schedule_instagram",
                               return_value=True) as sched, \
                mock.patch.object(bot, "send_message", return_value=True), \
                mock.patch.object(bot, "save_to_vitrine"), \
                mock.patch.object(bot, "load_json", return_value={}), \
                mock.patch.object(bot, "save_json"):
            bot.publish(product, announce_instagram=True)
        self.assertEqual(sched.call_args.kwargs.get("link"), "https://meli.la/ig")

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

    def test_queue_stores_affiliate_link_for_first_comment(self):
        with mock.patch.object(bot, "IG_MIN_DISCOUNT", 0), \
                mock.patch.object(bot, "load_json", return_value=[]), \
                mock.patch.object(bot, "save_json") as save:
            queued = bot.schedule_instagram(
                {"thumbnail": "https://img/1.jpg"}, "Fone", 80.0, 100.0,
                link="https://meli.la/abc")
        self.assertTrue(queued)
        item = save.call_args[0][1][-1]
        self.assertEqual(item["link"], "https://meli.la/abc")
        self.assertTrue(item["qid"].startswith("q_"))


class InstagramHashtagTests(unittest.TestCase):
    def test_hashtags_are_three_distinct_from_the_list(self):
        for _ in range(20):
            tags = bot.ig_hashtags().split()
            self.assertEqual(len(tags), 3)
            self.assertEqual(len(set(tags)), 3)
            self.assertTrue(set(tags).issubset(set(bot.IG_HASHTAGS)))

    def test_hashtag_count_env_never_exceeds_list(self):
        self.assertLessEqual(bot.IG_HASHTAG_COUNT, len(bot.IG_HASHTAGS))
        self.assertGreaterEqual(bot.IG_HASHTAG_COUNT, 1)


class InstagramCycleTests(unittest.TestCase):
    def _queue_item(self, title, link=None):
        item = {"title": title, "price": 80.0, "old": 100.0,
                "image": "https://img/1.jpg", "pct": 20.0}
        if link:
            item["link"] = link
        return item

    def test_posts_two_per_cycle(self):
        queue = [self._queue_item(t) for t in ("a", "b", "c")]

        def fake_load(path, default=None):
            return queue if str(path).endswith("ig_queue.json") else default

        def fake_save(path, data):
            if str(path).endswith("ig_queue.json"):
                queue[:] = data

        with mock.patch.object(bot, "IG_POSTS_PER_CYCLE", 2), \
                mock.patch.object(bot, "IG_POST_DELAY", 0), \
                mock.patch.object(bot, "load_json", side_effect=fake_load), \
                mock.patch.object(bot, "save_json", side_effect=fake_save) as save, \
                mock.patch.object(bot, "arte_para_publicar",
                                  return_value="https://img/arte.jpg"), \
                mock.patch.object(bot, "post_to_instagram",
                                  return_value=True) as post:
            bot.instagram_cycle()
        self.assertEqual(post.call_count, 2)
        self.assertEqual([item["title"] for item in queue], ["c"])
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

    def test_caption_has_three_hashtags_and_link_goes_to_first_comment(self):
        link = "https://meli.la/abc"
        queue = [self._queue_item("a", link=link)]
        tags = ["#achados", "#ofertas", "#promocao"]
        with mock.patch.object(bot, "IG_POSTS_PER_CYCLE", 1), \
                mock.patch.object(bot, "IG_POST_DELAY", 0), \
                mock.patch.object(bot, "load_json", return_value=queue), \
                mock.patch.object(bot, "save_json"), \
                mock.patch.object(bot, "arte_para_publicar",
                                  return_value="https://img/arte.jpg"), \
                mock.patch.object(bot.random, "sample", return_value=tags), \
                mock.patch.object(bot, "post_to_instagram",
                                  return_value=True) as post:
            bot.instagram_cycle()
        caption = post.call_args[0][1]
        self.assertEqual(post.call_args.kwargs.get("comment"), link)
        self.assertIn("Link no primeiro comentário", caption)
        for tag in tags:
            self.assertIn(tag, caption)

    def test_post_publishes_comment_with_media_id(self):
        respostas = [mock.Mock(), mock.Mock(), mock.Mock()]
        respostas[0].json.return_value = {"id": "container-1"}
        respostas[1].json.return_value = {"id": "media-1"}
        respostas[2].json.return_value = {"id": "comment-1"}
        with mock.patch.object(bot, "IG_ACCESS_TOKEN", "token"), \
                mock.patch.object(bot, "IG_USER_ID", "user-1"), \
                mock.patch.object(bot.requests, "post",
                                  side_effect=respostas) as post, \
                mock.patch.object(bot.time, "sleep"):
            ok = bot.post_to_instagram("https://img/arte.jpg", "legenda",
                                       comment="https://meli.la/abc")
        self.assertTrue(ok)
        url = post.call_args_list[2][0][0]
        self.assertTrue(url.endswith("/media-1/comments"))
        self.assertEqual(post.call_args_list[2][1]["data"]["message"],
                         "https://meli.la/abc")


class InstagramLegacyLinkTests(unittest.TestCase):
    def test_uses_item_link_without_reading_vitrine(self):
        item = {"title": "Fone", "price": 80.0, "link": "https://meli.la/new"}
        with mock.patch.object(bot, "load_json") as load:
            self.assertEqual(bot._ig_queue_link(item), "https://meli.la/new")
        load.assert_not_called()

    def test_recovers_link_by_image_from_vitrine(self):
        item = {"title": "Fone", "price": 80.0, "image": "https://img/1.jpg"}
        vitrine = [{"id": "x", "title": "Outro título", "price": 80.0,
                    "image": "https://img/1.jpg", "link": "https://meli.la/old"}]
        with mock.patch.object(bot, "load_json", return_value=vitrine):
            self.assertEqual(bot._ig_queue_link(item), "https://meli.la/old")

    def test_recovers_link_by_title_and_price(self):
        item = {"title": "Fone Bluetooth", "price": 80.0}
        vitrine = [{"id": "x", "title": "fone bluetooth", "price": 80.0,
                    "image": "", "link": "https://meli.la/titulo"}]
        with mock.patch.object(bot, "load_json", return_value=vitrine):
            self.assertEqual(bot._ig_queue_link(item), "https://meli.la/titulo")

    def test_without_match_returns_empty(self):
        item = {"title": "Fone", "price": 80.0}
        with mock.patch.object(bot, "load_json", return_value=[]):
            self.assertEqual(bot._ig_queue_link(item), "")


class InstagramQueueTests(unittest.TestCase):
    def test_fila_publica_tem_qid_e_ignora_lixo(self):
        fila = [{"title": "a", "price": 10.0, "image": "i"}, "lixo",
                {"qid": "q_x", "title": "b"}]
        with mock.patch.object(bot, "load_json", return_value=fila):
            pub = bot._ig_queue_publica()
        self.assertEqual([p["title"] for p in pub], ["a", "b"])
        self.assertTrue(pub[0]["qid"].startswith("q_"))
        self.assertEqual(pub[1]["qid"], "q_x")

    def test_remove_item_legado_pela_qid(self):
        item = {"id": "1", "title": "a", "image": "i", "price": 10.0}
        qid = bot._ig_queue_qid(item)
        fila = [item, {"qid": "q_b", "title": "b"}]

        def fake_load(path, default=None):
            return fila if str(path).endswith("ig_queue.json") else default

        def fake_save(path, data):
            if str(path).endswith("ig_queue.json"):
                fila[:] = data

        with mock.patch.object(bot, "load_json", side_effect=fake_load), \
                mock.patch.object(bot, "save_json", side_effect=fake_save):
            ok, msg = bot.delete_from_ig_queue(qid)
        self.assertTrue(ok)
        self.assertIn("1", msg)
        self.assertEqual([i["title"] for i in fila], ["b"])

    def test_remove_item_inexistente_nao_salva(self):
        with mock.patch.object(bot, "load_json",
                               return_value=[{"qid": "q_a"}]), \
                mock.patch.object(bot, "save_json") as save:
            ok, msg = bot.delete_from_ig_queue("q_x")
        self.assertFalse(ok)
        self.assertIn("não encontrado", msg)
        save.assert_not_called()


class InstagramDiagnosticTests(unittest.TestCase):
    def _call(self, comments):
        respostas = [mock.Mock(), mock.Mock(), mock.Mock()]
        respostas[0].json.return_value = {"id": "1", "username": "vagantepromo"}
        respostas[1].json.return_value = {
            "data": [{"id": "media-1", "timestamp": "2026-10-23T14:57:07+0000"}]
        }
        respostas[2].json.return_value = comments
        with mock.patch.object(bot, "IG_ACCESS_TOKEN", "token"), \
                mock.patch.object(bot.requests, "get",
                                  side_effect=respostas):
            return bot.instagram_diagnostico()

    def test_permission_ok(self):
        texto = self._call({"data": []})
        self.assertIn("Token válido: @vagantepromo", texto)
        self.assertIn("Autorização de comentários OK", texto)

    def test_permission_error_explains_scope(self):
        texto = self._call({"error": {"code": 200, "message": "Permissions error"}})
        self.assertIn("código 200", texto)
        self.assertIn("instagram_business_manage_comments", texto)

    def test_without_token(self):
        with mock.patch.object(bot, "IG_ACCESS_TOKEN", ""):
            self.assertIn("IG_ACCESS_TOKEN ausente", bot.instagram_diagnostico())


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


class ControlFlagTests(unittest.TestCase):
    def setUp(self):
        self._orig = dict(bot.CONTROL)

    def tearDown(self):
        with bot.CONTROL_LOCK:
            bot.CONTROL.clear()
            bot.CONTROL.update(self._orig)

    def test_defaults_ligados(self):
        for nome in ("channels", "sheet", "scrape", "coupons", "instagram", "telegram"):
            self.assertTrue(bot.control_enabled(nome))

    def test_desconhecido_nao_bloqueia(self):
        self.assertTrue(bot.control_enabled("nao_existe"))

    def test_apply_aplica_so_booleanos(self):
        bot.apply_control_flags({"instagram": False, "scrape": "sim", "x": False})
        self.assertFalse(bot.control_enabled("instagram"))
        self.assertTrue(bot.control_enabled("scrape"))

    def test_snapshot_e_copia(self):
        snap = bot.control_snapshot()
        snap["instagram"] = False
        self.assertTrue(bot.control_enabled("instagram"))


class RunNowTests(unittest.TestCase):
    def setUp(self):
        for chave in bot.RUN_NOW:
            bot.RUN_NOW[chave] = False

    def test_consome_uma_vez(self):
        self.assertFalse(bot.take_run("telegram"))
        bot.request_run("telegram")
        self.assertTrue(bot.take_run("telegram"))
        self.assertFalse(bot.take_run("telegram"))

    def test_ciclo_desconhecido_e_ignorado(self):
        bot.request_run("busca")
        self.assertFalse(bot.take_run("busca"))


class PanelExecuteTests(unittest.TestCase):
    def setUp(self):
        self._orig = dict(bot.CONTROL)
        for chave in bot.RUN_NOW:
            bot.RUN_NOW[chave] = False

    def tearDown(self):
        with bot.CONTROL_LOCK:
            bot.CONTROL.clear()
            bot.CONTROL.update(self._orig)

    def test_run_telegram_agenda_ciclo(self):
        self.assertEqual(bot.panel_execute("run_telegram", {}),
                         "ciclo do Telegram agendado")
        self.assertTrue(bot.take_run("telegram"))

    def test_set_flags(self):
        bot.panel_execute("set_flags", {"flags": {"instagram": False}})
        self.assertFalse(bot.control_enabled("instagram"))

    def test_delete_delega_para_a_vitrine(self):
        with mock.patch.object(bot, "delete_from_vitrine",
                               return_value=(True, "removido; 3 itens")) as dele:
            result = bot.panel_execute("delete_vitrine",
                                       {"id": "x", "remove_from_seen": True})
        self.assertIn("ok:", result)
        dele.assert_called_once_with("x", True)

    def test_delete_fila_ig_delega_para_a_fila(self):
        with mock.patch.object(bot, "delete_from_ig_queue",
                               return_value=(True, "removido; 2 itens")) as dele:
            result = bot.panel_execute("delete_ig_queue", {"qid": "q_x"})
        self.assertIn("ok:", result)
        dele.assert_called_once_with("q_x")

    def test_comando_desconhecido_estoura(self):
        with self.assertRaises(ValueError):
            bot.panel_execute("explodir", {})


class VitrineDeleteTests(unittest.TestCase):
    def test_remove_e_republica(self):
        vitrine = [{"id": "a", "price": 10.0}, {"id": "b", "price": 20.0}]
        with mock.patch.object(bot, "load_json", return_value=vitrine), \
                mock.patch.object(bot, "save_json") as save, \
                mock.patch.object(bot, "upload_to_blob",
                                  return_value="https://blob/v.json") as upload:
            ok, msg = bot.delete_from_vitrine("a")
        self.assertTrue(ok)
        self.assertEqual(save.call_args[0][1],
                         [{"id": "b", "price": 20.0}])
        upload.assert_called_once()

    def test_id_inexistente_nao_publica(self):
        vitrine = [{"id": "a", "price": 10.0}]
        with mock.patch.object(bot, "load_json", return_value=vitrine), \
                mock.patch.object(bot, "save_json") as save, \
                mock.patch.object(bot, "upload_to_blob") as upload:
            ok, msg = bot.delete_from_vitrine("z")
        self.assertFalse(ok)
        self.assertIn("não encontrado", msg)
        save.assert_not_called()
        upload.assert_not_called()

    def test_falha_no_blob(self):
        with mock.patch.object(bot, "load_json",
                               return_value=[{"id": "a", "price": 10.0}]), \
                mock.patch.object(bot, "save_json"), \
                mock.patch.object(bot, "upload_to_blob", return_value=None):
            ok, msg = bot.delete_from_vitrine("a")
        self.assertFalse(ok)
        self.assertIn("Blob", msg)

    def test_remove_do_seen(self):
        def fake_load(path, default=None):
            if path == bot.VITRINE_FILE:
                return [{"id": "a", "price": 10.0}]
            if path == bot.SEEN_FILE:
                return ["a", "b"]
            return default

        with mock.patch.object(bot, "load_json", side_effect=fake_load), \
                mock.patch.object(bot, "save_json") as save, \
                mock.patch.object(bot, "upload_to_blob",
                                  return_value="https://blob/v.json"):
            ok, _ = bot.delete_from_vitrine("a", remove_from_seen=True)
        self.assertTrue(ok)
        self.assertEqual(save.call_args[0][1], ["b"])


class ControlGatingTests(unittest.TestCase):
    def test_schedule_instagram_desligado(self):
        with mock.patch.object(bot, "control_enabled", return_value=False), \
                mock.patch.object(bot, "save_json") as save:
            queued = bot.schedule_instagram({"thumbnail": "x"}, "t", 10, 20)
        self.assertFalse(queued)
        save.assert_not_called()

    def test_instagram_cycle_desligado_nao_le_fila(self):
        with mock.patch.object(bot, "control_enabled", return_value=False), \
                mock.patch.object(bot, "load_json") as load:
            bot.instagram_cycle()
        load.assert_not_called()

    def test_telegram_cycle_desligado_nao_raspa(self):
        with mock.patch.object(bot, "control_enabled", return_value=False), \
                mock.patch.object(bot, "proxy_health") as health, \
                mock.patch.object(bot, "load_json") as load:
            bot.telegram_cycle()
        health.assert_not_called()
        load.assert_not_called()

    def test_cupons_desligados_nao_abrem_pagina(self):
        with mock.patch.object(bot, "control_enabled", return_value=False), \
                mock.patch.object(bot, "browser_get") as get:
            enviados = bot.cupons_cycle()
        self.assertEqual(enviados, 0)
        get.assert_not_called()

    def test_collect_products_sem_planilha(self):
        with mock.patch.object(bot, "fetch_sheet_products") as sheet, \
                mock.patch.object(bot, "fetch_mercado_livre_products",
                                  return_value=[]), \
                mock.patch.object(bot, "fetch_shopee_products", return_value=[]), \
                mock.patch.object(bot, "MIN_PRICE", 0), \
                mock.patch.object(bot, "MAX_PRICE", 0), \
                mock.patch.object(bot, "MIN_DISCOUNT", 0):
            bot.collect_products(include_sheet=False)
        sheet.assert_not_called()


class PanelStatusTests(unittest.TestCase):
    def test_campos_do_painel(self):
        with mock.patch.object(bot, "load_json", return_value=[]):
            dados = bot.panel_status()
        for campo in ("updated_at", "online", "flags", "last_telegram",
                      "last_instagram", "last_listener", "next_telegram",
                      "next_instagram", "next_channels", "seen", "ig_queue",
                      "ig_queue_items", "vitrine", "logs"):
            self.assertIn(campo, dados)
        self.assertEqual(dados["vitrine"], [])
        self.assertEqual(dados["ig_queue_items"], [])
        self.assertIn("instagram", dados["flags"])

    def test_painel_lista_a_fila_do_instagram(self):
        fila = [{"qid": "q_a", "title": "Fone", "price": 80.0,
                 "image": "https://img/1.jpg"}]

        def fake_load(path, default=None):
            if str(path).endswith("ig_queue.json"):
                return fila
            return default

        with mock.patch.object(bot, "load_json", side_effect=fake_load):
            dados = bot.panel_status()
        self.assertEqual(dados["ig_queue"], 1)
        self.assertEqual(dados["ig_queue_items"][0]["qid"], "q_a")
        self.assertEqual(dados["ig_queue_items"][0]["title"], "Fone")

    def test_proximos_ciclos(self):
        agora = 1_700_000_000.0

        def fake_load(path, default=None):
            if Path(path) == bot.CHANNEL_STATE_FILE:
                return {"last_batch_at": agora - 100,
                        "next_batch_at": agora + 1700}
            return default

        with mock.patch.object(bot, "PANEL_STATE",
                               {"last_telegram": agora - 60,
                                "last_instagram": agora - 120,
                                "last_listener": agora - 30}), \
                mock.patch.object(bot, "INTERVAL_TELEGRAM", 3600), \
                mock.patch.object(bot, "INTERVAL_INSTAGRAM", 10800), \
                mock.patch.object(bot, "SOURCE_CHANNELS", ["@a"]), \
                mock.patch.object(bot, "load_json", side_effect=fake_load), \
                mock.patch.object(bot.time, "time", return_value=agora), \
                mock.patch.dict(bot.CONTROL, {"telegram": True,
                                              "instagram": True,
                                              "channels": True}):
            dados = bot.panel_status()
        self.assertEqual(dados["next_telegram"], agora - 60 + 3600)
        self.assertEqual(dados["next_instagram"], agora - 120 + 10800)
        self.assertEqual(dados["next_channels"], agora + 1700)

    def test_proximos_desligados(self):
        with mock.patch.object(bot, "load_json", return_value=[]), \
                mock.patch.dict(bot.CONTROL, {"telegram": False,
                                              "instagram": False,
                                              "channels": False}):
            dados = bot.panel_status()
        self.assertIsNone(dados["next_telegram"])
        self.assertIsNone(dados["next_instagram"])
        self.assertIsNone(dados["next_channels"])

    def test_vitrine_publica_ignora_item_quebrado(self):
        itens = [{"id": 1, "title": "a", "price": 10.0, "link": "l",
                  "image": "i", "time": "t"}, "lixo", {"id": 2, "title": "b"}]
        with mock.patch.object(bot, "load_json", return_value=itens):
            pub = bot._vitrine_publica()
        self.assertEqual([i["id"] for i in pub], ["1", "2"])
        self.assertEqual(pub[0]["title"], "a")


class FirestoreValueTests(unittest.TestCase):
    def test_roundtrip(self):
        valores = [True, False, 12, 1.5, "texto", None, [1, "a"],
                   {"a": True, "b": [2]}]
        for valor in valores:
            self.assertEqual(panel_sync._from_value(panel_sync._to_value(valor)),
                             valor)

    def test_doc_completo(self):
        doc = {"fields": {"status": {"stringValue": "pending"},
                          "n": {"integerValue": "3"},
                          "ok": {"booleanValue": True}}}
        self.assertEqual(panel_sync._from_doc(doc),
                         {"status": "pending", "n": 3, "ok": True})

    def test_tipo_desconhecido_vira_none(self):
        self.assertIsNone(panel_sync._from_value({"geoPointValue": {}}))


class PanelSyncTests(unittest.TestCase):
    def _sync(self):
        return panel_sync.PanelSync(lambda flags: None,
                                    lambda tipo, payload: "ok",
                                    lambda: {"online": True},
                                    lambda msg: None)

    def test_sem_env_fica_desativado(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            sync = self._sync()
        self.assertFalse(sync.enabled)

    def test_com_env_fica_ativado(self):
        env = {"FIREBASE_PROJECT_ID": "p", "FIREBASE_API_KEY": "k",
               "FIREBASE_BOT_EMAIL": "e", "FIREBASE_BOT_PASSWORD": "s"}
        with mock.patch.dict(os.environ, env, clear=False):
            sync = self._sync()
        self.assertTrue(sync.enabled)

    def test_tick_aplica_flags_e_roda_comandos(self):
        chamadas = []
        sync = self._sync()
        sync.on_flags = lambda flags: chamadas.append(("flags", flags))
        sync.on_command = lambda tipo, payload: chamadas.append(("cmd", tipo)) or "feito"
        sync.get_doc = lambda path: {"flags": {"instagram": False}}
        sync.pending_commands = lambda: [("c1", {"type": "run_telegram"})]
        sync.write_status = lambda: chamadas.append(("status", None))
        sync.update_command = (lambda doc_id, status, result:
                               chamadas.append(("ack", doc_id, status, result)))
        sync.tick()
        self.assertEqual(chamadas[0], ("flags", {"instagram": False}))
        self.assertEqual(chamadas[1], ("cmd", "run_telegram"))
        self.assertEqual(chamadas[2],
                         ("ack", "c1", "done", "feito"))
        self.assertEqual(chamadas[3], ("status", None))

    def test_comando_com_erro_grava_error(self):
        gravado = []
        sync = self._sync()
        sync.on_command = lambda tipo, payload: (_ for _ in ()).throw(RuntimeError("x"))
        sync.update_command = lambda doc_id, status, result: gravado.append((status, result))
        sync.run_command("c9", {"type": "delete_vitrine"})
        self.assertEqual(gravado[0][0], "error")
        self.assertIn("RuntimeError", gravado[0][1])

    def test_pending_commands_le_nome_do_documento(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = [{
            "document": {
                "name": ("projects/p/databases/(default)/documents/"
                         "panel_commands/abc"),
                "fields": {"type": {"stringValue": "run_telegram"}},
            }
        }]
        sync = self._sync()
        sync._request = lambda method, url, **kw: resp
        self.assertEqual(sync.pending_commands(),
                         [("abc", {"type": "run_telegram"})])


class LogRedactionTests(unittest.TestCase):
    def test_token_do_telegram_nao_vaza_na_url(self):
        with mock.patch.object(bot, "TELEGRAM_TOKEN", "123456:SEGREDO123456"):
            texto = bot._redact(
                "url: /bot123456:SEGREDO123456/getUpdates?offset=1")
        self.assertNotIn("SEGREDO123456", texto)
        self.assertIn("***", texto)

    def test_segredo_vindo_do_ambiente_nao_vaza(self):
        with mock.patch.dict(os.environ, {"API_HASH": "hash-super-secreto"}):
            texto = bot._redact("falhou com hash-super-secreto no login")
        self.assertNotIn("hash-super-secreto", texto)
        self.assertIn("***", texto)


class ChannelOfferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(bot, "CHANNEL_QUEUE_FILE",
                                    Path(self.tmp.name) / "queue.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _item(self, key, price=80.0, old=100.0):
        return {"key": key, "id": "ch_" + key, "title": key, "price": price,
                "old": old, "image": "https://img",
                "link": "https://link/" + key, "url": "https://p/" + key}

    def test_fila_mantem_ordem_e_evita_repetida(self):
        self.assertTrue(bot._channel_enqueue(self._item("a")))
        self.assertTrue(bot._channel_enqueue(self._item("b")))
        self.assertFalse(bot._channel_enqueue(self._item("b")))
        queue = bot.load_json(bot.CHANNEL_QUEUE_FILE, [])
        self.assertEqual([q["key"] for q in queue], ["a", "b"])

    def test_lote_publica_os_primeiros(self):
        for key in ("a", "b", "c"):
            bot._channel_enqueue(self._item(key))
        with mock.patch.object(bot, "CHANNEL_BATCH_SIZE", 2), \
                mock.patch.object(bot, "CHANNEL_POST_DELAY", 0), \
                mock.patch.object(bot, "_post_channel_offer",
                                  return_value=True) as post:
            enviados = bot.publish_channel_batch()
        self.assertEqual(enviados, 2)
        self.assertEqual([c[0][0]["key"] for c in post.call_args_list],
                         ["a", "b"])
        restante = bot.load_json(bot.CHANNEL_QUEUE_FILE, [])
        self.assertEqual([q["key"] for q in restante], ["c"])

    def test_agenda_usa_next_e_cai_para_intervalo(self):
        state_file = Path(self.tmp.name) / "state.json"
        with mock.patch.object(bot, "CHANNEL_STATE_FILE", state_file):
            bot.save_json(state_file, {"last_batch_at": 100})
            _, ultimo, proximo = bot._channel_schedule()
            self.assertEqual(ultimo, 100)
            self.assertEqual(proximo, 100 + bot.CHANNEL_BATCH_INTERVAL)
            bot.save_json(state_file, {"last_batch_at": 100,
                                       "next_batch_at": 500})
            _, _, proximo = bot._channel_schedule()
            self.assertEqual(proximo, 500)

    def test_vitrine_so_depois_do_envio(self):
        item = self._item("a")
        with mock.patch.object(bot, "send_message", return_value=False), \
                mock.patch.object(bot, "save_to_vitrine") as vitrine:
            self.assertFalse(bot._post_channel_offer(item))
        vitrine.assert_not_called()
        with mock.patch.object(bot, "send_message", return_value=True), \
                mock.patch.object(bot, "save_to_vitrine") as vitrine:
            self.assertTrue(bot._post_channel_offer(item))
        vitrine.assert_called_once()


if __name__ == "__main__":
    unittest.main()
