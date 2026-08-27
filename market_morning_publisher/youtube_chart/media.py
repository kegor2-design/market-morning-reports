from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]


def safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    if not cleaned:
        raise ValueError("unsafe empty path component")
    return cleaned[:160]


def command_runner(args: Sequence[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(args), text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown yt-dlp error")[-1600:]
        raise RuntimeError(f"yt-dlp exited with {result.returncode}: {detail}")
    return result


def require_binary(binary: str) -> str:
    resolved = shutil.which(binary) if "/" not in binary else binary
    if not resolved or not Path(resolved).exists():
        raise RuntimeError(f"required executable not found: {binary}")
    return resolved


def _cookie_args(cookie_file: Path | None) -> list[str]:
    return ["--cookies", str(cookie_file)] if cookie_file else []


def list_channel_videos(
    channel_url: str,
    *,
    limit: int = 30,
    yt_dlp: str = "yt-dlp",
    cookie_file: Path | None = None,
    runner: Runner = command_runner,
) -> list[dict]:
    command = [
        require_binary(yt_dlp), "--flat-playlist", "--dump-single-json", "--playlist-end", str(limit),
        "--no-warnings", *_cookie_args(cookie_file), channel_url,
    ]
    payload = json.loads(runner(command, timeout=300).stdout)
    return [entry for entry in payload.get("entries", []) if entry and entry.get("id")]


def collect_metadata_and_captions(
    video_url: str,
    destination: Path,
    *,
    subtitle_languages: Sequence[str] = ("ko", "en"),
    yt_dlp: str = "yt-dlp",
    cookie_file: Path | None = None,
    runner: Runner = command_runner,
) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    output = str(destination / "%(id)s.%(ext)s")
    command = [
        require_binary(yt_dlp), "--skip-download", "--no-simulate", "--write-info-json", "--write-subs", "--write-auto-subs",
        "--sub-format", "vtt", "--sub-langs", ",".join(subtitle_languages), "--no-warnings",
        "--dump-single-json", "-o", output, *_cookie_args(cookie_file), video_url,
    ]
    result = runner(command, timeout=600)
    return json.loads(result.stdout)


def download_video_once(
    video_url: str,
    destination: Path,
    *,
    yt_dlp: str = "yt-dlp",
    cookie_file: Path | None = None,
    runner: Runner = command_runner,
) -> Path:
    destination.mkdir(parents=True, exist_ok=True)

    # 재실행 시 이미 받은 영상을 재사용한다.
    existing = [
        path
        for path in destination.glob("source_video.*")
        if (
            path.is_file()
            and path.suffix not in {".part", ".ytdl"}
            and path.stat().st_size > 0
        )
    ]

    if existing:
        return max(existing, key=lambda path: path.stat().st_size)

    output = str(destination / "source_video.%(ext)s")

    command = [
        require_binary(yt_dlp),
        "--no-playlist",
        "--no-warnings",
        "--no-simulate",
        "-f",
        "bv*[height<=1080]/b[height<=1080]",
        "--print",
        "after_move:filepath",
        "-o",
        output,
        *_cookie_args(cookie_file),
        video_url,
    ]

    result = runner(command, timeout=3600)

    # yt-dlp가 최종 경로를 stdout으로 돌려준 경우 우선 사용.
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if lines:
        reported = Path(lines[-1])

        if not reported.is_absolute():
            reported = Path.cwd() / reported

        if reported.exists():
            return reported.resolve()

    # stdout 형식이 달라져도 실제 생성 파일을 탐색한다.
    created = [
        path
        for path in destination.glob("source_video.*")
        if (
            path.is_file()
            and path.suffix not in {".part", ".ytdl"}
            and path.stat().st_size > 0
        )
    ]

    if not created:
        raise RuntimeError(
            f"yt-dlp did not create cached source video in {destination}"
        )

    return max(
        created,
        key=lambda path: path.stat().st_size
    ).resolve()


def download_claim_clip(
    video_url: str,
    output_path: Path,
    *,
    start_ms: int,
    end_ms: int,
    padding_ms: int = 2_000,
    yt_dlp: str = "yt-dlp",
    cookie_file: Path | None = None,
    runner: Runner = command_runner,
) -> Path:
    if end_ms <= start_ms:
        raise ValueError("clip end must be later than clip start")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start = max(0.0, (start_ms - padding_ms) / 1000)
    end = (end_ms + padding_ms) / 1000
    section = f"*{start:.3f}-{end:.3f}"
    command = [
        require_binary(yt_dlp), "--download-sections", section, "--force-keyframes-at-cuts",
        "-f", "bv*[height<=1080]/b[height<=1080]", "--no-playlist", "--no-warnings",
        "-o", str(output_path), *_cookie_args(cookie_file), video_url,
    ]
    runner(command, timeout=1800)
    return output_path


def extract_frame(
    video_path: Path,
    output_path: Path,
    *,
    timestamp_ms: int,
    ffmpeg: str = "ffmpeg",
    runner: Runner = command_runner,
) -> Path:
    if timestamp_ms < 0:
        raise ValueError("timestamp_ms cannot be negative")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_binary(ffmpeg), "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp_ms / 1000:.3f}",
        "-i", str(video_path), "-frames:v", "1", "-q:v", "2", "-y", str(output_path),
    ]
    runner(command, timeout=120)
    if not output_path.exists():
        raise RuntimeError(f"ffmpeg did not create frame: {output_path}")
    return output_path
