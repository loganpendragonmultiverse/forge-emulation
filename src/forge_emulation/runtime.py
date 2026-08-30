from __future__ import annotations

import argparse
import ctypes
import json
import logging
import struct
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pygame
from pygame._sdl2.audio import AUDIO_S16, AudioDevice
from pygame._sdl2.sdl2 import INIT_AUDIO, init_subsystem

from .controller import binding_pressed, default_bindings
from .libretro import (
    RETRO_DEVICE_ID_JOYPAD_MASK,
    RETRO_DEVICE_JOYPAD,
    RETRO_PIXEL_FORMAT_RGB565,
    RETRO_PIXEL_FORMAT_XRGB8888,
    LibretroCore,
)

STATE_MAGIC = b"FORGESTATE1\n"


class AudioSink:
    def __init__(self, volume: int = 100, muted: bool = False) -> None:
        self._chunks: deque[bytes] = deque()
        self._offset = 0
        self._lock = threading.Lock()
        self.device: AudioDevice | None = None
        self.volume = max(0, min(100, int(volume)))
        self.muted = muted

    def set_level(self, volume: int, muted: bool) -> None:
        self.volume = max(0, min(100, int(volume)))
        self.muted = bool(muted)

    def open(self, sample_rate: int) -> None:
        self.device = AudioDevice(
            devicename=None,
            iscapture=False,
            frequency=max(8000, sample_rate),
            audioformat=AUDIO_S16,
            numchannels=2,
            chunksize=512,
            allowed_changes=0,
            callback=self._fill,
        )
        self.device.pause(0)

    def push(self, data: bytes) -> None:
        if not data:
            return
        level = 0 if self.muted else self.volume
        if level == 0:
            data = bytes(len(data))
        elif level != 100:
            samples = list(struct.unpack(f"<{len(data) // 2}h", data))
            data = struct.pack(
                f"<{len(samples)}h",
                *(max(-32768, min(32767, round(sample * level / 100))) for sample in samples),
            )
        with self._lock:
            self._chunks.append(data)

    def _fill(self, _device: AudioDevice, target: memoryview) -> None:
        needed = len(target)
        output = bytearray(needed)
        written = 0
        with self._lock:
            while written < needed and self._chunks:
                chunk = self._chunks[0]
                available = len(chunk) - self._offset
                take = min(needed - written, available)
                output[written : written + take] = chunk[self._offset : self._offset + take]
                written += take
                self._offset += take
                if self._offset >= len(chunk):
                    self._chunks.popleft()
                    self._offset = 0
            while len(self._chunks) > 32:
                self._chunks.popleft()
        target[:] = output

    def close(self) -> None:
        if self.device:
            self.device.close()
            self.device = None


