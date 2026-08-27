#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "ap": ROOT / "youtube_sources/ap_investment/source",
    "chesley": ROOT / "youtube_sources/chesley_investment/transcripts",
    "kpunch": ROOT / "youtube_sources/kpunch/videos",
    "plainbagel": ROOT / "youtube_sources/plainbagel/videos",
}
OUT_JSON = ROOT / "insight/cross_channel_insight_review.json"
OUT_MD = ROOT / "insight/cross_channel_insight_review.md"

# Two or more groups must match. This deliberately favors precision over recall.
THEMES = {
    "KP-MON-001": [["RP", "환매조건부", "repo purchase"], ["유동성", "채권", "liquidity", "bond"], ["시장.*신호", "도덕적 해이", "신용", "market signal", "moral hazard", "credit"]],
    "KP-MON-002": [["M2", "통화량", "money supply"], ["물가", "인플레이션", "구매력", "inflation", "purchasing power"], ["자산.*가격", "통화.*가치", "asset price", "currency value"]],
    "KP-EQT-001": [["환율", "원화", "달러", "exchange rate", "dollar"], ["주가", "코스피", "수익률", "stock price", "return"], ["실질", "구매력", "물가", "real return", "purchasing power", "inflation"]],
    "KP-FX-001": [["환율", "원달러", "원/달러", "exchange rate", "currency"], ["외국인", "자금.*유출", "금리차", "capital flow", "rate differential"], ["정책.*신뢰", "외환보유", "policy credibility", "foreign reserve"]],
    "KP-HOU-001": [["금리.*인하", "기준금리", "rate cut", "policy rate"], ["가계부채", "집값", "부동산", "household debt", "house price", "housing"], ["환율", "내수", "exchange rate", "domestic demand"]],
    "KP-RATE-001": [["장기.*금리", "10년물", "국채.*금리", "long-term rate", "10-year", "bond yield"], ["기준금리.*인하", "금리.*인하", "rate cut"], ["국채.*발행", "재정.*적자", "기간.*프리미엄", "bond issuance", "fiscal deficit", "term premium"]],
    "KP-FIS-001": [["재정.*적자", "적자.*재정", "국가.*부채", "fiscal deficit", "government debt"], ["국채.*발행", "국채.*금리", "bond issuance", "bond yield"], ["환율", "재정.*지출", "exchange rate", "government spending"]],
    "KP-DEM-001": [["고령화", "생산연령", "베이비부머", "aging", "working-age", "baby boomer"], ["잠재.*성장", "저성장", "복지.*지출", "potential growth", "welfare spending"], ["재정", "부채", "세입", "fiscal", "debt", "tax revenue"]],
    "KP-TRADE-001": [["원화.*약세", "환율.*상승", "weaker currency", "currency depreciation"], ["수입.*물가", "원자재.*가격", "에너지.*가격", "import price", "commodity price", "energy price"], ["기업.*마진", "내수", "수출", "margin", "domestic demand", "export"]],
    "KP-EQT-002": [["코스피", "한국.*증시", "국내.*증시", "Korean stock", "Korea.*market"], ["외국인", "반도체", "삼성전자", "foreign investor", "semiconductor", "Samsung"], ["환율", "실물.*경제", "정책.*수급", "exchange rate", "real economy"]],
    "KP-HOU-002": [["부동산", "집값", "주택", "real estate", "house price", "housing"], ["가계부채", "PF", "프로젝트.*파이낸싱", "household debt", "project finance"], ["규제.*완화", "지역.*격차", "미분양", "deregulation", "regional gap", "unsold"]],
    "KP-CHN-001": [["중국", "China"], ["부동산", "디플레", "내수", "real estate", "deflation", "domestic demand"], ["외국인.*투자", "FDI", "한국.*수출", "foreign investment", "Korean export"]],
    "KP-AI-001": [["AI", "인공지능", "artificial intelligence"], ["데이터센터", "전력", "반도체", "HBM", "GPU", "data center", "power", "semiconductor"], ["설비.*투자", "CAPEX", "현금흐름", "capital expenditure", "cash flow"]],
}


def clean_vtt(path: Path) -> str:
    seen, out = set(), []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        line = re.sub(r"^align:.*$", "", line).strip()
        if line and line not in seen:
            seen.add(line)
            out.append(line)
    return " ".join(out)


