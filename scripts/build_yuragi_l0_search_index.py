#!/usr/bin/env python3
"""YuragiWiki L0: 検索用インデックス（search-index run）.

入力 = 現行 chunk run（units.jsonl + units/<unit>.jsonl）と raw 群ファイル。
産出（runs/<run_id>/）:
  search/posts.jsonl   — 全文投稿マスタ 1 投稿 1 行（unit 情報・著者・ISO 日時・60字スニペット・群ファイル参照）
  search/by-author.jsonl — 著者 → 投稿参照一覧
  search/by-date.jsonl   — 時系列全量（ISO 日時でソート）
  search/terms.jsonl     — 【…】表記（ゆらぎ用語習慣）→ 出現索引
  stats.json / run.json
日付の ISO 正規化は索引側の仕事（台帳本体はサイト別形式を保持する）。
スニペットは引用レベルの抜粋（原文全文は work に置かない則）。
"""
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW_ROOT = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki")
L0 = REPO / "work" / "yuragi" / "L0"
INDEX_DIR = REPO / "work" / "yuragi" / "index"
JST = timezone(timedelta(hours=9))
SNIPPET = 60

DATE_RE = re.compile(
    r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日)]?.*?(\d{1,2}):(\d{2})(?::(\d{2}))?$"
)
TERM_RE = re.compile(r"【([^】\n]{2,40})】")


def iso_date(raw: str):
    m = DATE_RE.match(raw.strip())
    if not m:
        return None, None
    y, mo, d, h, mi, s = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0), tzinfo=JST)
    except ValueError:
        return None, None
    return dt.isoformat(), int(dt.timestamp())


