# -*- coding: utf-8 -*-
"""Testes offline dos geradores de link de afiliado e do publish."""

import hashlib
import json
import sys
import tempfile
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
        with mock.patch.object(bot, "BROWSER_SCRAPING", True), \
                mock.patch.object(bot, "expand_url", side_effect=lambda u: u), \
                mock.patch.object(bot, "browser_eval",
                                  return_value={"ok": True,
                                                "value": {"ok": True,
                                                          "link": "https://shope.ee/ok"}}):
            link, error = bot.generate_shopee_portal_link(
                "https://shopee.com.br/product/1/2")
        self.assertEqual(link, "https://shope.ee/ok")
        self.assertIsNone(error)

    def test_portal_link_falls_back_to_open_api(self):
        with mock.patch.object(bot, "BROWSER_SCRAPING", True), \
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


if __name__ == "__main__":
    unittest.main()
