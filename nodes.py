import os
import json
import time
import wave
import array
import math

import torch
import torch.nn.functional as F

import cv2
import numpy as np
from PIL import Image, ImageEnhance


try:
    import folder_paths
except Exception:
    folder_paths = None

try:
    import torchaudio
    TORCHAUDIO_AVAILABLE = True
except Exception:
    torchaudio = None
    TORCHAUDIO_AVAILABLE = False

try:
    import av
    AV_AVAILABLE = True
except Exception:
    av = None
    AV_AVAILABLE = False


PACK_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PACK_DIR, "config.json")

DEFAULT_CONFIG = {
    "speakers_folder": "models/SPEAKERS"
}

AUDIO_EXTENSIONS = (".mp3", ".wav", ".mp4")
PLACEHOLDER = "[no speakers saved]"

_CATEGORY = "CoolB Nodes ⚡️"

def comfyui_root():
    if folder_paths is not None:
        base = getattr(folder_paths, "base_path", None)
        if base:
            return str(base)

        models = getattr(folder_paths, "models_dir", None)
        if models:
            return os.path.dirname(str(models))

    return os.path.dirname(os.path.dirname(PACK_DIR))


def text_io_base_dir():
    """Base directory for TextFileReader / TextFileWriter.

    Uses the ComfyUI output directory instead of the whole root, so neither
    node can reach custom_nodes/ (executable code), user/ (settings/keys),
    or models/. Falls back to <root>/output when folder_paths is absent.
    """
    if folder_paths is not None:
        try:
            out = folder_paths.get_output_directory()
            if out:
                return os.path.abspath(str(out))
        except Exception:
            pass
    return os.path.abspath(os.path.join(comfyui_root(), "output"))


def default_speakers_dir():
    if folder_paths is not None:
        models = getattr(folder_paths, "models_dir", None)
        if models:
            return os.path.abspath(os.path.join(str(models), "SPEAKERS"))

        base = getattr(folder_paths, "base_path", None)
        if base:
            return os.path.abspath(os.path.join(str(base), "models", "SPEAKERS"))

    return os.path.abspath(os.path.join(comfyui_root(), "models", "SPEAKERS"))


def load_config():
    cfg = dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        if isinstance(data, dict):
            cfg.update(data)
    except FileNotFoundError:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except Exception:
            pass
    except Exception:
        pass

    return cfg


def get_speakers_dir():
    cfg = load_config()

    raw = cfg.get("speakers_folder", DEFAULT_CONFIG["speakers_folder"])
    if raw is None:
        raw = DEFAULT_CONFIG["speakers_folder"]

    folder = str(raw).strip()
    if not folder:
        folder = DEFAULT_CONFIG["speakers_folder"]

    expanded = os.path.expandvars(os.path.expanduser(folder))

    normalized_default = os.path.normpath(DEFAULT_CONFIG["speakers_folder"].replace("\\", "/"))
    normalized_folder = os.path.normpath(expanded.replace("\\", "/"))

    if normalized_folder == normalized_default:
        path = default_speakers_dir()
    elif os.path.isabs(expanded):
        path = expanded
    else:
        normalized = expanded.replace("\\", "/")
        parts = [p for p in normalized.split("/") if p not in ("", ".")]

        if not parts:
            parts = ["models", "SPEAKERS"]

        path = os.path.join(comfyui_root(), *parts)

    path = os.path.abspath(path)

    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass

    return path


def sanitize_filename(name):
    name = str(name or "").strip()

    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "_")

    name = "".join(ch for ch in name if ord(ch) >= 32)
    name = name.strip(" .")

    if len(name) > 150:
        name = name[:150].rstrip(" .")

    if not name:
        name = "speaker"

    return name


def remove_file_if_exists(path):
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except Exception:
            pass


def remove_existing_audio(base_path, exclude_path=None):
    folder = os.path.dirname(base_path)
    base = os.path.basename(base_path).lower()

    if not folder or not base:
        return

    exclude_norm = None
    if exclude_path:
        exclude_norm = os.path.normcase(os.path.abspath(exclude_path))

    try:
        for file_name in os.listdir(folder):
            full_path = os.path.join(folder, file_name)
            name, ext = os.path.splitext(file_name)

            if name.lower() != base:
                continue

            if ext.lower() not in AUDIO_EXTENSIONS:
                continue

            if exclude_norm and os.path.normcase(os.path.abspath(full_path)) == exclude_norm:
                continue

            remove_file_if_exists(full_path)
    except Exception:
        pass


def cleanup_temp_audio(base_path):
    folder = os.path.dirname(base_path)
    base = os.path.basename(base_path).lower()
    temp_base = base + ".saving"

    try:
        for file_name in os.listdir(folder):
            name, ext = os.path.splitext(file_name)

            if name.lower() == temp_base and ext.lower() in AUDIO_EXTENSIONS:
                remove_file_if_exists(os.path.join(folder, file_name))
    except Exception:
        pass


def finalize_audio_file(temp_path, final_path):
    if not (os.path.isfile(temp_path) and os.path.getsize(temp_path) > 0):
        remove_file_if_exists(temp_path)
        return False

    try:
        os.replace(temp_path, final_path)
    except Exception:
        remove_file_if_exists(temp_path)
        return False

    base, _ = os.path.splitext(final_path)

    try:
        remove_existing_audio(base, exclude_path=final_path)
    except Exception:
        pass

    return True


def find_json_path(base_path):
    folder = os.path.dirname(base_path)
    base = os.path.basename(base_path)

    for ext in (".json", ".JSON"):
        candidate = os.path.join(folder, base + ext)
        if os.path.isfile(candidate):
            return candidate

    try:
        lower_base = base.lower()

        for file_name in os.listdir(folder):
            name, ext = os.path.splitext(file_name)

            if name.lower() == lower_base and ext.lower() == ".json":
                return os.path.join(folder, file_name)
    except Exception:
        pass

    return None


def find_audio_path(base_path, preferred_name=None):
    folder = os.path.dirname(base_path)
    base = os.path.basename(base_path)

    if preferred_name:
        preferred = os.path.basename(str(preferred_name))

        if preferred:
            candidate = os.path.join(folder, preferred)

            if os.path.isfile(candidate):
                return candidate

    for ext in AUDIO_EXTENSIONS:
        for candidate_ext in (ext, ext.upper()):
            candidate = os.path.join(folder, base + candidate_ext)

            if os.path.isfile(candidate):
                return candidate

    try:
        lower_base = base.lower()

        for file_name in os.listdir(folder):
            name, ext = os.path.splitext(file_name)

            if name.lower() == lower_base and ext.lower() in AUDIO_EXTENSIONS:
                return os.path.join(folder, file_name)
    except Exception:
        pass

    return None


def read_json_safe(path):
    if not path or not os.path.isfile(path):
        return None

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def read_ref_text(json_path):
    data = read_json_safe(json_path)

    if data is None:
        return ""

    if isinstance(data, dict):
        for key in ("ref_text", "text", "transcription"):
            if key in data:
                return str(data[key])

        return ""

    return str(data)


def list_speaker_names():
    folder = get_speakers_dir()
    names = []

    try:
        for file_name in os.listdir(folder):
            if not file_name.lower().endswith(".json"):
                continue

            base = os.path.splitext(file_name)[0]
            base_path = os.path.join(folder, base)
            json_path = os.path.join(folder, file_name)

            meta = read_json_safe(json_path)
            preferred_audio = None

            if isinstance(meta, dict):
                preferred_audio = meta.get("audio_file")

            if find_audio_path(base_path, preferred_audio):
                names.append(base)
    except Exception:
        pass

    if not names:
        return [PLACEHOLDER]

    return sorted(names, key=lambda x: x.lower())


def resolve_audio_path(value):
    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    candidates = []

    expanded = os.path.expandvars(os.path.expanduser(value))
    candidates.append(expanded)
    candidates.append(os.path.basename(expanded))

    if folder_paths is not None:
        try:
            input_dir = folder_paths.get_input_directory()
            candidates.append(os.path.join(input_dir, value))
            candidates.append(os.path.join(input_dir, os.path.basename(value)))
        except Exception:
            pass

        try:
            if hasattr(folder_paths, "get_annotated_filepath"):
                candidates.append(folder_paths.get_annotated_filepath(value))
        except Exception:
            pass

    seen = set()

    for candidate in candidates:
        if not candidate:
            continue

        candidate = os.path.abspath(os.path.expanduser(candidate))

        if candidate in seen:
            continue

        seen.add(candidate)

        if os.path.isfile(candidate):
            return candidate

    return None


