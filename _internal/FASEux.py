
import argparse
import curses
import math
import random
import time
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import FASEmsfx as audio
except Exception:
    audio = None

from FASE import (
    Simulator, summary, TICKS_PER_YEAR, TICKS_PER_MONTH, TICKS_PER_DAY,
    ENDGAME_POPULATION_FLOOR, ENDGAME_INFLUENCE_LOSS_THRESHOLD, ENDGAME_INFLUENCE_WIN_THRESHOLD,
    ENDGAME_MAJORITY_CONTROL_THRESHOLD,
    HOLY_WAR_MIN_ATTACKER_INFLUENCE,
)
from FASErg import valid_templates_for_role, BOON_DEFS as RELIC_BOON_DEFS, TIER_DEFS as RELIC_TIER_DEFS
from FASEhelp import get_help_lines
try:
    import FASEcfg as FASECFG
except Exception:
    FASECFG = None

try:
    from FASEcfg import BIOME_PROFILES
except Exception:
    BIOME_PROFILES = {}

v_info = 1.23
FAST_FORWARD_TICKS = 50
EVENT_ROWS = 12
EVENT_BUFFER_ROWS = 500
ACTOR_PANEL_MAX_ROWS = 7
SPEED_PRESETS = [1, 5, 20]
HEX_W = 9
HEX_H = 5

BANNER = [
"__/  \__/  \__/  \__/  \__/  \__/  \_",
"  -┏┳┓┏┳┓┏━┓┏━┓ ╻ ┏━┓╻_/  \__/  \__/ ",
"__┃┃┃┃┃┃┃┃ ┃┣┳┛╺╋╸┣━┫┃  __/  \__/  \_",
"  ╹╹ ╹╹ ╹┗━┛╹┗╸ ╹ ╹ ╹┗━╸  \__/  \__/ ",
"__┏━╸╻ ╻┏━┓┏┳┓┏━┓-┏━┓┏┓╻┏━┓  \__/  \_",
"  ┃  ┣━┫┣━┫┃┃┃┣━┛┃┃ ┃┃┗┫┗━┓__/  \__/ ",
"__┗━╸╹ ╹╹ ╹╹ ╹╹  ╹┗━┛╹ ╹┗━┛  \__/  \_",
"  \__/  \__/  \__/  \__/  \__/  \__/ ",
"__/  \__/  \__/  \__/  \__/  \__/  \_",
]

