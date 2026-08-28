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

from .libretro import (
    RETRO_DEVICE_ID_JOYPAD_MASK,
    RETRO_DEVICE_JOYPAD,
    RETRO_PIXEL_FORMAT_RGB565,
    RETRO_PIXEL_FORMAT_XRGB8888,
    LibretroCore,
)

STATE_MAGIC = b"FORGESTATE1\n"


class AudioSink:
    def __init__(self) -> None:
        self._chunks: deque[bytes] = deque()
        self._offset = 0
        self._lock = threading.Lock()
        self.device: AudioDevice | None = None

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
        self.state_path = Path(config["state_path"])
        self.screenshot_dir = Path(config["screenshot_dir"])
        self.system_dir = Path(config["system_dir"])
        self.game_id = str(config["game_id"])
        self.title = str(config["title"])
        self.fullscreen = bool(config.get("fullscreen", False))
        self.audio_enabled = bool(config.get("audio", True))
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
        self.audio = AudioSink()
        self.joystick: pygame.joystick.JoystickType | None = None
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
            button_map = {0: 0, 8: 1, 1: 2, 9: 3, 2: 4, 3: 6, 10: 9, 11: 10}
            for retro_id, button in button_map.items():
                if button < self.joystick.get_numbuttons():
                    mapping[retro_id] = mapping.get(retro_id, False) or bool(
                        self.joystick.get_button(button)
                    )
            if self.joystick.get_numhats():
                horizontal, vertical = self.joystick.get_hat(0)
                mapping[4] = mapping.get(4, False) or vertical > 0
                mapping[5] = mapping.get(5, False) or vertical < 0
                mapping[6] = mapping.get(6, False) or horizontal < 0
                mapping[7] = mapping.get(7, False) or horizontal > 0
        mask = 0
        for control_id, pressed in mapping.items():
            if pressed:
                mask |= 1 << control_id
        return mask

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
        self._show_message("State saved")

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
        self._show_message("State loaded")

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
            elif event.type == pygame.KEYDOWN:
                try:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
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
                        pygame.display.toggle_fullscreen()
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
                if not self.paused:
                    self.core.run()
                    completed_frames += 1
                    current_surface = self._surface_from_frame() or current_surface
                screen.fill((8, 10, 15))
                if current_surface:
                    area = screen.get_rect()
                    scale = min(
                        area.width / current_surface.get_width(),
                        area.height / current_surface.get_height(),
                    )
                    size = (
                        max(1, round(current_surface.get_width() * scale)),
                        max(1, round(current_surface.get_height() * scale)),
                    )
                    rendered = pygame.transform.scale(current_surface, size)
                    screen.blit(rendered, rendered.get_rect(center=area.center))
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
