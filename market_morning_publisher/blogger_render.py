from __future__ import annotations

import html
import os
import re


MARKET_ORDER = {
    "S&P 500": 0, "NASDAQ": 1, "PHLX Semiconductor": 2, "VIX": 3,
    "US 10Y yield": 4, "US Dollar Index": 5, "USD/KRW": 6,
    "WTI": 7, "Gold": 8, "EURO STOXX 50": 9, "DAX": 10, "FTSE 100": 11,
}


def _inline(text: str) -> str:
    value = html.escape(text.strip())
    value = re.sub(r"\[([^]]+)]\((https?://[^)]+)\)", r'<a href="\2" rel="noopener noreferrer" target="_blank">\1</a>', value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = value.replace("&lt;br&gt;", "<br>")
    return value


def _table(lines: list[str]) -> tuple[str, int]:
    rows: list[list[str]] = []
    consumed = 0
    for line in lines:
        if not line.strip().startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        consumed += 1
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return "", consumed
    head, *body = rows
    parts = ["<div class=\"mmp-table-wrap\"><table><thead><tr>"]
    parts.extend(f"<th>{_inline(cell)}</th>" for cell in head)
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts), consumed


def _markdown_blocks(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    list_open = False
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if line.startswith("|"):
            if list_open:
                parts.append("</ul>")
                list_open = False
            table, consumed = _table(lines[index:])
            parts.append(table)
            index += consumed
            continue
        match = re.match(r"^(#{2,4})\s+(.+)$", line)
        if match:
            if list_open:
                parts.append("</ul>")
                list_open = False
            level = len(match.group(1))
            parts.append(f"<h{level}>{_inline(match.group(2))}</h{level}>")
        elif line.startswith("- "):
            if not list_open:
                parts.append("<ul>")
                list_open = True
            parts.append(f"<li>{_inline(line[2:])}</li>")
        elif line.strip():
            if list_open:
                parts.append("</ul>")
                list_open = False
            parts.append(f"<p>{_inline(line)}</p>")
        index += 1
    if list_open:
        parts.append("</ul>")
    return "".join(parts)


def _section(markdown: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    return match.group(1).strip() if match else ""


def _market_rows(markdown: str) -> list[dict[str, str]]:
    section = _section(markdown, "밤사이 시장 계기판")
    table_lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 6:
            rows.append(dict(zip(("region", "market", "value", "change", "session", "asof"), cells[:6])))
    return sorted(rows, key=lambda row: MARKET_ORDER.get(row["market"], 99))


def _cards(rows: list[dict[str, str]]) -> str:
    cards = []
    for row in rows:
        change = row["change"]
        direction = "up" if change.startswith("+") else "down" if change.startswith("-") else "flat"
        session = "완료" if row["session"] == "COMPLETED" else "진행"
        cards.append(
            f'<div class="mmp-card {direction}"><div class="mmp-card-top"><span>{_inline(row["region"])}</span>'
            f'<em>{session}</em></div><h3>{_inline(row["market"])}</h3><div class="mmp-quote">'
            f'<strong>{_inline(row["value"])}</strong><b>{_inline(change)}</b></div>'
            f'<small>{_inline(row["asof"])}</small></div>'
        )
    return "".join(cards)


def render_blogger_html(markdown: str) -> str:
    """Render one semantic report into separate desktop and mobile responsive views."""
    from .responsive_publish import render_morning_html
    return render_morning_html(markdown)
