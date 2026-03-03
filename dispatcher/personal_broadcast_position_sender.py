from __future__ import annotations

import random

from core import gui_driver as gd
from dispatcher.personal_broadcast_position_state import PersonalBroadcastPositionRegistry
from dispatcher.personal_broadcast_sender import PersonalBroadcastSender
from log import log_and_print
from recognize_text import perform_ocr_with_positions, preprocess_image
from utils import take_screenshot
from vb_utils import scroll_with_mouse


class _NoOpRegistry:
    def has(self, _name: str) -> bool:
        return False

    def add(self, _name: str) -> None:
        return

    def find_similar(self, _name: str, **_kwargs):
        return None


class PersonalBroadcastPositionSender(PersonalBroadcastSender):
    """Personal broadcast mode that iterates member list by row positions instead of OCR names."""

    def __init__(self, config):
        super().__init__(config)
        self._position_registry = PersonalBroadcastPositionRegistry(config.position_processed_file)
        self._noop_registry = _NoOpRegistry()

    def update_config(self, config) -> None:
        pos_file_changed = self._config.position_processed_file != config.position_processed_file
        super().update_config(config)
        if pos_file_changed:
            self._position_registry = PersonalBroadcastPositionRegistry(config.position_processed_file)
            log_and_print(
                f"[personal_broadcast] position registry file changed: {config.position_processed_file}",
                "debug",
            )

    def _run_channel(self, window, s, channel_name: str) -> bool:
        had_candidates_total = False
        if not self._open_participants(window):
            return False

        resume_scroll_no, resume_position_no = self._position_registry.load_last_processed()
        if resume_scroll_no > 1:
            log_and_print(
                f"[personal_broadcast] position mode resume from scroll={resume_scroll_no} position={resume_position_no}",
                "debug",
            )
            self._restore_scroll_position(window, resume_scroll_no - 1)

        step = max(0, int(resume_scroll_no) - 1)  # zero-based scroll step
        while step < self._config.max_scroll_steps:
            log_and_print(f"[personal_broadcast] position scan step={step+1}/{self._config.max_scroll_steps}", "debug")
            self._dismiss_no_personal_messages_popup(scan_id=f"pos_pre_scan_step{step+1}", context="pre_scan")
            if not self._ensure_participants_list(window):
                return had_candidates_total

            candidates, scan_id = self._read_position_candidates(channel_name=channel_name, step=step)
            if step == max(0, int(resume_scroll_no) - 1) and int(resume_position_no) > 0:
                before = len(candidates)
                candidates = [c for c in candidates if int(c["position_no"]) > int(resume_position_no)]
                skipped = before - len(candidates)
                if skipped > 0:
                    log_and_print(
                        f"[personal_broadcast] position resume skip rows={skipped} at step={step} scan_id={scan_id}",
                        "debug",
                    )

            log_and_print(f"[personal_broadcast] position candidates found={len(candidates)} scan_id={scan_id}", "debug")

            sent_any = False
            raw_count = len(candidates)
            if raw_count > 0:
                had_candidates_total = True
            skip_registry = 0
            send_attempted = 0
            force_scroll_rescan = False

            for candidate in candidates:
                scroll_no = int(candidate["scroll_no"])
                position_no = int(candidate["position_no"])
                marker = f"scroll={scroll_no} position={position_no}"

                if self._position_registry.has(scroll_no, position_no):
                    skip_registry += 1
                    log_and_print(
                        f"[personal_broadcast] position skip already processed: {marker} scan_id={scan_id}",
                        "debug",
                    )
                    continue

                send_attempted += 1
                send_result = self._send_to_member_without_name_registry(window, s, candidate, channel_name, scan_id=scan_id)

                if send_result == "sent":
                    sent_any = True
                    self._position_registry.add(scroll_no, position_no, self._read_current_viber_name())
                    pause = random.uniform(0, max(self._config.max_pause_seconds, 0.0))
                    if pause > 0:
                        gd.pause(pause)
                    if not self._back_to_group(window):
                        return had_candidates_total
                    if not self._open_participants(window):
                        return had_candidates_total
                    self._restore_scroll_position(window, step)
                    break

                if send_result == "skip":
                    # Admin/role row: mark processed to avoid loops on same position.
                    self._position_registry.add(scroll_no, position_no, self._read_current_viber_name())
                    log_and_print(
                        f"[personal_broadcast] position skip admin/role row marker={marker} scan_id={scan_id}",
                        "debug",
                    )
                    continue

                if send_result == "recover":
                    # Do not loop on same row forever.
                    self._position_registry.add(scroll_no, position_no, self._read_current_viber_name())
                    log_and_print(
                        f"[personal_broadcast] recover participants list after marker={marker} scan_id={scan_id}",
                        "warning",
                    )
                    if not self._open_participants(window):
                        log_and_print(
                            "[personal_broadcast] participants reopen failed; scroll and rescan without return-to-group",
                            "warning",
                        )
                        force_scroll_rescan = True
                        break
                    continue

            after_registry = raw_count - skip_registry
            log_and_print(
                f"[personal_broadcast] position candidate pipeline raw={raw_count} "
                f"after_registry={after_registry} send_attempted={send_attempted} scan_id={scan_id}",
                "debug",
            )

            if sent_any:
                log_and_print("[personal_broadcast] message sent, refresh members screenshot", "debug")
                continue

            if force_scroll_rescan:
                log_and_print("[personal_broadcast] force scroll after participants reopen failure", "debug")
            else:
                log_and_print("[personal_broadcast] no candidate sent, scroll down", "debug")
            self._scroll_members_down(window)
            gd.pause(1.5)
            step += 1

        log_and_print(f"[personal_broadcast] no more candidates in {channel_name}", "info")
        self._back_to_group(window)
        return had_candidates_total

    def _send_to_member_without_name_registry(self, window, s, candidate: dict, channel_name: str, scan_id: str | None = None) -> str:
        original_registry = self._registry
        self._registry = self._noop_registry
        try:
            return self._send_to_member(window, s, candidate, channel_name, scan_id=scan_id)
        finally:
            self._registry = original_registry

    def _read_current_viber_name(self) -> str:
        # Best-effort OCR for header in private dialog; not used for matching.
        scope = (350, 50, 830, 125)
        try:
            snap = take_screenshot((scope[0], scope[1], scope[2] - scope[0], scope[3] - scope[1]))
            processed = preprocess_image(snap)
            words = perform_ocr_with_positions(processed, min_conf=35, lang="ukr+eng+rus")
            if not words:
                words = perform_ocr_with_positions(snap, min_conf=35, lang="ukr+eng+rus")
            if not words:
                return ""
            words.sort(key=lambda w: int(w.get("left", 0)))
            tokens = [str(w.get("text", "")).strip() for w in words if str(w.get("text", "")).strip()]
            if not tokens:
                return ""
            name = " ".join(tokens[:6]).strip()
            if len(name) > 80:
                name = name[:80]
            return name
        except Exception:
            return ""


    def _scroll_members_down(self, window, use_mouse_fallback: bool = True) -> None:
        """In positional mode scroll by approximately one visible page of the members list."""
        scope = self._config.members_scope
        cx = int(scope[0] + scope[2] // 2)
        cy = int(scope[1] + scope[3] // 2)
        window.set_focus()
        log_and_print(f"[personal_broadcast] position page-scroll at x={cx}, y={cy}", "debug")
        gd.human_move(cx, cy)
        gd.pause(0.05)

        row_h = max(1, int(self._config.position_row_height))
        visible_rows = max(6, int(scope[3] // row_h))
        # One page down ~= number of visible rows.
        scroll_with_mouse(window, count_scroll=visible_rows, direction="down")

    def _read_position_candidates(self, channel_name: str, step: int) -> tuple[list[dict], str]:
        scope = self._config.members_scope
        img = take_screenshot(scope)
        scan_id, _ = self._save_scan_snapshot(img, channel_name=channel_name, step=step + 1, scope=scope)

        row_h = int(self._config.position_row_height)
        row_center_offset = int(self._config.position_row_center_offset)
        click_x = int(scope[0] + self._config.position_click_x_offset)
        max_y = int(scope[1] + scope[3] - 12)
        min_safe_y = max(int(scope[1] + 120), 200)

        rows_count = max(1, int((scope[3] - row_center_offset) // row_h) + 1)
        candidates: list[dict] = []
        scroll_no = int(step) + 1
        position_no = 0

        for row_idx in range(rows_count):
            y = int(scope[1] + row_center_offset + (row_idx * row_h))
            if y > max_y:
                break
            if step == 0 and row_idx == 0:
                continue
            if y < min_safe_y:
                continue

            position_no += 1
            candidates.append(
                {
                    "name": f"position_{scroll_no}_{position_no}",
                    "x": click_x,
                    "y": y,
                    "row_index": row_idx,
                    "scroll_no": scroll_no,
                    "position_no": position_no,
                }
            )

        self._update_scan_metadata(
            scan_id,
            scan_mode="by_positions",
            position_step=int(step),
            scroll_no=scroll_no,
            row_height=row_h,
            row_center_offset=row_center_offset,
            click_x=click_x,
            candidates_count=len(candidates),
            candidates=[
                {
                    "scroll_no": int(c["scroll_no"]),
                    "position_no": int(c["position_no"]),
                    "x": int(c["x"]),
                    "y": int(c["y"]),
                    "row_index": int(c["row_index"]),
                }
                for c in candidates
            ],
        )
        return candidates, scan_id
