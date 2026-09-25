import unittest

from openpyxl import Workbook

from excel_reporter import (
    align_step_groups,
    match_packets_in_step,
    packet_identity,
    process_single_sheet,
)
from measurement_adapters import get_registered_adapters
from measurement_adapters.base import MeasurementAdapter
from measurement_adapters.ga4 import GA4Adapter
from tracker import (
    PageRegistry,
    click_first_actionable,
    fill_value,
    prepare_steps,
    scroll_page,
    select_value,
    wait_for_actionable_locator,
)


def ga4_packet(event_name, sequence, step_id="step_0001", step_index=0, page="/checkout"):
    return {
        "type": "GA4",
        "step_id": step_id,
        "step_index": step_index,
        "packet_index_in_step": sequence,
        "params": {
            "en": event_name,
            "tid": "G-TEST",
            "dl": f"https://example.com{page}",
        },
    }


def aa_packet(page_name, sequence, pe="", pev2=""):
    return {
        "type": "Adobe Analytics (Legacy)",
        "step_id": "step_0001",
        "step_index": 0,
        "packet_index_in_step": sequence,
        "params": {
            "pageName": page_name,
            "g": f"https://example.com/{page_name}",
            "pe": pe,
            "pev2": pev2,
        },
    }


def aep_packet(event_type, sequence):
    return {
        "type": "AEP Web SDK",
        "step_id": "step_0001",
        "step_index": 0,
        "packet_index_in_step": sequence,
        "xdm_payload": {
            "events": [{
                "xdm": {
                    "eventType": event_type,
                    "web": {"webPageDetails": {"name": "checkout", "URL": "https://example.com/checkout"}},
                }
            }]
        },
    }


