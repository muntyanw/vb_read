# viber_worker/dispatch_client.py
import os
from typing import Optional, Dict, Any, List, Union
import asyncio
import httpx
from pydantic import BaseModel, ValidationError
from datetime import datetime, timezone
from find_message import load_previous_text, save_current_text
from log import log_and_print
from core import gui_driver as gd
import pyperclip
import pyautogui as pag
from utils import read_setting
import hashlib
import ctypes
from vb_utils import scroll_with_mouse
from recognize_text import text_includes_fast
import time
from tg import telegram_channel_name

pag.FAILSAFE = False

DISPATCH_URL = os.getenv(
    "DISPATCH_URL", "http://46.63.40.211:8888/api/v1/dispatch/analyze"
)
DISPATCH_API_KEY = os.getenv(
    "DISPATCH_API_KEY",
    "3e7e07d4f2a64f99a95cf8b18a1381f635ea2cde93cce94e4dcbfdd4c3af5d87",
)

# Глобальный флаг для предотвращения двойной реакции
processed_messages = set()
# Семафор для последовательной обработки сообщений
processing_semaphore = asyncio.Semaphore(1)
count_y_mess_empty = 0


class DispatchError(Exception):
    pass


# ---- Клиентские модели под ответ сервера ----
class Action(BaseModel):
    type: str
    payload: Optional[Dict[str, Any]] = None


class Decision(BaseModel):
    matches: Optional[bool] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None

class MatchedContact(BaseModel):
    order_id: int
    carrier_id: int
    viber_contact_name: Optional[str] = None

class DispatchResult(BaseModel):
    message_id: str
    extracted: Dict[str, Any] = {}
    actions: List[Action] = []
    # опционально: поддержка старого/нового формата
    decision: Optional[Decision] = None
    matched_contacts: Optional[List[MatchedContact]] = None


def _dispatch_base_url() -> str:
    # из "http://host/api/v1/dispatch/analyze" → "http://host/api/v1/dispatch"
    base = DISPATCH_URL.rstrip("/")
    return base.rsplit("/", 1)[0]


async def has_active_orders(
    window_days: int = 2,
    include_count: bool = False,
    timeout_s: float = 5.0,
    retries: int = 1,
) -> tuple[bool, Optional[int]]:
    """
    Возвращает (has_active, count|None).
    - has_active: True/False — есть ли активные заказы в окне [сегодня..сегодня+window_days]
    - count: если include_count=True — количество (ограничено лимитом на сервере), иначе None
    """
    url = _dispatch_base_url() + "/has-active-orders"
    params = {
        "window_days": window_days,
        "include_count": "true" if include_count else "false",
    }
    headers = {
        "X-API-Key": DISPATCH_API_KEY,
        "X-Client": "viber-worker",
    }

    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s, follow_redirects=True
            ) as client:
                resp = await client.get(url, params=params, headers=headers)
                log_and_print(
                    f"[has_active_orders] GET {url} status={resp.status_code}"
                )
                if resp.status_code == 401:
                    raise DispatchError("Unauthorized: check X-API-Key")
                resp.raise_for_status()
                data = resp.json() or {}
                return bool(data.get("has_active")), data.get("count")
        except Exception as e:
            log_and_print(
                f"[has_active_orders] attempt {attempt+1}/{retries+1} failed: {e}",
                "error",
            )
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))

    log_and_print("[has_active_orders] giving up, returning (False, None)", "error")
    return False, None


def _fallback_result(message_id: str) -> DispatchResult:
    """Резервный ответ, чтобы наверх не улетал None."""
    return DispatchResult(
        message_id=message_id,
        extracted={},
        actions=[Action(type="ignore", payload=None)],
        decision=Decision(matches=False, confidence=0.0, reason="Fallback"),
    )


def _safe_action_type(a: Union[Action, Dict[str, Any], None]) -> Optional[str]:
    if a is None:
        return None
    if isinstance(a, dict):
        return a.get("type")
    try:
        return a.type  # pydantic-модель
    except Exception:
        return None


