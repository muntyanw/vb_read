# viber_worker/dispatch_client.py
import os
from typing import Optional, Dict, Any, List, Union
import asyncio
import httpx
from pydantic import BaseModel, Field, field_validator, ValidationError, ConfigDict
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
import random
import win32gui
import win32con
from pywinauto import keyboard

pag.FAILSAFE = False

ip_numbber = 0

def _get_ips() -> list[str]:
    ips = read_setting("IPS") or []
    if not isinstance(ips, list):
        return []
    return [str(ip).strip() for ip in ips if str(ip).strip()]


def get_dispatch_url():
    ips = _get_ips()
    if not ips:
        return "http://127.0.0.1:8888/api/v1/dispatch/analyze"

    global ip_numbber
    ip_numbber = ip_numbber % len(ips)
    return f"http://{ips[ip_numbber]}:8888/api/v1/dispatch/analyze"


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
    # Игнорируем неожиданные поля от бэкенда
    model_config = ConfigDict(extra='ignore')

    message_id: str
    # Превращаем null -> {}, и задаём безопасный дефолт через default_factory
    extracted: Dict[str, Any] = Field(default_factory=dict)
    # Заодно приводим null -> [] для списков
    actions: List[Action] = Field(default_factory=list)
    decision: Optional[Decision] = None
    matched_contacts: List[MatchedContact] = Field(default_factory=list)

    @field_validator("extracted", mode="before")
    @classmethod
    def _coerce_extracted(cls, v):
        return v or {}

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, v):
        return v or []

    @field_validator("matched_contacts", mode="before")
    @classmethod
    def _coerce_matched_contacts(cls, v):
        return v or []

def _dispatch_base_url() -> str:
    # из "http://host/api/v1/dispatch/analyze" → "http://host/api/v1/dispatch"
    base = get_dispatch_url().rstrip("/")
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
    name_viber_channel: str,
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
                chat_id=name_viber_channel,
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
    
    global ip_numbber
    
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

    log_and_print(f"[dispatch] POST {get_dispatch_url()}")
    log_and_print(
        "[dispatch] headers: {{'X-API-Key': '***', 'Content-Type': 'application/json', 'X-Client': 'viber-worker'}}"
    )
    log_and_print(f"[dispatch] payload: {payload}")

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s, follow_redirects=True
            ) as client:
                log_and_print(f"[dispatch] post to {get_dispatch_url()}", "debug")
                resp = await client.post(get_dispatch_url(), json=payload, headers=headers)
                log_and_print(f"[dispatch] status={resp.status_code}", "debug")
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
            ips = _get_ips()
            current_ip = ips[ip_numbber % len(ips)] if ips else "no-ip-configured"
            log_and_print(
                f"[dispatch] attempt {attempt+1}/{retries+1} failed from {current_ip}: {e}", "error"
            )
            if ips:
                ip_numbber = (ip_numbber + 1) % len(ips)
                log_and_print(f"[dispatch] change ip to {ips[ip_numbber]}", "INFO")
            else:
                log_and_print("[dispatch] IPS is empty in settings.json", "ERROR")
            
            if attempt < retries:
                await asyncio.sleep(0.7 * (attempt + 1))  # легкий backoff
            else:
                # На последней попытке возвращаем fallback, а не выбрасываем исключение
                log_and_print("[dispatch] returning fallback result", "error")
                return _fallback_result(message_id=message_id)

    # теоретически недостижимо
    raise DispatchError(f"Dispatch failed: {last_exc}")
 
def is_foto_message(scope):

    pos = gd.find_text_any(queries=["Копировать фото",],
                            lang="rus", 
                            count=2, 
                            pause_attempt_sec =1, 
                            scope=scope, 
                            threshold = 0.8,
                            is_debug=False, 
                            occurrence = 1)
    if pos:
        return True
    
    return False

