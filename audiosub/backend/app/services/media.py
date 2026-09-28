"""FFmpeg helpers: probing and audio extraction/normalisation."""

import os
import re
import shutil
import subprocess
import wave

from ..config import get_settings

SUPPORTED_EXTENSIONS = {
    "mp3": "audio",
    "wav": "audio",
    "m4a": "audio",
    "mp4": "video",
}
# Accepted by FFmpeg already; enable by adding to SUPPORTED_EXTENSIONS.
FUTURE_EXTENSIONS = {"mov": "video", "mkv": "video", "aac": "audio", "flac": "audio"}


class MediaError(Exception):
    pass


def file_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


def media_kind(filename: str) -> str | None:
    return SUPPORTED_EXTENSIONS.get(file_extension(filename))


def ffmpeg_binary() -> str:
    configured = get_settings().ffmpeg_binary
    if shutil.which(configured) or os.path.isfile(configured):
        return configured
    try:  # dev/test fallback: bundled binary from imageio-ffmpeg
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise MediaError(
            "FFmpeg not found. Install it or set FFMPEG_BINARY to its path."
        ) from exc


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_STREAM_RE = re.compile(r"Stream #\S+.*?: Audio:")


def probe(path: str) -> dict:
    """Return {duration, has_audio}. Uses `ffmpeg -i` so ffprobe is not required."""
    proc = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-i", path],
        capture_output=True,
        text=True,
        errors="replace",
    )
    info = proc.stderr
    match = _DURATION_RE.search(info)
    duration = None
    if match:
        h, m, s = match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)
    if "Invalid data found" in info or (duration is None and "Stream #" not in info):
        raise MediaError("File is not a readable audio/video file.")
    return {"duration": duration, "has_audio": bool(_AUDIO_STREAM_RE.search(info))}


def extract_audio(src: str, dest_wav: str, normalize: bool = True) -> float:
    """Convert any input (audio or video) to 16 kHz mono PCM WAV for ASR.

    Returns the duration of the produced audio in seconds.
    """
    filters = ["loudnorm=I=-16:TP=-1.5:LRA=11"] if normalize else []
    cmd = [ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vn"]
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dest_wav]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0 or not os.path.exists(dest_wav):
        raise MediaError(f"Audio extraction failed: {proc.stderr.strip()[-500:]}")
    return wav_duration(dest_wav)


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())
