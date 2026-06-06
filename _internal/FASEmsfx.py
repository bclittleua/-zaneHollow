from __future__ import annotations

"""
audio_v2.py
Optional audio layer for Fantasy Antfarm curses UX.

Install for audio support:
    pip install pygame

Required folder layout:
    source/
      audio_v2.py
      audio/
        music/
          intro.mp3
          game_01.mp3
          game_02.mp3
        sfx/
          ui_click.wav
          ui_select.wav
          monster_appears.wav
          necromancer_crisis.wav
          holy_war.wav
          relic_claim.wav
          relic_lost.wav
          save.wav
          load.wav
          game_over.wav
          victory.wav
          error.wav
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# -----------------------------
# User-editable audio settings
# -----------------------------

AUDIO_ENABLED = True
MUSIC_ENABLED = True
SFX_ENABLED = True

MUSIC_VOLUME = 0.5   # 0.0 - 1.0
SFX_VOLUME = 0.4     # 0.0 - 1.0

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio"
MUSIC_DIR = AUDIO_DIR / "music"
SFX_DIR = AUDIO_DIR / "sfx"

# All path strings below are resolved beneath BASE_DIR/audio.
# Leave any entry as None, "", or an empty list to disable it.
INTRO_MUSIC: Optional[str] = "music/intro.mp3"

GAME_MUSIC_PLAYLIST: List[str] = [
    "music/game_01.mp3",
    "music/game_02.mp3",
    "music/game_03.mp3",
]

SFX: Dict[str, Optional[str]] = {
    "ui_click": "sfx/ui_click.wav",
    "ui_select": "sfx/ui_select.wav",
    "ui_back": "sfx/ui_back.wav",
    "monster_appears": "sfx/monster_appears.wav",
    "necromancer_crisis": "sfx/necromancer_crisis.wav",
    "holy_war": "sfx/holy_war.wav",
    "relic_claim": "sfx/relic_claim.wav",
    "relic_lost": "sfx/relic_lost.wav",
    "save": "sfx/save.wav",
    "load": "sfx/load.wav",
    "game_over": "sfx/game_over.wav",
    "victory": "sfx/victory.wav",
    "error": "sfx/error.wav",
}


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class AudioManager:
    enabled: bool = AUDIO_ENABLED
    music_enabled: bool = MUSIC_ENABLED
    sfx_enabled: bool = SFX_ENABLED
    music_volume: float = MUSIC_VOLUME
    sfx_volume: float = SFX_VOLUME
    intro_music: Optional[str] = INTRO_MUSIC
    game_playlist: List[str] = field(default_factory=lambda: list(GAME_MUSIC_PLAYLIST))
    sfx_paths: Dict[str, Optional[str]] = field(default_factory=lambda: dict(SFX))

    _pygame: object = None
    _ready: bool = False
    _sounds: Dict[str, object] = field(default_factory=dict)
    _mode: Optional[str] = None  # None | intro | game
    _game_index: int = 0
    _current_music_path: Optional[Path] = None

    def init(self) -> bool:
        """Initialize pygame.mixer if available. Returns True if audio is usable."""
        if not self.enabled:
            return False
        if self._ready:
            return True
        try:
            import pygame  # type: ignore
            self._pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._ready = True
            self._load_sfx()
            return True
        except Exception:
            # Audio is optional. Never crash the UI because sound failed.
            self._pygame = None
            self._ready = False
            return False

    def _resolve_audio_path(self, raw_path: Optional[str]) -> Optional[Path]:
        """Resolve paths beneath BASE_DIR/audio only. Missing files disable that entry."""
        if not raw_path:
            return None
        try:
            raw_text = str(raw_path).strip()
            if not raw_text:
                return None
            path = Path(raw_text)
            # Absolute paths are deliberately ignored so the project stays portable.
            if path.is_absolute():
                return None
            resolved = (AUDIO_DIR / path).resolve()
            audio_root = AUDIO_DIR.resolve()
            if audio_root not in resolved.parents and resolved != audio_root:
                return None
            return resolved if resolved.exists() else None
        except Exception:
            return None

    def _valid_game_tracks(self) -> List[Path]:
        tracks: List[Path] = []
        for raw_path in self.game_playlist:
            path = self._resolve_audio_path(raw_path)
            if path is not None:
                tracks.append(path)
        return tracks

    def set_enabled(self, enabled: bool) -> None:
        """Hard-enable/disable audio. Disabled means mixer is shut down and releases the device."""
        self.enabled = bool(enabled)
        if not self.enabled:
            self.shutdown()

    def game_track_names(self) -> List[str]:
        return [path.name for path in self._valid_game_tracks()]

    def current_game_track_name(self) -> str:
        path = self._current_music_path
        return path.name if path is not None else "None"

    def select_game_track(self, index: int, play_now: bool = True) -> bool:
        """Select a specific valid game-music track by index."""
        tracks = self._valid_game_tracks()
        if not tracks:
            return False
        self._game_index = max(0, int(index)) % len(tracks)
        if play_now:
            return self._play_game_track(tracks[self._game_index])
        return True

    def next_game_track(self) -> bool:
        tracks = self._valid_game_tracks()
        if not tracks:
            return False
        self._game_index = (self._game_index + 1) % len(tracks)
        return self._play_game_track(tracks[self._game_index])

    def previous_game_track(self) -> bool:
        tracks = self._valid_game_tracks()
        if not tracks:
            return False
        self._game_index = (self._game_index - 1) % len(tracks)
        return self._play_game_track(tracks[self._game_index])

    def _load_sfx(self) -> None:
        if not self._ready or not self.sfx_enabled or self._pygame is None:
            return
        self._sounds.clear()
        for key, raw_path in self.sfx_paths.items():
            path = self._resolve_audio_path(raw_path)
            if path is None:
                continue
            try:
                sound = self._pygame.mixer.Sound(str(path))
                sound.set_volume(_clamp_volume(self.sfx_volume))
                self._sounds[key] = sound
            except Exception:
                continue

    def play_intro_music(self, loops: int = 0) -> bool:
        """Play intro-card music. Loops by default until stopped or game music starts."""
        if not self.music_enabled or not self.init() or self._pygame is None:
            return False
        path = self._resolve_audio_path(self.intro_music)
        if path is None:
            return False
        try:
            if self._mode == "intro" and self._current_music_path == path:
                return True
            self._pygame.mixer.music.load(str(path))
            self._pygame.mixer.music.set_volume(_clamp_volume(self.music_volume))
            self._pygame.mixer.music.play(loops)
            self._mode = "intro"
            self._current_music_path = path
            return True
        except Exception:
            return False

    def play_game_music(self, start_index: int = 0) -> bool:
        """Start in-game playlist cycling. Call update() periodically to advance tracks."""
        if not self.music_enabled or not self.init() or self._pygame is None:
            return False
        tracks = self._valid_game_tracks()
        if not tracks:
            return False
        self._game_index = max(0, int(start_index)) % len(tracks)
        return self._play_game_track(tracks[self._game_index])

    def _play_game_track(self, path: Path) -> bool:
        try:
            if self._mode == "game" and self._current_music_path == path and self._pygame.mixer.music.get_busy():
                return True
            self._pygame.mixer.music.load(str(path))
            self._pygame.mixer.music.set_volume(_clamp_volume(self.music_volume))
            self._pygame.mixer.music.play(0)  # no per-track loop; playlist advances in update()
            self._mode = "game"
            self._current_music_path = path
            return True
        except Exception:
            return False

    def update(self) -> None:
        """Advance game playlist when the current track ends. Safe to call every UI loop."""
        if not self._ready or self._pygame is None or self._mode != "game":
            return
        try:
            if self._pygame.mixer.music.get_busy():
                return
        except Exception:
            return
        tracks = self._valid_game_tracks()
        if not tracks:
            self.stop_music()
            return
        self._game_index = (self._game_index + 1) % len(tracks)
        self._play_game_track(tracks[self._game_index])

    def stop_music(self) -> None:
        if not self._ready or self._pygame is None:
            return
        try:
            self._pygame.mixer.music.stop()
        except Exception:
            pass
        self._mode = None
        self._current_music_path = None

    def pause_music(self) -> None:
        if not self._ready or self._pygame is None:
            return
        try:
            self._pygame.mixer.music.pause()
        except Exception:
            pass

    def resume_music(self) -> None:
        if not self._ready or self._pygame is None:
            return
        try:
            self._pygame.mixer.music.unpause()
        except Exception:
            pass

    def play_sfx(self, key: str) -> bool:
        """Play a named sound effect. Missing keys/files are ignored."""
        if not self.sfx_enabled or not self.init():
            return False
        sound = self._sounds.get(key)
        if sound is None:
            return False
        try:
            sound.play()
            return True
        except Exception:
            return False

    def shutdown(self) -> None:
        if self._pygame is None:
            return
        try:
            self.stop_music()
            self._pygame.mixer.quit()
        except Exception:
            pass
        self._ready = False


# Convenience singleton for ux_curses.
audio = AudioManager()


def init_audio() -> bool:
    return audio.init()


def play_intro_music(loops: int = -1) -> bool:
    return audio.play_intro_music(loops=loops)


def play_game_music(start_index: int = 0) -> bool:
    return audio.play_game_music(start_index=start_index)


def update_audio() -> None:
    audio.update()


def stop_music() -> None:
    audio.stop_music()


def pause_music() -> None:
    audio.pause_music()


def resume_music() -> None:
    audio.resume_music()


def play_sfx(key: str) -> bool:
    return audio.play_sfx(key)


def set_audio_enabled(enabled: bool) -> None:
    audio.set_enabled(enabled)


def game_track_names() -> List[str]:
    return audio.game_track_names()


def current_game_track_name() -> str:
    return audio.current_game_track_name()


def select_game_track(index: int, play_now: bool = True) -> bool:
    return audio.select_game_track(index, play_now=play_now)


def next_game_track() -> bool:
    return audio.next_game_track()


def previous_game_track() -> bool:
    return audio.previous_game_track()


def shutdown_audio() -> None:
    audio.shutdown()