class UX:
    def __init__(self, stdscr, args):
        self.stdscr = stdscr
        self.args = args
        if getattr(args, "load", None):
            self._draw_loading_message(args.load)
            self.sim = Simulator.load_state(args.load)
        else:
            self.sim = Simulator(
                seed=args.seed,
                population_scale=args.pop_scale,
            )
        self._running = False
        self.run_started_at = time.perf_counter()
        self.paused_runtime_seconds = 0.0
        self._pause_started_at = self.run_started_at
        self.running = False
        self.ticks_per_frame = 1
        self.frame_delay = 0.05
        self.god_filter_mode = "none"
        self.god_sort_reverse = False
        # Open help on UX startup for new-user onboarding. Existing H/Esc close behavior remains unchanged.
        self.help_mode = True
        self._help_resume_running = False
        self.help_scroll = 0

        self.periodic_summary_years = max(0, int(args.psum))
        self.summary_every_ticks = self.periodic_summary_years * TICKS_PER_YEAR if self.periodic_summary_years > 0 else 0
        self.next_summary_tick = self.summary_every_ticks if self.summary_every_ticks > 0 else None
        self.last_summary_path: Optional[Path] = None
        self.summary_mode = False
        self.summary_files: List[Path] = []
        self.summary_selected_index = 0
        self.summary_scroll = 0
        self.summary_content_lines: List[str] = []
        self.journal_mode = False
        self.journal_scroll = 0

        self.region_ids: List[int] = []
        self.selected_region_index = 0
        self.selected_actor_index = 0
        self.last_events: List[object] = []
        self.skip_autopause = bool(getattr(args, "no_autopause", False))
        self.music_muted = False
        self.music_volume = self._current_music_volume(default=0.2)
        self.sfx_volume = self._current_sfx_volume(default=0.4)

        self.main_view = "map"  # map | list
        self.map_color_view = "order"  # order | religion
        self.screen_mode = "main"  # main | actor
        self.inspect_actor_id: Optional[int] = None
        self.actor_page = 0
        self.monster_inspector = False
        self.monster_selected_index = 0
        self.monster_scroll = 0
        self.god_mode = False
        self.god_page = 0
        self.god_selected_index = 0
        self.god_scroll = 0
        self.god_mouse_scrolled = False
        self.god_panel_bounds: Optional[Tuple[int, int, int, int]] = None
        self.god_message = ""
        self.endgame_prompt = None
        self.endgame_suppressed = set()
        self.monster_appearance_prompt_seen = False
        self.event_focus_mode = False
        self._social_hitboxes: Dict[int, Tuple[int, int, int, int]] = {}
        self._inspector_link_hitboxes: Dict[int, Tuple[int, int, int, int]] = {}
        self._event_link_hitboxes: Dict[int, Tuple[int, int, int, int]] = {}

        self._map_layout_cache: Dict[str, object] = {}
        self._last_map_selection_id: Optional[int] = None
        self.map_scroll_y = 0
        self.map_scroll_x = 0
        self._last_map_max_scroll_y = 0
        self._last_map_max_scroll_x = 0
        self._map_hitboxes: Dict[int, Tuple[int, int, int, int]] = {}
        self._actor_hitboxes: Dict[int, Tuple[int, int, int, int]] = {}
        self.actor_list_scroll = 0
        self.actor_list_mouse_scrolled = False
        self.actor_list_panel_bounds: Optional[Tuple[int, int, int, int]] = None
        self.region_list_scroll = 0
        self.region_list_mouse_scrolled = False
        self.region_list_panel_bounds: Optional[Tuple[int, int, int, int]] = None

        self._last_screen_size: Optional[Tuple[int, int]] = None

        self.status_message = (
            "SPACE run/pause | F2 events | F5 save | F9 load | 1/2/3 speed | c cartography | "
            "/ find actor | a audio | i actor | m monsters | g god UI | j journal | h help | q quit | u summaries"
        )
        self._apply_startup_god_injection(args)

    @property
    def running(self) -> bool:
        return bool(getattr(self, "_running", False))

    @running.setter
    def running(self, value: bool) -> None:
        new_value = bool(value)
        old_value = bool(getattr(self, "_running", False))
        now = time.perf_counter()
        if old_value and not new_value:
            self._pause_started_at = now
        elif (not old_value) and new_value:
            paused_at = getattr(self, "_pause_started_at", None)
            if paused_at is not None:
                self.paused_runtime_seconds = float(getattr(self, "paused_runtime_seconds", 0.0)) + max(0.0, now - paused_at)
            self._pause_started_at = None
        self._running = new_value

    def _runtime_seconds(self) -> float:
        elapsed = time.perf_counter() - float(getattr(self, "run_started_at", time.perf_counter()))
        paused = float(getattr(self, "paused_runtime_seconds", 0.0))
        if not self.running:
            paused_at = getattr(self, "_pause_started_at", None)
            if paused_at is not None:
                paused += max(0.0, time.perf_counter() - paused_at)
        return max(0.0, elapsed - paused)

    def _audio_init(self):
        if audio is None:
            return
        try:
            audio.init_audio()
        except Exception:
            pass

    def _play_sfx(self, name: str):
        if audio is None:
            return
        try:
            audio.play_sfx(name)
        except Exception:
            pass

    def _play_game_music(self):
        if audio is None:
            return
        try:
            audio.play_game_music()
        except Exception:
            pass

    def _audio_update(self):
        if audio is None:
            return
        try:
            audio.update_audio()
        except Exception:
            pass

    def _audio_manager(self):
        return getattr(audio, "audio", None) if audio is not None else None

    def _audio_enabled(self) -> bool:
        mgr = self._audio_manager()
        return bool(getattr(mgr, "enabled", False)) if mgr is not None else False

    def _set_audio_enabled(self, enabled: bool) -> None:
        mgr = self._audio_manager()
        if mgr is None:
            return
        try:
            if hasattr(audio, "set_audio_enabled"):
                audio.set_audio_enabled(bool(enabled))
            else:
                mgr.enabled = bool(enabled)
                if not bool(enabled) and hasattr(mgr, "shutdown"):
                    mgr.shutdown()
            if bool(enabled):
                self._audio_init()
                if not self.music_muted:
                    self._play_game_music()
            self.status_message = "Audio enabled." if bool(enabled) else "Audio disabled; mixer shut down."
        except Exception:
            self.status_message = "Audio setting change failed."

    def _current_track_name(self) -> str:
        try:
            if audio is not None and hasattr(audio, "current_game_track_name"):
                return audio.current_game_track_name()
            mgr = self._audio_manager()
            path = getattr(mgr, "_current_music_path", None) if mgr is not None else None
            return path.name if path is not None else "None"
        except Exception:
            return "None"

    def _select_game_track_modal(self) -> None:
        if audio is None:
            self.status_message = "Audio module unavailable."
            return
        try:
            names = audio.game_track_names() if hasattr(audio, "game_track_names") else []
        except Exception:
            names = []
        if not names:
            self.status_message = "No valid game music tracks found."
            return
        pick = self._modal_choose("Select Game Music Track", names, footer="Enter select | Esc/q cancel")
        if pick is None:
            return
        try:
            ok = audio.select_game_track(pick, play_now=True) if hasattr(audio, "select_game_track") else False
            self.music_muted = False
            self.status_message = f"Track selected: {names[pick]}" if ok else "Track selection failed."
        except Exception:
            self.status_message = "Track selection failed."

    def _current_music_volume(self, default: float = 0.2) -> float:
        mgr = self._audio_manager()
        try:
            return max(0.0, min(1.0, float(getattr(mgr, "music_volume", default))))
        except Exception:
            return default

    def _current_sfx_volume(self, default: float = 0.4) -> float:
        mgr = self._audio_manager()
        try:
            return max(0.0, min(1.0, float(getattr(mgr, "sfx_volume", default))))
        except Exception:
            return default

    def _set_music_volume(self, value: float) -> None:
        self.music_volume = max(0.0, min(1.0, float(value)))
        mgr = self._audio_manager()
        if mgr is not None:
            try:
                mgr.music_volume = self.music_volume
                if getattr(mgr, "_pygame", None) is not None and getattr(mgr, "_ready", False):
                    mgr._pygame.mixer.music.set_volume(0.0 if self.music_muted else self.music_volume)
            except Exception:
                pass

    def _set_sfx_volume(self, value: float) -> None:
        self.sfx_volume = max(0.0, min(1.0, float(value)))
        mgr = self._audio_manager()
        if mgr is not None:
            try:
                mgr.sfx_volume = self.sfx_volume
                for sound in getattr(mgr, "_sounds", {}).values():
                    try:
                        sound.set_volume(self.sfx_volume)
                    except Exception:
                        pass
            except Exception:
                pass

    def _toggle_music_mute(self) -> None:
        self.music_muted = not bool(getattr(self, "music_muted", False))
        mgr = self._audio_manager()
        try:
            if mgr is not None and getattr(mgr, "_pygame", None) is not None and getattr(mgr, "_ready", False):
                mgr._pygame.mixer.music.set_volume(0.0 if self.music_muted else self.music_volume)
        except Exception:
            pass
        self.status_message = "Music muted." if self.music_muted else f"Music unmuted. Volume {int(self.music_volume * 100)}%."

    def _modal_choose(self, title: str, options: List[str], footer: str = "Enter select | Esc/q cancel") -> Optional[int]:
        was_running = self.running
        self.running = False
        old_nodelay = True
        idx = 0
        try:
            self.stdscr.nodelay(False)
            while True:
                self.stdscr.erase()
                h, w = self.stdscr.getmaxyx()
                self._safe_addstr(1, max(0, (w - len(title)) // 2), title[:w - 1], curses.A_BOLD)
                visible = max(1, min(len(options), h - 6))
                top_idx = max(0, min(idx - visible // 2, max(0, len(options) - visible)))
                start_y = max(3, h // 2 - visible // 2)
                for row, opt in enumerate(options[top_idx:top_idx + visible]):
                    actual = top_idx + row
                    attr = curses.A_REVERSE if actual == idx else 0
                    line = f"> {opt}" if actual == idx else f"  {opt}"
                    self._safe_addstr(start_y + row, max(0, (w - len(line)) // 2), line[:w - 1], attr)
                self._safe_addstr(h - 2, max(0, (w - len(footer)) // 2), footer[:w - 1])
                self.stdscr.refresh()
                key = self.stdscr.getch()
                if key in (27, ord('q'), ord('Q')):
                    return None
                if key == curses.KEY_UP:
                    idx = (idx - 1) % len(options)
                elif key == curses.KEY_DOWN:
                    idx = (idx + 1) % len(options)
                elif key in (10, 13, curses.KEY_ENTER):
                    return idx
        finally:
            self.stdscr.nodelay(old_nodelay)
            self.running = False

    def _modal_prompt_text(self, title: str, default: str = "") -> Optional[str]:
        was_running = self.running
        self.running = False
        old_nodelay = True
        try:
            self.stdscr.nodelay(False)
            curses.echo()
            curses.curs_set(1)
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            self._safe_addstr(max(0, h // 2 - 3), max(0, (w - len(title)) // 2), title[:w - 1], curses.A_BOLD)
            if default:
                line = f"Default: {default}"
                self._safe_addstr(max(0, h // 2 - 2), max(0, (w - len(line)) // 2), line[:w - 1])
            x = max(0, w // 2 - 30)
            y = max(0, h // 2)
            self._safe_addstr(y, x, "> ")
            self.stdscr.refresh()
            raw = self.stdscr.getstr(y, x + 2, 60).decode(errors="ignore").strip()
            return raw or default
        finally:
            curses.noecho()
            try:
                curses.curs_set(0)
            except Exception:
                pass
            self.stdscr.nodelay(old_nodelay)
            self.running = False

    def _relic_creation_modal(self, actor) -> None:
        if actor is None:
            self._set_god_action_message(False, "No champion selected.")
            return
        if getattr(actor, "champion_of", None) != self._player_god():
            self._set_god_action_message(False, "Select one of your champions to receive a relic.")
            return
        tier_keys = ["lesser", "greater"]
        tier_options = []
        for key in tier_keys:
            info = RELIC_TIER_DEFS[key]
            tier_options.append(f"{info['label']} relic — cost {info['cost']} souls | limit {info['limit']}")
        pick = self._modal_choose("Grant Divine Relic: choose tier", tier_options)
        if pick is None:
            self._set_god_action_message(False, "Relic creation cancelled.")
            return
        tier = tier_keys[pick]
        templates = valid_templates_for_role(getattr(actor, "role", "Fighter"))
        template_options = [f"{t.label} — {t.description}" for t in templates]
        pick = self._modal_choose("Grant Divine Relic: choose item", template_options)
        if pick is None:
            self._set_god_action_message(False, "Relic creation cancelled.")
            return
        template = templates[pick]
        name = self._modal_prompt_text("Name the relic", default=f"{template.label} of {actor.short_name()}")
        if name is None:
            self._set_god_action_message(False, "Relic creation cancelled.")
            return
        boon_keys = list(RELIC_BOON_DEFS.keys())
        boon_options = [f"{v['label']:<10} {v['description']}" for v in RELIC_BOON_DEFS.values()]
        pick = self._modal_choose("Choose permanent relic boon", boon_options)
        if pick is None:
            self._set_god_action_message(False, "Relic creation cancelled.")
            return
        boon = boon_keys[pick]
        cost = int(RELIC_TIER_DEFS[tier].get("cost", 0))
        confirm = self._modal_choose(
            "Confirm Relic Creation",
            [f"Create {name}", f"Tier: {tier.title()} | Item: {template.label}", f"Boon: {RELIC_BOON_DEFS[boon]['label']} — {RELIC_BOON_DEFS[boon]['description']}", f"Cost: {cost} souls", "CONFIRM", "Cancel"],
            footer="Select CONFIRM and press Enter, or Esc/q cancel",
        )
        if confirm != 4:
            self._set_god_action_message(False, "Relic creation cancelled.")
            return
        ok, msg = self.sim._grant_player_relic(actor.id, tier=tier, template_key=template.key, name=name, boon_label=boon)
        self._set_god_action_message(ok, msg)

    def _audio_settings_modal(self) -> None:
        old_nodelay = True
        was_running = self.running
        self.running = False
        try:
            self.stdscr.nodelay(False)
            idx = 0
            options = ["enabled", "music", "sfx", "track"]
            while True:
                self.stdscr.erase()
                h, w = self.stdscr.getmaxyx()
                enabled_text = "ON" if self._audio_enabled() else "OFF"
                music_text = "MUTED" if self.music_muted else str(int(self.music_volume * 100)) + "%"
                lines = [
                    "Audio Settings",
                    "",
                    f"Audio: {enabled_text}",
                    f"Music: {music_text}",
                    f"SFX:   {int(self.sfx_volume * 100)}%",
                    f"Track: {self._current_track_name()}",
                    "",
                    "Up/Down select | Left/Right volume | e disable/enable | m mute | t track | Esc/Enter close",
                ]
                top = max(0, h // 2 - len(lines) // 2)
                selectable_lines = {"enabled": 2, "music": 3, "sfx": 4, "track": 5}
                for i, line in enumerate(lines):
                    attr = curses.A_BOLD if i == 0 else 0
                    if i == selectable_lines.get(options[idx], -1):
                        attr |= curses.A_REVERSE
                    self._safe_addstr(top + i, max(0, (w - len(line)) // 2), line[:w - 1], attr)
                self.stdscr.refresh()
                key = self.stdscr.getch()
                if key in (27, 10, 13, curses.KEY_ENTER, ord('q'), ord('Q'), ord('b'), ord('B')):
                    break
                if key == curses.KEY_UP:
                    idx = (idx - 1) % len(options)
                    continue
                if key == curses.KEY_DOWN:
                    idx = (idx + 1) % len(options)
                    continue
                if key in (ord('e'), ord('E')):
                    self._set_audio_enabled(not self._audio_enabled())
                    continue
                if key in (ord('m'), ord('M')):
                    self._toggle_music_mute()
                    continue
                if key in (ord('t'), ord('T')) or (key in (10, 13, curses.KEY_ENTER) and options[idx] == "track"):
                    self._select_game_track_modal()
                    continue
                if key in (curses.KEY_LEFT, ord('-')):
                    if options[idx] == "music":
                        self._set_music_volume(self.music_volume - 0.05)
                        if self.music_volume > 0:
                            self.music_muted = False
                    elif options[idx] == "sfx":
                        self._set_sfx_volume(self.sfx_volume - 0.05)
                    elif options[idx] == "track" and audio is not None:
                        try:
                            if hasattr(audio, "previous_game_track") and audio.previous_game_track():
                                self.music_muted = False
                                self.status_message = f"Track selected: {self._current_track_name()}"
                        except Exception:
                            pass
                    continue
                if key in (curses.KEY_RIGHT, ord('+'), ord('=')):
                    if options[idx] == "music":
                        self._set_music_volume(self.music_volume + 0.05)
                        self.music_muted = False
                    elif options[idx] == "sfx":
                        self._set_sfx_volume(self.sfx_volume + 0.05)
                    elif options[idx] == "track" and audio is not None:
                        try:
                            if hasattr(audio, "next_game_track") and audio.next_game_track():
                                self.music_muted = False
                                self.status_message = f"Track selected: {self._current_track_name()}"
                        except Exception:
                            pass
                    continue
                if key == ord('0'):
                    if options[idx] == "enabled":
                        self._set_audio_enabled(False)
                    elif options[idx] == "music":
                        self._set_music_volume(0.0)
                        self.music_muted = True
                    elif options[idx] == "sfx":
                        self._set_sfx_volume(0.0)
                    continue
                if key == ord('1'):
                    if options[idx] == "enabled":
                        self._set_audio_enabled(True)
                    elif options[idx] == "music":
                        self._set_music_volume(1.0)
                        self.music_muted = False
                    elif options[idx] == "sfx":
                        self._set_sfx_volume(1.0)
                    continue
        finally:
            self.stdscr.nodelay(old_nodelay)
            self.running = was_running

    def _force_terminal_refresh(self):
        """Force curses to re-read terminal dimensions after Windows launch/resize weirdness."""
        try:
            curses.update_lines_cols()
        except Exception:
            pass
        try:
            h, w = self.stdscr.getmaxyx()
            curses.resize_term(h, w)
        except Exception:
            pass
        self._map_layout_cache = {}
        self._last_map_selection_id = None
        try:
            # Force curses to throw away any stale Windows console geometry
            # and repaint the whole physical screen on the next draw.
            self.stdscr.clearok(True)
            self.stdscr.erase()
            self.stdscr.refresh()
        except Exception:
            pass


    def _draw_loading_message(self, path=None, detail: str = "") -> None:
        """Display a blocking-load notice before expensive .fics deserialization/resume work."""
        try:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            name = Path(path).name if path is not None else "save state"
            lines = [
                "Loading save state...",
                str(name),
                "",
                "Large or old worlds may take up to a minute to resume.",
                "Please wait.",
            ]
            if detail:
                lines.insert(2, str(detail))
            start = max(0, h // 2 - len(lines) // 2)
            for i, line in enumerate(lines):
                attr = curses.A_BOLD if i == 0 else 0
                self._safe_addstr(start + i, max(0, (w - len(line)) // 2), line[:w - 1], attr)
            self.stdscr.refresh()
        except Exception:
            pass


    def _apply_startup_god_injection(self, args) -> None:
        """Apply load-save player-god injection after the simulator exists.

        This is intentionally a UX-level bridge only. The simulator owns the
        actual rules for revelation/cult formalization; the UI just passes
        launcher CLI intent into those simulator entry points.
        """
        if args is None:
            return

        inject_god = getattr(args, "inject_god", None)
        inject_champion = getattr(args, "inject_champion", None)
        ascend_cult_id = getattr(args, "ascend_cult_id", None)

        if inject_god is None and ascend_cult_id is None:
            return

        # These options are only sane for an existing world. Starting a brand
        # new sim with injection flags should not crash the UI or half-apply a
        # god before worldgen settles.
        if not getattr(args, "load", None):
            self.status_message = "God injection ignored: load an existing .fics save first."
            self.god_message = self.status_message
            return

        try:
            if inject_god is not None and ascend_cult_id is not None:
                self.status_message = "God injection skipped: choose either cult ascension or revealed god, not both."
                self.god_message = self.status_message
                return

            if ascend_cult_id is not None:
                if not hasattr(self.sim, "formalize_proto_cult_as_player_god"):
                    self.status_message = "Cult ascension unavailable on this simulator version."
                    self.god_message = self.status_message
                    return
                ok, msg = self.sim.formalize_proto_cult_as_player_god(int(ascend_cult_id))
                self.status_message = ("OK: " if ok else "FAILED: ") + str(msg)
                self.god_message = self.status_message
                return

            if inject_god is not None:
                if not hasattr(self.sim, "inject_revealed_player_god"):
                    self.status_message = "Revealed-god injection unavailable on this simulator version."
                    self.god_message = self.status_message
                    return
                ok, msg = self.sim.inject_revealed_player_god(inject_god, inject_champion)
                self.status_message = ("OK: " if ok else "FAILED: ") + str(msg)
                self.god_message = self.status_message
                return

        except Exception as exc:
            self.status_message = f"God injection failed: {exc}"
            self.god_message = self.status_message
            return


    def confirm_exit(self) -> bool:
        self.paused = True
        h, w = self.stdscr.getmaxyx()
        lines = [
            "Quit simulation?",
            "Y = write summary and exit",
            "N / Esc = return to simulation",
        ]
        box_w = min(44, max(30, w - 4))
        box_h = len(lines) + 4
        top = max(0, h // 2 - box_h // 2)
        left = max(0, w // 2 - box_w // 2)
        for y in range(top, min(h, top + box_h)):
            self._safe_addstr(y, left, " " * min(box_w, w - left - 1), curses.A_REVERSE)
        for i, line in enumerate(lines):
            x = left + max(1, (box_w - len(line)) // 2)
            self._safe_addstr(top + 1 + i, x, line, curses.A_REVERSE | (curses.A_BOLD if i == 0 else 0))
        self.stdscr.refresh()
        while True:
            key = self.stdscr.getch()
            if key in (ord('y'), ord('Y')):
                return True
            if key in (ord('n'), ord('N'), 27, ord('q'), ord('Q')):
                return False


    def run(self):
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        except Exception:
            pass
        self._force_terminal_refresh()
        # Windows consoles can report stale size on first paint after launcher handoff;
        # a tiny second pass usually catches the real dimensions without user resize.
        time.sleep(0.05)
        self._force_terminal_refresh()
        self._init_colors()
        self._audio_init()
        self._play_game_music()
        self._refresh_summary_files()
        self._refresh_region_ids()  # regions are static after world init; no need to rebuild every frame

        while True:
            self._clamp_selection()
            self.handle_input()
            if self.running and self.endgame_prompt is None:
                for _ in range(max(1, self.ticks_per_frame)):
                    self.step()
                    if self.endgame_prompt is not None:
                        break
            self.draw()
            self._audio_update()
            time.sleep(self.frame_delay)

    def _init_colors(self):
        if not curses.has_colors():
            self.has_colors = False
            return
        self.has_colors = True
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)   # good
        curses.init_pair(2, curses.COLOR_RED, -1)     # evil
        curses.init_pair(3, curses.COLOR_YELLOW, -1)  # contested/neutral
        curses.init_pair(4, curses.COLOR_CYAN, -1)    # selected
        curses.init_pair(5, curses.COLOR_MAGENTA, -1) # polity/siege
        curses.init_pair(6, curses.COLOR_WHITE, -1)   # banner/seams


    def _pause_for_monster_appearance(self, new_monsters):
        if getattr(self, "skip_autopause", False):
            self.monster_appearance_prompt_seen = True
            self.status_message = "Notification skipped: monsters have appeared."
            return
        self._play_sfx("monster_appears")
        self.running = False
        self.monster_appearance_prompt_seen = True
        names = []
        for monster in new_monsters[:5]:
            kind = getattr(getattr(monster, "kind", None), "value", "Monster")
            region = self.sim.world.region_name(getattr(monster, "region_id", -1)) if hasattr(self.sim.world, "region_name") else "unknown"
            names.append(f"{kind} in {region}")
        if len(new_monsters) > 5:
            names.append(f"...and {len(new_monsters) - 5} more")
        old_nodelay = True
        try:
            self.stdscr.nodelay(False)
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            lines = ["MONSTERS HAVE APPEARED", "'Human' is now on the menu."] + names + ["", "Press any key to continue."]
            start = max(0, h // 2 - len(lines) // 2)
            for i, line in enumerate(lines):
                attr = curses.A_BOLD if i == 0 else 0
                self._safe_addstr(start + i, max(0, (w - len(line)) // 2), line[:w - 1], attr)
            self.stdscr.refresh()
            self.stdscr.getch()
        finally:
            self.stdscr.nodelay(old_nodelay)

    def _pause_message_modal(self, lines):
        if getattr(self, "skip_autopause", False):
            self.status_message = str(lines[0]) if lines else "Notification skipped."
            return
        was_running = self.running
        self.running = False
        old_nodelay = True
        try:
            self.stdscr.nodelay(False)
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            lines = [str(line) for line in lines]
            start = max(0, h // 2 - len(lines) // 2)
            for i, line in enumerate(lines):
                attr = curses.A_BOLD if i == 0 else 0
                self._safe_addstr(start + i, max(0, (w - len(line)) // 2), line[:w - 1], attr)
            self.stdscr.refresh()
            self.stdscr.getch()
        finally:
            self.stdscr.nodelay(old_nodelay)
            self.running = False

    def _maybe_pause_for_necromancer_crisis(self, events):
        for event in events:
            if getattr(event, "category", "") != "necromancer_crisis":
                continue
            text = getattr(event, "text", "")
            if " rises from " not in text:
                continue
            crisis = getattr(self.sim.world, "adventurer_surplus_necromancer_crisis", {}) or {}
            title = crisis.get("title", "The Black Host")
            start_adv = int(crisis.get("starting_adventurers", 0) or 0)
            total = int(crisis.get("starting_total", 1) or 1)
            target = int(crisis.get("target_adventurers", 0) or 0)
            ratio = (start_adv / max(1, total)) * 100.0
            target_ratio = (target / max(1, total)) * 100.0
            self._play_sfx("necromancer_crisis")
            self._pause_message_modal([
                "THE BLACK HOST RISES",
                str(title),
                f"Adventurers: {start_adv} / {total} ({ratio:.1f}%)",
                f"Target after war: {target} ({target_ratio:.1f}%)",
                "All adventurers march. Many will not return.",
                "",
                "Press any key to continue.",
            ])
            return

    def _event_targets_player_god(self, event) -> bool:
        god_name = str(self._player_god_name() or "").strip()
        if not god_name or god_name == "No player god":
            return False
        cat = str(getattr(event, "category", "") or "")
        text = str(getattr(event, "text", "") or "")
        low = text.lower()
        name_low = god_name.lower()
        if cat == "holy_war":
            # AI/player holy-war text uses: "<attacker> launches a Holy War against <target>..."
            # or "<attacker>'s Holy War against <target> falters...". Only pause if
            # the player god is the target, not merely mentioned as attacker.
            return f"against {name_low}" in low
        if cat == "god_death":
            return name_low in low
        return False

    def _maybe_pause_for_player_god_attack(self, events) -> None:
        for event in events:
            if not self._event_targets_player_god(event):
                continue
            text = str(getattr(event, "text", event))
            if getattr(self, "skip_autopause", False):
                self.status_message = f"Autopause skipped: {self._player_god_name()} was targeted by immortal action."
                self.god_message = self.status_message
                return
            self._play_sfx("holy_war")
            self.running = False
            self._pause_message_modal([
                "IMMORTAL ATTACK",
                f"{self._player_god_name()} has been targeted.",
                "",
                text,
                "",
                "Press any key to continue.",
            ])
            return

    def _play_event_sfx(self, events):
        for event in events:
            cat = str(getattr(event, "category", "") or "")
            text = str(getattr(event, "text", "") or "").lower()
            if cat == "relic":
                if " claims " in text:
                    self._play_sfx("relic_claim")
                    return
                if " lost " in text or " is lost " in text:
                    self._play_sfx("relic_lost")
                    return
            if cat in {"holy_war", "god_death"}:
                self._play_sfx("holy_war")
                return
            if cat in {"save", "load"}:
                self._play_sfx(cat)
                return

    def step(self):
        before_counter = int(getattr(self.sim.world, "event_counter", len(getattr(self.sim.world, "events", []))) or 0)
        # Only snapshot monster IDs when we still care about new appearances.
        if not self.monster_appearance_prompt_seen:
            before_monster_ids = {m.id for m in self.sim.world.living_monsters()}
        else:
            before_monster_ids = None
        self.sim.step()
        if before_monster_ids is not None:
            new_monsters = [m for m in self.sim.world.living_monsters() if m.id not in before_monster_ids]
            if new_monsters:
                self._pause_for_monster_appearance(new_monsters)
        after_counter = int(getattr(self.sim.world, "event_counter", len(getattr(self.sim.world, "events", []))) or 0)
        if after_counter > before_counter:
            delta = after_counter - before_counter
            new_events = list(getattr(self.sim.world, "events", [])[-delta:])
            self.last_events.extend(new_events)
            self.last_events = self.last_events[-EVENT_BUFFER_ROWS:]
            self._play_event_sfx(new_events)
            self._maybe_pause_for_necromancer_crisis(new_events)
            self._maybe_pause_for_player_god_attack(new_events)
        self._maybe_write_periodic_summary()
        self._check_endgame_state()

    def _player_influence_share(self) -> Optional[float]:
        god = self._player_god()
        if god is None:
            return None
        try:
            state = self.sim._player_god_state()
        except Exception:
            state = None
        if state is None:
            return None
        return float(getattr(state, "influence_share", 0.0))

    def _player_living_follower_share(self) -> Optional[float]:
        if not hasattr(self.sim, "_player_living_follower_share"):
            return None
        try:
            return self.sim._player_living_follower_share()
        except Exception:
            return None

    def _player_map_dominance_ticks(self) -> int:
        if not hasattr(self.sim, "_update_player_map_dominance_streak"):
            return 0
        try:
            return int(self.sim._update_player_map_dominance_streak())
        except Exception:
            return 0

    def _check_endgame_state(self) -> None:
        if self.endgame_prompt is not None:
            return
        total_pop = self._total_population()
        influence = self._player_influence_share()
        living_follower_share = self._player_living_follower_share()
        majority_control_share = self.sim._player_majority_control_share() if hasattr(self.sim, "_player_majority_control_share") else living_follower_share
        map_dom_ticks = self._player_map_dominance_ticks()
        if total_pop < ENDGAME_POPULATION_FLOOR and "population_collapse" not in self.endgame_suppressed:
            self._set_endgame_prompt(
                "population_collapse",
                "GAME OVER: POPULATION COLLAPSE",
                f"Overall living population has fallen below {ENDGAME_POPULATION_FLOOR}: current population {total_pop}.",
            )
            return
        if influence is not None and influence < ENDGAME_INFLUENCE_LOSS_THRESHOLD and "god_influence_lost" not in self.endgame_suppressed:
            self._set_endgame_prompt(
                "god_influence_lost",
                "GAME OVER: DIVINE INFLUENCE LOST",
                f"{self._player_god_name()} influence has fallen below {ENDGAME_INFLUENCE_LOSS_THRESHOLD:.1f}%: current influence {influence:.1f}%.",
            )
            return
        majority_threshold = float(getattr(self.sim, "ENDGAME_MAJORITY_CONTROL_THRESHOLD", ENDGAME_MAJORITY_CONTROL_THRESHOLD))
        if majority_control_share is not None and majority_control_share > majority_threshold and "god_majority_won" not in self.endgame_suppressed:
            self._set_endgame_prompt(
                "god_majority_won",
                "VICTORY: MORTAL MAJORITY",
                f"{self._player_god_name()} controls {majority_control_share:.1f}% of living commoners and adventurers, passing the {majority_threshold:.1f}% majority threshold.",
            )
            return
        if living_follower_share is not None and living_follower_share >= ENDGAME_INFLUENCE_WIN_THRESHOLD and "god_followers_won" not in self.endgame_suppressed:
            self._set_endgame_prompt(
                "god_followers_won",
                "ACHIEVEMENT: OVERWHELMING FAITH DOMINANCE",
                f"{self._player_god_name()} controls {living_follower_share:.1f}% of living followers, meeting the {ENDGAME_INFLUENCE_WIN_THRESHOLD:.1f}% dominance threshold.",
            )
            return
        if map_dom_ticks >= TICKS_PER_MONTH and "map_dominance_won" not in self.endgame_suppressed:
            self._set_endgame_prompt(
                "map_dominance_won",
                "VICTORY: TOTAL MAP DOMINANCE",
                f"{self._player_god_name()} has dominated every region for one month.",
            )
            return

    def _set_endgame_prompt(self, key: str, title: str, message: str) -> None:
        self._play_sfx("victory" if str(key).endswith("_won") else "game_over")
        if getattr(self, "skip_autopause", False):
            self.endgame_suppressed.add(key)
            self.status_message = f"Autopause skipped: {title} — {message}"
            return
        self.running = False
        self.endgame_prompt = {"key": key, "title": title, "message": message}

    def _handle_endgame_input(self, key: int) -> bool:
        if self.endgame_prompt is None:
            return False
        if key in (ord('c'), ord('C'), 10, 13, curses.KEY_ENTER):
            self.endgame_suppressed.add(self.endgame_prompt.get("key", ""))
            self.endgame_prompt = None
            return True
        return True

    def _maybe_write_periodic_summary(self):
        if self.next_summary_tick is None:
            return
        world_tick = self.sim.world.tick
        while self.next_summary_tick is not None and world_tick >= self.next_summary_tick:
            elapsed_years = world_tick // TICKS_PER_YEAR
            self.sim.world.runtime_seconds = self._runtime_seconds()
            self.sim._flush_historian() if hasattr(self.sim, "_flush_historian") else None
            self.last_summary_path = summary.write_summary(self.sim, elapsed_years)
            self._refresh_summary_files()
            self.next_summary_tick += self.summary_every_ticks

    def fast_forward(self, ticks: int = FAST_FORWARD_TICKS):
        for _ in range(ticks):
            self.step()
            if self.endgame_prompt is not None:
                break

    def _write_final_summary_now(self):
        self.running = False
        elapsed_years = max(0, self.sim.world.tick // TICKS_PER_YEAR)
        self.sim.world.runtime_seconds = self._runtime_seconds()
        self.sim._flush_historian() if hasattr(self.sim, "_flush_historian") else None
        self.last_summary_path = summary.write_summary(self.sim, elapsed_years)
        self._refresh_summary_files()
        self.summary_mode = True
        self.god_mode = False
        self.inspect_actor_id = None
        self.status_message = f"Summary written: {self.last_summary_path.name}"

    def _summary_dir(self) -> Path:
        return Path(getattr(self.sim.world, "output_dir", Path.cwd()))

    def _refresh_summary_files(self):
        out_dir = self._summary_dir()
        try:
            files = sorted(out_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            files = []
        self.summary_files = files
        if not files:
            self.summary_selected_index = 0
            self.summary_scroll = 0
            self.summary_content_lines = [f"No summary files found in {out_dir}"]
            return
        self.summary_selected_index = max(0, min(self.summary_selected_index, len(files)-1))
        self._load_selected_summary()

    def _load_selected_summary(self):
        if not self.summary_files:
            self.summary_content_lines = ["No summary files available."]
            self.summary_scroll = 0
            return
        path = self.summary_files[self.summary_selected_index]
        try:
            self.summary_content_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            self.summary_content_lines = [f"Unable to read {path.name}: {exc}"]
        self.summary_scroll = 0

    def _change_summary_selection(self, delta: int):
        if not self.summary_files:
            self._refresh_summary_files()
            return
        self.summary_selected_index = max(0, min(self.summary_selected_index + delta, len(self.summary_files)-1))
        self._load_selected_summary()


    def _proper_quit_cleanup(self) -> None:
        if hasattr(self.sim, "_flush_historian"):
            self.sim._flush_historian()
        return


    def _save_dir(self) -> Path:
        save_dir = Path(__file__).resolve().parent / "saves"
        save_dir.mkdir(exist_ok=True)
        return save_dir

    def _safe_save_component(self, value) -> str:
        text = str(value or "seed")
        text = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
        return text.strip("._") or "seed"

    def _save_date_stamp(self) -> str:
        try:
            year, month, day, _tod, _season = self.sim.world.current_calendar()
            month_name = self.sim.MONTH_NAMES[month - 1] if 1 <= month <= len(self.sim.MONTH_NAMES) else f"M{month:02d}"
            month_safe = self._safe_save_component(month_name)
            tick = int(getattr(self.sim.world, "tick", 0))
            return f"Y{int(year):04d}_{month_safe}_{int(day):02d}_T{tick}"
        except Exception:
            world = getattr(getattr(self, "sim", None), "world", None)
            return f"tick_{getattr(world, 'tick', 0)}"

    def _quicksave_path(self) -> Path:
        seed = self._safe_save_component(getattr(self.sim.world, "seed_used", getattr(self.args, "seed", None) or "random"))
        stamp = self._save_date_stamp()
        return self._save_dir() / f"save_{seed}_{stamp}.fics"

    def _latest_save_path(self) -> Optional[Path]:
        save_dir = self._save_dir()
        try:
            saves = sorted(save_dir.glob("*.fics"), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            saves = []
        return saves[0] if saves else None

    def _save_quick_state(self) -> None:
        was_running = self.running
        self.running = False
        path = self._quicksave_path()
        try:
            self.sim.save_state(path)
            self._play_sfx("save")
            self.status_message = f"Saved state: {path.name}"
            self.god_message = self.status_message
        except Exception as exc:
            self.status_message = f"Save failed: {exc}"
            self.god_message = self.status_message
        finally:
            self.running = was_running

    def _load_quick_state(self) -> None:
        path = self._latest_save_path()
        if path is None or not path.exists():
            self.status_message = "No .fics saves found."
            self.god_message = self.status_message
            return
        self.running = False
        try:
            self._draw_loading_message(path)
            self.sim = Simulator.load_state(path)
            self._draw_loading_message(path, "Save loaded. Rebuilding world state...")
            self._play_sfx("load")
            self.last_events = list(getattr(self.sim.world, "events", [])[-EVENT_BUFFER_ROWS:])
            self.inspect_actor_id = None
            self.god_selected_index = 0
            self.god_scroll = 0
            self.summary_mode = False
            self.journal_mode = False
            self.endgame_prompt = None
            self._refresh_summary_files()
            self._refresh_region_ids()
            self._force_terminal_refresh()
            self.status_message = f"Loaded state: {path.name}"
            self.god_message = self.status_message
        except Exception as exc:
            self.status_message = f"Load failed: {exc}"
            self.god_message = self.status_message


    def _close_top_overlay(self) -> bool:
        """Close only the currently active overlay/panel via its normal close key.

        Runtime curses does not implement Start Game's Back navigation.
        """
        if getattr(self, "help_mode", False):
            self.help_mode = False
            self.running = self._help_resume_running
            return True
        if getattr(self, "endgame_prompt", None) is not None:
            self.endgame_suppressed.add(self.endgame_prompt.get("key", ""))
            self.endgame_prompt = None
            return True
        if self.inspect_actor_id is not None:
            self.inspect_actor_id = None
            return True
        if self.summary_mode:
            self.summary_mode = False
            return True
        if getattr(self, "journal_mode", False):
            self.journal_mode = False
            return True
        if self.god_mode:
            self.god_mode = False
            return True
        if self.event_focus_mode:
            self.event_focus_mode = False
            return True
        if getattr(self, "monster_inspector", False):
            self.monster_inspector = False
            return True
        if self._region_dossier_open():
            self._close_region_dossier()
            return True
        return False

    def _region_dossier_open(self) -> bool:
        return self.main_view == "list"

    def _close_region_dossier(self) -> None:
        if self.main_view == "list":
            self.main_view = "map"

    def _close_panels_for(self, keep: str) -> None:
        """Keep only the named primary panel open.

        The expanded region dossier is implemented as main_view == "list", but
        functionally it is an inspector panel. Keep it mutually exclusive with
        actor/god/monster/summary/event panels so the main UI does not redraw
        buried panels behind active overlays.
        """
        if keep != "region":
            self._close_region_dossier()
        if keep != "actor":
            self.inspect_actor_id = None
        if keep != "god":
            self.god_mode = False
        if keep != "summary":
            self.summary_mode = False
        if keep != "journal":
            self.journal_mode = False
        if keep != "events":
            self.event_focus_mode = False
        if keep != "monster":
            self.monster_inspector = False

    def _open_actor_inspector(self, actor, *, push: bool = True) -> None:
        if actor is None:
            return
        self._close_panels_for("actor")
        self.inspect_actor_id = actor.id
        self.actor_page = 0

    def _open_summary_browser(self) -> None:
        if not self.summary_mode:
            self._close_panels_for("summary")
            self.summary_mode = True
            self._refresh_summary_files()
        else:
            self.summary_mode = False

    def _open_journal(self) -> None:
        if not getattr(self, "journal_mode", False):
            self._close_panels_for("journal")
            self.journal_mode = True
            self.journal_scroll = 0
            self.status_message = "Journal open."
        else:
            self.journal_mode = False

    def _open_god_ui(self) -> None:
        if not self.god_mode:
            self._close_panels_for("god")
            self.god_mode = True
            self.god_message = ""
        else:
            self.god_mode = False

    def _toggle_event_focus(self) -> None:
        if not self.event_focus_mode:
            self._close_panels_for("events")
            self.event_focus_mode = True
            self.status_message = "Expanded event log"
        else:
            self.event_focus_mode = False


    def _open_monster_inspector(self) -> None:
        opening = not getattr(self, "monster_inspector", False)
        self.monster_inspector = opening
        if opening:
            self._close_panels_for("monster")
            self.monster_inspector = True
            self.monster_selected_index = max(0, int(getattr(self, "monster_selected_index", 0)))
            self.monster_scroll = max(0, int(getattr(self, "monster_scroll", 0)))

    def _living_monsters_sorted(self):
        monsters = [m for m in getattr(self.sim.world, "monsters", {}).values() if getattr(m, "alive", False)]
        monsters.sort(key=lambda m: (str(getattr(getattr(m, "kind", None), "value", getattr(m, "kind", ""))), -int(getattr(m, "monster_xp", 0) or 0), -int(getattr(m, "power", 0) or 0), str(getattr(m, "name", ""))))
        return monsters

    def _selected_monster(self):
        monsters = self._living_monsters_sorted()
        if not monsters:
            self.monster_selected_index = 0
            return None
        self.monster_selected_index = max(0, min(int(getattr(self, "monster_selected_index", 0)), len(monsters) - 1))
        return monsters[self.monster_selected_index]

    def _format_tick_timestamp(self, tick: int) -> str:
        tick = max(0, int(tick or 0))
        tod_list = TIME_OF_DAY if "TIME_OF_DAY" in globals() else ["Morning", "Midday", "Evening", "Night"]
        ticks_per_day = max(1, int(globals().get("TICKS_PER_DAY", len(tod_list))))
        day_index = tick // ticks_per_day
        year = day_index // 360 + 1
        day_of_year = day_index % 360
        month = day_of_year // 30 + 1
        day = day_of_year % 30 + 1
        tod = tod_list[tick % len(tod_list)]
        season = "Spring" if month <= 3 else "Summer" if month <= 6 else "Autumn" if month <= 9 else "Winter"
        month_names = globals().get("MONTH_NAMES", ["Dawnsreach", "Rainmoot", "Bloomtide", "Suncrest", "Goldfire", "Highsun", "Harvestwane", "Emberfall", "Duskmarch", "Frostburn", "Deepcold", "Yearsend"])
        return f"Year {year}, {season}, {month_names[month - 1]} {day}, {tod}"

    def _monster_age_status(self, monster) -> str:
        if monster is None:
            return "unknown"
        kind = getattr(monster, "kind", None)
        kind_value = getattr(kind, "value", str(kind))
        if kind_value == "Ancient Horror":
            return "Ageless / banishable only"
        age_ticks = int(getattr(monster, "age_ticks", 0) or 0)
        max_age_ticks = int(getattr(monster, "max_age_ticks", 0) or 0)
        if max_age_ticks <= 0:
            return f"{age_ticks / TICKS_PER_YEAR:.1f}y / lifespan unknown"
        ratio = age_ticks / max_age_ticks if max_age_ticks else 0
        label = "young"
        if ratio >= 1.0:
            label = "overdue"
        elif ratio >= 0.85:
            label = "elder"
        elif ratio >= 0.55:
            label = "mature"
        return f"{age_ticks / TICKS_PER_YEAR:.1f}y / {max_age_ticks / TICKS_PER_YEAR:.0f}y max ({label})"

    def _handle_monster_input(self, key: int) -> bool:
        if key in (27, ord('m')):
            self.monster_inspector = False
            return True
        monsters = self._living_monsters_sorted()
        if key == curses.KEY_UP:
            self.monster_selected_index = max(0, int(getattr(self, "monster_selected_index", 0)) - 1)
            return True
        if key == curses.KEY_DOWN:
            self.monster_selected_index = min(max(0, len(monsters) - 1), int(getattr(self, "monster_selected_index", 0)) + 1)
            return True
        if key == curses.KEY_PPAGE:
            self.monster_selected_index = max(0, int(getattr(self, "monster_selected_index", 0)) - 8)
            return True
        if key == curses.KEY_NPAGE:
            self.monster_selected_index = min(max(0, len(monsters) - 1), int(getattr(self, "monster_selected_index", 0)) + 8)
            return True
        # No Enter/R jump behavior in monster inspector. Arrow keys select; m/Esc closes.
        if key in (10, 13, curses.KEY_ENTER, ord('r'), ord('R')):
            return True
        return False

    def handle_input(self):
        try:
            key = self.stdscr.getch()
        except Exception:
            return

        if key == -1:
            return

        if key != curses.KEY_RESIZE:
            self._play_sfx("ui_click")

        if key == curses.KEY_RESIZE:
            self._force_terminal_refresh()
            return

        if self.endgame_prompt is not None:
            if key in (ord('q'), ord('Q')):
                if self.confirm_exit():
                    self._proper_quit_cleanup()
                    raise SystemExit
                return
            self._handle_endgame_input(key)
            return

        if self.help_mode:
            if key in (ord('h'), ord('H'), ord('q'), ord('Q'), 27, 10, 13, curses.KEY_ENTER):
                self.help_mode = False
                self.running = self._help_resume_running
                return
            if key == curses.KEY_UP:
                self.help_scroll = max(0, int(getattr(self, "help_scroll", 0)) - 1)
                return
            if key == curses.KEY_DOWN:
                self.help_scroll = int(getattr(self, "help_scroll", 0)) + 1
                return
            if key == curses.KEY_PPAGE:
                self.help_scroll = max(0, int(getattr(self, "help_scroll", 0)) - 12)
                return
            if key == curses.KEY_NPAGE:
                self.help_scroll = int(getattr(self, "help_scroll", 0)) + 12
                return
            if key == curses.KEY_HOME:
                self.help_scroll = 0
                return
            if key == curses.KEY_END:
                self.help_scroll = 10_000
                return
            if key == curses.KEY_MOUSE:
                try:
                    _id, _mx, _my, _z, bstate = curses.getmouse()
                    wheel_up = bstate & getattr(curses, "BUTTON4_PRESSED", 0)
                    wheel_down = bstate & getattr(curses, "BUTTON5_PRESSED", 0)
                    if wheel_up or wheel_down:
                        self.help_scroll = max(0, int(getattr(self, "help_scroll", 0)) + (-3 if wheel_up else 3))
                except Exception:
                    pass
                return
            return

        if key == 27:
            self._close_top_overlay()
            return

        if key in (ord('h'), ord('H')):
            self._help_resume_running = self.running
            self.running = False
            self._close_panels_for("help")
            self.help_mode = True
            self.help_scroll = 0
            return

        if key == getattr(curses, "KEY_F2", 266):
            self._toggle_event_focus()
            return

        if key == ord('/'):
            self._actor_lookup_modal()
            return

        if key in (ord('a'), ord('A')):
            self._audio_settings_modal()
            return

        if key in (ord('j'), ord('J')):
            self._open_journal()
            return

        if key in (ord('q'), ord('Q')):
            if self.confirm_exit():
                self._proper_quit_cleanup()
                raise SystemExit
            return

        if key == getattr(curses, "KEY_F5", 269):
            self._save_quick_state()
            return

        if key == getattr(curses, "KEY_F9", 273):
            self._load_quick_state()
            return

        if key == ord('m'):
            self._open_monster_inspector()
            return

        if key in (ord('c'), ord('C')):
            if self.main_view == "map":
                self._close_panels_for("region")
                self.main_view = "list"
            else:
                self.main_view = "map"
            return

        # God UI toggle must stay global, even while an actor inspector is open.
        # Actor-inspector handling below used to consume overlay context first,
        # which made G feel dead/overridden in inspector view.
        if key in (ord('g'), ord('G')):
            self._open_god_ui()
            return

        if getattr(self, "monster_inspector", False):
            if self._handle_monster_input(key):
                return

        if self.god_mode and self.inspect_actor_id is not None:
            actor_keys = (ord('i'), ord('I'), ord('s'), ord('S'), ord('o'), ord('O'), ord('X'), ord('P'), ord('r'), ord('R'), ord('T'), ord('Y'))
            if key in actor_keys and self._handle_actor_input(key):
                return
            if self._handle_god_input(key):
                return

        if self.god_mode:
            if self._handle_god_input(key):
                return

        if self.inspect_actor_id is not None:
            if self._handle_actor_input(key):
                return

        if key in (ord('u'), ord('U')):
            self._open_summary_browser()
            return

        if getattr(self, "journal_mode", False):
            if key in (27, ord('j'), ord('J')):
                self.journal_mode = False
                return
            if key == curses.KEY_UP:
                self.journal_scroll = max(0, int(getattr(self, "journal_scroll", 0)) - 1)
                return
            if key == curses.KEY_DOWN:
                self.journal_scroll = int(getattr(self, "journal_scroll", 0)) + 1
                return
            if key == curses.KEY_PPAGE:
                self.journal_scroll = max(0, int(getattr(self, "journal_scroll", 0)) - 8)
                return
            if key == curses.KEY_NPAGE:
                self.journal_scroll = int(getattr(self, "journal_scroll", 0)) + 8
                return

        if self.summary_mode:
            if key == curses.KEY_LEFT:
                self._change_summary_selection(-1)
                return
            elif key == curses.KEY_RIGHT:
                self._change_summary_selection(1)
                return
            elif key == curses.KEY_UP:
                self.summary_scroll = max(0, self.summary_scroll - 1)
                return
            elif key == curses.KEY_DOWN:
                self.summary_scroll += 1
                return
            elif key == curses.KEY_NPAGE:
                self.summary_scroll += 8
                return
            elif key == curses.KEY_PPAGE:
                self.summary_scroll = max(0, self.summary_scroll - 8)
                return
            elif key in (ord('r'), ord('R')):
                self._refresh_summary_files()
                return

        if key == ord(' '):
            self.running = not self.running
            # Simulation pause should not pause/stop music. Some pygame/audio
            # backends report paused music as not busy, which makes the audio
            # updater advance to the next track on the following frame. Keep
            # music playing continuously and only pause simulation ticks.
            # Windows terminal sometimes reports stale dimensions until user interaction.
            # Space is the natural first interaction, so force a full geometry/cache refresh here.
            self._force_terminal_refresh()
            return
        elif key in (10, 13, curses.KEY_ENTER):
            actor = self._selected_actor()
            if actor is not None:
                self._open_actor_inspector(actor)
            return
        elif key in (ord('v'), ord('V')):
            self.map_color_view = "religion" if self.map_color_view == "order" else "order"
        elif key in (ord('1'), ord('2'), ord('3')):
            self.ticks_per_frame = SPEED_PRESETS[int(chr(key)) - 1]
        elif key == curses.KEY_MOUSE:
            self._handle_mouse()
        elif key == curses.KEY_LEFT:
            self._move_map_selection(-1, axis="x")
        elif key == curses.KEY_RIGHT:
            self._move_map_selection(1, axis="x")
        elif key == curses.KEY_UP:
            self._move_map_selection(-1, axis="y")
        elif key == curses.KEY_DOWN:
            self._move_map_selection(1, axis="y")
        elif key == curses.KEY_PPAGE:
            self.selected_actor_index = max(0, int(getattr(self, "selected_actor_index", 0)) - 1)
            self.actor_list_mouse_scrolled = False
        elif key == curses.KEY_NPAGE:
            actors_here = self._actors_in_selected_region() if hasattr(self, "_actors_in_selected_region") else []
            self.selected_actor_index = min(max(0, len(actors_here) - 1), int(getattr(self, "selected_actor_index", 0)) + 1)
            self.actor_list_mouse_scrolled = False
        elif key == curses.KEY_HOME:
            self.selected_actor_index = 0
            self.actor_list_mouse_scrolled = False
        elif key == curses.KEY_END:
            actors_here = self._actors_in_selected_region() if hasattr(self, "_actors_in_selected_region") else []
            self.selected_actor_index = max(0, len(actors_here) - 1)
            self.actor_list_mouse_scrolled = False
        elif key in (ord('i'), ord('I')):
            if self.inspect_actor_id is not None:
                self._close_top_overlay()
            else:
                actor = self._selected_actor()
                if actor is not None:
                    self._open_actor_inspector(actor)

        self._clamp_selection()

    def _value_label(self, value) -> str:
        return str(getattr(value, "value", getattr(value, "name", value if value is not None else "None")))

    def _deity_label(self, deity) -> str:
        return self._value_label(deity)

    def _deity_is_defeated(self, deity) -> bool:
        """Best-effort UX check for gods that remain visible after defeat.

        Different save versions have stored this state on god_state, god_profiles,
        deity-like objects, or world-level defeated/dead sets. This stays display-only.
        """
        if deity is None:
            return False
        world = getattr(self.sim, "world", None)
        name = str(self._deity_name(deity) if hasattr(self, "_deity_name") else self._value_label(deity)).strip().lower()

        def truthy_flag(obj) -> bool:
            if obj is None:
                return False
            for attr in ("defeated", "dead", "is_dead", "is_defeated", "killed", "vanquished"):
                if bool(getattr(obj, attr, False)):
                    return True
            for attr in ("alive", "active"):
                if hasattr(obj, attr) and getattr(obj, attr) is False:
                    return True
            status = str(getattr(obj, "status", getattr(obj, "state", "")) or "").strip().lower()
            return status in {"dead", "defeated", "killed", "fallen", "vanquished"}

        if truthy_flag(deity):
            return True
        if world is not None:
            state = (getattr(world, "god_state", {}) or {}).get(deity)
            profile = (getattr(world, "god_profiles", {}) or {}).get(deity)
            if truthy_flag(state) or truthy_flag(profile):
                return True
            for field in ("defeated_gods", "dead_gods", "killed_gods", "vanquished_gods"):
                values = getattr(world, field, None)
                if not values:
                    continue
                try:
                    if deity in values:
                        return True
                except Exception:
                    pass
                try:
                    labels = {str(self._deity_name(v) if hasattr(self, "_deity_name") else self._value_label(v)).strip().lower() for v in values}
                    if name in labels:
                        return True
                except Exception:
                    pass
        return False

    def _deity_display_name(self, deity) -> str:
        name = self._deity_name(deity) if hasattr(self, "_deity_name") else self._value_label(deity)
        return f"{name} [D]" if self._deity_is_defeated(deity) else name

    def _cult_title_label(self, cult) -> str:
        title = str(getattr(cult, "public_title", "") or "").strip()
        if title:
            return title
        return str(getattr(cult, "name", "Unnamed Cult") or "Unnamed Cult")

    def _actor_protocult(self, actor):
        """Return the single strongest active proto-cult membership for display."""
        if actor is None:
            return None, 0.0
        world = getattr(self.sim, "world", None)
        if world is None:
            return None, 0.0
        actor_id = getattr(actor, "id", None)
        cults = getattr(world, "proto_cults", {}) or {}
        aff_map = getattr(actor, "cult_affinity", {}) or {}
        best = None
        best_val = 0.0

        def valid(cult):
            if cult is None:
                return False
            if getattr(cult, "failed", False):
                return False
            if getattr(cult, "formalized", False) or getattr(cult, "ascended", False):
                return False
            return True

        for cid, raw_val in aff_map.items():
            try:
                val = float(raw_val or 0.0)
            except Exception:
                val = 0.0
            if val <= best_val:
                continue
            cult = cults.get(cid)
            if cult is None:
                try:
                    cult = cults.get(int(cid))
                except Exception:
                    cult = None
            if valid(cult):
                best = cult
                best_val = val

        if best is None and actor_id is not None:
            for cult in cults.values():
                if not valid(cult):
                    continue
                hmap = getattr(cult, "hidden_affinity_by_actor_id", {}) or {}
                raw_val = hmap.get(actor_id, hmap.get(str(actor_id), 0.0))
                try:
                    val = float(raw_val or 0.0)
                except Exception:
                    val = 0.0
                if val > best_val:
                    best = cult
                    best_val = val

        return best, best_val

    def _actor_protocult_label(self, actor, none_label: str = "—") -> str:
        cult, _val = self._actor_protocult(actor)
        if cult is None:
            return none_label
        return self._cult_title_label(cult)

    def _alignment_label(self, alignment) -> str:
        return self._value_label(alignment)

    def _role_label(self, role) -> str:
        return self._value_label(role)

    def _champion_title_label(self, actor) -> str:
        title = getattr(actor, "title", None)
        if title:
            return str(title)
        if getattr(actor, "champion_of", None) is not None:
            role = self._role_label(getattr(actor, "role", None))
            god = self._deity_label(getattr(actor, "champion_of", None))
            return f"Champion of {god}" if god and god != "None" else f"Champion {role}"
        return "None"

    def _ensure_champion_title(self, actor) -> None:
        if actor is None or getattr(actor, "champion_of", None) is None:
            return
        if getattr(actor, "title", None):
            return
        role = self._role_label(getattr(actor, "role", None))
        try:
            actor.title = f"Champion {role}"
        except Exception:
            pass

    def _actor_search_text(self, actor) -> str:
        parts = [
            str(getattr(actor, "name", "")),
            str(getattr(actor, "surname", "")),
            str(actor.short_name() if hasattr(actor, "short_name") else ""),
            str(actor.full_name() if hasattr(actor, "full_name") else ""),
            str(getattr(actor, "title", "") or ""),
        ]
        return " ".join(part.lower() for part in parts if part)

    def _search_actors(self, query: str):
        q = str(query or "").strip().lower()
        if not q:
            return []
        tokens = [tok for tok in q.split() if tok]
        results = []
        seen_ids = set()
        for actor in getattr(self.sim.world, "actors", {}).values():
            hay = self._actor_search_text(actor)
            if all(tok in hay for tok in tokens):
                exact_name = q in {
                    str(getattr(actor, "name", "")).lower(),
                    str(getattr(actor, "surname", "")).lower(),
                    str(actor.short_name() if hasattr(actor, "short_name") else "").lower(),
                    str(actor.full_name() if hasattr(actor, "full_name") else "").lower(),
                }
                results.append((exact_name, actor))
                seen_ids.add(actor.id)

        for tomb in getattr(self.sim.world, "dead_actor_index", {}).values():
            name = str(tomb.get("name", ""))
            role = str(tomb.get("role", ""))
            hay = f"{name} {role}".lower()
            actor_id = int(tomb.get("id", -1))
            if actor_id in seen_ids:
                continue
            if all(tok in hay for tok in tokens):
                actor = self.sim.resolve_actor(actor_id) if hasattr(self.sim, "resolve_actor") else None
                if actor is not None:
                    exact_name = q in {name.lower(), role.lower()}
                    results.append((exact_name, actor))
                    seen_ids.add(actor_id)
        results.sort(key=lambda item: (not item[0], not getattr(item[1], "alive", False), -getattr(item[1], "reputation", 0), item[1].short_name()))
        return [actor for _exact, actor in results]

    def _actor_lookup_modal(self) -> None:
        old_nodelay = True
        was_running = self.running
        self.running = False
        query = ""
        idx = 0
        try:
            self.stdscr.nodelay(False)
            try:
                curses.curs_set(1)
            except Exception:
                pass
            while True:
                results = self._search_actors(query) if query.strip() else []
                self.stdscr.erase()
                h, w = self.stdscr.getmaxyx()
                panel_w = min(100, max(40, w - 6))
                left = max(0, (w - panel_w) // 2)
                top = max(1, h // 2 - 12)
                self._safe_addstr(top, left, "Actor Lookup", curses.A_BOLD)
                self._safe_addstr(top + 1, left, "Type first name, surname, full name, or partial. Enter opens selected. Esc closes."[:panel_w - 1])
                prompt = f"/ {query}"
                self._safe_addstr(top + 3, left, prompt[:panel_w - 1], curses.A_REVERSE)
                visible_rows = max(4, min(14, h - top - 7))
                idx = max(0, min(idx, max(0, len(results) - 1)))
                start = max(0, min(idx - visible_rows // 2, max(0, len(results) - visible_rows)))
                if query.strip() and not results:
                    self._safe_addstr(top + 5, left, "No matches."[:panel_w - 1])
                else:
                    for row, actor in enumerate(results[start:start + visible_rows], start=start):
                        y = top + 5 + (row - start)
                        marker = ">" if row == idx else " "
                        alive = "Alive" if getattr(actor, "alive", False) else "Dead "
                        role = self._actor_role_label(actor) if hasattr(self, "_actor_role_label") else getattr(getattr(actor, "role", None), "value", "?")
                        region = self.sim.world.region_name(actor.region_id) if getattr(actor, "region_id", None) in self.sim.world.regions else "?"
                        title = getattr(actor, "title", None) or ""
                        line = f"{marker} {actor.id:04d} {actor.short_name():<24.24} {alive:<5} {role:<8.8} rep={getattr(actor, 'reputation', 0):>4} {region:<14.14} {title}"
                        attr = self._actor_display_attr(actor, selected=(row == idx))
                        self._safe_addstr(y, left, line[:panel_w - 1], attr)
                count_line = f"Matches: {len(results)}" if query.strip() else "Matches: type to search"
                self._safe_addstr(min(h - 2, top + 5 + visible_rows + 1), left, count_line[:panel_w - 1], curses.A_DIM if self.has_colors else 0)
                try:
                    self.stdscr.move(top + 3, min(w - 2, left + 2 + len(query)))
                except Exception:
                    pass
                self.stdscr.refresh()
                key = self.stdscr.getch()
                if key == curses.KEY_MOUSE:
                    try:
                        _id, mx, my, _z, bstate = curses.getmouse()
                    except Exception:
                        continue
                    wheel_up = bstate & getattr(curses, "BUTTON4_PRESSED", 0)
                    wheel_down = bstate & getattr(curses, "BUTTON5_PRESSED", 0)
                    if wheel_up or wheel_down:
                        step = -3 if wheel_up else 3
                        idx = max(0, min(max(0, len(results) - 1), idx + step))
                        continue
                    left_click = (
                        bstate & getattr(curses, "BUTTON1_CLICKED", 0)
                        or bstate & getattr(curses, "BUTTON1_PRESSED", 0)
                        or bstate & getattr(curses, "BUTTON1_RELEASED", 0)
                        or bstate & getattr(curses, "BUTTON1_DOUBLE_CLICKED", 0)
                    )
                    if left_click and results:
                        row_y0 = top + 5
                        if row_y0 <= my < row_y0 + visible_rows and left <= mx <= left + panel_w:
                            actual = start + (my - row_y0)
                            if 0 <= actual < len(results):
                                idx = actual
                                actor = results[idx]
                                self._open_actor_inspector(actor)
                                self._select_region_by_id(actor.region_id)
                                self._select_actor_in_region(actor.id)
                                break
                    continue
                if key in (27,):
                    break
                if key in (10, 13, curses.KEY_ENTER):
                    if results:
                        actor = results[idx]
                        self._open_actor_inspector(actor)
                        self._select_region_by_id(actor.region_id)
                        self._select_actor_in_region(actor.id)
                    break
                if key in (curses.KEY_UP,):
                    idx = max(0, idx - 1)
                    continue
                if key in (curses.KEY_DOWN,):
                    idx = min(max(0, len(results) - 1), idx + 1)
                    continue
                if key in (curses.KEY_NPAGE,):
                    idx = min(max(0, len(results) - 1), idx + visible_rows)
                    continue
                if key in (curses.KEY_PPAGE,):
                    idx = max(0, idx - visible_rows)
                    continue
                if key in (curses.KEY_BACKSPACE, 127, 8):
                    query = query[:-1]
                    idx = 0
                    continue
                if 32 <= key <= 126:
                    query += chr(key)
                    idx = 0
        finally:
            try:
                curses.curs_set(0)
            except Exception:
                pass
            self.stdscr.nodelay(old_nodelay)
            self.running = was_running

    def _handle_actor_input(self, key: int) -> bool:
        if key in (ord('i'), ord('I'), 27):
            self._close_top_overlay()
            return True
        actor = self._inspected_actor()
        if actor is None:
            self.inspect_actor_id = None
            return False


        if key == ord('P'):
            if hasattr(self.sim, "_promote_player_champion"):
                ok, msg = self.sim._promote_player_champion(actor.id)
                if ok:
                    self._ensure_champion_title(actor)
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Champion promotion unavailable.")
            return True

        if key == ord('Y'):
            if hasattr(self.sim, "mark_actor_as_story_character"):
                ok, msg = self.sim.mark_actor_as_story_character(actor.id)
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Story marking unavailable.")
            return True

        if key == ord('T'):
            if hasattr(self.sim, "_issue_player_assassination_target"):
                ok, msg = self.sim._issue_player_assassination_target(actor.id)
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Targeting unavailable on this loaded simulator. Save/reload with current fantfarm or start a new run.")
            return True

        if key == ord('X'):
            if hasattr(self.sim, "_cancel_player_assassination_target"):
                ok, msg = self.sim._cancel_player_assassination_target(None)
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Target cancellation unavailable on this loaded simulator.")
            return True

        # Relationship/profile navigation is handled by clickable underlined actor links.
        # Keep only non-navigation inspector actions above (region jump, champion, story, page close).
        return False

    def _scroll_map(self, dy: int = 0, dx: int = 0):
        self.map_scroll_y = max(0, min(self.map_scroll_y + dy, self._last_map_max_scroll_y))
        self.map_scroll_x = max(0, min(self.map_scroll_x + dx, self._last_map_max_scroll_x))

    def _point_in_bounds(self, x: int, y: int, bounds) -> bool:
        if bounds is None:
            return False
        x1, y1, x2, y2 = bounds
        return x1 <= x <= x2 and y1 <= y <= y2

    def _scroll_region_list(self, dy: int):
        try:
            h, _w = self.stdscr.getmaxyx()
            top = 3 + len(BANNER) + 2
            bottom = h - EVENT_ROWS - 4
            visible = max(1, bottom - top - 1)
        except Exception:
            visible = 10
        max_scroll = max(0, len(self.region_ids) - visible)
        self.region_list_scroll = max(0, min(getattr(self, "region_list_scroll", 0) + dy, max_scroll))
        self.region_list_mouse_scrolled = True

    def _scroll_actor_list(self, dy: int):
        actors_here = self._actors_in_selected_region()
        visible_rows = max(1, int(getattr(self, "actor_list_visible_rows", ACTOR_PANEL_MAX_ROWS) or ACTOR_PANEL_MAX_ROWS))
        max_scroll = max(0, len(actors_here) - visible_rows)
        self.actor_list_scroll = max(0, min(getattr(self, "actor_list_scroll", 0) + dy, max_scroll))
        self.actor_list_mouse_scrolled = True

    def _scroll_god_list(self, dy: int):
        rows = self._god_rows()
        try:
            h, _w = self.stdscr.getmaxyx()
            top = 3
            bottom = h - EVENT_ROWS - 4
            max_rows = max(1, bottom - (top + 12))
        except Exception:
            max_rows = 8
        max_scroll = max(0, len(rows) - max_rows)
        self.god_scroll = max(0, min(getattr(self, "god_scroll", 0) + dy, max_scroll))
        self.god_mouse_scrolled = True

    def _handle_mouse(self):
        try:
            _id, mouse_x, mouse_y, _z, bstate = curses.getmouse()
        except Exception:
            return

        wheel_up = bstate & getattr(curses, "BUTTON4_PRESSED", 0)
        wheel_down = bstate & getattr(curses, "BUTTON5_PRESSED", 0)
        if wheel_up or wheel_down:
            dy = -3 if wheel_up else 3
            if getattr(self, "journal_mode", False):
                self.journal_scroll = max(0, int(getattr(self, "journal_scroll", 0)) + dy)
                return
            if self.god_mode and self._point_in_bounds(mouse_x, mouse_y, getattr(self, "god_panel_bounds", None)):
                self._scroll_god_list(dy)
                return
            if self._point_in_bounds(mouse_x, mouse_y, getattr(self, "actor_list_panel_bounds", None)):
                self._scroll_actor_list(dy)
                return
            if self.main_view == "list" and self._point_in_bounds(mouse_x, mouse_y, getattr(self, "region_list_panel_bounds", None)):
                self._scroll_region_list(dy)
                return
            self._scroll_map(dy, 0)
            return

        left_click = (
            bstate & getattr(curses, "BUTTON1_CLICKED", 0)
            or bstate & getattr(curses, "BUTTON1_PRESSED", 0)
            or bstate & getattr(curses, "BUTTON1_RELEASED", 0)
            or bstate & getattr(curses, "BUTTON1_DOUBLE_CLICKED", 0)
        )
        if not left_click:
            return

        for hitbox_map in (getattr(self, "_inspector_link_hitboxes", {}), getattr(self, "_social_hitboxes", {}), getattr(self, "_event_link_hitboxes", {})):
            for actor_id, (x1, y1, x2, y2) in hitbox_map.items():
                if x1 <= mouse_x <= x2 and y1 <= mouse_y <= y2:
                    actor = self.sim.resolve_actor(actor_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(actor_id)
                    if actor is not None:
                        self._open_actor_inspector(actor)
                        self._select_region_by_id(actor.region_id)
                        self._select_actor_in_region(actor.id)
                    return

        for actor_id, (x1, y1, x2, y2) in getattr(self, "_actor_hitboxes", {}).items():
            if x1 <= mouse_x <= x2 and y1 <= mouse_y <= y2:
                actor = self.sim.resolve_actor(actor_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(actor_id)
                if actor is not None and getattr(actor, "alive", False):
                    self._select_region_by_id(actor.region_id)
                    self._select_actor_in_region(actor.id)
                    self.actor_list_mouse_scrolled = False
                    if bstate & getattr(curses, "BUTTON1_DOUBLE_CLICKED", 0):
                        self._open_actor_inspector(actor)
                return

        for region_id, (x1, y1, x2, y2) in getattr(self, "_map_hitboxes", {}).items():
            if x1 <= mouse_x <= x2 and y1 <= mouse_y <= y2:
                self._select_region_by_id(region_id)
                return

    def _adjust_speed(self, delta: int):
        idx = 0
        try:
            idx = SPEED_PRESETS.index(self.ticks_per_frame)
        except ValueError:
            idx = 0
        idx = max(0, min(len(SPEED_PRESETS) - 1, idx + delta))
        self.ticks_per_frame = SPEED_PRESETS[idx]

    def draw(self):
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        current_size = (height, width)
        if self._last_screen_size != current_size:
            self._last_screen_size = current_size
            self._map_layout_cache = {}
            self._last_map_max_scroll_y = 0
            self._last_map_max_scroll_x = 0
        if height < 28 or width < 100:
            self._safe_addstr(0, 0, f"Terminal too small ({width}x{height}). Resize to at least 100x28.")
            self.stdscr.refresh()
            return

        self._active_directive_cache = self._build_directive_cache()
        self.draw_header(width)
        if self.event_focus_mode and not self.summary_mode and self.endgame_prompt is None:
            self.draw_event_focus(height, width)
        else:
            self.draw_main(height, width)
        if self.endgame_prompt is not None:
            self.draw_events(height, width)
            self.draw_endgame_prompt(height, width)
        elif self.summary_mode:
            self.draw_summary_browser(height, width)
        else:
            if not self.event_focus_mode:
                self.draw_events(height, width)
        if self.help_mode:
            self.draw_help_menu(height, width)
        self.draw_footer(height, width)
        self.stdscr.refresh()

    def _total_population(self) -> int:
        world = self.sim.world
        commoners = sum(getattr(world, "commoners_by_region", {}).values())
        # Use _living_actor_cache directly rather than building a new list via living_actors().
        living = len(getattr(world, "_living_actor_cache", None) or world.living_actors())
        return commoners + living

    def _sparkline(self, values, width: int = 24) -> str:
        if not values:
            return ""
        values = list(values)
        if width <= 0:
            return ""
        if len(values) > width:
            step = len(values) / float(width)
            values = [values[int(i * step)] for i in range(width)]
        lo = min(values)
        hi = max(values)
        if hi == lo:
            return "─" * len(values)
        chars = "▁▂▃▄▅▆▇█"
        span = hi - lo
        out = []
        for value in values:
            idx = int(round((float(value) - lo) / span * (len(chars) - 1)))
            idx = max(0, min(idx, len(chars) - 1))
            out.append(chars[idx])
        return "".join(out)

    def _history_values(self, key: str):
        history = getattr(self.sim.world, "history", None)
        if not history:
            return []
        return list(history.get(key, []) or [])

    def _draw_live_history_bar(self, y: int, width: int):
        history = getattr(self.sim.world, "history", None)
        if not history:
            return

        pop = self._history_values("total_population")
        adv = self._history_values("adventurers")
        mon = self._history_values("monsters")
        if not pop and not adv and not mon:
            return

        # Keep the live graph compact so it can survive narrower terminals.
        label_overhead = len("Pop  Adv  Mon  ") + 18
        bar_w = max(6, min(24, (width - label_overhead) // 3))
        if width < 100:
            bar_w = max(5, min(12, bar_w))

        pop_bar = self._sparkline(pop, bar_w) if pop else ""
        adv_bar = self._sparkline(adv, bar_w) if adv else ""
        mon_bar = self._sparkline(mon, bar_w) if mon else ""

        pop_last = pop[-1] if pop else 0
        adv_last = adv[-1] if adv else 0
        mon_last = mon[-1] if mon else 0
        sample_count = len(getattr(history, "get", lambda *_: [])("tick", [])) if isinstance(history, dict) else 0

        line = (
            f"Live history [{sample_count:>3}]: "
            f"Pop {pop_bar} {pop_last} | "
            f"Adv {adv_bar} {adv_last} | "
            f"Mon {mon_bar} {mon_last}"
        )
        self._safe_addstr(y, 0, line[:width - 1], curses.A_DIM if self.has_colors else 0)

    def draw_header(self, width: int):
        world = self.sim.world
        mode = "RUNNING" if self.running else "PAUSED"
        year, month, day, tod, _season = world.current_calendar()
        month_name = self.sim.MONTH_NAMES[month - 1]
        living_adv = self.sim._living_adventurer_count() if hasattr(self.sim,"_living_adventurer_count") else len(world.living_actors())
        school_kids = self.sim._school_child_count() if hasattr(self.sim, "_school_child_count") else len([a for a in world.living_actors() if getattr(a,"in_school",False)])
        living_mon = len(world.living_monsters())
        total_pop = self._total_population()
        elapsed = self._runtime_seconds()
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        runtime_str = f"{mins}m {secs}s"
        self._safe_addstr(0, 0, f"Immortal Champions v{v_info} | Tick {world.tick} | {mode} | speed {self.ticks_per_frame} t/frame | runtime {runtime_str}"[:width - 1])
        line2 = f"Year {year} {month_name} {day} | pop {total_pop} | adv {living_adv} | school {school_kids} | monsters {living_mon} | parties {len(world.parties)} | polities {len(world.polities)}"
        if self.periodic_summary_years > 0:
            line2 += f"\n | psum {self.periodic_summary_years}y"
        self._safe_addstr(1, 0, line2[:width - 1])
        if self.last_summary_path is not None:
            self._safe_addstr(2, 0, f"Last summary: {self.last_summary_path.name}"[:width - 1])
        # Permanent religious-influence tracker. It lives in the same horizontal
        # band as the logo so it remains visible in map, journal, inspector,
        # monster, and god views without competing with the event log.
        self._draw_immortal_summary(8, 0, width)

    def draw_main(self, height: int, width: int):
        content_bottom = height - EVENT_ROWS - 4

        banner_top = 3
        banner_w = min(34, max(28, width // 4))
        self.draw_banner_panel(banner_top, 0, banner_w)

        banner_bottom = banner_top + len(BANNER) + 1
        map_top = banner_bottom + 1

        # Default/fallback region-summary placement. In map mode this is
        # recalculated after the hexes are rendered so the compact region block
        # floats just to the right of the visible map instead of living at a
        # fixed offset from the banner.
        region_w = min(42, max(34, width // 4))
        region_x = min(max(banner_w + 14, width // 4 + 12), max(0, width - region_w - 2))
        inspector_base_x = region_x + region_w + 6

        if self.main_view == "map":
            self.draw_map_panel(map_top, 0, content_bottom, width, header_width=max(24, width - 2))
            bounds = self._visible_map_bounds()
            if bounds is not None:
                _x1, y1, x2, _y2 = bounds
                floated_x = x2 + 4
                if floated_x + region_w < width - 2:
                    region_x = floated_x
                    # Align near the map, but keep it clear of the banner.
                    region_top = max(banner_top, min(y1, content_bottom - 14))
                else:
                    region_top = banner_top
            else:
                region_top = banner_top
            self.draw_region_summary_compact(region_top, region_x, region_w)
            inspector_base_x = region_x + region_w + 6
        else:
            # Region list mode is now the region dossier view: compact list on
            # the left, selected-region inspector in the freed middle space.
            list_w = min(56, max(42, width // 4))
            self.draw_region_list(map_top, 0, content_bottom, list_w)
            dossier_x = list_w + 3
            dossier_w = max(40, width - dossier_x - 2)
            if dossier_w >= 36:
                self.draw_region_dossier(map_top, dossier_x, content_bottom, dossier_w)
            inspector_base_x = dossier_x + min(dossier_w, 80) + 4

        if self.inspect_actor_id is not None:
            inspector_x = max(region_x, inspector_base_x)
            inspector_w = max(72, width - inspector_x - 2)
            inspector_top = map_top
            inspector_bottom = content_bottom
            if inspector_top < inspector_bottom and inspector_w >= 28:
                self.draw_actor_inspector(inspector_top, inspector_x, inspector_bottom, inspector_w)

        if getattr(self, "monster_inspector", False):
            inspector_x = max(region_x, min(width - 64, inspector_base_x))
            inspector_w = max(54, min(width - inspector_x - 2, 78))
            inspector_top = map_top
            inspector_bottom = content_bottom
            if inspector_top < inspector_bottom and inspector_w >= 42:
                self.draw_monster_inspector(inspector_top, inspector_x, inspector_bottom, inspector_w)

        if getattr(self, "god_mode", False) and not self.summary_mode and self.endgame_prompt is None:
            # God inspector uses the same right-side lane as other inspectors.
            inspector_x = max(region_x, inspector_base_x)
            inspector_w = max(54, width - inspector_x - 2)
            inspector_top = map_top
            inspector_bottom = content_bottom
            if inspector_top < inspector_bottom and inspector_w >= 42:
                self.draw_god_ui(height, width, top=inspector_top, left=inspector_x, bottom=inspector_bottom, panel_w=inspector_w)

        if getattr(self, "journal_mode", False) and not self.summary_mode and self.endgame_prompt is None:
            # Journal uses the same right-side lane and leaves map/region context visible.
            inspector_x = max(region_x, inspector_base_x)
            inspector_w = max(54, width - inspector_x - 2)
            inspector_top = map_top
            inspector_bottom = content_bottom
            if inspector_top < inspector_bottom and inspector_w >= 42:
                self.draw_journal_panel(height, width, top=inspector_top, left=inspector_x, bottom=inspector_bottom, panel_w=inspector_w)

    def _visible_map_bounds(self):
        boxes = list(getattr(self, "_map_hitboxes", {}) or [])
        hitboxes = list((getattr(self, "_map_hitboxes", {}) or {}).values())
        if not hitboxes:
            return None
        x1 = min(box[0] for box in hitboxes)
        y1 = min(box[1] for box in hitboxes)
        x2 = max(box[2] for box in hitboxes)
        y2 = max(box[3] for box in hitboxes)
        return (x1, y1, x2, y2)

    def draw_banner_panel(self, top: int, left: int, width: int):
        self._safe_addstr(top, left, "-" * max(1, width - 1))
        if width < 24:
            return
        start_x = left + 1
        attr = curses.color_pair(6) | curses.A_BOLD if self.has_colors else curses.A_BOLD
        for i, line in enumerate(BANNER):
            self._safe_addstr(top + 1 + i, start_x, line[: max(0, width - start_x - 1)], attr)

    def draw_region_list(self, top: int, left: int, bottom: int, width: int):
        self.region_list_panel_bounds = (left, top, left + width - 1, max(top, bottom - 1))
        self._safe_addstr(top, left, "Regions")
        self._safe_addstr(top + 1, left, "-" * max(1, width - 1))
        visible_rows = max(5, bottom - top - 2)
        total = len(self.region_ids)
        max_scroll = max(0, total - visible_rows)
        self.region_list_scroll = max(0, min(getattr(self, "region_list_scroll", 0), max_scroll))
        if not getattr(self, "region_list_mouse_scrolled", False):
            if self.selected_region_index < self.region_list_scroll:
                self.region_list_scroll = self.selected_region_index
            elif self.selected_region_index >= self.region_list_scroll + visible_rows:
                self.region_list_scroll = max(0, self.selected_region_index - visible_rows + 1)
        start = self.region_list_scroll
        end_idx = min(total, start + visible_rows)
        for row, rid in enumerate(self.region_ids[start:end_idx], start=start):
            y = top + 2 + (row - start)
            region = self.sim.world.regions[rid]
            marker = ">" if row == self.selected_region_index else " "
            lean = self._region_lean(region)
            polity = self._region_polity_name(region) or "-"
            line = f"{marker} {rid:02d} {region.name[:14]:14} {lean[:4]:4} o={region.order:3} c={region.control:4} {polity[:10]}"
            attr = self._region_attr(region, selected=(row == self.selected_region_index))
            self._safe_addstr(y, left, line[:width - 1], attr)
        if total > visible_rows:
            self._safe_addstr(bottom - 1, left, f"Showing {start + 1}-{end_idx} of {total} (mouse wheel scroll)"[:width - 1], curses.A_DIM if self.has_colors else 0)

    def draw_map_panel(self, top: int, left: int, bottom: int, width: int, header_width: Optional[int] = None):
        header_width = width if header_width is None else max(1, min(width, int(header_width)))
        #title = ""
        #if self.map_color_view == "religion":
        #    title += " [religion view]"
        #self._safe_addstr(top, left, title[:header_width - 1])
        self._safe_addstr(top + 0, left, "-" * max(1, header_width - 1))
        map_top = top + 2
        map_bottom = bottom - 5
        viewport_h = max(8, map_bottom - map_top)
        viewport_w = max(24, width - 2)
        origin_x = left + 1
        self._map_hitboxes = {}

        # Render into an offscreen canvas, then show a scrollable viewport.
        layout = self._region_positions(0, 0, viewport_h, viewport_w)
        positions = layout["screen"]
        logical = layout["axial"]
        coord_to_region = {coord: rid for rid, coord in logical.items()}

        if positions:
            min_px = min(x for x, _ in positions.values())
            min_py = min(y for _, y in positions.values())
            max_px = max(x + HEX_W + 2 for x, _ in positions.values())
            max_py = max(y + HEX_H + 2 for _, y in positions.values())
        else:
            min_px = min_py = 0
            max_px = viewport_w
            max_py = viewport_h

        pad_x = 2
        pad_y = 1
        canvas_w = max(viewport_w, max_px - min_px + pad_x * 2)
        canvas_h = max(viewport_h, max_py - min_py + pad_y * 2)
        offset_x = pad_x - min_px
        offset_y = pad_y - min_py

        self._last_map_max_scroll_y = max(0, canvas_h - viewport_h)
        self._last_map_max_scroll_x = max(0, canvas_w - viewport_w)
        self.map_scroll_y = max(0, min(self.map_scroll_y, self._last_map_max_scroll_y))
        self.map_scroll_x = max(0, min(self.map_scroll_x, self._last_map_max_scroll_x))

        chars = [[" " for _ in range(canvas_w)] for _ in range(canvas_h)]
        attrs = [[0 for _ in range(canvas_w)] for _ in range(canvas_h)]
        priority = [[-1 for _ in range(canvas_w)] for _ in range(canvas_h)]

        selected_rid = self._selected_region().id if self._selected_region() is not None else None
        order = sorted(self.region_ids, key=lambda rid: (positions[rid][1], positions[rid][0], rid != selected_rid))
        for rid in order:
            region = self.sim.world.regions[rid]
            x, y = positions[rid]
            selected = rid == selected_rid
            canvas_x = x + offset_x
            canvas_y = y + offset_y
            self._stamp_big_hex(chars, attrs, priority, canvas_x, canvas_y, rid, region, selected, logical, coord_to_region)

            screen_x1 = origin_x + canvas_x - self.map_scroll_x
            screen_y1 = map_top + canvas_y - self.map_scroll_y
            screen_x2 = screen_x1 + HEX_W
            screen_y2 = screen_y1 + HEX_H
            view_x1 = origin_x
            view_y1 = map_top
            view_x2 = origin_x + viewport_w - 1
            view_y2 = map_top + viewport_h - 1
            if screen_x2 >= view_x1 and screen_x1 <= view_x2 and screen_y2 >= view_y1 and screen_y1 <= view_y2:
                self._map_hitboxes[rid] = (
                    max(screen_x1, view_x1),
                    max(screen_y1, view_y1),
                    min(screen_x2, view_x2),
                    min(screen_y2, view_y2),
                )

        for screen_row in range(viewport_h):
            canvas_row = screen_row + self.map_scroll_y
            if canvas_row < 0 or canvas_row >= canvas_h:
                continue
            col = self.map_scroll_x
            max_col = min(canvas_w, self.map_scroll_x + viewport_w)
            while col < max_col:
                attr = attrs[canvas_row][col]
                start_col = col
                buf = []
                while col < max_col and attrs[canvas_row][col] == attr:
                    buf.append(chars[canvas_row][col])
                    col += 1
                segment = ''.join(buf).rstrip()
                if segment:
                    self._safe_addstr(map_top + screen_row, origin_x + start_col - self.map_scroll_x, segment, attr)

        region = self._selected_region()
        # Map helper belongs to the main map UI only. Do not draw it behind God/Actor/Monster/summary overlays.
        overlay_open = bool(
            getattr(self, "god_mode", False)
            or getattr(self, "summary_mode", False)
            or getattr(self, "journal_mode", False)
            or getattr(self, "event_focus_mode", False)
            or getattr(self, "monster_inspector", False)
            or getattr(self, "inspect_actor_id", None) is not None
        )
        if region is not None and not overlay_open:
            info_y = map_bottom + 1
            lq, lr = logical.get(region.id, (0, 0))
            monsters = self.sim.world.monsters_in_region(region.id)
            self._safe_addstr(info_y, left, f"Neighbors: {', '.join(str(n).zfill(2) for n in region.neighbors) or 'None'} | Monsters here: {len(monsters)} | hex=({lq},{lr})"[:width - 1])
            self._safe_addstr(info_y + 1, left, self._region_dominant_faith_line(region)[:width - 1])
            self._safe_addstr(info_y + 2, left, self._region_directive_summary(region.id)[:width - 1], curses.A_BOLD if self._region_directive_agents(region.id) else 0)
            if self.map_color_view == "religion":
                legend = "Religion: player=magenta | Light=yellow | Darkness=red | Chance=green | contested=white | V toggles"
            else:
                legend = "Order: Good=green | Evil=red | Contested=yellow | Selected=cyan | V toggles"
            self._safe_addstr(info_y + 3, left, legend[:width - 1])
            if self._last_map_max_scroll_y > 0 or self._last_map_max_scroll_x > 0:
                scroll = f"Map scroll y={self.map_scroll_y}/{self._last_map_max_scroll_y} x={self.map_scroll_x}/{self._last_map_max_scroll_x} | mouse wheel"
                self._safe_addstr(info_y + 4, left, scroll[:width - 1], curses.A_DIM if self.has_colors else 0)
    def _draw_immortal_summary(self, y: int, left: int, width: int):
        try:
            # Use the sim's already-maintained god_state rather than rescanning all actors.
            god_state = getattr(self.sim.world, "god_state", None)
            if not god_state:
                immortals = summary._deity_influence_summary(self.sim)
            else:
                total = sum(getattr(st, "influence", 0) for st in god_state.values())
                immortals = [
                    (st.deity, getattr(st, "followers", 0), 0, getattr(st, "souls", 0),
                     getattr(st, "influence", 0),
                     (getattr(st, "influence", 0) / total * 100.0) if total > 0 else 0.0)
                    for st in god_state.values()
                ]
        except Exception:
            return

        parts = []
        for deity, _living, _commoners, _souls, _influence, pct in immortals:
            base_name = self._deity_name(deity) if hasattr(self, "_deity_name") else getattr(deity, "value", str(deity))
            display_name = self._deity_display_name(deity)
            parts.append((base_name, f"{display_name} {pct:4.1f}%"))

        total_len = sum(len(text) for _name, text in parts) + max(0, len(parts) - 1) * 3
        if total_len <= 0:
            return

        center_x = max(left, (width - total_len) // 2)
        min_x = left + 36
        x = max(center_x, min_x)
        if x >= width - 1:
            return

        for i, (name, text) in enumerate(parts):
            if i > 0:
                sep = " | "
                self._safe_addstr(y, x, sep[:max(0, width - x - 1)], curses.A_BOLD if self.has_colors else 0)
                x += len(sep)

            attr = curses.A_BOLD
            if self.has_colors:
                deity_obj = next((d for d in getattr(self.sim.world, "gods", []) if self._deity_name(d) == name), None)
                if deity_obj is not None and self._is_player_god(deity_obj):
                    attr |= curses.color_pair(5)
                else:
                    lname = name.lower()
                    if "darkness" in lname:
                        attr |= curses.color_pair(2)
                    elif "light" in lname:
                        attr |= curses.color_pair(3)
                    elif "chance" in lname:
                        attr |= curses.color_pair(1)

            self._safe_addstr(y, x, text[:max(0, width - x - 1)], attr)
            x += len(text)

    def _region_dominant_faith_line(self, region) -> str:
        if region is None or not hasattr(self.sim, "_region_dominant_deity"):
            return "Faith: None"
        deity, count, pct = self.sim._region_dominant_deity(region.id)
        if deity is None:
            return "Faith: None"
        name = self._deity_display_name(deity)
        return f"Faith: {name[:20]} {pct:4.1f}%"

    def _biome_profile_for_region(self, region) -> dict:
        profiles = globals().get("BIOME_PROFILES", {}) or {}
        biome = str(getattr(region, "biome", "") or "") if region is not None else ""
        profile = profiles.get(biome) or profiles.get(biome.title()) or profiles.get(biome.replace("_", " ").title())
        return profile if isinstance(profile, dict) else {}

    def _biome_rating_label(self, value) -> str:
        try:
            v = int(value)
        except Exception:
            return "Unknown"
        if v >= 80:
            return f"Very High ({v})"
        if v >= 60:
            return f"High ({v})"
        if v >= 40:
            return f"Medium ({v})"
        if v >= 20:
            return f"Low ({v})"
        return f"Very Low ({v})"

    def _biome_flavor_lines(self, region, width: int) -> list:
        profile = self._biome_profile_for_region(region)
        if not profile:
            return []
        lines = []
        desc = str(profile.get("description", "") or "").strip()
        if desc:
            lines.append(desc)
        lines.append(f"Hardship: {self._biome_rating_label(profile.get('hardship', 45))}")
        lines.append(f"Monster pressure: {self._biome_rating_label(profile.get('monster_pressure', 45))}")
        lines.append(f"Settlement appeal: {self._biome_rating_label(profile.get('settlement_appeal', 50))}")
        lines.append(f"Adventure appeal: {self._biome_rating_label(profile.get('adventure_appeal', 50))}")
        yields = profile.get("yields")
        if isinstance(yields, dict) and yields:
            pieces = []
            for key in ("grain", "livestock", "wood", "metal"):
                if key in yields:
                    pieces.append(f"{key} x{float(yields.get(key, 1.0)):.2f}")
            if pieces:
                lines.append("Yield mods: " + ", ".join(pieces))
        return lines

    def _region_stockpile_lines(self, region, compact: bool = False) -> list:
        stock = getattr(region, "stockpile", {}) if region is not None else {}
        if not isinstance(stock, dict):
            stock = {}
        grain = int(stock.get("grain", 0))
        livestock = int(stock.get("livestock", 0))
        wood = int(stock.get("wood", 0))
        metal = int(stock.get("metal", 0))
        weapons = int(stock.get("weapons", 0))
        armor = int(stock.get("armor", 0))
        if compact:
            return [f"Food: grain {grain} livestock {livestock}", f"Stock: wood {wood} metal {metal} W/A {weapons}/{armor}"]
        return [
            f"Grain: {grain}",
            f"Livestock: {livestock}",
            f"Wood: {wood}",
            f"Metal: {metal}",
            f"Weapons: {weapons}",
            f"Armor: {armor}",
        ]

    def _region_polity(self, region):
        if region is None:
            return None
        polity_id = getattr(region, "polity_id", None)
        if polity_id is None:
            return None
        return getattr(self.sim.world, "polities", {}).get(polity_id)

    def _region_ruler_actor(self, region):
        if region is None:
            return None
        ruler_id = getattr(region, "ruler_id", None)
        if ruler_id is None:
            polity = self._region_polity(region)
            ruler_id = getattr(polity, "ruler_id", None) if polity is not None else None
        if ruler_id is None:
            return None
        return self.sim.resolve_actor(ruler_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(ruler_id)

    def _parties_in_region(self, region_id: int):
        parties = []
        world = self.sim.world
        for party in getattr(world, "parties", {}).values():
            member_ids = list(getattr(party, "member_ids", []) or [])
            live_members = [world.actors.get(mid) for mid in member_ids if mid in world.actors]
            live_members = [a for a in live_members if a is not None and getattr(a, "alive", False)]
            if not live_members:
                continue
            if any(getattr(a, "region_id", None) == region_id for a in live_members):
                parties.append((party, live_members))
        parties.sort(key=lambda item: (-sum(getattr(a, "power_rating", lambda: 0)() for a in item[1]), getattr(item[0], "name", "")))
        return parties

    def _region_faith_breakdown_lines(self, region, width: int, limit: int = 5):
        faith = getattr(self.sim.world, "commoner_faith_by_region", {}).get(region.id, {}) if region is not None else {}
        if not faith:
            return ["Faith: None"]
        total = sum(int(v or 0) for v in faith.values()) or 1
        ranked = sorted(faith.items(), key=lambda item: int(item[1] or 0), reverse=True)
        lines = []
        for deity, count in ranked[:limit]:
            if int(count or 0) <= 0:
                continue
            name = self._deity_display_name(deity)
            pct = float(count) / total * 100.0
            lines.append(f"  {name[:26]:26} {pct:5.1f}%")
        return lines or ["  None"]

    def _recent_region_event_lines(self, region, limit: int = 5):
        if region is None:
            return []
        name = str(getattr(region, "name", "") or "")
        if not name:
            return []
        found = []
        for event in reversed(self.last_events):
            text = self._event_text(event)
            if name in text:
                found.append(text)
                if len(found) >= limit:
                    break
        return list(reversed(found))

    def _section_header_attr(self, title: str) -> int:
        attr = curses.A_BOLD
        if not self.has_colors:
            return attr
        label = str(title or "").upper()
        if "CIVIC" in label:
            return attr | curses.color_pair(6)
        if "POLITY" in label:
            return attr | curses.color_pair(4)
        if "ECONOMY" in label:
            return attr | curses.color_pair(3)
        if "MILITARY" in label:
            return attr | curses.color_pair(2)
        if "RELIGION" in label:
            return attr | curses.color_pair(5)
        if "THREAT" in label:
            return attr | curses.color_pair(2)
        if "EVENT" in label:
            return attr | curses.color_pair(1)
        if "LIVING ACTORS" in label:
            return attr | curses.color_pair(5)
        # Actor / journal inspector sections. Keep this display-only and reuse
        # the existing palette so no global color behavior changes.
        if label in {"IDENTITY", "TOP SONGS"}:
            return attr | curses.color_pair(4)
        if label in {"STATUS", "METRICS"}:
            return attr | curses.color_pair(1)
        if label in {"STATS", "SONG TYPES"}:
            return attr | curses.color_pair(3)
        if label in {"CAREER", "FAMOUS BARDS"}:
            return attr | curses.color_pair(5)
        if label in {"FAMILY", "CULTS & LEGENDS"}:
            return attr | curses.color_pair(6)
        if label in {"RELATIONS", "STORY NOTES"}:
            return attr | curses.color_pair(2)
        return attr

    def _inspector_title_attr(self, kind: str = "") -> int:
        attr = curses.A_BOLD
        if not self.has_colors:
            return attr
        label = str(kind or "").lower()
        if label == "journal":
            return attr | curses.color_pair(5)
        if label == "actor":
            return attr | curses.color_pair(4)
        return attr | curses.color_pair(6)

    def _journal_row_attr(self, label: str = "") -> int:
        if not self.has_colors:
            return 0
        low = str(label or "").lower()
        if "song" in low or "ballad" in low or "hymn" in low:
            return curses.color_pair(3)
        if "cult" in low or "legend" in low:
            return curses.color_pair(5)
        if "bard" in low or "performance" in low:
            return curses.color_pair(4)
        return 0

    def _draw_section_header(self, y: int, x: int, width: int, title: str) -> int:
        attr = self._section_header_attr(title)
        self._safe_addstr(y, x, str(title)[:width - 1], attr)
        y += 1
        self._safe_addstr(y, x, "-" * max(1, width - 1), attr if self.has_colors else curses.A_DIM)
        return y + 1

    def _polity_relation_values(self, polity, names):
        """Return raw relation values from the first populated polity relation field."""
        if polity is None:
            return []
        for name in names:
            raw = getattr(polity, name, None)
            if not raw:
                continue
            if isinstance(raw, dict):
                vals = list(raw.keys())
            elif isinstance(raw, (list, tuple, set)):
                vals = list(raw)
            else:
                vals = [raw]
            if vals:
                return vals
        return []

    def _polity_display_name(self, value) -> str:
        """Resolve a polity id/object/string into a display name."""
        if value is None:
            return "None"
        if hasattr(value, "name"):
            return str(getattr(value, "name", value))
        polities = getattr(self.sim.world, "polities", {}) or {}
        try:
            pid = int(value)
            polity = polities.get(pid)
            return str(getattr(polity, "name", pid)) if polity is not None else f"P{pid}"
        except Exception:
            return str(value)

    def _format_polity_relation_names(self, values, limit: int = 3) -> str:
        vals = list(values or [])
        if not vals:
            return "-"
        names = [self._polity_display_name(v) for v in vals]
        shown = names[:max(1, limit)]
        if len(names) > len(shown):
            shown.append(f"+{len(names) - len(shown)} more")
        return ", ".join(shown)

    def draw_region_actor_list_section(self, top: int, left: int, bottom: int, width: int):
        """Draw selectable living actors for the selected region inside region dossier.

        This replaces the old top-right main-map actor pane. It preserves the
        existing actor hitboxes, actor scroll state, and Enter/click behavior.
        """
        y = top
        actors_here = self._actors_in_selected_region()
        self._actor_hitboxes = {}
        self.actor_list_panel_bounds = None
        if width < 24 or y >= bottom:
            return y
        self.actor_list_panel_bounds = (left, top, left + width - 1, max(top, bottom - 1))
        y = self._draw_section_header(y, left, width, f"LIVING ACTORS HERE ({len(actors_here)})")
        visible_rows = max(1, bottom - y - 1)
        self.actor_list_visible_rows = visible_rows
        total = len(actors_here)
        max_scroll = max(0, total - visible_rows)
        self.actor_list_scroll = max(0, min(getattr(self, "actor_list_scroll", 0), max_scroll))

        if total > 0:
            self.selected_actor_index = max(0, min(self.selected_actor_index, total - 1))
            if not getattr(self, "actor_list_mouse_scrolled", False):
                if self.selected_actor_index < self.actor_list_scroll:
                    self.actor_list_scroll = self.selected_actor_index
                elif self.selected_actor_index >= self.actor_list_scroll + visible_rows:
                    self.actor_list_scroll = max(0, self.selected_actor_index - visible_rows + 1)

        start = self.actor_list_scroll
        end = min(total, start + visible_rows)
        for list_index, actor in enumerate(actors_here[start:end], start=start):
            if y >= bottom:
                break
            marker = ">" if list_index == self.selected_actor_index else " "
            retired = "RET" if getattr(actor, "retired", False) and actor.alive else "   "
            champ = "*" if getattr(actor, "champion_of", None) is not None else " "
            line = (
                f"{marker} {champ}{actor.id:04d} {retired} {self._role_label(getattr(actor, 'role', None))[:1]} "
                f"{actor.short_name()[:20]:20} {self._alignment_label(getattr(actor, 'alignment', None))[:11]:11} "
                f"rep={actor.reputation:4} lvl={getattr(actor, 'level', 1):2} hp={actor.hp:>3}/{actor.max_hp:<3}"
            )
            attr = self._actor_display_attr(actor, selected=(list_index == self.selected_actor_index))
            self._safe_addstr(y, left, line[:width - 1], attr)
            self._actor_hitboxes[actor.id] = (left, y, left + min(width - 2, len(line)), y)
            y += 1

        if total > visible_rows and y < bottom:
            self._safe_addstr(y, left, f"Showing {start + 1}-{end} of {total} (click select | wheel scroll)"[:width - 1], curses.A_DIM if self.has_colors else 0)
            y += 1
        elif total == 0 and y < bottom:
            self._safe_addstr(y, left, "None.")
            y += 1
        return y

    def _party_kind_label(self, party) -> str:
        """Return a compact visible label for region dossier party rows."""
        if party is None:
            return "PARTY"
        goal = str(getattr(party, "goal", "") or "").lower()
        if goal == "military":
            return "MIL"
        # Some older saves may not reliably preserve party.goal. Treat any party
        # referenced by a polity's military roster as military.
        pid = getattr(party, "id", None)
        for polity in getattr(self.sim.world, "polities", {}).values():
            if pid in (getattr(polity, "military_party_ids", []) or []):
                return "MIL"
        if bool(getattr(party, "is_large_group", False)):
            return "GROUP"
        return "PARTY"

    def draw_region_dossier(self, top: int, left: int, bottom: int, width: int):
        self._inspector_link_hitboxes = {}
        region = self._selected_region()
        if region is None:
            self._safe_addstr(top, left, "REGION DOSSIER: None"[:width - 1])
            return

        y = top
        world = self.sim.world
        commoners = int(getattr(world, "commoners_by_region", {}).get(region.id, 0) or 0)
        actors_here = self._actors_in_selected_region()
        adventurers = [a for a in actors_here if getattr(a, "alive", False) and a.is_adventurer()]
        monsters = world.monsters_in_region(region.id)
        polity = self._region_polity(region)
        ruler = self._region_ruler_actor(region)
        parties = self._parties_in_region(region.id)

        title = f"REGION DOSSIER: {region.name}"
        self._safe_addstr(y, left, title[:width - 1], curses.A_BOLD if self.has_colors else 0); y += 1
        self._safe_addstr(y, left, "=" * max(1, width - 1)); y += 1

        col_gap = 3
        use_three_cols = width >= 118
        if use_three_cols:
            col_w = max(28, (width - col_gap * 2) // 3)
            left_w = col_w
            mid_x = left + left_w + col_gap
            mid_w = col_w
            right_x = mid_x + mid_w + col_gap
            right_w = max(28, width - left_w - mid_w - col_gap * 2)
            start_y = y
        else:
            left_w = max(30, (width - col_gap) // 2)
            mid_x = left + left_w + col_gap
            mid_w = max(28, width - left_w - col_gap)
            right_x = mid_x
            right_w = mid_w
            start_y = y

        # Left column: civic/core state, polity, economy.
        ly = start_y
        ly = self._draw_section_header(ly, left, left_w, "CIVIC")
        civic_lines = [
            f"Biome: {getattr(region, 'biome', '-')}",
        ]
        civic_lines.extend(self._biome_flavor_lines(region, left_w))
        civic_lines.extend([
            f"Commoners: {commoners}",
            f"Adventurers: {len(adventurers)}",
            f"Order: {getattr(region, 'order', 0)}",
            f"Control: {getattr(region, 'control', 0)}",
            f"Danger: {getattr(region, 'danger', 0)}",
            f"Lean: {self._region_lean(region)}",
            self._region_directive_summary(region.id),
        ])
        for line in civic_lines:
            ly = self._draw_text_line(ly, left, left_w, line)
        ly += 1

        ly = self._draw_section_header(ly, left, left_w, "POLITY")
        if polity is None:
            ly = self._draw_text_line(ly, left, left_w, "Polity: None")
            ly = self._draw_text_line(ly, left, left_w, f"Local ruler: {ruler.short_name() if ruler is not None and getattr(ruler, 'alive', False) else 'None'}")
            if ruler is not None:
                ly = self._draw_actor_link_line(ly, left, left_w, "Spouse", getattr(ruler, "spouse_id", None))
                child_ids = list(getattr(ruler, "children_ids", []) or [])
                ly = self._draw_text_line(ly, left, left_w, f"Children: {len(child_ids)}")
                for child_id in child_ids[:3]:
                    ly = self._draw_actor_link_line(ly, left + 2, max(1, left_w - 2), "child", child_id)
                if len(child_ids) > 3:
                    ly = self._draw_text_line(ly, left + 2, max(1, left_w - 2), f"+{len(child_ids) - 3} more children")
            ly = self._draw_text_line(ly, left, left_w, "Allies: -")
            ly = self._draw_text_line(ly, left, left_w, "Enemies: -")
        else:
            allies = self._polity_relation_values(polity, ("allies", "ally_ids", "allied_polity_ids", "allied_polities"))
            rivals = self._polity_relation_values(polity, ("rivals", "enemies", "enemy_ids", "enemy_polity_ids", "war_targets"))
            polity_ruler_id = getattr(polity, "ruler_id", None)
            polity_ruler = self.sim.resolve_actor(polity_ruler_id) if polity_ruler_id is not None and hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(polity_ruler_id)
            ly = self._draw_text_line(ly, left, left_w, f"Polity: {getattr(polity, 'name', 'Unnamed')}")
            ly = self._draw_actor_link_line(ly, left, left_w, "Ruler", polity_ruler_id, "None")
            if polity_ruler is not None:
                ly = self._draw_actor_link_line(ly, left, left_w, "Spouse", getattr(polity_ruler, "spouse_id", None))
                child_ids = list(getattr(polity_ruler, "children_ids", []) or [])
                ly = self._draw_text_line(ly, left, left_w, f"Children: {len(child_ids)}")
                for child_id in child_ids[:3]:
                    ly = self._draw_actor_link_line(ly, left + 2, max(1, left_w - 2), "child", child_id)
                if len(child_ids) > 3:
                    ly = self._draw_text_line(ly, left + 2, max(1, left_w - 2), f"+{len(child_ids) - 3} more children")
            ly = self._draw_text_line(ly, left, left_w, f"Alignment: {self._alignment_label(getattr(polity, 'alignment', None))}")
            ly = self._draw_text_line(ly, left, left_w, f"Stability: {getattr(polity, 'stability', '-')}")
            ly = self._draw_text_line(ly, left, left_w, f"Legitimacy: {getattr(polity, 'legitimacy', '-')}")
            ly = self._draw_text_line(ly, left, left_w, f"Allies: {self._format_polity_relation_names(allies)}")
            ly = self._draw_text_line(ly, left, left_w, f"Enemies: {self._format_polity_relation_names(rivals)}")
        ly += 1

        ly = self._draw_section_header(ly, left, left_w, "ECONOMY")
        for line in self._region_stockpile_lines(region, compact=False):
            ly = self._draw_text_line(ly, left, left_w, line)
        surplus = getattr(region, "surplus", None)
        deficits = getattr(region, "deficits", None)
        imports = getattr(region, "imports", None)
        exports = getattr(region, "exports", None)
        if isinstance(surplus, dict) and surplus:
            ly = self._draw_text_line(ly, left, left_w, "Surplus: " + ", ".join(f"{k}={v}" for k, v in list(surplus.items())[:4]))
        if isinstance(deficits, dict) and deficits:
            ly = self._draw_text_line(ly, left, left_w, "Deficits: " + ", ".join(f"{k}={v}" for k, v in list(deficits.items())[:4]))
        if imports:
            ly = self._draw_text_line(ly, left, left_w, "Imports: " + str(imports)[:left_w - 10])
        if exports:
            ly = self._draw_text_line(ly, left, left_w, "Exports: " + str(exports)[:left_w - 10])

        # Middle column: military/religion/threats/events.
        my = start_y
        my = self._draw_section_header(my, mid_x, mid_w, "MILITARY")
        if not parties:
            my = self._draw_text_line(my, mid_x, mid_w, "No active parties here.")
        else:
            for party, members in parties[:6]:
                leader = world.actors.get(getattr(party, "leader_id", None))
                power = sum(getattr(a, "power_rating", lambda: 0)() for a in members)
                pname = getattr(party, "name", None) or f"Party {getattr(party, 'id', '?')}"
                leader_name = leader.short_name() if leader is not None else "None"
                kind_label = self._party_kind_label(party)
                polity = world.polities.get(getattr(party, "polity_id", None)) if getattr(party, "polity_id", None) is not None else None
                owner = getattr(polity, "name", None) or "independent"
                my = self._draw_text_line(my, mid_x, mid_w, f"[{kind_label:<5}] {pname[:22]:22} str={power:3} n={len(members):2}")
                my = self._draw_text_line(my, mid_x + 2, max(1, mid_w - 2), f"leader: {leader_name} | owner: {owner[:18]}")
        my += 1

        my = self._draw_section_header(my, mid_x, mid_w, "RELIGION")
        for line in self._region_faith_breakdown_lines(region, mid_w):
            my = self._draw_text_line(my, mid_x, mid_w, line)
        my += 1

        my = self._draw_section_header(my, mid_x, mid_w, "THREATS")
        my = self._draw_text_line(my, mid_x, mid_w, f"Local monsters: {self._monster_summary(monsters)}")
        siege = getattr(region, "under_siege_by", None)
        if siege is not None:
            siege_polity = world.polities.get(siege)
            my = self._draw_text_line(my, mid_x, mid_w, f"Under siege by: {getattr(siege_polity, 'name', siege)}")
            my = self._draw_text_line(my, mid_x, mid_w, f"Siege progress: {getattr(region, 'siege_progress', 0):.1f}")
        else:
            my = self._draw_text_line(my, mid_x, mid_w, "Siege: none")
        my += 1

        # Living actors are now part of the expanded region dossier only.
        if use_three_cols:
            ay = self.draw_region_actor_list_section(start_y, right_x, bottom - 2, right_w)
            event_x, event_w, event_y = mid_x, mid_w, my
        else:
            # In narrower terminals, put actors below the middle diagnostic blocks.
            actor_top = my
            actor_bottom = max(actor_top + 5, bottom - 8)
            ay = self.draw_region_actor_list_section(actor_top, mid_x, actor_bottom, mid_w)
            event_x, event_w, event_y = mid_x, mid_w, ay + 1

        if event_y < bottom - 2:
            event_y = self._draw_section_header(event_y, event_x, event_w, "RECENT REGION EVENTS")
            recent = self._recent_region_event_lines(region, limit=max(3, bottom - event_y - 1))
            if not recent:
                event_y = self._draw_text_line(event_y, event_x, event_w, "None in recent buffer.")
            else:
                for line in recent:
                    if event_y >= bottom:
                        break
                    event_y = self._draw_text_line(event_y, event_x, event_w, line)

        if bottom > top:
            hint = "c returns to map | arrows select region | PgUp/PgDn/Home/End select actor | Enter/i inspect"
            self._safe_addstr(bottom - 1, left, hint[:width - 1], curses.A_DIM if self.has_colors else 0)

    def draw_region_summary_compact(self, top: int, left: int, width: int):
        region = self._selected_region()
        if region is None:
            self._safe_addstr(top, left, "Region: None"[:width - 1])
            return top + 1

        polity_name = self._region_polity_name(region) or "None"
        ruler_name = self._region_ruler_name(region)
        commoners = getattr(self.sim.world, "commoners_by_region", {}).get(region.id, 0)
        local_monsters = self.sim.world.monsters_in_region(region.id)
        monster_summary = self._monster_summary(local_monsters)

        lines = [
            f"Region: {region.name}",
            "-" * max(1, width - 1),
            f"Biome: {str(region.biome)[:14]:14} Ruler: {ruler_name[:14]}",
            f"Order: {region.order:<3}       Polity: {polity_name[:16]}",
            f"Control: {region.control:<4}    Commoners: {commoners}",
            f"Danger: {region.danger:<3}      Monsters: {monster_summary[:18]}",
            f"Lean: {self._region_lean(region)}",
            self._region_dominant_faith_line(region),
            self._region_directive_summary(region.id),
        ]
        lines.extend(self._region_stockpile_lines(region, compact=True))
        y = top
        for line in lines:
            self._safe_addstr(y, left, line[:width - 1])
            y += 1
        return y

    def draw_region_summary(self, top: int, left: int, bottom: int, width: int):
        y = top
        region = self._selected_region()
        if region is None:
            self._safe_addstr(y, left, "No region selected.")
            return y + 1

        self._safe_addstr(y, left, f"Region: {region.name}")
        y += 1
        self._safe_addstr(y, left, "-" * max(1, width - 1))
        y += 1

        polity_name = self._region_polity_name(region) or "None"
        ruler_name = self._region_ruler_name(region)
        commoners = getattr(self.sim.world, "commoners_by_region", {}).get(region.id, 0)
        local_monsters = self.sim.world.monsters_in_region(region.id)
        monster_summary = self._monster_summary(local_monsters)

        lines = [
            f"Biome: {region.biome}",
            f"Order: {region.order}",
            f"Control: {region.control}",
            f"Danger: {region.danger}",
            f"Lean: {self._region_lean(region)}",
            self._region_dominant_faith_line(region),
            f"Ruler: {ruler_name}",
            f"Polity: {polity_name}",
            f"Commoners: {commoners}",
            f"Monsters: {monster_summary}",
        ]
        lines.extend(self._region_stockpile_lines(region, compact=False))
        if getattr(region, "under_siege_by", None) is not None:
            polity = self.sim.world.polities.get(region.under_siege_by)
            siege_name = polity.name if polity is not None else str(region.under_siege_by)
            lines.append(f"Under siege by: {siege_name}")
            lines.append(f"Siege progress: {getattr(region, 'siege_progress', 0):.1f}")

        max_lines = max(1, bottom - y + 1)
        for line in lines[:max_lines]:
            self._safe_addstr(y, left, line[:width - 1])
            y += 1
        return y

    def _actor_display_attr(self, actor, selected: bool = False) -> int:
        """Color actor rows by special status first, then class.

        Precedence:
        1. .stri/story actors = bold white
        2. champions = yellow
        3. class color
        """
        attr = curses.A_REVERSE if selected else 0
        if not self.has_colors:
            if getattr(actor, "is_story_actor", False):
                return attr | curses.A_BOLD
            return attr

        if getattr(actor, "champion_of", None) is not None:
            attr |= curses.color_pair(3) | curses.A_BOLD
            return attr
        if getattr(actor, "is_story_actor", False):
            attr |= curses.color_pair(6) | curses.A_BOLD
            return attr

        role_value = getattr(getattr(actor, "role", None), "value", "").lower()
        if role_value == "fighter":
            attr |= curses.color_pair(5)  # magenta
        elif role_value == "warden":
            attr |= curses.color_pair(1)  # green
        elif role_value == "bard":
            attr |= curses.color_pair(2)  # red
        elif role_value == "wizard":
            attr |= curses.color_pair(4)  # cyan
        return attr

    def draw_actor_list_panel(self, top: int, left: int, bottom: int, width: int):
        y = top
        actors_here = self._actors_in_selected_region()
        self._actor_hitboxes = {}
        self.actor_list_panel_bounds = None
        if width < 20 or y >= bottom:
            return y
        self.actor_list_panel_bounds = (left, top, left + width - 1, max(top, bottom - 1))
        self._safe_addstr(y, left, f"Living actors here ({len(actors_here)}):")
        y += 1
        self._safe_addstr(y, left, "-" * max(1, width - 1))
        y += 1
        visible_rows = min(ACTOR_PANEL_MAX_ROWS, max(1, bottom - y - 1))
        self.actor_list_visible_rows = visible_rows
        total = len(actors_here)
        max_scroll = max(0, total - visible_rows)
        self.actor_list_scroll = max(0, min(getattr(self, "actor_list_scroll", 0), max_scroll))

        if total > 0:
            self.selected_actor_index = max(0, min(self.selected_actor_index, total - 1))
            if not getattr(self, "actor_list_mouse_scrolled", False):
                if self.selected_actor_index < self.actor_list_scroll:
                    self.actor_list_scroll = self.selected_actor_index
                elif self.selected_actor_index >= self.actor_list_scroll + visible_rows:
                    self.actor_list_scroll = max(0, self.selected_actor_index - visible_rows + 1)

        start = self.actor_list_scroll
        end = min(total, start + visible_rows)
        for list_index, actor in enumerate(actors_here[start:end], start=start):
            marker = ">" if list_index == self.selected_actor_index else " "
            retired = "RET" if getattr(actor, "retired", False) and actor.alive else "   "
            champ = "*" if getattr(actor, "champion_of", None) is not None else " "
            line = (
                f"{marker} {champ}{actor.id:04d} {retired} {self._role_label(getattr(actor, 'role', None))[:1]} {actor.short_name()[:22]:22} "
                f"{self._alignment_label(getattr(actor, 'alignment', None))[:13]:13} rep={actor.reputation:4} lvl={getattr(actor, 'level', 1):2} "
                f"hp={actor.hp:>4}/{actor.max_hp:<4}"
            )
            attr = self._actor_display_attr(actor, selected=(list_index == self.selected_actor_index))
            self._safe_addstr(y, left, line[:width - 1], attr)
            self._actor_hitboxes[actor.id] = (left, y, left + min(width - 2, len(line)), y)
            y += 1

        if total > visible_rows and y < bottom:
            self._safe_addstr(y, left, f"Showing {start + 1}-{end} of {total}  (click select | wheel scroll)"[:width - 1], curses.A_DIM if self.has_colors else 0)
        return y


    def draw_monster_inspector(self, top: int, left: int, bottom: int, width: int):
        monsters = self._living_monsters_sorted()
        self._safe_addstr(top, left, f"Monster Inspector | live={len(monsters)}")
        self._safe_addstr(top + 1, left, "-" * max(1, width - 1))
        if not monsters:
            self._safe_addstr(top + 2, left, "No live monsters abroad.")
            return
        self.monster_selected_index = max(0, min(int(getattr(self, "monster_selected_index", 0)), len(monsters) - 1))
        list_w = max(22, min(36, width // 2))
        rows = max(1, bottom - top - 3)
        if self.monster_selected_index < self.monster_scroll:
            self.monster_scroll = self.monster_selected_index
        if self.monster_selected_index >= self.monster_scroll + rows:
            self.monster_scroll = self.monster_selected_index - rows + 1
        self.monster_scroll = max(0, min(int(getattr(self, "monster_scroll", 0)), max(0, len(monsters) - rows)))
        y = top + 2
        for idx, monster in enumerate(monsters[self.monster_scroll:self.monster_scroll + rows], start=self.monster_scroll):
            marker = ">" if idx == self.monster_selected_index else " "
            kind = getattr(getattr(monster, "kind", None), "value", str(getattr(monster, "kind", "?")))
            region = self.sim.world.region_name(getattr(monster, "region_id", -1))
            line = f"{marker} {getattr(monster, 'name', '?')} [{kind}] @ {region}"
            attr = curses.A_REVERSE if idx == self.monster_selected_index else 0
            self._safe_addstr(y, left, line[:list_w - 1], attr)
            y += 1
        monster = monsters[self.monster_selected_index]
        x = left + list_w + 2
        y = top + 2
        detail_w = max(10, width - list_w - 3)
        kind = getattr(getattr(monster, "kind", None), "value", str(getattr(monster, "kind", "?")))
        self._draw_text_line(y, x, detail_w, f"Name: {getattr(monster, 'name', '?')}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Kind: {kind}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Region: {self.sim.world.region_name(getattr(monster, 'region_id', -1))}"); y += 1
        birth_tick = int(getattr(monster, "birth_tick", 0) or 0)
        self._draw_text_line(y, x, detail_w, f"Appeared: {self._format_tick_timestamp(birth_tick)}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Age: {self._monster_age_status(monster)}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Power: {getattr(monster, 'power', 0)} base / {monster.effective_power()} effective"); y += 1
        self._draw_text_line(y, x, detail_w, f"XP: {getattr(monster, 'monster_xp', 0)} | Horde: {getattr(monster, 'horde_size', 1)}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Stats: hostility {getattr(monster, 'hostility', 0)} cha {getattr(monster, 'charisma', 0)} int {getattr(monster, 'intelligence', 0)}"); y += 1
        if getattr(monster, "dragon_color", None):
            self._draw_text_line(y, x, detail_w, f"Dragon: {getattr(monster, 'dragon_color', '-')} / {getattr(monster, 'dragon_temperament', '-')}"); y += 1
        if getattr(monster, "giant_temperament", None) and kind == "Giant":
            self._draw_text_line(y, x, detail_w, f"Giant: {getattr(monster, 'giant_temperament', '-')}"); y += 1
        patron_id = getattr(monster, "patron_actor_id", None)
        patron = self.sim.world.actors.get(patron_id) if patron_id is not None else None
        self._draw_text_line(y, x, detail_w, f"Patron: {patron.short_name() if patron is not None else '-'}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Deity: {self._deity_label(getattr(monster, 'patron_deity', None))}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Commoners: killed {getattr(monster, 'monster_kills_commoners', 0)} / scattered {getattr(monster, 'monster_scattered_commoners', 0)}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Adventurers killed: {getattr(monster, 'monster_kills_adventurers', 0)}"); y += 1
        self._draw_text_line(y, x, detail_w, f"Raids: {getattr(monster, 'monster_raids', 0)}"); y += 1
        retreat = int(getattr(monster, "retreat_until_tick", -1) or -1)
        provoked = int(getattr(monster, "provoked_until_tick", -1) or -1)
        now = int(getattr(self.sim.world, "tick", 0) or 0)
        status = []
        if retreat > now:
            status.append(f"retreat {retreat - now}t")
        if provoked > now:
            status.append(f"provoked {provoked - now}t")
        self._draw_text_line(y, x, detail_w, f"State: {', '.join(status) if status else 'active'}"); y += 1

    def _actor_display_name_by_id(self, actor_id, fallback: str = "Unknown") -> str:
        if actor_id is None:
            return fallback
        actor = self.sim.resolve_actor(actor_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(actor_id)
        if actor is not None:
            return actor.short_name() if hasattr(actor, "short_name") else str(getattr(actor, "name", actor_id))
        tomb = (getattr(self.sim.world, "dead_actor_index", {}) or {}).get(actor_id)
        if isinstance(tomb, dict):
            return str(tomb.get("name", fallback))
        return fallback

    def _song_type_label(self, song) -> str:
        return str(getattr(song, "song_type", getattr(song, "type", "unknown")) or "unknown").replace("_", " ").title()

    def _song_subject_label(self, song) -> str:
        subject_deity = getattr(song, "subject_deity", None)
        if subject_deity is not None:
            return self._deity_name(subject_deity) if hasattr(self, "_deity_name") else str(subject_deity)
        names = []
        for aid in list(getattr(song, "subject_actor_ids", []) or [])[:2]:
            names.append(self._actor_display_name_by_id(aid, "Unknown"))
        relic_id = getattr(song, "subject_relic_id", None)
        if relic_id is not None:
            names.append(self._relic_name(relic_id))
        monster_id = getattr(song, "subject_monster_id", None)
        if monster_id is not None:
            monster = getattr(self.sim.world, "monsters", {}).get(monster_id)
            names.append(getattr(monster, "name", f"monster {monster_id}"))
        text = ", ".join([n for n in names if n])
        if text:
            return text
        return str(getattr(song, "subject_event", "") or "Unknown")

    def _journal_songs(self):
        songs = [song for song in getattr(self.sim.world, "songs", {}).values() if not getattr(song, "forgotten", False)]
        songs.sort(key=lambda song: (
            float(getattr(song, "historical_weight", 0.0) or 0.0),
            float(getattr(song, "popularity", 0.0) or 0.0),
            int(getattr(song, "performances", 0) or 0),
        ), reverse=True)
        return songs

    def _journal_bards(self):
        world = self.sim.world
        bard_ids = set()
        for actor in getattr(world, "actors", {}).values():
            try:
                if self._actor_role_label(actor) == "Bard":
                    bard_ids.add(actor.id)
            except Exception:
                pass
        for song in getattr(world, "songs", {}).values():
            cid = getattr(song, "composer_id", None)
            if cid is not None:
                bard_ids.add(cid)
            for pid in getattr(song, "performer_actor_ids", set()) or set():
                bard_ids.add(pid)
        rows = []
        songs = list(getattr(world, "songs", {}).values())
        for aid in bard_ids:
            actor = self.sim.resolve_actor(aid) if hasattr(self.sim, "resolve_actor") else world.actors.get(aid)
            name = actor.short_name() if actor is not None else self._actor_display_name_by_id(aid, f"Bard {aid}")
            alive = bool(getattr(actor, "alive", False)) if actor is not None else False
            rep = int(getattr(actor, "reputation", 0) or 0) if actor is not None else 0
            composed = sum(1 for song in songs if getattr(song, "composer_id", None) == aid and not getattr(song, "forgotten", False))
            performed = sum(1 for song in songs if aid in (getattr(song, "performer_actor_ids", set()) or set()) and not getattr(song, "forgotten", False))
            known = len(getattr(actor, "known_song_ids", []) or []) if actor is not None else 0
            region = self.sim.world.region_name(getattr(actor, "region_id", -1)) if actor is not None and getattr(actor, "region_id", None) in world.regions else "-"
            rows.append({"id": aid, "actor": actor, "name": name, "alive": alive, "rep": rep, "composed": composed, "performed": performed, "known": known, "region": region})
        rows.sort(key=lambda r: (r["composed"] * 8 + r["performed"] * 2 + r["rep"], r["rep"]), reverse=True)
        return rows

    def _journal_song_type_counts(self, songs):
        counts = {}
        for song in songs:
            label = self._song_type_label(song)
            counts[label] = counts.get(label, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def _journal_cults(self):
        cults = [c for c in getattr(self.sim.world, "proto_cults", {}).values() if not getattr(c, "failed", False)]
        cults.sort(key=lambda c: float(getattr(c, "legend_pressure", 0.0) or 0.0), reverse=True)
        return cults

    def _journal_legends(self):
        rows = sorted((getattr(self.sim.world, "legend_pressure_by_actor_id", {}) or {}).items(), key=lambda item: float(item[1]), reverse=True)
        return rows

    def _draw_journal_song_row(self, y: int, x: int, width: int, index: int, song) -> int:
        title = str(getattr(song, "title", "Untitled") or "Untitled")
        stype = self._song_type_label(song)
        composer = self._actor_display_name_by_id(getattr(song, "composer_id", None), "Unknown")
        pop = float(getattr(song, "popularity", 0.0) or 0.0)
        weight = float(getattr(song, "historical_weight", 0.0) or 0.0)
        perf = int(getattr(song, "performances", 0) or 0)
        regions = len(getattr(song, "known_region_ids", set()) or set())
        line = f"{index:>2}. {title[:28]:28} {stype[:10]:10} pop={pop:5.1f} wt={weight:5.1f} p={perf:3} r={regions:2} {composer[:16]}"
        return self._draw_text_line(y, x, width, line, self._journal_row_attr(stype))

    def _draw_journal_bard_row(self, y: int, x: int, width: int, index: int, row) -> int:
        actor = row.get("actor")
        prefix = f"{index:>2}. "
        self._safe_addstr(y, x, prefix[:width - 1])
        link_x = x + len(prefix)
        name = str(row.get("name", "Unknown"))
        attr = self._link_attr() if actor is not None else 0
        self._safe_addstr(y, link_x, name[:18], attr)
        if actor is not None:
            self._inspector_link_hitboxes[actor.id] = (link_x, y, min(link_x + len(name), x + width - 2), y)
        tail_x = link_x + 20
        state = "live" if row.get("alive") else "dead"
        tail = f"{state:<4} songs={row.get('composed',0):2} perf={row.get('performed',0):3} known={row.get('known',0):2} rep={row.get('rep',0):4} {str(row.get('region','-'))[:12]}"
        tail_attr = curses.color_pair(1) if self.has_colors and row.get("alive") else curses.color_pair(2) if self.has_colors else 0
        self._safe_addstr(y, tail_x, tail[:max(0, width - (tail_x - x) - 1)], tail_attr)
        return y + 1

    def draw_journal_panel(self, height: int, width: int, top: Optional[int] = None, left: Optional[int] = None, bottom: Optional[int] = None, panel_w: Optional[int] = None):
        self._inspector_link_hitboxes = {}
        top = 3 if top is None else int(top)
        bottom = (height - EVENT_ROWS - 4) if bottom is None else int(bottom)
        left = 0 if left is None else int(left)
        panel_w = (width - left - 1) if panel_w is None else min(int(panel_w), max(1, width - left - 1))
        if bottom <= top + 4:
            return
        songs = self._journal_songs()
        bards = self._journal_bards()
        cults = self._journal_cults()
        legends = self._journal_legends()
        type_counts = self._journal_song_type_counts(songs)

        lines = []
        # Draw directly, but honor a vertical scroll by shifting the start row.
        scroll = max(0, int(getattr(self, "journal_scroll", 0)))
        y = top - scroll
        title_attr = self._inspector_title_attr("journal")
        self._safe_addstr(y, left, "JOURNAL: SONGS, BARDS, CULTS, AND LIVING MEMORY"[:panel_w - 1], title_attr); y += 1
        self._safe_addstr(y, left, "=" * max(1, panel_w - 1), title_attr if self.has_colors else 0); y += 1
        metrics = f"Songs {len(songs)} | Bards {len(bards)} | Proto-cults {len(cults)} | Remembered figures {len(legends)}"
        if songs:
            metrics += f" | Top song: {str(getattr(songs[0], 'title', 'Untitled'))[:28]}"
        metrics_attr = (curses.color_pair(6) | curses.A_DIM) if self.has_colors else 0
        self._safe_addstr(y, left, metrics[:panel_w - 1], metrics_attr); y += 2

        col_gap = 3
        use_two_cols = panel_w >= 96
        if use_two_cols:
            left_w = max(44, (panel_w - col_gap) // 2)
            right_x = left + left_w + col_gap
            right_w = max(38, panel_w - left_w - col_gap)
        else:
            left_w = panel_w
            right_x = left
            right_w = panel_w
        start_y = y

        ly = start_y
        ly = self._draw_section_header(ly, left, left_w, "TOP SONGS")
        if not songs:
            ly = self._draw_text_line(ly, left, left_w, "No songs in living memory.")
        else:
            for i, song in enumerate(songs[:10], start=1):
                ly = self._draw_journal_song_row(ly, left, left_w, i, song)
        ly += 1
        ly = self._draw_section_header(ly, left, left_w, "SONG TYPES")
        if not type_counts:
            ly = self._draw_text_line(ly, left, left_w, "None.")
        else:
            for name, count in type_counts[:12]:
                ly = self._draw_text_line(ly, left, left_w, f"{name[:24]:24} {count:4}")
        ly += 1
        ly = self._draw_section_header(ly, left, left_w, "METRICS")
        live_bards = sum(1 for b in bards if b.get("alive"))
        dead_bards = len(bards) - live_bards
        avg_known = sum(int(b.get("known", 0) or 0) for b in bards) / len(bards) if bards else 0.0
        most_performed = max(songs, key=lambda song: int(getattr(song, "performances", 0) or 0), default=None)
        metric_lines = [
            f"Living bards: {live_bards} | dead/archived bards: {dead_bards}",
            f"Avg known songs per bard: {avg_known:.1f}",
            f"Most performed: {getattr(most_performed, 'title', 'None') if most_performed else 'None'}",
        ]
        for line in metric_lines:
            ly = self._draw_text_line(ly, left, left_w, line)

        ry = start_y if use_two_cols else ly + 1
        ry = self._draw_section_header(ry, right_x, right_w, "FAMOUS BARDS")
        if not bards:
            ry = self._draw_text_line(ry, right_x, right_w, "No bards recorded.")
        else:
            for i, row in enumerate(bards[:10], start=1):
                ry = self._draw_journal_bard_row(ry, right_x, right_w, i, row)
        ry += 1
        ry = self._draw_section_header(ry, right_x, right_w, "CULTS & LEGENDS")
        if not cults and not legends:
            ry = self._draw_text_line(ry, right_x, right_w, "No cults or legends yet.")
        else:
            if cults:
                ry = self._draw_text_line(ry, right_x, right_w, "Proto-cults:", self._section_header_attr("CULTS & LEGENDS"))
                for cult in cults[:5]:
                    title = str(getattr(cult, "public_title", "") or getattr(cult, "name", "Unnamed Cult"))
                    status = "asc" if getattr(cult, "ascended", False) else "formal" if getattr(cult, "formalized", False) else "proto"
                    pressure = float(getattr(cult, "legend_pressure", 0.0) or 0.0)
                    regions = len(getattr(cult, "known_region_ids", set()) or set())
                    ry = self._draw_text_line(ry, right_x + 2, max(1, right_w - 2), f"{title[:26]:26} {status:<6} p={pressure:6.1f} r={regions}")
            if legends:
                ry = self._draw_text_line(ry + 1, right_x, right_w, "Remembered figures:", self._section_header_attr("CULTS & LEGENDS"))
                for actor_id, pressure in legends[:8]:
                    name = self._actor_display_name_by_id(actor_id, f"Actor {actor_id}")
                    ry = self._draw_text_line(ry, right_x + 2, max(1, right_w - 2), f"{name[:28]:28} legend={float(pressure):7.1f}")

        max_content_y = max(ly, ry)
        max_scroll = max(0, max_content_y - bottom + 1 + scroll)
        self.journal_scroll = max(0, min(scroll, max_scroll))
        if bottom > top:
            hint = "j/Esc close journal | wheel/up/down scroll | click bard opens actor inspector"
            self._safe_addstr(bottom - 1, left, hint[:panel_w - 1], curses.A_DIM if self.has_colors else 0)

    def draw_actor_inspector(self, top: int, left: int, bottom: int, width: int):
        actor = self._inspected_actor()
        if actor is None:
            self.inspect_actor_id = None
            return

        self._inspector_link_hitboxes = {}
        title_name = actor.full_name() if hasattr(actor, "full_name") else actor.short_name()
        title = f"ACTOR DOSSIER: {title_name}"
        title_attr = self._inspector_title_attr("actor")
        self._safe_addstr(top, left, title[:width - 1], title_attr)
        self._safe_addstr(top + 1, left, "=" * max(1, width - 1), title_attr if self.has_colors else 0)

        col_gap = 3
        usable_h = max(1, bottom - (top + 3) - 1)
        use_three_cols = width >= 108
        use_two_cols = width >= 72
        if use_three_cols:
            col_w = max(28, (width - col_gap * 2) // 3)
            cols = [
                (left, col_w),
                (left + col_w + col_gap, col_w),
                (left + (col_w + col_gap) * 2, max(28, width - (col_w + col_gap) * 2)),
            ]
        elif use_two_cols:
            col_w = max(32, (width - col_gap) // 2)
            cols = [
                (left, col_w),
                (left + col_w + col_gap, max(28, width - col_w - col_gap)),
            ]
        else:
            cols = [(left, width)]

        start_y = top + 3
        max_y = max(start_y, bottom - 1)

        def draw_lines(y: int, x: int, w: int, lines, *, max_rows: Optional[int] = None) -> int:
            count = 0
            for item in lines:
                if y >= max_y:
                    break
                if max_rows is not None and count >= max_rows:
                    break
                if isinstance(item, tuple):
                    text, attr = item
                else:
                    text, attr = item, 0
                y = self._draw_text_line(y, x, w, text, attr)
                count += 1
            return y

        def remaining(y: int) -> int:
            return max(0, max_y - y)

        # Column 1: identity + current state.
        x1, w1 = cols[0]
        y1 = self._draw_section_header(start_y, x1, w1, "IDENTITY")
        age = self._actor_age(actor)
        identity_lines = [
            f"ID: {actor.id}",
            f"Name: {actor.full_name()}",
            f"Sex: {getattr(actor, 'sex', '-')}",
            f"Age: {age}",
            f"Role: {self._actor_role_label(actor)}",
            f"Alignment: {self._alignment_label(getattr(actor, 'alignment', None))}",
            f"Religion: {self._deity_label(getattr(actor, 'deity', None))}",
            f"Protocult: {self._actor_protocult_label(actor)}",
            f"Title: {self._champion_title_label(actor)}",
            f"Region: {self.sim.world.region_name(actor.region_id)}",
            (f"Alive: {'Yes' if actor.alive else 'No'}", (curses.color_pair(1) if actor.alive else curses.color_pair(2)) if self.has_colors else 0),
            f"Birth: {actor.birth_text()} Year {actor.birth_year}",
            f"Death: {getattr(actor, 'death_timestamp', None) or '-'}",
            f"Cause: {getattr(actor, 'death_cause', None) or '-'}",
            (f"Story actor: {'Yes' if getattr(actor, 'is_story_actor', False) else 'No'}", (curses.color_pair(6) | curses.A_BOLD) if self.has_colors and getattr(actor, 'is_story_actor', False) else 0),
            (self._targeted_by_line(actor), (curses.color_pair(2) | curses.A_BOLD) if self.has_colors and self._active_directives_for_actor(actor.id) else curses.A_BOLD if self._active_directives_for_actor(actor.id) else 0),
        ]
        y1 = draw_lines(y1, x1, w1, identity_lines)
        killer_id = getattr(actor, 'death_killer_id', None)
        if (not getattr(actor, 'alive', False)) and killer_id is not None and y1 < max_y:
            y1 = self._draw_actor_link_line(y1, x1, w1, "Killed by", killer_id, "Unknown")
        if y1 < max_y:
            y1 += 1
            y1 = self._draw_section_header(y1, x1, w1, "STATUS")
            status_lines = [
                f"HP: {actor.hp}/{actor.max_hp}",
                f"Level: {getattr(actor, 'level', 1)}",
                f"XP: {getattr(actor, 'experience', 0)}",
                f"Reputation: {actor.reputation}",
                f"Recovering: {getattr(actor, 'recovering', 0)}",
                f"Retired: {'Yes' if getattr(actor, 'retired', False) else 'No'}",
                f"Fatigue actions: {getattr(actor, 'fatigue_actions', 0)}",
                f"Resting until tick: {getattr(actor, 'resting_until_tick', -1)}",
                f"Pregnant until tick: {getattr(actor, 'pregnant_until_tick', -1)}",
                (f"Champion of: {getattr(getattr(actor, 'champion_of', None), 'value', 'None')}", (curses.color_pair(3) | curses.A_BOLD) if self.has_colors and getattr(actor, 'champion_of', None) is not None else 0),
                (f"Relic: {self._relic_name(getattr(actor, 'relic_id', None))}", curses.color_pair(5) if self.has_colors and getattr(actor, 'relic_id', None) is not None else 0),
                f"Protects region: {self._region_name_safe(getattr(actor, 'protects_region', None))}",
            ]
            y1 = draw_lines(y1, x1, w1, status_lines)

        # Column 2: stats, ideology, career.
        x2, w2 = cols[1] if len(cols) > 1 else cols[0]
        y2 = self._draw_section_header(start_y, x2, w2, "STATS") if len(cols) > 1 else y1 + 1
        if len(cols) == 1 and y2 < max_y:
            y2 = self._draw_section_header(y2, x2, w2, "STATS")
        stat_lines = [
            f"STR {actor.strength:>3}   DEX {actor.dexterity:>3}   CON {actor.constitution:>3}",
            f"INT {actor.intelligence:>3}   WIS {actor.wisdom:>3}   CHA {actor.charisma:>3}",
            f"LCK {actor.luck:>3}",
            f"Power rating: {actor.power_rating()}",
            f"Mind score: {actor.mind_score()}",
            f"Governance ideology: {getattr(actor, 'governance_ideology', 0.0):.2f}",
            f"Economic ideology: {getattr(actor, 'economic_ideology', 0.0):.2f}",
        ]
        y2 = draw_lines(y2, x2, w2, stat_lines)
        if y2 < max_y:
            y2 += 1
            y2 = self._draw_section_header(y2, x2, w2, "CAREER")
            party = self.sim.world.get_party(actor)
            polity = self.sim.world.polities.get(actor.polity_id) if actor.polity_id is not None else None
            career_lines = [
                f"Party: {(party.name if party and party.name else (f'Party {party.id}' if party else 'None'))}",
                f"Polity: {polity.name if polity else 'None'}",
                f"Polity favor: {getattr(actor, 'polity_favor', 0)}",
                f"Kills: {actor.kills}",
                f"Monster kills: {actor.monster_kills}",
                f"Dragon kills: {actor.dragon_kills}",
                f"Giant kills: {getattr(actor, 'giant_kills', 0)}",
                f"Horror kills: {actor.horror_kills}",
                f"Regions defended: {actor.regions_defended}",
                f"Regions oppressed: {actor.regions_oppressed}",
                f"Converted followers: {getattr(actor, 'converted_followers', 0)}",
                f"At adventurer school: {'Yes' if getattr(actor, 'in_school', False) else 'No'}",
            ]
            y2 = draw_lines(y2, x2, w2, career_lines)
            if y2 < max_y:
                y2 = self._draw_actor_link_line(y2, x2, w2, "Party leader", getattr(party, "leader_id", None) if party else None)
            if y2 < max_y:
                y2 = self._draw_actor_link_line(y2, x2, w2, "Polity ruler", getattr(polity, "ruler_id", None) if polity else None)

        # Column 3, or lower-right in two-column mode: family, relations, story notes.
        if len(cols) > 2:
            x3, w3 = cols[2]
            y3 = self._draw_section_header(start_y, x3, w3, "FAMILY")
        elif len(cols) > 1:
            x3, w3 = cols[1]
            y3 = y2 + 1
            if y3 < max_y:
                y3 = self._draw_section_header(y3, x3, w3, "FAMILY")
        else:
            x3, w3 = cols[0]
            y3 = y2 + 1
            if y3 < max_y:
                y3 = self._draw_section_header(y3, x3, w3, "FAMILY")

        if y3 < max_y:
            y3 = self._draw_actor_link_line(y3, x3, w3, "Spouse", getattr(actor, "spouse_id", None))
        if y3 < max_y:
            y3 = self._draw_actor_link_line(y3, x3, w3, "Mother", getattr(actor, "mother_id", None), self._actor_parent_display(actor, "mother"))
        if y3 < max_y:
            y3 = self._draw_actor_link_line(y3, x3, w3, "Father", getattr(actor, "father_id", None), self._actor_parent_display(actor, "father"))
        child_ids = list(getattr(actor, "children_ids", []) or [])
        if y3 < max_y:
            y3 = self._draw_text_line(y3, x3, w3, f"Children: {len(child_ids)}")
        for child_id in child_ids[:max(0, min(5, remaining(y3) - 1))]:
            if y3 >= max_y:
                break
            y3 = self._draw_actor_link_line(y3, x3 + 2, max(1, w3 - 2), "child", child_id)
        if len(child_ids) > 5 and y3 < max_y:
            y3 = self._draw_text_line(y3, x3 + 2, max(1, w3 - 2), f"+{len(child_ids) - 5} more children")

        if y3 < max_y:
            y3 += 1
            y3 = self._draw_section_header(y3, x3, w3, "RELATIONS")
            y3 = self._draw_actor_link_line(y3, x3, w3, "Best friend", getattr(actor, "best_friend_id", None))
            friend_ids = list(getattr(actor, "friend_ids", []) or [])
            y3 = self._draw_text_line(y3, x3, w3, f"Friends: {len(friend_ids)}")
            for friend_id in friend_ids[:max(0, min(5, remaining(y3) - 4))]:
                if y3 >= max_y:
                    break
                y3 = self._draw_actor_link_line(y3, x3 + 2, max(1, w3 - 2), "friend", friend_id)
            if len(friend_ids) > 5 and y3 < max_y:
                y3 = self._draw_text_line(y3, x3 + 2, max(1, w3 - 2), f"+{len(friend_ids) - 5} more friends")
            if y3 < max_y:
                y3 = self._draw_actor_link_line(y3, x3, w3, "Nemesis", getattr(actor, "nemesis_id", None))
            if y3 < max_y:
                y3 = self._draw_text_line(y3, x3, w3, f"Nemesis reason: {getattr(actor, 'nemesis_reason', '') or 'None'}")
            if y3 < max_y:
                y3 = self._draw_actor_link_line(y3, x3, w3, "Revenge for", getattr(actor, "revenge_for_actor_id", None))
            if y3 < max_y:
                y3 = self._draw_actor_link_line(y3, x3, w3, "Loyalty", getattr(actor, "loyalty", None))

        if y3 < max_y:
            y3 += 1
            y3 = self._draw_section_header(y3, x3, w3, "STORY NOTES")
            if getattr(actor, 'is_story_actor', False):
                notes = list(getattr(actor, 'story_notes', []))[-max(1, min(8, remaining(y3))):]
                if not notes:
                    y3 = self._draw_text_line(y3, x3, w3, "None.")
                else:
                    for note in notes:
                        if y3 >= max_y:
                            break
                        y3 = self._draw_text_line(y3, x3, w3, f"- {self._compact_story_note(note)}")
            else:
                y3 = self._draw_text_line(y3, x3, w3, "n/a")

        if bottom > top:
            hint = "i/Esc close | / find actor | P champion | T target | X cancel all | Y story"
            self._safe_addstr(bottom - 1, left, hint[:width - 1], curses.A_DIM if self.has_colors else 0)

    def _link_attr(self, base_attr: int = 0) -> int:
        attr = base_attr | curses.A_UNDERLINE
        if self.has_colors:
            attr |= curses.color_pair(4)
        return attr

    def _draw_actor_link_line(self, y: int, x: int, width: int, label: str, actor_id: Optional[int], fallback: str = "None") -> int:
        prefix = f"{label}: "
        self._safe_addstr(y, x, prefix[:width - 1])
        actor = None
        if actor_id is not None:
            actor = self.sim.resolve_actor(actor_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(actor_id)
        text = actor.short_name() if actor is not None else fallback
        link_x = x + len(prefix)
        # Only live in-memory actors are clickable; archived actors still display by name.
        live_actor = self.sim.world.actors.get(actor_id) if actor_id is not None else None
        attr = self._link_attr() if live_actor is not None else 0
        self._safe_addstr(y, link_x, str(text)[:max(0, width - len(prefix) - 1)], attr)
        if live_actor is not None:
            self._inspector_link_hitboxes[live_actor.id] = (link_x, y, min(link_x + len(str(text)), x + width - 2), y)
        return y + 1

    def _draw_text_line(self, y: int, x: int, width: int, text: str, attr: int = 0) -> int:
        self._safe_addstr(y, x, str(text)[:width - 1], attr)
        return y + 1

    def _build_directive_cache(self):
        """Cache active divine directives for one draw pass.

        This avoids scanning every actor once per region while rendering the map.
        """
        world = getattr(self.sim, "world", None)
        by_target = {}
        by_region = {}
        if world is None:
            return {"target": by_target, "region": by_region}
        now = int(getattr(world, "tick", 0))
        expiry = int(globals().get("DIVINE_DIRECTIVE_EXPIRATION_TICKS", TICKS_PER_YEAR))
        for actor in getattr(world, "_living_actor_cache", None) or getattr(world, "actors", {}).values():
            directive = getattr(actor, "divine_directive_type", None)
            if not directive:
                continue
            issued = int(getattr(actor, "divine_directive_issued_tick", -1) or -1)
            if issued >= 0 and now - issued > expiry:
                continue
            if directive == "assassinate":
                target_id = getattr(actor, "divine_directive_target_actor_id", None)
                if target_id is not None:
                    by_target.setdefault(target_id, []).append(actor)
            elif directive in ("stabilize", "destabilize"):
                region_id = getattr(actor, "divine_directive_target_region_id", None)
                if region_id is not None:
                    by_region.setdefault(region_id, {}).setdefault(directive, []).append(actor)
        return {"target": by_target, "region": by_region}

    def _directive_cache(self):
        cache = getattr(self, "_active_directive_cache", None)
        if cache is None:
            cache = self._build_directive_cache()
            self._active_directive_cache = cache
        return cache

    def _active_directives_for_actor(self, actor_id: int):
        """Return active divine assassination directives aimed at this actor."""
        if actor_id is None:
            return []
        return list(self._directive_cache().get("target", {}).get(actor_id, []) or [])

    def _targeted_by_line(self, actor) -> str:
        agents = self._active_directives_for_actor(getattr(actor, "id", None))
        if not agents:
            return "Targeted by: -"
        names = []
        seen = set()
        for agent in agents:
            source = getattr(agent, "divine_directive_source", None)
            name = self._deity_name(source) if source is not None else "Unknown god"
            if name not in seen:
                seen.add(name)
                names.append(name)
        agent_names = ", ".join(a.short_name() for a in agents[:3])
        if len(agents) > 3:
            agent_names += f", +{len(agents) - 3} more"
        return f"Targeted by: {', '.join(names)} via {agent_names}"

    def _region_directive_agents(self, region_id: int, directive_type: Optional[str] = None):
        """Return living agents carrying active divine region directives for this region."""
        by_type = self._directive_cache().get("region", {}).get(region_id, {}) or {}
        if directive_type is not None:
            return list(by_type.get(directive_type, []) or [])
        out = []
        for agents in by_type.values():
            out.extend(agents)
        return out

    def _region_directive_summary(self, region_id: int) -> str:
        stab = self._region_directive_agents(region_id, "stabilize")
        destab = self._region_directive_agents(region_id, "destabilize")
        parts = []
        if stab:
            parts.append(f"stabilize {len(stab)}")
        if destab:
            parts.append(f"destabilize {len(destab)}")
        return "Directives: " + (" | ".join(parts) if parts else "-")

    def _set_god_action_message(self, ok: bool, msg: str) -> None:
        prefix = "OK" if ok else "FAILED"
        self.god_message = f"{prefix}: {msg}"
        self.status_message = self.god_message
        self._active_directive_cache = None
        if not ok:
            self._play_sfx("error")

    def _draw_actor_identity(self, actor, y: int, x: int, width: int):
        age = self._actor_age(actor)
        lines = [
            f"ID: {actor.id}",
            f"Name: {actor.full_name()}",
            f"Sex: {actor.sex}",
            f"Age: {age}",
            f"Role: {self._actor_role_label(actor)}",
            f"Alignment: {self._alignment_label(getattr(actor, 'alignment', None))}",
            f"Religion: {self._deity_label(getattr(actor, 'deity', None))}",
            f"Protocult: {self._actor_protocult_label(actor)}",
            f"Traits: {', '.join(actor.traits)}",
            f"Title: {self._champion_title_label(actor)}",
            f"Region: {self.sim.world.region_name(actor.region_id)}",
            f"Alive: {'Yes' if actor.alive else 'No'}",
            f"Birth: {actor.birth_text()} Year {actor.birth_year}",
            f"Death: {getattr(actor, 'death_timestamp', None) or '-'}",
            f"Cause: {getattr(actor, 'death_cause', None) or '-'}",
        ]
        for line in lines:
            y = self._draw_text_line(y, x, width, line)
        killer_id = getattr(actor, 'death_killer_id', None)
        if (not getattr(actor, 'alive', False)) and killer_id is not None:
            y = self._draw_actor_link_line(y, x, width, "Killed by", killer_id, "Unknown")
        y = self._draw_text_line(y, x, width, f"Monster killer: {getattr(actor, 'death_monster_id', None) or '-'}")
        y = self._draw_text_line(y, x, width, f"Story actor: {'Yes' if getattr(actor, 'is_story_actor', False) else 'No'}")
        y = self._draw_text_line(y, x, width, self._targeted_by_line(actor), curses.A_BOLD if self._active_directives_for_actor(actor.id) else 0)

    def _draw_actor_stats(self, actor, y: int, x: int, width: int):
        lines = [
            f"HP: {actor.hp}/{actor.max_hp}",
            f"Level: {getattr(actor, 'level', 1)}",
            f"XP: {getattr(actor, 'experience', 0)}",
            f"Reputation: {actor.reputation}",
            f"Recovering: {getattr(actor, 'recovering', 0)}",
            f"Retired: {'Yes' if getattr(actor, 'retired', False) else 'No'}",
            f"Fatigue actions: {getattr(actor, 'fatigue_actions', 0)}",
            f"Resting until tick: {getattr(actor, 'resting_until_tick', -1)}",
            f"Pregnant until tick: {getattr(actor, 'pregnant_until_tick', -1)}",
            "",
            f"STR {actor.strength:>3}   DEX {actor.dexterity:>3}   CON {actor.constitution:>3}",
            f"INT {actor.intelligence:>3}   WIS {actor.wisdom:>3}   CHA {actor.charisma:>3}",
            f"LCK {actor.luck:>3}",
            "",
            f"Power rating: {actor.power_rating()}",
            f"Mind score: {actor.mind_score()}",
            f"Governance ideology: {getattr(actor, 'governance_ideology', 0.0):.2f}",
            f"Economic ideology: {getattr(actor, 'economic_ideology', 0.0):.2f}",
        ]
        for line in lines:
            self._safe_addstr(y, x, line[:width - 1])
            y += 1

    def _add_social_hitbox(self, actor_id, y, x, text):
        if actor_id is None or actor_id not in self.sim.world.actors:
            return
        self._social_hitboxes[actor_id] = (x, y, min(x + len(str(text)), x + 80), y)

    def _draw_actor_social(self, actor, y: int, x: int, width: int):
        self._social_hitboxes = {}
        party = self.sim.world.get_party(actor)
        polity = self.sim.world.polities.get(actor.polity_id) if actor.polity_id is not None else None
        y = self._draw_actor_link_line(y, x, width, "Spouse", getattr(actor, "spouse_id", None))
        y = self._draw_actor_link_line(y, x, width, "Mother", getattr(actor, "mother_id", None), self._actor_parent_display(actor, "mother"))
        y = self._draw_actor_link_line(y, x, width, "Father", getattr(actor, "father_id", None), self._actor_parent_display(actor, "father"))
        y = self._draw_text_line(y, x, width, f"Children: {len(getattr(actor, 'children_ids', []))}")
        child_ids = list(getattr(actor, "children_ids", []) or [])
        if child_ids:
            shown = 0
            for child_id in child_ids[:4]:
                y = self._draw_actor_link_line(y, x + 2, max(1, width - 2), "child", child_id)
                shown += 1
            if len(child_ids) > shown:
                y = self._draw_text_line(y, x + 2, max(1, width - 2), f"+{len(child_ids) - shown} more children")
        y = self._draw_actor_link_line(y, x, width, "Best friend", getattr(actor, "best_friend_id", None))
        friend_ids = list(getattr(actor, "friend_ids", []) or [])
        y = self._draw_text_line(y, x, width, f"Friends: {len(friend_ids)}")
        for friend_id in friend_ids[:4]:
            y = self._draw_actor_link_line(y, x + 2, max(1, width - 2), "friend", friend_id)
        if len(friend_ids) > 4:
            y = self._draw_text_line(y, x + 2, max(1, width - 2), f"+{len(friend_ids) - 4} more friends")
        y = self._draw_actor_link_line(y, x, width, "Nemesis", getattr(actor, "nemesis_id", None))
        y = self._draw_text_line(y, x, width, f"Nemesis reason: {getattr(actor, 'nemesis_reason', '') or 'None'}")
        y = self._draw_actor_link_line(y, x, width, "Revenge for", getattr(actor, "revenge_for_actor_id", None))
        y = self._draw_actor_link_line(y, x, width, "Loyalty", getattr(actor, "loyalty", None))
        y = self._draw_text_line(y, x, width, f"Party: {(party.name if party and party.name else (f'Party {party.id}' if party else 'None'))}")
        y = self._draw_actor_link_line(y, x, width, "Party leader", getattr(party, "leader_id", None) if party else None)
        y = self._draw_text_line(y, x, width, f"Polity: {polity.name if polity else 'None'}")
        y = self._draw_actor_link_line(y, x, width, "Polity ruler", getattr(polity, "ruler_id", None) if polity else None)
        y = self._draw_text_line(y, x, width, f"Polity favor: {getattr(actor, 'polity_favor', 0)}")
        y = self._draw_text_line(y, x, width, f"Champion of: {getattr(getattr(actor, 'champion_of', None), 'value', 'None')}")
        y = self._draw_text_line(y, x, width, "")
        y = self._draw_text_line(y, x, width, "Click names. i/Esc close | P champion | T target | X cancel all | Y make story |", curses.A_DIM if self.has_colors else 0)

    def _draw_actor_career(self, actor, y: int, x: int, width: int):
        lines = [
            f"Kills: {actor.kills}",
            f"Monster kills: {actor.monster_kills}",
            f"Dragon kills: {actor.dragon_kills}",
            f"Giant kills: {getattr(actor, 'giant_kills', 0)}",
            f"Horror kills: {actor.horror_kills}",
            f"Regions defended: {actor.regions_defended}",
            f"Regions oppressed: {actor.regions_oppressed}",
            f"Converted followers: {getattr(actor, 'converted_followers', 0)}",
            f"Relic: {self._relic_name(getattr(actor, 'relic_id', None))}",
            f"Protects region: {self._region_name_safe(getattr(actor, 'protects_region', None))}",
            f"Revenge targets: {len(getattr(actor, 'revenge_target_ids', []) or [])}",
            f"Monster revenge targets: {len(getattr(actor, 'revenge_monster_ids', []))}",
            f"At adventurer school: {'Yes' if getattr(actor, 'in_school', False) else 'No'}",
            "",
        ]

        if getattr(actor, 'is_story_actor', False):
            lines.append("Recent story notes:")
            notes = list(getattr(actor, 'story_notes', []))[-8:]
            if not notes:
                lines.append("  None.")
            else:
                for note in notes:
                    lines.append(f"  {self._compact_story_note(note)}")
        else:
            lines.append("Recent story notes: n/a")

        for line in lines:
            self._safe_addstr(y, x, line[:width - 1])
            y += 1
        revenge_ids = list(getattr(actor, 'revenge_target_ids', []) or [])
        if revenge_ids:
            self._safe_addstr(y, x, "Clickable revenge targets:"[:width - 1])
            y += 1
            for target_id in revenge_ids[:5]:
                y = self._draw_actor_link_line(y, x + 2, max(1, width - 2), "target", target_id)


    def _compact_story_note(self, note: str) -> str:
        if not note:
            return ""
        note = str(note)
        if note.startswith("[") and "] " in note:
            return note.split("] ", 1)[1]
        return note

    def draw_summary_browser(self, height: int, width: int):
        y = max(0, height - EVENT_ROWS - 3)
        title = "Summary Browser"
        self._safe_addstr(y, 0, title)
        self._safe_addstr(y + 1, 0, "-" * max(1, width - 1))
        body_top = y + 2
        body_bottom = height - 2
        visible_rows = max(1, body_bottom - body_top)

        if not self.summary_files:
            self._safe_addstr(body_top, 0, "No summary files found.")
            return

        current = self.summary_files[self.summary_selected_index]
        file_line = f"[{self.summary_selected_index + 1}/{len(self.summary_files)}] {current.name}"
        self._safe_addstr(body_top, 0, file_line[:width - 1], curses.A_BOLD if self.has_colors else 0)

        max_scroll = max(0, len(self.summary_content_lines) - max(1, visible_rows - 1))
        self.summary_scroll = max(0, min(self.summary_scroll, max_scroll))

        row_y = body_top + 1
        for line in self.summary_content_lines[self.summary_scroll:self.summary_scroll + max(1, visible_rows - 1)]:
            if row_y >= body_bottom:
                break
            self._safe_addstr(row_y, 0, str(line)[:width - 1])
            row_y += 1


    def _ascii_sparkline(self, values, width: int = 32) -> str:
        if not values:
            return "-" * width
        vals = list(values)[-max(1, width):]
        if len(vals) > width:
            step = len(vals) / float(width)
            vals = [vals[int(i * step)] for i in range(width)]
        lo = min(vals)
        hi = max(vals)
        if hi == lo:
            return "-" * len(vals)
        chars = "._-=+*#"
        span = hi - lo
        out = []
        for value in vals:
            idx = int(round((float(value) - lo) / span * (len(chars) - 1)))
            idx = max(0, min(idx, len(chars) - 1))
            out.append(chars[idx])
        return "".join(out)

    def draw_history_trends(self, top: int, left: int, width: int):
        history = getattr(self.sim.world, "history", None)
        if not history:
            return

        # Keep this curses-safe: ASCII only, narrow, and unobtrusive.
        graph_w = max(12, min(36, width - 18))
        rows = [
            ("Pop", "total_population"),
            ("Adv", "adventurers"),
            ("Mon", "monsters"),
        ]

        # Cache sparkline strings; history only appends once per month so
        # recomputing every frame is pure waste.
        history_len = sum(len(history.get(key, [])) for _, key in rows)
        spark_cache = getattr(self, "_sparkline_cache", None)
        if spark_cache is None or spark_cache.get("len") != history_len or spark_cache.get("w") != graph_w:
            lines_cache = {}
            for label, key in rows:
                values = history.get(key, [])
                if not values:
                    continue
                lines_cache[key] = (self._ascii_sparkline(values, graph_w), values[-1])
            self._sparkline_cache = {"len": history_len, "w": graph_w, "lines": lines_cache}
        lines_cache = self._sparkline_cache["lines"]

        title_attr = curses.A_BOLD if self.has_colors else 0
        self._safe_addstr(top, left, "Trend", title_attr)
        y = top + 1
        for label, key in rows:
            if key not in lines_cache:
                continue
            spark, last = lines_cache[key]
            line = f"{label:<3} {spark:<{graph_w}} {last}"
            self._safe_addstr(y, left, line[:width - 1])
            y += 1


    def draw_event_focus(self, height: int, width: int):
        self._event_link_hitboxes = {}
        self._rebuild_event_link_index()
        self._safe_addstr(3, 0, f"EXPANDED EVENT LOG — F2 returns", curses.A_BOLD)
        self._safe_addstr(4, 0, "-" * max(1, width - 1))
        y = 5
        max_rows = max(1, height - 8)
        for event in self.last_events[-max_rows:]:
            if y >= height - 2:
                break
            self._draw_event_line_with_links(y, 0, width - 1, event)
            y += 1

    def draw_events(self, height: int, width: int):
        self._event_link_hitboxes = {}
        self._rebuild_event_link_index()
        y = max(0, height - EVENT_ROWS - 3)
        self._safe_addstr(y, 0, "-" * max(1, width - 1))

        trend_w = min(56, max(34, width // 3))
        trend_left = max(0, width - trend_w - 1)
        event_w = max(40, trend_left - 2)

        self.draw_history_trends(y + 1, trend_left, trend_w)

        y += 1
        for event in self.last_events[-EVENT_ROWS:]:
            if y >= height - 1:
                break
            self._draw_event_line_with_links(y, 0, event_w, event)
            y += 1


    def _player_god(self):
        try:
            return self.sim._player_god()
        except Exception:
            return None

    def _player_god_name(self) -> str:
        god = self._player_god()
        if god is None:
            return "No player god"
        return getattr(god, "value", getattr(god, "name", str(god)))

    def _player_champion_rows(self, alive_only: Optional[bool] = None):
        """Return player champions, including dead/resolved champions when available.

        Older saves can lose dead champions from world.actors; resolve through
        dead_actor_index when possible and fall back to actor-like tomb objects.
        """
        rows = []
        seen = set()
        try:
            source = list(self.sim._player_champions(alive_only=False))
        except Exception:
            source = []
        god = self._player_god()
        for actor in source:
            if actor is None:
                continue
            aid = getattr(actor, "id", None)
            if aid in seen:
                continue
            if alive_only is True and not getattr(actor, "alive", False):
                continue
            if alive_only is False and getattr(actor, "alive", False):
                continue
            rows.append(actor)
            seen.add(aid)

        # Some versions only expose living actors through _player_champions.
        # Scan all loaded actors for champion markers/titles.
        for actor in getattr(self.sim.world, "actors", {}).values():
            aid = getattr(actor, "id", None)
            if aid in seen:
                continue
            if getattr(actor, "champion_of", None) != god:
                continue
            if alive_only is True and not getattr(actor, "alive", False):
                continue
            if alive_only is False and getattr(actor, "alive", False):
                continue
            rows.append(actor)
            seen.add(aid)

        # Dead champions are archived out of world.actors, so the God UI has to
        # look through the morgue/dead_actor_index. v2 tombstones carry
        # champion_of; older tombstones do not, so load them once and cache.
        if alive_only is not True:
            god_label = str(self._deity_label(god)).strip().lower()
            dead_index = getattr(self.sim.world, "dead_actor_index", {}) or {}
            cache_key = (god_label, len(dead_index), tuple(sorted(dead_index.keys()))[-5:] if isinstance(dead_index, dict) else ())
            cache = getattr(self, "_dead_champion_rows_cache", None)
            if cache is not None and cache.get("key") == cache_key:
                dead_rows = list(cache.get("rows", []))
            else:
                dead_rows = []
                for aid, tomb in list(dead_index.items()):
                    if aid in seen:
                        continue
                    champ_label = None
                    if isinstance(tomb, dict):
                        champ_label = tomb.get("champion_of") or tomb.get("champion")
                    # New morgue tombstones can be filtered cheaply. Old ones
                    # must be resolved once to recover champion_of.
                    if champ_label is not None and str(champ_label).strip().lower() != god_label:
                        continue
                    actor = None
                    if hasattr(self.sim, "resolve_actor"):
                        actor = self.sim.resolve_actor(aid)
                    if actor is None:
                        continue
                    if getattr(actor, "alive", False):
                        continue
                    actor_god = getattr(actor, "champion_of", None)
                    if str(self._deity_label(actor_god)).strip().lower() != god_label:
                        continue
                    dead_rows.append(actor)
                dead_rows.sort(key=lambda a: (-getattr(a, "reputation", 0), -getattr(a, "level", 1), a.short_name()))
                self._dead_champion_rows_cache = {"key": cache_key, "rows": list(dead_rows)}
            for actor in dead_rows:
                aid = getattr(actor, "id", None)
                if aid in seen:
                    continue
                rows.append(actor)
                seen.add(aid)

        return rows

    def _god_rows(self):
        page = self.god_page % 4
        data = self._god_data_for_tick()

        if page == 0:
            rows = list(data["followers"])
        elif page == 1:
            rows = list(data["live_champions"])
        elif page == 2:
            rows = list(data["children"])
        else:
            rows = list(data["dead_champions"])

        mode = getattr(self, "god_filter_mode", "none")
        reverse = bool(getattr(self, "god_sort_reverse", False))

        def default_rank(actor):
            return (
                getattr(actor, "level", 1),
                getattr(actor, "reputation", 0),
                getattr(actor, "hp", 0),
                getattr(actor, "id", 0),
            )

        if page == 0:
            ranked = sorted(rows, key=default_rank, reverse=True)
            by_class = {}
            for actor in ranked:
                role = getattr(getattr(actor, "role", None), "value", "Unknown")
                by_class.setdefault(role, [])
                if len(by_class[role]) < 20:
                    by_class[role].append(actor)

            rows = []
            for role in sorted(by_class.keys()):
                rows.extend(by_class[role])

            if mode == "class":
                rows.sort(key=lambda a: (getattr(getattr(a, "role", None), "value", ""), getattr(a, "level", 1), getattr(a, "reputation", 0), getattr(a, "hp", 0)), reverse=reverse)
            elif mode == "rep":
                rows.sort(key=lambda a: (getattr(a, "reputation", 0), getattr(a, "level", 1), getattr(a, "hp", 0)), reverse=not reverse)
            else:
                rows.sort(key=default_rank, reverse=not reverse)
            return rows

        if mode in ("none", "level"):
            rows.sort(key=default_rank, reverse=not reverse)
        elif mode == "class":
            rows.sort(key=lambda a: (getattr(getattr(a, "role", None), "value", ""), getattr(a, "level", 1), getattr(a, "reputation", 0)), reverse=reverse)
        elif mode == "rep":
            rows.sort(key=lambda a: (getattr(a, "reputation", 0), getattr(a, "level", 1), getattr(a, "hp", 0)), reverse=not reverse)
        elif reverse:
            rows.reverse()

        return rows

    def _selected_god_actor(self):
        rows = self._god_rows()
        if not rows:
            return None
        self.god_selected_index = max(0, min(self.god_selected_index, len(rows) - 1))
        return rows[self.god_selected_index]

    def _boon_display_text(self, actor, width: int = 28) -> str:
        if actor is None:
            return "-"
        boons = []
        try:
            if hasattr(self.sim, "_active_boons_for_actor"):
                boons = list(self.sim._active_boons_for_actor(getattr(actor, "id", None)) or [])
        except Exception:
            boons = []
        parts = []
        now = int(getattr(self.sim.world, "tick", 0) or 0)
        for boon in boons:
            label = str(getattr(boon, "label", getattr(boon, "boon_type", "boon")) or "boon")
            stat = str(getattr(boon, "stat", "") or "")
            amount = int(getattr(boon, "amount", 0) or 0)
            expires = int(getattr(boon, "expires_tick", 0) or 0)
            dur = "perm" if expires >= 10**9 else f"{max(0, expires - now)}t"
            statbit = f" {stat[:3]}+{amount}" if stat and amount else ""
            parts.append(f"{label}{statbit} {dur}")
        if not parts:
            relic = self._relic_name(getattr(actor, "relic_id", None))
            if relic and relic != "None":
                parts.append(f"Relic: {relic}")
        text = "; ".join(parts) if parts else "-"
        return text[:max(1, width)]


    def _choose_holy_war_target(self):
        targets = self.sim._holy_war_available_targets() if hasattr(self.sim, "_holy_war_available_targets") else []
        if not targets:
            self.god_message = "No rival faith can currently be targeted."
            return None
        if len(targets) == 1:
            return targets[0][0]
        old_nodelay = True
        try:
            self.stdscr.nodelay(False)
            idx = 0
            while True:
                self.stdscr.erase()
                h, w = self.stdscr.getmaxyx()
                title = "Choose Holy War target"
                self._safe_addstr(max(0, h // 2 - len(targets) // 2 - 3), max(0, (w - len(title)) // 2), title, curses.A_BOLD)
                y0 = max(2, h // 2 - len(targets) // 2)
                for i, (deity, state) in enumerate(targets):
                    name = self._deity_display_name(deity)
                    line = f"{name:<24} influence={getattr(state, 'influence_share', 0.0):5.1f}% followers={getattr(state, 'followers', 0)} souls={getattr(state, 'souls', 0)}"
                    attr = curses.A_REVERSE if i == idx else 0
                    self._safe_addstr(y0 + i, max(0, (w - len(line)) // 2), line[:w - 1], attr)
                footer = "Enter select | Esc cancel"
                self._safe_addstr(min(h - 2, y0 + len(targets) + 2), max(0, (w - len(footer)) // 2), footer)
                self.stdscr.refresh()
                key = self.stdscr.getch()
                if key == curses.KEY_UP:
                    idx = (idx - 1) % len(targets)
                elif key == curses.KEY_DOWN:
                    idx = (idx + 1) % len(targets)
                elif key in (10, 13, curses.KEY_ENTER):
                    return targets[idx][0]
                elif key in (27, ord('q'), ord('Q')):
                    self.god_message = "Holy War cancelled."
                    return None
        finally:
            self.stdscr.nodelay(old_nodelay)


    def _choose_school_region(self):
        god = self._player_god()
        if god is None:
            self.god_message = "No player god loaded."
            return None
        regions = sorted(self.sim.world.regions.values(), key=lambda r: r.id)
        if not regions:
            self.god_message = "No regions available."
            return None
        old_nodelay = True
        try:
            self.stdscr.nodelay(False)
            idx = max(0, min(getattr(self, "selected_region_id", 0) or 0, len(regions) - 1))
            while True:
                self.stdscr.erase()
                h, w = self.stdscr.getmaxyx()
                title = f"Move {self._player_god_name()} Adventurer School"
                self._safe_addstr(max(0, h // 2 - 12), max(0, (w - len(title)) // 2), title, curses.A_BOLD)
                status = self.sim._school_status(god) if hasattr(self.sim, "_school_status") else None
                if status:
                    school = status.get("school")
                    region = status.get("region")
                    current = getattr(region, "name", "Unknown")
                    cooldown = int(status.get("move_cooldown_ticks", 0) or 0)
                    if cooldown > 0:
                        years = cooldown / float(TICKS_PER_YEAR)
                        line = f"Current: {current} | move cooldown: {years:.1f} years"
                    else:
                        line = f"Current: {current} | move ready"
                    self._safe_addstr(max(1, h // 2 - 10), max(0, (w - len(line)) // 2), line[:w - 1])
                page_size = max(5, min(18, h - 12))
                start = max(0, min(idx - page_size // 2, max(0, len(regions) - page_size)))
                y0 = max(2, h // 2 - page_size // 2)
                for line_i, region in enumerate(regions[start:start + page_size], start=start):
                    text = f"{region.id:02d} {region.name:<18.18} order={region.order:>3} control={region.control:>4} danger={region.danger}"
                    attr = curses.A_REVERSE if line_i == idx else 0
                    self._safe_addstr(y0 + (line_i - start), max(0, (w - len(text)) // 2), text[:w - 1], attr)
                footer = "Enter move | Up/Down select | Esc cancel"
                self._safe_addstr(min(h - 2, y0 + page_size + 2), max(0, (w - len(footer)) // 2), footer)
                self.stdscr.refresh()
                key = self.stdscr.getch()
                if key == curses.KEY_UP:
                    idx = max(0, idx - 1)
                elif key == curses.KEY_DOWN:
                    idx = min(len(regions) - 1, idx + 1)
                elif key in (10, 13, curses.KEY_ENTER):
                    return regions[idx].id
                elif key in (27, ord('q'), ord('Q')):
                    self.god_message = "School move cancelled."
                    return None
        finally:
            self.stdscr.nodelay(old_nodelay)

    def _handle_god_input(self, key: int) -> bool:
        if key in (ord('f'), ord('F')):
            modes = ["none", "level", "class", "rep"]
            cur = getattr(self, "god_filter_mode", "none")
            try:
                idx = modes.index(cur)
            except ValueError:
                idx = 0
            self.god_filter_mode = modes[(idx + 1) % len(modes)]
            self.god_selected_index = 0
            self.god_scroll = 0
            self.god_mouse_scrolled = False
            self.god_message = f"Follower sort: {self.god_filter_mode}"
            return True
        if key in (ord('z'), ord('Z')):
            self.god_sort_reverse = not getattr(self, "god_sort_reverse", False)
            self.god_selected_index = 0
            self.god_scroll = 0
            self.god_mouse_scrolled = False
            direction = "ascending" if self.god_sort_reverse else "descending"
            self.god_message = f"Sort order: {direction}"
            return True

        if key in (27,):
            self._close_top_overlay()
            return True
        if key == 9:
            self.god_page = (self.god_page + 1) % 4
            self.god_selected_index = 0
            self.god_scroll = 0
            self.god_mouse_scrolled = False
            return True
        if key == curses.KEY_UP:
            self.god_mouse_scrolled = False
            self.god_selected_index = max(0, self.god_selected_index - 1)
            return True
        if key == curses.KEY_DOWN:
            self.god_mouse_scrolled = False
            self.god_selected_index += 1
            rows = self._god_rows()
            self.god_selected_index = max(0, min(self.god_selected_index, max(0, len(rows) - 1)))
            return True
        if key in (ord('i'), ord('I'), 10, 13, curses.KEY_ENTER):
            actor = self._selected_god_actor()
            if actor is not None:
                self._open_actor_inspector(actor)
                self._select_region_by_id(actor.region_id)
                self._select_actor_in_region(actor.id)
            return True
        if key in (ord('w'), ord('W')):
            if hasattr(self.sim, "_launch_holy_war"):
                target = self._choose_holy_war_target()
                if target is not None:
                    ok, msg = self.sim._launch_holy_war(target)
                    self._set_god_action_message(ok, msg)
                    self._play_sfx("holy_war")
                    self._pause_message_modal(["HOLY WAR RESULT", msg, "", "Press any key to continue."])
            else:
                self._set_god_action_message(False, "Holy War system unavailable.")
            return True

        if key in (ord('s'), ord('S')):
            if not hasattr(self.sim, "_move_player_school"):
                self._set_god_action_message(False, "School movement unavailable.")
                return True
            region_id = self._choose_school_region()
            if region_id is not None:
                ok, msg = self.sim._move_player_school(region_id)
                self._set_god_action_message(ok, msg)
            return True

        if key == ord('T'):
            actor = self._selected_god_actor()
            if actor is None:
                self._set_god_action_message(False, "No actor selected.")
                return True
            if hasattr(self.sim, "_issue_player_assassination_target"):
                ok, msg = self.sim._issue_player_assassination_target(actor.id)
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Targeting unavailable on this loaded simulator. Save/reload with current fantfarm or start a new run.")
            return True

        if key == ord('X'):
            if hasattr(self.sim, "_cancel_player_assassination_target"):
                ok, msg = self.sim._cancel_player_assassination_target(None)
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Target cancellation unavailable on this loaded simulator.")
            return True

        if key in (ord('l'), ord('L')):
            region = self._selected_region()
            if region is None:
                self._set_god_action_message(False, "No region selected.")
                return True
            if hasattr(self.sim, "_issue_player_region_directive"):
                ok, msg = self.sim._issue_player_region_directive(region.id, "stabilize")
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Region directives unavailable on this loaded simulator. Save/reload with current fantfarm or start a new run.")
            return True

        if key in (ord('d'), ord('D')):
            region = self._selected_region()
            if region is None:
                self._set_god_action_message(False, "No region selected.")
                return True
            if hasattr(self.sim, "_issue_player_region_directive"):
                ok, msg = self.sim._issue_player_region_directive(region.id, "destabilize")
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Region directives unavailable on this loaded simulator. Save/reload with current fantfarm or start a new run.")
            return True

        if key == ord('P'):
            actor = self._selected_god_actor()
            if actor is None:
                self._set_god_action_message(False, "No actor selected.")
                return True
            if hasattr(self.sim, "_promote_player_champion"):
                ok, msg = self.sim._promote_player_champion(actor.id)
                if ok:
                    self._ensure_champion_title(actor)
                self._set_god_action_message(ok, msg)
            else:
                self._set_god_action_message(False, "Champion promotion unavailable.")
            return True
        if key in (ord('r'), ord('R')):
            actor = self._selected_god_actor()
            self._relic_creation_modal(actor)
            return True
        if key in (ord('b'), ord('B')):
            actor = self._selected_god_actor()
            if actor is None:
                self.god_message = "No champion selected."
                return True
            boons = ["might", "grace", "endurance", "insight", "fortune", "resolve"]
            boon = boons[getattr(self, "_next_boon_index", 0) % len(boons)]
            self._next_boon_index = getattr(self, "_next_boon_index", 0) + 1
            ok, msg = self.sim._grant_player_boon(actor.id, boon)
            self._set_god_action_message(ok, msg)
            return True
        return False


    def _cfg_cost_value(self, *names, contains=None):
        """Return a soul-cost value from FASEcfg without hardcoding cost numbers."""
        cfg = globals().get("FASECFG", None)
        if cfg is None:
            return None
        for name in names:
            if hasattr(cfg, name):
                try:
                    return int(getattr(cfg, name))
                except Exception:
                    try:
                        return float(getattr(cfg, name))
                    except Exception:
                        return getattr(cfg, name)
        if contains:
            needles = tuple(str(part).lower() for part in contains)
            matches = []
            for attr in dir(cfg):
                low = attr.lower()
                if all(part in low for part in needles):
                    value = getattr(cfg, attr, None)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        matches.append((attr, value))
            if matches:
                matches.sort(key=lambda item: (len(item[0]), item[0]))
                return matches[0][1]
        return None

    def _first_mapping_value(self, mapping, *keys):
        if not isinstance(mapping, dict):
            return None
        for key in keys:
            if key in mapping and mapping.get(key) is not None:
                return mapping.get(key)
        return None

    def _god_cost_summary_line(self) -> str:
        """Display current divine action soul costs from config/status sources only."""
        parts = []

        hw_cost = None
        if hasattr(self.sim, "_holy_war_status"):
            try:
                hw_cost = self._first_mapping_value(self.sim._holy_war_status(), "soul_cost", "cost", "holy_war_cost")
            except Exception:
                hw_cost = None
        if hw_cost is None:
            hw_cost = self._cfg_cost_value(
                "HOLY_WAR_SOUL_COST", "PLAYER_HOLY_WAR_SOUL_COST", "DIVINE_HOLY_WAR_SOUL_COST",
                contains=("holy", "war", "cost"),
            )
        if hw_cost is not None:
            parts.append(f"HW {hw_cost}")

        boon_cost = self._cfg_cost_value(
            "DIVINE_BOON_SOUL_COST", "PLAYER_BOON_SOUL_COST", "BOON_SOUL_COST", "GRANT_BOON_SOUL_COST",
            contains=("boon", "cost"),
        )
        if boon_cost is not None:
            parts.append(f"boon {boon_cost}")

        champion_cost = self._cfg_cost_value(
            "CHAMPION_SOUL_COST", "PLAYER_CHAMPION_SOUL_COST", "PROMOTE_CHAMPION_SOUL_COST", "DIVINE_CHAMPION_SOUL_COST",
            contains=("champion", "cost"),
        )
        if champion_cost is not None:
            parts.append(f"champ {champion_cost}")

        target_cost = self._cfg_cost_value(
            "ASSASSINATION_DIRECTIVE_SOUL_COST", "DIVINE_ASSASSINATION_SOUL_COST", "PLAYER_ASSASSINATION_SOUL_COST", "TARGET_SOUL_COST",
            contains=("assassin", "cost"),
        )
        if target_cost is None:
            target_cost = self._cfg_cost_value(contains=("target", "cost"))
        if target_cost is not None:
            parts.append(f"target {target_cost}")

        region_cost = self._cfg_cost_value(
            "REGION_DIRECTIVE_SOUL_COST", "STABILIZE_REGION_SOUL_COST", "PLAYER_REGION_DIRECTIVE_SOUL_COST",
            contains=("region", "directive", "cost"),
        )
        if region_cost is None:
            region_cost = self._cfg_cost_value(contains=("stabil", "cost"))
        if region_cost is not None:
            parts.append(f"stab/destab {region_cost}")

        school_cost = None
        god = self._player_god()
        if god is not None and hasattr(self.sim, "_school_status"):
            try:
                school_status = self.sim._school_status(god)
                school_cost = self._first_mapping_value(
                    school_status,
                    "move_soul_cost", "school_move_soul_cost", "move_cost", "soul_cost", "cost",
                )
            except Exception:
                school_cost = None
        if school_cost is None:
            school_cost = self._cfg_cost_value(
                "SCHOOL_MOVE_SOUL_COST", "ADVENTURER_SCHOOL_MOVE_SOUL_COST", "PLAYER_SCHOOL_MOVE_SOUL_COST",
                contains=("school", "cost"),
            )
        if school_cost is not None:
            parts.append(f"school move {school_cost}")

        try:
            lesser = RELIC_TIER_DEFS.get("lesser", {}).get("cost", None)
            greater = RELIC_TIER_DEFS.get("greater", {}).get("cost", None)
        except Exception:
            lesser = greater = None
        if lesser is not None or greater is not None:
            if lesser is not None and greater is not None:
                parts.append(f"relic L/G {lesser}/{greater}")
            elif lesser is not None:
                parts.append(f"relic L {lesser}")
            else:
                parts.append(f"relic G {greater}")

        return "Costs: " + (" | ".join(parts) if parts else "unavailable")

    def _holy_war_flag(self):
        """Compact God UI status for Holy War readiness."""
        if not hasattr(self.sim, "_holy_war_status"):
            return "HW: unavailable", 0
        try:
            status = self.sim._holy_war_status()
        except Exception as exc:
            return f"HW: status error ({exc})", 0

        cooldown = int(status.get("cooldown_ticks", 0) or 0)
        share = float(status.get("player_share", 0.0) or 0.0)
        cost = int(status.get("soul_cost", 0) or 0)
        targets = list(status.get("targets", []) or [])
        state = self.sim._player_god_state() if self._player_god() is not None else None
        souls = int(getattr(state, "souls", 0) or 0) if state is not None else 0

        if cooldown > 0:
            years = cooldown / float(TICKS_PER_YEAR)
            if years >= 1.0:
                return f"HW: cooldown {years:.1f}y", curses.A_DIM if self.has_colors else 0
            months = max(1, int(round(years * 12)))
            return f"HW: cooldown {months}m", curses.A_DIM if self.has_colors else 0

        if share < HOLY_WAR_MIN_ATTACKER_INFLUENCE:
            return f"HW: influence low {share:.1f}%/{HOLY_WAR_MIN_ATTACKER_INFLUENCE:.0f}%", curses.A_DIM if self.has_colors else 0

        if souls < cost:
            return f"HW: need souls {souls}/{cost}", curses.A_DIM if self.has_colors else 0

        if not targets:
            return "HW: no vulnerable god", curses.A_DIM if self.has_colors else 0

        try:
            names = []
            for deity, _state in targets[:2]:
                names.append(self._deity_display_name(deity))
            suffix = ", ".join(names)
            if len(targets) > 2:
                suffix += f" +{len(targets) - 2}"
        except Exception:
            suffix = f"{len(targets)} target{'s' if len(targets) != 1 else ''}"

        attr = curses.A_BOLD
        if self.has_colors:
            attr |= curses.color_pair(3)
        return f"HW READY: {suffix}", attr

    def _god_data_for_tick(self) -> dict:
        """Compute follower/champion data once per tick and cache it for the whole draw pass."""
        tick = getattr(self.sim.world, "tick", -1)
        cache = getattr(self, "_god_data_cache", None)
        if cache is not None and cache.get("tick") == tick:
            return cache
        try:
            all_followers = list(self.sim._player_followers(adventurers_only=False, alive_only=True))
        except Exception:
            all_followers = []
        try:
            live_champions = self._player_champion_rows(alive_only=True)
            dead_champions = self._player_champion_rows(alive_only=False)
        except Exception:
            live_champions = []
            dead_champions = []
        data = {
            "tick": tick,
            "followers": [a for a in all_followers if a.is_adventurer()],
            "children": [a for a in all_followers if not a.is_adventurer()],
            "live_champions": live_champions,
            "dead_champions": dead_champions,
        }
        self._god_data_cache = data
        return data

    def _god_page_counts(self) -> Dict[str, int]:
        data = self._god_data_for_tick()
        return {
            "disciples": len(data["followers"]),
            "active champs": len(data["live_champions"]),
            "children": len(data["children"]),
            "dead champs": len(data["dead_champions"]),
        }

    def draw_god_ui(self, height: int, width: int, top: Optional[int] = None, left: Optional[int] = None, bottom: Optional[int] = None, panel_w: Optional[int] = None):
        # Same right-side inspector lane as actor/monster inspectors. Never covers the map.
        top = 3 if top is None else int(top)
        left = 0 if left is None else int(left)
        bottom = (height - EVENT_ROWS - 4) if bottom is None else int(bottom)
        panel_w = min(width - left - 1, 132) if panel_w is None else min(int(panel_w), max(1, width - left - 1))
        if bottom <= top + 8:
            return
        self.god_panel_bounds = (left, top, left + panel_w - 1, bottom)
        god = self._player_god()
        state = self.sim._player_god_state() if god is not None else None
        souls = getattr(state, "souls", 0) if state is not None else 0
        followers = getattr(state, "followers", 0) if state is not None else 0
        influence = getattr(state, "influence_share", 0.0) if state is not None else 0.0
        try:
            favored_classes = self.sim._favored_classes_label(god)
        except Exception:
            favored_classes = "None"
        god_display = self._deity_display_name(god) if god is not None else self._player_god_name()

        self._safe_addstr(top, left, f"GOD INSPECTOR: {god_display}"[:panel_w - 1], curses.A_BOLD if self.has_colors else 0)
        self._safe_addstr(top + 1, left, "=" * max(1, panel_w - 1))
        self._safe_addstr(top + 2, left, f"Souls {souls} | Followers {followers} | Influence {influence:.1f}% | Favored classes: {favored_classes}"[:panel_w - 1])

        school_text = "School: unavailable"
        try:
            school_status = self.sim._school_status(god) if hasattr(self.sim, "_school_status") else None
            if school_status:
                region = school_status.get("region")
                region_name = getattr(region, "name", "Unknown")
                teachers = len(school_status.get("teachers", []) or [])
                children = len(school_status.get("children", []) or [])
                prestige = int(school_status.get("prestige_bonus", 0) or 0)
                capacity = int(school_status.get("capacity", children) or children)
                cap_bonus = int(school_status.get("capacity_bonus", 0) or 0)
                combat = len(school_status.get("combat_training", []) or [])
                rank = school_status.get("influence_rank") or "-"
                cd = int(school_status.get("move_cooldown_ticks", 0) or 0)
                move = "move ready" if cd <= 0 else f"move {cd / float(TICKS_PER_YEAR):.1f}y"
                school_text = f"School: {region_name} | kids {children}/{capacity} (+{cap_bonus}, rank {rank}) | combat {combat} | teachers {teachers} | prestige {prestige} | {move}"
        except Exception as exc:
            school_text = f"School: status error ({exc})"
        self._safe_addstr(top + 3, left, school_text[:panel_w - 1])

        hw_text, hw_attr = self._holy_war_flag()
        self._safe_addstr(top + 4, left, f"{hw_text}"[:panel_w - 1], hw_attr)
        if self.god_message:
            self._safe_addstr(top + 5, left, str(self.god_message)[:panel_w - 1], curses.A_BOLD)
        else:
            self._safe_addstr(top + 5, left, "No recent immortal action."[:panel_w - 1], curses.A_DIM if self.has_colors else 0)

        cost_attr = (curses.color_pair(3) | curses.A_BOLD) if self.has_colors else curses.A_BOLD
        self._safe_addstr(top + 6, left, self._god_cost_summary_line()[:panel_w - 1], cost_attr)

        counts = self._god_page_counts()
        page = self.god_page % 4
        page_titles = [
            ("DISCIPLES", "disciples", counts.get("disciples", 0)),
            ("ACTIVE CHAMPIONS", "active champs", counts.get("active champs", 0)),
            ("CHILDREN", "children", counts.get("children", 0)),
            ("DEAD CHAMPIONS", "dead champs", counts.get("dead champs", 0)),
        ]
        page_title, _page_key, page_count = page_titles[page]
        count_text = " | ".join([
            f"disciples {counts.get('disciples', 0)}",
            f"active champs {counts.get('active champs', 0)}",
            f"children {counts.get('children', 0)}",
            f"dead champs {counts.get('dead champs', 0)}",
        ])
        sort_dir = "asc" if getattr(self, "god_sort_reverse", False) else "desc"
        self._safe_addstr(top + 8, left, f"Page {page + 1}/4: {page_title} ({page_count}) | {count_text} | sort {getattr(self, 'god_filter_mode', 'none')} {sort_dir}"[:panel_w - 1], curses.A_DIM if self.has_colors else 0)

        rows = self._god_rows()
        if not rows:
            self._safe_addstr(top + 10, left, f"No {page_title.lower()} found."[:panel_w - 1])
            return
        self.god_selected_index = max(0, min(self.god_selected_index, len(rows) - 1))
        max_rows = max(1, bottom - (top + 12))
        max_scroll = max(0, len(rows) - max_rows)
        self.god_scroll = max(0, min(getattr(self, "god_scroll", 0), max_scroll))
        if not getattr(self, "god_mouse_scrolled", False):
            if self.god_selected_index < self.god_scroll:
                self.god_scroll = self.god_selected_index
            elif self.god_selected_index >= self.god_scroll + max_rows:
                self.god_scroll = max(0, self.god_selected_index - max_rows + 1)

        role_w = 8
        rep_w = 4
        lvl_w = 3
        hp_w = 8
        gap_w = 5  # spaces between columns in the formatted row
        if panel_w >= 118:
            name_w = max(28, min(44, panel_w // 3))
            region_w = max(16, min(28, panel_w // 5))
        elif panel_w >= 86:
            name_w = max(24, min(34, panel_w // 3))
            region_w = max(12, min(20, panel_w // 5))
        else:
            name_w = max(18, min(28, panel_w // 3))
            region_w = max(10, min(16, panel_w // 6))
        fixed = name_w + role_w + rep_w + lvl_w + hp_w + region_w + gap_w
        boon_w = max(8, panel_w - fixed - 1)
        header = f"{'name':<{name_w}} {'role':<{role_w}} rep lvl hp       {'region':<{region_w}} boons"
        self._safe_addstr(top + 10, left, header[:panel_w - 1], curses.A_BOLD if self.has_colors else 0)
        y = top + 12
        for idx, actor in enumerate(rows[self.god_scroll:self.god_scroll + max_rows], start=self.god_scroll):
            alive = bool(getattr(actor, "alive", False))
            hp_text = "dead" if not alive else f"{getattr(actor, 'hp', 0):>3}/{getattr(actor, 'max_hp', 0):<3}"
            rep = int(getattr(actor, "reputation", 0) or 0)
            level = int(getattr(actor, "level", 1) or 1)
            region_name = self.sim.world.region_name(getattr(actor, "region_id", -1)) if getattr(actor, "region_id", None) in self.sim.world.regions else "-"
            boon_text = self._boon_display_text(actor, boon_w) if hasattr(self, "_boon_display_text") else "-"
            line = (
                f"{actor.short_name():<{name_w}.{name_w}} "
                f"{self._role_label(getattr(actor, 'role', None)):<{role_w}.{role_w}} "
                f"{rep:>4} {level:>3} {hp_text:<8.8} "
                f"{region_name:<{region_w}.{region_w}} {boon_text}"
            )
            attr = self._actor_display_attr(actor, selected=(idx == self.god_selected_index))
            if page == 3 and self.has_colors and idx != self.god_selected_index:
                attr |= curses.A_DIM
            self._safe_addstr(y, left, line[:panel_w - 1], attr)
            y += 1
            if y >= bottom:
                break


    def draw_endgame_prompt(self, height: int, width: int):
        if self.endgame_prompt is None:
            return
        panel_w = min(width - 4, 92)
        left = max(0, (width - panel_w) // 2)
        top = max(4, min(height - 8, height // 2 - 4))
        title = self.endgame_prompt.get("title", "ENDGAME")
        message = self.endgame_prompt.get("message", "")
        attr = curses.A_BOLD
        if self.has_colors:
            attr |= curses.color_pair(3)
        border = "=" * max(1, panel_w - 1)
        self._safe_addstr(top, left, border, attr)
        self._safe_addstr(top + 1, left + 2, str(title)[:panel_w - 5], attr)
        self._safe_addstr(top + 2, left, "-" * max(1, panel_w - 1), attr)
        self._safe_addstr(top + 3, left + 2, str(message)[:panel_w - 5], attr)
        self._safe_addstr(top + 5, left + 2, "Press C/Enter to continue this run, or Q to quit. Like a bitch."[:panel_w - 5], attr)
        self._safe_addstr(top + 6, left, border, attr)

    def draw_help_menu(self, height: int, width: int):
        panel_w = min(width - 4, 104)
        panel_h = min(height - 4, 30)
        left = max(0, (width - panel_w) // 2)
        top = max(1, (height - panel_h) // 2)
        attr = curses.A_BOLD
        if self.has_colors:
            attr |= curses.color_pair(4)
        border = "=" * max(1, panel_w - 1)

        lines = get_help_lines(
            win_majority=ENDGAME_MAJORITY_CONTROL_THRESHOLD,
            divine_pct=ENDGAME_INFLUENCE_WIN_THRESHOLD,
            defeat_pct=ENDGAME_INFLUENCE_LOSS_THRESHOLD,
            pop_floor=ENDGAME_POPULATION_FLOOR,
        )

        body_top = top + 3
        body_bottom = top + panel_h - 1
        visible_rows = max(1, body_bottom - body_top)
        max_scroll = max(0, len(lines) - visible_rows)
        self.help_scroll = max(0, min(int(getattr(self, "help_scroll", 0)), max_scroll))

        self._safe_addstr(top, left, border, attr)
        self._safe_addstr(top + 1, left + 2, "HELP / GAMEPLAY", attr)
        self._safe_addstr(top + 2, left, "-" * max(1, panel_w - 1), attr)
        y = body_top
        for line in lines[self.help_scroll:self.help_scroll + visible_rows]:
            self._safe_addstr(y, left + 2, str(line)[:panel_w - 5])
            y += 1
        self._safe_addstr(top + panel_h - 1, left, border, attr)

    def draw_footer(self, height: int, width: int):
        footer = self.status_message
        if self.summary_mode:
            footer = "u close summary browser | left/right pick file | up/down scroll | PgUp/PgDn page | r refresh | q quit"
        elif self.god_mode:
            footer = "g close god UI | i actor | j journal | c cartography | m monsters | P champion | f sort | z reverse | S school | W Holy War | r relic | B boon | T target | X cancel all | L/D stab/destab"
        elif self.inspect_actor_id is not None:
            footer = "i/Esc close dossier | / find actor | P champion | T target | X cancel all | Y story | q quit"
        elif self._region_dossier_open():
            footer = "c close cartography | arrows select region | PgUp/PgDn/Home/End select actor | click/Enter/i opens inspector | q quit"
        self._safe_addstr(height - 1, 0, footer[:width - 1])

    def _refresh_region_ids(self):
        self.region_ids = sorted(self.sim.world.regions.keys())
        # Precompute index lookup to avoid O(n) list.index() calls in selection/navigation.
        self._region_id_to_index: Dict[int, int] = {rid: idx for idx, rid in enumerate(self.region_ids)}

    def _clamp_selection(self):
        if not self.region_ids:
            self.selected_region_index = 0
            self.selected_actor_index = 0
            return
        self.selected_region_index = max(0, min(self.selected_region_index, len(self.region_ids) - 1))
        actors_here = self._actors_in_selected_region()
        if not actors_here:
            self.selected_actor_index = 0
        else:
            self.selected_actor_index = max(0, min(self.selected_actor_index, len(actors_here) - 1))

    def _cycle_actor_selection(self, delta: int):
        actors_here = self._actors_in_selected_region()
        if not actors_here:
            self.selected_actor_index = 0
            return
        self.actor_list_mouse_scrolled = False
        self.selected_actor_index = (self.selected_actor_index + delta) % len(actors_here)
        if self.selected_actor_index < self.actor_list_scroll:
            self.actor_list_scroll = self.selected_actor_index
        elif self.selected_actor_index >= self.actor_list_scroll + ACTOR_PANEL_MAX_ROWS:
            self.actor_list_scroll = max(0, self.selected_actor_index - ACTOR_PANEL_MAX_ROWS + 1)

    def _inspect_selected_region_ruler(self):
        region = self._selected_region()
        if region is None:
            return
        ruler_id = getattr(region, "ruler_id", None)
        if ruler_id is None:
            return
        actor = self.sim.resolve_actor(ruler_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(ruler_id)
        if actor is None:
            return
        self._open_actor_inspector(actor)
        self._select_region_by_id(actor.region_id)
        self._select_actor_in_region(actor.id)

    def _selected_region(self):
        if not self.region_ids:
            return None
        rid = self.region_ids[self.selected_region_index]
        return self.sim.world.regions[rid]

    def _actors_in_selected_region(self):
        region = self._selected_region()
        if region is None:
            return []
        rid = region.id
        tick = getattr(self.sim.world, "tick", -1)
        cache = getattr(self, "_actors_in_region_cache", None)
        if cache is not None and cache[0] == rid and cache[1] == tick:
            return cache[2]
        # actors_in_region() returns from the O(1) region cache; no full-dict scan needed.
        actors_here = list(self.sim.world.actors_in_region(rid))
        actors_here.sort(key=lambda a: (not a.is_adventurer(), -getattr(a, "reputation", 0), a.short_name()))
        self._actors_in_region_cache = (rid, tick, actors_here)
        return actors_here

    def _selected_actor(self):
        actors_here = self._actors_in_selected_region()
        if not actors_here:
            return None
        return actors_here[self.selected_actor_index]

    def _inspected_actor(self):
        if self.inspect_actor_id is None:
            return None
        if hasattr(self.sim, "resolve_actor"):
            return self.sim.resolve_actor(self.inspect_actor_id)
        return self.sim.world.actors.get(self.inspect_actor_id)

    def _select_region_by_id(self, region_id: int):
        idx = getattr(self, "_region_id_to_index", {}).get(region_id)
        if idx is None and region_id in self.region_ids:
            idx = self.region_ids.index(region_id)
        if idx is not None:
            self.selected_region_index = idx
            self.selected_actor_index = 0
            self.actor_list_scroll = 0
            self.actor_list_mouse_scrolled = False
            self._clamp_selection()

    def _select_actor_in_region(self, actor_id: int):
        actors_here = self._actors_in_selected_region()
        for i, actor in enumerate(actors_here):
            if actor.id == actor_id:
                self.selected_actor_index = i
                return

    def _move_map_selection(self, direction: int, axis: str = "x"):
        region = self._selected_region()
        if region is None:
            return
        axial = self._map_layout_cache.get("axial", {})
        if not isinstance(axial, dict) or region.id not in axial:
            self._move_to_neighbor(direction)
            return

        q0, r0 = axial[region.id]
        target_dirs = []
        if axis == "x":
            target_dirs = [(1, 0), (1, -1), (0, 1)] if direction > 0 else [(-1, 0), (-1, 1), (0, -1)]
        else:
            target_dirs = [(0, -1), (1, -1), (-1, 0)] if direction < 0 else [(0, 1), (-1, 1), (1, 0)]

        inverse = {pos: rid for rid, pos in axial.items()}
        for dq, dr in target_dirs:
            rid = inverse.get((q0 + dq, r0 + dr))
            if rid is not None:
                self._select_region_by_id(rid)
                return
        self._move_to_neighbor(direction)

    def _move_to_neighbor(self, direction: int):
        region = self._selected_region()
        if region is None or not region.neighbors:
            return
        neighbors = sorted(region.neighbors)
        current_rid = region.id
        id_to_idx = getattr(self, "_region_id_to_index", {})
        current_idx = id_to_idx.get(current_rid, self.region_ids.index(current_rid))
        ranked = sorted(neighbors, key=lambda rid: abs(id_to_idx.get(rid, 0) - current_idx))
        target = ranked[0] if direction > 0 else ranked[-1]
        self._select_region_by_id(target)

    def _last_cached_positions(self) -> Optional[Dict[int, Tuple[int, int]]]:
        positions = self._map_layout_cache.get("screen")
        return positions if isinstance(positions, dict) else None
    def _region_positions(self, top: int, left: int, height: int, width: int) -> Dict[str, Dict[int, Tuple[int, int]]]:
        key = (
            tuple(self.region_ids),
            top,
            left,
            height,
            width,
            tuple((rid, tuple(sorted(self.sim.world.regions[rid].neighbors))) for rid in self.region_ids),
        )
        cached_key = self._map_layout_cache.get("key")
        if cached_key == key:
            return self._map_layout_cache  # type: ignore[return-value]

        layout = self._compute_hex_layout(top, left, height, width)
        self._map_layout_cache = {
            "key": key,
            "axial": layout["axial"],
            "screen": layout["screen"],
        }
        return self._map_layout_cache
    def _compute_hex_layout(self, top: int, left: int, height: int, width: int) -> Dict[str, Dict[int, Tuple[int, int]]]:
        if not self.region_ids:
            return {"axial": {}, "screen": {}}

        # Logical hex directions for the large ASCII tile. These are not direct
        # screen offsets. They are axial-like logical coords that project into
        # the user's desired sketch pattern:
        #   N=(0,-1), NE=(1,-1), SE=(1,0), S=(0,1), SW=(-1,1), NW=(-1,0)
        directions = [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)]
        neighbors = {rid: sorted(set(self.sim.world.regions[rid].neighbors)) for rid in self.region_ids}

        # For large worlds, favor a broad staggered sheet over a deep BFS clump.
        # This keeps 40+ regions visible in the middle pane instead of falling
        # off the bottom of the terminal.
        if len(self.region_ids) >= 30:
            draw_w = max(32, width - 2)
            cols_by_width = max(6, (draw_w - HEX_W) // 7 + 1)
            target_cols = max(8, int(math.ceil(math.sqrt(len(self.region_ids) * 2.2))))
            cols = max(1, min(cols_by_width, target_cols))
            logical = {}
            for idx, rid in enumerate(sorted(self.region_ids)):
                row = idx // cols
                col = idx % cols
                logical[rid] = (col - (row // 2), row)

            COL_PITCH = 7
            ROW_PITCH = 4
            DIAG_PITCH = 2
            grid_points = {}
            for rid, (q, r) in logical.items():
                gx = q * COL_PITCH
                gy = q * DIAG_PITCH + r * ROW_PITCH
                grid_points[rid] = (gx, gy)
            xs = [x for x, _ in grid_points.values()]
            ys = [y for _, y in grid_points.values()]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            draw_h = max(10, height - 1)
            span_y = HEX_H + max(0, max_y - min_y)
            offset_x = left + 1
            offset_y = top + max(0, (draw_h - span_y) // 2)
            screen = {}
            for rid, (gx, gy) in grid_points.items():
                screen[rid] = (offset_x + (gx - min_x), offset_y + (gy - min_y))
            return {"axial": logical, "screen": screen}

        root = max(self.region_ids, key=lambda rid: (len(neighbors[rid]), -rid))
        logical: Dict[int, Tuple[int, int]] = {root: (0, 0)}
        occupied = {(0, 0)}
        queue = [root]
        parent_dir: Dict[int, int] = {root: 0}

        while queue:
            rid = queue.pop(0)
            q, r = logical[rid]
            start_dir = parent_dir.get(rid, 0)
            candidate_dirs = list(range(start_dir, start_dir + 6))
            for nbr in neighbors[rid]:
                if nbr in logical:
                    continue
                placed = False
                for di in candidate_dirs:
                    dq, dr = directions[di % 6]
                    spot = (q + dq, r + dr)
                    if spot in occupied:
                        continue
                    logical[nbr] = spot
                    occupied.add(spot)
                    parent_dir[nbr] = (di + 3) % 6
                    queue.append(nbr)
                    placed = True
                    break
                if not placed:
                    best = self._best_open_hex_for_region(nbr, logical, occupied, neighbors, directions)
                    logical[nbr] = best
                    occupied.add(best)
                    queue.append(nbr)

        for rid in self.region_ids:
            if rid not in logical:
                best = self._best_open_hex_for_region(rid, logical, occupied, neighbors, directions)
                logical[rid] = best
                occupied.add(best)

        # Project logical coords into screen coords so the big ASCII hexes tile
        # like the user's white sketch.
        COL_PITCH = 7
        ROW_PITCH = 4
        DIAG_PITCH = 2

        grid_points: Dict[int, Tuple[int, int]] = {}
        for rid, (q, r) in logical.items():
            gx = q * COL_PITCH
            gy = q * DIAG_PITCH + r * ROW_PITCH
            grid_points[rid] = (gx, gy)

        xs = [x for x, _ in grid_points.values()]
        ys = [y for _, y in grid_points.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        draw_w = max(16, width - 2)
        draw_h = max(10, height - 1)
        span_x = HEX_W + max(0, max_x - min_x)
        span_y = HEX_H + max(0, max_y - min_y)
        offset_x = left + 1
        offset_y = top + max(0, (draw_h - span_y) // 2)

        screen: Dict[int, Tuple[int, int]] = {}
        for rid, (gx, gy) in grid_points.items():
            x = offset_x + (gx - min_x)
            y = offset_y + (gy - min_y)
            screen[rid] = (x, y)

        return {"axial": logical, "screen": screen}

    def _nudge_to_free_slot(self, x: int, y: int, occupied: set, min_x: int, max_x: int, min_y: int, max_y: int) -> Tuple[int, int]:
        if (x, y) not in occupied:
            return x, y
        for radius in range(1, 6):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx = max(min_x, min(max_x, x + dx))
                    ny = max(min_y, min(max_y, y + dy))
                    if (nx, ny) not in occupied:
                        return nx, ny
        return x, y


    def _best_open_hex_for_region(
        self,
        rid: int,
        axial: Dict[int, Tuple[int, int]],
        occupied: set,
        neighbors: Dict[int, List[int]],
        directions: List[Tuple[int, int]],
    ) -> Tuple[int, int]:
        placed_neighbors = [n for n in neighbors[rid] if n in axial]
        if not placed_neighbors:
            radius = 1
            while True:
                for q in range(-radius, radius + 1):
                    for r in range(-radius, radius + 1):
                        if abs(q + r) > radius:
                            continue
                        if (q, r) not in occupied:
                            return (q, r)
                radius += 1

        candidates = set()
        for nbr in placed_neighbors:
            q, r = axial[nbr]
            for dq, dr in directions:
                spot = (q + dq, r + dr)
                if spot not in occupied:
                    candidates.add(spot)

        if not candidates:
            radius = 1
            while True:
                for q in range(-radius, radius + 1):
                    for r in range(-radius, radius + 1):
                        if abs(q + r) > radius:
                            continue
                        if (q, r) not in occupied:
                            return (q, r)
                radius += 1

        def score(cell: Tuple[int, int]):
            q, r = cell
            adj = 0
            dist = 0
            for other in placed_neighbors:
                oq, or_ = axial[other]
                d = max(abs(q - oq), abs(r - or_), abs((q + r) - (oq + or_)))
                dist += d
                if d == 1:
                    adj += 1
            crowd = sum(1 for oq, or_ in axial.values() if max(abs(q - oq), abs(r - or_), abs((q + r) - (oq + or_))) <= 1)
            return (-adj, dist, crowd, abs(q) + abs(r))

        return min(candidates, key=score)

    def _put_canvas(self, chars, attrs, priority, x: int, y: int, ch: str, attr: int, pri: int):
        if y < 0 or y >= len(chars) or x < 0 or x >= len(chars[0]):
            return
        if pri < priority[y][x]:
            return
        chars[y][x] = ch
        attrs[y][x] = attr
        priority[y][x] = pri

    def _put_canvas_text(self, chars, attrs, priority, x: int, y: int, text: str, attr: int, pri: int):
        for i, ch in enumerate(text):
            self._put_canvas(chars, attrs, priority, x + i, y, ch, attr, pri)

    def _hex_edge_segments(self, x: int, y: int):
        return {
            "N":  [("text", x + 2, y + 0, "_____")],
            "NW": [("char", x + 1, y + 1, "/"), ("char", x + 0, y + 2, "/")],
            "NE": [("char", x + 7, y + 1, "\\"), ("char", x + 8, y + 2, "\\")],
            "SW": [("char", x + 0, y + 3, "\\"), ("char", x + 1, y + 4, "\\")],
            "SE": [("char", x + 8, y + 3, "/"), ("char", x + 7, y + 4, "/")],
            "S":  [("text", x + 2, y + 4, "_____")],
        }

    def _stamp_segment(self, chars, attrs, priority, segment, attr: int, pri: int):
        kind, sx, sy, payload = segment
        if kind == "char":
            self._put_canvas(chars, attrs, priority, sx, sy, payload, attr, pri)
        else:
            self._put_canvas_text(chars, attrs, priority, sx, sy, payload, attr, pri)

    def _stamp_big_hex(self, chars, attrs, priority, x: int, y: int, rid: int, region, selected: bool, logical: Dict[int, Tuple[int, int]], coord_to_region: Dict[Tuple[int, int], int]):
        border_attr = self._region_attr(region, selected=selected)
        fill_attr = self._hex_fill_attr(region, selected=selected)
        text_attr = border_attr | curses.A_BOLD
        seam_attr = self._hex_seam_attr(region, selected=False)
        directive_agents = self._region_directive_agents(rid)
        directive_blink_on = bool(directive_agents) and (int(time.time() * 2) % 2 == 0)
        directive_border_attr = border_attr | curses.A_BOLD | (curses.A_REVERSE if directive_blink_on else 0)

        rid_text = f"{rid:02d}"
        lean = self._region_lean(region)
        if self.map_color_view == "religion":
            deity, contested = self._region_dominant_deity(region)
            if contested or deity is None:
                fill = "+~+"
            else:
                fill = self._deity_short_label(deity)[:3].ljust(3)
        else:
            fill = "+++" if lean == "Good" else "---" if lean == "Evil" else "+~+"

        marker = " "
        if getattr(region, "polity_id", None) is not None:
            marker = "P"
        if getattr(region, "under_siege_by", None) is not None:
            marker = "!"
        monsters = self.sim.world.monsters_in_region(region.id)
        if monsters:
            marker = "M"
        if selected:
            marker = "*"

        q, r = logical[rid]
        occupied = {
            "N": (q + 0, r - 1) in coord_to_region,
            "NE": (q + 1, r - 1) in coord_to_region,
            "SE": (q + 1, r + 0) in coord_to_region,
            "S": (q + 0, r + 1) in coord_to_region,
            "SW": (q - 1, r + 1) in coord_to_region,
            "NW": (q - 1, r + 0) in coord_to_region,
        }

        segments = self._hex_edge_segments(x, y)

        # interior seams first
        for side, has_neighbor in occupied.items():
            if has_neighbor:
                for segment in segments[side]:
                    self._stamp_segment(chars, attrs, priority, segment, seam_attr, 1)

        # exposed borders next
        for side, has_neighbor in occupied.items():
            if not has_neighbor:
                for segment in segments[side]:
                    self._stamp_segment(chars, attrs, priority, segment, border_attr, 3)

        # selected region gets a full bright outline on top; active divine
        # region directives get a blinking border without adding more glyph clutter.
        if selected or directive_agents:
            outline_attr = directive_border_attr if directive_agents else border_attr
            outline_pri = 4 if selected else 3
            for side in ("N", "NE", "SE", "S", "SW", "NW"):
                for segment in segments[side]:
                    self._stamp_segment(chars, attrs, priority, segment, outline_attr, outline_pri)

        self._put_canvas_text(chars, attrs, priority, x + 3, y + 1, rid_text, text_attr, 5)
        self._put_canvas_text(chars, attrs, priority, x + 3, y + 2, fill, fill_attr, 5)
        self._put_canvas(chars, attrs, priority, x + 4, y + 3, marker, text_attr, 5)

    def _draw_line(self, y1: int, x1: int, y2: int, x2: int, char: str):
        dx = x2 - x1
        dy = y2 - y1
        steps = max(abs(dx), abs(dy))
        if steps <= 1:
            return
        for step in range(1, steps):
            x = x1 + int(round(dx * (step / steps)))
            y = y1 + int(round(dy * (step / steps)))
            self._safe_addstr(y, x, char)

    def _deity_name(self, deity) -> str:
        return getattr(deity, "value", getattr(deity, "name", str(deity)))

    def _deity_short_label(self, deity) -> str:
        name = self._deity_name(deity)
        words = [part for part in name.replace("_", " ").split() if part]
        if not words:
            return "???"
        if len(words) == 1:
            return words[0][:3].upper()
        return "".join(word[0] for word in words[:3]).upper()

    def _is_player_god(self, deity) -> bool:
        state = getattr(self.sim.world, "god_state", {}).get(deity)
        if state is not None and getattr(state, "is_player_god", False):
            return True
        profile = getattr(self.sim.world, "god_profiles", {}).get(deity)
        return bool(getattr(profile, "is_player", False) or getattr(profile, "is_player_god", False))

    def _region_dominant_deity(self, region):
        faith = getattr(self.sim.world, "commoner_faith_by_region", {}).get(region.id, {})
        if not faith:
            return None, True
        ranked = sorted(faith.items(), key=lambda item: item[1], reverse=True)
        if not ranked or ranked[0][1] <= 0:
            return None, True
        if len(ranked) > 1 and ranked[1][1] > 0:
            margin = ranked[0][1] - ranked[1][1]
            total = sum(faith.values()) or 1
            if margin <= max(2, int(total * 0.05)):
                return ranked[0][0], True
        return ranked[0][0], False

    def _religion_attr(self, region, selected: bool = False):
        attr = 0
        if selected:
            attr |= curses.A_BOLD
            if self.has_colors:
                attr |= curses.color_pair(4)
            return attr
        if not self.has_colors:
            return attr
        deity, contested = self._region_dominant_deity(region)
        if contested or deity is None:
            return curses.color_pair(6)
        if self._is_player_god(deity):
            return curses.color_pair(5) | curses.A_BOLD
        return self._order_attr_for_deity(deity)

    def _order_attr_for_deity(self, deity):
        if not self.has_colors:
            return 0
        name = self._deity_name(deity).lower()
        if "dark" in name or "evil" in name:
            return curses.color_pair(2)
        if "light" in name or "good" in name:
            return curses.color_pair(3)
        if "chance" in name:
            return curses.color_pair(1)
        return curses.color_pair(6)

    def _region_lean(self, region) -> str:
        if region.control >= 20:
            return "Good"
        if region.control <= -20:
            return "Evil"
        return "Contested"

    def _region_attr(self, region, selected: bool = False):
        attr = 0
        if selected:
            attr |= curses.A_BOLD
            if self.has_colors:
                attr |= curses.color_pair(4)
            return attr
        if not self.has_colors:
            return attr
        if self.map_color_view == "religion":
            return self._religion_attr(region, selected=selected)
        lean = self._region_lean(region)
        if lean == "Good":
            attr |= curses.color_pair(1)
        elif lean == "Evil":
            attr |= curses.color_pair(2)
        else:
            attr |= curses.color_pair(3)
        return attr

    def _hex_fill_attr(self, region, selected: bool = False):
        attr = 0
        if not self.has_colors:
            return attr
        if selected:
            return curses.color_pair(4) | curses.A_BOLD
        if self.map_color_view == "religion":
            return self._religion_attr(region, selected=selected)
        lean = self._region_lean(region)
        if lean == "Good":
            return curses.color_pair(1)
        if lean == "Evil":
            return curses.color_pair(2)
        return curses.color_pair(3)

    def _hex_seam_attr(self, region, selected: bool = False):
        if not self.has_colors:
            return curses.A_DIM
        if self.map_color_view == "religion":
            return self._religion_attr(region, selected=selected) | curses.A_DIM
        lean = self._region_lean(region)
        if lean == "Good":
            return curses.color_pair(1) | curses.A_DIM
        if lean == "Evil":
            return curses.color_pair(2) | curses.A_DIM
        return curses.color_pair(3) | curses.A_DIM

    def _region_ruler_name(self, region) -> str:
        ruler_id = getattr(region, "ruler_id", None)
        if ruler_id is None:
            return "None"
        actor = self.sim.resolve_actor(ruler_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(ruler_id)
        if actor is None or not actor.alive:
            return "None"
        return actor.short_name()

    def _region_polity_name(self, region) -> Optional[str]:
        polity_id = getattr(region, "polity_id", None)
        if polity_id is None:
            return None
        polity = self.sim.world.polities.get(polity_id)
        if polity is None:
            return f"P{polity_id}"
        return polity.name

    def _monster_summary(self, monsters) -> str:
        if not monsters:
            return "None"
        counts = {}
        for monster in monsters:
            counts[monster.kind.value] = counts.get(monster.kind.value, 0) + 1
        parts = [f"{name} x{count}" for name, count in sorted(counts.items())]
        return ", ".join(parts)

    def _rebuild_event_link_index(self) -> None:
        """Build a name→actor_id lookup table for event link highlighting.

        Called once per draw pass (from draw_events/draw_event_focus) rather than
        once per event line. The index maps lowercased full/short names to actor IDs
        so _event_actor_link_matches only needs to search text against the index.
        """
        index = []  # list of (needle_lower, label, actor_id)
        seen_labels: set = set()
        for actor in getattr(self.sim.world, "actors", {}).values():
            try:
                if not actor.is_adventurer():
                    continue
            except Exception:
                continue
            labels = []
            try:
                labels.append(actor.short_name())
            except Exception:
                pass
            try:
                labels.append(actor.full_name())
            except Exception:
                pass
            actor_id = getattr(actor, "id", None)
            for label in labels:
                label = str(label or "").strip()
                if len(label) < 4 or " " not in label:
                    continue
                key = (label.lower(), actor_id)
                if key in seen_labels:
                    continue
                seen_labels.add(key)
                index.append((label.lower(), label, actor_id))
        self._event_link_index = index
        self._event_link_index_actor_count = len(getattr(self.sim.world, "actors", {}))

    def _event_actor_link_matches(self, line: str):
        """Return non-overlapping actor-name matches for an event line.

        This deliberately only links adventurers, not commoners, so the event roll
        does not turn into a field of accidental one-off civilian names.
        """
        text = str(line or "")
        low = text.lower()
        # Use the per-draw-pass index built by _rebuild_event_link_index().
        # Fall back to rebuilding if somehow not present.
        index = getattr(self, "_event_link_index", None)
        if index is None:
            self._rebuild_event_link_index()
            index = self._event_link_index
        raw_matches = []
        for needle, label, actor_id in index:
            start = 0
            while True:
                idx = low.find(needle, start)
                if idx < 0:
                    break
                end = idx + len(label)
                before_ok = idx == 0 or not low[idx - 1].isalnum()
                after_ok = end >= len(low) or not low[end:end + 1].isalnum()
                if before_ok and after_ok:
                    raw_matches.append((idx, end, actor_id, label))
                start = idx + 1

        if not raw_matches:
            return []

        # Prefer longer labels at the same spot and reject overlaps.
        raw_matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
        chosen = []
        occupied = set()
        for start, end, actor_id, label in raw_matches:
            span = set(range(start, end))
            if occupied.intersection(span):
                continue
            chosen.append((start, end, actor_id, label))
            occupied.update(span)
        return chosen

    def _draw_event_line_with_links(self, y: int, x: int, width: int, event) -> None:
        line = self._event_text(event)
        if width <= 0:
            return
        clipped = line[:max(0, width - 1)]
        matches = [m for m in self._event_actor_link_matches(clipped) if m[0] < len(clipped)]
        if not matches:
            self._safe_addstr(y, x, clipped)
            return

        cursor = 0
        for start, end, actor_id, _label in matches:
            start = max(0, min(start, len(clipped)))
            end = max(start, min(end, len(clipped)))
            if start > cursor:
                self._safe_addstr(y, x + cursor, clipped[cursor:start])
            link_text = clipped[start:end]
            self._safe_addstr(y, x + start, link_text, self._link_attr())
            if actor_id is not None:
                self._event_link_hitboxes[actor_id] = (x + start, y, x + max(start, end - 1), y)
            cursor = end
        if cursor < len(clipped):
            self._safe_addstr(y, x + cursor, clipped[cursor:])

    def _event_text(self, event) -> str:
        ts = getattr(event, "timestamp", "")
        text = getattr(event, "text", str(event))
        return f"[{ts}] {text}" if ts else text

    def _actor_name(self, actor_id: Optional[int]) -> str:
        if actor_id is None:
            return "None"
        actor = self.sim.resolve_actor(actor_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(actor_id)
        return actor.short_name() if actor is not None else str(actor_id)

    def _actor_names(self, actor_ids) -> str:
        ids = [aid for aid in (actor_ids or []) if aid is not None]
        if not ids:
            return "None"
        names = [self._actor_name(aid) for aid in ids[:5]]
        if len(ids) > 5:
            names.append(f"+{len(ids) - 5} more")
        return ", ".join(names)

    def _actor_parent_display(self, actor, side: str) -> str:
        parent_id = getattr(actor, f"{side}_id", None)
        if parent_id is not None:
            parent = self.sim.resolve_actor(parent_id) if hasattr(self.sim, "resolve_actor") else self.sim.world.actors.get(parent_id)
            if parent is not None:
                return f"{parent.short_name()} ({parent_id})" if hasattr(parent, "short_name") else str(parent_id)
            tomb = (getattr(self.sim.world, "dead_actor_index", {}) or {}).get(parent_id)
            if tomb:
                return f"{tomb.get('name', parent_id)} ({parent_id})"
            return f"Unknown actor ({parent_id})"
        label = getattr(actor, f"{side}_label", None)
        if label:
            return str(label)
        return "Unknown"

    def _actor_age(self, actor) -> int:
        year, _month, _day, _tod, _season = self.sim.world.current_calendar()
        return max(0, year - actor.birth_year)

    def _actor_role_label(self, actor) -> str:
        role_value = getattr(getattr(actor, "role", None), "value", str(getattr(actor, "role", "")))
        if role_value == "Commoner" and self._actor_age(actor) < 16:
            return "Child"
        return role_value

    def _relic_name(self, relic_id: Optional[int]) -> str:
        if relic_id is None:
            return "None"
        relic = getattr(self.sim.world, 'relics', {}).get(relic_id)
        return relic.name if relic is not None else str(relic_id)

    def _region_name_safe(self, region_id: Optional[int]) -> str:
        if region_id is None:
            return "None"
        if region_id in self.sim.world.regions:
            return self.sim.world.region_name(region_id)
        return str(region_id)

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0):
        height, width = self.stdscr.getmaxyx()
        if y < 0 or y >= height or x < 0 or x >= width:
            return
        clipped = text[:max(0, width - x - 1)]
        if not clipped:
            return
        try:
            self.stdscr.addstr(y, x, clipped, attr)
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Curses UI for fantasy antfarm v124.")
    parser.add_argument("--seed", default=None, help="Seed string passed to the simulator.")
    parser.add_argument("--pop-scale", type=float, default=1.0, help="Population scale passed to the simulator.")
    parser.add_argument("--psum", type=int, default=0, help="Write periodic summaries every N years while the curses UI runs. 0 disables periodic summaries.")
    parser.add_argument("--load", default=None, help="Load a .fics save file instead of starting a new simulation.")
    parser.add_argument("--inject-god", default=None, help="After loading, reveal this .imrt as a new player god.")
    parser.add_argument("--inject-champion", default=None, help="Starting champion .stri for --inject-god.")
    parser.add_argument("--ascend-cult-id", type=int, default=None, help="After loading, formalize this proto-cult as the player god.")
    parser.add_argument("--no-autopause", action="store_true", help="Skip notification/autopause modal screens for unattended long runs.")
    return parser


def launch(stdscr, args):
    ux = UX(stdscr, args)
    ux.run()


if __name__ == "__main__":
    args = build_parser().parse_args()
    curses.wrapper(lambda stdscr: launch(stdscr, args))