def main():
    ts = datetime.now().strftime("%Y%m%dT%H%M")
    run_id = f"{ts}_l0si"
    run_dir = L0 / "runs" / run_id
    (run_dir / "search").mkdir(parents=True, exist_ok=True)

    latest = (L0 / "latest.txt").read_text().strip()
    src_dir = L0 / "runs" / latest
    if not (src_dir / "units.jsonl").exists():
        raise SystemExit(f"latest.txt must point to a chunk run (units.jsonl missing in {latest})")
    units = [json.loads(l) for l in open(src_dir / "units.jsonl", encoding="utf-8")]
    units.sort(key=lambda u: u["unit_id"])

    posts_all = []
    authors = {}
    terms = {}
    no_date = 0
    for u in units:
        uid = u["unit_id"]
        unit_meta = {
            "unit_id": uid, "unit_title": u["title"], "source": u["source"], "url": u.get("url"),
        }
        unit_posts = [json.loads(l) for l in open(src_dir / "units" / f"{uid}.jsonl", encoding="utf-8")]
        # body text: per-post raw file (hatena) or unit raw file
        per_post_raw = all("raw_path" in p for p in unit_posts)
        text_cache = {}
        for p in unit_posts:
            rp = p.get("raw_path") if per_post_raw else u["raw_path"]
            if rp not in text_cache:
                text_cache[rp] = (RAW_ROOT / rp).read_bytes().decode("utf-8", errors="replace")  # raw 基準
            text = text_cache[rp]
            body = text[p["body_start"]:p["body_end"]].strip()
            iso, ep = iso_date(p["date"])
            if iso is None:
                no_date += 1
            snippet = " ".join(body[:SNIPPET].split())
            rec = {
                "ref": f"{uid}:{p['post_no']}",
                **unit_meta,
                "post_no": p["post_no"],
                "author": p["author"],
                "date_raw": p["date"],
                "date_iso": iso,
                "epoch": ep,
                "chars": p["chars"],
                "snippet": snippet,
                "raw_group_path": None,
                "body_start": p["body_start"],
                "body_end": p["body_end"],
            }
            posts_all.append(rec)
            key = p["author"].strip()
            authors.setdefault(key, []).append(rec["ref"])
            for t in TERM_RE.findall(body):
                tn = " ".join(t.split())
                if tn:
                    e = terms.setdefault(tn, {"count": 0, "refs": [], "units": set()})
                    e["count"] += 1
                    if len(e["refs"]) < 60:
                        e["refs"].append(rec["ref"])
                    e["units"].add(uid)

    # group file refs (from chunk run)
    group_of = {}
    for u in units:
        uid = u["unit_id"]
        for l in open(src_dir / "chunks" / f"{uid}.jsonl", encoding="utf-8"):
            c = json.loads(l)
            for n in range(c["post_range"][0], c["post_range"][1] + 1):
                group_of[f"{uid}:{n}"] = (c["group_id"], c["raw_group_path"])
    for rec in posts_all:
        g = group_of.get(rec["ref"])
        if g:
            rec["group_id"], rec["raw_group_path"] = g[0], g[1]

    posts_all.sort(key=lambda r: (r["unit_id"], r["post_no"]))
    with open(run_dir / "search" / "posts.jsonl", "w", encoding="utf-8") as f:
        for r in posts_all:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(run_dir / "search" / "by-author.jsonl", "w", encoding="utf-8") as f:
        for a in sorted(authors, key=lambda k: -len(authors[k])):
            f.write(json.dumps({"author": a, "n": len(authors[a]), "refs": authors[a]}, ensure_ascii=False) + "\n")

    dated = sorted((r for r in posts_all if r["epoch"]), key=lambda r: r["epoch"])
    with open(run_dir / "search" / "by-date.jsonl", "w", encoding="utf-8") as f:
        for r in dated:
            f.write(json.dumps({
                "date_iso": r["date_iso"], "epoch": r["epoch"], "ref": r["ref"],
                "source": r["source"], "unit_id": r["unit_id"], "post_no": r["post_no"],
                "author": r["author"], "snippet": r["snippet"],
            }, ensure_ascii=False) + "\n")

    with open(run_dir / "search" / "terms.jsonl", "w", encoding="utf-8") as f:
        for t in sorted(terms, key=lambda k: -terms[k]["count"]):
            e = terms[t]
            f.write(json.dumps({"term": t, "count": e["count"], "units_touched": len(e["units"]),
                                "units": sorted(e["units"]), "refs": e["refs"]}, ensure_ascii=False) + "\n")

    total = {
        "derived_from_chunk_run": latest,
        "posts": len(posts_all),
        "authors": len(authors),
        "terms": len(terms),
        "term_occurrences": sum(e["count"] for e in terms.values()),
        "date_normalized": len(dated),
        "no_date_posts": no_date,
        "group_refs_resolved": sum(1 for r in posts_all if r["raw_group_path"]),
    }
    top_authors = [(a, len(authors[a])) for a in sorted(authors, key=lambda k: -len(authors[k]))[:20]]
    top_terms = [(t, terms[t]["count"]) for t in sorted(terms, key=lambda k: -terms[k]["count"])[:50]]
    with open(run_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump({"totals": total, "top_authors": top_authors, "top_terms": top_terms},
                  f, ensure_ascii=False, indent=2)

    run_meta = {
        "run_id": run_id, "wiki": "yuragi", "layer": "L0",
        "kind": "search-index（投稿マスタ・著者・時系列・【用語】索引）",
        "created": datetime.now(timezone.utc).isoformat(),
        "tool": "scripts/build_yuragi_l0_search_index.py",
        "params": {"snippet_chars": SNIPPET, "term_pattern": "【…】(2-40字)", "timezone": "JST"},
        "derived_from": {
            "l0_run": latest,
            "source_repo": "YuragiWiki (local Downloads/Code/YuragiWiki)",
            "raw_commit": __import__("subprocess").run(
                ["git", "-C", str(RAW_ROOT), "rev-parse", "HEAD"],
                capture_output=True, text=True).stdout.strip(),
        },
        "notes": "日付 ISO 正規化は索引側。スニペット 60 字は引用レベルの抜粋。无日期投稿（削除投稿）は by-date に含まれず posts に no_date で残る。",
        "stats": total,
    }
    with open(run_dir / "run.json", "w", encoding="utf-8") as f:
        json.dump(run_meta, f, ensure_ascii=False, indent=2)

    # latest.txt は本体チェーン（chunk run）のまま — 派生索引 run では更新しない
    idx_path = INDEX_DIR / "runs-index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    idx.setdefault("L0", {})[run_id] = {
        "path": "work/yuragi/L0/runs/" + run_id,
        "status": "complete", "wiki": "yuragi", "layer": "L0", "kind": "search-index",
        "created": run_meta["created"], "derived_from": run_meta["derived_from"], "stats": total,
    }
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"RUN {run_id}")
    print(json.dumps(total, ensure_ascii=False))


if __name__ == "__main__":
    main()
