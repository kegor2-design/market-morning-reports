from __future__ import annotations
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
from .core import load_json

KST = ZoneInfo("Asia/Seoul")

def render_rumor_page(root: Path) -> str:
    rows = load_json(root / "data/state/event_intelligence/rumor_watch.json", {"rows": []}).get("rows", [])
    lifecycle = load_json(root / "data/state/event_intelligence/event_lifecycle.json", {"events": []}).get("events", [])
    evidence_by_id = {str(x.get("event_id")): x.get("evidence") or [] for x in lifecycle}
    cards = []
    for row in rows:
        evidence = evidence_by_id.get(str(row.get("event_id")), [])
        ev = evidence[-1] if evidence else {}
        source = ev.get("source_name") or ev.get("source_type") or "출처 확인 중"
        url = ev.get("url") or ""
        link = f"<a href='{escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>원문 보기</a>" if url else "원문 링크 없음"
        cards.append(f"<article class='rwc'><div><span>{escape(str(row.get('badge') or '미확인'))}</span><span>{escape(str(row.get('status') or 'UNVERIFIED'))}</span><span>{escape(str(row.get('confidence_band') or 'LOW'))}</span></div><h2>{escape(str(row.get('title') or '제목 미정'))}</h2><p>{escape(str(row.get('why_it_matters') or row.get('impact_summary') or '영향 확인 중'))}</p><small>{escape(str(source))} · {link}</small></article>")
    body = "".join(cards) or "<p class='rwe'>현재 추적 중인 미확인 소문·찌라시가 없습니다.</p>"
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    return f"""<style>.rw{{max-width:1100px;margin:auto;padding:24px 16px;font-family:Arial,'Noto Sans KR',sans-serif;color:#152236}}.rw header{{padding:24px;border-radius:14px;background:#071a2f;color:#fff}}.rw header p{{color:#c9d8e7}}.rwg{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:16px}}.rwc{{padding:18px;border:1px solid #dbe3ea;border-top:3px solid #b27a19;border-radius:11px;background:#fff}}.rwc div{{display:flex;gap:6px}}.rwc span{{padding:3px 6px;border-radius:4px;background:#fbf6ea;font-size:10px;font-weight:800}}.rwc h2{{font-size:17px}}.rwc p{{color:#566a7c;line-height:1.6}}.rwc a{{color:#145e9d}}@media(max-width:720px){{.rwg{{grid-template-columns:1fr}}}}</style><main class='rw'><header><small>RUMOR WATCH · UNVERIFIED</small><h1>소문·찌라시 추적 카드</h1><p>기사·유튜브·텔레그램의 확인 전 주장을 공식 사실과 분리해 추적합니다. 출처 수만으로 사실로 승격하지 않습니다.</p><b>갱신: {now} KST</b></header><section class='rwg'>{body}</section></main>"""
