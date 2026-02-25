from find_message import (
    load_previous_text,
)
from utils import read_setting
from core import gui_driver as gd
from dispatcher.dispatch_client import (
    processViberMess,
    window_left,
    window_top_focus,
    reset_copy_watchdog
)
from dispatcher.periodic_broadcast_config import load_periodic_broadcast_config
from dispatcher.periodic_broadcast_sender import PeriodicBroadcastSender
from dispatcher.personal_broadcast_config import load_personal_broadcast_config
from dispatcher.personal_broadcast_sender import PersonalBroadcastSender
import asyncio
from pywinauto import Application
from pathlib import Path
import subprocess
import traceback
import time


s = {}
count_y_mess_empty = 0

STOP_FILE = Path("stop.txt")

def _to_int(val, default):
    try:
        return int(val)
    except Exception:
        return default

def _to_float(val, default):
    try:
        return float(val)
    except Exception:
        return default

class Context:
    def __init__(
        self,
        viber_channels,
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

        self.viber_channels = viber_channels
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
        viber_channels = read_setting("viber_channels"),
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

async def ensure_viber_ready():
    """Ensure Viber app is running and return connected (app, window)."""
    app = Application(backend="uia")
    try:
        app.connect(title="Rakuten Viber")
    except Exception:
        viber_exe = read_setting("viber_exe_path") or str(
            Path.home() / "AppData" / "Local" / "Viber" / "Viber.exe"
        )
        try:
            subprocess.Popen(viber_exe)
        except Exception as e:
            raise RuntimeError(f"Failed to start Viber at {viber_exe}: {e}")

        for _ in range(15):
            await asyncio.sleep(1)
            try:
                app.connect(title="Rakuten Viber")
                break
            except Exception:
                continue
        else:
            raise RuntimeError("Viber window not found after startup attempts")

    window = app.window(title="Rakuten Viber")
    return app, window


async def main():
    def load_runtime_settings():
        return {
            "count_scroll_up": _to_int(read_setting("count_scroll_up"), 2),
            "count_scroll_down": _to_int(read_setting("count_scroll_down"), 2),
            "pause_cycle_read": _to_float(read_setting("pause_read_messages_second"), 1.0),
            "cycle_timeout_s": _to_int(read_setting("cycle_timeout_s"), 120),
            "restart_delay_s": _to_int(read_setting("restart_delay_s"), 5),
            "settings_reload_interval_s": _to_int(read_setting("settings_reload_interval_s"), 30),
            "work_mode": str(read_setting("work_mode") or "reader").strip().lower(),
        }

    def refresh_context_from_settings(ctx):
        viber_channels = read_setting("viber_channels")
        if isinstance(viber_channels, list) and viber_channels:
            ctx.viber_channels = viber_channels

        ctx.search_board_mess_x_start = _to_int(
            read_setting("search_board_mess_x_start"),
            ctx.search_board_mess_x_start,
        )
        ctx.search_board_mess_x_end = _to_int(
            read_setting("search_board_mess_x_end"),
            ctx.search_board_mess_x_end,
        )
        ctx.search_board_mess_y_start = _to_int(
            read_setting("search_board_mess_y_start"),
            ctx.search_board_mess_y_start,
        )
        ctx.search_board_mess_y_end = _to_int(
            read_setting("search_board_mess_y_end"),
            ctx.search_board_mess_y_end,
        )

    runtime_settings = load_runtime_settings()
    last_settings_reload_at = time.monotonic()

    gd.ensure_layout()
    periodic_sender = PeriodicBroadcastSender(load_periodic_broadcast_config())
    personal_sender = PersonalBroadcastSender(load_personal_broadcast_config())

    def stop_requested():
        if STOP_FILE.exists():
            try:
                STOP_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            print("[pwa] stop file detected, shutting down")
            return True
        return False


    async def run_worker():
        nonlocal runtime_settings, last_settings_reload_at, periodic_sender, personal_sender
        s = await init()
        reset_copy_watchdog()

        _, window = await ensure_viber_ready()
        window_top_focus(window)
        window_left(window)

        gd.pause(0.5)

        while True:
            if stop_requested():
                break

            now = time.monotonic()
            if now - last_settings_reload_at >= runtime_settings["settings_reload_interval_s"]:
                runtime_settings = load_runtime_settings()
                refresh_context_from_settings(s)
                periodic_sender.update_config(load_periodic_broadcast_config())
                personal_sender.update_config(load_personal_broadcast_config())
                last_settings_reload_at = now

            if runtime_settings["work_mode"] == "personal_broadcast":
                personal_sender.run_once(window, s)
                await asyncio.sleep(0.2)
            else:
                periodic_sender.send_if_due(window, s)
                await processViberMess(
                    window,
                    s,
                    runtime_settings["count_scroll_up"],
                    runtime_settings["count_scroll_down"],
                    runtime_settings["pause_cycle_read"],
                )

    while True:
        try:
            await run_worker()
        except Exception as e:
            print(f"[pwa] error: {e}, restarting worker")

        if stop_requested():
            break

        await asyncio.sleep(runtime_settings["restart_delay_s"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception:
        traceback.print_exc()
    finally:
        input("\nPress Enter to close...")
