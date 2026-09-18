import unittest

from openpyxl import Workbook

from excel_reporter import (
    align_step_groups,
    match_packets_in_step,
    packet_identity,
    process_single_sheet,
)
from tracker import prepare_steps


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
    def test_missing_step_ids_are_added_without_overwriting_existing_ids(self):
        scenario = {
            "steps": [
                {"action": "click", "memo": "first"},
                {"step_id": "saved-step", "action": "fill", "memo": "second"},
            ]
        }

        steps = prepare_steps(scenario, project_dir="unused")

        self.assertEqual(steps[0]["step_id"], "step_0001")
        self.assertEqual(steps[0]["step_name"], "first")
        self.assertEqual(steps[1]["step_id"], "saved-step")

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
