from __future__ import annotations

import random
import shutil
from pathlib import Path

from core import gui_driver as gd
from dispatcher.personal_broadcast_registry import PersonalBroadcastRegistry
from dispatcher.personal_broadcast_scroll_names_state import PersonalBroadcastScrollNamesState
from dispatcher.personal_broadcast_sender import PersonalBroadcastSender
from log import log_and_print


class PersonalBroadcastScrollNamesSender(PersonalBroadcastSender):
    """
    Personal broadcast mode: process users by names inside current scroll page,
    persist current scroll number, and keep per-scroll processed names in a separate file.
    """

    def __init__(self, config):
        super().__init__(config)
        self._scroll_state = PersonalBroadcastScrollNamesState(config.scroll_names_scroll_file)
        self._registry = PersonalBroadcastRegistry(config.scroll_names_processed_file)
        self._history_path = Path(config.scroll_names_history_file)

    def update_config(self, config) -> None:
        names_file_changed = self._config.scroll_names_processed_file != config.scroll_names_processed_file
        scroll_file_changed = self._config.scroll_names_scroll_file != config.scroll_names_scroll_file
        sent_file_changed = self._config.sent_names_file != config.sent_names_file
        super().update_config(config)

        if names_file_changed:
            self._reload_registries()
            log_and_print(
                f"[personal_broadcast] scroll-names registry file changed: {config.scroll_names_processed_file}",
                "debug",
            )

        if scroll_file_changed:
            self._scroll_state = PersonalBroadcastScrollNamesState(config.scroll_names_scroll_file)
            log_and_print(
                f"[personal_broadcast] scroll-names state file changed: {config.scroll_names_scroll_file}",
                "debug",
            )

        if sent_file_changed:
                log_and_print(
                f"[personal_broadcast] scroll-names global registry file changed: {config.sent_names_file}",
                "debug",
            )

    def _reset_processed_names_for_scroll(self) -> None:
        path = Path(self._config.scroll_names_processed_file)
        try:
            path.write_text("", encoding="utf-8")
        except Exception as exc:
            log_and_print(f"[personal_broadcast] cannot clear scroll-names file: {exc}", "error")
        self._registry = PersonalBroadcastRegistry(self._config.scroll_names_processed_file)

    def _reload_registries(self) -> None:
        self._registry = PersonalBroadcastRegistry(self._config.scroll_names_processed_file)
        self._history_path = Path(self._config.scroll_names_history_file)

    def _append_history_name(self, name: str) -> None:
        raw = str(name or "").strip()
        if not raw:
            return
        ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with self._history_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{ts} | {raw}\n")
        except Exception as exc:
            log_and_print(f"[personal_broadcast] cannot append history file: {exc}", "error")

    def _clear_current_processed_names(self) -> None:
        path = Path(self._config.scroll_names_processed_file)
        try:
            path.write_text("", encoding="utf-8")
        except Exception as exc:
            log_and_print(f"[personal_broadcast] cannot clear scroll-names file: {exc}", "error")
        self._reload_registries()

    def _maybe_clear_current_processed_after_scroll_advance(self, new_scroll_no: int) -> None:
        keep_for = max(1, int(self._config.scroll_names_reset_every))
        # Clear once per configured number of scroll pages.
        if keep_for == 1:
            self._clear_current_processed_names()
            return
        if new_scroll_no > 1 and ((new_scroll_no - 1) % keep_for == 0):
            self._clear_current_processed_names()

    def _ensure_participants_panel(self, window) -> bool:
        """Ensure we are in participants list before page scroll / scan progression."""
        if self._ensure_participants_list(window):
            return True
        log_and_print("[personal_broadcast] participants panel missing, reopen", "warning")
        if not self._open_participants(window):
            return False
        return self._ensure_participants_list(window)

    def _restore_scroll_position(self, window, steps: int) -> None:
        """Restore in scroll-names mode without UIA fallback that can hit left messages pane."""
        if steps <= 0:
            return
        self._handle_same_one_before_scroll(window)

        scope = self._config.members_scope
        cx = int(scope[0] + scope[2] // 2)
        cy = int(scope[1] + scope[3] // 2)

        window.set_focus()
        gd.human_move(cx, cy)
        gd.pause(0.03)
        gd.click(cx, cy)

        log_and_print(f"[personal_broadcast] scroll-names restore steps={steps}", "debug")
        for _ in range(int(steps)):
            self._scroll_members_down(window, use_mouse_fallback=False)

    @staticmethod
    def _is_same_row_position(a: dict, b: tuple[int, int], max_dx: int = 95, max_dy: int = 22) -> bool:
        try:
            ax = int(a.get("x", 0))
            ay = int(a.get("y", 0))
            bx = int(b[0])
            by = int(b[1])
        except Exception:
            return False
        return abs(ax - bx) <= max_dx and abs(ay - by) <= max_dy

    def _run_channel(self, window, s, channel_name: str) -> bool:
        had_candidates_total = False
        # Reload from files on every channel run to survive restarts/reloads.
        self._reload_registries()
        self._scroll_state = PersonalBroadcastScrollNamesState(self._config.scroll_names_scroll_file)

        if not self._open_participants(window):
            return False

        scroll_no = self._scroll_state.load_scroll_no()
        scroll_no = max(1, int(scroll_no))
        if scroll_no > 1:
            log_and_print(
                f"[personal_broadcast] scroll-names resume from scroll={scroll_no}",
                "debug",
            )
            self._restore_scroll_position(window, scroll_no - 1)

        step = scroll_no - 1
        blocked_candidates_on_step: set[str] = set()
        blocked_candidates_step_no = step
        processed_positions_on_step: list[tuple[int, int]] = []
        processed_positions_step_no = step
        while step < self._config.max_scroll_steps:
            current_scroll_no = step + 1
            if blocked_candidates_step_no != step:
                blocked_candidates_on_step.clear()
                blocked_candidates_step_no = step
            if processed_positions_step_no != step:
                processed_positions_on_step.clear()
                processed_positions_step_no = step
            log_and_print(
                f"[personal_broadcast] scroll-names scan step={current_scroll_no}/{self._config.max_scroll_steps}",
                "debug",
            )
            self._dismiss_no_personal_messages_popup(scan_id=f"sn_pre_scan_step{current_scroll_no}", context="pre_scan")
            if not self._ensure_participants_list(window):
                return had_candidates_total

            candidates, scan_id = self._read_candidates_from_scope(channel_name=channel_name, step=current_scroll_no)
            if candidates and step == 0:
                first_candidate = min(candidates, key=lambda c: (c["y"], c["x"]))
                top_y = int(first_candidate["y"])
                top_row_window = 14
                filtered = [c for c in candidates if abs(int(c["y"]) - top_y) > top_row_window]
                skipped_top = len(candidates) - len(filtered)
                candidates = filtered
                if skipped_top > 0:
                    log_and_print(
                        f"[personal_broadcast] skip top row around y={top_y}, skipped={skipped_top}",
                        "debug",
                    )

            # In scroll-names mode process from very first visible candidate (no forced top-row skip).
            if step == 0:
                before = len(candidates)
                candidates = self._dedupe_candidates_by_position(candidates)
                removed = before - len(candidates)
                if removed > 0:
                    log_and_print(
                        f"[personal_broadcast] dedupe by position removed={removed} scan_id={scan_id}",
                        "debug",
                    )

            candidates.sort(key=lambda c: (int(c.get("y", 0)), int(c.get("x", 0))))
            log_and_print(f"[personal_broadcast] candidates found={len(candidates)} scan_id={scan_id}", "debug")

            sent_any = False
            raw_count = len(candidates)
            if raw_count > 0:
                had_candidates_total = True
            skip_registry = 0
            skip_gender = 0
            send_attempted = 0
            force_rescan_same_step = False

            for candidate in candidates:
                name = candidate["name"]
                if self._registry.has(name):
                    skip_registry += 1
                    sim = self._registry.find_similar(name, min_ratio=0.70, max_len_diff=24)
                    if sim:
                        log_and_print(
                            f"[personal_broadcast] skip already sent (current scroll): {name} ~ {sim[0]} ({sim[1]:.2f}) scan_id={scan_id}",
                            "debug",
                        )
                    else:
                        log_and_print(
                            f"[personal_broadcast] skip already sent (current scroll): {name} (exact/normalized match) scan_id={scan_id}",
                            "debug",
                        )
                    continue
                if name in blocked_candidates_on_step:
                    skip_registry += 1
                    log_and_print(f"[personal_broadcast] skip failed candidate on this step: {name} scan_id={scan_id}", "debug")
                    continue

                if any(self._is_same_row_position(candidate, pos) for pos in processed_positions_on_step):
                    skip_registry += 1
                    log_and_print(
                        f"[personal_broadcast] skip already processed row-position name={name} x={candidate.get('x')} y={candidate.get('y')} scan_id={scan_id}",
                        "debug",
                    )
                    continue

                if not self._gender_matches(name):
                    skip_gender += 1
                    log_and_print(f"[personal_broadcast] skip gender filter: {name} scan_id={scan_id}", "debug")
                    continue

                if self._is_participants_label(name):
                    skip_registry += 1
                    log_and_print(
                        f"[personal_broadcast] skip participants label: {name} scan_id={scan_id}",
                        "debug",
                    )
                    continue

                send_attempted += 1
                send_result = self._send_to_member(window, s, candidate, channel_name, scan_id=scan_id)
                if send_result == "sent":
                    try:
                        processed_positions_on_step.append((int(candidate.get("x", 0)), int(candidate.get("y", 0))))
                    except Exception:
                        pass
                    self._append_history_name(name)
                    sent_any = True
                    pause = random.uniform(0, max(self._config.max_pause_seconds, 0.0))
                    if pause > 0:
                        gd.pause(pause)
                    if not self._back_to_group(window):
                        return had_candidates_total
                    if not self._open_participants(window):
                        return had_candidates_total
                    self._restore_scroll_position(window, step)
                    break
                if send_result == "recover":
                    try:
                        processed_positions_on_step.append((int(candidate.get("x", 0)), int(candidate.get("y", 0))))
                    except Exception:
                        pass
                    log_and_print(
                        f"[personal_broadcast] recover participants list after '{name}' scan_id={scan_id}",
                        "warning",
                    )
                    # Avoid re-entering the same contact after recover in this and next scans.
                    self._registry.add(name)
                    self._append_history_name(name)
                    blocked_candidates_on_step.add(name)
                    if not self._open_participants(window):
                        log_and_print(
                            "[personal_broadcast] participants reopen failed; rescan same step and try next candidate",
                            "warning",
                        )
                        force_rescan_same_step = True
                        break
                    # Reopen can jump to top; restore current scroll page before rescan.
                    self._restore_scroll_position(window, step)
                    force_rescan_same_step = True
                    break

            after_registry = raw_count - skip_registry
            after_gender = after_registry - skip_gender
            log_and_print(
                f"[personal_broadcast] candidate pipeline raw={raw_count} "
                f"after_registry={after_registry} after_gender={after_gender} "
                f"send_attempted={send_attempted} scan_id={scan_id}",
                "debug",
            )

            if sent_any:
                log_and_print("[personal_broadcast] message sent, refresh members screenshot", "debug")
                continue
            if force_rescan_same_step:
                log_and_print("[personal_broadcast] recover completed; rescan current step with fresh coordinates", "debug")
                continue
            log_and_print("[personal_broadcast] no candidate sent, scroll down", "debug")

            if not self._ensure_participants_panel(window):
                log_and_print(
                    "[personal_broadcast] cannot ensure participants panel before scroll; retry same step",
                    "warning",
                )
                gd.pause(0.8)
                continue

            self._handle_same_one_before_scroll(window)
            self._scroll_members_down(window)
            gd.pause(1.5)

            if not self._ensure_participants_panel(window):
                log_and_print(
                    "[personal_broadcast] participants panel lost after scroll; retry same step without increment",
                    "warning",
                )
                gd.pause(0.8)
                continue

            # Move to next page only after participants panel is confirmed.
            step += 1
            new_scroll_no = step + 1
            self._scroll_state.save_scroll_no(new_scroll_no)
            self._maybe_clear_current_processed_after_scroll_advance(new_scroll_no)
            log_and_print(
                f"[personal_broadcast] scroll-names moved to scroll={new_scroll_no}; "
                f"reset_every={self._config.scroll_names_reset_every}",
                "debug",
            )

        log_and_print(f"[personal_broadcast] no more candidates in {channel_name}", "info")
        self._back_to_group(window)
        return had_candidates_total
