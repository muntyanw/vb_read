import pyautogui as pag
import pyperclip

from core import gui_driver as gd
from log import log_and_print


def insert_message_text(sender, window, text: str | None = None) -> bool:
    text = text if text is not None else sender._config.message_text
    if not text:
        log_and_print("[personal_broadcast] message text is empty", "error")
        return False

    x, y = sender._config.message_input_xy
    target_layout = sender._target_input_layout()
    previous_layout_name = None
    try:
        current_code = gd.get_current_layout()
        previous_layout_name = sender._LAYOUT_CODE_TO_NAME.get(int(current_code))
    except Exception:
        previous_layout_name = None

    try:
        gd.ensure_layout(target_layout)
    except Exception as exc:
        log_and_print(f"[personal_broadcast] cannot set input layout={target_layout}: {exc}", "error")

    last_error = None
    try:
        dialog_send_scope = sender._config.dialog_send_scope
        for attempt in range(1, 4):
            try:
                window.set_focus()
                gd.click(x, y)
                gd.pause(0.08)
                gd.click(x, y)
                log_and_print(
                    f"[personal_broadcast] double-click message input at {(x, y)} attempt={attempt}/3",
                    "debug",
                )
                gd.pause(0.25)

                pag.hotkey("ctrl", "a")
                gd.pause(0.05)
                pag.press("backspace")
                gd.pause(0.05)

                typed = sender._type_with_pywinauto(text)
                gd.pause(0.2)
                state, send_score, mic_score = sender._detect_dialog_action_state_with_pause(
                    dialog_send_scope,
                    pause_s=1.0,
                )
                log_and_print(
                    f"[personal_broadcast] post-keyboard-type state={state} typed={typed} "
                    f"send_score={send_score:.3f} mic_score={mic_score:.3f} attempt={attempt}/3",
                    "debug",
                )
                if state == "send":
                    log_and_print(
                        f"[personal_broadcast] message accepted via keyboard typing attempt={attempt}/3",
                        "debug",
                    )
                    return True

                pag.hotkey("ctrl", "a")
                gd.pause(0.04)
                pag.press("backspace")
                gd.pause(0.04)
                pyperclip.copy(text)
                sender._paste_ctrl_v()
                gd.pause(0.25)
                state, send_score, mic_score = sender._detect_dialog_action_state_with_pause(
                    dialog_send_scope,
                    pause_s=1.0,
                )
                log_and_print(
                    f"[personal_broadcast] post-paste(ctrl+v) state={state} "
                    f"send_score={send_score:.3f} mic_score={mic_score:.3f} attempt={attempt}/3",
                    "debug",
                )
                if state == "send":
                    log_and_print(
                        f"[personal_broadcast] message paste accepted via ctrl+v attempt={attempt}/3",
                        "debug",
                    )
                    return True

                pag.hotkey("ctrl", "a")
                gd.pause(0.04)
                pag.press("backspace")
                gd.pause(0.04)
                pyperclip.copy(text)
                sender._paste_shift_insert()
                gd.pause(0.25)
                state, send_score, mic_score = sender._detect_dialog_action_state_with_pause(
                    dialog_send_scope,
                    pause_s=1.0,
                )
                log_and_print(
                    f"[personal_broadcast] post-paste(shift+insert) state={state} "
                    f"send_score={send_score:.3f} mic_score={mic_score:.3f} attempt={attempt}/3",
                    "debug",
                )
                if state == "send":
                    log_and_print(
                        f"[personal_broadcast] message paste accepted via shift+insert attempt={attempt}/3",
                        "debug",
                    )
                    return True

                if attempt >= 2:
                    if sender._type_message_fallback(window, text, x, y):
                        log_and_print(
                            f"[personal_broadcast] message manual-typing fallback success attempt={attempt}/3",
                            "debug",
                        )
                        return True

                state, send_score, mic_score = sender._detect_dialog_action_state_with_pause(
                    dialog_send_scope,
                    pause_s=1.0,
                )
                log_and_print(
                    f"[personal_broadcast] paste verification failed attempt={attempt}/3 "
                    f"(state={state}, send_score={send_score:.3f}, mic_score={mic_score:.3f})",
                    "warning",
                )
                sender._save_dialog_action_snapshot(
                    dialog_send_scope,
                    reason=f"input_verify_failed_attempt{attempt}",
                    state=state,
                    send_score=send_score,
                    mic_score=mic_score,
                    scan_id=None,
                    member_name=None,
                )
            except Exception as exc:
                last_error = exc
                log_and_print(f"[personal_broadcast] paste attempt={attempt}/3 failed: {exc}", "error")
                gd.pause(0.2)

        if last_error:
            log_and_print(f"[personal_broadcast] paste failed after retries: {last_error}", "error")
        return False
    finally:
        if previous_layout_name and previous_layout_name != target_layout:
            try:
                gd.ensure_layout(previous_layout_name)
                log_and_print(
                    f"[personal_broadcast] keyboard layout restored to {previous_layout_name}",
                    "debug",
                )
            except Exception as exc:
                log_and_print(
                    f"[personal_broadcast] cannot restore keyboard layout to {previous_layout_name}: {exc}",
                    "error",
                )