def is_link(scope):

    pos = gd.find_text_any(queries=["Копировать ссылку",],
                            lang="rus", 
                            count=2, 
                            pause_attempt_sec =1, 
                            scope=scope, 
                            threshold = 0.8,
                            is_debug=False, 
                            occurrence = 1)
    if pos:
        return True
    
    return False

def is_center_ok():
    
    if not gd.click_image(
        "center_ok.png",
        scope=(350, 450, 800, 800),
        confidence=0.88,
        count_click=2,
        multiscale=True,
        is_debug=False,
        ):
        log_and_print("[is_center_ok] Not find center OK")
        return False
    
    log_and_print("[is_center_ok] Find center OK")
    
    return True

def is_center_continue():
    
    if not gd.click_image(
        "continue.png",
        scope=(300, 550, 600, 700),
        confidence=0.88,
        count_click=2,
        multiscale=True,
        is_debug=False,
        ):
        log_and_print("[is_center_continue] Not find center Continue")
        return False
    
    log_and_print("[is_center_continue] Find center Continue")
    return True

def press_esq(window):
    window.set_focus()
    
    # Escape closes context menus; pyautogui uses "esc" as key name.
    pag.keyDown("esc")
    gd.pause(0.4)
    pag.keyUp("esc")
    gd.pause(0.4)
    log_and_print("[press_esq] press esq", "INFO")
    # gd.right_click(
    #     s.search_board_mess_x_start + s.x_offset_out_mess,
    #     s.search_board_mess_y_start + 10,
    # )

def click_copy_text(tp, window, s, x, y, is_debug = False):
    #global count_y_mess_empty
    
    scope=(
            int(x - s.width_menu),
            y - int(s.height_menu),
            x + int(s.width_menu),
            y + int(s.height_menu),
    )
    
    gd.pause(1)
    pos = False
    if tp == "image":
        pos = not gd.click_image(
            "copy.png",
            scope=scope,
            confidence=0.88,
            count_click=1,
            multiscale=True,
            is_debug=is_debug,
        )
    else:
        pos = gd.click_text(
            ["Копировать текст", "Скопировать сообщение", ],
            count_attempt_find=2,
            pause_attempt=2,
            lang="rus",
            scope=scope,
            is_debug=is_debug,
            threshold=0.8,
            occurrence=1,
        )
    
    log_and_print(f"pos = {pos}", "INFO")
    if not pos:
        
        if tp == "image":
        
            pos = gd.click_text(
                ["Копировать текст", "Скопировать сообщение", ],
                count_attempt_find=2,
                pause_attempt=2,
                lang="rus",
                scope=scope,
                is_debug=is_debug,
                threshold=0.8,
                occurrence=1,
            )
        else:
            pos = gd.click_image(
                "copy.png",
                scope=scope,
                confidence=0.88,
                count_click=1,
                multiscale=True,
                is_debug=is_debug,
            )
            
    if not pos:
        
        log_and_print("[send_messages_from_y_mess] Not find Скопировать сообщение", "INFO")
        
        press_esq(window)    
        #if is_foto_message(scope) or is_link(scope) or is_center_continue():
    
        #count_y_mess_empty = count_y_mess_empty + 1
        
        #log_and_print("[send_messages_from_y_mess] right click empty place", "INFO")
        return "is_foto"
        
        #else:
        #    press_esq(window)
        #    return None

    log_and_print("[send_messages_from_y_mess] Повідомлення скопіювано в буфер обміну", "INFO")
    return pyperclip.paste()

count_old_mess = 0

