# project_config.py
from __future__ import annotations

import os
import sys
import yaml
from pathlib import Path
from typing import Any, Dict

def resource_path(filename: str) -> Path:
    """
    Возвращает абсолютный путь к ресурсу, который работает как в .py, так и в .exe (PyInstaller).
    """
    if hasattr(sys, "_MEIPASS"):
        # 1) путь внутри PyInstaller bundle
        bundle_path = Path(sys._MEIPASS) / filename
        if bundle_path.exists():
            return bundle_path
        # 2) fallback: рядом с exe (для внешних конфигов)
        return Path(sys.executable).resolve().parent / filename

    # обычный путь при запуске из .py
    return Path(__file__).resolve().parent / filename


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def external_or_resource_path(filename: str) -> Path:
    external_path = app_dir() / filename
    if external_path.exists():
        return external_path
    return resource_path(filename)


def writable_app_path(filename: str) -> Path:
    target = app_dir() / filename
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or os.access(str(target.parent), os.W_OK):
            return target
    except OSError:
        pass

    fallback_dir = Path.home() / ".vb_read"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    return fallback_dir / filename


def _resolve_config_path(value: str, default: str) -> Path:
    raw_value = value or default
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = _SETTINGS_PATH.parent / path
    return path.resolve()

# -------------------------------------------------------------------
# 1) Определяем путь до settings.yaml (корень проекта)
# -------------------------------------------------------------------
_SETTINGS_PATH = external_or_resource_path("settings.yaml")

# -------------------------------------------------------------------
# 2) Загружаем YAML-данные при импорте (одно чтение)
# -------------------------------------------------------------------
try:
    with _SETTINGS_PATH.open("rt", encoding="utf-8") as _fh:
        _RAW_SETTINGS: Dict[str, Any] = yaml.safe_load(_fh) or {}
except FileNotFoundError:
    raise RuntimeError(f"settings.yaml not found at {_SETTINGS_PATH}")

# -------------------------------------------------------------------
# 3) “Высвобождаем” из _RAW_SETTINGS нужные переменные в виде констант
# -------------------------------------------------------------------
# Пример: пути к каталогам
USERS_DIR: Path = _resolve_config_path(_RAW_SETTINGS.get("users_dir", "users_cfg"), "users_cfg")
KEYS_DIR: Path = _resolve_config_path(_RAW_SETTINGS.get("keys_dir", "keys"), "keys")

# Путь до шаблона профиля Chrome
CHROME_TEMPLATE: Path = _resolve_config_path(
    _RAW_SETTINGS.get("chrome_template", "chrome_template/profile"),
    "chrome_template/profile",
)
CHROME_TEMPLATES: Path = _resolve_config_path(
    _RAW_SETTINGS.get("chrome_templates", "chrome_template/profiles"),
    "chrome_template/profiles",
)

# Флаг: сохраняем ли профили между запусками
KEEP_PROFILES: bool = bool(_RAW_SETTINGS.get("keep_profiles", False))

# Порт TCP-контроля (pause/resume/stop)
CONTROL_PORT: int = int(_RAW_SETTINGS.get("control_port", 4567))

# Параметры для целевого монитора
MONITOR_WIDTH:  int = int(_RAW_SETTINGS.get("monitor_width", 1920))
MONITOR_HEIGHT: int = int(_RAW_SETTINGS.get("monitor_height", 1080))
MONITOR_INDEX: int = int(_RAW_SETTINGS.get("monitor_index", 1))
MON_X: int = int(_RAW_SETTINGS.get("mon_x", 1920))


TEMPLATE_DIR: Path = _resolve_config_path(_RAW_SETTINGS.get("ui_images", "images"), "images")

# Настройки HTML-логгера
HTML_LOG_DIR: Path = _resolve_config_path(
    _RAW_SETTINGS.get("html_log_dir", "data/html_log"),
    "data/html_log",
)

# Уровень логирования (строка, например "DEBUG", "INFO")
LOG_LEVEL: str = str(_RAW_SETTINGS.get("log_level", "INFO")).upper()

TESSDATA_PREFIX: str = str(_RAW_SETTINGS.get("tessdata_prefix", r"C:/Program Files/Tesseract-OCR/"))
TESSERCAT_CMD: str = str(_RAW_SETTINGS.get("tesseract_cmd", r"C:/Program Files/Tesseract-OCR/tesseract.exe"))

CHECK_EMPTY_TEMPLATE_PATH: str = str(_RAW_SETTINGS.get("check_empty_template_path", "check_empty.png"))
CHECK_CHECKED_TEMPLATE_PATH: str = str(_RAW_SETTINGS.get("check_checked_template_path", "check_checked.png"))

VISIT_CHECK_DAY_TEMPLATE_PATH: str = str(_RAW_SETTINGS.get("visit_check_day_template_path", "visit_check_day.png"))
VISIT_CHECK_WEEK_TEMPLATE_PATH: str = str(_RAW_SETTINGS.get("visit_check_week_template_path", "visit_check_week.png"))
VISIT_CHECK_MONTH_TEMPLATE_PATH: str = str(_RAW_SETTINGS.get("visit_check_month_template_path", "visit_check_month.png"))
