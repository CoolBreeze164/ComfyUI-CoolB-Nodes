import os
import json
import time
import wave
import array

import torch

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

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    np = None
    NUMPY_AVAILABLE = False


PACK_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PACK_DIR, "config.json")

DEFAULT_CONFIG = {
    "speakers_folder": "models/SPEAKERS"
}

AUDIO_EXTENSIONS = (".mp3", ".wav", ".mp4")
PLACEHOLDER = "[no speakers saved]"

_CATEGORY = "CoolB вљЎпёЏ"

def comfyui_root():
    if folder_paths is not None:
        base = getattr(folder_paths, "base_path", None)
        if base:
            return str(base)

        models = getattr(folder_paths, "models_dir", None)
        if models:
            return os.path.dirname(str(models))

    return os.path.dirname(os.path.dirname(PACK_DIR))


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
                    "default": "output/configs/config1.txt", 
                    "multiline": False
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text_content",)
    FUNCTION = "read_file"
    CATEGORY = f"{_CATEGORY}"
    DESCRIPTION = "Loads a text file from path within ComfyUI root folder."


    def read_file(self, file_path):
        # Resolve path relative to ComfyUI base directory, confined to it.
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
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
                    "default": "output/configs/config1.txt", 
                    "multiline": False,
                    "tooltip": "The path where the text file will be saved, relative to the ComfyUI root folder."
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
    DESCRIPTION = "Saves a string into a text file within ComfyUI root folder."


    def save_file(self, file_path, mode, text_input):
        # 1. Setup base paths (confined to the ComfyUI root).
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
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

        # 3. Create directories only inside the validated base directory.
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
