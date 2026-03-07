from dataclasses import dataclass

from utils import read_setting


@dataclass
class PersonalBroadcastConfig:
    mode: str
    message_text: str
    max_pause_seconds: float
    gender_filter: str
    sent_names_file: str
    exceptions_file: str
    participants_texts: list[str]
    role_keywords: list[str]
    members_scope: tuple[int, int, int, int]
    participants_click_scope: tuple[int, int, int, int]
    message_input_xy: tuple[int, int]
    open_info_image: str
    open_info_scope: tuple[int, int, int, int] | None
    row_send_image: str
    dialog_send_image: str
    dialog_send_scope: tuple[int, int, int, int]
    return_image: str
    return_scope: tuple[int, int, int, int] | None
    max_scroll_steps: int
    line_top_tolerance: int
    processing_mode: str
    position_row_height: int
    position_row_center_offset: int
    position_click_x_offset: int
    position_scroll_amount: int
    position_processed_file: str
    scroll_names_processed_file: str
    scroll_names_scroll_file: str
    target_channel: dict

    @property
    def enabled(self) -> bool:
        return self.mode == "personal_broadcast" and bool(self.message_text.strip())


def _as_tuple4(value, default):
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        except Exception:
            return default
    return default


def _as_optional_tuple4(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        except Exception:
            return None
    return None


def _as_tuple2(value, default):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (int(value[0]), int(value[1]))
        except Exception:
            return default
    return default


def load_personal_broadcast_config() -> PersonalBroadcastConfig:
    mode = str(read_setting("work_mode") or "reader").strip().lower()
    message_text = str(read_setting("personal_broadcast_text") or "")

    try:
        max_pause_seconds = float(read_setting("personal_broadcast_max_pause_seconds") or 8.0)
    except Exception:
        max_pause_seconds = 8.0

    gender_filter = str(read_setting("personal_broadcast_gender_filter") or "all").strip().lower()
    sent_names_file = str(read_setting("personal_broadcast_sent_names_file") or "personal_broadcast_sent_names.txt")

    exceptions_file = str(read_setting("personal_broadcast_exceptions_file") or "personal_broadcast_exceptions.txt")

    participants_texts = read_setting("personal_broadcast_participants_texts") or ["Участники", "Учасники"]
    if not isinstance(participants_texts, list):
        participants_texts = ["Участники", "Учасники"]
    participants_texts = [str(x) for x in participants_texts if str(x).strip()]

    role_keywords = read_setting("personal_broadcast_role_keywords") or []
    if not isinstance(role_keywords, list):
        role_keywords = []
    role_keywords = [str(x).strip().lower() for x in role_keywords if str(x).strip()]

    members_scope = _as_tuple4(
        read_setting("personal_broadcast_members_scope"),
        (330, 230, 450, 620),
    )
    participants_click_scope = _as_tuple4(
        read_setting("personal_broadcast_participants_click_scope"),
        (790, 120, 1120, 780),
    )
    message_input_xy = _as_tuple2(
        read_setting("personal_broadcast_message_input_xy"),
        (560, 770),
    )

    open_info_image = str(read_setting("personal_broadcast_open_info_image"))
    open_info_scope = _as_optional_tuple4(read_setting("personal_broadcast_open_info_scope"))
    row_send_image = str(read_setting("personal_broadcast_row_send_image"))
    dialog_send_image = str(read_setting("personal_broadcast_dialog_send_image"))
    dialog_send_scope = _as_tuple4(
        read_setting("personal_broadcast_dialog_send_scope"),
        (710, 980, 800, 1040),
    )
    return_image = str(read_setting("personal_broadcast_return_image"))
    return_scope = _as_optional_tuple4(read_setting("personal_broadcast_return_scope"))

    try:
        max_scroll_steps = int(read_setting("personal_broadcast_max_scroll_steps") or 120)
    except Exception:
        max_scroll_steps = 120
    try:
        line_top_tolerance = int(read_setting("personal_broadcast_line_top_tolerance") or 14)
    except Exception:
        line_top_tolerance = 14

    processing_mode = str(read_setting("personal_broadcast_processing_mode") or "by_names").strip().lower()
    if processing_mode not in {"by_names", "by_positions", "by_scroll_names"}:
        processing_mode = "by_names"

    try:
        position_row_height = int(read_setting("personal_broadcast_position_row_height") or 50)
    except Exception:
        position_row_height = 50
    position_row_height = max(30, min(position_row_height, 120))

    try:
        position_row_center_offset = int(
            read_setting("personal_broadcast_position_row_center_offset") or (position_row_height // 2)
        )
    except Exception:
        position_row_center_offset = position_row_height // 2
    position_row_center_offset = max(8, min(position_row_center_offset, position_row_height - 4))

    try:
        position_click_x_offset = int(read_setting("personal_broadcast_position_click_x_offset") or 80)
    except Exception:
        position_click_x_offset = 80
    position_click_x_offset = max(20, min(position_click_x_offset, 220))

    try:
        position_scroll_amount = int(read_setting("personal_broadcast_position_scroll_amount") or 410)
    except Exception:
        position_scroll_amount = 410
    position_scroll_amount = max(50, min(abs(position_scroll_amount), 5000))

    position_processed_file = str(
        read_setting("personal_broadcast_position_processed_file")
        or "personal_broadcast_positions_processed.txt"
    )

    scroll_names_processed_file = str(
        read_setting("personal_broadcast_scroll_names_processed_file")
        or "personal_broadcast_scroll_names_processed.txt"
    )
    scroll_names_scroll_file = str(
        read_setting("personal_broadcast_scroll_names_scroll_file")
        or "personal_broadcast_scroll_state.txt"
    )

    target_channel = read_setting("personal_broadcast_channel")
    if not isinstance(target_channel, dict):
        target_channel = {
            "name_viber_channel": "pereviz",
            "name_viber_contact": "DECPEAT",
            "name_viber_contact_lang": "eng",
        }

    required_keys = {"name_viber_channel", "name_viber_contact", "name_viber_contact_lang"}
    if not required_keys.issubset(set(target_channel.keys())):
        target_channel = {
            "name_viber_channel": "pereviz",
            "name_viber_contact": "DECPEAT",
            "name_viber_contact_lang": "eng",
        }

    return PersonalBroadcastConfig(
        mode=mode,
        message_text=message_text,
        max_pause_seconds=max_pause_seconds,
        gender_filter=gender_filter,
        sent_names_file=sent_names_file,
        exceptions_file=exceptions_file,
        participants_texts=participants_texts,
        role_keywords=role_keywords,
        members_scope=members_scope,
        participants_click_scope=participants_click_scope,
        message_input_xy=message_input_xy,
        open_info_image=open_info_image,
        open_info_scope=open_info_scope,
        row_send_image=row_send_image,
        dialog_send_image=dialog_send_image,
        dialog_send_scope=dialog_send_scope,
        return_image=return_image,
        return_scope=return_scope,
        max_scroll_steps=max_scroll_steps,
        line_top_tolerance=line_top_tolerance,
        processing_mode=processing_mode,
        position_row_height=position_row_height,
        position_row_center_offset=position_row_center_offset,
        position_click_x_offset=position_click_x_offset,
        position_scroll_amount=position_scroll_amount,
        position_processed_file=position_processed_file,
        scroll_names_processed_file=scroll_names_processed_file,
        scroll_names_scroll_file=scroll_names_scroll_file,
        target_channel=target_channel,
    )