def load_wav_fallback(path):
    with wave.open(path, "rb") as wf:
        channels = int(wf.getnchannels())
        sample_rate = int(wf.getframerate())
        sample_width = int(wf.getsampwidth())
        frames = wf.readframes(wf.getnframes())

    if channels <= 0:
        channels = 1

    if sample_rate <= 0:
        sample_rate = 44100

    out_channels = min(channels, 2)

    if sample_width <= 0:
        raise ValueError("Invalid WAV sample width.")

    # Trim to complete samples.
    usable_bytes = (len(frames) // sample_width) * sample_width

    if usable_bytes <= 0:
        return {
            "waveform": torch.zeros((1, out_channels, 1), dtype=torch.float32),
            "sample_rate": sample_rate,
        }

    frames = frames[:usable_bytes]

    if sample_width == 1:
        # 8-bit WAV is unsigned.
        pcm = torch.frombuffer(bytearray(frames), dtype=torch.uint8).to(torch.float32)
        pcm = (pcm - 128.0) / 128.0

    elif sample_width == 2:
        # 16-bit PCM.
        try:
            pcm = torch.frombuffer(bytearray(frames), dtype=torch.int16)
        except Exception:
            pcm = torch.tensor(array.array("h", frames).tolist(), dtype=torch.int16)

        pcm = pcm.to(torch.float32) / 32768.0

    elif sample_width == 3:
        # 24-bit PCM.
        if not NUMPY_AVAILABLE:
            raise ValueError("24-bit WAV loading requires numpy.")

        raw = np.frombuffer(frames, dtype=np.uint8)

        usable_raw = (raw.size // 3) * 3

        if usable_raw <= 0:
            return {
                "waveform": torch.zeros((1, out_channels, 1), dtype=torch.float32),
                "sample_rate": sample_rate,
            }

        raw = raw[:usable_raw].reshape(-1, 3).astype(np.int32)

        pcm_np = (
            raw[:, 0]
            | (raw[:, 1] << 8)
            | (raw[:, 2] << 16)
        )

        # Sign-extend 24-bit values to 32-bit signed range.
        pcm_np[pcm_np >= 0x800000] -= 0x1000000

        pcm = torch.from_numpy(pcm_np.astype(np.int32)).to(torch.float32) / 8388608.0

    elif sample_width == 4:
        # 32-bit integer PCM.
        # Note: floating-point WAVs are usually rejected by Python's wave module,
        # so this path is normally integer PCM.
        try:
            pcm = torch.frombuffer(bytearray(frames), dtype=torch.int32)
        except Exception:
            pcm = torch.tensor(array.array("i", frames).tolist(), dtype=torch.int32)

        pcm = pcm.to(torch.float32) / 2147483648.0

    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

    usable = (pcm.numel() // channels) * channels

    if usable <= 0:
        return {
            "waveform": torch.zeros((1, out_channels, 1), dtype=torch.float32),
            "sample_rate": sample_rate,
        }

    pcm = pcm[:usable].reshape(-1, channels).transpose(0, 1)

    # Keep mono/stereo. Downmix anything above stereo to the first two channels.
    if pcm.shape[0] > 2:
        pcm = pcm[:2, :]

    return {
        "waveform": pcm.unsqueeze(0).to(torch.float32),
        "sample_rate": sample_rate,
    }


def filesystem_safe_path(path):
    path = str(path)

    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(32768)
            result = ctypes.windll.kernel32.GetShortPathNameW(path, buffer, 32768)

            if 0 < result < 32768:
                return buffer.value
        except Exception:
            pass

    return path


def load_audio_file_av(path):
    if not (AV_AVAILABLE and NUMPY_AVAILABLE):
        raise RuntimeError("PyAV/numpy audio decoder is not available.")

    open_path = filesystem_safe_path(path)

    try:
        container = av.open(open_path)
    except Exception:
        container = av.open(path)

    try:
        audio_stream = None

        for stream in container.streams:
            stream_type = getattr(stream, "type", None)

            if stream_type is None:
                stream_codec_ctx = getattr(stream, "codec_context", None)
                if stream_codec_ctx is not None:
                    stream_type = getattr(stream_codec_ctx, "type", None)

            if stream_type == "audio":
                audio_stream = stream
                break

        if audio_stream is None:
            try:
                audio_stream = container.streams.get(audio=0)
            except Exception:
                audio_stream = None

        if audio_stream is None:
            raise RuntimeError("No audio stream found in file.")

        sample_rate = 44100
        stream_channels = 0

        try:
            sr = getattr(audio_stream, "rate", None)

            if not sr:
                sr = getattr(audio_stream, "sample_rate", None)

            if not sr:
                stream_codec_ctx = getattr(audio_stream, "codec_context", None)

                if stream_codec_ctx is not None:
                    sr = getattr(stream_codec_ctx, "sample_rate", None)

                    if not sr:
                        sr = getattr(stream_codec_ctx, "rate", None)

            if sr:
                sample_rate = int(sr)
        except Exception:
            sample_rate = 44100

        try:
            stream_channels = int(getattr(audio_stream, "channels", 0) or 0)

            if stream_channels <= 0:
                stream_codec_ctx = getattr(audio_stream, "codec_context", None)

                if stream_codec_ctx is not None:
                    stream_channels = int(getattr(stream_codec_ctx, "channels", 0) or 0)
        except Exception:
            stream_channels = 0

        target_channels = None
        target_layout = None

        if stream_channels >= 2:
            target_channels = 2
            target_layout = "stereo"
        elif stream_channels == 1:
            target_channels = 1
            target_layout = "mono"

        chunks = []
        use_forced_layout = True
        decode_errors = []

        for frame in container.decode(audio_stream):
            if frame is None:
                continue

            frame_rate = int(getattr(frame, "sample_rate", 0) or getattr(frame, "rate", 0) or 0)

            if frame_rate > 0:
                sample_rate = frame_rate

            frame_channels = int(getattr(frame, "channels", 0) or 0)

            if frame_channels <= 0:
                frame_layout = getattr(frame, "layout", None)

                if frame_layout is not None:
                    frame_channels = int(getattr(frame_layout, "nb_channels", 0) or 0)

            if frame_channels <= 0:
                frame_channels = stream_channels

            if target_channels is None:
                if frame_channels >= 2:
                    target_channels = 2
                    target_layout = "stereo"
                else:
                    target_channels = 1
                    target_layout = "mono"

            arr = None
            arr_is_forced_target_layout = False

            # Preferred path: convert directly to the target channel layout.
            if use_forced_layout and target_layout is not None:
                try:
                    arr = frame.to_ndarray(format="s16", layout=target_layout)
                    arr_is_forced_target_layout = True
                except TypeError:
                    use_forced_layout = False
                except Exception as e:
                    decode_errors.append(f"forced {target_layout}: {e}")
                    use_forced_layout = False

            # Fallback: int16 without forcing layout.
            if arr is None:
                try:
                    arr = frame.to_ndarray(format="s16")
                except Exception as e:
                    decode_errors.append(f"s16: {e}")

            # Last fallback: native frame array.
            if arr is None:
                try:
                    arr = frame.to_ndarray()
                except Exception as e:
                    decode_errors.append(f"default: {e}")
                    continue

            if arr is None or arr.size == 0:
                continue

            # Normalize dtype to float32.
            if arr.dtype == np.int16:
                arr = arr.astype(np.float32) / 32768.0
            elif arr.dtype == np.int32:
                arr = arr.astype(np.float32) / 2147483648.0
            elif arr.dtype == np.uint8:
                arr = (arr.astype(np.float32) - 128.0) / 128.0
            else:
                arr = arr.astype(np.float32)

            if arr.ndim == 0:
                arr = arr.reshape(1, 1)
            elif arr.ndim == 1:
                arr = arr.reshape(1, -1)
            elif arr.ndim > 2:
                arr = arr.reshape(arr.shape[0], -1)

            expected_channels = 0

            if arr_is_forced_target_layout:
                expected_channels = target_channels if target_channels else 1
            elif frame_channels > 0:
                expected_channels = frame_channels

            # Unpack interleaved packed audio if needed.
            if expected_channels > 1:
                if arr.shape[0] == 1 and arr.size % expected_channels == 0:
                    arr = arr.reshape(expected_channels, -1)
                elif arr.shape[0] != expected_channels and arr.size % expected_channels == 0:
                    arr = arr.reshape(expected_channels, -1)

            # Adjust channel count to the target channel count.
            if target_channels is not None and arr.shape[0] != target_channels:
                if arr.shape[0] == 0:
                    continue

                if target_channels == 1:
                    arr = arr.mean(axis=0, keepdims=True)
                elif arr.shape[0] == 1:
                    arr = np.repeat(arr, target_channels, axis=0)
                elif target_channels == 2:
                    if arr.shape[0] > 2:
                        arr = arr[:2, :]
                    else:
                        arr = np.repeat(arr.mean(axis=0, keepdims=True), target_channels, axis=0)
                else:
                    if arr.shape[0] > target_channels:
                        arr = arr[:target_channels, :]
                    else:
                        arr = np.repeat(arr.mean(axis=0, keepdims=True), target_channels, axis=0)

            if arr.size > 0:
                chunks.append(arr)

        if target_channels is None:
            target_channels = 1

        if not chunks:
            raise RuntimeError(
                "PyAV decoded no audio samples. Details: " + " | ".join(decode_errors[-3:])
            )

        audio = np.concatenate(chunks, axis=1)
        waveform = torch.from_numpy(audio).to(torch.float32).unsqueeze(0)
        waveform = torch.nan_to_num(waveform, nan=0.0, posinf=0.0, neginf=0.0)

        return {
            "waveform": waveform,
            "sample_rate": int(sample_rate),
        }

    finally:
        try:
            container.close()
        except Exception:
            pass


def load_audio_file(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Audio file not found: {path}")

    errors = []

    is_wav = path.lower().endswith(".wav")

    # For WAV files, prefer the native PCM WAV reader.
    # This avoids PyAV misinterpreting interleaved PCM data in some cases.
    if is_wav:
        try:
            return load_wav_fallback(filesystem_safe_path(path))
        except Exception as e:
            errors.append(f"native wav: {e}")

    # Then try PyAV.
    if AV_AVAILABLE and NUMPY_AVAILABLE:
        try:
            return load_audio_file_av(path)
        except Exception as e:
            errors.append(f"av: {e}")

    # Then try torchaudio.
    if TORCHAUDIO_AVAILABLE:
        torchaudio_error = None

        for load_path in (filesystem_safe_path(path), path):
            try:
                waveform, sample_rate = torchaudio.load(load_path)

                if waveform.dim() == 1:
                    waveform = waveform.unsqueeze(0)
                elif waveform.dim() == 3:
                    waveform = waveform[0]

                waveform = waveform.unsqueeze(0).to(torch.float32)

                if sample_rate <= 0:
                    sample_rate = 44100

                return {
                    "waveform": waveform,
                    "sample_rate": int(sample_rate),
                }
            except Exception as e:
                torchaudio_error = e

        if torchaudio_error is not None:
            errors.append(f"torchaudio: {torchaudio_error}")

    raise RuntimeError("Could not load audio. Details: " + " | ".join(errors[-3:]))


def audio_tensor_from_comfy_audio(ref_audio):
    if isinstance(ref_audio, str):
        path = resolve_audio_path(ref_audio)

        if path is None:
            raise ValueError("ref_audio string is not an existing audio file path.")

        ref_audio = load_audio_file(path)

    waveform = None
    sample_rate = 44100

    if isinstance(ref_audio, (tuple, list)):
        if len(ref_audio) == 0:
            raise ValueError("ref_audio tuple/list is empty.")

        first = ref_audio[0]

        if isinstance(first, dict):
            ref_audio = first
        elif isinstance(first, str):
            path = resolve_audio_path(first)

            if path is not None:
                loaded = load_audio_file(path)
                waveform = loaded.get("waveform")
                sample_rate = int(loaded.get("sample_rate", sample_rate))
            else:
                waveform = first
        else:
            waveform = first

        if len(ref_audio) > 1:
            try:
                sample_rate = int(ref_audio[1])
            except Exception:
                sample_rate = 44100

    if isinstance(ref_audio, dict):
        waveform = ref_audio.get("waveform", waveform)

        if waveform is None:
            waveform = ref_audio.get("audio", waveform)

        for key in ("sample_rate", "samplerate", "sr"):
            if key in ref_audio:
                try:
                    sample_rate = int(ref_audio[key])
                    break
                except Exception:
                    pass

    if isinstance(waveform, str):
        path = resolve_audio_path(waveform)

        if path is not None:
            loaded = load_audio_file(path)
            waveform = loaded.get("waveform")

            try:
                sample_rate = int(loaded.get("sample_rate", sample_rate))
            except Exception:
                pass

    if waveform is None:
        raise ValueError("ref_audio does not contain a usable waveform.")

    if not torch.is_tensor(waveform):
        waveform = torch.as_tensor(waveform)

    input_dtype = waveform.dtype
    waveform = waveform.detach().cpu()

    if input_dtype in (torch.int8, torch.int16, torch.int32, torch.int64, torch.uint8):
        waveform = waveform.to(torch.float32)

        if input_dtype == torch.int8:
            waveform = waveform / 128.0
        elif input_dtype == torch.int16:
            waveform = waveform / 32768.0
        elif input_dtype == torch.int32:
            waveform = waveform / 2147483648.0
        elif input_dtype == torch.uint8:
            waveform = (waveform - 128.0) / 128.0
    else:
        waveform = waveform.to(torch.float32)

    if waveform.numel() == 0:
        waveform = torch.zeros((1, 1), dtype=torch.float32)

    if waveform.dim() == 0:
        waveform = waveform.view(1, 1)
    elif waveform.dim() == 1:
        waveform = waveform.unsqueeze(0)
    elif waveform.dim() == 3:
        waveform = waveform[0]
    elif waveform.dim() > 3:
        while waveform.dim() > 2:
            waveform = waveform[0]

    if waveform.dim() != 2:
        waveform = waveform.reshape(1, -1)

    # If the tensor looks like samples x channels, convert it to channels x samples.
    if (
        waveform.dim() == 2
        and waveform.shape[1] <= 8
        and waveform.shape[0] > 16
        and waveform.shape[0] > waveform.shape[1]
    ):
        waveform = waveform.transpose(0, 1)

    waveform = torch.nan_to_num(waveform, nan=0.0, posinf=0.0, neginf=0.0)

    if sample_rate <= 0:
        sample_rate = 44100

    return waveform, int(sample_rate)


def save_wav_fallback(path, waveform, sample_rate):
    if waveform.dim() != 2:
        waveform = waveform.reshape(1, -1)

    channels = int(waveform.shape[0])

    pcm = waveform.transpose(0, 1).reshape(-1).clamp(-1.0, 1.0)
    pcm = (pcm * 32767.0).round().to(torch.int16).cpu()

    try:
        data = pcm.numpy().tobytes()
    except Exception:
        data = array.array("h", pcm.tolist()).tobytes()

    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(data)


def save_mp3_with_av(path, waveform, sample_rate):
    if not (AV_AVAILABLE and NUMPY_AVAILABLE):
        raise RuntimeError("PyAV/numpy MP3 encoder is not available.")

    if waveform.dim() != 2:
        waveform = waveform.reshape(1, -1)

    channels = int(waveform.shape[0])

    if channels > 2:
        waveform = waveform.mean(dim=0, keepdim=True)
        channels = 1

    layout = "mono" if channels == 1 else "stereo"
    sample_rate = int(sample_rate)

    pcm = waveform.transpose(0, 1).reshape(-1).clamp(-1.0, 1.0)
    pcm = (pcm * 32767.0).round().to(torch.int16).cpu()

    total_samples = pcm.numel() // max(1, channels)

    if total_samples == 0:
        pcm = torch.zeros((channels,), dtype=torch.int16)
        total_samples = 1

    pcm_planar = pcm.reshape(total_samples, channels).transpose(0, 1).contiguous().numpy()
    pcm_planar = np.ascontiguousarray(pcm_planar)

    container = av.open(path, mode="w")

    try:
        stream = None
        last_error = None

        for codec_name in ("libmp3lame", "mp3"):
            try:
                stream = container.add_stream(codec_name, rate=sample_rate)
                break
            except Exception as e:
                last_error = e

        if stream is None:
            raise RuntimeError(f"No MP3 codec available in PyAV: {last_error}")

        try:
            stream.codec_context.channels = channels
            stream.codec_context.layout = layout
        except Exception:
            pass

        frame_size = int(getattr(stream.codec_context, "frame_size", 0) or 1152)

        if frame_size <= 0:
            frame_size = 1152

        pts = 0

        for start in range(0, total_samples, frame_size):
            chunk = pcm_planar[:, start:start + frame_size]

            frame = av.AudioFrame.from_ndarray(chunk, format="s16p", layout=layout)
            frame.sample_rate = sample_rate
            frame.pts = pts

            for packet in stream.encode(frame):
                container.mux(packet)

            pts += int(chunk.shape[1])

        for packet in stream.encode(None):
            container.mux(packet)
    finally:
        container.close()


def _try_torchaudio_save(path, waveform, sample_rate, **kwargs):
    torchaudio.save(path, waveform, sample_rate, **kwargs)

    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return True

    remove_file_if_exists(path)
    return False


def normalize_audio_format(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if len(value) > 0 else "mp3"

    fmt = str(value or "mp3").strip().lower().lstrip(".")

    if fmt in ("wav", "wave"):
        return "wav"

    if fmt in ("mp3", "mpeg"):
        return "mp3"

    return "mp3"


def save_audio_file(ref_audio, target_audio_path, audio_format="mp3"):
    waveform, sample_rate = audio_tensor_from_comfy_audio(ref_audio)

    audio_format = normalize_audio_format(audio_format)

    base, _ = os.path.splitext(target_audio_path)
    cleanup_temp_audio(base)

    errors = []

    if audio_format == "mp3":
        final_mp3_path = base + ".mp3"
        temp_mp3 = base + ".saving.mp3"

        if TORCHAUDIO_AVAILABLE:
            for kwargs in ({"format": "mp3"}, {}):
                try:
                    if _try_torchaudio_save(temp_mp3, waveform, sample_rate, **kwargs):
                        if finalize_audio_file(temp_mp3, final_mp3_path):
                            return final_mp3_path, sample_rate
                except Exception as e:
                    errors.append(f"torchaudio mp3: {e}")

                remove_file_if_exists(temp_mp3)

        try:
            save_mp3_with_av(temp_mp3, waveform, sample_rate)

            if finalize_audio_file(temp_mp3, final_mp3_path):
                return final_mp3_path, sample_rate
        except Exception as e:
            errors.append(f"av mp3: {e}")

        remove_file_if_exists(temp_mp3)

        # Fallback to WAV if MP3 encoding fails.
        wav_path = base + ".wav"
        temp_wav = base + ".saving.wav"

        if TORCHAUDIO_AVAILABLE:
            try:
                if _try_torchaudio_save(temp_wav, waveform, sample_rate, format="wav"):
                    if finalize_audio_file(temp_wav, wav_path):
                        print(f"[Speaker Pack] MP3 encoding failed; saved WAV fallback: {wav_path}")
                        return wav_path, sample_rate
            except Exception as e:
                errors.append(f"torchaudio wav: {e}")

            remove_file_if_exists(temp_wav)

        try:
            save_wav_fallback(temp_wav, waveform, sample_rate)

            if finalize_audio_file(temp_wav, wav_path):
                print(f"[Speaker Pack] MP3 encoding failed; saved WAV fallback: {wav_path}")
                return wav_path, sample_rate
        except Exception as e:
            errors.append(f"wav fallback: {e}")

        remove_file_if_exists(temp_wav)

        raise RuntimeError(
            "Could not save speaker audio. Details: " + " | ".join(errors[-4:])
        )

    # WAV format
    final_wav_path = base + ".wav"
    temp_wav = base + ".saving.wav"

    if TORCHAUDIO_AVAILABLE:
        try:
            if _try_torchaudio_save(temp_wav, waveform, sample_rate, format="wav"):
                if finalize_audio_file(temp_wav, final_wav_path):
                    return final_wav_path, sample_rate
        except Exception as e:
            errors.append(f"torchaudio wav: {e}")

        remove_file_if_exists(temp_wav)

    try:
        save_wav_fallback(temp_wav, waveform, sample_rate)

        if finalize_audio_file(temp_wav, final_wav_path):
            return final_wav_path, sample_rate
    except Exception as e:
        errors.append(f"wav fallback: {e}")

    remove_file_if_exists(temp_wav)

    raise RuntimeError(
        "Could not save speaker audio. Details: " + " | ".join(errors[-4:])
    )


def empty_audio():
    return {
        "waveform": torch.zeros((1, 1, 1), dtype=torch.float32),
        "sample_rate": 44100,
    }


def _assert_within_base(base_dir, candidate):
    """Realpath both sides and prove containment with commonpath.

    commonpath is segment-aware (unlike startswith), and realpath resolves
    symlinks, so symlink-based escapes are caught as well.
    """
    base_real = os.path.realpath(base_dir)
    candidate_real = os.path.realpath(candidate)
    try:
        common = os.path.commonpath([base_real, candidate_real])
    except ValueError:
        # e.g. paths on different Windows drives
        raise ValueError("Path escapes the allowed base directory.")
    if common != base_real:
        raise ValueError("Path escapes the allowed base directory.")
    return candidate_real


def _safe_resolve_under_base(base_dir, file_path):
    """Resolve a widget-supplied path strictly inside base_dir.

    Rejects absolute paths, rooted paths, drive/UNC prefixes, null bytes and
    any '..' segment, then verifies containment against the resolved base.
    """
    raw = str(file_path or "").strip()
    if not raw:
        raise ValueError("File path is empty.")
    if "\x00" in raw:
        raise ValueError("File path contains invalid characters.")

    normalized = raw.replace("\\", "/")

    # Reject absolute / rooted paths before touching the filesystem.
    if os.path.isabs(raw) or normalized.startswith("/"):
        raise ValueError(f"Absolute paths are not allowed: '{file_path}'")
    # Windows drive-letter ("C:x", "C:\x") and UNC ("\\server\...", "\x") roots.
    if len(raw) >= 2 and raw[1] == ":":
        raise ValueError(f"Drive paths are not allowed: '{file_path}'")
    if raw.startswith("\\"):
        raise ValueError(f"Rooted paths are not allowed: '{file_path}'")

    # Reject any '..' segment, even one that would resolve back inside base.
    segments = [p for p in normalized.split("/") if p not in ("", ".")]
    if not segments:
        raise ValueError("File path is empty.")
    if any(seg == ".." for seg in segments):
        raise ValueError("Path traversal ('..') is not allowed.")

    return _assert_within_base(base_dir, os.path.join(base_dir, raw))


class SaveSpeaker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ref_audio": ("AUDIO",),
                "ref_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                }),
                "speaker_name": ("STRING", {
                    "multiline": False,
                    "default": "speaker",
                }),
                "audio_format": (["mp3", "wav"], {
                    "default": "mp3",
                }),
            }
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "save_speaker"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Saves a speaker's voice audio sample and corresponding speach transcription together. Default saving folder is models/SPEAKERS (can be changed in config.json)."

    def save_speaker(self, ref_audio, ref_text, speaker_name, audio_format="mp3"):
        speakers_dir = get_speakers_dir()

        safe_name = sanitize_filename(speaker_name)
        fmt = normalize_audio_format(audio_format)

        base_path = os.path.join(speakers_dir, safe_name)
        target_audio_path = base_path + "." + fmt
        json_path = base_path + ".json"

        actual_audio_path, sample_rate = save_audio_file(
            ref_audio,
            target_audio_path,
            fmt,
        )

        text = "" if ref_text is None else str(ref_text)

        payload = {
            "speaker_name": safe_name,
            "ref_text": text,
            "audio_file": os.path.basename(actual_audio_path),
            "audio_format": os.path.splitext(actual_audio_path)[1].lower().lstrip("."),
            "sample_rate": int(sample_rate),
            "created_utc": time.time(),
        }

        temp_json_path = json_path + ".tmp"

        try:
            with open(temp_json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            os.replace(temp_json_path, json_path)
        except Exception:
            remove_file_if_exists(temp_json_path)
            raise

        print(f"[Speaker Pack] Saved speaker '{safe_name}' to: {speakers_dir}")

        return {}


class LoadSpeaker:
    @classmethod
    def INPUT_TYPES(cls):
        speakers = list_speaker_names()

        return {
            "required": {
                "speaker": (speakers, {
                    "default": speakers[0] if speakers else PLACEHOLDER,
                }),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("ref_audio", "ref_text")
    FUNCTION = "load_speaker"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Loads a speaker's voice audio sample and corresponding speach transcription from the saving folder. Default saving folder is models/SPEAKERS (can be changed in config.json)."

    def load_speaker(self, speaker):
        if isinstance(speaker, (list, tuple)):
            speaker = speaker[0] if len(speaker) > 0 else ""

        speaker = str(speaker or "")

        if not speaker:
            return (empty_audio(), "")

        speakers_dir = get_speakers_dir()
        safe_name = sanitize_filename(speaker)

        base_path = os.path.join(speakers_dir, safe_name)
        json_path = find_json_path(base_path)

        meta = read_json_safe(json_path) if json_path else None
        preferred_audio = None

        if isinstance(meta, dict):
            preferred_audio = meta.get("audio_file")

        audio_path = find_audio_path(base_path, preferred_audio)

        if speaker == PLACEHOLDER and json_path is None and audio_path is None:
            return (empty_audio(), "")

        if audio_path is None:
            raise FileNotFoundError(
                f"No audio file found for speaker '{speaker}' in {speakers_dir}"
            )

        audio = load_audio_file(audio_path)
        text = read_ref_text(json_path) if json_path else ""

        return (audio, text)


import re
from server import PromptServer

class SetMuteBypassState:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "signal": ("*",),  # Wildcard type for passthrough
                "node_ids": ("STRING", {"default": "1, 2", "multiline": False}),
                "mode": (["Mute", "Bypass", "Active"], {"default": "Mute"}),
            }
        }

    FUNCTION = "doit"
    CATEGORY = f"{_CATEGORY}"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("signal",)
    OUTPUT_NODE = True
    DESCRIPTION = "Can be triggered by any passthrough signal to set Mute/Bypass/Active state to nodes, defined by their IDs (multiple IDs are devided by comma or space). This action doesn't affect the current run, only the next one."

    def doit(self, signal, node_ids, mode):
        ids = []
        if node_ids:
            parts = re.split(r'[\s,]+', node_ids.strip())
            for part in parts:
                if part.isdigit():
                    ids.append(int(part))
        
        # Send the data to the frontend via a custom event
        PromptServer.instance.send_sync(
            "custom-node-mute-bypass-state", 
            {"node_ids": ids, "mode": mode}
        )
        return (signal,)

class Textbox:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "forceInput": False,
                        "print_to_screen": True,
                    },
                ),
            },
            "optional": {
                "passthrough": (
                    "*",  # Accepts ANY input type
                    {
                        "default": "",
                        "forceInput": True,
                        # Added tooltip noting it can accept any input
                        "tooltip": "Can accept any input. The connected value will overwrite the widget and be converted to a string."
                    },
                )
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    OUTPUT_NODE = True
    FUNCTION = "textbox"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Just a simple textbox. Can accept any input and convert it to string which overwrites the widget."

    def textbox(self, text="", passthrough=None):
        # If passthrough is connected, it overwrites the text widget's value
        if passthrough is not None:
            # Convert the input of any type to string
            text = str(passthrough)
            # Return as a list: the frontend JS uses .join("") which requires an array
            return {"ui": {"text": [text]}, "result": (text,)}
        else:
            return (text,)

class StringListMatchIndex:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_string": (
                    "STRING", 
                    {
                        "default": "",
                        "tooltip": "The target text you want to search for in the list."
                    }
                ),
                "string_list": (
                    "STRING", 
                    {
                        "multiline": True, 
                        "default": "apple\nbanana\ncherry",
                        "tooltip": "The list of existing strings to look through. Format based on your chosen delimiter."
                    }
                ),
                "delimiter": (
                    ["newline", "comma"], 
                    {
                        "default": "newline",
                        "tooltip": "How the string list is split. Choose 'newline' if each item is on its own line."
                    }
                ),
                "match_mode": (
                    ["Equal", "Contains", "Starts with", "Ends with"], 
                    {
                        "default": "Equal",
                        "tooltip": "How the input string should match items in the list. 'Equal' requires an exact match."
                    }
                ),
                "case_sensitive": (
                    "BOOLEAN", 
                    {
                        "default": True,
                        "tooltip": "If True, 'Apple' and 'apple' will be treated as different strings."
                    }
                ),
            }
        }
    
    RETURN_TYPES = ("INT", "BOOLEAN")
    RETURN_NAMES = ("index", "matched")
    FUNCTION = "find_index"
    CATEGORY = f"{_CATEGORY}"
    
    DESCRIPTION = "Compares an input string against a list using custom matching rules. Returns a 1-based index if matched, or 0 if not found."

    def find_index(self, input_string, string_list, delimiter, match_mode, case_sensitive):
        # 1. Clean the input string
        target = input_string.strip()
        if not case_sensitive:
            target = target.lower()

        # 2. Split and clean the list items
        lines = string_list.split('\n') if delimiter == "newline" else string_list.split(',')
        cleaned_list = [item.strip() for item in lines if item.strip()]
        
        # 3. Iterate and evaluate based on the selected mode
        for i, item in enumerate(cleaned_list):
            compare_item = item if case_sensitive else item.lower()
            
            is_match = False
            if match_mode == "Equal":
                is_match = (target == compare_item)
            elif match_mode == "Contains":
                # Checks if your input string contains the list item
                is_match = (compare_item in target)
            elif match_mode == "Starts with":
                # Checks if your input string starts with the list item
                is_match = target.startswith(compare_item)
            elif match_mode == "Ends with":
                # Checks if your input string ends with the list item
                is_match = target.endswith(compare_item)
                
            if is_match:
                return (i + 1, True) # Return 1-based index immediately on first match
                
        # 4. Fallback if no items match
        return (0, False) 

