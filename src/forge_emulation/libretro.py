from __future__ import annotations

import ctypes
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

RETRO_API_VERSION = 1

RETRO_ENVIRONMENT_GET_OVERSCAN = 2
RETRO_ENVIRONMENT_GET_CAN_DUPE = 3
RETRO_ENVIRONMENT_SET_MESSAGE = 6
RETRO_ENVIRONMENT_SHUTDOWN = 7
RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL = 8
RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9
RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10
RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS = 11
RETRO_ENVIRONMENT_GET_VARIABLE = 15
RETRO_ENVIRONMENT_SET_VARIABLES = 16
RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE = 17
RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME = 18
RETRO_ENVIRONMENT_GET_LIBRETRO_PATH = 19
RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY = 30
RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31
RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO = 32
RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO = 34
RETRO_ENVIRONMENT_SET_CONTROLLER_INFO = 35
RETRO_ENVIRONMENT_SET_MEMORY_MAPS = 36
RETRO_ENVIRONMENT_SET_GEOMETRY = 37
RETRO_ENVIRONMENT_GET_USERNAME = 38
RETRO_ENVIRONMENT_GET_LANGUAGE = 39
RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS = 42
RETRO_ENVIRONMENT_GET_VFS_INTERFACE = 45
RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE = 47
RETRO_ENVIRONMENT_GET_FASTFORWARDING = 49
RETRO_ENVIRONMENT_GET_TARGET_REFRESH_RATE = 50
RETRO_ENVIRONMENT_GET_INPUT_BITMASKS = 51
RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION = 52
RETRO_ENVIRONMENT_SET_CORE_OPTIONS = 53
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL = 54
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY = 55
RETRO_ENVIRONMENT_GET_PREFERRED_HW_RENDER = 56
RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION = 57
RETRO_ENVIRONMENT_SET_DISK_CONTROL_EXT_INTERFACE = 58
RETRO_ENVIRONMENT_GET_MESSAGE_INTERFACE_VERSION = 59
RETRO_ENVIRONMENT_SET_MESSAGE_EXT = 60
RETRO_ENVIRONMENT_GET_INPUT_MAX_USERS = 61
RETRO_ENVIRONMENT_SET_AUDIO_BUFFER_STATUS_CALLBACK = 62
RETRO_ENVIRONMENT_SET_MINIMUM_AUDIO_LATENCY = 63
RETRO_ENVIRONMENT_SET_FASTFORWARDING_OVERRIDE = 64
RETRO_ENVIRONMENT_SET_CONTENT_INFO_OVERRIDE = 65
RETRO_ENVIRONMENT_GET_GAME_INFO_EXT = 66
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2 = 67
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL = 68
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK = 69
RETRO_ENVIRONMENT_SET_VARIABLE = 70
RETRO_ENVIRONMENT_GET_THROTTLE_STATE = 71
RETRO_ENVIRONMENT_GET_SAVESTATE_CONTEXT = 72
RETRO_ENVIRONMENT_GET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE_SUPPORT = 73
RETRO_ENVIRONMENT_GET_JIT_CAPABLE = 74
RETRO_ENVIRONMENT_GET_MICROPHONE_INTERFACE = 75
RETRO_ENVIRONMENT_SET_NETPACKET_INTERFACE = 76
RETRO_ENVIRONMENT_GET_DEVICE_POWER = 77
RETRO_ENVIRONMENT_SET_NETPACKET_INTERFACE_V2 = 78

RETRO_PIXEL_FORMAT_0RGB1555 = 0
RETRO_PIXEL_FORMAT_XRGB8888 = 1
RETRO_PIXEL_FORMAT_RGB565 = 2

RETRO_MEMORY_SAVE_RAM = 0
RETRO_DEVICE_JOYPAD = 1
RETRO_DEVICE_ID_JOYPAD_MASK = 256


class RetroSystemInfo(ctypes.Structure):
    _fields_ = [
        ("library_name", ctypes.c_char_p),
        ("library_version", ctypes.c_char_p),
        ("valid_extensions", ctypes.c_char_p),
        ("need_fullpath", ctypes.c_bool),
        ("block_extract", ctypes.c_bool),
    ]


class RetroGameInfo(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_char_p),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
        ("meta", ctypes.c_char_p),
    ]


