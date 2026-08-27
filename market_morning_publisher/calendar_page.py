from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import load_json
from .calendar_decision_card import compact_card_summary, decision_card_from_event
from .post_event_result import PostEventResult, calendar_phase, compact_result_summary
from .calendar_event_impact import project_impact_and_scenarios

KST = ZoneInfo("Asia/Seoul")


def _event_date(row: dict) -> str:
    return str(row.get("scheduled_at_kst") or row.get("event_date") or "")[:10]


def _event_time(row: dict) -> str:
    value = str(row.get("scheduled_at_kst") or "")
    return value[11:16] if len(value) >= 16 else "미정"


def calendar_rows(root: Path, now: datetime | None = None) -> list[dict]:
    now = (now or datetime.now(KST)).astimezone(KST)
    official = load_json(root / "data/state/event_intelligence/calendar.json", {"events": []}).get("events", [])
    overlay = load_json(root / "data/state/event_intelligence/calendar_overlay.json", {"rows": []}).get("rows", [])
    rows = []
    for raw in [*official, *overlay]:
        date = _event_date(raw)
        if not date or date < (now.date() - timedelta(days=90)).isoformat():
            continue
        truth = str(raw.get("truth_class") or "OFFICIAL_FACT")
        result_raw = raw.get("post_event_result") or None
        result = PostEventResult.from_dict(result_raw) if result_raw else None
        event_time = raw.get("scheduled_at_kst") or raw.get("event_date")
        phase = str(raw.get("calendar_phase") or calendar_phase(event_time, result, now=now,
                    result_expected_at=raw.get("result_expected_at"), estimated_end_date=raw.get("estimated_end_date")))
        impact = project_impact_and_scenarios(raw)
        rows.append({
            "event_id": str(raw.get("event_id") or raw.get("id") or "event"),
            "date": date,
            "time": _event_time(raw),
            "name": str(raw.get("name") or raw.get("title") or "이름 미정"),
            "importance": str(raw.get("dynamic_importance") or raw.get("base_importance") or raw.get("confidence_band") or "B"),
            "status": str(raw.get("status") or "SCHEDULED"),
            "badge": str(raw.get("badge") or ("공식" if truth == "OFFICIAL_FACT" else "미확인")),
            "detail": str(raw.get("korea_transmission") or raw.get("why_it_matters") or raw.get("impact_summary") or "추가 확인 예정"),
            "source_url": str(raw.get("source_url") or ""),
            "decision_card": {**compact_card_summary(decision_card_from_event(raw)), **impact},
            "calendar_phase": phase,
            "post_event_result": compact_result_summary(result),
        })
    unique = {}
    for row in rows:
        unique[(row["event_id"], row["date"], row["time"])] = row
    return sorted(unique.values(), key=lambda x: (x["date"], x["time"], x["name"]))


