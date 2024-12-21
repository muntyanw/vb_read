from tg import startTgClient
from vb_utils import *
from recognize_text import capture_and_find_multiple_text_coordinates, capture_and_find_text_coordinates
from log import log_and_print
import pyperclip
from find_message import load_previous_text, save_current_text, remove_service_symbols_and_spaces
from pywinauto import Application
import ctypes
import cv2
from PIL import Image, ImageGrab
from io import BytesIO
import hashlib
from ScreenRegionSelector import ScreenRegionSelector
import keyboard
from utils import read_setting, write_setting

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

class Context:
    def __init__(self, bot_client, name_viber, channels, channel_names, old_text,
                 x_menu_left_padding=40,
                 y_menu_top_padding=40,
                 y_menu_minus_padding=160,
                 width_menu=190,
                 height_menu=220,
                 height_item_menu=40,
                 x_offset_out_mess=400,
                 template_board="images/komentar.png",
                 search_phrases = None,
                 search_board_mess_x_start=360,
                 search_board_mess_x_end=1000,
                 search_board_mess_y_start=100,
                 search_board_mess_y_end=1000,
                 ):

        # Assign parameters to instance attributes
        if search_phrases is None:
            search_phrases = {
                "isText": "Скопировать",
                "isImage": "Копировать"
            }
        self.bot_client = bot_client
        self.name_viber = name_viber
        self.channels = channels
        self.channel_names = channel_names
        self.old_text = old_text

        # Assign default attributes
        self.search_board_mess_x_start = search_board_mess_x_start
        self.x_menu_left_padding = x_menu_left_padding
        self.y_menu_top_padding = y_menu_top_padding
        self.y_menu_minus_padding = y_menu_minus_padding
        self.width_menu = width_menu
        self.height_menu = height_menu
        self.height_item_menu = height_item_menu
        self.x_offset_out_mess = x_offset_out_mess
        self.template_board = template_board

        self.y_mess = []
        self.search_phrases = search_phrases

        self.search_board_mess_x_start = search_board_mess_x_start,
        self.search_board_mess_x_end = search_board_mess_x_end,
        self.search_board_mess_y_start = search_board_mess_y_start,
        self.search_board_mess_y_end = search_board_mess_y_end,


    def display_info(self):
        """Method to display the bot's main information."""
        return (f"Bot Name: {self.name_viber}, Channels: {len(self.channels)}, "
                f"Template Board: {self.template_board}")

async def init():
    bot_client, name_viber, channels, channel_names = await startTgClient()
    old_text = load_previous_text()

    s = Context(bot_client, name_viber, channels, channel_names, old_text,
                x_menu_left_padding=40,
                y_menu_top_padding=40,
                y_menu_minus_padding=160,
                width_menu=190,
                height_menu=220,
                height_item_menu=40,
                x_offset_out_mess=400,
                template_board="images/komentar.png",
                search_phrases={
                    "isText": "Скопировать",
                    "isImage": "Копировать"
                },
                search_board_mess_x_start=60,
                search_board_mess_x_end=1000,
                search_board_mess_y_start=100,
                search_board_mess_y_end=1000
                )

    # Создаем экземпляр и запускаем
    log_and_print(f"Нажмить клавишу r щоб виділити область єкрана з сповіщеннями вайбєр, чи Enter щоб залишити старі")
    while True:
        if keyboard.is_pressed('enter'):
            log_and_print("Нажата клавиша Enter")
            s.search_board_mess_x_start = read_setting("search_board_mess_x_start")
            s.search_board_mess_x_end = read_setting("search_board_mess_x_end")
            s.search_board_mess_y_start = read_setting("search_board_mess_y_start")
            s.search_board_mess_y_end = read_setting("search_board_mess_y_end")
            break

        elif keyboard.is_pressed('r'):
            print("Нажата клавиша R")
            screen_selector = ScreenRegionSelector()
            screen_selector.run()

            # После того как окно будет закрыто, получаем координаты выделенной области
            selected_region = screen_selector.get_selected_region()
            if selected_region:
                start_x, start_y, end_x, end_y = selected_region
                log_and_print(
                    f"Координаты области с сообщениями для дальнейшего использования: ({start_x}, {start_y}) до ({end_x}, {end_y})")

                s.search_board_mess_x_start = start_x
                s.search_board_mess_x_end = end_x
                s.search_board_mess_y_start = start_y
                s.search_board_mess_y_end = end_y

                write_setting("search_board_mess_x_start", start_x)
                write_setting("search_board_mess_x_end", end_x)
                write_setting("search_board_mess_y_start", start_y)
                write_setting("search_board_mess_y_end", end_y)

            break

    return s

