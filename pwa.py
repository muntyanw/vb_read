from tg import startTgClient
from recognize_text import find_text_upward_with_highlight
from log import log_and_print
import pyperclip
from find_message import load_previous_text, save_current_text, remove_service_symbols_and_spaces
from pywinauto import Application
import cv2
from PIL import Image, ImageGrab
from io import BytesIO
import hashlib
from ScreenRegionSelector import ScreenRegionSelector
import keyboard
from utils import read_setting, write_setting
import pyautogui as pag

import os
from paint import show_position
from core import gui_driver as gd
from dispatcher.dispatch_client import processViberMess, klickUkrBus
import asyncio
from vb_utils import scroll_with_mouse, left_click

pag.FAILSAFE = False

# Константы WinAPI
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_DRAWFRAME = 0x0020

s = {}
count_y_mess_empty = 0

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
                 width_menu=190,
                 height_menu=220,
                 height_item_menu=20,
                 x_offset_out_mess=400,
                 search_board_mess_x_start=360,
                 search_board_mess_x_end=1000,
                 search_board_mess_y_start=100,
                 search_board_mess_y_end=1000,
                 ):

        self.bot_client = bot_client
        self.name_viber = name_viber
        self.channels = channels
        self.channel_names = channel_names
        self.old_text = old_text

        # Assign default attributes
        self.search_board_mess_x_start = search_board_mess_x_start
        self.width_menu = width_menu
        self.height_menu = height_menu
        self.height_item_menu = height_item_menu
        self.x_offset_out_mess = x_offset_out_mess

        self.y_mess = []

        self.search_board_mess_x_start = search_board_mess_x_start,
        self.search_board_mess_x_end = search_board_mess_x_end,
        self.search_board_mess_y_start = search_board_mess_y_start,
        self.search_board_mess_y_end = search_board_mess_y_end,


    def display_info(self):
        """Method to display the bot's main information."""
        return (f"Bot Name: {self.name_viber}, Channels: {len(self.channels)}")

async def init():
    bot_client, name_viber, channels, channel_names = await startTgClient()
    old_text = load_previous_text()

    s = Context(bot_client, name_viber, channels, channel_names, old_text,
                width_menu=190,
                height_menu=220,
                height_item_menu=20,
                x_offset_out_mess=400,
                search_board_mess_x_start=60,
                search_board_mess_x_end=1000,
                search_board_mess_y_start=100,
                search_board_mess_y_end=1000
                )

    s.search_board_mess_x_start = read_setting("search_board_mess_x_start")
    s.search_board_mess_x_end = read_setting("search_board_mess_x_end")
    s.search_board_mess_y_start = read_setting("search_board_mess_y_start")
    s.search_board_mess_y_end = read_setting("search_board_mess_y_end")
    # Создаем экземпляр и запускаем
    #log_and_print(f"Нажмить клавишу r щоб виділити область єкрана з сповіщеннями вайбєр, чи Enter щоб залишити старі")
    #while True:
    #    if keyboard.is_pressed('enter'):
    #        log_and_print("Нажата клавиша Enter")
    #        s.search_board_mess_x_start = read_setting("search_board_mess_x_start")
    #        s.search_board_mess_x_end = read_setting("search_board_mess_x_end")
    #        s.search_board_mess_y_start = read_setting("search_board_mess_y_start")
    #        s.search_board_mess_y_end = read_setting("search_board_mess_y_end")
    #        break

    #    elif keyboard.is_pressed('r'):
    #        print("Нажата клавиша R")
    #        screen_selector = ScreenRegionSelector()
    #        screen_selector.run()

            # После того как окно будет закрыто, получаем координаты выделенной области
    #        selected_region = screen_selector.get_selected_region()
    #        if selected_region:
    #            start_x, start_y, end_x, end_y = selected_region
    #            log_and_print(
    #                f"Координаты области с сообщениями для дальнейшего использования: ({start_x}, {start_y}) до ({end_x}, {end_y})")

    #            s.search_board_mess_x_start = start_x
    #            s.search_board_mess_x_end = end_x
    #            s.search_board_mess_y_start = start_y
    #            s.search_board_mess_y_end = end_y

    #            write_setting("search_board_mess_x_start", start_x)
    #            write_setting("search_board_mess_x_end", end_x)
    #            write_setting("search_board_mess_y_start", start_y)
    #            write_setting("search_board_mess_y_end", end_y)

    #        break

    return s