async def process_one_message_dispatcher(
    message_text: Optional[str], 
    file_path: Optional[str],
    s
):
    log_and_print("!!! process_one_message_dispatcher !!!")

    uid_source = message_text or file_path or f"msg-{time.time()}"
    if uid_source:
        processed_messages.add(uid_source)

    # Обрабатываем сообщение последовательно с использованием семафора
    async with processing_semaphore:
        try:
            log_and_print(f"Обработка сообщения: {message_text}", "info")
            md5_hash = hashlib.md5(uid_source.encode()).hexdigest()

            return await send_for_analysis(
                message_id=md5_hash,
                text=message_text or "",
                chat_id=s.name_viber_channel,
                sender="",  # <— отправляем имя отправителя
                attachments=None,
                locale="uk",
                timeout_s=float(read_setting("dispatch_timeout_s") or 15.0),
                retries=int(read_setting("dispatch_retries") or 2),
            )
        except Exception as e:
            log_and_print(f"Oшибка при обработке одного сообщения: {e}", "error")
            await asyncio.sleep(2)  # небольшая пауза
            # ВАЖНО: всегда возвращаем не-None, чтобы наверху логика не падала
            return _fallback_result(message_id=md5_hash)


async def send_for_analysis(
    *,
    message_id: str,
    text: str,
    chat_id: Optional[str] = None,
    sender: Optional[str] = None,
    attachments: Optional[list] = None,
    locale: str = "uk",
    timeout_s: float = 15.0,
    retries: int = 2,
) -> DispatchResult:
    payload = {
        "message_id": message_id,
        "chat_id": chat_id,
        "sender": sender,
        "text": text,
        "attachments": attachments or [],
        "received_at": datetime.now(timezone.utc).isoformat(),
        "locale": locale,
    }

    headers = {
        "X-API-Key": DISPATCH_API_KEY,
        "Content-Type": "application/json",
        "X-Client": "viber-worker",
    }

    log_and_print(f"[dispatch] POST {DISPATCH_URL}")
    log_and_print(
        f"[dispatch] headers: {{'X-API-Key': '***', 'Content-Type': 'application/json', 'X-Client': 'viber-worker'}}"
    )
    log_and_print(f"[dispatch] payload: {payload}")

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s, follow_redirects=True
            ) as client:
                resp = await client.post(DISPATCH_URL, json=payload, headers=headers)
                log_and_print(f"[dispatch] status={resp.status_code}")
                # логируем тело всегда — помогает при несовпадении контрактов
                body_preview = (
                    resp.text
                    if len(resp.text) < 2000
                    else (resp.text[:2000] + "...<truncated>")
                )
                log_and_print(f"[dispatch] body: {body_preview}")

                if resp.status_code == 401:
                    raise DispatchError("Unauthorized: check X-API-Key")

                resp.raise_for_status()

                data = resp.json()
                try:
                    result = DispatchResult(**data)
                except ValidationError as ve:
                    # Логируем и пробуем мягко привести actions, если это список dict'ов
                    log_and_print(f"[dispatch] ValidationError: {ve}", "error")
                    # Попытка «ручной» сборки результата
                    actions_raw = data.get("actions") or []
                    actions: List[Action] = []
                    for a in actions_raw:
                        if isinstance(a, dict):
                            actions.append(
                                Action(
                                    type=a.get("type", "ignore"),
                                    payload=a.get("payload"),
                                )
                            )
                    result = DispatchResult(
                        message_id=data.get("message_id", message_id),
                        extracted=data.get("extracted") or {},
                        actions=actions,
                        decision=data.get("decision"),
                    )
                return result

        except Exception as e:
            last_exc = e
            log_and_print(
                f"[dispatch] attempt {attempt+1}/{retries+1} failed: {e}", "error"
            )
            if attempt < retries:
                await asyncio.sleep(0.7 * (attempt + 1))  # легкий backoff
            else:
                # На последней попытке возвращаем fallback, а не выбрасываем исключение
                log_and_print("[dispatch] returning fallback result", "error")
                return _fallback_result(message_id=message_id)

    # теоретически недостижимо
    raise DispatchError(f"Dispatch failed: {last_exc}")


def click_copy_text_from_text(window, s, x, y):
    global count_y_mess_empty
    if not gd.click_text(
        ["Скопировать сообщение", "Копировать текст"],
        count_attempt_find=2,
        pause_attempt=2,
        lang="rus",
        scope=(
            int(x - s.width_menu),
            y - int(s.height_menu),
            x + int(s.width_menu * 1.2),
            y + int(s.height_menu * 1.4),
        ),
        is_debug=0,
        threshold=0.8,
        occurrence=1,
    ):
        log_and_print("[send_messages_from_y_mess] Not find Скопировать сообщение")
        count_y_mess_empty = count_y_mess_empty + 1
        window.set_focus()
        pag.keyDown("esq")
        gd.pause(0.4)
        pag.keyUp("esq")
        gd.pause(0.4)
        log_and_print("[send_messages_from_y_mess] press esq")
        gd.right_click(
            s.search_board_mess_x_start + s.x_offset_out_mess,
            s.search_board_mess_y_start + 10,
        )
        log_and_print("[send_messages_from_y_mess] right click empty place")

    log_and_print("[send_messages_from_y_mess] Повідомлення скопіювано в буфер обміну")


