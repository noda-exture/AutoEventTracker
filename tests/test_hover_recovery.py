import unittest
from unittest.mock import Mock
from hover_recovery import recover_hover


class HoverRecoveryTests(unittest.TestCase):
    def test_success_does_not_probe_next_action(self):
        ready = Mock()
        self.assertEqual(recover_hover(Mock(), ready), 'completed')
        ready.assert_not_called()

    def test_missing_transient_hover_is_unconfirmed(self):
        hover = Mock(side_effect=TimeoutError())
        self.assertEqual(recover_hover(hover, lambda: True), 'unconfirmed')
        self.assertEqual(hover.call_count, 1)

    def test_required_menu_is_retried(self):
        hover = Mock(side_effect=[TimeoutError(), None])
        self.assertEqual(recover_hover(hover, lambda: False), 'completed')
        self.assertEqual(hover.call_count, 2)

    def test_unrecoverable_hover_continues_without_manual_input(self):
        hover = Mock(side_effect=TimeoutError())
        self.assertEqual(recover_hover(hover, lambda: False), 'unconfirmed')
        self.assertEqual(hover.call_count, 2)
