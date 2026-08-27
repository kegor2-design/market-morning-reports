from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import os

UTC = timezone.utc


@dataclass
class TelegramMessage:
    source_type: str
    message_id: str
    channel: str
    source_name: str
    author: str | None
    published_at: str
    url: str | None
    text: str
    metadata: dict[str, Any]


def normalize_message(channel: str, message_id: int | str, text: str, published_at: datetime, title: str | None = None, username: str | None = None, views: int | None = None, forwards: int | None = None, source_config: dict[str, Any] | None = None) -> dict[str, Any]:
    published_at = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    slug = username or channel.lstrip("@")
    url = f"https://t.me/{slug}/{message_id}" if slug else None
    source_config = dict(source_config or {})
    metadata = {"views": views, "forwards": forwards, "collector": "mtproto"}
    for key in ("registry_id", "tier", "role", "independence_group", "origin_group", "corroboration_eligible", "categories"):
        if key in source_config:
            out_key = {"registry_id":"source_registry_id", "tier":"source_tier", "role":"source_role"}.get(key, key)
            metadata[out_key] = source_config[key]
    row = TelegramMessage(
        source_type=str(source_config.get("default_source_type") or "TELEGRAM_NAMED"),
        message_id=str(message_id),
        channel=channel,
        source_name=title or channel,
        author=title or channel,
        published_at=published_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        url=url,
        text=(text or "").strip(),
        metadata=metadata,
    )
    out = asdict(row)
    if "attributable" in source_config:
        out["attributable"] = bool(source_config.get("attributable"))
    if source_config.get("registry_id"):
        out["registry_id"] = source_config["registry_id"]
    return out


def load_config(path: str | Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("contract") != "MMP_TELEGRAM_RUMOR_SOURCE_V1":
        raise ValueError("invalid telegram source contract")
    return obj


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(p)


async def _collect_mtproto(config: dict[str, Any], session_path: Path, api_id: int, api_hash: str, since_hours: int) -> list[dict[str, Any]]:
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError("telethon is not installed; use a separate telegram venv") from exc

    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    rows: list[dict[str, Any]] = []
    session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.start()
    try:
        for src in config.get("sources") or []:
            if not src.get("enabled", True):
                continue
            handle = str(src.get("handle") or "").strip()
            if not handle:
                continue
            entity = await client.get_entity(handle)
            username = getattr(entity, "username", None)
            title = getattr(entity, "title", None) or handle
            limit = int(src.get("max_messages_per_run") or config.get("max_messages_per_source") or 100)
            async for msg in client.iter_messages(entity, limit=limit):
                dt = getattr(msg, "date", None)
                if not dt:
                    continue
                dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
                if dt.astimezone(UTC) < cutoff:
                    break
                text = getattr(msg, "message", None) or ""
                if not text.strip():
                    continue
                rows.append(normalize_message(
                    channel=handle,
                    message_id=getattr(msg, "id", ""),
                    text=text,
                    published_at=dt,
                    title=title,
                    username=username,
                    views=getattr(msg, "views", None),
                    forwards=getattr(msg, "forwards", None),
                    source_config=src,
                ))
    finally:
        await client.disconnect()
    # de-duplicate by channel/message id, newest first
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        unique[(row["channel"], row["message_id"])] = row
    return sorted(unique.values(), key=lambda x: x["published_at"], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect allowlisted Telegram public-channel messages for rumor intelligence")
    parser.add_argument("--config", default="config/telegram_rumor_sources.json")
    parser.add_argument("--output", default="data/private/telegram/normalized/messages.jsonl")
    parser.add_argument("--session", default="data/private/telegram/session/mmp_telegram")
    parser.add_argument("--since-hours", type=int, default=48)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    enabled = bool(config.get("enabled"))
    sources = [x for x in config.get("sources") or [] if x.get("enabled", True) and x.get("handle")]
    print(f"telegram_enabled={enabled} configured_sources={len(sources)}")
    if args.check_only or not enabled:
        return 0

    api_id_raw = os.getenv("MMP_TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("MMP_TELEGRAM_API_HASH", "").strip()
    if not api_id_raw or not api_hash:
        raise SystemExit("[BLOCK] MMP_TELEGRAM_API_ID/MMP_TELEGRAM_API_HASH missing")
    api_id = int(api_id_raw)

    import asyncio
    rows = asyncio.run(_collect_mtproto(config, Path(args.session), api_id, api_hash, max(1, args.since_hours)))
    write_jsonl(args.output, rows)
    print(f"telegram_messages={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