class RetroGameGeometry(ctypes.Structure):
    _fields_ = [
        ("base_width", ctypes.c_uint),
        ("base_height", ctypes.c_uint),
        ("max_width", ctypes.c_uint),
        ("max_height", ctypes.c_uint),
        ("aspect_ratio", ctypes.c_float),
    ]


class RetroSystemTiming(ctypes.Structure):
    _fields_ = [("fps", ctypes.c_double), ("sample_rate", ctypes.c_double)]


class RetroSystemAvInfo(ctypes.Structure):
    _fields_ = [("geometry", RetroGameGeometry), ("timing", RetroSystemTiming)]


class RetroVariable(ctypes.Structure):
    _fields_ = [("key", ctypes.c_char_p), ("value", ctypes.c_char_p)]


class RetroMessage(ctypes.Structure):
    _fields_ = [("msg", ctypes.c_char_p), ("frames", ctypes.c_uint)]


EnvironmentCallback = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
VideoRefreshCallback = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t
)
AudioSampleCallback = ctypes.CFUNCTYPE(None, ctypes.c_int16, ctypes.c_int16)
AudioSampleBatchCallback = ctypes.CFUNCTYPE(
    ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t
)
InputPollCallback = ctypes.CFUNCTYPE(None)
InputStateCallback = ctypes.CFUNCTYPE(
    ctypes.c_int16, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint
)


