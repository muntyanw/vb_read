import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from dispatcher import dispatch_client as client


class CommentsRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.header = np.full((100, 220, 3), 255, dtype=np.uint8)
        template = cv2.imread(str(client.TEMPLATE_DIR / "return_to_group.png"))
        self.header[10:41, 40:75] = cv2.cvtColor(template, cv2.COLOR_BGR2RGB)
        self.word = {
            "text": "Комментарии",
            "left": 170,
            "top": 40,
            "width": 160,
            "height": 24,
        }

    def test_arrow_is_found_only_with_comments_header(self):
        with patch.object(client, "perform_ocr_with_positions", return_value=[self.word]):
            x, y = client._comments_back_position(self.header)
        self.assertTrue(50 <= x <= 65 and 20 <= y <= 32)

        with patch.object(client, "perform_ocr_with_positions", return_value=[]):
            self.assertIsNone(client._comments_back_position(self.header))

    def test_missing_arrow_does_not_click(self):
        blank = np.full_like(self.header, 255)
        with patch.object(client, "perform_ocr_with_positions", return_value=[self.word]):
            with self.assertRaisesRegex(RuntimeError, "back arrow not found"):
                client._comments_back_position(blank)

    def test_close_checks_that_comments_disappear(self):
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=100, top=50, right=900, bottom=750)
        with patch.object(client, "take_screenshot", return_value=self.header), \
             patch.object(client, "_comments_back_position", side_effect=[(57, 25), None]), \
             patch.object(client.pag, "click") as click, \
             patch.object(client.gd, "pause"):
            self.assertTrue(client.close_comments_if_open(window))
            click.assert_called_once_with(157, 75)

        with patch.object(client, "take_screenshot", return_value=self.header), \
             patch.object(client, "_comments_back_position", return_value=(57, 25)), \
             patch.object(client.pag, "click"), \
             patch.object(client.gd, "pause"):
            with self.assertRaisesRegex(RuntimeError, "comments are still open"):
                client.close_comments_if_open(window)

    def test_normal_chat_is_not_clicked(self):
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=0, top=0, right=800, bottom=700)
        with patch.object(client, "take_screenshot", return_value=self.header), \
             patch.object(client, "_comments_back_position", return_value=None), \
             patch.object(client.pag, "click") as click:
            self.assertFalse(client.close_comments_if_open(window))
            click.assert_not_called()

    def test_recovery_discards_old_message_coordinates(self):
        state = SimpleNamespace(y_mess=[(10, 20)], search_board_mess_x_start=0, search_board_mess_y_start=0)
        with patch.object(client, "close_comments_if_open", return_value=True), \
             patch.object(client.gd, "right_click") as right_click:
            result = asyncio.run(client.send_messages_from_y_mess(Mock(), {}, state))
            self.assertEqual(result, "repeat")
            right_click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
