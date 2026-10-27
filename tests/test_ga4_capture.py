import copy
import unittest
from unittest.mock import patch

from measurement_adapters.ga4 import GA4Adapter, collect_params, split_events
from tracker import wait_for_final_analytics


class GA4BatchTests(unittest.TestCase):
    def test_batch_keeps_common_values_and_isolates_event_parameters(self):
        packet = {'type': 'GA4', 'url': 'https://www.google-analytics.com/g/collect?tid=G-TEST&dl=https%3A%2F%2Fexample.test%2Fsecond',
                  'step_id': '0024', 'page_id': 'main',
                  'post_data': 'en=page_view&epn.hour=18&ep.title=one%0Atwo\r\nen=search_view&ep.query=camera'}
        original = copy.deepcopy(packet)
        events = GA4Adapter().filter_events([packet])
        self.assertEqual([collect_params(e)['en'] for e in events], ['page_view', 'search_view'])
        self.assertEqual(collect_params(events[0])['ep.title'], 'one\ntwo')
        self.assertNotIn('epn.hour', collect_params(events[1]))
        self.assertNotIn('ep.query', collect_params(events[0]))
        for event in events:
            self.assertEqual(collect_params(event)['tid'], 'G-TEST')
            self.assertEqual(collect_params(event)['dl'], 'https://example.test/second')
            self.assertEqual(event['step_id'], '0024')
        self.assertEqual(packet, original)
        self.assertEqual(GA4Adapter().filter_events(events), events)

    def test_single_event_is_unchanged(self):
        for body in (None, '', 'en=page_view'):
            packet = {'type': 'GA4', 'post_data': body}
            self.assertEqual(split_events(packet), [packet])


class FinalCaptureTests(unittest.TestCase):
    def run_wait(self, load_at=0, popup_at=None, request_at=None):
        clock = [0.0]
        states = {'main': {'last_request_at': None}}

        class Page:
            def is_closed(self):
                return False

            def evaluate(self, expression):
                return 'complete' if clock[0] >= load_at else 'loading'

            def wait_for_timeout(self, ms):
                clock[0] += ms / 1000
                if request_at is not None and clock[0] >= request_at:
                    states['main']['last_request_at'] = request_at

        main, popup = Page(), Page()

        class Context:
            @property
            def pages(self):
                return [main, popup] if popup_at is not None and clock[0] >= popup_at else [main]

        with patch('tracker.time.monotonic', side_effect=lambda: clock[0]):
            wait_for_final_analytics(Context(), states)
        return clock[0]

    def test_waits_five_seconds_after_load(self):
        elapsed = self.run_wait(load_at=3)
        self.assertGreaterEqual(elapsed, 8)
        self.assertLess(elapsed, 8.3)

    def test_late_popup_gets_observation_window(self):
        elapsed = self.run_wait(popup_at=4)
        self.assertGreaterEqual(elapsed, 9)
        self.assertLess(elapsed, 9.3)

    def test_late_analytics_extends_quiet_wait(self):
        self.assertGreaterEqual(self.run_wait(request_at=4.8), 5.8)

    def test_unfinished_load_has_bounded_wait(self):
        self.assertLess(self.run_wait(load_at=100), 15.2)


if __name__ == '__main__':
    unittest.main()
