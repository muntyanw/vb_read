from dataclasses import dataclass

from utils import read_setting, write_setting


@dataclass
class PersonalBroadcastConfig:
    mode: str
    message_text: str
    max_pause_seconds: float
    gender_filter: str
    sent_names_file: str
    participants_texts: list[str]
    role_keywords: list[str]
    members_scope: tuple[int, int, int, int]
    participants_click_scope: tuple[int, int, int, int]
    message_input_xy: tuple[int, int]
    open_info_image: str
    row_send_image: str
    dialog_send_image: str
    back_to_group_image: str
    max_scroll_steps: int
    line_top_tolerance: int
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


def _as_tuple2(value, default):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (int(value[0]), int(value[1]))
        except Exception:
            return default
    return default


def _ensure_setting(key: str, default_value) -> None:
    if read_setting(key) is None:
        write_setting(key, default_value)


def load_personal_broadcast_config() -> PersonalBroadcastConfig:
    defaults = {
        "work_mode": "reader",
        "personal_broadcast_text": "",
        "personal_broadcast_max_pause_seconds": 8,
        "personal_broadcast_gender_filter": "all",
        "personal_broadcast_sent_names_file": "personal_broadcast_sent_names.txt",
        "personal_broadcast_participants_texts": ["Учасники", "Участники"],
        "personal_broadcast_role_keywords": ["адмін", "admin", "moderator", "модератор", "creator", "создатель"],
        "personal_broadcast_members_scope": [330, 230, 450, 620],
        "personal_broadcast_participants_click_scope": [790, 120, 1120, 780],
        "personal_broadcast_message_input_xy": [560, 770],
        "personal_broadcast_open_info_image": "info.png",
        "personal_broadcast_row_send_image": "send_to_member.png",
        "personal_broadcast_dialog_send_image": "send_message.png",
        "personal_broadcast_back_to_group_image": "group.png",
        "personal_broadcast_max_scroll_steps": 120,
        "personal_broadcast_line_top_tolerance": 14,
        "personal_broadcast_channel": {
            "name_viber_channel": "pereviz",
            "name_viber_contact": "DECPEAT",
            "name_viber_contact_lang": "eng",
        },
    }
    for key, value in defaults.items():
        _ensure_setting(key, value)

    mode = str(read_setting("work_mode") or "reader").strip().lower()
    message_text = str(read_setting("personal_broadcast_text") or "")

    try:
        max_pause_seconds = float(read_setting("personal_broadcast_max_pause_seconds") or 8.0)
    except Exception:
        max_pause_seconds = 8.0

    gender_filter = str(read_setting("personal_broadcast_gender_filter") or "all").strip().lower()
    sent_names_file = str(read_setting("personal_broadcast_sent_names_file") or "personal_broadcast_sent_names.txt")

    participants_texts = read_setting("personal_broadcast_participants_texts") or ["Учасники", "Участники"]
    if not isinstance(participants_texts, list):
        participants_texts = ["Учасники", "Участники"]
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

    open_info_image = str(read_setting("personal_broadcast_open_info_image") or "info.png")
    row_send_image = str(read_setting("personal_broadcast_row_send_image") or "send_to_member.png")
    dialog_send_image = str(read_setting("personal_broadcast_dialog_send_image") or "send_message.png")
    back_to_group_image = str(read_setting("personal_broadcast_back_to_group_image") or "group.png")

    try:
        max_scroll_steps = int(read_setting("personal_broadcast_max_scroll_steps") or 120)
    except Exception:
        max_scroll_steps = 120
    try:
        line_top_tolerance = int(read_setting("personal_broadcast_line_top_tolerance") or 14)
    except Exception:
        line_top_tolerance = 14

    target_channel = read_setting("personal_broadcast_channel")
    if not isinstance(target_channel, dict):
        target_channel = defaults["personal_broadcast_channel"]

    required_keys = {"name_viber_channel", "name_viber_contact", "name_viber_contact_lang"}
    if not required_keys.issubset(set(target_channel.keys())):
        target_channel = defaults["personal_broadcast_channel"]

    return PersonalBroadcastConfig(
        mode=mode,
        message_text=message_text,
        max_pause_seconds=max_pause_seconds,
        gender_filter=gender_filter,
        sent_names_file=sent_names_file,
        participants_texts=participants_texts,
        role_keywords=role_keywords,
        members_scope=members_scope,
        participants_click_scope=participants_click_scope,
        message_input_xy=message_input_xy,
        open_info_image=open_info_image,
        row_send_image=row_send_image,
        dialog_send_image=dialog_send_image,
        back_to_group_image=back_to_group_image,
        max_scroll_steps=max_scroll_steps,
        line_top_tolerance=line_top_tolerance,
        target_channel=target_channel,
    )