def click_copy_text_from_image(window, s, x, y, is_debug = False):
    global count_y_mess_empty
    if not gd.click_image(
        "copy.png",
        scope=(
            int(x - s.width_menu),
            y - int(s.height_menu),
            x + int(s.width_menu),
            y + int(s.height_menu),
        ),
        confidence=0.88,
        count_click=1,
        multiscale=True,
        is_debug=is_debug,
    ):
        log_and_print("[send_messages_from_y_mess] Not find Скопировать сообщение")
        count_y_mess_empty = count_y_mess_empty + 1
        window.set_focus()
        pag.keyDown("esq")
        gd.pause(0.4)
        pag.keyUp("esq")
        gd.pause(0.4)
        log_and_print("[send_messages_from_y_mess] press esq")
        gd.right_click(
            s.search_board_mess_x_start + s.x_offset_out_mess,
            s.search_board_mess_y_start + 10,
        )
        log_and_print("[send_messages_from_y_mess] right click empty place")
        return ""

    log_and_print("[send_messagfrom_y_mess] Повідомлення скопіювано в буфер обміну")
    return pyperclip.paste()


count_old_mess = 0


async def send_messages_from_y_mess(window, s):
    global count_y_mess_empty
    window.set_focus()
    sending = 0
    was_new_mess = False
    global count_old_mess

    for x, y in s.y_mess:
        if y:
            log_and_print(f"[send_messages_from_y_mess] Меседж y = {y}")
            window.set_focus()

            x = x + s.search_board_mess_x_start + 180
            y = y + s.search_board_mess_y_start

            xRight = x - 140
            yRight = y
            gd.right_click(xRight, yRight)
            log_and_print(
                f"[send_messages_from_y_mess] right_click xRight = {xRight}, yRight = {yRight}"
            )

            text = click_copy_text_from_image(window, s, x, y, is_debug=False)

            if not text:
                log_and_print(
                    "[send_messages_from_y_mess] Не вдалося скопіювати меседж, буфер обміну пустий"
                )
            else:
                if not text_includes_fast(text, s.old_text, 0.7):
                    was_new_mess = True
                    count_old_mess = 0
                    log_and_print(
                        "[send_messages_from_y_mess] Відправка та збереження нового сповіщення для аналізу:"
                    )
                    resp = await process_one_message_dispatcher(
                        text, None, s
                    )
                    log_and_print(
                        f"[send_messages_from_y_mess] response from server: {resp.model_dump() if isinstance(resp, DispatchResult) else resp}"
                    )

                    # Извлекаем тип первой команды (если есть)
                    action_type = None
                    viber_names = []
                    
                    if isinstance(resp, DispatchResult) and resp.actions:
                        first_action = resp.actions[0]
                        action_type = _safe_action_type(first_action)
                        
                        # 2) достаём имена перевозчиков, если backend вернул matched_contacts
                        if hasattr(resp, "matched_contacts") and getattr(resp, "matched_contacts", None):
                            # resp.matched_contacts — это список объектов или словарей
                            for mc in resp.matched_contacts or []:
                                # если это словарь
                                if isinstance(mc, dict):
                                    name = mc.get("viber_contact_name")
                                else:
                                    # Pydantic-модель MatchedContact
                                    name = getattr(mc, "viber_contact_name", None)

                                if name and name not in viber_names:
                                    viber_names.append(name)

                    result = True
                    if action_type != "ignore":
                        log_and_print("++++++++++++++++++++++++++++++++++++++++++++++")

                        result = sendViberMessDispatherToСarrier(
                            viber_names, window, xRight, yRight, s, text
                        )



                        if not result:
                            pag.keyDown("esq")
                            gd.pause(0.2)
                            pag.keyUp("esq")
                            gd.pause(0.2)

                            gd.right_click(
                                s.search_board_mess_x_start + s.x_offset_out_mess,
                                s.search_board_mess_y_start + 10,
                            )

                            result = sendViberMessDispatherToСarrier(
                            "Віталій", window, xRight, yRight, s, text
                        )

                    else:
                        log_and_print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

                    if result:
                        save_current_text(text)
                        s.old_text = load_previous_text()
                else:
                    count_old_mess += 1
                    if count_old_mess >= 3:
                        was_new_mess = False
                        count_old_mess = 0
                        return was_new_mess
                    sending += 1
                    log_and_print(
                        "[send_messages_from_y_mess] Сповіщення вже було відправлено"
                    )
                    if sending >= 2:
                        # break
                        pass

    return was_new_mess


