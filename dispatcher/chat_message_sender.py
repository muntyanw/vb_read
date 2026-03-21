import pyautogui as pag
import pyperclip

from core import gui_driver as gd


def send_text_to_active_chat(window, input_xy: tuple[int, int], text: str) -> None:
    """
    Reusable chat send primitive:
    focus input field, paste message and press Enter.
    """
    input_x, input_y = int(input_xy[0]), int(input_xy[1])
    window.set_focus()
    gd.click(input_x, input_y)
    gd.pause(0.2)

    pyperclip.copy(text)
    pag.hotkey("ctrl", "v")
    gd.pause(0.2)
    pag.press("enter")
    gd.pause(0.5)
