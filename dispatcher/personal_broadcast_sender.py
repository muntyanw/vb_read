import random
import json
import time
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import cv2
import pyautogui as pag
import pyperclip
from pywinauto import keyboard as pwa_keyboard

from core import gui_driver as gd
from dispatcher.dispatch_client import klickViberChannel, window_top_focus
from dispatcher.message_send_logger import log_sent_message
from dispatcher.personal_broadcast_config import PersonalBroadcastConfig
from dispatcher.personal_broadcast_registry import PersonalBroadcastRegistry
from log import log_and_print
from recognize_text import perform_ocr_with_positions, preprocess_image
from utils import take_screenshot, read_setting, showImage
from vb_utils import scroll_with_mouse

def _ui_debug() -> bool:
    return bool(read_setting("debug_methods_mode"))


class PersonalBroadcastSender:
    _NON_MEMBER_WORDS = {
        "СѓС‡Р°СЃС‚РЅРёРєРё",
        "СѓС‡Р°СЃРЅРёРєРё",
        "СѓС‡Р°РєРЅРёРєРё",
        "participants",
        "РІС‹",
        "you",
        "Р·Р°РїСЂРѕСЃРёС‚Рё",
        "Р·Р°РїСЂРѕСЃ",
        "Р·Р°РїР°",
        "РЅРµРёР·РІРµСЃС‚РЅРѕ",
        "--",
    }
    _RIGHT_TEXT_MIN_GAP_PX = 110
    _BUILTIN_ROLE_KEYWORDS = {
        "admin",
        "administrator",
        "superadmin",
        "Р°РґРјРёРЅ",
        "Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ",
        "Р°РґРјС–РЅС–СЃС‚СЂР°С‚РѕСЂ",
        "СЃСѓРїРµСЂР°РґРјРёРЅ",
        "СЃСѓРїРµСЂР°РґРјС–РЅ",
    }
    _ROLE_MARKERS = (
        "admin",
        "administrator",
        "Р°РґРјРёРЅ",
        "Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ",
        "Р°РґРјС–РЅС–СЃС‚СЂР°С‚РѕСЂ",
        "СЃСѓРїРµСЂР°РґРјРёРЅ",
        "СЃСѓРїРµСЂР°РґРјС–РЅ",
    )

    _INFO_STATE_EPS = 0.015
    _NAME_MAX_X_RATIO = 0.62

    def __init__(self, config: PersonalBroadcastConfig):
        self._config = config
        self._registry = PersonalBroadcastRegistry(config.sent_names_file)
        log_and_print("[personal_broadcast] initialized", "info")

    def update_config(self, config: PersonalBroadcastConfig) -> None:
        sent_file_changed = self._config.sent_names_file != config.sent_names_file
        self._config = config
        log_and_print("[personal_broadcast] config updated", "debug")
        if sent_file_changed:
            self._registry = PersonalBroadcastRegistry(config.sent_names_file)
            log_and_print(f"[personal_broadcast] registry file changed: {config.sent_names_file}", "debug")

    def run_once(self, window, s) -> None:
        if not self._config.enabled:
            log_and_print("[personal_broadcast] skipped: disabled by config", "debug")
            return

        channel = self._config.target_channel
        log_and_print(f"[personal_broadcast] start channel={channel.get('name_viber_channel')}", "debug")
        window_top_focus(window)
        if not klickViberChannel("image", window, False, channel):
            log_and_print(
                f"[personal_broadcast] channel open failed: {channel.get('name_viber_channel')}",
                "error",
            )
            return
        self._run_channel(window, s, channel.get("name_viber_channel", "unknown"))

    def _run_channel(self, window, s, channel_name: str) -> None:
        if not self._open_participants(window):
            return

        for step in range(self._config.max_scroll_steps):
            log_and_print(f"[personal_broadcast] scan step={step+1}/{self._config.max_scroll_steps}", "debug")
            if not self._ensure_participants_list(window):
                return
            candidates, scan_id = self._read_candidates_from_scope(channel_name=channel_name, step=step + 1)
            if step == 0 and candidates:
                first_candidate = min(candidates, key=lambda c: (c["y"], c["x"]))
                candidates = [c for c in candidates if c is not first_candidate]
                log_and_print(
                    f"[personal_broadcast] first pass skip top candidate '{first_candidate['name']}' "
                    f"at ({first_candidate['x']},{first_candidate['y']})",
                    "debug",
                )
            log_and_print(f"[personal_broadcast] candidates found={len(candidates)} scan_id={scan_id}", "debug")
            sent_any = False
            raw_count = len(candidates)
            skip_registry = 0
            skip_gender = 0
            send_attempted = 0

            for candidate in candidates:
                name = candidate["name"]
                if self._registry.has(name):
                    skip_registry += 1
                    log_and_print(f"[personal_broadcast] skip already sent: {name} scan_id={scan_id}", "debug")
                    continue
                if not self._gender_matches(name):
                    skip_gender += 1
                    log_and_print(f"[personal_broadcast] skip gender filter: {name} scan_id={scan_id}", "debug")
                    continue

                send_attempted += 1
                if self._send_to_member(window, s, candidate, channel_name, scan_id=scan_id):
                    self._registry.add(name)
                    sent_any = True
                    pause = random.uniform(0, max(self._config.max_pause_seconds, 0.0))
                    time.sleep(pause)
                    if not self._back_to_group(window):
                        return
                    if not self._open_participants(window):
                        return

            after_registry = raw_count - skip_registry
            after_gender = after_registry - skip_gender
            log_and_print(
                f"[personal_broadcast] candidate pipeline raw={raw_count} "
                f"after_registry={after_registry} after_gender={after_gender} "
                f"send_attempted={send_attempted} scan_id={scan_id}",
                "debug",
            )

            if sent_any:
                log_and_print("[personal_broadcast] processed current scan, scroll down", "debug")
            else:
                log_and_print("[personal_broadcast] no candidate sent, scroll down", "debug")
            scroll_with_mouse(window, count_scroll=2, direction="down")
            gd.pause(0.3)

        log_and_print(f"[personal_broadcast] no more candidates in {channel_name}", "info")
        self._back_to_group(window)

    def _open_participants(self, window) -> bool:
        for attempt in range(1, 4):
            window.set_focus()
            state, score_unselect, score_info = self._detect_info_icon_state()
            log_and_print(
                f"[personal_broadcast] info state attempt={attempt}/3 "
                f"state={state} score_unselect={score_unselect:.3f} score_info={score_info:.3f}",
                "debug",
            )

            if state != "open":
                log_and_print(
                    f"[personal_broadcast] click info image={self._config.open_info_image}, "
                    f"scope={self._config.open_info_scope} attempt={attempt}/3",
                    "debug",
                )
                gd.click_image(
                    self._config.open_info_image,
                    scope=self._config.open_info_scope,
                    confidence=0.8,
                    count_click=1,
                    multiscale=True,
                    is_debug=_ui_debug(),
                )
                gd.pause(0.6)
            else:
                log_and_print("[personal_broadcast] info already open (info.png dominates), skip info click", "debug")

            if self._click_participants_text():
                gd.pause(2.0)
                return True

            log_and_print(
                f"[personal_broadcast] participants text not found, retry open info attempt={attempt}/3",
                "warning",
            )
            gd.pause(0.8)

        log_and_print("[personal_broadcast] cannot click participants", "error")
        return False

    def _click_participants_text(self) -> bool:
        log_and_print(
            f"[personal_broadcast] click participants text in scope={self._config.participants_click_scope}",
            "debug",
        )
        gd.pause(1.0)
        return bool(
            gd.click_text(
                self._config.participants_texts,
                count_attempt_find=2,
                pause_attempt=1,
                lang="ukr",
                scope=self._config.participants_click_scope,
                threshold=0.6,
                is_debug=_ui_debug(),
                count_click=1,
            )
        )

    def _detect_info_icon_state(self) -> tuple[str, float, float]:
        """
        Returns (state, score_unselect, score_info):
        - state=open: info.png is more similar (info panel likely already opened)
        - state=closed: info_unselect.png is more similar
        - state=unknown: similarity is too close or templates not available
        """
        scope = self._config.open_info_scope
        if scope is None:
            return "unknown", -1.0, -1.0

        score_unselect = self._template_score_in_scope(self._config.open_info_image, scope)
        score_info = self._template_score_in_scope("info.png", scope)

        if score_unselect < 0 and score_info < 0:
            return "unknown", score_unselect, score_info
        if score_info > score_unselect + self._INFO_STATE_EPS:
            return "open", score_unselect, score_info
        if score_unselect > score_info + self._INFO_STATE_EPS:
            return "closed", score_unselect, score_info
        return "unknown", score_unselect, score_info

    def _template_score_in_scope(self, image_name: str, scope: tuple[int, int, int, int]) -> float:
        path = self._resolve_template_path(image_name)
        if path is None:
            return -1.0

        left, bottom, right, top = [int(v) for v in scope]
        width = max(1, right - left)
        height = max(1, top - bottom)
        snap_rgb = take_screenshot((left, bottom, width, height))
        snap_bgr = cv2.cvtColor(snap_rgb, cv2.COLOR_RGB2BGR)

        tpl = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if tpl is None:
            return -1.0

        mask = None
        if tpl.ndim == 3 and tpl.shape[2] == 4:
            alpha = tpl[:, :, 3]
            _, mask = cv2.threshold(alpha, 0, 255, cv2.THRESH_BINARY)
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_BGRA2BGR)
        elif tpl.ndim == 3:
            tpl_bgr = tpl
        else:
            tpl_bgr = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)

        ih, iw = snap_bgr.shape[:2]
        th, tw = tpl_bgr.shape[:2]
        if th < 1 or tw < 1 or th > ih or tw > iw:
            return -1.0

        if mask is not None:
            res = cv2.matchTemplate(snap_bgr, tpl_bgr, cv2.TM_CCORR_NORMED, mask=mask)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return float(max_val)

        img_gray = cv2.cvtColor(snap_bgr, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return float(max_val)

    @staticmethod
    def _resolve_template_path(image_name: str) -> Path | None:
        p = Path(str(image_name))
        candidates = [
            p,
            Path.cwd() / p,
            Path.cwd() / "images" / p.name,
            Path(__file__).resolve().parents[1] / "images" / p.name,
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _ensure_participants_list(self, window) -> bool:
        window.set_focus()
        clicked = gd.click_text(
            self._config.participants_texts,
            count_attempt_find=1,
            pause_attempt=0.2,
            lang="ukr",
            scope=self._config.participants_click_scope,
            threshold=0.6,
            is_debug=_ui_debug(),
            count_click=1,
        )
        if clicked:
            log_and_print("[personal_broadcast] participants label visible; open participants list", "debug")
            gd.pause(0.6)
        return True

    def _scan_meta_path(self, scan_id: str) -> Path:
        out_dir = Path(__file__).resolve().parents[1] / "temp_log"
        return out_dir / f"{scan_id}.json"

    def _update_scan_metadata(self, scan_id: str, **fields) -> None:
        try:
            meta_path = self._scan_meta_path(scan_id)
            if meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            else:
                data = {"scan_id": scan_id}
            for k, v in fields.items():
                data[k] = v
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log_and_print(f"[personal_broadcast] metadata update failed scan_id={scan_id}: {e}", "error")

    def _save_scan_snapshot(self, image_np, channel_name: str, step: int, scope: tuple[int, int, int, int]) -> tuple[str, str | None]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_channel = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(channel_name or "unknown"))
        scan_id = f"pb_{safe_channel}_step{int(step):03d}_{ts}"
        try:
            out_dir = Path(__file__).resolve().parents[1] / "temp_log"
            out_dir.mkdir(parents=True, exist_ok=True)
            image_path = out_dir / f"{scan_id}.png"
            meta_path = out_dir / f"{scan_id}.json"

            # take_screenshot returns RGB; cv2.imwrite expects BGR
            image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(image_path), image_bgr)

            meta = {
                "scan_id": scan_id,
                "channel": str(channel_name or "unknown"),
                "step": int(step),
                "scope": [int(scope[0]), int(scope[1]), int(scope[2]), int(scope[3])],
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "image": str(image_path.resolve()),
                "cwd": str(Path.cwd()),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            log_and_print(f"[personal_broadcast] snapshot saved scan_id={scan_id} image={image_path}", "debug")
            return scan_id, str(image_path)
        except Exception as e:
            log_and_print(f"[personal_broadcast] snapshot save failed scan_id={scan_id}: {e}", "error")
            return scan_id, None

    def _read_candidates_from_scope(self, channel_name: str, step: int) -> tuple[list[dict], str]:
        skip_stats = {"role_line": 0, "role_label": 0, "no_avatar": 0, "bad_token": 0, "short_name": 0}
        scope = self._config.members_scope
        log_and_print(f"[personal_broadcast] OCR scope={scope}", "debug")
        gd.pause(1.0)
        img = take_screenshot(scope)
        scan_id, _snapshot_path = self._save_scan_snapshot(img, channel_name=channel_name, step=step, scope=scope)
        processed = preprocess_image(img)
        circles = self._detect_avatar_circles(img)
        log_and_print(f"[personal_broadcast] avatar circles={len(circles)}", "debug")
        if _ui_debug():
            # quick preview for debug mode without stopping the loop
            showImage(img, 0, title=f"[personal_broadcast] OCR raw scope={scope}")
            showImage(processed, 0, title=f"[personal_broadcast] OCR processed scope={scope}")
        words = perform_ocr_with_positions(processed, min_conf=35, lang="ukr+eng+rus")
        raw_words = perform_ocr_with_positions(img, min_conf=35, lang="ukr+eng+rus")
        if raw_words:
            seen = {(w["text"], int(w["left"]), int(w["top"])) for w in words}
            added = 0
            for w in raw_words:
                key = (w["text"], int(w["left"]), int(w["top"]))
                if key in seen:
                    continue
                words.append(w)
                seen.add(key)
                added += 1
            log_and_print(
                f"[personal_broadcast] OCR merged raw+processed: raw={len(raw_words)} "
                f"added={added}, total={len(words)} scan_id={scan_id}",
                "debug",
            )
        if not words:
            self._update_scan_metadata(
                scan_id,
                ocr_words_count=0,
                avatar_circles_count=len(circles),
                skip_stats=skip_stats,
                candidates_count=0,
                candidates=[],
            )
            log_and_print(f"[personal_broadcast] OCR returned 0 words scan_id={scan_id}", "debug")
            return [], scan_id

        lines = defaultdict(list)
        for w in words:
            key = int(w["top"] / max(self._config.line_top_tolerance, 1))
            lines[key].append(w)

        candidates = []
        for _, line_words in lines.items():
            line_words.sort(key=lambda x: x["left"])
            line_text = " ".join(str(w["text"]).strip() for w in line_words if str(w["text"]).strip())
            if not line_text:
                continue
            low = line_text.lower()
            role_keywords = set(self._config.role_keywords) | self._BUILTIN_ROLE_KEYWORDS
            if any(role in low for role in role_keywords):
                skip_stats["role_line"] += 1
                log_and_print(f"[personal_broadcast] role detected, skip line='{line_text}' scan_id={scan_id}", "debug")
                continue

            chosen = None
            for w in line_words:
                token = str(w["text"]).strip()
                normalized = self._normalize_name(token)
                if self._is_member_name_token(normalized):
                    chosen = w
                    break
            if not chosen:
                skip_stats["bad_token"] += 1
                continue

            raw_name = str(chosen["text"]).strip()
            name = self._normalize_name(raw_name)
            if len(name) < 2:
                skip_stats["short_name"] += 1
                continue

            chosen_left = int(chosen["left"])
            chosen_top = int(chosen["top"])
            chosen_w = int(chosen["width"])
            chosen_h = int(chosen["height"])
            chosen_right = chosen_left + chosen_w
            chosen_bottom = chosen_top + chosen_h
            if self._row_has_role_label(words, chosen_left, chosen_top, chosen_w, chosen_h):
                skip_stats["role_label"] += 1
                log_and_print(
                    f"[personal_broadcast] skip role label on row for name='{name}' line='{line_text}' scan_id={scan_id}",
                    "debug",
                )
                continue
            # Right-side OCR noise is common; keep candidate if role checks passed.

            local_center_x = int(chosen["left"]) + int(chosen["width"]) // 2
            local_center_y = int(chosen["top"]) + int(chosen["height"]) // 2
            if local_center_x > int(scope[2] * self._NAME_MAX_X_RATIO):
                skip_stats["bad_token"] += 1
                log_and_print(
                    f"[personal_broadcast] skip right-column token name='{name}' x={local_center_x} "
                    f"scope_w={scope[2]} scan_id={scan_id}",
                    "debug",
                )
                continue
            if not self._has_avatar_left(local_center_x, local_center_y, circles):
                skip_stats["no_avatar"] += 1
                log_and_print(f"[personal_broadcast] skip no avatar near name='{name}' line='{line_text}' scan_id={scan_id}", "debug")
                continue

            center_x = scope[0] + local_center_x
            center_y = scope[1] + local_center_y
            candidates.append({"name": name, "x": center_x, "y": center_y})

        unique = {}
        for c in candidates:
            key = c["name"].lower()
            if key not in unique:
                unique[key] = c
        result = list(unique.values())
        self._update_scan_metadata(
            scan_id,
            ocr_words_count=len(words),
            avatar_circles_count=len(circles),
            skip_stats=skip_stats,
            candidates_count=len(result),
            candidates=[{"name": c["name"], "x": int(c["x"]), "y": int(c["y"])} for c in result[:80]],
        )
        if result:
            preview = ", ".join(f"{c['name']}@({c['x']},{c['y']})" for c in result[:15])
            log_and_print(f"[personal_broadcast] candidates: {preview} scan_id={scan_id}", "debug")
        else:
            ocr_preview = [str(w.get("text", "")).strip() for w in words if str(w.get("text", "")).strip()]
            if ocr_preview:
                log_and_print(
                    f"[personal_broadcast] no candidates from OCR words: {', '.join(ocr_preview[:25])} scan_id={scan_id}",
                    "debug",
                )
            else:
                log_and_print(f"[personal_broadcast] no candidates: OCR words are empty after filtering scan_id={scan_id}", "debug")
        return result, scan_id

    @classmethod
    def _is_member_name_token(cls, token: str) -> bool:
        if len(token) < 2:
            return False
        low = token.lower()
        if cls._looks_like_role_word(low):
            return False
        if low.startswith(("СѓС‡Р°СЃРЅ", "СѓС‡Р°СЃС‚РЅ", "СѓС‡Р°РєРЅ", "Р·Р°РїСЂРѕСЃ", "Р·Р°РїР°")):
            return False
        if low in cls._NON_MEMBER_WORDS:
            return False
        if not any(ch.isalpha() for ch in token):
            return False
        return True

    @staticmethod
    def _looks_like_role_word(low: str) -> bool:
        low = (low or "").lower()
        if not low:
            return False
        role_parts = (
            "admin",
            "dmin",
            "superadmin",
            "админ",
            "дмин",
            "министратор",
            "дминистратор",
            "суперадмин",
        )
        return any(p in low for p in role_parts)
    @classmethod
    def _contains_role_marker(cls, text: str) -> bool:
        low = str(text or "").strip().lower()
        if not low:
            return False
        return any(marker in low for marker in cls._ROLE_MARKERS)

    def _row_has_role_label(
        self,
        words: list[dict],
        chosen_left: int,
        chosen_top: int,
        chosen_w: int,
        chosen_h: int,
    ) -> bool:
        chosen_right = chosen_left + chosen_w
        chosen_bottom = chosen_top + chosen_h
        for w in words:
            text = str(w.get("text", "")).strip()
            if not text:
                continue
            if not self._contains_role_marker(text):
                continue
            w_left = int(w["left"])
            if w_left < chosen_right + 40:
                continue
            w_top = int(w["top"])
            w_bottom = w_top + int(w["height"])
            overlap = max(0, min(chosen_bottom, w_bottom) - max(chosen_top, w_top))
            if overlap >= max(4, min(chosen_h, int(w["height"])) // 3):
                return True
        return False

    @staticmethod
    def _detect_avatar_circles(image_np) -> list[tuple[int, int, int]]:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=26,
            param1=80,
            param2=16,
            minRadius=9,
            maxRadius=34,
        )
        if circles is None:
            return []
        return [(int(c[0]), int(c[1]), int(c[2])) for c in circles[0]]

    @staticmethod
    def _has_avatar_left(name_x: int, name_y: int, circles: list[tuple[int, int, int]]) -> bool:
        for cx, cy, _ in circles:
            if cx >= name_x:
                continue
            dx = name_x - cx
            dy = abs(name_y - cy)
            if 10 <= dx <= 180 and dy <= 45:
                return True
        return False

    def _send_to_member(self, window, s, candidate: dict, channel_name: str, scan_id: str | None = None) -> bool:
        name = candidate["name"]
        x = candidate["x"]
        y = candidate["y"]
        sid = scan_id or "na"

        if self._has_role_in_member_row(y, scan_id=sid):
            log_and_print(f"[personal_broadcast] skip role account before send: {name} scan_id={sid}", "debug")
            return False

        log_and_print(f"[personal_broadcast] sending to {name} scan_id={sid}", "info")
        log_and_print(f"[personal_broadcast] click member name='{name}' at x={x}, y={y} scan_id={sid}", "debug")

        window.set_focus()
        gd.click(x, y)
        gd.pause(0.2)

        member_scope = self._config.members_scope
        send_scope = (
            member_scope[0] + member_scope[2] - 130,
            max(member_scope[1], y - 30),
            member_scope[0] + member_scope[2],
            min(member_scope[1] + member_scope[3], y + 30),
        )

        if not gd.click_image(
            self._config.row_send_image,
            scope=send_scope,
            confidence=0.95,
            count_click=1,
            multiscale=False,
            is_debug=_ui_debug(),
        ):
            log_and_print(f"[personal_broadcast] row send icon not found for {name} scan_id={sid}", "error")
            return False
        log_and_print(f"[personal_broadcast] row send clicked, scope={send_scope} scan_id={sid}", "debug")

        window.set_focus()
        if not self._insert_message_text(window):
            log_and_print(f"[personal_broadcast] cannot insert message text for {name} scan_id={sid}", "error")
            return False

        dialog_send_scope = self._config.dialog_send_scope
        mic_pos = gd.find_image(
            "microfon.png",
            scope=dialog_send_scope,
            timeout=0.2,
            confidence=0.75,
            multiscale=True,
            is_debug=_ui_debug(),
        )
        if mic_pos:
            log_and_print(
                f"[personal_broadcast] microphone is visible at {mic_pos}; "
                f"text likely not inserted, skip send scan_id={sid}",
                "error",
            )
            return False

        if not gd.click_image(
            self._config.dialog_send_image,
            scope=dialog_send_scope,
            confidence=0.7,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
        ):
            log_and_print(f"[personal_broadcast] dialog send icon not found for {name} scan_id={sid}", "error")
            return False
        log_and_print(f"[personal_broadcast] dialog send clicked, scope={dialog_send_scope} scan_id={sid}", "debug")

        log_sent_message(channel_name=channel_name, text=self._config.message_text, source=f"personal:{name}")
        return True

    def _has_role_in_member_row(self, member_center_y: int, scan_id: str | None = None) -> bool:
        scope = self._config.members_scope
        left = scope[0] + int(scope[2] * 0.55)
        top = max(scope[1], int(member_center_y) - 28)
        right = scope[0] + scope[2]
        bottom = min(scope[1] + scope[3], int(member_center_y) + 28)
        if right - left < 20 or bottom - top < 10:
            return False

        # take_screenshot expects (x, y, width, height)
        row_scope = (left, top, right - left, bottom - top)
        img = take_screenshot(row_scope)
        processed = preprocess_image(img)
        words = perform_ocr_with_positions(processed, min_conf=30, lang="ukr+eng+rus")
        if not words:
            words = perform_ocr_with_positions(img, min_conf=35, lang="ukr+eng+rus")
        if not words:
            return False
        row_text = " ".join(str(w.get("text", "")).strip() for w in words if str(w.get("text", "")).strip())
        if self._contains_role_marker(row_text):
            sid = scan_id or "na"
            log_and_print(f"[personal_broadcast] role marker in right column: '{row_text}' scan_id={sid}", "debug")
            return True
        return False

    def _insert_message_text(self, window) -> bool:
        text = self._config.message_text
        if not text:
            log_and_print("[personal_broadcast] message text is empty", "error")
            return False

        x, y = self._config.message_input_xy
        last_error = None
        for attempt in range(1, 4):
            try:
                window.set_focus()
                gd.click(x, y)
                gd.pause(0.08)
                gd.click(x, y)
                log_and_print(
                    f"[personal_broadcast] double-click message input at {(x, y)} attempt={attempt}/3",
                    "debug",
                )
                gd.pause(0.25)

                # Try to focus and clear current text before paste.
                pag.hotkey("ctrl", "a")
                gd.pause(0.05)
                pag.press("backspace")
                gd.pause(0.05)

                # Strategy 1: Ctrl+V
                pyperclip.copy(text)
                pag.hotkey("ctrl", "v")
                gd.pause(0.2)
                if self._input_contains_text(text):
                    log_and_print(f"[personal_broadcast] message paste done via ctrl+v attempt={attempt}/3", "debug")
                    return True

                # Strategy 2: Shift+Insert
                pyperclip.copy(text)
                pag.hotkey("shift", "insert")
                gd.pause(0.2)
                if self._input_contains_text(text):
                    log_and_print(f"[personal_broadcast] message paste done via shift+insert attempt={attempt}/3", "debug")
                    return True
                # Strategy 3: pywinauto Ctrl+V fallback
                pyperclip.copy(text)
                pwa_keyboard.send_keys("^v")
                gd.pause(0.2)
                if self._input_contains_text(text):
                    log_and_print(f"[personal_broadcast] message paste done via pywinauto ctrl+v attempt={attempt}/3", "debug")
                    return True
                # No direct typing fallback here: it can duplicate text when paste already worked.


                log_and_print(
                    f"[personal_broadcast] paste verification failed attempt={attempt}/3",
                    "warning",
                )
                continue

            except Exception as exc:
                last_error = exc
                log_and_print(f"[personal_broadcast] paste attempt={attempt}/3 failed: {exc}", "error")
                gd.pause(0.2)

        if last_error:
            log_and_print(f"[personal_broadcast] paste failed after retries: {last_error}", "error")
        return False

    @staticmethod
    def _input_contains_text(expected: str) -> bool:
        if not expected:
            return False
        try:
            old_clip = pyperclip.paste()
        except Exception:
            old_clip = None

        try:
            marker = "__pb_clip_marker__"
            pyperclip.copy(marker)
            pag.hotkey("ctrl", "a")
            gd.pause(0.04)
            pag.hotkey("ctrl", "c")
            gd.pause(0.08)
            current = (pyperclip.paste() or "").strip().lower()
            target = expected.strip().lower()
            # If marker remains in clipboard, copy-from-input did not happen.
            if not current or current == marker:
                return False
            return target in current or current in target
        except Exception:
            return False
        finally:
            if old_clip is not None:
                try:
                    pyperclip.copy(old_clip)
                except Exception:
                    pass

    def _back_to_group(self, window) -> bool:
        window.set_focus()
        log_and_print(
            f"[personal_broadcast] click return image={self._config.return_image}, scope={self._config.return_scope}",
            "debug",
        )
        if not gd.click_image(
            self._config.return_image,
            scope=self._config.return_scope,
            confidence=0.7,
            count_click=1,
            multiscale=True,
            is_debug=_ui_debug(),
        ):
            log_and_print("[personal_broadcast] cannot return to group", "error")
            return False
        gd.pause(0.3)
        return True

    def _gender_matches(self, name: str) -> bool:
        filter_value = self._config.gender_filter
        if filter_value == "all":
            return True
        is_female = self._is_female_name(name)
        if filter_value == "female":
            return is_female
        if filter_value == "male":
            return not is_female
        return True

    @staticmethod
    def _is_female_name(name: str) -> bool:
        n = name.strip().lower()
        if not n:
            return False
        # Heuristic for ukr/rus/eng OCR names:
        # female names often end with: Р°/СЏ (cyrillic) or a (latin).
        return n[-1] in {"Р°", "СЏ", "a"}

    @staticmethod
    def _normalize_name(name: str) -> str:
        allowed = []
        for ch in name:
            if ch.isalpha() or ch in {"-", "'"}:
                allowed.append(ch)
        return "".join(allowed).strip()





