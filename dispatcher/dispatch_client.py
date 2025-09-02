# viber_worker/dispatch_client.py
import os
from typing import Optional, Dict, Any
import asyncio
import httpx
from pydantic import BaseModel
from datetime import datetime, timezone
from find_message import load_previous_text, save_current_text
from log import log_and_print
from core import gui_driver as gd
import pyperclip
import pyautogui as pag
from utils import read_setting
import hashlib

DISPATCH_URL = os.getenv("DISPATCH_URL", "http://192.168.1.223:8888/api/v1/dispatch/analyze")
DISPATCH_API_KEY = os.getenv("DISPATCH_API_KEY", "3e7e07d4f2a64f99a95cf8b18a1381f635ea2cde93cce94e4dcbfdd4c3af5d87")
# Глобальный флаг для предотвращения двойной реакции
processed_messages = set()
# Семафор для последовательной обработки сообщений
processing_semaphore = asyncio.Semaphore(1)
count_y_mess_empty = 0


class DispatchError(Exception):
    pass

class DispatchResult(BaseModel):
    message_id: str
    extracted: Dict[str, Any]
    actions: list
    
async def process_one_message_dispatcher(message_text, name_viber, file_path):
    log_and_print(f"!!! process_one_message_dispatcher !!!")
    log_and_print(f"name_viber: {name_viber}", 'info')

    if message_text:
        # Добавляем ID сообщения в список обработанных
        processed_messages.add(message_text)
    elif file_path:
        processed_messages.add(file_path)


    # Обрабатываем сообщение последовательно с использованием семафора
    async with processing_semaphore:
        try:
            log_and_print(f'Обработка сообщения: {message_text}', 'info')
            md5_hash = hashlib.md5(message_text.encode()).hexdigest()

            return await send_for_analysis(
                message_id = md5_hash,
                text = message_text,
                chat_id = "UkrBusTravel",
                sender = None,
                attachments = None,
                locale = "uk",
                timeout_s = 8.0,
                retries = 2
            )
            
        except Exception as e:
            log_and_print(f"Oшибка при обработке одного сообщения: {e}", 'error')
            await asyncio.sleep(10)  # Задержка


async def send_for_analysis(
    *,
    message_id: str,
    text: str,
    chat_id: Optional[str] = None,
    sender: Optional[str] = None,
    attachments: Optional[list] = None,
    locale: str = "uk",
    timeout_s: float = 8.0,
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

    log_and_print(f"Send message payload = {payload}")
    
    headers = {"X-API-Key": DISPATCH_API_KEY}

    last_exc = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(DISPATCH_URL, json=payload, headers=headers)
                if resp.status_code == 401:
                    raise DispatchError("Unauthorized: check X-API-Key")
                
                log_and_print(f"Recive response from chat gpt resp = {resp}")
                 
                resp.raise_for_status()
                data = resp.json()
                return DispatchResult(**data)
        except Exception as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # backoff
            else:
                raise DispatchError(f"Dispatch request failed after {retries+1} tries: {e}") from e
    # theoretically unreachable
    raise DispatchError(f"Dispatch failed: {last_exc}")


async def send_messages_from_y_mess(window, s):
    global count_y_mess_empty
    window.set_focus()
    x, y_start = s.search_board_mess_x_start, s.search_board_mess_y_start
    for y in s.y_mess:
        if y:
            log_and_print(f"[send_messages_from_y_mess] Меседж y = {y}")
            y = y_start + y - s.height_item_menu
            window.set_focus()

            xRight = x + 10
            yRight = y
            gd.right_click(xRight, yRight)

            x = x + 50
            
            if not gd.click_text(["Скопировать сообщение",], 
                count_attempt_find=2,
                pause_attempt = 2,
                lang="rus", 
                scope=(x - 100, 
                    y -  int(s.height_menu*1.5), 
                    x + int(s.width_menu*2.4), 
                    y + int(s.height_menu*2.4)), 
                is_debug=False,
                threshold = 0.5,
                occurrence = 1
                ):
                log_and_print("Not find Скопировать сообщение")
                count_y_mess_empty = count_y_mess_empty + 1
                gd.right_click(s.search_board_mess_x_start + s.x_offset_out_mess,
                    s.search_board_mess_y_end - 100)
            
                    
            log_and_print("[send_text] Повідомлення скопиювовано в буфер обміну")
            
            text = pyperclip.paste()

            if not text:
                log_and_print(f"[send_text] Не вдалося скопіювати меседж, буфєр обміну пустий")
            else:
                if text not in s.old_text:
                    log_and_print(f"[send_text] Збереження нового сповіщення для аналізу: {text}")
                    save_current_text(text)
                    s.old_text = load_previous_text()
                    
                    #resp =  await process_one_message_dispatcher(text, s.name_viber, None)
                    if True: #resp.actions:
                        sendViberMessDispatherToСarrier("Віталій", window, xRight, yRight)
                        #виходемо з циклу, щоб почати пошук меседжів з початку (помінялись коордінати )
                        return True
    
    return False #відсилкі не було       

def sendViberMessDispatherToСarrier(NameViberCarrier, window, x, y):
            
    is_debug = False
    gd.right_click(x, y)
    if not gd.click_text(["Переслать",], 
            count_attempt_find=2,
            pause_attempt = 4,
            lang="rus", 
            scope=(x - 100, y - 100, x+550, y+650),
            is_debug=is_debug):
                log_and_print("Not find menu item Переслать")
                return False
            
    pos = gd.find_image("find.png", 
            scope=(420, 200, 560, 300),
            multiscale=False,
            is_debug=is_debug)
    
    if not pos:
        log_and_print("Not find field find in resend")
        return False
    
    gd.click(pos[0] + 100, pos[1] + 10)
    
    pyperclip.copy(NameViberCarrier)
    gd.pause(1)
    pag.keyDown('ctrl')
    gd.pause(0.1)
    pag.press('v')
    gd.pause(0.1)
    pag.keyUp('ctrl')
    gd.pause(1)
    
    if not gd.click_text([NameViberCarrier,], 
            count_attempt_find=2,
            pause_attempt = 4,
            lang="rus", 
            scope=(pos[0], pos[0]-200, pos[0]+300, pos[0]+300), 
            is_debug=is_debug,
            threshold = 0.5,
            occurrence = 1
            ):
                log_and_print(f"Not find 2 NameViberCarrier  {NameViberCarrier}")
                return False
            
    gd.pause(1)
            
    if not gd.click_image("resend.png", 
                          scope=(680, 840, 980, 960), 
                          confidence=0.5,
                          count_click=1,
                          #plus_y=30,
                          is_debug=False):
            
        log_and_print(f"Not find name carrier {NameViberCarrier}")
        return False
    
    gd.pause(1)
    
    if not gd.click_image("ukrbus.png", 
                        scope=(0, 300, 120, 700), 
                        confidence=0.7,
                        count_click=1,
                        multiscale = True,
                        #plus_y=0,
                        is_debug=False):
        
        log_and_print("Not find name carrier UkrBusTravel")
        return False

    gd.pause(1)
            
    return True
    
            
    
            
    