def fill_y_mess(window, s):
    s.y_mess = []
    window.set_focus()
    log_and_print(f"Старт fill_y_mess")

    height = s.search_board_mess_y_end - s.search_board_mess_y_start
    width = s.search_board_mess_x_end - s.search_board_mess_x_start
    x, y = s.search_board_mess_x_start, s.search_board_mess_y_start

    log_and_print(f"x = {x} y = {y} height = {height}, width = {width}")

    region = [x,y, width, height]
    coordinates = capture_and_find_text_coordinates(region, read_setting("word_comment"), visualize = read_setting("visualize"))
    window.set_focus()

    s.y_mess = [coord[1] for coord in coordinates]

    log_and_print(f"s.y_mess = {s.y_mess}")

async def send_text(window, s, menu_items, x, y):
    x2, y2, w, h = menu_items["isText"]
    x = x + x2 + int(w / 2)
    y = y + y2 +10
    #show_position(x, y, duration=10, size=40, color="blue")
    left_click(x, y)
    cv2.waitKey(100)
    log_and_print(f"[send_text] Повідомлення скопиювовано в буфер обміну")

    textOrigin = pyperclip.paste()
    textFind = remove_service_symbols_and_spaces(textOrigin)
    text = reformat_telegram_text(textOrigin)
    log_and_print(f"[send_text] textOrigin = {textOrigin}")

    if not text:
        log_and_print(f"[send_text] Не вдалося скопіювати меседж, буфєр обміну пустий")
    else:
        if not textFind in s.old_text:
            log_and_print(f"[send_text] Отправка нового текста в tg: {text}")
            for channel_name in s.channel_names:
                await process_one_message(text, s.bot_client, channel_name, s.name_viber, None)

            save_current_text(textOrigin)
            s.old_text = load_previous_text()

        else:
            log_and_print(f"[send_text] Нема нового меседжа")

async def send_image(window, s, menu_items, x, y):

    x2, y2, w, h = menu_items["isImage"]
    x = x + x2 + int(w / 2)
    y = y + y2 + int(h / 2)
    #show_position(x, y, duration=10, size=40, color="blue")
    left_click(x, y)
    cv2.waitKey(100)
    log_and_print(f"[send_image] Зображення скопиювовано в буфер обміну")

    img = ImageGrab.grabclipboard()
    if img is None:
        log_and_print(f"[send_image] В буфере обмена нет изображения!")
        return

    hash = get_image_hash(img)

    if hash in s.old_text:
        log_and_print(f"[send_image] Картинка уже была отправлена!")
        return

    save_current_text(hash)
    s.old_text = load_previous_text()

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
    #left_click(x, y)
    #cv2.waitKey(10)

    if menu_items["isText"]:
        await send_text(window, s, menu_items, x, y)
    elif menu_items["isImage"]:
        await send_image(window, s, menu_items, x, y)

async def send_messages_from_y_mess(window, s):
    window.set_focus()
    x, y_start, height = s.search_board_mess_x_start, s.search_board_mess_y_start, s.search_board_mess_x_end - s.search_board_mess_x_start
    region = []
    for y in s.y_mess:
        if y:
            log_and_print(f"[send_messages_from_y_mess] Меседж y = {y}")
            y = y_start + y - 20
            window.set_focus()
            #show_position(x, y+ 10, duration=10, size=10, color="blue")
            #cv2.waitKey(3000)
            #window.set_focus()
            #left_click(x, y)
            right_click(x, y)

            y = y - s.y_menu_top_padding - 100
            x = x + 50
            region = [x, y, s.width_menu, s.height_menu + 80]
            cv2.waitKey(1000)
            menu_items = capture_and_find_multiple_text_coordinates(region, s.search_phrases, visualize = read_setting("visualize"))

            log_and_print(f"menu_items = {menu_items}")

            await send_message(window, s, menu_items, region[0], region[1])


async def main():
    try:
        s = await init()

        app = Application(backend="uia").connect(title_re=".*Viber.*")
        window = app.window(title_re=".*Viber.*")
        window.set_focus()
        hwnd = window.handle

        scroll_with_mouse(window, count_scroll=read_setting("count_scroll"))

        i = 0

        while True:
            pause = 2
            i = i + 1
            ctypes.windll.user32.LockWindowUpdate(hwnd)

            if i == read_setting("count_repeat"):
                scroll_with_mouse(window, count_scroll=read_setting("count_scroll"))
                pause = read_setting("pause_read_messages_second")
                i = 0
            else:
                scroll_with_mouse(window, count_scroll=1)

            fill_y_mess(window, s)
            if len(s.y_mess) > 0:
                await send_messages_from_y_mess(window,s)

            ctypes.windll.user32.LockWindowUpdate(0)

            right_click(s.search_board_mess_x_start + s.x_offset_out_mess, s.search_board_mess_y_end - 100)

            log_and_print(f"pause = {pause}")
            await asyncio.sleep(pause)

    except Exception as e:
        print(f"An error occurred: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())