def metadata() -> tuple[dict[str, dict], dict[str, str], dict[str, dict]]:
    kp = {}
    for line in (ROOT / "youtube_sources/kpunch/video_metadata.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            kp[item["video_id"]] = item
    ch = {}
    for name in ("videos_playlist.json", "streams_playlist.json"):
        data = json.loads((ROOT / "youtube_sources/chesley_investment/inventory" / name).read_text(encoding="utf-8"))
        for item in data.get("entries", []):
            if item and item.get("id"):
                ch[item["id"]] = item.get("title") or item["id"]
    pb = {}
    for line in (ROOT / "youtube_sources/plainbagel/video_metadata.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            pb[item["video_id"]] = item
    return kp, ch, pb


def records():
    kp_meta, ch_titles, pb_meta = metadata()
    seen = set()
    for source, root in SOURCES.items():
        paths = root.rglob("*.txt") if source == "chesley" else root.rglob("*.vtt")
        for path in paths:
            # kpunch and AP often contain original + normalized variants; retain one per video.
            if source == "kpunch" and path.name.endswith("ko-orig.vtt"):
                continue
            stem = path.name.split(".")[0]
            if source in {"kpunch", "plainbagel"}:
                video_id = path.parent.name
            elif source == "chesley":
                video_id = path.stem
            else:
                video_id = stem.split("_", 1)[-1]
            key = (source, video_id)
            if key in seen:
                continue
            seen.add(key)
            date_match = re.match(r"(\d{8})_", stem)
            text = path.read_text(encoding="utf-8", errors="ignore") if source == "chesley" else clean_vtt(path)
            if source in {"kpunch", "plainbagel"}:
                meta = (kp_meta if source == "kpunch" else pb_meta).get(video_id, {})
                title, date = meta.get("title", video_id), meta.get("upload_date")
            elif source == "chesley":
                title, date = ch_titles.get(video_id, video_id), None
            else:
                title, date = video_id, date_match.group(1) if date_match else None
            yield source, video_id, title, date, text


def match(text: str, groups: list[list[str]]) -> tuple[int, list[re.Match]]:
    # Require concepts to co-occur locally. Long livestreams otherwise create
    # false matches from unrelated words spoken tens of minutes apart.
    anchors = []
    for pattern in groups[0]:
        anchors.extend(re.finditer(pattern, text, re.I))
    best: list[re.Match] = []
    for anchor in anchors:
        left, right = max(0, anchor.start() - 500), min(len(text), anchor.end() + 500)
        window = text[left:right]
        local = [anchor]
        for group in groups[1:]:
            found = next((re.search(pattern, window, re.I) for pattern in group if re.search(pattern, window, re.I)), None)
            if found:
                # Translate window-relative offsets for a coherent snippet.
                found = re.search(found.re.pattern, text[left:right], re.I)
                local.append(found)
        if len(local) > len(best):
            # snippet() only needs the anchor span; window matches merely score.
            best = [anchor] * len(local)
        if len(best) == len(groups):
            break
    return len(best), best


def snippet(text: str, hits: list[re.Match], radius: int = 100) -> str:
    if not hits:
        return ""
    start = max(0, hits[0].start() - radius)
    end = min(len(text), hits[0].end() + 350)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def main() -> None:
    claims = {item["claim_id"]: item for item in json.loads((ROOT / "config/kpunch_insight_claims.json").read_text(encoding="utf-8"))["claims"]}
    ledger = json.loads((ROOT / "insight/kpunch_insight_ledger.json").read_text(encoding="utf-8"))
    validation = {item["claim_id"]: item for item in ledger["claims"]}
    docs = defaultdict(lambda: defaultdict(list))
    totals = defaultdict(int)
    for source, video_id, title, date, text in records():
        totals[source] += 1
        for claim_id, groups in THEMES.items():
            score, hits = match(text, groups)
            if score >= 2:
                docs[claim_id][source].append({
                    "video_id": video_id, "title": title, "date": date, "score": score,
                    "url": f"https://www.youtube.com/watch?v={video_id}", "snippet": snippet(text, hits),
                })
    results = []
    for claim_id, claim in claims.items():
        per_source = {}
        for source in SOURCES:
            matches = docs[claim_id][source]
            matches.sort(key=lambda x: (x["score"], x.get("date") or ""), reverse=True)
            per_source[source] = {"matched_documents": len(matches), "examples": matches[:3]}
        independent = sum(per_source[s]["matched_documents"] > 0 for s in SOURCES)
        objective = validation[claim_id]["validation_status"]
        evidence_grade = "B" if independent >= 3 and objective == "TRACKABLE" else "C" if independent >= 2 and objective in {"TRACKABLE", "PARTIAL"} else "D"
        results.append({
            "claim_id": claim_id, "theme": claim["theme"], "claim": claim["claim"],
            "channel_coverage": independent, "objective_validation": objective,
            "evidence_grade": evidence_grade, "sources": per_source,
            "review": "채널 합의는 존재하지만 인과의 진위를 증명하지 않는다. 보유 지표와 시계열·가격 확인이 필요하다." if independent >= 2 else "다른 채널의 독립 반복 근거가 약하다. 단일 관점으로 유지한다.",
        })
    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Keyword-group retrieval across full local transcript corpus; channel agreement is not treated as factual validation.",
        "document_totals": dict(totals),
        "grades": {"B": "3개 이상 채널 반복 + 객관지표 TRACKABLE", "C": "2개 이상 채널 반복 + 일부 객관검증 가능", "D": "교차 반복 또는 객관검증 부족"},
        "claims": results,
    }
    OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# AP·체슬리·박종훈·The Plain Bagel 투자 인사이트 교차검토", "",
        f"- 생성 시각(UTC): {output['generated_at_utc']}",
        f"- 분석 문서: AP {totals['ap']:,}개, 체슬리 {totals['chesley']:,}개, 박종훈 {totals['kpunch']:,}개, The Plain Bagel {totals['plainbagel']:,}개", "",
        "## 판정 원칙", "",
        "- 채널 간 같은 주장의 반복은 독립적인 사실 검증이 아니라 추가 검증 우선순위다.",
        "- B는 강한 매매 신호가 아니라 보유 데이터로 검증 가능한 공통 가설이라는 뜻이다.",
        "- 자막 자동생성 오류, AP 제목 메타데이터 부재, 키워드 검색의 문맥 오탐 가능성을 감안해야 한다.", "",
        "## 핵심 검토 결론", "",
        "- 네 채널은 유동성·금리·환율·이익·수급을 함께 봐야 한다는 분석 틀에서는 대체로 겹친다.",
        "- 가장 중요한 충돌은 `KP-MON-002`다. 박종훈은 상대적 통화량 증가를 원화 약세의 핵심 설명으로 강조하지만, 체슬리 자료에는 통화량 하나로 환율을 예측할 수 없고 미국의 통화팽창 뒤에도 달러가 강해졌다는 명시적 반례가 있다. 따라서 이 주장은 금리차·위험회피·경상수지·자금흐름을 통제한 조건부 가설로만 유지한다.",
        "- AP 자료는 단기 수급·테마·진입 시점, 체슬리는 기업이익·밸류에이션·시장 국면, 박종훈은 구조적 거시 위험, The Plain Bagel은 금융 개념·역사적 사례·과도한 단순화에 대한 반론에 상대적으로 강하다. 시간축이 달라 방향 전망이 달라도 곧바로 모순은 아니다.",
        "- 이번 검토만으로 `INSIGHT.md`의 활성 원칙을 추가하거나 매매 규칙을 바꾸지 않는다. B·C 항목은 시장 데이터로 후속 검증하고 D 항목은 데이터 확보 전 `UNKNOWN`으로 둔다.", "",
        "## 요약", "",
        "|등급|주장|주제|채널 수|객관검증|AP/체슬리/박종훈/Plain Bagel 문서 수|", "|---|---|---|---:|---|---:|",
    ]
    for item in results:
        counts = "/".join(str(item["sources"][s]["matched_documents"]) for s in ("ap", "chesley", "kpunch", "plainbagel"))
        lines.append(f"|{item['evidence_grade']}|`{item['claim_id']}`|{item['theme']}|{item['channel_coverage']}|{item['objective_validation']}|{counts}|")
    for item in results:
        lines.extend(["", f"## {item['claim_id']} · {item['theme']} · {item['evidence_grade']}", "", item["claim"], "", f"검토: {item['review']}", ""])
        for source in ("ap", "chesley", "kpunch", "plainbagel"):
            info = item["sources"][source]
            lines.append(f"### {source.upper()} ({info['matched_documents']:,}개 후보)")
            lines.append("")
            for ex in info["examples"]:
                label = ex["title"] if source != "ap" else f"{ex.get('date') or '날짜 미상'} · {ex['video_id']}"
                lines.append(f"- [{label}]({ex['url']}): {ex['snippet']}")
            if not info["examples"]:
                lines.append("- 교차 근거 후보 없음")
            lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT_JSON), "markdown": str(OUT_MD), "documents": dict(totals)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