async def send_messages_from_y_mess(window, viber_channel, s):
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
            yRight = y - 10
            gd.right_click(xRight, yRight)
            log_and_print(
                f"[send_messages_from_y_mess] right_click xRight = {xRight}, yRight = {yRight}"
            )

            text = click_copy_text("text", window, s, x, y, is_debug=False)
            

            if len(text) == 1:
                continue
    
            if text == "is_foto":
                log_and_print("[send_messages_from_y_mess] Фото повідомлення", "INFO")
                continue
            
            if text is None:
                log_and_print(
                    "[send_messages_from_y_mess] Не вдалося скопіювати меседж, буфер обміну пустий", "INFO"
                )
                
                if is_center_ok():
                    continue
                else:
                    return "repeat"

                
            if not text_includes_fast(text, s.old_text, 0.7):
                was_new_mess = True
                count_old_mess = 0
                log_and_print(
                    "[send_messages_from_y_mess] Відправка та збереження нового сповіщення для аналізу", "INFO"
                )
                resp = await process_one_message_dispatcher(
                    text, None,
                    viber_channel["name_viber_channel"],
                    s
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
                    log_and_print("++++++++++++++++++++++++++++++++++++++++++++++", "INFO")

                    result = sendViberMessDispatherToСarrier(
                        viber_names, window, xRight, yRight, viber_channel, text, s
                    )



                    if not result:
                        press_esq(window)

                        gd.right_click(
                            s.search_board_mess_x_start + s.x_offset_out_mess,
                            s.search_board_mess_y_start + 10,
                        )

                        result = sendViberMessDispatherToСarrier(
                        viber_names, window, xRight, yRight, viber_channel, text, s
                    )

                else:
                    log_and_print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "INFO")

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
                    "[send_messages_from_y_mess] ------------------------------------- Сповіщення вже було відправлено", "INFO"
                )
                if sending >= 2:
                    # break
                    pass

    return was_new_mess

def clickLastMess(window, name_viber_channel):
    window.set_focus()
    if not gd.click_image(
        f"{name_viber_channel}\\last_mess.png",
        scope=(880, 910, 1100, 990),
        confidence=0.7,
        count_click=1,
        multiscale=True,
        is_debug=False,
    ):
        log_and_print("Not find icon LastMessage", "INFO")
        return False
        
    
    log_and_print("Click down to last messages", "INFO")
    #scroll_with_mouse(window, count_scroll=2, direction="up")
    return True

def moveToContactsAndScrollUp():
    log_and_print("[moveToContactsAndScrollUp] scroll up contacts")
    
    gd.human_move(140, 400)
    gd.scroll(3000)

def click_viber_channel_image(name_viber_channel ):
    
    return gd.click_image(
            name_viber_channel + ".png",
            scope=(0, 200, 120, 700),
            confidence=0.88,
            count_click=1,
            multiscale=True,
            is_debug=False,
    )
    
def click_viber_channel_text(viber_channel):
    
    return gd.click_text(
            [viber_channel["name_viber_contact"],],
            count_attempt_find=2,
            pause_attempt=4,
            lang=viber_channel["name_viber_contact_lang"],
            scope=(0, 200, 320, 700),
            threshold=0.5,
            plus_x = -16,
            is_debug=False,
            count_click=2
    )

def klickViberChannel(tp, window, clickLastMessBool, viber_channel):

    log_and_print(f"start click {viber_channel["name_viber_channel"]}", "DEBUG")
    press_esq(window)
    
    if tp == "image":

        pos = click_viber_channel_image(viber_channel["name_viber_channel"])
        
        if not pos:       
            log_and_print(f"Not find image chat {viber_channel["name_viber_channel"]}", "INFO")
                
            pos = click_viber_channel_text(viber_channel)
            
            if not pos:  
                log_and_print(f"Not find text name chat {viber_channel["name_viber_channel"]}", "INFO")
            
        
    else:
        pos = click_viber_channel_text(viber_channel)
        
        if not pos:       
            log_and_print(f"Not find text name chat {viber_channel["name_viber_channel"]}", "INFO")
                
            pos = click_viber_channel_image(viber_channel["name_viber_channel"])
            
            if not pos:  
                log_and_print(f"Not find image chat {viber_channel["name_viber_channel"]}", "INFO")
            

    log_and_print(f"Click name chat {viber_channel["name_viber_channel"]}")
    if clickLastMessBool:
        clickLastMess(window, viber_channel["name_viber_channel"])
        
    moveToContactsAndScrollUp()
    
    return True