def clickLastMess(window, s):
    if not gd.click_image(
        f"{s.name_viber_channel}\\last_mess.png",
        scope=(720, 910, 790, 980),
        confidence=0.7,
        count_click=1,
        multiscale=True,
        is_debug=False,
    ):
        log_and_print("Not find name carrier UkrBusTravel")
        return False
    log_and_print("Click down to last messages")
    #scroll_with_mouse(window, count_scroll=2, direction="up")
    return True


def klickViberChannel(window, clickMessBool, s):

    if not gd.click_image(
        s.name_viber_channel + ".png",
        scope=(0, 200, 120, 700),
        confidence=0.88,
        count_click=1,
        multiscale=True,
        is_debug=False,
    ):
        log_and_print(f"Not find name chat {s.name_viber_channel}")
        return False

    log_and_print("Click name chat Perevezniki")
    if clickMessBool:
        clickLastMess(window, s)
    return True


def findMessage(window, x, y, s, text):
    log_and_print(f"[findMessage] text = {text}")
    gd.right_click(x, y)
    gd.pause(0.5)
    current_text = click_copy_text_from_image(window, s, x+60, y, is_debug=False)

    log_and_print(f"[findMessage] current_text = {current_text}")

    if text_includes_fast(text, current_text, 0.7):
        log_and_print("[findMessage] succ message find")
        return x, y
    else:
        log_and_print("[findMessage] succ message not find")
        count_attempt_find = 0
        count_attempt_find_max = 3
        while True:
            window.set_focus()
            fill_y_mess(window, s)
            if len(s.y_mess) > 0:

                for x, y in s.y_mess:
                    if y:
                        log_and_print(f"[findMessage] Меседж y = {y}")
                        window.set_focus()

                        x = x + s.search_board_mess_x_start + 180
                        y = y + s.search_board_mess_y_start

                        xRight = x - 160
                        yRight = y
                        gd.right_click(xRight, yRight)
                        log_and_print(
                            f"[findMessage] right_click xRight = {xRight}, yRight = {yRight}"
                        )

                        current_text = click_copy_text_from_image(window, s, x, y)
                        if current_text == "":
                            clickLastMess(window, s)
                            continue

                        if text_includes_fast(text, current_text, 0.7):
                            log_and_print("succ message find")
                            return x, y
                        else:
                            log_and_print("[findMessage] this not right text")

                count_attempt_find += 1
                if count_attempt_find > count_attempt_find_max:
                    return False

                count_scroll_up = read_setting("count_scroll_up")
                scroll_with_mouse(window, count_scroll=count_scroll_up, direction="up")
            else:
                klickViberChannel(window, True, s)
                pag.keyDown("esq")
                gd.pause(0.2)
                pag.keyUp("esq")
                gd.pause(0.2)

                gd.right_click(
                    s.search_board_mess_x_start + s.x_offset_out_mess,
                    s.search_board_mess_y_start + 10,
                )