class PacketMatchingTests(unittest.TestCase):
    def test_builtin_measurement_adapters_are_registered_independently(self):
        adapters = {adapter.key: adapter for adapter in get_registered_adapters()}

        self.assertEqual(set(adapters), {"GA4", "AA"})
        self.assertEqual(adapters["GA4"].sheet_name, "GA4")
        self.assertEqual(adapters["AA"].sheet_name, "Adobe Analytics")

    def test_ga4_adapter_extracts_post_body_parameters(self):
        adapter = GA4Adapter()
        packet = {
            "type": "GA4",
            "url": "https://www.google-analytics.com/g/collect?tid=G-TEST",
            "post_data": "en=purchase&value=1200",
        }

        self.assertEqual(adapter.extract_value(packet, {"source_key": "en"}), "purchase")
        self.assertEqual(adapter.packet_identity(packet)["event"], "purchase")

    def test_sheet_processing_accepts_an_unregistered_adapter(self):
        class CustomAdapter(MeasurementAdapter):
            key = "CUSTOM"
            sheet_name = "Custom Analytics"
            display_name = "Custom Analytics"

            def matches_event(self, event):
                return event.get("type") == self.key

            def extract_value(self, packet, mapping):
                if not packet:
                    return None
                return packet.get("params", {}).get(mapping["source_key"])

            def packet_identity(self, packet):
                if not packet:
                    return {}
                return {
                    "tool": self.key,
                    "source": self.display_name,
                    "event": packet.get("params", {}).get("event", ""),
                    "page": "",
                    "url": "",
                    "account": "",
                    "events": "",
                }

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Custom Analytics"
        sheet.append([])
        sheet.append(["Key", "Path", "Data", "項目", "説明"])
        sheet.append(["event", "", "", "イベント名", "送信イベント"])
        latest = {
            "type": "CUSTOM",
            "step_id": "0001",
            "step_index": 0,
            "packet_index_in_step": 0,
            "params": {"event": "purchase"},
        }
        config = {
            "excel_setting": {
                "font_name": "游ゴシック",
                "theme_color_new": "E2EFDA",
                "theme_color_old": "FFF2CC",
                "diff_color": "FFC7CE",
                "diff_font_color": "9C0006",
            },
            "extraction_rules": {"ignore_params": [], "nested_separator": "."},
        }

        process_single_sheet(
            sheet,
            CustomAdapter(),
            [latest],
            [latest],
            config,
            "latest.json",
            "baseline.json",
        )

        self.assertEqual(sheet["F3"].value, "purchase")

    def test_click_tries_next_matching_element_when_first_is_blocked(self):
        class Candidate:
            def __init__(self, blocked=False, visible=True):
                self.blocked = blocked
                self.visible = visible
                self.clicked = False

            def is_visible(self):
                return self.visible

            def click(self, timeout):
                if self.blocked:
                    raise RuntimeError("intercepts pointer events")
                self.clicked = True

        class Locator:
            def __init__(self, candidates):
                self.candidates = candidates

            @property
            def first(self):
                return self.candidates[0]

            def count(self):
                return len(self.candidates)

            def nth(self, index):
                return self.candidates[index]

        blocked = Candidate(blocked=True)
        actionable = Candidate()

        click_first_actionable(Locator([blocked, actionable]))

        self.assertFalse(blocked.clicked)
        self.assertTrue(actionable.clicked)

    def test_click_skips_hidden_duplicate_and_uses_visible_element(self):
        class Candidate:
            def __init__(self, visible):
                self.visible = visible
                self.clicked = False

            def is_visible(self):
                return self.visible

            def click(self, timeout):
                self.clicked = True

        class Locator:
            def __init__(self, candidates):
                self.candidates = candidates

            def count(self):
                return len(self.candidates)

            def nth(self, index):
                return self.candidates[index]

        hidden = Candidate(visible=False)
        visible = Candidate(visible=True)

        click_first_actionable(Locator([hidden, visible]))

        self.assertFalse(hidden.clicked)
        self.assertTrue(visible.clicked)

    def test_lazy_loaded_element_is_found_after_progressive_scroll(self):
        class Candidate:
            def is_visible(self):
                return True

            def is_enabled(self):
                return True

        candidate = Candidate()

        class Locator:
            def __init__(self, page):
                self.page = page

            def count(self):
                return 1 if self.page.scroll_count else 0

            def nth(self, index):
                return candidate

        class Page:
            def __init__(self):
                self.scroll_count = 0

            def locator(self, selector):
                return Locator(self)

            def evaluate(self, expression, value):
                self.scroll_count += 1

            def wait_for_timeout(self, timeout):
                return None

        page = Page()

        result = wait_for_actionable_locator(page, "#lazy-content", timeout_ms=1000)

        self.assertIs(result, candidate)
        self.assertEqual(page.scroll_count, 1)

    def test_actionable_element_is_found_inside_child_frame(self):
        class Candidate:
            def is_visible(self): return True
            def is_enabled(self): return True

        candidate = Candidate()

        class Locator:
            def __init__(self, candidates): self.candidates = candidates
            def count(self): return len(self.candidates)
            def nth(self, index): return self.candidates[index]

        class Scope:
            def __init__(self, candidates=None): self.candidates = candidates or []
            def locator(self, selector): return Locator(self.candidates)

        class Page(Scope):
            def __init__(self):
                super().__init__()
                self.frames = [self, Scope([candidate])]

        self.assertIs(wait_for_actionable_locator(Page(), "#in-frame"), candidate)

    def test_search_reverses_direction_at_end_of_scroll_surface(self):
        class Candidate:
            def is_visible(self): return True
            def is_enabled(self): return True

        candidate = Candidate()

        class Locator:
            def __init__(self, page): self.page = page
            def count(self): return 1 if -1 in self.page.directions else 0
            def nth(self, index): return candidate

        class Page:
            def __init__(self): self.directions = []
            def locator(self, selector): return Locator(self)
            def evaluate(self, expression, value):
                self.directions.append(value["direction"])
                return False
            def wait_for_timeout(self, timeout): return None

        page = Page()
        result = wait_for_actionable_locator(page, "#virtual-item", timeout_ms=1000)

        self.assertIs(result, candidate)
        self.assertEqual(page.directions[:2], [1, -1])

    def test_has_text_selector_tolerates_missing_dom_whitespace(self):
        class Candidate:
            def evaluate(self, expression, value):
                return "Tomonaga著者の記事を見る".replace(" ", "").find(value) >= 0

            def is_visible(self): return True
            def is_enabled(self): return True

        candidate = Candidate()

        class Locator:
            def __init__(self, candidates): self.candidates = candidates
            def count(self): return len(self.candidates)
            def nth(self, index): return self.candidates[index]

        class Page:
            def locator(self, selector):
                if selector == "a":
                    return Locator([candidate])
                return Locator([])

        result = wait_for_actionable_locator(
            Page(),
            'a:has-text("Tomonaga 著者の記事を見る")',
        )

        self.assertIs(result, candidate)

    def test_href_selector_ignores_changed_analytics_parameters(self):
        class Candidate:
            def evaluate(self, expression, value=None):
                return "https://example.com/service/?_gl=new-value&_ga_TEST=current"

            def is_visible(self): return True
            def is_enabled(self): return True

        candidate = Candidate()

        class Locator:
            def __init__(self, candidates): self.candidates = candidates
            def count(self): return len(self.candidates)
            def nth(self, index): return self.candidates[index]

        class Page:
            def locator(self, selector):
                return Locator([candidate] if selector == "a[href]" else [])

        result = wait_for_actionable_locator(
            Page(),
            'a[href="https://example.com/service/?_gl=recorded&_ga_TEST=old"]',
        )

        self.assertIs(result, candidate)

    def test_scroll_action_supports_absolute_and_relative_positions(self):
        class Page:
            def __init__(self):
                self.calls = []

            def evaluate(self, expression, value):
                self.calls.append((expression, value))

        page = Page()

        scroll_page(page, {"x": 10, "y": 900})
        scroll_page(page, 500)

        self.assertEqual(page.calls[0][1], [10, 900])
        self.assertEqual(page.calls[1][1], 500)

    def test_scroll_action_can_target_a_scroll_container(self):
        class Locator:
            def __init__(self): self.calls = []
            def evaluate(self, expression, value): self.calls.append((expression, value))

        target = Locator()
        scroll_page(None, {"x": 5, "y": 700}, target)

        self.assertEqual(target.calls[0][1], {"x": 5, "y": 700})

    def test_select_value_verifies_the_selected_option(self):
        class Locator:
            def __init__(self): self.value = None
            def select_option(self, value, timeout): self.value = value
            def input_value(self, timeout): return self.value

        locator = Locator()
        select_value(locator, "R08")

        self.assertEqual(locator.value, "R08")

    def test_fill_value_verifies_text_and_moves_focus(self):
        class Locator:
            def __init__(self):
                self.value = None
                self.pressed = None
                self.clicked = False
            def click(self, timeout): self.clicked = True
            def fill(self, value, timeout): self.value = value
            def input_value(self, timeout): return self.value
            def press(self, key, timeout): self.pressed = key

        locator = Locator()
        fill_value(locator, "GB6")

        self.assertEqual(locator.value, "GB6")
        self.assertEqual(locator.pressed, "Tab")
        self.assertTrue(locator.clicked)

    def test_page_registry_assigns_stable_ids_and_excludes_closed_tabs(self):
        class FakePage:
            def __init__(self):
                self.closed = False

            def is_closed(self):
                return self.closed

        main = FakePage()
        popup = FakePage()
        another_popup = FakePage()
        registry = PageRegistry(main)

        self.assertEqual(registry.page_id_for(main), "main")
        self.assertEqual(registry.register(popup), "page1")
        self.assertEqual(registry.register(popup), "page1")
        self.assertEqual(registry.register(another_popup), "page2")

        popup.closed = True
        self.assertIsNone(registry.get_live("page1"))
        self.assertEqual(set(registry.live_pages()), {"main", "page2"})

    def test_missing_step_ids_are_added_without_overwriting_existing_ids(self):
        scenario = {
            "steps": [
                {"action": "click", "memo": "first", "page_id": "main"},
                {"step_id": "saved-step", "action": "fill", "memo": "second"},
            ]
        }

        steps = prepare_steps(scenario, project_dir="unused")

        self.assertEqual(steps[0]["step_id"], "0001")
        self.assertEqual(steps[0]["step_name"], "first")
        self.assertEqual(steps[0]["page_id"], "main")
        self.assertEqual(steps[1]["step_id"], "saved-step")

    def test_existing_step_prefix_is_removed_during_preparation(self):
        scenario = {
            "steps": [
                {"step_id": "step_0042", "action": "click", "memo": "legacy"},
            ]
        }

        steps = prepare_steps(scenario, project_dir="unused")

        self.assertEqual(steps[0]["step_id"], "0042")

    def test_extra_packet_does_not_shift_following_matches(self):
        baseline = [
            ga4_packet("page_view", 0),
            ga4_packet("purchase", 1),
        ]
        latest = [
            ga4_packet("page_view", 0),
            ga4_packet("view_item", 1),
            ga4_packet("purchase", 2),
        ]

        pairs = match_packets_in_step(latest, baseline, "GA4")
        paired_events = {
            (packet_identity(new, "GA4").get("event"), packet_identity(old, "GA4").get("event"))
            for new, old, _ in pairs
            if new and old
        }
        latest_only = [packet_identity(new, "GA4").get("event") for new, old, _ in pairs if new and not old]

        self.assertEqual(paired_events, {("page_view", "page_view"), ("purchase", "purchase")})
        self.assertEqual(latest_only, ["view_item"])

    def test_adobe_extra_link_does_not_shift_following_match(self):
        baseline = [
            aa_packet("home", 0),
            aa_packet("checkout", 1, pe="lnk_o", pev2="purchase"),
        ]
        latest = [
            aa_packet("home", 0),
            aa_packet("campaign", 1, pe="lnk_o", pev2="promo"),
            aa_packet("checkout", 2, pe="lnk_o", pev2="purchase"),
        ]

        pairs = match_packets_in_step(latest, baseline, "AA")
        paired_events = {
            (packet_identity(new, "AA").get("event"), packet_identity(old, "AA").get("event"))
            for new, old, _ in pairs
            if new and old
        }

        self.assertIn(("lnk_o:purchase", "lnk_o:purchase"), paired_events)
        self.assertTrue(any(
            new and not old and packet_identity(new, "AA").get("event") == "lnk_o:promo"
            for new, old, _ in pairs
        ))

    def test_aep_packets_match_by_xdm_event_type(self):
        latest = [aep_packet("commerce.purchases", 1)]
        baseline = [aep_packet("commerce.purchases", 0)]

        pairs = match_packets_in_step(latest, baseline, "AA")

        self.assertEqual(len(pairs), 1)
        self.assertIsNotNone(pairs[0][0])
        self.assertIsNotNone(pairs[0][1])

    def test_different_event_names_are_not_forced_into_a_pair(self):
        latest = [ga4_packet("login", 0)]
        baseline = [ga4_packet("sign_up", 0)]

        pairs = match_packets_in_step(latest, baseline, "GA4")

        self.assertEqual(len(pairs), 2)
        self.assertTrue(any(new and not old for new, old, _ in pairs))
        self.assertTrue(any(old and not new for new, old, _ in pairs))

    def test_unidentified_helper_request_does_not_match_semantic_event(self):
        helper_request = {
            "type": "GA4",
            "step_id": "step_0001",
            "step_index": 0,
            "packet_index_in_step": 0,
            "params": {"tid": "G-TEST"},
        }
        latest = [helper_request, ga4_packet("purchase", 1)]
        baseline = [ga4_packet("purchase", 0)]

        pairs = match_packets_in_step(latest, baseline, "GA4")

        matched = [(new, old) for new, old, _ in pairs if new and old]
        self.assertEqual(len(matched), 1)
        self.assertEqual(packet_identity(matched[0][0], "GA4")["event"], "purchase")
        self.assertEqual(packet_identity(matched[0][1], "GA4")["event"], "purchase")
        self.assertTrue(any(new is helper_request and old is None for new, old, _ in pairs))

    def test_stable_step_id_wins_when_step_index_changes(self):
        latest = [ga4_packet("purchase", 0, step_id="purchase_step", step_index=4)]
        baseline = [ga4_packet("purchase", 0, step_id="purchase_step", step_index=3)]

        groups = align_step_groups(latest, baseline)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["step_id"], "purchase_step")
        self.assertEqual(len(groups[0]["new"]), 1)
        self.assertEqual(len(groups[0]["old"]), 1)

    def test_prefixed_and_unprefixed_step_ids_align(self):
        latest = [ga4_packet("purchase", 0, step_id="0001", step_index=4)]
        baseline = [ga4_packet("purchase", 0, step_id="step_0001", step_index=3)]

        groups = align_step_groups(latest, baseline)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["step_id"], "0001")
        self.assertEqual(len(groups[0]["new"]), 1)
        self.assertEqual(len(groups[0]["old"]), 1)

    def test_legacy_result_matches_new_step_by_index(self):
        latest = [ga4_packet("page_view", 0, step_id="step_0001", step_index=0)]
        baseline = [ga4_packet("page_view", 0, step_id=None, step_index=0)]
        baseline[0].pop("step_id")
        baseline[0].pop("packet_index_in_step")

        groups = align_step_groups(latest, baseline)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["new"]), 1)
        self.assertEqual(len(groups[0]["old"]), 1)
        self.assertEqual(groups[0]["old"][0]["packet_index_in_step"], 0)

    def test_excel_uses_formula_rules_and_keeps_item_columns_visible(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Adobe Analytics"
        sheet.append([])
        sheet.append(["AA項目", "XDM", "Data", "項目", "説明"])
        sheet.append(["eVar1", "", "", "会員区分", "送信された会員区分"])

        latest = aa_packet("checkout", 0)
        latest["params"]["eVar1"] = "member"
        baseline = aa_packet("checkout", 0)
        baseline["params"]["eVar1"] = "guest"
        config = {
            "excel_setting": {
                "font_name": "游ゴシック",
                "theme_color_new": "E2EFDA",
                "theme_color_old": "FFF2CC",
                "diff_color": "FFC7CE",
                "diff_font_color": "9C0006",
            },
            "extraction_rules": {"ignore_params": [], "nested_separator": "."},
        }

        process_single_sheet(
            sheet,
            "Adobe Analytics",
            [latest],
            [baseline],
            config,
            "latest.json",
            "baseline.json",
        )

        self.assertTrue(sheet.column_dimensions["A"].hidden)
        self.assertTrue(sheet.column_dimensions["B"].hidden)
        self.assertTrue(sheet.column_dimensions["C"].hidden)
        self.assertFalse(sheet.column_dimensions["D"].hidden)
        self.assertFalse(sheet.column_dimensions["E"].hidden)
        self.assertFalse(sheet.column_dimensions["F"].hidden)

        self.assertIsNone(sheet["F3"].fill.fill_type)
        self.assertIsNone(sheet["F8"].fill.fill_type)
        formulas = {
            formula
            for rules in sheet.conditional_formatting._cf_rules.values()
            for rule in rules
            for formula in (rule.formula or [])
        }
        self.assertIn('AND(F3<>"",F3<>F8,F3<>"最新になし")', formulas)
        self.assertIn('AND(F8<>"",F8<>F3,F8<>"比較元になし")', formulas)


if __name__ == "__main__":
    unittest.main()