def findMessage(window, x, y, viber_channel, text, s):
    log_and_print(f"[findMessage] text = {text}")
    gd.right_click(x, y)
    gd.pause(0.5)
    current_text = click_copy_text("text", window, s, x+60, y, is_debug=False)
    
    log_and_print(f"[findMessage] current_text = {current_text}")

    if current_text and text_includes_fast(text, current_text, 0.7):
        log_and_print("[findMessage] succ message find")
        return x, y
    else:
        log_and_print("[findMessage] succ message not find")
        count_attempt_find = 0
        count_attempt_find_max = 3
        while True:
            window.set_focus()
            fill_y_mess(window, viber_channel, s)
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

                        current_text = click_copy_text("text", window, s, x, y)
                        if current_text == "":
                            press_esq(window)
                            continue

                        if text_includes_fast(text, str(current_text), 0.7):
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
                klickViberChannel("image", window, True, viber_channel)
                pag.keyDown("esq")
                gd.pause(0.2)
                pag.keyUp("esq")
                gd.pause(0.2)

                gd.right_click(
                    s.search_board_mess_x_start + s.x_offset_out_mess,
                    s.search_board_mess_y_start + 10,
                )

def sendViberMessDispatherToСarrier(viber_names, window, x, y, viber_channel, text, s):
    is_debug = False

    resultFind = findMessage(window, x, y, viber_channel, text, s)
    if resultFind:
        x, y = resultFind
    else:
        return False

    xRight = x - 90
    yRight = y + 20

    gd.right_click(xRight, yRight)

    if not gd.click_text(
        ["Переслать"],
        count_attempt_find=2,
        pause_attempt=4,
        lang="rus",
        scope=(x - 200, y - 50, x + 200, y + 400),
        threshold=0.86,
        plus_x = -16,
        is_debug=False,
    ):
        log_and_print("Not find menu item Переслать")
        return False

    log_and_print("Click Переслать")

    for viber_name in viber_names:
        log_and_print(f"viber_name = {viber_name}")
        
        first_name = viber_name.split()[0]
   
        pos = gd.find_image(
            "find.png", scope=(320, 320, 380, 380), multiscale=True, is_debug=is_debug
        )

        if not pos:
            log_and_print("Not find field find in resend")
            return False
    
        gd.click(pos[0] + 100, pos[1] - 10)
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
        gd.pause(1)
        
        
        if not gd.click_image(
            "select.png",
            scope=(580, 400, 740, 520),
            confidence=0.88,
            count_click=1,
            multiscale=True,
            is_debug=False,
        ): 

        #if not gd.click_text(
        #    [first_name],
        #    count_attempt_find=2,
        #    pause_attempt=4,
        #    lang="ukr",
        #    scope=(pos[0], pos[0] + 40, pos[0] + 300, pos[0] + 200),
        #    is_debug=False,
        #    threshold=0.5,
        #    occurrence=1,
        #):
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

    klickViberChannel("image", window, True, viber_channel)
    return True

def fill_y_mess(window, viber_channel, s):
    s.y_mess = []
    window.set_focus()
    log_and_print("Старт fill_y_mess")

    height = s.search_board_mess_y_end - s.search_board_mess_y_start
    width = s.search_board_mess_x_end - s.search_board_mess_x_start
    x, y = s.search_board_mess_x_start + 120, s.search_board_mess_y_start

    log_and_print(f"x = {x} y = {y} height = {height}, width = {width}")

    coordinates = gd.capture_and_find_image_boundary_coordinates(
        (x, y, 800, height),
        [
            f"images\\{viber_channel["name_viber_channel"]}\\heart.png",
            f"images\\{viber_channel["name_viber_channel"]}\\heart2.png",
            f"images\\{viber_channel["name_viber_channel"]}\\heart3.png",
            f"images\\{viber_channel["name_viber_channel"]}\\heart4.png",
            f"images\\{viber_channel["name_viber_channel"]}\\heart5.png",
            f"images\\{viber_channel["name_viber_channel"]}\\heart6.png",
            f"images\\{viber_channel["name_viber_channel"]}\\heart5.png",
        ],
        visualize=False,
        threshold=0.88,
    )
    window.set_focus()

    s.y_mess = [(coord[0], coord[1]) for coord in coordinates]
    log_and_print(f"s.y_mess = {s.y_mess}")