def render_calendar_page(root: Path, now: datetime | None = None) -> str:
    now = (now or datetime.now(KST)).astimezone(KST)
    today = now.date().isoformat()
    rows = calendar_rows(root, now)
    cards = []
    for row in rows:
        today_class = " today" if row["date"] == today else ""
        today_label = "<strong class='mcal-today'>오늘</strong>" if today_class else ""
        source = f"<a href='{escape(row['source_url'], quote=True)}' target='_blank' rel='noopener noreferrer'>공식 원문</a>" if row["source_url"] else "원문 확인 중"
        card = row["decision_card"]
        impact = card.get("impact_profile") or {}
        impact_badge = escape(str(impact.get("badge") or ""))
        impact_intro = (f"<section class='mcal-impact'><b>{impact_badge}</b><p>{escape(str(impact.get('plain_label') or ''))}</p>"
                        f"<p>{escape(str(impact.get('reason') or ''))}</p></section>") if impact else ""
        outcome_html = "".join(
            f"<li><b>{escape(str(x.get('name') or '조건부 시나리오'))}</b> — {escape(str(x.get('if_result') or ''))}<br>"
            f"{escape(str(x.get('beginner_summary') or ''))}</li>" for x in card.get("outcome_scenarios") or []
        )
        phase = row["calendar_phase"]
        result = row.get("post_event_result")
        current = ""
        if card.get("current_view"):
            confidence = f" · {escape(str(card.get('current_view_confidence') or ''))}" if card.get("current_view_confidence") else ""
            current = f"<section class='mcal-current'><b>현재 우리 판단{confidence}</b><p>{escape(card['current_view'])}</p></section>"
        watches = "".join(f"<li><b>{escape(str(x.get('label') or '확인'))}</b> {escape(str(x.get('what_to_check') or ''))}</li>" for x in card.get("watch_items") or [])
        scenarios = "".join(x for x in (
            f"<li><b>상방:</b> {escape(str(card['scenario_up']))}</li>" if card.get("scenario_up") else "",
            f"<li><b>하방:</b> {escape(str(card['scenario_down']))}</li>" if card.get("scenario_down") else "",
        ))
        invalidation = "".join(f"<li>{escape(str(x))}</li>" for x in card.get("invalidation_conditions") or [])
        glossary = "".join(f"<li><b>{escape(str(k))}</b>: {escape(str(v))}</li>" for k, v in (card.get("beginner_glossary") or {}).items())
        path = " → ".join(escape(str(x)) for x in card.get("transmission_path") or [])
        result_html = ""
        if phase == "RESULT_PENDING":
            result_html = "<section class='mcal-result pending'><b>결과 확인 중</b><p>일정은 끝났지만 공식 결과를 확인 중입니다.</p></section>"
        elif result:
            reactions = "".join(
                f"<li><b>{escape(str(x.get('window') or '관측'))} · {escape(str(x.get('asset') or '자산'))}</b> "
                f"{escape(str(x.get('change_pct')) + '%' if x.get('change_pct') is not None else str(x.get('interpretation') or '관측 중'))}</li>"
                for x in result.get("market_reactions") or []
            )
            next_watch = "".join(f"<li>{escape(str(x))}</li>" for x in result.get("next_watch") or [])
            result_html = (
                f"<section class='mcal-result'><b>공식 결과</b><h2>{escape(str(result.get('headline') or '공식 결과가 확인됐습니다.'))}</h2>"
                f"<p>{escape(str(result.get('official_result_summary') or ''))}</p>"
                f"{f'<h3>예상 대비</h3><p>{escape(str(result.get("expected_vs_actual")))}</p>' if result.get('expected_vs_actual') else ''}"
                f"{f'<h3>시장반응</h3><ul>{reactions}</ul>' if reactions else ''}"
                f"{f'<h3>OUR_MI 사후평가 · {escape(str(result.get("mi_review_status")))}</h3><p>{escape(str(result.get("mi_review_summary") or "평가 대기 중"))}</p>' if phase == 'REVIEW_COMPLETE' or result.get('mi_review_status') not in (None, 'PENDING') else '<p>OUR_MI 평가는 아직 PENDING입니다.</p>'}"
                f"{f'<h3>무엇이 바뀌었나</h3><p>{escape(str(result.get("what_changed")))}</p>' if result.get('what_changed') else ''}"
                f"{f'<h3>다음에 볼 것</h3><ul>{next_watch}</ul>' if next_watch else ''}</section>"
            )
        cards.append(
            f"<article class='mcal-event{today_class}' id='{escape(row['event_id'], quote=True)}'>"
            f"<div class='mcal-when'>{escape(row['date'])} {escape(row['time'])}{today_label}</div>"
            f"<div class='mcal-meta'><span>{escape(row['badge'])}</span><span>{escape(row['importance'])}</span><span>{escape(row['status'])}</span></div>"
            f"<div class='mcal-phase'>{escape(phase)}</div>{impact_intro}{result_html}"
            f"<h2 class='mcal-question'>{escape(card['decision_question'])}</h2>"
            f"<p class='mcal-summary'>{escape(card['plain_summary'])}</p>"
            f"<section class='mcal-why'><b>왜 중요한가</b><p>{escape(card['why_it_matters'])}</p></section>{current}"
            f"<details><summary>상세 판단 카드 · {escape(row['name'])}</summary>"
            f"<h3>무엇을 볼까</h3><ul>{watches}</ul>"
            f"{f'<h3>결과별 시나리오</h3><ul>{scenarios}</ul>' if scenarios else ''}"
            f"{f'<h3>조건부 결과 시나리오</h3><ul>{outcome_html}</ul>' if outcome_html else ''}"
            f"{f'<h3>판단이 틀렸다고 볼 조건</h3><ul>{invalidation}</ul>' if invalidation else ''}"
            f"{f'<h3>용어 설명</h3><ul>{glossary}</ul>' if glossary else ''}"
            f"{f'<h3>시장 전달경로</h3><p>{path}</p>' if path else ''}"
            f"<small>{source}</small></details></article>"
        )
    body = "".join(cards) or "<p class='mcal-empty'>현재 확인된 예정 일정이 없습니다.</p>"
    return f"""<style>
.mcal{{max-width:1100px;margin:0 auto;padding:24px 16px;color:#152236;font-family:Arial,'Noto Sans KR',sans-serif}}.mcal header{{padding:24px;border-radius:14px;background:#071a2f;color:#fff}}.mcal header small{{color:#a9bfd1}}.mcal-list{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:16px}}.mcal-event{{padding:18px;border:1px solid #dbe3ea;border-radius:11px;background:#fff}}.mcal-event.today{{border:2px solid #2068a0;background:#eef6fc}}.mcal-when{{font-weight:900;color:#145e9d}}.mcal-today{{margin-left:8px;padding:3px 6px;border-radius:5px;background:#2068a0;color:#fff;font-size:10px}}.mcal-meta{{display:flex;gap:6px;margin:9px 0}}.mcal-meta span,.mcal-phase{{display:inline-block;padding:3px 6px;border-radius:4px;background:#edf2f6;font-size:10px;font-weight:800}}.mcal-question{{margin:8px 0;font-size:19px;line-height:1.35}}.mcal-event p{{color:#566a7c;line-height:1.5;margin:6px 0}}.mcal-why,.mcal-current,.mcal-result{{padding:9px 11px;margin:8px 0;border-radius:8px;background:#f4f7fa}}.mcal-current{{background:#eaf4ff}}.mcal-result{{background:#eef8f1;border-left:4px solid #24834b}}.mcal-result.pending{{background:#fff7e7;border-color:#ca7a12}}.mcal-event details{{margin-top:10px}}.mcal-event summary{{cursor:pointer;font-weight:800;color:#145e9d}}.mcal-event h3{{font-size:13px;margin:12px 0 5px}}.mcal-event ul{{margin:4px 0;padding-left:20px;color:#566a7c}}@media(max-width:720px){{.mcal{{padding:12px 8px}}.mcal header{{padding:14px}}.mcal-list{{grid-template-columns:1fr}}.mcal-event{{padding:13px}}.mcal-question{{font-size:17px}}}}
</style><main class='mcal'><header><small>MARKET EVENT INTELLIGENCE · KST</small><h1>Market Calendar | 주요 일정</h1><p>공식 일정, 보도·주장, 미확인 추적 이벤트를 분리해 지속 관리합니다.</p><b>기준일: {today} KST</b></header><section class='mcal-list' id='calendar-upcoming'>{body}</section></main>"""
