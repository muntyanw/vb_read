import pyautogui as pag

from core import gui_driver as gd
from log import log_and_print
from utils import read_setting
from dispatcher.personal_message_input import insert_message_text
from dispatcher.outgoing_text import prepare_outgoing_text_for_ui


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
    def _verify_send_completed(self, phone: str, message_text: str | None = None) -> None:
        sender = self._message_sender
        expected_text = str(message_text if message_text is not None else sender._config.message_text or "")
        gd.pause(0.6)
        text_still_present = False
        try:
            if expected_text:
                text_still_present = bool(sender._input_contains_text(expected_text))
        except Exception as exc:
            log_and_print(f"[personal_direct] post-send input verification failed phone={phone}: {exc}", "info")
        state, send_score, mic_score = sender._detect_dialog_action_state_with_pause(
            sender._config.dialog_send_scope,
            pause_s=0.6,
        )
        log_and_print(
            f"[personal_direct] post-send verify phone={phone} state={state} "
            f"text_still_present={text_still_present} send_score={send_score:.3f} mic_score={mic_score:.3f}",
            "info",
        )
        if text_still_present:
            try:
                sender._save_dialog_action_snapshot(
                    sender._config.dialog_send_scope,
                    reason="direct_post_send_text_still_present",
                    state=state,
                    send_score=send_score,
                    mic_score=mic_score,
                    scan_id=None,
                    member_name=phone,
                )
            except Exception:
                pass
            raise RuntimeError(f"send click did not clear input for phone={phone}")

    def _click_dialog_send(self, phone: str, message_text: str | None = None) -> None:
        sender = self._message_sender
        dialog_send_scope = sender._config.dialog_send_scope
        action_state, send_score, mic_score = sender._detect_dialog_action_state_with_pause(dialog_send_scope, pause_s=1.0)
        log_and_print(
            f"[personal_direct] dialog action state={action_state} phone={phone} "
            f"send_score={send_score:.3f} mic_score={mic_score:.3f}",
            "debug",
        )
        if action_state == "microphone":
            sender._save_dialog_action_snapshot(
                dialog_send_scope,
                reason="direct_dialog_action_microphone",
                state=action_state,
                send_score=send_score,
                mic_score=mic_score,
                scan_id=None,
                member_name=phone,
            )
            raise RuntimeError(f"send button not ready, microphone detected for phone={phone}")
        if action_state == "unknown":
            log_and_print(
                f"[personal_direct] dialog action unknown phone={phone}; try direct send-image click",
                "warning",
            )

        if sender._dismiss_no_personal_messages_popup(scan_id=None, context="direct_before_send_click"):
            raise RuntimeError(f"cannot send personal messages to phone={phone}")

        click_xy = gd.find_image(
            sender._config.dialog_send_image,
            timeout=0.6,
            confidence=0.75,
            scope=dialog_send_scope,
            multiscale=True,
            is_debug=False,
        )
        if not click_xy:
            if action_state == "unknown":
                sender._save_dialog_action_snapshot(
                    dialog_send_scope,
                    reason="direct_dialog_action_unknown",
                    state=action_state,
                    send_score=send_score,
                    mic_score=mic_score,
                    scan_id=None,
                    member_name=phone,
                )
            sender._save_dialog_action_snapshot(
                dialog_send_scope,
                reason="direct_dialog_send_not_found",
                state=action_state,
                send_score=send_score,
                mic_score=mic_score,
                scan_id=None,
                member_name=phone,
            )
            raise RuntimeError(f"dialog send icon not found for phone={phone}")

        log_and_print(f"[personal_direct] dialog send match phone={phone} click_xy={click_xy}", "debug")
        try:
            sender._save_scope_click_snapshot(dialog_send_scope, click_xy, tag=f"pd_send_before_{phone}")
        except Exception:
            pass

        gd.click(int(click_xy[0]), int(click_xy[1]))
        log_and_print(f"[personal_direct] dialog send clicked phone={phone} scope={dialog_send_scope} click_xy={click_xy}", "debug")

        try:
            sender._save_scope_click_snapshot(dialog_send_scope, click_xy, tag=f"pd_send_after_{phone}")
        except Exception:
            pass

        if sender._dismiss_no_personal_messages_popup(scan_id=None, context="direct_after_send_click"):
            raise RuntimeError(f"send rejected by popup for phone={phone}")

        self._verify_send_completed(phone=phone, message_text=message_text)
        text_preview = str(message_text or "")
        text_preview = text_preview if len(text_preview) <= 80 else text_preview[:80] + "..."
        log_and_print(f"[personal_direct] dialog send confirmed phone={phone} text_preview={text_preview}", "debug")

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

        prepared_text = prepare_outgoing_text_for_ui(message_text)

        if not insert_message_text(self._message_sender, window, text=prepared_text):
            log_and_print(f"[personal_direct] message input failed phone={phone}", "info")
            raise RuntimeError(f"cannot insert message text for phone={phone}")

        self._click_dialog_send(phone=phone, message_text=prepared_text)

        text_preview = prepared_text
        text_preview = text_preview if len(text_preview) <= 80 else text_preview[:80] + "..."
        log_and_print(
            f"[personal_direct] sent to phone={phone} search_xy={(search_x, search_y)} "
            f"select_xy={(select_x, select_y)} text_preview={text_preview}",
            "info",
        )