def click_close_hitlite():
    log_and_print("Find hitlite", "INFO")
    if not gd.click_image(
        "close.png",
        scope=(750, 945, 800, 990),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        plus_x=10,
        plus_y=6,
        is_debug=False,
    ):
        log_and_print("Not find icon close", "INFO")
        return False

    log_and_print("Find success hitlite and click close", "INFO")
    return True

def click_folder():
    log_and_print("Find button folder", "INFO")
    if not gd.click_image(
        "folder.png",
        scope=(66, 154, 175, 207),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        is_debug=False,
    ):
        log_and_print("Not find button folder", "INFO")
        return False

    log_and_print("Find success button folder and click", "INFO")
    return True

def click_close_image():
    log_and_print("Find hitlite", "INFO")
    if not gd.click_image(
        "close_image.png",
        scope=(930, 40, 1080, 100),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        plus_x=10,
        plus_y=6,
        is_debug=False,
    ):
        log_and_print("Not find icon close image", "INFO")
        return False
    
    log_and_print("Find success image close and click close", "INFO")
    return True

def click_exist_mess(window, viber_channel):
    log_and_print("Find exist mrssages", "INFO")
    
    for number in range(5):
        if not gd.click_image(
            f"exist_mess{number}.png",
            scope=(245, 220, 300, 700),
            confidence=0.9,
            count_click=1,
            multiscale=True,
            plus_x=0,
            plus_y=0,
            is_debug=False,
        ):
            log_and_print(f"Not find exist mrssages{number}", "INFO")
            
        else:
            log_and_print("Success find and click images exist messages", "INFO")
            
            clickLastMess(window, viber_channel["name_viber_channel"])
            return True
        
    log_and_print("Not find images exist messages", "INFO")
    return False

def click_close_info():
    log_and_print("Find info", "INFO")
    if not gd.click_image(
        "info.png",
        scope=(720, 70, 800, 120),
        confidence=0.9,
        plus_y=0,
        plus_x=0,
        count_click=1,
        multiscale=True,
        is_debug=False,
    ):
        log_and_print("Not find icon close info, attempt 2", "INFO")
        
    log_and_print("Find success image close info and click", "INFO")
    return True

def click_open_info():
    log_and_print("Find info", "INFO")
    if not gd.click_image(
        "info.png",
        scope=(1050, 70, 1100, 120),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        is_debug=False,
    ):
        log_and_print("Not find icon open info, attempt 2", "INFO")
        if not gd.click_image(
        "info.png",
        scope=(910, 70, 950, 120),
        confidence=0.8,
        count_click=1,
        multiscale=True,
        is_debug=False,
        ):
            
            log_and_print("Not find icon open info atte,pt2", "INFO")
            return False
        
    log_and_print("Find success image open info and click", "INFO")
    return True

def click_cancel_window_save_as():
    log_and_print("Find window_save_as", "INFO")
    if not gd.click_image(
        "cancel.png",
        scope=(800, 500, 1060, 580),
        confidence=0.9,
        count_click=1,
        multiscale=True,
        is_debug=False,
    ):
        log_and_print("Not find window_save_as - attempt 2", "INFO")
        if not gd.click_image(
            "cancel2.png",
            scope=(800, 500, 1060, 580),
            confidence=0.9,
            count_click=1,
            multiscale=True,
            is_debug=False,
        ):
            log_and_print("Not find window_save_as - attempt 3", "INFO")
            if not gd.click_image(
                "cancel_close.png",
                scope=(800, 20, 970, 100),
                confidence=0.8,
                count_click=1,
                multiscale=True,
                is_debug=False,
                ):
                    
                    log_and_print("Not find window_save_as attempt2", "INFO")
                    return False
        
    log_and_print("Find success window_save_as and click", "INFO")
    return True

