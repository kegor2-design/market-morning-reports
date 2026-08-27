from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def fallback_enabled() -> bool:
    return os.getenv("MMP_YOUTUBE_ASR_FALLBACK", "0") == "1"


def _require(binary: str) -> str:
    resolved = binary if Path(binary).is_file() else shutil.which(binary)
    if not resolved:
        raise RuntimeError(f"required binary not found: {binary}")
    return str(resolved)


def _format_vtt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def _download_audio(
    video_url: str,
    destination: Path,
    *,
    yt_dlp: str,
    cookie_file: Path | None,
) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    existing = [p for p in destination.glob("source_audio.*") if p.is_file() and p.suffix not in {".part", ".ytdl"} and p.stat().st_size > 0]
    if existing:
        return max(existing, key=lambda p: p.stat().st_size)
    command = [
        _require(yt_dlp), "--no-playlist", "--no-warnings", "-f", "bestaudio/best",
        "--print", "after_move:filepath", "-o", str(destination / "source_audio.%(ext)s"),
    ]
    if cookie_file:
        command.extend(["--cookies", str(cookie_file)])
    command.append(video_url)
    process = subprocess.run(command, text=True, capture_output=True, timeout=3600, check=False)
    if process.returncode != 0:
        raise RuntimeError(f"yt-dlp audio download failed: {(process.stderr or process.stdout)[-1000:]}")
    reported = [Path(line.strip()) for line in process.stdout.splitlines() if line.strip()]
    for path in reversed(reported):
        if path.exists() and path.is_file():
            return path
    files = [p for p in destination.glob("source_audio.*") if p.is_file() and p.stat().st_size > 0]
    if not files:
        raise RuntimeError("audio download completed without an output file")
    return max(files, key=lambda p: p.stat().st_size)


def transcribe_with_faster_whisper(
    video_url: str,
    destination: Path,
    *,
    language: str | None,
    yt_dlp: str = "yt-dlp",
    cookie_file: Path | None = None,
    model_name: str | None = None,
    force: bool = False,
) -> Path:
    """Optional expensive fallback. Disabled unless explicitly enabled by environment.

    This function imports faster_whisper lazily so the normal release has no new runtime
    dependency.  It writes a VTT compatible with the existing caption parser.
    """
    if not (force or fallback_enabled()):
        raise RuntimeError("ASR fallback is disabled; set MMP_YOUTUBE_ASR_FALLBACK=1 explicitly")
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        # The transcript collector owns the heavy ASR dependency. Reuse its isolated
        # site-packages instead of duplicating the model stack in the publisher env.
        collector_env = Path(__file__).resolve().parents[2] / "tools/youtube_transcript_collector/.venv/lib"
        for site in collector_env.glob("python*/site-packages"):
            if str(site) not in sys.path:
                sys.path.insert(0, str(site))
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise RuntimeError("faster-whisper is unavailable in both publisher and transcript-collector environments") from exc
    audio = _download_audio(video_url, destination, yt_dlp=yt_dlp, cookie_file=cookie_file)
    model = WhisperModel(
        model_name or os.getenv("MMP_YOUTUBE_ASR_MODEL", "small"),
        device=os.getenv("MMP_YOUTUBE_ASR_DEVICE", "cpu"),
        compute_type=os.getenv("MMP_YOUTUBE_ASR_COMPUTE_TYPE", "int8"),
    )
    segments, info = model.transcribe(str(audio), language=language or None, vad_filter=True, beam_size=3)
    output = destination / "fallback.asr.vtt"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write("WEBVTT\n\n")
        for index, segment in enumerate(segments, 1):
            text = " ".join(str(segment.text or "").split())
            if not text:
                continue
            handle.write(f"{index}\n{_format_vtt_time(float(segment.start))} --> {_format_vtt_time(float(segment.end))}\n{text}\n\n")
    if temporary.stat().st_size <= 8:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"ASR produced no transcript (language={getattr(info, 'language', None)})")
    temporary.replace(output)
    return output