class RuntimeSession:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.core_path = Path(config["core_path"])
        self.content_path = Path(config["content_path"])
        self.save_path = Path(config["save_path"])
        legacy_state = Path(config.get("state_path", "slot-1.state"))
        self.state_dir = Path(config.get("state_dir", legacy_state.parent))
        self.state_slot = max(1, min(9, int(config.get("state_slot", 1))))
        self.screenshot_dir = Path(config["screenshot_dir"])
        self.system_dir = Path(config["system_dir"])
        self.game_id = str(config["game_id"])
        self.title = str(config["title"])
        self.fullscreen = bool(config.get("fullscreen", False))
        self.audio_enabled = bool(config.get("audio", True))
        self.volume = max(0, min(100, int(config.get("volume", 100))))
        self.muted = bool(config.get("muted", False))
        self.scaling = str(config.get("scaling", "fit"))
        self.video_filter = str(config.get("video_filter", "nearest"))
        self.max_frames = max(0, int(config.get("max_frames", 0)))
        self.frame: bytes | None = None
        self.frame_width = 0
        self.frame_height = 0
        self.frame_pitch = 0
        self.input_mask = 0
        self.running = True
        self.paused = False
        self.message = ""
        self.message_until = 0.0
        self.audio = AudioSink(self.volume, self.muted)
        self.menu_open = False
        self.menu_index = 0
        self._menu_controller_latch = False
        self.joystick: pygame.joystick.JoystickType | None = None
        profiles = config.get("controller_profiles", {})
        self.controller_profiles = profiles if isinstance(profiles, dict) else {}
        self.core = LibretroCore(self.core_path, self.system_dir, self.save_path.parent)
        self.core.configure_callbacks(
            video=self._video,
            audio_sample=self._audio_sample,
            audio_batch=self._audio_batch,
            input_poll=self._input_poll,
            input_state=self._input_state,
        )

    def _video(self, data: int, width: int, height: int, pitch: int) -> None:
        if not data:
            return
        self.frame = ctypes.string_at(data, pitch * height)
        self.frame_width = width
        self.frame_height = height
        self.frame_pitch = pitch

    def _audio_sample(self, left: int, right: int) -> None:
        self.audio.push(struct.pack("<hh", left, right))

    def _audio_batch(self, data: Any, frames: int) -> int:
        self.audio.push(ctypes.string_at(data, frames * 4))
        return frames

    def _input_poll(self) -> None:
        self.input_mask = self._current_input_mask()

    def _input_state(self, port: int, device: int, _index: int, control_id: int) -> int:
        if port != 0 or device != RETRO_DEVICE_JOYPAD:
            return 0
        if control_id == RETRO_DEVICE_ID_JOYPAD_MASK:
            return self.input_mask
        return int(bool(self.input_mask & (1 << control_id)))

    def _current_input_mask(self) -> int:
        if self.menu_open:
            return 0
        keys = pygame.key.get_pressed()
        mapping = {
            0: keys[pygame.K_z],
            1: keys[pygame.K_a],
            2: keys[pygame.K_RSHIFT],
            3: keys[pygame.K_RETURN],
            4: keys[pygame.K_UP],
            5: keys[pygame.K_DOWN],
            6: keys[pygame.K_LEFT],
            7: keys[pygame.K_RIGHT],
            8: keys[pygame.K_x],
            9: keys[pygame.K_s],
            10: keys[pygame.K_q],
            11: keys[pygame.K_w],
        }
        if self.joystick:
            bindings = default_bindings()
            profile = self.controller_profiles.get(self.joystick.get_guid(), {})
            stored = profile.get("bindings", {}) if isinstance(profile, dict) else {}
            if isinstance(stored, dict):
                bindings.update(
                    {
                        action: binding
                        for action, binding in stored.items()
                        if action in bindings and isinstance(binding, dict)
                    }
                )
            retro_actions = {
                0: "b",
                1: "y",
                2: "select",
                3: "start",
                4: "up",
                5: "down",
                6: "left",
                7: "right",
                8: "a",
                9: "x",
                10: "l",
                11: "r",
            }
            for retro_id, action in retro_actions.items():
                mapping[retro_id] = mapping.get(retro_id, False) or binding_pressed(
                    self.joystick, bindings[action]
                )
        mask = 0
        for control_id, pressed in mapping.items():
            if pressed:
                mask |= 1 << control_id
        return mask

    def _controller_bindings(self) -> dict[str, dict[str, Any]]:
        bindings: dict[str, dict[str, Any]] = default_bindings()
        if not self.joystick:
            return bindings
        profile = self.controller_profiles.get(self.joystick.get_guid(), {})
        stored = profile.get("bindings", {}) if isinstance(profile, dict) else {}
        if isinstance(stored, dict):
            bindings.update(
                {
                    action: binding
                    for action, binding in stored.items()
                    if action in bindings and isinstance(binding, dict)
                }
            )
        return bindings

    def _surface_from_frame(self) -> pygame.Surface | None:
        if not self.frame or not self.frame_width or not self.frame_height:
            return None
        width, height = self.frame_width, self.frame_height
        bytes_per_pixel = 4 if self.core.pixel_format == RETRO_PIXEL_FORMAT_XRGB8888 else 2
        tight_pitch = width * bytes_per_pixel
        data = self.frame
        if self.frame_pitch != tight_pitch:
            data = b"".join(
                data[row * self.frame_pitch : row * self.frame_pitch + tight_pitch]
                for row in range(height)
            )
        if self.core.pixel_format == RETRO_PIXEL_FORMAT_XRGB8888:
            # XRGB8888 arrives as B, G, R, unused bytes on little-endian Windows.
            # Pygame accepts BGRA rather than BGRX; convert immediately so the
            # unused byte is not interpreted as transparent alpha.
            return pygame.image.frombuffer(data, (width, height), "BGRA").convert()
        masks = (
            (0xF800, 0x07E0, 0x001F, 0)
            if self.core.pixel_format == RETRO_PIXEL_FORMAT_RGB565
            else (0x7C00, 0x03E0, 0x001F, 0)
        )
        surface = pygame.Surface((width, height), depth=16, masks=masks)
        surface.get_buffer().write(data)
        return surface

    def _show_message(self, message: str) -> None:
        self.message = message
        self.message_until = time.monotonic() + 2.5

    @property
    def state_path(self) -> Path:
        return self.state_dir / f"slot-{self.state_slot}.state"

    def _save_state(self) -> None:
        metadata = {
            "game_id": self.game_id,
            "core": self.core.name,
            "core_version": self.core.version,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        header = json.dumps(metadata, sort_keys=True).encode()
        state = self.core.serialize()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".partial")
        temporary.write_bytes(STATE_MAGIC + struct.pack("<I", len(header)) + header + state)
        temporary.replace(self.state_path)
        self._show_message(f"State saved to slot {self.state_slot}")

    def _load_state(self) -> None:
        data = self.state_path.read_bytes()
        if not data.startswith(STATE_MAGIC):
            raise RuntimeError("This is not a ForgeEmulation save state.")
        header_length = struct.unpack("<I", data[len(STATE_MAGIC) : len(STATE_MAGIC) + 4])[0]
        header_start = len(STATE_MAGIC) + 4
        metadata = json.loads(data[header_start : header_start + header_length])
        if metadata.get("game_id") != self.game_id:
            raise RuntimeError("This state belongs to a different game.")
        if metadata.get("core") != self.core.name:
            raise RuntimeError("This state was created by a different emulator core.")
        self.core.unserialize(data[header_start + header_length :])
        self._show_message(f"State loaded from slot {self.state_slot}")

    @staticmethod
    def scaled_size(source: tuple[int, int], target: tuple[int, int], mode: str) -> tuple[int, int]:
        source_width, source_height = source
        target_width, target_height = target
        if mode == "stretch":
            return max(1, target_width), max(1, target_height)
        scale = min(target_width / source_width, target_height / source_height)
        if mode == "integer" and scale >= 1:
            scale = max(1, int(scale))
        return max(1, round(source_width * scale)), max(1, round(source_height * scale))

    def _menu_items(self) -> list[str]:
        return [
            "Resume",
            f"Save state — slot {self.state_slot}",
            f"Load state — slot {self.state_slot}",
            f"State slot — {self.state_slot}",
            "Screenshot",
            "Reset game",
            f"Scaling — {self.scaling.title()}",
            f"Filter — {self.video_filter.title()}",
            f"Volume — {'Muted' if self.muted else str(self.volume) + '%'}",
            "Toggle fullscreen",
            "Exit game",
        ]

    def _adjust_menu(self, delta: int) -> None:
        if self.menu_index == 3:
            self.state_slot = ((self.state_slot - 1 + delta) % 9) + 1
        elif self.menu_index == 6:
            values = ["fit", "integer", "stretch"]
            self.scaling = values[(values.index(self.scaling) + delta) % len(values)]
        elif self.menu_index == 7:
            self.video_filter = "smooth" if self.video_filter == "nearest" else "nearest"
        elif self.menu_index == 8:
            self.muted = False
            self.volume = max(0, min(100, self.volume + delta * 10))
            self.audio.set_level(self.volume, self.muted)

    def _activate_menu(self, current_surface: pygame.Surface | None) -> None:
        if self.menu_index == 0:
            self.menu_open = False
        elif self.menu_index == 1:
            self._save_state()
        elif self.menu_index == 2:
            self._load_state()
        elif self.menu_index == 3:
            self._adjust_menu(1)
        elif self.menu_index == 4 and current_surface:
            self._save_screenshot(current_surface)
        elif self.menu_index == 5:
            self.core.reset()
            self._show_message("Game reset")
        elif self.menu_index in {6, 7}:
            self._adjust_menu(1)
        elif self.menu_index == 8:
            self.muted = not self.muted
            self.audio.set_level(self.volume, self.muted)
        elif self.menu_index == 9:
            self._toggle_fullscreen()
        elif self.menu_index == 10:
            self.running = False

    def _toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        flags = pygame.DOUBLEBUF | (pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE)
        size = (0, 0) if self.fullscreen else (960, 720)
        pygame.display.set_mode(size, flags)

    def _draw_menu(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((4, 6, 10, 190))
        screen.blit(overlay, (0, 0))
        items = self._menu_items()
        width = min(560, screen.get_width() - 40)
        panel = pygame.Rect(0, 0, width, min(screen.get_height() - 40, 96 + len(items) * 38))
        panel.center = screen.get_rect().center
        pygame.draw.rect(screen, (20, 24, 33), panel, border_radius=14)
        pygame.draw.rect(screen, (59, 68, 84), panel, 1, border_radius=14)
        heading = font.render("FORGE QUICK MENU", True, (244, 122, 103))
        screen.blit(heading, (panel.x + 24, panel.y + 20))
        for index, label in enumerate(items):
            row = pygame.Rect(panel.x + 16, panel.y + 58 + index * 38, panel.width - 32, 34)
            if index == self.menu_index:
                pygame.draw.rect(screen, (45, 53, 68), row, border_radius=7)
            text = font.render(
                label, True, (248, 249, 252) if index == self.menu_index else (174, 182, 196)
            )
            screen.blit(text, (row.x + 12, row.y + 7))

    def _save_screenshot(self, surface: pygame.Surface) -> None:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.screenshot_dir / f"{timestamp}.png"
        pygame.image.save(surface, target)
        self._show_message(f"Screenshot saved: {target.name}")

    def _handle_events(self, current_surface: pygame.Surface | None) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.JOYDEVICEADDED and self.joystick is None:
                self.joystick = pygame.joystick.Joystick(event.device_index)
            elif event.type == pygame.JOYDEVICEREMOVED and self.joystick:
                if self.joystick.get_instance_id() == event.instance_id:
                    self.joystick = None
            elif self.menu_open and event.type == pygame.JOYHATMOTION:
                horizontal, vertical = event.value
                if vertical:
                    self.menu_index = (self.menu_index - vertical) % len(self._menu_items())
                if horizontal:
                    self._adjust_menu(horizontal)
            elif self.menu_open and event.type == pygame.JOYBUTTONDOWN:
                if event.button == 0:
                    self._activate_menu(current_surface)
                elif event.button == 1:
                    self.menu_open = False
            elif event.type == pygame.KEYDOWN:
                try:
                    if self.menu_open:
                        if event.key in {pygame.K_ESCAPE, pygame.K_TAB}:
                            self.menu_open = False
                        elif event.key == pygame.K_UP:
                            self.menu_index = (self.menu_index - 1) % len(self._menu_items())
                        elif event.key == pygame.K_DOWN:
                            self.menu_index = (self.menu_index + 1) % len(self._menu_items())
                        elif event.key == pygame.K_LEFT:
                            self._adjust_menu(-1)
                        elif event.key == pygame.K_RIGHT:
                            self._adjust_menu(1)
                        elif event.key in {pygame.K_RETURN, pygame.K_SPACE}:
                            self._activate_menu(current_surface)
                        continue
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_TAB:
                        self.menu_open = True
                        self.menu_index = 0
                    elif event.key == pygame.K_SPACE:
                        self.paused = not self.paused
                        self._show_message("Paused" if self.paused else "Resumed")
                    elif event.key == pygame.K_F5:
                        self._save_state()
                    elif event.key == pygame.K_F8:
                        self._load_state()
                    elif event.key == pygame.K_F12 and current_surface:
                        self._save_screenshot(current_surface)
                    elif event.key == pygame.K_r and event.mod & pygame.KMOD_CTRL:
                        self.core.reset()
                        self._show_message("Game reset")
                    elif event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT:
                        self._toggle_fullscreen()
                except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                    logging.exception("Runtime action failed")
                    self._show_message(str(exc))

    def run(self) -> dict[str, Any]:
        started = datetime.now(UTC)
        exit_reason = "normal"
        core_name = ""
        core_version = ""
        pygame.display.init()
        pygame.font.init()
        pygame.joystick.init()
        init_subsystem(INIT_AUDIO)
        if pygame.joystick.get_count():
            self.joystick = pygame.joystick.Joystick(0)
        flags = pygame.RESIZABLE | pygame.DOUBLEBUF
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        screen = pygame.display.set_mode((960, 720), flags)
        pygame.display.set_caption(f"ForgeEmulation — {self.title}")
        font = pygame.font.SysFont("Segoe UI", 18)
        clock = pygame.time.Clock()
        current_surface: pygame.Surface | None = None
        try:
            self.core.initialize()
            av_info = self.core.load_game(self.content_path)
            core_name = self.core.name
            core_version = self.core.version
            self.core.load_save_ram(self.save_path)
            if self.audio_enabled:
                self.audio.open(round(av_info.timing.sample_rate))
            target_fps = max(1.0, float(av_info.timing.fps))
            completed_frames = 0
            while self.running and not self.core.shutdown_requested:
                self._handle_events(current_surface)
                if self.joystick:
                    bindings = self._controller_bindings()
                    select_start = binding_pressed(
                        self.joystick, bindings["select"]
                    ) and binding_pressed(self.joystick, bindings["start"])
                    if select_start and not self._menu_controller_latch:
                        self.menu_open = not self.menu_open
                        self.menu_index = 0
                    self._menu_controller_latch = bool(select_start)
                if not self.paused and not self.menu_open:
                    self.core.run()
                    completed_frames += 1
                    current_surface = self._surface_from_frame() or current_surface
                screen.fill((8, 10, 15))
                if current_surface:
                    area = screen.get_rect()
                    size = self.scaled_size(current_surface.get_size(), area.size, self.scaling)
                    transform = (
                        pygame.transform.smoothscale
                        if self.video_filter == "smooth"
                        else pygame.transform.scale
                    )
                    rendered = transform(current_surface, size)
                    screen.blit(rendered, rendered.get_rect(center=area.center))
                if self.menu_open:
                    self._draw_menu(screen, font)
                if self.message and time.monotonic() < self.message_until:
                    text = font.render(self.message, True, (245, 247, 250))
                    panel = text.get_rect()
                    panel.inflate_ip(28, 18)
                    panel.midbottom = (screen.get_width() // 2, screen.get_height() - 24)
                    pygame.draw.rect(screen, (28, 32, 43), panel, border_radius=10)
                    screen.blit(text, text.get_rect(center=panel.center))
                pygame.display.flip()
                if self.max_frames and completed_frames >= self.max_frames:
                    break
                clock.tick(target_fps)
        except Exception:
            exit_reason = "error"
            logging.exception("Runtime session failed")
            raise
        finally:
            try:
                self.core.save_save_ram(self.save_path)
            except Exception:
                logging.exception("Could not save native save RAM")
            self.audio.close()
            try:
                self.core.close()
            except Exception:
                logging.exception("Could not close core cleanly")
            pygame.quit()
        ended = datetime.now(UTC)
        return {
            "started_at": started.isoformat(timespec="seconds"),
            "ended_at": ended.isoformat(timespec="seconds"),
            "duration_seconds": max(0, round((ended - started).total_seconds())),
            "core_name": core_name,
            "core_version": core_version,
            "exit_reason": exit_reason,
            "state_slot": self.state_slot,
            "runtime_settings": {
                "fullscreen": self.fullscreen,
                "scaling": self.scaling,
                "video_filter": self.video_filter,
                "volume": self.volume,
                "muted": self.muted,
            },
        }


def _configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ForgeEmulation isolated libretro runtime")
    parser.add_argument("--config", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    _configure_logging(Path(config["log_path"]))
    result_path = Path(config["result_path"])
    try:
        result = RuntimeSession(config).run()
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        result_path.write_text(
            json.dumps({"exit_reason": "error", "error": str(exc)}, indent=2),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