class TextFileReader:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {
                    "default": "configs/config1.txt",
                    "multiline": False,
                    "tooltip": "Path relative to the ComfyUI output folder."
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text_content",)
    FUNCTION = "read_file"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Loads a text file from a path inside the ComfyUI output folder."

    def read_file(self, file_path):
        # Confine all reads to the ComfyUI output directory.
        base_dir = text_io_base_dir()
        try:
            full_path = _safe_resolve_under_base(base_dir, file_path)
        except ValueError as e:
            return (f"Error: {e}",)

        if not os.path.isfile(full_path):
            return (f"Error: File not found at path '{file_path}'",)

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return (content,)
        except Exception as e:
            return (f"Error reading file: {str(e)}",)


class TextFileWriter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {
                    "default": "configs/config1.txt",
                    "multiline": False,
                    "tooltip": "The path where the text file will be saved, relative to the ComfyUI output folder."
                }),
                "mode": (["overwrite", "append", "increment"], {
                    "default": "overwrite",
                    "tooltip": "overwrite: Replaces the file content.\nappend: Adds text to the end.\nincrement: Creates a new file like config1_00002.txt if 00001 already exists."
                }),
                "text_input": ("STRING", {
                    "forceInput": True,
                    "tooltip": "The text string you want to write into the file."
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_text",)
    FUNCTION = "save_file"
    CATEGORY = f"{_CATEGORY}"
    OUTPUT_NODE = True
    DESCRIPTION = "Saves a string into a text file inside the ComfyUI output folder."

    def save_file(self, file_path, mode, text_input):
        # 1. Confine all writes to the ComfyUI output directory.
        base_dir = text_io_base_dir()
        try:
            full_path = _safe_resolve_under_base(base_dir, file_path)
        except ValueError as e:
            return (f"Error: {e}",)

        write_mode = "w"
        content_to_write = str(text_input)

        # 2. Handle modes
        if mode == "append":
            write_mode = "a"
            # If appending and the file already exists and is not empty, add a newline separator
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                content_to_write = "\n" + content_to_write
        elif mode == "increment":
            if os.path.exists(full_path):
                dir_name = os.path.dirname(full_path)
                file_name = os.path.basename(full_path)
                name, ext = os.path.splitext(file_name)
                counter = 1
                while True:
                    new_file_name = f"{name}_{counter:05d}{ext}"
                    new_full_path = os.path.join(dir_name, new_file_name)
                    if not os.path.exists(new_full_path):
                        full_path = new_full_path
                        break
                    counter += 1
                # Defense in depth: re-validate the incremented target.
                try:
                    full_path = _assert_within_base(base_dir, full_path)
                except ValueError as e:
                    return (f"Error: {e}",)

        # 3. Create directories only inside the validated output directory.
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
        except Exception as e:
            print(f"[Save Text File Error] Failed to create directories: {str(e)}")
            return (f"Error: {str(e)}",)

        # 4. Write file
        try:
            with open(full_path, write_mode, encoding="utf-8") as f:
                f.write(content_to_write)
        except Exception as e:
            print(f"[Save Text File Error] Failed to write file: {str(e)}")
            return (f"Error: {str(e)}",)

        return (content_to_write,)


class StringSelector:
    """
    Selects a specific string from a delimited list.
    Based on the Impact Pack String Selector, but with a choice of delimiters.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True, 
                    "default": ""
                }),
                "delimiter": (["newline", "comma", "space"], {
                    "default": "newline"
                }),
                "index": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "max": 10000, 
                    "step": 1,
                    "display": "number"
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "select_string"
    CATEGORY = f"{_CATEGORY}"
    OUTPUT_NODE = False
    DESCRIPTION = "Splits a string into substrings based on chosen delimiter and returns the substring, selected by index."

    def select_string(self, text, delimiter, index):
        # Map the dropdown choice to the actual character
        if delimiter == "newline":
            sep = "\n"
        elif delimiter == "comma":
            sep = ","
        elif delimiter == "space":
            sep = " "
        else:
            sep = "\n"
            
        # Split the text
        parts = text.split(sep)
        
        # Quality of life: strip whitespace if using comma or space 
        # so "a, b, c" becomes ["a", "b", "c"] instead of ["a", " b", " c"]
        if delimiter in ["comma", "space"]:
            parts = [p.strip() for p in parts]
            
        # Filter out completely empty strings (happens if there are double commas/spaces)
        parts = [p for p in parts if p != ""]
        
        if not parts:
            return ("",)
            
        # Use modulo to loop the index if it's out of bounds or negative
        safe_index = index % len(parts)
        
        return (parts[safe_index],)

class SetGroupMuteBypassState:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "signal": ("*",), # Wildcard type for passthrough
                "group_name_contains": ("STRING", {"default": "Group", "multiline": False}),
                "mode": (["Mute", "Bypass", "Active"], {"default": "Mute"}),
            }
        }

    FUNCTION = "doitgr"
    CATEGORY = f"{_CATEGORY}"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("signal",)
    OUTPUT_NODE = True
    DESCRIPTION = "Can be triggered by any passthrough signal to set Mute/Bypass/Active state to a group of nodes, defined by its name. This action doesn't affect the current run, only the next one."

    def doitgr(self, signal, group_name_contains, mode):
        # Send the data to the frontend via a custom event
        PromptServer.instance.send_sync(
            "custom-group-mute-bypass-state", 
            {"search_str": group_name_contains, "mode": mode}
        )
        return (signal,)

class AnyToPrimitive:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # "*" allows the socket to accept any connection type in ComfyUI
                "value": ("*",), 
                "output_type": (["STRING", "FLOAT", "INT", "BOOLEAN"], {"default": "STRING"}),
            }
        }

    # Returning dynamic wildcard types requires specifying returning names/types
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("converted_value",)
    FUNCTION = "convert"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Converts any data type to String, Int, Float or Boolean."

    def convert(self, value, output_type):
        # 1. Convert to STRING
        if output_type == "STRING":
            return (str(value),)

        # 2. Convert to FLOAT
        elif output_type == "FLOAT":
            try:
                return (float(value),)
            except (ValueError, TypeError):
                # Fallback if it's a non-numeric string or object
                return (0.0,)

        # 3. Convert to INT
        elif output_type == "INT":
            try:
                # Direct float conversion first handles strings like "3.14" cleanly
                return (int(float(value)),)
            except (ValueError, TypeError):
                return (0,)

        # 4. Convert to BOOLEAN
        elif output_type == "BOOLEAN":
            if isinstance(value, str):
                # Common string representations for truthiness
                return (value.lower().strip() in ("true", "1", "yes", "on"),)
            return (bool(value),)

        return (value,)


# New nodes in V1.1.0

class AudioProcessor:
    """
    Processes a single audio track with precise control over volume, fades, and silence extensions.
    """
    
    DESCRIPTION = "Processes an audio track with volume, fades, and silence padding. Can be used alongside native Merge Audio nodes to combine multiple tracks with precise control. Uses PyAV natively for resampling."

    @classmethod
    def INPUT_TYPES(cls):
        sample_rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000]
        fade_curves = ["linear", "ease-inward", "ease-outward", "ease-in-out"]
        
        return {
            "required": {
                "audio": ("AUDIO", {"tooltip": "Input audio track to process."}),
                "sample_rate": (sample_rates, {
                    "default": 44100, 
                    "tooltip": "Target sample rate for the output audio."
                }),
                "volume": ("FLOAT", {
                    "default": 0.0, "min": -60.0, "max": 24.0, "step": 0.1,
                    "tooltip": "Volume adjustment in dB."
                }),
                "fade_in_time": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 60.0, "step": 0.001,
                    "tooltip": "Duration of the fade-in effect in seconds."
                }),
                "fade_out_time": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 60.0, "step": 0.001,
                    "tooltip": "Duration of the fade-out effect in seconds."
                }),
                "fade_curve": (fade_curves, {
                    "default": "linear",
                    "tooltip": "The mathematical curve used for the fade transitions."
                }),
                "extend_start": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.001,
                    "tooltip": "Amount of silence to add before the audio starts, in seconds."
                }),
                "extend_end": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.001,
                    "tooltip": "Amount of silence to add after the audio ends, in seconds."
                })
            }
        }

    RETURN_TYPES = ("AUDIO", "FLOAT")
    RETURN_NAMES = ("audio", "duration")
    FUNCTION = "audio_process"
    CATEGORY = f"{_CATEGORY}"

    def resample_wav(self, wav, orig_sr, target_sr):
        if orig_sr == target_sr:
            return wav
            
        batch_size, channels, samples = wav.shape
        resampled = []
        
        for b in range(batch_size):
            np_arr = wav[b].cpu().numpy()
            if channels == 1:
                layout = 'mono'
            elif channels == 2:
                layout = 'stereo'
            else:
                layout = f'{channels}c'
                
            try:
                if HAS_PYAV:
                    frame = av.AudioFrame.from_ndarray(np_arr, format='fltp', layout=layout)
                    frame.sample_rate = orig_sr
                    resampler = av.AudioResampler(format='fltp', layout=layout, rate=target_sr)
                    
                    frames = resampler.resample(frame)
                    frames.extend(resampler.resample(None))
                    
                    if frames:
                        arr = np.concatenate([f.to_ndarray() for f in frames], axis=1)
                        resampled.append(torch.from_numpy(arr.copy()).to(wav.device))
                        continue
            except Exception:
                pass
                
            # Fallback linear resample if PyAV fails
            ratio = target_sr / orig_sr
            new_samples = max(1, int(samples * ratio))
            resampled_wav = F.interpolate(wav[b:b+1], size=new_samples, mode='linear', align_corners=False)[0]
            resampled.append(resampled_wav)
            
        return torch.stack(resampled, dim=0)

    def get_envelope(self, length, curve, dtype, device):
        if length <= 0:
            return torch.empty(0, dtype=dtype, device=device)
            
        t = torch.linspace(0, 1, length, dtype=dtype, device=device)
        if curve == "linear":
            env = t
        elif curve == "ease-inward":
            env = t ** 2
        elif curve == "ease-outward":
            env = 1 - (1 - t) ** 2
        elif curve == "ease-in-out":
            env = 0.5 - 0.5 * torch.cos(t * math.pi)
        else:
            env = t
        return env

    def audio_process(self, audio, sample_rate, volume, fade_in_time, fade_out_time, fade_curve, extend_start, extend_end):
        if audio is None:
            raise ValueError("Audio input is None")
            
        wav = audio["waveform"]
        orig_sr = audio["sample_rate"]
        
        # 1. Resample
        wav = self.resample_wav(wav, orig_sr, sample_rate)
        b, c, t_len = wav.shape
        
        # 2. Apply Volume
        linear_gain = 10 ** (volume / 20.0)
        wav = wav * linear_gain
        
        # 3. Apply Fades (on the original audio boundaries)
        fade_in_samp = int(fade_in_time * sample_rate)
        fade_out_samp = int(fade_out_time * sample_rate)
        
        # Clamp fades to prevent overlap issues if combined fades exceed audio length
        if fade_in_samp + fade_out_samp > t_len and t_len > 0:
            ratio = fade_in_time / (fade_in_time + fade_out_time) if (fade_in_time + fade_out_time) > 0 else 0.5
            fade_in_samp = int(t_len * ratio)
            fade_out_samp = t_len - fade_in_samp

        if fade_in_samp > 0 and t_len > 0:
            env_in = self.get_envelope(fade_in_samp, fade_curve, wav.dtype, wav.device)
            wav[:, :, :fade_in_samp] *= env_in.view(1, 1, -1)
            
        if fade_out_samp > 0 and t_len > 0:
            env_out = self.get_envelope(fade_out_samp, fade_curve, wav.dtype, wav.device)
            # fade out goes from 1 to 0, so we reverse the envelope
            env_out = env_out.flip(0)
            wav[:, :, -fade_out_samp:] *= env_out.view(1, 1, -1)
            
        # 4. Extends (Add silence AFTER fades are applied)
        extend_start_samp = int(extend_start * sample_rate)
        extend_end_samp = int(extend_end * sample_rate)
        
        if extend_start_samp > 0:
            silence_start = torch.zeros((b, c, extend_start_samp), dtype=wav.dtype, device=wav.device)
            wav = torch.cat([silence_start, wav], dim=2)
            
        if extend_end_samp > 0:
            silence_end = torch.zeros((b, c, extend_end_samp), dtype=wav.dtype, device=wav.device)
            wav = torch.cat([wav, silence_end], dim=2)
            
        final_duration = wav.shape[2] / sample_rate
        
        return ({"waveform": wav, "sample_rate": sample_rate}, final_duration)


class AudioRollTrim:
    DESCRIPTION = "Rolls audio by a time offset first, then trims from start/end. No resampling is performed; this is a cyclic sample shift and sample-accurate trim."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": (
                    "AUDIO",
                    {
                        "tooltip": (
                            "Audio input. Expects an AUDIO dict with 'waveform' and 'sample_rate'."
                        )
                    },
                ),
                "offset": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": -3600.0,
                        "max": 3600.0,
                        "step": 0.001,
                        "tooltip": (
                            "Roll amount in seconds. Positive = wave samples shift forward with modulo wrapping; negative = backward."
                        ),
                    },
                ),
                "trim_start": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 3600.0,
                        "step": 0.001,
                        "tooltip": "Seconds to remove from the start (after rolling).",
                    },
                ),
                "trim_end": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 3600.0,
                        "step": 0.001,
                        "tooltip": "Seconds to remove from the end (after rolling).",
                    },
                ),
            }
        }

    RETURN_TYPES = ("AUDIO", "AUDIO", "AUDIO")
    RETURN_NAMES = ("trimmed_audio", "start_audio", "end_audio")
    FUNCTION = "roll_and_trim_audio"
    CATEGORY = f"{_CATEGORY}"

    def roll_and_trim_audio(self, audio, offset, trim_start, trim_end):
        if audio is None:
            raise ValueError("Audio input is None")

        # Match AudioProcessor's I/O contract: read directly from the AUDIO dict.
        waveform = audio["waveform"]
        sample_rate = audio["sample_rate"]

        if not torch.is_tensor(waveform):
            waveform = torch.as_tensor(waveform)

        # Ensure at least 1D.
        if waveform.dim() == 0:
            waveform = waveform.unsqueeze(0)

        total_samples = waveform.shape[-1]

        # Empty audio handling.
        if total_samples == 0:
            empty_waveform = self._empty_waveform(waveform)

            rolled_audio = {"waveform": waveform, "sample_rate": sample_rate}
            empty_audio = {"waveform": empty_waveform, "sample_rate": sample_rate}

            return (rolled_audio, empty_audio, empty_audio)

        # Safety fallback only if the input contains no usable sample rate.
        if sample_rate <= 0:
            sample_rate = 44100

        offset_seconds = float(offset)
        trim_start_seconds = max(0.0, float(trim_start))
        trim_end_seconds = max(0.0, float(trim_end))

        # Convert seconds to samples.
        offset_samples = int(round(offset_seconds * sample_rate))
        start_samples = int(round(trim_start_seconds * sample_rate))
        end_samples = int(round(trim_end_seconds * sample_rate))

        # Roll first.
        k = offset_samples % total_samples

        if k == 0:
            rolled_waveform = waveform
        else:
            # Positive offset moves forward in time:
            # -N samples -> [N+1, N+2, ..., N]
            rolled_waveform = torch.roll(waveform, shifts=k, dims=-1)

        # If trimming is impossible, return rolled audio and empty start/end audio.
        if start_samples + end_samples >= total_samples:
            original_duration = total_samples / sample_rate

            print(
                f"[AudioRollTrim] Warning: Cannot trim {trim_start_seconds:.3f}s from start "
                f"and {trim_end_seconds:.3f}s from end."
            )
            print(
                f"[AudioRollTrim] Audio only has {total_samples} samples "
                f"(~{original_duration:.3f}s at {sample_rate} Hz)."
            )
            print(
                "[AudioRollTrim] Returning rolled audio with empty start/end audio."
            )

            empty_waveform = self._empty_waveform(waveform)

            rolled_audio = {"waveform": rolled_waveform, "sample_rate": sample_rate}
            empty_audio = {"waveform": empty_waveform, "sample_rate": sample_rate}

            return (rolled_audio, empty_audio, empty_audio)

        # Trim.
        start_idx = start_samples
        end_idx = total_samples - end_samples

        trimmed_waveform = rolled_waveform[..., start_idx:end_idx]

        if start_samples > 0:
            start_waveform = rolled_waveform[..., :start_samples]
        else:
            start_waveform = self._empty_waveform(waveform)

        if end_samples > 0:
            end_waveform = rolled_waveform[..., end_idx:]
        else:
            end_waveform = self._empty_waveform(waveform)

        trimmed_audio = {"waveform": trimmed_waveform, "sample_rate": sample_rate}
        start_audio = {"waveform": start_waveform, "sample_rate": sample_rate}
        end_audio = {"waveform": end_waveform, "sample_rate": sample_rate}

        return (trimmed_audio, start_audio, end_audio)

    def _empty_waveform(self, waveform):
        """
        Create an empty waveform with the same leading dimensions, dtype, and device.
        Assumes the sample dimension is the last dimension.
        """
        if waveform.dim() == 0:
            return torch.empty(0, dtype=waveform.dtype, device=waveform.device)

        return torch.empty(
            *waveform.shape[:-1],
            0,
            dtype=waveform.dtype,
            device=waveform.device,
        )


class VideoRollTrim:
    DESCRIPTION = "Rolls the clip by an integer offset first, then trims frames from the start/end. Returns trimmed video, removed start frames, and removed end frames. For example, inputing images={A B C D E F G} with offset=3, trim_start=1 and trim_end=2 will return trimmed_video={F G A B}, start_frames={E} and end_frames={C D}"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": (
                    "IMAGE",
                    {"tooltip": "Input video frames"},
                ),
                "offset": (
                    "INT",
                    {
                        "default": 0,
                        "min": -9999,
                        "max": 9999,
                        "step": 1,
                        "tooltip": "Roll amount. Positive = frame indices shift forward with modulo wrapping; negative = backward.",
                    },
                ),
                "trim_start": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 1000,
                        "step": 1,
                        "tooltip": "Number of frames to remove from the start (after rolling).",
                    },
                ),
                "trim_end": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 1000,
                        "step": 1,
                        "tooltip": "Number of frames to remove from the end (after rolling).",
                    },
                ),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("trimmed_video", "start_frames", "end_frames")
    FUNCTION = "roll_and_trim"
    CATEGORY = f"{_CATEGORY}"

    def roll_and_trim(self, images, offset, trim_start, trim_end):
        batch_size = images.shape[0]

        # Handle empty batch safely
        if batch_size == 0:
            empty_tensor = torch.empty(
                0, *images.shape[1:], dtype=images.dtype, device=images.device
            )
            return (images, empty_tensor, empty_tensor)

        # Normalize offset
        offset = int(offset)
        trim_start = int(trim_start)
        trim_end = int(trim_end)

        k = offset % batch_size

        # Roll first
        if k == 0:
            rolled_images = images
        else:
            # Same behavior as UnrollFrames: -1 -> [2, 3, ..., 1]
            rolled_images = torch.roll(images, shifts=k, dims=0)

        # Check if trimming is possible
        if trim_start + trim_end >= batch_size:
            print(
                f"[VideoRollTrim] Warning: Cannot trim {trim_start} frames from start "
                f"and {trim_end} frames from end as batch only has {batch_size} frames."
            )
            print(
                "[VideoRollTrim] Returning rolled batch with empty start/end frames."
            )

            empty_tensor = torch.empty(
                0, *images.shape[1:], dtype=images.dtype, device=images.device
            )
            return (rolled_images, empty_tensor, empty_tensor)

        # Calculate start/end indices for trimmed batch
        start_idx = trim_start
        end_idx = batch_size - trim_end

        # Extract trimmed frames
        trimmed_images = rolled_images[start_idx:end_idx]

        # Extract start frames
        if trim_start > 0:
            start_frames = rolled_images[:trim_start]
        else:
            start_frames = torch.empty(
                0, *images.shape[1:], dtype=images.dtype, device=images.device
            )

        # Extract end frames
        if trim_end > 0:
            end_frames = rolled_images[end_idx:]
        else:
            end_frames = torch.empty(
                0, *images.shape[1:], dtype=images.dtype, device=images.device
            )
        
        return (trimmed_images, start_frames, end_frames)


class AudioInfo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
            },
        }

    RETURN_TYPES = ("FLOAT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("duration_sec", "sample_rate", "total_samples", "channels", "info")
    FUNCTION = "audio_info"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "A simple audio info node."

    def audio_info(self, audio):
        waveform = audio["waveform"]          # shape: (batch, channels, samples)
        sample_rate = int(audio["sample_rate"])

        channels = int(waveform.shape[1])
        total_samples = int(waveform.shape[2])
        duration_sec = total_samples / sample_rate

        # Format as MM:SS.xx (2 decimal places)
        minutes = int(duration_sec // 60)
        seconds = duration_sec % 60
        duration_str = f"{minutes:02d}:{seconds:05.2f}"

        info = (
            f"Duration: {duration_str} ({duration_sec:.5f} s)\n"
            f"Sample rate: {sample_rate} Hz\n"
            f"Samples: {total_samples}\n"
            f"Channels: {channels}"
        )

        return (float(duration_sec), sample_rate, total_samples, channels, info)


def srgb_to_linear(x):
    x = x.clamp(0.0, 1.0)
    return torch.where(
        x <= 0.04045,
        x / 12.92,
        ((x.clamp(min=0.04045) + 0.055) / 1.055) ** 2.4
    )


def linear_to_srgb(x):
    x = x.clamp(0.0, 1.0)
    return torch.where(
        x <= 0.0031308,
        x * 12.92,
        1.055 * x.clamp(min=0.0031308) ** (1.0 / 2.4) - 0.055
    )



class NearestResolution:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "megapixels": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.01,
                        "max": 100.0,
                        "step": 0.01,
                        "round": 0.01,
                    },
                ),
                "divisible_by": (
                    "INT",
                    {
                        "default": 32,
                        "min": 1,
                        "max": 1024,
                    },
                ),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "resolve"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Calculates the nearest resolution for an input image/video that matches chosen megapixels and divisible_by, while keeping the aspect ratio closest to the original. Connect output to any resize node."

    def resolve_megapixel_size(self, w, h, megapixels):
        w = max(1.0, float(w))
        h = max(1.0, float(h))

        aspect = w / h if h else 1.0
        area = max(0.000001, float(megapixels)) * 1_000_000.0

        nw = max(1, int(round(math.sqrt(area * aspect))))
        nh = max(1, int(round(area / max(1, nw))))

        return nw, nh

    def snap(self, v, div):
        v = max(1, int(v))
        div = max(1, int(round(div)))

        if div <= 1:
            return v

        return max(div, (v // div) * div)

    def resolve(self, image, megapixels, divisible_by):
        # Image batches have shape: B, H, W, C
        # Only the first frame resolution is used.
        orig_h = max(1, int(image.shape[1]))
        orig_w = max(1, int(image.shape[2]))

        w, h = self.resolve_megapixel_size(
            orig_w,
            orig_h,
            megapixels
        )

        div = max(1, int(round(divisible_by)))

        w = self.snap(w, div)
        h = self.snap(h, div)

        return (int(w), int(h))


class ColorCorrect:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "temperature": ("FLOAT", {"default": 0, "min": -100, "max": 100, "step": 1, "tooltip": "Color temperature. Positive values warm the image, negative values cool it."}),
                "hue": ("FLOAT", {"default": 0, "min": -90, "max": 90, "step": 1, "tooltip": "Shifts the colors around the hue wheel, in degrees."}),
                "brightness": ("FLOAT", {"default": 0, "min": -100, "max": 100, "step": 1, "tooltip": "Adjusts overall brightness. -100 becomes black."}),
                "contrast": ("FLOAT", {"default": 0, "min": -100, "max": 100, "step": 1, "tooltip": "Adjusts contrast. -100 reduces the image to flat gray."}),
                "saturation": ("FLOAT", {"default": 0, "min": -100, "max": 100, "step": 1, "tooltip": "Adjusts color intensity. -100 becomes grayscale."}),
                "gamma": ("FLOAT", {"default": 1, "min": 0.2, "max": 2.2, "step": 0.1, "tooltip": "Gamma correction. Values below 1 brighten midtones, values above 1 darken them."}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "color_correct"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Tweaks the color of the image/video. Processing speed highly depends on the number of paremeter values, chosen to be tweaked at the same time (e.i. changing one parameter and leaving others at default values is processed much faster)."

    def color_correct(self, image, temperature, hue, brightness, contrast, saturation, gamma):
        # 1) no-op fast path
        if (temperature == 0 and hue == 0 and brightness == 0 and
                contrast == 0 and saturation == 0 and gamma == 1.0):
            return (image,)

        device, dtype = image.device, image.dtype

        # 2) single H2D/D2H transfer for the whole batch
        arr = image.detach().cpu().numpy().astype(np.float32, copy=True)  # [B,H,W,C] in [0,1]

        # 3) brightness (was PIL) — vectorized
        if brightness != 0:
            arr *= (1.0 + brightness / 100.0)
            np.clip(arr, 0.0, 1.0, out=arr)

        # 4) contrast (was PIL) — mean-based, vectorized
        if contrast != 0:
            cf = 1.0 + contrast / 100.0
            # PIL's ImageEnhance.Contrast blends toward the mean of the *L* channel.
            # Per-image scalar luma mean, broadcast to all 3 channels:
            lum = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
            mean_l = lum.mean(axis=(1, 2), keepdims=True)[..., None]   # [B,1,1,1]
            arr = (arr - mean_l) * cf + mean_l
            np.clip(arr, 0.0, 1.0, out=arr)

        # 5) temperature — vectorized
        if temperature != 0:
            t = temperature / 100.0
            if t > 0:
                arr[..., 0] *= (1.0 + t)
                arr[..., 1] *= (1.0 + t * 0.4)
            else:
                arr[..., 2] *= (1.0 - t)
            np.clip(arr, 0.0, 1.0, out=arr)

        # 6) gamma — vectorized
        if gamma != 1.0:
            np.power(arr, gamma, out=arr)
            np.clip(arr, 0.0, 1.0, out=arr)

        # 7) color-space ops — still per-image (cv2 is not batched),
        #    but only run the branches that actually need it.
        if saturation != 0 or hue != 0:
            sat_f = 1.0 + saturation / 100.0
            need_sat = saturation != 0
            need_hue = hue != 0
            for b in range(arr.shape[0]):
                img = arr[b]
                if need_sat:
                    hls = cv2.cvtColor(img, cv2.COLOR_RGB2HLS)         # [0,1] float — correct range
                    hls[:, :, 2] = np.clip(sat_f * hls[:, :, 2], 0.0, 1.0)
                    img = cv2.cvtColor(hls, cv2.COLOR_HLS2RGB)
                if need_hue:
                    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)         # H in [0,360) for float32
                    hsv[:, :, 0] = (hsv[:, :, 0] + hue) % 360.0
                    img = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
                arr[b] = img

        np.clip(arr, 0.0, 1.0, out=arr)

        # 8) single transfer back, dtype/device preserved, no float64 detour
        result = torch.from_numpy(arr).to(device=device, dtype=dtype)
        return (result,)
