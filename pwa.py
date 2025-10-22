from log import log_and_print
from find_message import (
    load_previous_text,
)
from utils import read_setting
from core import gui_driver as gd
from dispatcher.dispatch_client import (
    processViberMess,
    window_left,
    window_top_focus
)
import asyncio
from pywinauto import Application


s = {}
count_y_mess_empty = 0

class Context:
    def __init__(
        self,
        name_viber_channel,
        name_viber_contact,
        name_viber_contact_lang,
        old_text,
        width_menu=190,
        height_menu=220,
        height_item_menu=20,
        x_offset_out_mess=400,
        search_board_mess_x_start=360,
        search_board_mess_x_end=1000,
        search_board_mess_y_start=100,
        search_board_mess_y_end=1000,
    ):

        self.name_viber_channel = name_viber_channel
        self.name_viber_contact = name_viber_contact
        self.name_viber_contact_lang = name_viber_contact_lang
        self.old_text = old_text

        self.width_menu = width_menu
        self.height_menu = height_menu
        self.height_item_menu = height_item_menu
        self.x_offset_out_mess = x_offset_out_mess

        self.y_mess = []

        self.search_board_mess_x_start = search_board_mess_x_start
        self.search_board_mess_x_end = search_board_mess_x_end
        self.search_board_mess_y_start = search_board_mess_y_start
        self.search_board_mess_y_end = search_board_mess_y_end

    def display_info(self):
        """Method to display the bot's main information."""
        #return f"Bot Name: {self.name_viber}, Channels: {len(self.channels)}"


async def init():

    s = Context(
        name_viber_channel = read_setting("name_viber_channel"),
        name_viber_contact = read_setting("name_viber_contact"),
        name_viber_contact_lang = read_setting("name_viber_contact_lang"),
        old_text =  load_previous_text(),
        width_menu=190,
        height_menu=220,
        height_item_menu=20,
        x_offset_out_mess=400,
        search_board_mess_x_start=int(read_setting("search_board_mess_x_start")),
        search_board_mess_x_end=int(read_setting("search_board_mess_x_end")),
        search_board_mess_y_start=int(read_setting("search_board_mess_y_start")),
        search_board_mess_y_end=int(read_setting("search_board_mess_y_end")),
    )

    return s


async def main():

    count_scroll_up = read_setting("count_scroll_up")
    count_scroll_down = read_setting("count_scroll_down")
    pause_cycle_read = read_setting("pause_read_messages_second")

    gd.ensure_layout()

    try:
        s = await init()

        app = Application(backend="uia").connect(title="Rakuten Viber")
        window = app.window(title="Rakuten Viber")
        window_top_focus(window)
        window_left(window)

        gd.pause(0.5)

        while True:

            await processViberMess(
                window, s, count_scroll_up, count_scroll_down, pause_cycle_read
            )

    except Exception as e:
        print(f"An error occurred: {e}")
        input("Press Enter to exit...")


if __name__ == "__main__":
    asyncio.run(main())
