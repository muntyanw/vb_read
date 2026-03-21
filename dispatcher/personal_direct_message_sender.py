import pyautogui as pag

from core import gui_driver as gd
from log import log_and_print
from utils import read_setting
from dispatcher.personal_message_input import insert_message_text


def _as_tuple2(value, default):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (int(value[0]), int(value[1]))
        except Exception:
            return default
    return default



def _as_optional_tuple4(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        except Exception:
            return None
    return None


class PersonalDirectMessageSender:
    """
    Sends a personal Viber message by phone number using click/type flow.
    Reuses PersonalBroadcastSender message input/send logic.
    """

    def __init__(self, personal_broadcast_sender):
        self._message_sender = personal_broadcast_sender

    def _search_contact_xy(self) -> tuple[int, int]:
        return _as_tuple2(read_setting("personal_direct_search_contact_xy"), (0, 0))

    def _select_contact_y_offset(self) -> int:
        try:
            return int(read_setting("personal_direct_select_contact_y_offset") or 0)
        except Exception:
            return 0

    def _not_found_scope(self) -> tuple[int, int, int, int] | None:
        return _as_optional_tuple4(read_setting("personal_direct_not_found_scope"))

    def send_to_phone(
        self,
        window,
        phone: str,
        message_text: str | None = None,
    ) -> None:
        if not str(phone or "").strip():
            raise ValueError("phone is empty")

        search_x, search_y = self._search_contact_xy()
        select_x = search_x
        select_y = search_y + self._select_contact_y_offset()
        not_found_scope = self._not_found_scope()

        log_and_print(
            f"[personal_direct] start phone={phone} search_xy={(search_x, search_y)} "
            f"select_y_offset={self._select_contact_y_offset()} not_found_scope={not_found_scope}",
            "info",
        )

        window.set_focus()

        gd.click(search_x, search_y)
        gd.pause(0.5)
        gd.click(search_x, search_y)
        log_and_print(f"[personal_direct] search field focused phone={phone}", "debug")

        pag.typewrite(str(phone), interval=0.03)
        log_and_print(f"[personal_direct] phone typed phone={phone}", "debug")

        gd.pause(1.0)

        if not_found_scope and gd.find_image(
            "viber_out.png",
            timeout=0.6,
            confidence=0.9,
            scope=not_found_scope,
            multiscale=True,
        ):
            gd.click(search_x, search_y)
            gd.pause(0.1)
            pag.hotkey("ctrl", "a")
            gd.pause(0.05)
            pag.press("delete")
            log_and_print(
                f"[personal_direct] contact not found phone={phone} scope={not_found_scope}; search input cleared",
                "warning",
            )
            raise RuntimeError(f"contact not found for phone={phone}")

        log_and_print(f"[personal_direct] contact lookup ok phone={phone}; click contact row", "debug")
        gd.click(select_x, select_y)
        gd.pause(0.5)
        gd.click(select_x, select_y)

        if not insert_message_text(self._message_sender, window, text=message_text):
            log_and_print(f"[personal_direct] message input failed phone={phone}", "error")
            raise RuntimeError("cannot insert message text")

        text_preview = (message_text or "")
        text_preview = text_preview if len(text_preview) <= 80 else text_preview[:80] + "..."
        log_and_print(
            f"[personal_direct] sent to phone={phone} search_xy={(search_x, search_y)} "
            f"select_xy={(select_x, select_y)} text_preview={text_preview}",
            "info",
        )
