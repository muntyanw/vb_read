from tg import startTgClient
from vb_utils import *
from paint import *
from recognize_text import capture_and_recognize
from log import log_and_print
import pyperclip
from find_message import load_previous_text, save_current_text, are_texts_different
from pywinauto import Application, mouse

s = {}

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
                 template_height = 0):

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


    def display_info(self):
        """Method to display the bot's main information."""
        return (f"Bot Name: {self.name_viber}, Channels: {len(self.channels)}, "
                f"Template Board: {self.template_board}")

async def init():
    bot_client, name_viber, channels, channel_names = await startTgClient()
    old_text = load_previous_text()

    s = Context(bot_client, name_viber, channels, channel_names, old_text,
                ymax=880,
                xstart=351,
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
                template_height = get_image_height("images/komentar.png"))
    return s

def fill_y_mess(window, s):
    window.set_focus()
    log_and_print(f"Старт fill_y_mess")
    scroll_with_mouse(window, count_scroll=4)
    x, y, height = s.xstart, s.ymax, s.height_search_board_mess
    log_and_print(f"x = {x} y = {y} height = {height}")
    stop = False
    while not stop:
        #y = find_image_upward_with_highlight(x, y, s.ymax, height, s.template_board)
        y = find_text_upward_with_highlight(x, y, s.ymax, height, 20, 142, "Залишити коментар")
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

async def send_message(window, s, menu_items, x, y):
    window.set_focus()
    if isText(menu_items):
        left_click(x + int(s.width_menu / 2), y - s.height_item_menu)
        log_and_print(f"[send_message] Повідомлення скопиювовано в буфер обміну")

        text = reformat_telegram_text(pyperclip.paste())

        if are_texts_different(text, s.old_text):
            log_and_print(f"[send_message] Отправка нового текста в tg: {text}")
            for channel_name in s.channel_names:
                await process_one_message(text, s.bot_client, channel_name, s.name_viber)

            save_current_text(text)

        else:
            log_and_print(f"[send_message] Нема нового меседжа")

async def send_messages_from_y_mess(window, s):
    window.set_focus()
    x, y, height = s.xstart, s.ymax, s.height_search_board_mess
    region = []
    for y in reversed(s.y_mess):
        if y:
            y = y - s.y_menu_top_padding
            log_and_print(f"[send_messages_from_y_mess] Меседж y = {y}")
            region = [x + s.x_menu_left_padding, y - 120, s.width_menu, s.height_menu + 120]

        highlight_circle(x, y, duration=3, size=40, color="blue")
        right_click(x, y)
        # create_highlight_window(x + 40, y - 180, 220, 250, color=(255, 0, 0))
        #time.sleep(1)
        menu_items = capture_and_recognize(region)

        highlight_circle(x + s.x_offset_out_mess, y, duration=3, size=40, color="blue")

        log_and_print(f"menu_items = {menu_items}")

        await send_message(window, s, menu_items, x, y)

        right_click(x + s.x_offset_out_mess, y)

async def main():
    try:
        s = await init()

        app = Application(backend="uia").connect(title_re=".*Viber.*")
        window = app.window(title_re=".*Viber.*")
        window.set_focus()

        while True:
            fill_y_mess(window, s)
            await send_messages_from_y_mess(window,s)
            await asyncio.sleep(s.pause_read_messages_second)

    except Exception as e:
        print(f"An error occurred: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())


