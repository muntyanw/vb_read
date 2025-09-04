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
from vb_utils import scroll_with_mouse, capture_and_find_image_boundary_coordinates
from recognize_text import text_includes
import time

DISPATCH_URL = os.getenv("DISPATCH_URL", "http://192.168.1.223:8888/api/v1/dispatch/analyze")
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


class DispatchResult(BaseModel):
    message_id: str
    extracted: Dict[str, Any] = {}
    actions: List[Action] = []
    # опционально: поддержка старого/нового формата
    decision: Optional[Decision] = None


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


async def process_one_message_dispatcher(message_text: Optional[str], name_viber: Optional[str], file_path: Optional[str]):
    log_and_print("!!! process_one_message_dispatcher !!!")
    log_and_print(f"name_viber: {name_viber}", "info")

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
                chat_id="UkrBusTravel",
                sender=name_viber,           # <— отправляем имя отправителя
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
    log_and_print(f"[dispatch] headers: {{'X-API-Key': '***', 'Content-Type': 'application/json', 'X-Client': 'viber-worker'}}")
    log_and_print(f"[dispatch] payload: {payload}")

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
                resp = await client.post(DISPATCH_URL, json=payload, headers=headers)
                log_and_print(f"[dispatch] status={resp.status_code}")
                # логируем тело всегда — помогает при несовпадении контрактов
                body_preview = resp.text if len(resp.text) < 2000 else (resp.text[:2000] + "...<truncated>")
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
                            actions.append(Action(type=a.get("type", "ignore"), payload=a.get("payload")))
                    result = DispatchResult(
                        message_id=data.get("message_id", message_id),
                        extracted=data.get("extracted") or {},
                        actions=actions,
                        decision=data.get("decision"),
                    )
                return result

        except Exception as e:
            last_exc = e
            log_and_print(f"[dispatch] attempt {attempt+1}/{retries+1} failed: {e}", "error")
            if attempt < retries:
                await asyncio.sleep(0.7 * (attempt + 1))  # легкий backoff
            else:
                # На последней попытке возвращаем fallback, а не выбрасываем исключение
                log_and_print("[dispatch] returning fallback result", "error")
                return _fallback_result(message_id=message_id)

    # теоретически недостижимо
    raise DispatchError(f"Dispatch failed: {last_exc}")