def _text(value: bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if value else ""


class LibretroCore:
    def __init__(self, path: Path, system_directory: Path, save_directory: Path):
        if not path.is_file():
            raise FileNotFoundError(path)
        self.path = path.resolve()
        self.system_directory = system_directory.resolve()
        self.save_directory = save_directory.resolve()
        self.system_directory.mkdir(parents=True, exist_ok=True)
        self.save_directory.mkdir(parents=True, exist_ok=True)
        self.library = ctypes.CDLL(str(self.path))
        self.pixel_format = RETRO_PIXEL_FORMAT_0RGB1555
        self.shutdown_requested = False
        self.variables: dict[str, bytes] = {}
        self._system_directory_bytes = str(self.system_directory).encode()
        self._save_directory_bytes = str(self.save_directory).encode()
        self._core_path_bytes = str(self.path).encode()
        self._content_directory_bytes = b""
        self._username_bytes = b"ForgeEmulation"
        self._game_data: ctypes.Array[ctypes.c_char] | None = None
        self._callbacks: list[Any] = []
        self._initialized = False
        self._loaded = False
        self._configure_signatures()
        api_version = int(self.library.retro_api_version())
        if api_version != RETRO_API_VERSION:
            raise RuntimeError(f"Unsupported libretro API version: {api_version}")

    def _configure_signatures(self) -> None:
        lib = self.library
        lib.retro_api_version.restype = ctypes.c_uint
        lib.retro_set_environment.argtypes = [EnvironmentCallback]
        lib.retro_set_video_refresh.argtypes = [VideoRefreshCallback]
        lib.retro_set_audio_sample.argtypes = [AudioSampleCallback]
        lib.retro_set_audio_sample_batch.argtypes = [AudioSampleBatchCallback]
        lib.retro_set_input_poll.argtypes = [InputPollCallback]
        lib.retro_set_input_state.argtypes = [InputStateCallback]
        lib.retro_get_system_info.argtypes = [ctypes.POINTER(RetroSystemInfo)]
        lib.retro_get_system_av_info.argtypes = [ctypes.POINTER(RetroSystemAvInfo)]
        lib.retro_load_game.argtypes = [ctypes.POINTER(RetroGameInfo)]
        lib.retro_load_game.restype = ctypes.c_bool
        lib.retro_serialize_size.restype = ctypes.c_size_t
        lib.retro_serialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.retro_serialize.restype = ctypes.c_bool
        lib.retro_unserialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.retro_unserialize.restype = ctypes.c_bool
        lib.retro_get_memory_data.argtypes = [ctypes.c_uint]
        lib.retro_get_memory_data.restype = ctypes.c_void_p
        lib.retro_get_memory_size.argtypes = [ctypes.c_uint]
        lib.retro_get_memory_size.restype = ctypes.c_size_t

    def configure_callbacks(
        self,
        *,
        video: Callable[[int, int, int, int], None],
        audio_sample: Callable[[int, int], None],
        audio_batch: Callable[[Any, int], int],
        input_poll: Callable[[], None],
        input_state: Callable[[int, int, int, int], int],
    ) -> None:
        environment_callback = EnvironmentCallback(self._environment)
        video_callback = VideoRefreshCallback(video)
        audio_sample_callback = AudioSampleCallback(audio_sample)
        audio_batch_callback = AudioSampleBatchCallback(audio_batch)
        input_poll_callback = InputPollCallback(input_poll)
        input_state_callback = InputStateCallback(input_state)
        self._callbacks = [
            environment_callback,
            video_callback,
            audio_sample_callback,
            audio_batch_callback,
            input_poll_callback,
            input_state_callback,
        ]
        self.library.retro_set_environment(environment_callback)
        self.library.retro_set_video_refresh(video_callback)
        self.library.retro_set_audio_sample(audio_sample_callback)
        self.library.retro_set_audio_sample_batch(audio_batch_callback)
        self.library.retro_set_input_poll(input_poll_callback)
        self.library.retro_set_input_state(input_state_callback)

    def initialize(self) -> None:
        self.library.retro_init()
        self._initialized = True

    def system_info(self) -> RetroSystemInfo:
        info = RetroSystemInfo()
        self.library.retro_get_system_info(ctypes.byref(info))
        return info

    @property
    def name(self) -> str:
        return _text(self.system_info().library_name)

    @property
    def version(self) -> str:
        return _text(self.system_info().library_version)

    def load_game(self, content_path: Path) -> RetroSystemAvInfo:
        info = self.system_info()
        path_bytes = str(content_path.resolve()).encode()
        self._content_directory_bytes = str(content_path.resolve().parent).encode()
        if info.need_fullpath:
            game = RetroGameInfo(path=path_bytes, data=None, size=0, meta=None)
        else:
            content = content_path.read_bytes()
            self._game_data = ctypes.create_string_buffer(content)
            game = RetroGameInfo(
                path=path_bytes,
                data=ctypes.cast(self._game_data, ctypes.c_void_p),
                size=len(content),
                meta=None,
            )
        if not self.library.retro_load_game(ctypes.byref(game)):
            raise RuntimeError(f"{self.name} rejected the selected game content.")
        self._loaded = True
        av_info = RetroSystemAvInfo()
        self.library.retro_get_system_av_info(ctypes.byref(av_info))
        return av_info

    def run(self) -> None:
        self.library.retro_run()

    def reset(self) -> None:
        self.library.retro_reset()

    def serialize(self) -> bytes:
        size = int(self.library.retro_serialize_size())
        if size <= 0:
            raise RuntimeError("This core does not support save states.")
        buffer = ctypes.create_string_buffer(size)
        if not self.library.retro_serialize(buffer, size):
            raise RuntimeError("The core could not create a save state.")
        return buffer.raw

    def unserialize(self, state: bytes) -> None:
        buffer = ctypes.create_string_buffer(state)
        if not self.library.retro_unserialize(buffer, len(state)):
            raise RuntimeError("The core rejected this save state.")

    def load_save_ram(self, path: Path) -> None:
        size = int(self.library.retro_get_memory_size(RETRO_MEMORY_SAVE_RAM))
        pointer = self.library.retro_get_memory_data(RETRO_MEMORY_SAVE_RAM)
        if not pointer or size <= 0 or not path.is_file():
            return
        data = path.read_bytes()
        ctypes.memmove(pointer, data, min(size, len(data)))

    def save_save_ram(self, path: Path) -> None:
        size = int(self.library.retro_get_memory_size(RETRO_MEMORY_SAVE_RAM))
        pointer = self.library.retro_get_memory_data(RETRO_MEMORY_SAVE_RAM)
        if not pointer or size <= 0:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(ctypes.string_at(pointer, size))
        temporary.replace(path)

    def close(self) -> None:
        if self._loaded:
            self.library.retro_unload_game()
            self._loaded = False
        if self._initialized:
            self.library.retro_deinit()
            self._initialized = False

    def _set_string_pointer(self, data: int, value: bytes) -> bool:
        pointer = ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))
        pointer[0] = value
        return True

    def _environment(self, command: int, data: int) -> bool:
        if command in {RETRO_ENVIRONMENT_GET_OVERSCAN, RETRO_ENVIRONMENT_GET_FASTFORWARDING}:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
            return True
        if command == RETRO_ENVIRONMENT_GET_CAN_DUPE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if command == RETRO_ENVIRONMENT_SHUTDOWN:
            self.shutdown_requested = True
            return True
        if command == RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
            return self._set_string_pointer(data, self._system_directory_bytes)
        if command == RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
            return self._set_string_pointer(data, self._save_directory_bytes)
        if command == RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY:
            return self._set_string_pointer(data, self._content_directory_bytes)
        if command == RETRO_ENVIRONMENT_GET_LIBRETRO_PATH:
            return self._set_string_pointer(data, self._core_path_bytes)
        if command == RETRO_ENVIRONMENT_GET_USERNAME:
            return self._set_string_pointer(data, self._username_bytes)
        if command == RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
            requested = ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0]
            if requested not in {
                RETRO_PIXEL_FORMAT_0RGB1555,
                RETRO_PIXEL_FORMAT_XRGB8888,
                RETRO_PIXEL_FORMAT_RGB565,
            }:
                return False
            self.pixel_format = requested
            return True
        if command == RETRO_ENVIRONMENT_SET_VARIABLES:
            variables = ctypes.cast(data, ctypes.POINTER(RetroVariable))
            index = 0
            while variables[index].key:
                key = _text(variables[index].key)
                specification = _text(variables[index].value)
                choices = specification.split(";", 1)[-1].strip().split("|")
                if key and choices:
                    self.variables.setdefault(key, choices[0].encode())
                index += 1
            return True
        if command == RETRO_ENVIRONMENT_GET_VARIABLE:
            variable = ctypes.cast(data, ctypes.POINTER(RetroVariable)).contents
            key = _text(variable.key)
            variable.value = self.variables.get(key)
            return variable.value is not None
        if command == RETRO_ENVIRONMENT_SET_VARIABLE:
            variable = ctypes.cast(data, ctypes.POINTER(RetroVariable)).contents
            key = _text(variable.key)
            if key and variable.value:
                self.variables[key] = bytes(variable.value)
                return True
            return False
        if command == RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
            return True
        if command == RETRO_ENVIRONMENT_GET_INPUT_BITMASKS:
            return True
        if command == RETRO_ENVIRONMENT_GET_LANGUAGE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_GET_TARGET_REFRESH_RATE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_float))[0] = 60.0
            return True
        if command == RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0] = 3
            return True
        if command == RETRO_ENVIRONMENT_GET_INPUT_MAX_USERS:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 1
            return True
        if command == RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_GET_MESSAGE_INTERFACE_VERSION:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_SET_MESSAGE:
            message = ctypes.cast(data, ctypes.POINTER(RetroMessage)).contents
            logging.info("Core message: %s", _text(message.msg))
            return True
        if command in {
            RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL,
            RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS,
            RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME,
            RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO,
            RETRO_ENVIRONMENT_SET_CONTROLLER_INFO,
            RETRO_ENVIRONMENT_SET_MEMORY_MAPS,
            RETRO_ENVIRONMENT_SET_GEOMETRY,
            RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY,
            RETRO_ENVIRONMENT_SET_MINIMUM_AUDIO_LATENCY,
            RETRO_ENVIRONMENT_SET_CONTENT_INFO_OVERRIDE,
        }:
            return True
        if command in {
            RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO,
            RETRO_ENVIRONMENT_GET_VFS_INTERFACE,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL,
            RETRO_ENVIRONMENT_GET_PREFERRED_HW_RENDER,
            RETRO_ENVIRONMENT_GET_DISK_CONTROL_INTERFACE_VERSION,
            RETRO_ENVIRONMENT_SET_DISK_CONTROL_EXT_INTERFACE,
            RETRO_ENVIRONMENT_SET_MESSAGE_EXT,
            RETRO_ENVIRONMENT_SET_AUDIO_BUFFER_STATUS_CALLBACK,
            RETRO_ENVIRONMENT_SET_FASTFORWARDING_OVERRIDE,
            RETRO_ENVIRONMENT_GET_GAME_INFO_EXT,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK,
            RETRO_ENVIRONMENT_GET_THROTTLE_STATE,
            RETRO_ENVIRONMENT_GET_SAVESTATE_CONTEXT,
            RETRO_ENVIRONMENT_GET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE_SUPPORT,
            RETRO_ENVIRONMENT_GET_JIT_CAPABLE,
            RETRO_ENVIRONMENT_GET_MICROPHONE_INTERFACE,
            RETRO_ENVIRONMENT_SET_NETPACKET_INTERFACE,
            RETRO_ENVIRONMENT_GET_DEVICE_POWER,
            RETRO_ENVIRONMENT_SET_NETPACKET_INTERFACE_V2,
        }:
            return False
        return False
