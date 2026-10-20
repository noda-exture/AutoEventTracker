"""Browser regression tests for partially obscured hover targets."""
import unittest

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from tracker import hover_first_exposed_point


class HoverExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 800})
        self.page.set_content("""
            <style>
                .js__modal-wrap { position:fixed; inset:0; background:#999; }
                #modal { position:fixed; left:440px; top:250px;
                         width:400px; height:300px; background:white; }
                button { position:absolute; inset:100px 50px; }
            </style>
            <div class="js__modal-wrap"
                 onmouseenter="this.dataset.entered='yes'"></div>
            <div id="modal"><button>次へ</button></div>
        """)

    def tearDown(self):
        self.page.close()

    def test_background_center_blocked_by_next_button(self):
        target = self.page.locator(".js__modal-wrap")
        self.page.mouse.move(640, 400)
        target.evaluate("el => delete el.dataset.entered")
        with self.assertRaises(PlaywrightTimeoutError):
            target.hover(timeout=400)
        self.assertIsNone(target.get_attribute("data-entered"))
        hover_first_exposed_point(target, timeout_ms=2000)
        self.assertEqual(target.get_attribute("data-entered"), "yes")

    def test_fully_covered_target_still_fails(self):
        self.page.locator("#modal").evaluate(
            "el => el.style.cssText='position:fixed;inset:0;width:auto;height:auto'"
        )
        target = self.page.locator(".js__modal-wrap")
        with self.assertRaises(PlaywrightTimeoutError):
            hover_first_exposed_point(target, timeout_ms=400)
        self.assertIsNone(target.get_attribute("data-entered"))


if __name__ == "__main__":
    unittest.main()
