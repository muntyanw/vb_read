from tg import startTgClient
from vb_utils import *
from paint import *
from recognize_text import capture_and_find_multiple_text_coordinates, capture_and_find_text_coordinates
from log import log_and_print
import pyperclip
from find_message import load_previous_text, save_current_text, is_subtext_present_at_threshold
from pywinauto import Application, mouse
import ctypes
import cv2
from PIL import Image, ImageOps, ImageGrab
from io import BytesIO
from collections import deque
import hashlib

# Константы WinAPI
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_DRAWFRAME = 0x0020

s = {}


def get_image_hash(image, size=(8, 8)):
    """
    Возвращает хэш для изображения, снижая его разрешение до size
    и переводя в градации серого. Подходит для быстрого сравнения изображений.

    Параметры:
    - image: объект PIL.Image или любой формат, который PIL может прочитать
      (BytesIO, путь к файлу)
    - size: кортеж (ширина, высота) для уменьшения изображения

    Возвращает:
    - строку с хэшем (hex-формат)
    """
    # Если передан не PIL.Image, пытаемся открыть
    if not isinstance(image, Image.Image):
        if hasattr(image, 'read'):
            # Если это поток (например BytesIO)
            img = Image.open(image)
        else:
            # Если это путь к файлу
            img = Image.open(str(image))
    else:
        img = image

    # Преобразуем в градации серого и уменьшаем до маленького размера с LANCZOS-ресемплингом
    img = img.convert("L").resize(size, Image.Resampling.LANCZOS)

    # Извлекаем байты пикселей
    pixel_data = img.tobytes()

    # Получаем хэш от байтов пикселей
    hash_hex = hashlib.md5(pixel_data).hexdigest()

    return hash_hex

class ImageHashHistory:
    def __init__(self, max_size=400):
        """
        Инициализация хранилища с максимально допустимым размером.
        """
        self.max_size = max_size
        self.hashes = deque()

    def add_hash(self, new_hash):
        """
        Добавляет новый хэш в начало очереди.
        Если длина превышает max_size, удаляется самый старый хэш с другого конца.
        """
        self.hashes.appendleft(new_hash)
        if len(self.hashes) > self.max_size:
            self.hashes.pop()

    def contains(self, hash_to_check):
        """
        Проверяет, содержится ли указанный хэш в текущем списке.
        """
        return hash_to_check in self.hashes

    def get_all_hashes(self):
        """
        Возвращает список всех хэшей (от нового к старому).
        Это не обязательно, но может быть полезно для отладки.
        """
        return list(self.hashes)

history = ImageHashHistory(max_size=10)

class Context:
    def __init__(self, bot_client, name_viber, channels, channel_names, old_text,
                 ymax=820,
                 xstart=360,
                 x_menu_left_padding=40,
                 y_menu_top_padding=40,
                 y_menu_minus_padding=160,
                 width_menu=190,
                 height_menu=220,
                 height_item_menu=40,
                 height_search_board_mess=600,
                 x_offset_out_mess=400,
                 template_board="images/komentar.png",
                 pause_read_messages_second = 10,
                 template_height = 0,
                 search_phrases = {
                    "isText": "Скопировать",
                    "isImage": "Копировать"
                 },
                 width_search_board_mess = 650):

        # Assign parameters to instance attributes
        self.bot_client = bot_client
        self.name_viber = name_viber
        self.channels = channels
        self.channel_names = channel_names
        self.old_text = old_text

        # Assign default attributes
        self.ymax = ymax
        self.xstart = xstart
        self.x_menu_left_padding = x_menu_left_padding
        self.y_menu_top_padding = y_menu_top_padding
        self.y_menu_minus_padding = y_menu_minus_padding
        self.width_menu = width_menu
        self.height_menu = height_menu
        self.height_item_menu = height_item_menu
        self.height_search_board_mess = height_search_board_mess
        self.x_offset_out_mess = x_offset_out_mess
        self.template_board = template_board
        self.pause_read_messages_second = pause_read_messages_second
        self.template_height = template_height

        self.y_mess = []
        self.search_phrases = search_phrases
        self.width_search_board_mess = width_search_board_mess

    def display_info(self):
        """Method to display the bot's main information."""
        return (f"Bot Name: {self.name_viber}, Channels: {len(self.channels)}, "
                f"Template Board: {self.template_board}")

async def init():
    bot_client, name_viber, channels, channel_names = await startTgClient()
    old_text = load_previous_text()

    s = Context(bot_client, name_viber, channels, channel_names, old_text,
                ymax=1000,
                xstart=330,
                x_menu_left_padding=40,
                y_menu_top_padding=40,
                y_menu_minus_padding=160,
                width_menu=190,
                height_menu=220,
                height_item_menu=40,
                height_search_board_mess=900,
                x_offset_out_mess=400,
                template_board="images/komentar.png",
                pause_read_messages_second = 30,
                template_height = get_image_height("images/komentar.png"),
                search_phrases={
                    "isText": "Скопировать",
                    "isImage": "Копировать"
                },
                width_search_board_mess=650
    )
    return s