async def processViberMess(
    window, s, count_scroll_up, count_scroll_down, pause_cycle_read
):
    global count_y_mess_empty
    empty_send_count = 0
    numberViberChannel = 0
    viber_channel = s.viber_channels[numberViberChannel]

    window_top_focus(window)
    
    is_center_continue()
    click_folder()
    click_close_info()
    click_cancel_window_save_as()

    if not klickViberChannel("image",window, True, viber_channel):
                log_and_print(f"Not find chat {viber_channel["name_viber_channel"]}", "INFO")
                return None
            
    log_and_print(f"click chat {viber_channel["name_viber_channel"]}", "INFO")

    gd.right_click(
        s.search_board_mess_x_start + s.x_offset_out_mess,
        s.search_board_mess_y_start + 10,
    )

    count_repeat = int(read_setting("count_repeat"))
    break_flag = False

    for i in range(count_repeat):
        while True:
            log_and_print(f"empty_send_count: {empty_send_count}", "INFO")
            if empty_send_count > 4:
                window_top_focus(window)
                window_left(window)
                is_center_continue()
                click_folder()
                click_close_info()
                click_close_hitlite()
                click_close_image()
                scroll_with_mouse(
                                window, count_scroll=random.randint(1, 3), direction="up"
                            )

            if empty_send_count > 3:
                click_cancel_window_save_as()
                scroll_with_mouse(
                                window, count_scroll=random.randint(1, 3), direction="up"
                            )
                
            if empty_send_count > 2:
                
                if not click_exist_mess(window, viber_channel):
                    
                    if numberViberChannel + 1 >= len(s.viber_channels):
                        numberViberChannel = 0
                    else:
                        numberViberChannel = numberViberChannel + 1
                    
                    log_and_print(f"empty_send_count > 10 change channel to : {s.viber_channels[numberViberChannel]}", "INFO")
                    viber_channel = s.viber_channels[numberViberChannel]
                
                    if klickViberChannel("image", window, True, viber_channel):
                        log_and_print(f"Not find chat {viber_channel["name_viber_channel"]}", "INFO")
                        
                        empty_send_count = 0
                
                else:
                    empty_send_count = 0
                    
                

            fill_y_mess(window, viber_channel, s)

            if len(s.y_mess) > 0:
                was_send = await send_messages_from_y_mess(window, viber_channel, s)
                log_and_print(f"was_send: {was_send}", "INFO")
                if was_send != "repeat":
                    if was_send:
                        empty_send_count = 0
                        
                        scroll_with_mouse(
                            window, count_scroll=count_scroll_up, direction="up"
                        )
                    else:
                        empty_send_count += 1
                        press_esq(window)
                        clickLastMess(window, viber_channel["name_viber_channel"])
                        
            else:
                empty_send_count += 1
                window_top_focus(window)
                press_esq(window)
                is_center_ok()
                is_center_continue()
                break_flag = True
                break

            window_top_focus(window)
            
            #if not klickViberChannel("image", window, False, viber_channel):
            #    log_and_print(f"Not find chat {viber_channel["name_viber_channel"]}", "INFO")
            
            
        if break_flag:
            break

        ctypes.windll.user32.LockWindowUpdate(0)

        log_and_print(f"count_y_mess_empty = {count_y_mess_empty}")

    window_top_focus(window)

    press_esq(window)

    log_and_print(f"pause = {read_setting('pause_read_messages_second')}")
    
def window_top_focus(window):
    
    hwnd = window.handle

    # Устанавливаем флаг "всегда поверх остальных"
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,  # верх всех окон
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )
    window.set_focus()
    
def window_left(window):
    hwnd = window.handle
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    keyboard.send_keys('{LWIN down}{LEFT}{LWIN up}')
    
    

    
    
