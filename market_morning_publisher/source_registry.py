from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json
import re

CONTRACT = "MMP_SOURCE_REGISTRY_V1"


def _norm_handle(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "t.me/" in text:
        text = text.split("t.me/", 1)[1].split("?", 1)[0].strip("/")
    elif "youtube.com/@" in text:
        text = "@" + text.split("youtube.com/@", 1)[1].split("/", 1)[0]
    if text and not text.startswith("@") and "/" not in text and "." not in text:
        text = "@" + text
    return text


@dataclass(frozen=True)
class SourceRegistryEntry:
    id: str
    platform: str
    handle: str
    name: str
    url: str
    owner: str
    tier: str
    role: str
    default_source_type: str
    attributable: bool
    corroboration_eligible: bool
    independence_group: str
    origin_group: str
    categories: tuple[str, ...]
    enabled: bool = True
    official_capability: bool = False
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceRegistryEntry":
        return cls(
            id=str(raw["id"]),
            platform=str(raw["platform"]).upper(),
            handle=str(raw.get("handle") or ""),
            name=str(raw.get("name") or raw["id"]),
            url=str(raw.get("url") or ""),
            owner=str(raw.get("owner") or ""),
            tier=str(raw.get("tier") or "D").upper(),
            role=str(raw.get("role") or "DISCOVERY").upper(),
            default_source_type=str(raw.get("default_source_type") or "RUMOR").upper(),
            attributable=bool(raw.get("attributable")),
            corroboration_eligible=bool(raw.get("corroboration_eligible")),
            independence_group=str(raw.get("independence_group") or raw["id"]),
            origin_group=str(raw.get("origin_group") or raw.get("independence_group") or raw["id"]),
            categories=tuple(str(x) for x in raw.get("categories") or []),
            enabled=bool(raw.get("enabled", True)),
            official_capability=bool(raw.get("official_capability", False)),
            notes=str(raw.get("notes") or ""),
        )


class SourceRegistry:
    def __init__(self, entries: Iterable[SourceRegistryEntry]):
        self.entries = tuple(entries)
        self.by_id = {e.id: e for e in self.entries}
        if len(self.by_id) != len(self.entries):
            raise ValueError("duplicate source registry id")
        self.by_platform_handle: dict[tuple[str, str], SourceRegistryEntry] = {}
        self.by_platform_name: dict[tuple[str, str], SourceRegistryEntry] = {}
        for e in self.entries:
            key = (e.platform, _norm_handle(e.handle))
            if key[1]:
                self.by_platform_handle[key] = e
            name_key = (e.platform, e.name.strip().lower())
            if name_key[1]:
                self.by_platform_name[name_key] = e

    def find(self, raw: dict[str, Any]) -> SourceRegistryEntry | None:
        registry_id = str(raw.get("registry_id") or raw.get("source_registry_id") or "").strip()
        if registry_id and registry_id in self.by_id:
            return self.by_id[registry_id]

        source_type = str(raw.get("source_type") or raw.get("platform") or "").upper()
        if source_type.startswith("TELEGRAM"):
            platform = "TELEGRAM"
        elif source_type.startswith("YOUTUBE"):
            platform = "YOUTUBE"
        elif source_type in {"OPENDART", "KRX", "BOK", "FED", "TREASURY", "GOV", "COMPANY_IR", "EXCHANGE_NOTICE"}:
            platform = "OFFICIAL"
        else:
            platform = str(raw.get("platform") or "").upper()

        candidates = [
            raw.get("channel"), raw.get("handle"), raw.get("source_name"), raw.get("author"), raw.get("url"), raw.get("source_type")
        ]
        for value in candidates:
            handle = _norm_handle(value)
            if handle and (platform, handle) in self.by_platform_handle:
                return self.by_platform_handle[(platform, handle)]
            name = str(value or "").strip().lower()
            if name and (platform, name) in self.by_platform_name:
                return self.by_platform_name[(platform, name)]
        return None

    def enrich(self, raw: dict[str, Any]) -> dict[str, Any]:
        row = dict(raw)
        entry = self.find(row)
        if entry is None:
            return row
        metadata = dict(row.get("metadata") or {})
        metadata.update({
            "source_registry_id": entry.id,
            "source_tier": entry.tier,
            "source_role": entry.role,
            "independence_group": entry.independence_group,
            "origin_group": entry.origin_group,
            "corroboration_eligible": entry.corroboration_eligible,
            "source_owner": entry.owner,
            "official_capability": entry.official_capability,
        })
        row["metadata"] = metadata
        row["registry_id"] = entry.id
        row["source_type"] = entry.default_source_type
        row["attributable"] = entry.attributable
        if not row.get("source_name"):
            row["source_name"] = entry.name
        if not row.get("channel") and entry.platform == "TELEGRAM":
            row["channel"] = entry.handle
        return row


def load_source_registry(path: str | Path) -> SourceRegistry:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("contract") != CONTRACT:
        raise ValueError(f"invalid source registry contract: {obj.get('contract')}")
    entries = [SourceRegistryEntry.from_dict(x) for x in obj.get("sources") or []]
    if not entries:
        raise ValueError("source registry is empty")
    for e in entries:
        if e.tier not in {"A", "B", "C", "D"}:
            raise ValueError(f"invalid source tier: {e.id}:{e.tier}")
        if not e.independence_group:
            raise ValueError(f"missing independence_group: {e.id}")
    return SourceRegistry(entries)