def fill_y_mess(window, s):
    s.y_mess = []
    window.set_focus()
    log_and_print(f"Старт fill_y_mess")
    scroll_with_mouse(window, count_scroll=16)
    x, y, height, width = s.xstart, s.ymax - s.height_search_board_mess, s.height_search_board_mess, s.width_search_board_mess
    log_and_print(f"x = {x} y = {y} height = {height}, width = {width}")

    region = [x,y, width, height]
    coordinates = capture_and_find_text_coordinates(region, "Прокомментировать")

    s.y_mess = [coord[1] - s.y_menu_top_padding for coord in coordinates]

    log_and_print(f"s.y_mess = {s.y_mess}")


def fill_y_messOld(window, s):
    s.y_mess = []
    window.set_focus()
    log_and_print(f"Старт fill_y_mess")
    scroll_with_mouse(window, count_scroll=16)
    x, y, height = s.xstart, s.ymax, s.height_search_board_mess
    left_click(x + s.x_offset_out_mess, y)
    log_and_print(f"x = {x} y = {y} height = {height}")
    stop = False
    while not stop:
        window.set_focus()
        #y = find_image_upward_with_highlight(x, y, s.ymax, height, s.template_board)
        y = find_text_upward_with_highlight(x, y, s.ymax, height, 20, 142, "Прокомментировать")
        log_and_print(f"s.y_menu_top_padding = {s.y_menu_top_padding}")
        log_and_print(f"s.y = {y}")
        if y:
            s.y_mess.append(y - s.y_menu_top_padding)
            log_and_print(f"Границя меседжів знайдена y = {y}")
            y = y - s.template_height
        else:
            log_and_print(f"Не знайдена границя меседжів")
            stop = True

    log_and_print(f"s.y_mess = {s.y_mess}")

async def send_text(window, s, menu_items, x, y):
    x2, y2, w, h = menu_items["isText"]
    x = x + x2 + int(w / 2)
    y = y + y2 + int(h / 2)
    # highlight_circle(x, y, duration=3, size=40, color="blue")
    # time.sleep(30)
    left_click(x, y)
    cv2.waitKey(100)
    log_and_print(f"[send_text] Повідомлення скопиювовано в буфер обміну")

    textOrigin = pyperclip.paste()
    text = reformat_telegram_text(textOrigin)
    log_and_print(f"[send_text] textOrigin = {textOrigin}")

    if not text:
        log_and_print(f"[send_text] Не вдалося скопіювати меседж, буфєр обміну пустий")
    else:
        if not is_subtext_present_at_threshold(s.old_text, textOrigin, threshold=20):
            log_and_print(f"[send_text] Отправка нового текста в tg: {text}")
            for channel_name in s.channel_names:
                await process_one_message(text, s.bot_client, channel_name, s.name_viber, None)

            save_current_text(textOrigin)
            s.old_text = load_previous_text()

        else:
            log_and_print(f"[send_text] Нема нового меседжа")

async def send_image(window, s, menu_items, x, y):
    global history

    x2, y2, w, h = menu_items["isImage"]
    x = x + x2 + int(w / 2)
    y = y + y2 + int(h / 2)
    # highlight_circle(x, y, duration=3, size=40, color="blue")
    # time.sleep(30)
    left_click(x, y)
    cv2.waitKey(100)
    log_and_print(f"[send_image] Зображення скопиювовано в буфер обміну")

    img = ImageGrab.grabclipboard()
    if img is None:
        log_and_print(f"[send_image] В буфере обмена нет изображения!")
        return

    hash = get_image_hash(img)

    if history.contains(hash):
        log_and_print(f"[send_image] Картинка уже была отправлена!")
        return

    history.add_hash(hash)
    log_and_print(f"[send_image] get_all_hashes {history.get_all_hashes()}")

    # Преобразуем изображение в поток байтов
    bio = BytesIO()
    bio.name = hash + '.png'
    img.save(bio, 'PNG')
    bio.seek(0)

    log_and_print(f"[send_message] Отправка нового имиджа в tg: {bio.name}")
    for channel_name in s.channel_names:
        await process_one_message("", s.bot_client, channel_name, s.name_viber, bio)


async def send_message(window, s, menu_items, x, y):
    window.set_focus()
    if menu_items["isText"]:
        await send_text(window, s, menu_items, x, y)
    elif menu_items["isImage"]:
        await send_image(window, s, menu_items, x, y)


async def send_messages_from_y_mess(window, s):
    window.set_focus()
    x, y, height = s.xstart, s.ymax, s.height_search_board_mess
    region = []
    for y in reversed(s.y_mess):
        if y:
            y = y - s.y_menu_top_padding
            log_and_print(f"[send_messages_from_y_mess] Меседж y = {y}")
            region = [x + s.x_menu_left_padding, y - 120, s.width_menu, s.height_menu + 120]

        window.set_focus()
        right_click(x, y)
        cv2.waitKey(100)
        menu_items = capture_and_find_multiple_text_coordinates(region, s.search_phrases)

        log_and_print(f"menu_items = {menu_items}")

        await send_message(window, s, menu_items, region[0], region[1])

        right_click(x + s.x_offset_out_mess, y)

async def main():
    try:
        s = await init()

        app = Application(backend="uia").connect(title_re=".*Viber.*")
        window = app.window(title_re=".*Viber.*")
        window.set_focus()
        hwnd = window.handle

        while True:
            ctypes.windll.user32.LockWindowUpdate(hwnd)
            fill_y_mess(window, s)
            await send_messages_from_y_mess(window,s)
            ctypes.windll.user32.LockWindowUpdate(0)
            await asyncio.sleep(s.pause_read_messages_second)

    except Exception as e:
        print(f"An error occurred: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())