async def send_messages_from_y_mess(window, s):
    global count_y_mess_empty
    window.set_focus()
    sending = 0
    was_new_mess = False
    for x, y in s.y_mess:
        if y:
            log_and_print(f"[send_messages_from_y_mess] Меседж y = {y}")
            window.set_focus()

            x =  x + s.search_board_mess_x_start + 180
            y = y + s.search_board_mess_y_start

            xRight = x - 160
            yRight = y
            gd.right_click(xRight, yRight)
            log_and_print(f"[send_messages_from_y_mess] right_click xRight = {xRight}, yRight = {yRight}")

            if not gd.click_text(
                ["Скопировать сообщение", "Копировать текст"],
                count_attempt_find=2,
                pause_attempt=2,
                lang="rus",
                scope=(int(x - s.width_menu), y - int(s.height_menu/2), x + int(s.width_menu*1.4), y + int(s.height_menu*2 )),
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
                gd.right_click(s.search_board_mess_x_start + s.x_offset_out_mess, s.search_board_mess_y_start + 10)
                log_and_print("[send_messages_from_y_mess] right click empty place")
                was_new_mess = True
                
            log_and_print("[send_messages_from_y_mess] Повідомлення скопіювано в буфер обміну")

            text = pyperclip.paste()

            if not text:
                log_and_print("[send_messages_from_y_mess] Не вдалося скопіювати меседж, буфер обміну пустий")
            else:
                if not text_includes(text, s.old_text, 0.7):
                    was_new_mess = True
                    log_and_print("[send_messages_from_y_mess] Відправка та збереження нового сповіщення для аналізу:")
                    save_current_text(text)
                    s.old_text = load_previous_text()

                    resp = await process_one_message_dispatcher(text, s.name_viber, None)
                    log_and_print(f"[send_messages_from_y_mess] response from server: {resp.model_dump() if isinstance(resp, DispatchResult) else resp}")

                    # Извлекаем тип первой команды (если есть)
                    action_type = None
                    if isinstance(resp, DispatchResult) and resp.actions:
                        first_action = resp.actions[0]
                        action_type = _safe_action_type(first_action)

                    if action_type != "ignore":
                        log_and_print("++++++++++++++++++++++++++++++++++++++++++++++")
                        sendViberMessDispatherToСarrier("Віталій", window, xRight, yRight)
                        # The above code is a Python function that returns the boolean value True.
                        return was_new_mess
                    else:
                        log_and_print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
                else:
                    was_new_mess = False
                    sending +=1
                    log_and_print("[send_messages_from_y_mess] Сповіщення вже було відправлено")
                    if sending >= 2:
                        break

    return was_new_mess 


def clickLastMess():
    if not gd.click_image("last_mess.png", scope=(720, 910, 790, 980), confidence=0.7, count_click=1, multiscale=True, is_debug=False):
        log_and_print("Not find name carrier UkrBusTravel")
        return False
    log_and_print("Click down to last messages")
    return True


def klickUkrBus():
    if not gd.click_image("ukrbus.png", scope=(0, 200, 120, 700), confidence=0.88, count_click=1, multiscale=True, is_debug=False):
        log_and_print("Not find name chat UkrBusTravel")
        return False

    log_and_print("Click name chat UkrBusTravel")
    clickLastMess()
    return True


def sendViberMessDispatherToСarrier(NameViberCarrier, window, x, y):
    is_debug = False
    gd.right_click(x, y - 20)
    if not gd.click_text(
        ["Переслать"],
        count_attempt_find=2,
        pause_attempt=4,
        lang="rus",
        scope=(x, y - 100, x + 160, y + 400),
        threshold=0.86,
        is_debug=is_debug,
    ):
        log_and_print("Not find menu item Переслать")
        return False

    log_and_print("Click Переслать")

    pos = gd.find_image("find.png", 
                        scope=(320, 320, 380, 380), 
                        multiscale=False, 
                        is_debug=is_debug)

    if not pos:
        log_and_print("Not find field find in resend")
        return False

    countAttempt = 0
    while True:
        log_and_print(f"Attempt find recipient {countAttempt}")
        countAttempt += 1
        gd.click(pos[0] + 100, pos[1])
        log_and_print("Click field find")
        
        pyperclip.copy(NameViberCarrier)
        gd.pause(0.5)
        pag.keyDown("ctrl")
        gd.pause(0.3)
        pag.press("v")
        gd.pause(0.3)
        pag.keyUp("ctrl")
        gd.pause(1)
        log_and_print("Click ctrl v")

        if gd.find_text_any([NameViberCarrier,], 
                        lang="ukr", 
                        count = 2,
                        scope=(320, 320, 580, 380), 
                        threshold=0.5,
                        is_debug=0):
            log_and_print("Name recipient message paste successful")
            break
        else:
            log_and_print("Name recipient message not find")
            
            pag.keyDown("ctrl")
            gd.pause(0.5)
            pag.press("a")
            gd.pause(0.5)
            pag.keyUp("ctrl")
            gd.pause(1)
            pag.press("delete")
            log_and_print("delete old text")


        if countAttempt > 6:
            log_and_print("Error paste name recipient message ")
            return False

    if not gd.click_text(
        [NameViberCarrier],
        count_attempt_find=2,
        pause_attempt=4,
        lang="ukr",
        scope=(pos[0], pos[0] - 200, pos[0] + 300, pos[0] + 200),
        is_debug=is_debug,
        threshold=0.5,
        occurrence=2,
    ):
        log_and_print(f"Not find 2 NameViberCarrier  {NameViberCarrier}")
        return False

    log_and_print(f"click name chat {NameViberCarrier}")
    gd.pause(1)

    if not gd.click_image("resend.png", scope=(460, 730, 640, 810), confidence=0.5, count_click=1, is_debug=False):
        log_and_print(f"Not find name carrier {NameViberCarrier}")
        return False

    log_and_print("click button resend")
    return klickUkrBus()


def fill_y_mess(window, s):
    s.y_mess = []
    window.set_focus()
    log_and_print("Старт fill_y_mess")

    height = s.search_board_mess_y_end - s.search_board_mess_y_start
    width = s.search_board_mess_x_end - s.search_board_mess_x_start
    x, y = s.search_board_mess_x_start + 120, s.search_board_mess_y_start

    log_and_print(f"x = {x} y = {y} height = {height}, width = {width}")

    coordinates = capture_and_find_image_boundary_coordinates(
        (x, y, 320, height),
        ["images\\heart.png", "images\\heart2.png", "images\\heart3.png"],
        visualize=0,
        threshold=0.88,
    )
    window.set_focus()

    s.y_mess = [(coord[0], coord[1]) for coord in coordinates]
    log_and_print(f"s.y_mess = {s.y_mess}")


count_y_mess_empty = 0


async def processViberMess(window, s, count_scroll_up, count_scroll_down, pause_cycle_read):
    global count_y_mess_empty
    hwnd = window.handle

    window.set_focus()
    
    gd.right_click(s.search_board_mess_x_start + s.x_offset_out_mess, s.search_board_mess_y_start + 10)

    count_repeat = read_setting("count_repeat")
    for i in range(count_repeat):
        ctypes.windll.user32.LockWindowUpdate(hwnd)
        while True:
            
            fill_y_mess(window, s)

            if len(s.y_mess) > 0:
                was_send = await send_messages_from_y_mess(window, s)
                if was_send:
                    scroll_with_mouse(window, count_scroll=count_scroll_up, direction="up")
                else:
                    scroll_with_mouse(window, count_scroll=count_scroll_down, direction="down")
            else:
                break
                
            window.set_focus()
            gd.right_click(s.search_board_mess_x_start + s.x_offset_out_mess, s.search_board_mess_y_start + 10)

        ctypes.windll.user32.LockWindowUpdate(0)

        log_and_print(f"count_y_mess_empty = {count_y_mess_empty}")
        
    window.set_focus()
    
    pag.keyDown("esq")
    gd.pause(0.2)
    pag.keyUp("esq")
    gd.pause(0.2)
    
    gd.right_click(s.search_board_mess_x_start + s.x_offset_out_mess, s.search_board_mess_y_start + 10)
    
    if not klickUkrBus():
        log_and_print("Not find chat UkrBus")
        return None

    scroll_with_mouse(window, count_scroll=count_scroll_down, direction="down")

    

    log_and_print(f"pause = {read_setting('pause_read_messages_second')}")
    gd.pause(pause_cycle_read)
