from __future__ import annotations

import html
import os
import re
from typing import Iterable


DESKTOP_BREAKPOINT = 820


def _inline(text: str) -> str:
    from .blogger_render import _inline as legacy_inline
    return legacy_inline(text)


def _markdown(text: str) -> str:
    from .blogger_render import _markdown_blocks
    return _markdown_blocks(text)


def _section(markdown: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    return match.group(1).strip() if match else ""


def _sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, re.M))
    result: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        if start < len(markdown) and markdown[start] == "\n":
            start += 1
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        result.append((match.group(1).strip(), markdown[start:end].strip()))
    return result


def _strip_h1(markdown: str) -> str:
    return re.sub(r"^# .+\n?", "", markdown, count=1, flags=re.M)


def _title(markdown: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, re.M)
    return match.group(1).strip() if match else fallback


def _date_from_title(title: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", title)
    return match.group(0) if match else ""


def _bold_first(section: str, fallback: str = "확인 불가") -> str:
    match = re.search(r"^\*\*(.+?)\*\*", section, re.M)
    return match.group(1).strip() if match else fallback


def _bullet_value(section: str, label: str, fallback: str = "확인 불가") -> str:
    match = re.search(rf"^-\s*{re.escape(label)}:\s*(?:\*\*)?(.+?)(?:\*\*)?\s*$", section, re.M)
    if not match:
        return fallback
    return re.sub(r"\*\*", "", match.group(1)).strip()


def _list_items(section: str, limit: int | None = None) -> list[str]:
    values = []
    for line in section.splitlines():
        if line.startswith("- "):
            value = line[2:].strip()
            value = re.sub(r"^\*\*(.+?)\*\*\s*[—:-]?\s*", r"\1 — ", value)
            values.append(value)
            if limit is not None and len(values) >= limit:
                break
    return values


def _compact_list(values: Iterable[str], empty: str = "확인 가능한 항목이 없습니다.") -> str:
    items = [x for x in values if x]
    if not items:
        return f'<div class="mmp-empty">{html.escape(empty)}</div>'
    return '<ul class="mmp-compact-list">' + ''.join(f'<li>{_inline(x)}</li>' for x in items) + '</ul>'


def _details(title: str, body: str, open_by_default: bool = False) -> str:
    state = " open" if open_by_default else ""
    return (
        f'<details class="mmp-mobile-detail"{state}><summary>{html.escape(title)}</summary>'
        f'<div class="mmp-mobile-detail-body">{_markdown(body)}</div></details>'
    )


def _extract_table_rows(section: str, min_cells: int = 2) -> list[list[str]]:
    lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if len(cells) >= min_cells:
            rows.append(cells)
    return rows


def _responsive_css() -> str:
    return f"""<style>
.mmp-responsive{{--mmp-navy:#071a2f;--mmp-navy2:#102f50;--mmp-blue:#2068a0;--mmp-ink:#152236;--mmp-muted:#667085;--mmp-line:#dbe3ea;--mmp-soft:#f4f7fa;--mmp-up:#087a55;--mmp-down:#c33d3d;--mmp-watch:#a66a00;max-width:1240px;margin:0 auto;color:var(--mmp-ink);font-family:Arial,'Noto Sans KR',sans-serif;line-height:1.68;background:#fff}}
.mmp-responsive *{{box-sizing:border-box}}.mmp-responsive a{{color:#145e9d;text-decoration:none}}.mmp-responsive a:hover{{text-decoration:underline}}
.mmp-desktop{{display:block}}.mmp-mobile{{display:none}}
.mmp-desktop-hero{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:end;padding:34px 38px;background:linear-gradient(135deg,#061729,#123c66);color:#fff;border-radius:14px 14px 0 0;box-shadow:0 10px 26px rgba(7,26,47,.15)}}
.mmp-eyebrow{{font-size:10px;font-weight:800;letter-spacing:.18em;color:#9ec5e7}}.mmp-desktop-hero h1{{margin:6px 0 8px;font-size:31px;line-height:1.25}}.mmp-hero-meta{{font-size:12px;color:#cbd9e7}}.mmp-hero-badge{{min-width:150px;padding:12px 15px;border:1px solid rgba(255,255,255,.22);border-radius:9px;background:rgba(255,255,255,.08);text-align:right}}.mmp-hero-badge small{{display:block;color:#a9c5df;font-size:9px;letter-spacing:.12em}}.mmp-hero-badge strong{{display:block;margin-top:2px;font-size:17px}}
.mmp-desk-shell{{padding:20px 22px 34px;background:#eef3f7;border:1px solid #d8e1e8;border-top:0}}.mmp-desk-grid{{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:12px}}.mmp-panel{{background:#fff;border:1px solid var(--mmp-line);border-radius:9px;padding:17px 18px;box-shadow:0 1px 3px rgba(16,24,40,.04);min-width:0}}.mmp-panel h2{{margin:0 0 11px;padding:0;border:0;color:var(--mmp-navy);font-size:16px}}.mmp-panel h3{{font-size:14px;color:#244d73}}.mmp-panel p{{margin:7px 0}}.mmp-panel ul{{margin:6px 0;padding-left:18px}}.mmp-panel li{{margin:5px 0}}.mmp-panel table{{width:100%;border-collapse:collapse;font-size:11px}}.mmp-panel th{{padding:8px;background:var(--mmp-navy);color:#fff;text-align:left}}.mmp-panel td{{padding:8px;border-bottom:1px solid var(--mmp-line);vertical-align:top}}.mmp-panel .mmp-table-wrap{{overflow-x:auto;margin:8px 0}}
.mmp-span-12{{grid-column:span 12}}.mmp-span-8{{grid-column:span 8}}.mmp-span-7{{grid-column:span 7}}.mmp-span-6{{grid-column:span 6}}.mmp-span-5{{grid-column:span 5}}.mmp-span-4{{grid-column:span 4}}
.mmp-desk-view{{border-left:4px solid var(--mmp-blue);background:linear-gradient(120deg,#fff,#f5f9fc)}}.mmp-desk-view strong{{display:block;font-size:19px;line-height:1.45;color:var(--mmp-navy)}}.mmp-desk-view .mmp-subline{{margin-top:9px;font-size:12px;color:#42556b}}
.mmp-market-tiles{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}}.mmp-market-tile{{padding:12px;border:1px solid var(--mmp-line);border-top:3px solid #98a2b3;border-radius:7px;background:#fff}}.mmp-market-tile.up{{border-top-color:var(--mmp-up)}}.mmp-market-tile.down{{border-top-color:var(--mmp-down)}}.mmp-market-tile small{{display:block;color:var(--mmp-muted);font-size:9px}}.mmp-market-tile b{{display:block;margin-top:5px;color:var(--mmp-navy);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.mmp-market-tile strong{{display:block;margin-top:3px;font-size:18px}}.mmp-market-tile em{{font-style:normal;font-weight:800;font-size:12px}}.mmp-market-tile.up em{{color:var(--mmp-up)}}.mmp-market-tile.down em{{color:var(--mmp-down)}}
.mmp-section-label{{margin-bottom:8px;color:#64788e;font-size:9px;font-weight:800;letter-spacing:.13em}}.mmp-compact-list{{margin:0;padding-left:18px}}.mmp-compact-list li{{margin:5px 0}}.mmp-empty{{color:var(--mmp-muted);font-size:12px}}.mmp-detailed{{margin-top:16px;padding:22px 24px;background:#fff;border:1px solid var(--mmp-line);border-radius:9px}}.mmp-detailed>h2{{margin:0 0 16px;color:var(--mmp-navy);font-size:18px}}.mmp-detailed h2{{margin-top:31px;padding-bottom:7px;border-bottom:2px solid var(--mmp-navy);color:var(--mmp-navy);font-size:18px}}.mmp-detailed h3{{font-size:15px;color:#244d73}}.mmp-detailed .mmp-table-wrap{{overflow-x:auto}}.mmp-detailed table{{width:100%;border-collapse:collapse;font-size:11px}}.mmp-detailed th{{background:var(--mmp-navy);color:#fff;text-align:left;padding:8px}}.mmp-detailed td{{padding:8px;border-bottom:1px solid var(--mmp-line);vertical-align:top}}
.mmp-mobile-hero{{padding:20px 17px;background:linear-gradient(135deg,#071a2f,#154a78);color:#fff;border-radius:10px 10px 0 0}}.mmp-mobile-hero h1{{margin:5px 0;font-size:21px;line-height:1.35}}.mmp-mobile-meta{{font-size:10px;color:#c9d8e7}}.mmp-mobile-body{{padding:12px;background:#f1f5f8;border:1px solid #dce4eb;border-top:0}}.mmp-mobile-card{{margin-bottom:10px;padding:14px;background:#fff;border:1px solid var(--mmp-line);border-radius:8px}}.mmp-mobile-card h2{{margin:0 0 8px;border:0;padding:0;font-size:14px;color:var(--mmp-navy)}}.mmp-mobile-diagnosis{{border-left:4px solid var(--mmp-blue)}}.mmp-mobile-diagnosis strong{{display:block;font-size:16px;line-height:1.5;color:var(--mmp-navy)}}.mmp-mobile-scroll{{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x proximity;padding-bottom:4px}}.mmp-mobile-market{{flex:0 0 145px;scroll-snap-align:start;padding:11px;border:1px solid var(--mmp-line);border-top:3px solid #98a2b3;border-radius:7px;background:#fff}}.mmp-mobile-market.up{{border-top-color:var(--mmp-up)}}.mmp-mobile-market.down{{border-top-color:var(--mmp-down)}}.mmp-mobile-market span{{display:block;font-size:10px;color:var(--mmp-muted)}}.mmp-mobile-market b{{display:block;margin-top:3px;font-size:12px;color:var(--mmp-navy);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.mmp-mobile-market strong{{display:block;margin-top:3px;font-size:16px}}.mmp-mobile-market em{{font-style:normal;font-size:11px;font-weight:800}}.mmp-mobile-market.up em{{color:var(--mmp-up)}}.mmp-mobile-market.down em{{color:var(--mmp-down)}}
.mmp-mobile-detail{{margin-bottom:8px;background:#fff;border:1px solid var(--mmp-line);border-radius:8px;overflow:hidden}}.mmp-mobile-detail summary{{position:relative;padding:13px 38px 13px 14px;cursor:pointer;list-style:none;color:var(--mmp-navy);font-size:13px;font-weight:800}}.mmp-mobile-detail summary::-webkit-details-marker{{display:none}}.mmp-mobile-detail summary:after{{content:'+';position:absolute;right:14px;top:10px;font-size:18px;color:#59728a}}.mmp-mobile-detail[open] summary:after{{content:'–'}}.mmp-mobile-detail-body{{padding:0 14px 14px;border-top:1px solid #edf1f5;font-size:12px}}.mmp-mobile-detail-body h3{{font-size:13px;color:#244d73}}.mmp-mobile-detail-body .mmp-table-wrap{{overflow-x:auto}}.mmp-mobile-detail-body table{{min-width:640px;width:100%;border-collapse:collapse;font-size:10px}}.mmp-mobile-detail-body th{{background:var(--mmp-navy);color:#fff;padding:7px}}.mmp-mobile-detail-body td{{padding:7px;border-bottom:1px solid var(--mmp-line)}}
.mmp-mobile-news li{{margin:7px 0}}.mmp-history-link{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px;padding:12px 14px;border:1px solid #ddb24c;border-radius:8px;background:linear-gradient(120deg,#0b2744,#174f7d);color:#fff!important;text-decoration:none}}.mmp-history-link span{{display:block}}.mmp-history-link b{{display:block;color:#fff}}.mmp-history-link small{{display:block;margin-top:2px;color:#cfe0ed;font-size:10px}}.mmp-history-link em{{font-style:normal;font-size:19px;color:#f2ca62}}.mmp-mobile-footnote{{color:#6c7c8d;font-size:10px;line-height:1.55}}
@media(max-width:{DESKTOP_BREAKPOINT}px){{.mmp-desktop{{display:none!important}}.mmp-mobile{{display:block!important}}.mmp-responsive{{max-width:100%;line-height:1.6}}}}
@media(min-width:{DESKTOP_BREAKPOINT + 1}px){{.mmp-mobile{{display:none!important}}.mmp-desktop{{display:block!important}}}}
@media(max-width:1100px) and (min-width:{DESKTOP_BREAKPOINT + 1}px){{.mmp-market-tiles{{grid-template-columns:repeat(4,minmax(0,1fr))}}.mmp-span-4{{grid-column:span 6}}}}
</style>"""


def _market_rows(markdown: str, section_name: str = "밤사이 시장 계기판") -> list[dict[str, str]]:
    rows = _extract_table_rows(_section(markdown, section_name), 4)
    if len(rows) <= 1:
        return []
    result = []
    for cells in rows[1:]:
        if len(cells) < 4:
            continue
        result.append({
            "region": cells[0], "market": cells[1], "value": cells[2], "change": cells[3],
            "session": cells[4] if len(cells) > 4 else "", "asof": cells[5] if len(cells) > 5 else "",
        })
    return result


def _market_tiles(rows: list[dict[str, str]], mobile: bool = False) -> str:
    cls = "mmp-mobile-market" if mobile else "mmp-market-tile"
    cards = []
    for row in rows:
        change = row.get("change", "")
        direction = "up" if change.startswith("+") else "down" if change.startswith("-") else "flat"
        cards.append(
            f'<div class="mmp-card {direction} {cls}"><span>{_inline(row.get("region", ""))}</span>'
            f'<b>{_inline(row.get("market", ""))}</b><strong>{_inline(row.get("value", ""))}</strong>'
            f'<em>{_inline(change)}</em></div>'
        )
    return "".join(cards)



def _normalize_news_summaries(markdown: str) -> str:
    return re.sub(r"\n[ \t]+- 한글 요약:\s*", "<br>한글 요약: ", markdown)

def _news_excerpt(markdown: str, titles: list[str], per_section: int = 3) -> str:
    items: list[str] = []
    for title in titles:
        section = _section(markdown, title)
        if not section:
            continue
        for line in section.splitlines():
            if line.startswith("- "):
                items.append(line[2:].strip())
                if len(items) >= per_section * len(titles):
                    break
    return _compact_list(items[: per_section * len(titles)])



def _history_link() -> str:
    url = os.getenv("MMP_MARKET_HISTORY_URL", "https://mmorningbriefing.blogspot.com/p/market-history.html")
    return (
        f'<a class="mmp-history-link" href="{html.escape(url)}">'
        '<span><b>지금 시장, 역사적으로 어디쯤일까요?</b><small>장기 시장 지도에서 현재 위치를 확인</small></span><em class="mmp-history-arrow" aria-hidden="true">→</em></a>'
    )

def render_morning_html(markdown: str) -> str:
    title = _title(markdown, "우리의 모닝브리핑")
    report_date = _date_from_title(title)
    diagnosis = _section(markdown, "오늘의 한 줄 진단")
    diag_text = _bold_first(diagnosis, "분석 상태를 확인하세요.")
    regime = _bullet_value(diagnosis, "시장 국면")
    reason = _bullet_value(diagnosis, "판단 근거")
    market_rows = _market_rows(markdown)
    confidence_match = re.search(r"종합 확신도:\s*\*\*(.+?)\*\*", markdown)
    confidence = confidence_match.group(1).strip() if confidence_match else "UNKNOWN"
    basis_match = re.search(r"기준 시각:\s*\*\*(.+?)\*\*", markdown)
    basis = basis_match.group(1).strip() if basis_match else ""

    calendar = _section(markdown, "주요 일정 캘린더")
    core = _section(markdown, "핵심 동인")
    committee = _section(markdown, "오늘의 운용회의")
    scenario = _section(markdown, "기간별 시나리오")
    korea = _section(markdown, "KOSPI·KOSDAQ과 국내 전달경로")
    watch = _section(markdown, "확인할 데이터")
    invalidation = _section(markdown, "판단 무효화 조건")

    body = _normalize_news_summaries(_strip_h1(markdown))
    desktop = (
        '<div class="mmp-desktop">'
        '<header class="mmp-desktop-hero"><div><div class="mmp-eyebrow">MARKET MORNING · INVESTMENT DESK</div>'
        f'<h1>{_inline(title)}</h1><div class="mmp-hero-meta">{_inline(" · ".join(x for x in [report_date, basis] if x))}</div></div>'
        f'<div class="mmp-hero-badge"><small>OVERALL CONFIDENCE</small><strong>{_inline(confidence)}</strong></div></header>'
        '<div class="mmp-desk-shell"><div class="mmp-desk-grid">'
        f'<section class="mmp-panel mmp-span-12 mmp-desk-view"><div class="mmp-section-label">TODAY\'S DESK VIEW</div><strong>{_inline(diag_text)}</strong><div class="mmp-diagnosis-detail"><b>시장 국면:</b> {_inline(regime)}</div><div class="mmp-diagnosis-detail"><b>판단 근거:</b> {_inline(reason)}</div></section>'
        f'<section class="mmp-panel mmp-span-12 mmp-news-lead"><div class="mmp-section-label">TOP NEWS</div><h2>주요 언론사 기사</h2>{_news_excerpt(markdown,["주요 언론사 기사","주요 해외 언론사 기사","주요 국내 언론사 기사"],2)}</section>'
        f'<section id="mmp-event-calendar" class="mmp-panel mmp-span-12 mmp-event-calendar-source"><div class="mmp-section-label">MARKET EVENT CALENDAR</div><h2>주요 일정 캘린더</h2>{_markdown(calendar)}</section>'
        f'<section class="mmp-panel mmp-span-12"><div class="mmp-section-label">OVERNIGHT MARKET MONITOR</div><div class="mmp-market-tiles mmp-grid">{_market_tiles(market_rows)}</div>{_history_link()}</section>'
        f'<section class="mmp-panel mmp-span-7"><div class="mmp-section-label">CORE DRIVERS</div><h2>핵심 동인</h2>{_markdown(core)}</section>'
        f'<section class="mmp-panel mmp-span-5"><div class="mmp-section-label">KOREA TRANSMISSION</div><h2>국내 전달경로</h2>{_markdown(korea)}</section>'
        f'<section class="mmp-panel mmp-span-6"><div class="mmp-section-label">INVESTMENT COMMITTEE</div><h2>오늘의 운용회의</h2>{_markdown(committee)}</section>'
        f'<section class="mmp-panel mmp-span-6"><div class="mmp-section-label">SCENARIO MATRIX</div><h2>기간별 시나리오</h2>{_markdown(scenario)}</section>'
        f'<section class="mmp-panel mmp-span-6"><div class="mmp-section-label">DATA TO WATCH</div><h2>확인할 데이터</h2>{_markdown(watch)}</section>'
        f'<section class="mmp-panel mmp-span-6"><div class="mmp-section-label">INVALIDATION</div><h2>판단 무효화 조건</h2>{_markdown(invalidation)}</section>'
        '</div>'
        f'<section class="mmp-detailed"><h2>상세 리서치</h2>{_markdown(body)}</section></div></div>'
    )

    mobile_details = []
    skip = {"오늘의 한 줄 진단", "밤사이 시장 계기판"}
    default_open = {"주요 일정 캘린더", "주요 해외 언론사 기사", "주요 국내 언론사 기사", "핵심 동인", "기간별 시나리오"}
    for section_title, section_body in _sections(markdown):
        if section_title in skip or section_title == "주요 일정 캘린더":
            continue
        mobile_details.append(_details(section_title, section_body, section_title in default_open))
    mobile = (
        '<div class="mmp-mobile"><header class="mmp-mobile-hero"><div class="mmp-eyebrow">MORNING BRIEF</div>'
        f'<h1>{_inline(title)}</h1><div class="mmp-mobile-meta">{_inline(" · ".join(x for x in [basis, "CONFIDENCE " + confidence] if x))}</div></header>'
        '<div class="mmp-mobile-body">'
        f'<section class="mmp-mobile-card mmp-mobile-diagnosis"><h2>오늘 핵심</h2><strong>{_inline(diag_text)}</strong><div class="mmp-mobile-footnote">시장 국면: {_inline(regime)}<br>판단 근거: {_inline(reason)}</div></section>'
        f'<section class="mmp-mobile-card"><h2>밤사이 시장</h2><div class="mmp-mobile-scroll">{_market_tiles(market_rows, mobile=True)}</div>{_history_link()}</section>'
        f'<section id="mmp-mobile-event-calendar" class="mmp-mobile-card mmp-mobile-event-calendar mmp-event-calendar-source"><h2>주요 일정</h2>{_markdown(calendar)}</section>'
        f'<section class="mmp-mobile-card mmp-mobile-news"><h2>주요 뉴스 빠르게 보기</h2>{_news_excerpt(markdown,["주요 언론사 기사","주요 해외 언론사 기사","주요 국내 언론사 기사"],2)}</section>'
        f'<section class="mmp-mobile-card"><h2>오늘 확인할 것</h2>{_compact_list(_list_items(watch,5))}</section>'
        + ''.join(mobile_details)
        + '</div></div>'
    )
    return _responsive_css() + f'<article class="mmp-responsive mmp-morning-responsive">{desktop}{mobile}</article>'


def _closing_index_rows(markdown: str) -> list[dict[str, str]]:
    rows = _extract_table_rows(_section(markdown, "국내 시장 종가"), 3)
    result = []
    for cells in rows[1:]:
        if len(cells) >= 3:
            result.append({"region": "국내", "market": cells[0], "value": cells[1], "change": cells[2], "session": "CLOSE", "asof": ""})
    return result


def render_closing_html(markdown: str) -> str:
    title = _title(markdown, "우리의 장마감 리뷰")
    report_date = _date_from_title(title)
    diagnosis = _section(markdown, "오늘의 한 줄 진단")
    diag_text = _bold_first(diagnosis, "장마감 분석을 확인하세요.")
    confidence_match = re.search(r"종합 확신도:\s*\*\*(.+?)\*\*", markdown)
    confidence = confidence_match.group(1).strip() if confidence_match else "UNKNOWN"
    basis_match = re.search(r"기준 시각:\s*\*\*(.+?)\*\*", markdown)
    basis = basis_match.group(1).strip() if basis_match else ""
    indices = _closing_index_rows(markdown)
    facts = _section(markdown, "사실")
    interpretation = _section(markdown, "해석")
    hypothesis = _section(markdown, "가설")
    morning_score = _section(markdown, "아침 전망 채점")
    mi = _section(markdown, "우리 인사이트 일일 검증")
    carry = _section(markdown, "다음 거래일로 넘길 확인 과제")
    body = _strip_h1(markdown)

    desktop = (
        '<div class="mmp-desktop"><header class="mmp-desktop-hero"><div><div class="mmp-eyebrow">MARKET CLOSE · REVIEW DESK</div>'
        f'<h1>{_inline(title)}</h1><div class="mmp-hero-meta">{_inline(" · ".join(x for x in [report_date,basis] if x))}</div></div>'
        f'<div class="mmp-hero-badge"><small>OVERALL CONFIDENCE</small><strong>{_inline(confidence)}</strong></div></header>'
        '<div class="mmp-desk-shell"><div class="mmp-desk-grid">'
        f'<section class="mmp-panel mmp-span-12 mmp-desk-view"><div class="mmp-section-label">CLOSING DESK VIEW</div><strong>{_inline(diag_text)}</strong></section>'
        f'<section class="mmp-panel mmp-span-12"><div class="mmp-section-label">KOREA CLOSE</div><div class="mmp-market-tiles">{_market_tiles(indices)}</div></section>'
        f'<section class="mmp-panel mmp-span-4"><div class="mmp-section-label">FACT</div><h2>사실</h2>{_markdown(facts)}</section>'
        f'<section class="mmp-panel mmp-span-4"><div class="mmp-section-label">INTERPRETATION</div><h2>해석</h2>{_markdown(interpretation)}</section>'
        f'<section class="mmp-panel mmp-span-4"><div class="mmp-section-label">HYPOTHESIS</div><h2>가설</h2>{_markdown(hypothesis)}</section>'
        f'<section class="mmp-panel mmp-span-6"><div class="mmp-section-label">MORNING SCORECARD</div><h2>아침 전망 채점</h2>{_markdown(morning_score)}</section>'
        f'<section class="mmp-panel mmp-span-6"><div class="mmp-section-label">MI DAILY VALIDATION</div><h2>우리 인사이트 검증</h2>{_markdown(mi)}</section>'
        f'<section class="mmp-panel mmp-span-12"><div class="mmp-section-label">NEXT SESSION</div><h2>다음 거래일 확인 과제</h2>{_markdown(carry)}</section>'
        '</div>'
        f'<section class="mmp-detailed"><h2>상세 장마감 리포트</h2>{_markdown(body)}</section></div></div>'
    )
    details = []
    for section_title, section_body in _sections(markdown):
        if section_title in {"오늘의 한 줄 진단", "국내 시장 종가"}:
            continue
        details.append(_details(section_title, section_body, section_title in {"사실", "해석", "아침 전망 채점"}))
    mobile = (
        '<div class="mmp-mobile"><header class="mmp-mobile-hero"><div class="mmp-eyebrow">CLOSING REVIEW</div>'
        f'<h1>{_inline(title)}</h1><div class="mmp-mobile-meta">{_inline(" · ".join(x for x in [basis,"CONFIDENCE "+confidence] if x))}</div></header><div class="mmp-mobile-body">'
        f'<section class="mmp-mobile-card mmp-mobile-diagnosis"><h2>오늘 마감 핵심</h2><strong>{_inline(diag_text)}</strong></section>'
        f'<section class="mmp-mobile-card"><h2>국내 종가</h2><div class="mmp-mobile-scroll">{_market_tiles(indices,mobile=True)}</div></section>'
        f'<section class="mmp-mobile-card"><h2>다음 거래일 체크</h2>{_compact_list(_list_items(carry,5))}</section>'
        + ''.join(details) + '</div></div>'
    )
    return _responsive_css() + f'<article class="mmp-responsive mmp-closing-responsive">{desktop}{mobile}</article>'


def _youtube_card_sections(markdown: str) -> list[tuple[str, str]]:
    return [(title, body) for title, body in _sections(markdown) if re.match(r"^\d+\.\s+", title)]


def render_youtube_digest_html(markdown: str) -> str:
    title = _title(markdown, "시장 관점 카드")
    report_date = _date_from_title(title)
    card_sections = _youtube_card_sections(markdown)
    intro_lines = _list_items(_strip_h1(markdown), 4)
    card_html = ''.join(
        f'<section class="mmp-panel mmp-span-6"><div class="mmp-section-label">MARKET VIEW CARD</div><h2>{html.escape(section_title)}</h2>{_markdown(body)}</section>'
        for section_title, body in card_sections
    ) or '<section class="mmp-panel mmp-span-12"><div class="mmp-empty">오늘 게시 기준을 통과한 카드가 없습니다.</div></section>'
    desktop = (
        '<div class="mmp-desktop"><header class="mmp-desktop-hero"><div><div class="mmp-eyebrow">YOUTUBE · MARKET VIEW DESK</div>'
        f'<h1>{_inline(title)}</h1><div class="mmp-hero-meta">{_inline(report_date)}</div></div><div class="mmp-hero-badge"><small>RESEARCH MODE</small><strong>VERIFY FIRST</strong></div></header>'
        '<div class="mmp-desk-shell">'
        f'<section class="mmp-panel"><div class="mmp-section-label">POLICY</div>{_compact_list(intro_lines)}</section>'
        f'<div class="mmp-desk-grid" style="margin-top:12px">{card_html}</div>'
        f'<section class="mmp-detailed"><h2>전체 관점 카드</h2>{_markdown(_strip_h1(markdown))}</section></div></div>'
    )
    details = []
    for section_title, section_body in _sections(markdown):
        details.append(_details(section_title, section_body, bool(re.match(r"^[12]\.\s+", section_title))))
    mobile = (
        '<div class="mmp-mobile"><header class="mmp-mobile-hero"><div class="mmp-eyebrow">MARKET VIEW CARDS</div>'
        f'<h1>{_inline(title)}</h1><div class="mmp-mobile-meta">출처 주장과 검증 결과를 분리해 봅니다.</div></header><div class="mmp-mobile-body">'
        f'<section class="mmp-mobile-card"><h2>읽는 법</h2>{_compact_list(intro_lines)}</section>' + ''.join(details) + '</div></div>'
    )
    return _responsive_css() + f'<article class="mmp-responsive mmp-youtube-responsive">{desktop}{mobile}</article>'