async def send_image(window, s, menu_items, x, y):
    global count_y_mess_empty
    x2, y2, w, h = menu_items["isImage"]
    x = x + x2 + int(w / 2)
    y = y + y2 + int(h / 2)
    #show_position(x, y, duration=10, size=40, color="blue")
    left_click(window, x, y)
    cv2.waitKey(100)
    log_and_print(f"[send_image] Зображення скопиювовано в буфер обміну")

    img = ImageGrab.grabclipboard()
    if img is None:
        log_and_print(f"[send_image] В буфере обмена нет изображения!")
        return

    hash = get_image_hash(img)

    if hash in s.old_text:
        log_and_print(f"[send_image] Картинка уже была отправлена!")
        count_y_mess_empty = count_y_mess_empty + 1
        return

    save_current_text(hash)
    s.old_text = load_previous_text()

    # Преобразуем изображение в поток байтов
    bio = BytesIO()
    bio.name = hash + '.png'
    file_path = os.getcwd() + "\\images\\" + bio.name

    if not os.path.isfile(file_path):
        img.save(file_path, 'PNG')

    #img.save(bio, 'PNG')

    bio.seek(0)

    log_and_print(f"[send_message] Отправка нового имиджа в tg: {bio.name}")
    #for channel_name in s.channel_names:
        #await process_one_message_dispatcher("", s.name_viber, file_path)

async def send_video(window, s, menu_items, x, y):
    global count_y_mess_empty
    path_files_downloads = read_setting("path_files_downloads")

    window.set_focus()

    x2, y2, w, h = menu_items["isVideo"]
    x = x + x2 + int(w / 2)
    y = y + y2 + int(h / 2)
    #show_position(x, y, duration=10, size=40, color="blue")
    left_click(window, x, y)
    cv2.waitKey(1000)

    pag.hotkey('ctrl', 'c')
    cv2.waitKey(300)
    file_name =  pyperclip.paste()
    log_and_print(f"[send_video] Буфер обмена {file_name}")

    textFind = remove_service_symbols_and_spaces(file_name)
    if textFind in s.old_text:
        count_y_mess_empty = count_y_mess_empty + 1
        log_and_print(f"[send_image] Файл уже был отправлен!")
        pag.press('tab', presses=4, interval=0.1)
        # cv2.waitKey(1000)
        pag.press('enter')
        cv2.waitKey(1000)
        return

    save_current_text(textFind)
    s.old_text = load_previous_text()

    file = path_files_downloads + file_name + ".mp4"
    log_and_print(f"[send_video] file = {file}")

    if os.path.isfile(file):
        log_and_print(f"[send_message_to_tg_channel] Файл уже сохранен: {file}")
        pag.press('tab', presses=4, interval=0.1)
        # cv2.waitKey(1000)
        pag.press('enter')
        cv2.waitKey(1000)
        return

    pyperclip.copy(path_files_downloads)
    pag.press('tab', presses=6, interval=0.1)
    #cv2.waitKey(1000)
    pag.press('enter')
    #cv2.waitKey(1000)
    pag.hotkey('ctrl', 'v')
    #cv2.waitKey(1000)
    pag.press('enter')
    #cv2.waitKey(1000)
    pag.press('tab', presses=8, interval=0.1)
    #cv2.waitKey(1000)
    pag.press('enter')

    cv2.waitKey(1000)

    #file = get_latest_file(path_files_downloads)

    # if not file:
    #     log_and_print(f"[send_image] Не смогли сохранить файл!")
    #     return

    #file_name = Path(file).stem

    save_current_text(file_name)
    s.old_text = load_previous_text()

    log_and_print(f"[send_message] Отправка нового файла в tg: {file}")
    #for channel_name in s.channel_names:
        #await process_one_message_dispatcher("", s.name_viber, file)

async def main():
    
    count_scroll_up = read_setting("count_scroll_up")
    count_scroll_down = read_setting("count_scroll_down")
    pause_cycle_read = read_setting("pause_read_messages_second")
    
    gd.ensure_layout()
    
    try:
        s = await init()

        app = Application(backend="uia").connect(title="Rakuten Viber")
        window = app.window(title="Rakuten Viber")

        window.set_focus()
        
        if not klickUkrBus(False):
            log_and_print("Not find chat UkrBus")
            return None
        
        gd.pause(0.5)

        scroll_with_mouse(window, count_scroll=count_scroll_up, direction="up")

        while True:
            await processViberMess(window, s,
                             count_scroll_up,
                             count_scroll_down,
                             pause_cycle_read)
                             
                              
            

    except Exception as e:
        print(f"An error occurred: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())


