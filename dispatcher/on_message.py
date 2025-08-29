# viber_worker/on_message.py
import asyncio
from dispatcher.dispatch_client import send_for_analysis, DispatchResult

async def handle_new_viber_message(v_msg):
    # v_msg: ваш объект с полями id, text, chat_id, sender, attachments...
    try:
        result: DispatchResult = await send_for_analysis(
            message_id=v_msg.id,
            text=v_msg.text,
            chat_id=v_msg.chat_id,
            sender=v_msg.sender_name,
            attachments=[{"kind": "image", "url": a.url} for a in getattr(v_msg, "images", [])],
            locale="uk",
        )
    except Exception as e:
        # логируйте и решайте, что делать при ошибке связи
        print(f"[dispatch] error: {e}")
        return

    # Выполнение команд
    for act in result.actions:
        t = act.get("type")
        payload = act.get("payload") or {}
        if t == "reply_text":
            await viber_api_send_text(chat_id=v_msg.chat_id, text=payload.get("text", ""))
        elif t == "click_interest":
            await viber_api_click_interested(v_msg)
        elif t == "open_chat":
            await bring_chat_to_front(v_msg.chat_id)
        elif t == "ignore":
            pass

async def viber_api_send_text(chat_id: str, text: str):
    # TODO: ваш реальный вызов Viber API / эмуляция клика
    print(f"[VIBER] -> {chat_id}: {text}")

async def viber_api_click_interested(v_msg):
    # TODO: ваша логика: клик по реакции/кнопке
    print(f"[VIBER] clicked 'interested' on message {v_msg.id}")

async def bring_chat_to_front(chat_id: str):
    # TODO: ваш OS-level фокус/переход к окну чата
    print(f"[OS] focus chat {chat_id}")
