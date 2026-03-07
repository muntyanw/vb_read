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
from dispatcher.personal_broadcast_position_sender import PersonalBroadcastPositionSender
from dispatcher.personal_broadcast_scroll_names_sender import PersonalBroadcastScrollNamesSender
from dispatcher.server_dispatcher_config import load_server_dispatcher_config
from dispatcher.server_dispatcher_sender import ServerDispatcherSender
from log import set_debug_mode, log_and_print
import asyncio
import logging
from pywinauto import Application
from pathlib import Path
import subprocess
import shutil
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

def _to_bool(val, default=False):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default

def _clear_logs_and_temp_if_enabled():
    enabled = _to_bool(read_setting("clear_logs_and_temp_on_startup"), False)
    if not enabled:
        return

    # Truncate current log file through active logging handlers.
    cleared_log = False
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                handler.acquire()
                if handler.stream:
                    handler.stream.seek(0)
                    handler.stream.truncate(0)
                    handler.flush()
                    cleared_log = True
                    break
            except Exception:
                pass
            finally:
                try:
                    handler.release()
                except Exception:
                    pass

    if not cleared_log:
        try:
            Path("log.log").write_text("", encoding="utf-8")
        except Exception:
            pass

    # Remove previous temp snapshots for clean run diagnostics.
    temp_dir = Path(__file__).resolve().parent / "temp_log"
    try:
        if temp_dir.exists():
            for child in temp_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except Exception:
                        pass
        else:
            temp_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[pwa] failed to clear temp_log: {e}")


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
    _clear_logs_and_temp_if_enabled()

    def load_runtime_settings():
        return {
            "count_scroll_up": _to_int(read_setting("count_scroll_up"), 2),
            "count_scroll_down": _to_int(read_setting("count_scroll_down"), 2),
            "pause_cycle_read": _to_float(read_setting("pause_read_messages_second"), 1.0),
            "cycle_timeout_s": _to_int(read_setting("cycle_timeout_s"), 120),
            "restart_delay_s": _to_int(read_setting("restart_delay_s"), 5),
            "settings_reload_interval_s": _to_int(read_setting("settings_reload_interval_s"), 30),
            "work_mode": str(read_setting("work_mode") or "reader").strip().lower(),
            "debug_logs_mode": _to_bool(read_setting("debug_logs_mode"), False),
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
    set_debug_mode(runtime_settings["debug_logs_mode"])
    log_and_print(f"[pwa] startup mode={runtime_settings['work_mode']}", "debug")
    last_settings_reload_at = time.monotonic()

    gd.ensure_layout()
    periodic_sender = PeriodicBroadcastSender(load_periodic_broadcast_config())
    server_sender = ServerDispatcherSender(load_server_dispatcher_config())
    personal_config = load_personal_broadcast_config()
    if personal_config.processing_mode == "by_positions":
        personal_sender = PersonalBroadcastPositionSender(personal_config)
    elif personal_config.processing_mode == "by_scroll_names":
        personal_sender = PersonalBroadcastScrollNamesSender(personal_config)
    else:
        personal_sender = PersonalBroadcastSender(personal_config)

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
        nonlocal runtime_settings, last_settings_reload_at, periodic_sender, server_sender, personal_sender
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
                set_debug_mode(runtime_settings["debug_logs_mode"])
                refresh_context_from_settings(s)
                periodic_sender.update_config(load_periodic_broadcast_config())
                server_sender.update_config(load_server_dispatcher_config())
                new_personal_config = load_personal_broadcast_config()
                current_mode = getattr(getattr(personal_sender, "_config", None), "processing_mode", "by_names")
                if new_personal_config.processing_mode != current_mode:
                    if new_personal_config.processing_mode == "by_positions":
                        personal_sender = PersonalBroadcastPositionSender(new_personal_config)
                    elif new_personal_config.processing_mode == "by_scroll_names":
                        personal_sender = PersonalBroadcastScrollNamesSender(new_personal_config)
                    else:
                        personal_sender = PersonalBroadcastSender(new_personal_config)
                    log_and_print(
                        f"[pwa] personal sender switched to {new_personal_config.processing_mode}",
                        "debug",
                    )
                else:
                    personal_sender.update_config(new_personal_config)
                log_and_print(
                    f"[pwa] settings reloaded; mode={runtime_settings['work_mode']}",
                    "debug",
                )
                last_settings_reload_at = now

            if runtime_settings["work_mode"] == "personal_broadcast":
                personal_sender.run_once(window, s)
                await asyncio.sleep(0.2)
            else:
                periodic_sender.send_if_due(window, s)
                server_sender.send_if_due(window, s)
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
            log_and_print(f"[pwa] error: {e}, restarting worker", "error")

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
