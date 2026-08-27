from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path

from .expert_historical_corpus import load_inventory, parse_transcript


SIGNALS = {
    "valuation": ("밸류에이션", "적정주가", "저평가", "고평가", "비싸", "싸게", "멀티플", "per", "pbr"),
    "earnings": ("이익", "실적", "영업이익", "순이익", "eps", "매출", "마진", "추정치"),
    "rates_liquidity": ("금리", "유동성", "통화량", "기준금리", "할인율", "긴축", "완화", "양적"),
    "inflation": ("인플레이션", "물가", "소비자물가", "생산자물가", "디플레이션"),
    "fx": ("환율", "달러", "원화", "엔화", "위안", "외환"),
    "cycle": ("사이클", "경기침체", "경기회복", "선행지표", "재고", "수요", "공급"),
    "policy": ("연준", "fed", "재무부", "정부", "정책", "규제", "관세", "재정"),
    "positioning": ("수급", "외국인", "기관", "공매도", "포지션", "쏠림", "심리"),
    "risk": ("리스크", "위험", "손절", "반대", "틀릴", "무너지", "주의", "변동성"),
}
REASONING = ("때문", "따라서", "그러면", "그래서", "결국", "조건", "전제", "경우", "반면", "하지만")
ACTION = ("사야", "팔아", "매수", "매도", "투자", "비중", "기다", "확인", "판단", "전략")
FORECAST = ("전망", "예상", "가능성", "오를", "내릴", "상승", "하락", "회복", "악화")
EXCLUDE = ("구독", "좋아요", "알림", "댓글", "시청해", "광고", "협찬")


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    expert_id: str
    video_id: str
    published_at: str | None
    title: str | None
    evidence_tier: str
    sentence_start: int
    sentence_end: int
    score: int
    topics: list[str]
    text: str
    source_path: str
    text_sha256: str


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|(?<=다)\s+(?=[가-힣A-Z0-9])", normalized)
    return [x.strip() for x in parts if len(x.strip()) >= 10]


def score_sentence(sentence: str) -> tuple[int, list[str]]:
    lower = sentence.lower()
    if any(x in lower for x in EXCLUDE):
        return 0, []
    topics = [name for name, terms in SIGNALS.items() if any(term in lower for term in terms)]
    score = min(4, len(topics) * 2)
    score += 2 if any(x in lower for x in REASONING) else 0
    score += 2 if any(x in lower for x in ACTION) else 0
    score += 2 if any(x in lower for x in FORECAST) else 0
    score += 1 if re.search(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|조|억|원|달러|배)", lower) else 0
    score += 1 if any(x in lower for x in ("아니", "반대", "예외", "틀리", "무너지")) else 0
    return score, topics


def extract_candidates(expert_id: str, item, threshold: int = 6, context: int = 1) -> list[Candidate]:
    parsed = parse_transcript(item.subtitle_path)
    sentences = split_sentences(parsed["plain_text"])
    selected: list[tuple[int, int, int, list[str]]] = []
    for index, sentence in enumerate(sentences):
        score, topics = score_sentence(sentence)
        if score >= threshold:
            selected.append((max(0, index - context), min(len(sentences), index + context + 1), score, topics))
    merged: list[tuple[int, int, int, set[str]]] = []
    for start, end, score, topics in selected:
        if merged and start <= merged[-1][1]:
            old_start, old_end, old_score, old_topics = merged[-1]
            merged[-1] = (old_start, max(old_end, end), max(old_score, score), old_topics | set(topics))
        else:
            merged.append((start, end, score, set(topics)))
    out: list[Candidate] = []
    for start, end, score, topics in merged:
        text = " ".join(sentences[start:end])[:4000]
        digest = sha256(text.encode("utf-8")).hexdigest()
        candidate_id = "EHC-" + sha256(f"{expert_id}|{item.video_id}|{start}|{digest}".encode()).hexdigest()[:20]
        out.append(Candidate(candidate_id, expert_id, item.video_id, item.published_at, item.title,
                             item.evidence_tier, start, end, score, sorted(topics), text,
                             item.subtitle_path, digest))
    return out


def build_index(root: Path, expert_id: str, threshold: int, max_per_video: int) -> dict:
    state = root / "data/state/expert_corpus" / expert_id
    inventory = load_inventory(state / "inventory.jsonl")
    output = state / "local_candidates.jsonl"
    output_tmp = state / "local_candidates.jsonl.tmp"
    seen_hashes: set[str] = set()
    topic_counts: Counter[str] = Counter()
    candidate_count = duplicate_count = videos_with_candidates = 0
    with output_tmp.open("w", encoding="utf-8") as fh:
        for item in sorted(inventory.values(), key=lambda x: (x.published_at or "", x.video_id)):
            rows = sorted(extract_candidates(expert_id, item, threshold), key=lambda x: (-x.score, x.sentence_start))[:max_per_video]
            kept = 0
            for row in rows:
                if row.text_sha256 in seen_hashes:
                    duplicate_count += 1
                    continue
                seen_hashes.add(row.text_sha256)
                fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
                candidate_count += 1
                kept += 1
                topic_counts.update(row.topics)
            videos_with_candidates += bool(kept)
    output_tmp.replace(output)
    summary = {
        "contract": "MMP_EXPERT_LOCAL_CANDIDATE_INDEX_V1",
        "expert_id": expert_id,
        "inventory_videos": len(inventory),
        "videos_with_candidates": videos_with_candidates,
        "candidate_count": candidate_count,
        "duplicate_candidates_removed": duplicate_count,
        "threshold": threshold,
        "max_candidates_per_video": max_per_video,
        "topic_counts": dict(topic_counts.most_common()),
        "codex_calls": 0,
    }
    (state / "local_candidate_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def compact_index(root: Path, expert_id: str, limit: int) -> dict:
    state = root / "data/state/expert_corpus" / expert_id
    source = state / "local_candidates.jsonl"
    groups: dict[tuple[str, str], dict] = {}
    total = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        total += 1
        month = str(row.get("published_at") or "UNKNOWN")[:7]
        topics = row.get("topics") or ["general"]
        for topic in topics:
            key = (month, topic)
            old = groups.get(key)
            rank = (int(row.get("score") or 0), len(row.get("text") or ""))
            old_rank = (int(old.get("score") or 0), len(old.get("text") or "")) if old else (-1, -1)
            if rank > old_rank:
                groups[key] = row
    unique = {row["candidate_id"]: row for row in groups.values()}
    rows = sorted(unique.values(), key=lambda x: (-int(x.get("score") or 0), x.get("published_at") or "", x["candidate_id"]))[:limit]
    queue = state / "codex_review_queue.jsonl"
    queue.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    summary = {
        "contract": "MMP_EXPERT_CODEX_REVIEW_QUEUE_V1",
        "expert_id": expert_id,
        "local_candidates": total,
        "month_topic_representatives": len(unique),
        "review_queue": len(rows),
        "estimated_codex_batches_at_5_each": (len(rows) + 4) // 5,
        "codex_calls_performed": 0,
    }
    (state / "codex_review_queue_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--expert", required=True)
    parser.add_argument("--threshold", type=int, default=6)
    parser.add_argument("--max-candidates-per-video", type=int, default=8)
    parser.add_argument("--representative-limit", type=int, default=0)
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    result = build_index(root, args.expert, args.threshold, args.max_candidates_per_video)
    if args.representative_limit:
        result["review_queue"] = compact_index(root, args.expert, args.representative_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