def sendViberMessDispatherToСarrier(viber_names, window, x, y, s, text):
    is_debug = False

    resultFind = findMessage(window, x, y, s, text)
    if resultFind:
        x, y = resultFind
    else:
        return False

    xRight = x - 60
    yRight = y + 20

    gd.right_click(xRight, yRight)

    if not gd.click_text(
        ["Переслать"],
        count_attempt_find=2,
        pause_attempt=4,
        lang="rus",
        scope=(x - 200, y - 50, x + 200, y + 400),
        threshold=0.86,
        is_debug=False,
    ):
        log_and_print("Not find menu item Переслать")
        return False

    log_and_print("Click Переслать")

    for viber_name in viber_names:
        log_and_print(f"viber_name = {viber_name}")
        
        first_name = viber_name.split()[0]
   
        pos = gd.find_image(
            "find.png", scope=(320, 320, 380, 380), multiscale=False, is_debug=is_debug
        )

        if not pos:
            log_and_print("Not find field find in resend")
            return False
    
        gd.click(pos[0] + 100, pos[1])
        log_and_print("Click field find")

        pyperclip.copy(viber_name)
        gd.pause(0.5)
        pag.keyDown("ctrl")
        gd.pause(0.3)
        pag.press("v")
        gd.pause(0.3)
        pag.keyUp("ctrl")
        gd.pause(1)
        log_and_print("Click ctrl v")
        gd.pause(3)

        if not gd.click_text(
            [first_name],
            count_attempt_find=2,
            pause_attempt=4,
            lang="ukr",
            scope=(pos[0], pos[0] + 40, pos[0] + 300, pos[0] + 200),
            is_debug=False,
            threshold=0.5,
            occurrence=1,
        ):
            log_and_print(f"Not find NameViberCarrier  {viber_name}")
            return "repeat"

        log_and_print(f"click name chat {viber_name}")
        gd.pause(1)

    if not gd.click_image(
        "resend.png",
        scope=(460, 730, 640, 810),
        confidence=0.5,
        count_click=1,
        is_debug=False,
    ):
        log_and_print("Not find button resend")
        return "repeat"

    log_and_print("click button resend success")

    save_current_text(text)
    s.old_text = load_previous_text()

    klickViberChannel(window, True, s)
    return True


def fill_y_mess(window, s):
    s.y_mess = []
    window.set_focus()
    log_and_print("Старт fill_y_mess")

    height = s.search_board_mess_y_end - s.search_board_mess_y_start
    width = s.search_board_mess_x_end - s.search_board_mess_x_start
    x, y = s.search_board_mess_x_start + 120, s.search_board_mess_y_start

    log_and_print(f"x = {x} y = {y} height = {height}, width = {width}")

    coordinates = gd.capture_and_find_image_boundary_coordinates(
        (x, y, 320, height),
        [
            f"images\\{s.name_viber_channel}\\heart.png",
            f"images\\{s.name_viber_channel}\\heart2.png",
            f"images\\{s.name_viber_channel}\\heart3.png",
            f"images\\{s.name_viber_channel}\\heart4.png",
            f"images\\{s.name_viber_channel}\\heart5.png",
            f"images\\{s.name_viber_channel}\\heart6.png",
            f"images\\{s.name_viber_channel}\\heart5.png",
        ],
        visualize=False,
        threshold=0.88,
    )
    window.set_focus()

    s.y_mess = [(coord[0], coord[1]) for coord in coordinates]
    log_and_print(f"s.y_mess = {s.y_mess}")


async def processViberMess(
    window, s, count_scroll_up, count_scroll_down, pause_cycle_read
):
    global count_y_mess_empty
    hwnd = window.handle

    window.set_focus()

    gd.right_click(
        s.search_board_mess_x_start + s.x_offset_out_mess,
        s.search_board_mess_y_start + 10,
    )

    count_repeat = int(read_setting("count_repeat"))
    for i in range(count_repeat):
        ctypes.windll.user32.LockWindowUpdate(hwnd)
        while True:

            fill_y_mess(window, s)

            if len(s.y_mess) > 0:
                was_send = await send_messages_from_y_mess(window, s)
                if was_send != "repeat":
                    if was_send:
                        scroll_with_mouse(
                            window, count_scroll=count_scroll_up, direction="up"
                        )
                    else:
                        clickLastMess(window, s)
                        
            else:
                break

            window.set_focus()
            # gd.right_click(s.search_board_mess_x_start + s.x_offset_out_mess, s.search_board_mess_y_start + 10)

        ctypes.windll.user32.LockWindowUpdate(0)

        log_and_print(f"count_y_mess_empty = {count_y_mess_empty}")

    window.set_focus()

    pag.keyDown("esq")
    gd.pause(0.2)
    pag.keyUp("esq")
    gd.pause(0.2)

    gd.right_click(
        s.search_board_mess_x_start + s.x_offset_out_mess,
        s.search_board_mess_y_start + 10,
    )

    if not klickViberChannel(window, True, s):
        log_and_print(f"Not find chat {s.name_viber_channel}")
        return None

    scroll_with_mouse(window, count_scroll=count_scroll_down, direction="down")

    log_and_print(f"pause = {read_setting('pause_read_messages_second')}")
    gd.pause(pause_cycle_read)
