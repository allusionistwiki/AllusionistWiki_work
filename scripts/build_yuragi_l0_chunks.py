#!/usr/bin/env python3
"""YuragiWiki L0: 掲示板データのチャンク化.

入力は YuragiWiki repo（private・raw はここにのみ置く）の raw/bbs 配下。
産出は work repo の work/yuragi/L0/runs/<run_id>/ に run として追記専用。
産出物には原文本文をコピーしない（著作権・work 則）。篇単位の台帳:
  units.jsonl        — 解析単位（篇）マニフェスト
  units/<unit>.jsonl — レス単位の観測記録（raw 内の char オフセットでアンカー）
  chunks/<unit>.jsonl — LLM 入力用チャンク（応答範囲）
アンカー規約: unit_id + post_no（スレ/トピックのレス番号が原生アンカー）。
"""
import json
import re
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

RAW_ROOT = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki")
RAW_BBS = RAW_ROOT / "raw" / "bbs"
REPO = Path(__file__).resolve().parent.parent
OUT_BASE = REPO / "work" / "yuragi" / "L0" / "runs"
INDEX_DIR = REPO / "work" / "yuragi" / "index"
CHAR_BUDGET = 12000

# jbbs:  "## 1 ：名前 ：2006/06/30(金) 16:50:56"
# mixi :  "## 1 ：名前 ：2005年11月02日 01:42"
HEADER_RE = re.compile(
    r"^## (\d+) ：(.*?) ：((?:\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日)]?.*?\d{1,2}:\d{2}(?::\d{2})?)?)\s*$"
)
DELETED_RE = re.compile(r"^<<.+>>$")
MISSING_GROUP_FILES = []
# 削除投稿は「## N ：<<妖精は口を噤んだ>> ：」で日付が無い（date は None になる）
DECLARED_RE = re.compile(r"【取得レス数 (\d+)")
THREAD_ID_RE = re.compile(r"【スレID (\d+)】")
THREAD_URL_RE = re.compile(r"【URL (\S+)】")
TOPIC_ID_RE = re.compile(r"【トピックID (\d+)】")
TOPIC_URL_RE = re.compile(r"【URL (\S+)】")
TOPIC_POSTER_RE = re.compile(r"【投稿者 (.+?)】")
TOPIC_DATE_RE = re.compile(r"【日時 (.+?)】")
TOPIC_COMMENTS_RE = re.compile(r"【コメント数 (\d+)】")

HATENA_HDR_RE = re.compile(
    r"^##\s+\[(\d+)\]\(/bbs/\d+/\d+\)：\s*(?:\[([^\]]*)\]\([^)]*\))?\s*(.*)$"
)
HATENA_DATE_RE = re.compile(r"\[!\[\]\(/images/res1\.gif\)返信\]\([^)]*\)｜(\S+ \d{2}:\d{2}:\d{2})")


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


def parse_posts(text: str):
    """-> list of {post_no, author, date, body_start, body_end, chars} (char offsets in text)"""
    lines = text.splitlines(keepends=True)
    offs = []
    acc = 0
    for ln in lines:
        offs.append(acc)
        acc += len(ln)
    heads = []
    for i, ln in enumerate(lines):
        m = HEADER_RE.match(ln.rstrip("\r\n"))
        if m:
            heads.append((i, m))
    posts = []
    for k, (i, m) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body_start = offs[i] + len(lines[i])
        body_end = offs[end - 1] + len(lines[end - 1]) if end > i + 1 else body_start
        body = text[body_start:body_end].strip()
        posts.append(
            {
                "post_no": int(m.group(1)),
                "author": m.group(2).strip(),
                "date": (m.group(3) or "").strip(),
                "body_start": body_start,
                "body_end": body_start + (body_end - body_start),
                "chars": len(body),
                "body_len_stripped": len(body),
            }
        )
    return posts


def group_filename(posts):
    a = posts[0]["post_no"]
    b = posts[-1]["post_no"]
    return f"p{a:04d}.md" if len(posts) == 1 else f"p{a:04d}-{b:04d}.md"


def make_chunks(unit_id: str, posts: list, budget: int, base_dir: str = None):
    """チャンク意味論（2026-11-11 ユーザー確定）:
    - 1 投稿 = 1 チャンク。同一投稿者の隣接連投は 1 群（group）に統合。
    - 削除投稿（<<…>> マーク・投稿者不明）は連結を断ち、単独チャンク。
    - 1 群が budget を超えるときのみ post 境界で parts に分割（同一 group_id を共有）。
    - 群の実体（本文ファイル）は raw 層 = YuragiWiki repo の posts/ にある（split_posts.py）。
      ここは台帳: 各チャンクに raw_group_path を書く（hatena は 1 ページ 1 投稿）。"""
    groups = []
    for p in posts:
        author = p["author"]
        deleted = bool(DELETED_RE.match(author))
        g = groups[-1] if groups else None
        if g and not deleted and not g["deleted"] and author == g["author"]:
            g["posts"].append(p)
        else:
            groups.append({"author": author, "deleted": deleted, "posts": [p]})

    chunks = []
    seq = 0
    gseq = 0
    for g in groups:
        gseq += 1
        group_id = f"{unit_id}#g{gseq:03d}"
        plist = g["posts"]
        group_chars = sum(p["chars"] for p in plist)
        parts = []
        cur, cur_chars = [], 0
        for p in plist:
            if cur and cur_chars + p["chars"] > budget:
                parts.append((cur, cur_chars))
                cur, cur_chars = [], 0
            cur.append(p)
            cur_chars += p["chars"]
        if cur:
            parts.append((cur, cur_chars))
        kind = "deleted" if g["deleted"] else ("chain" if len(plist) > 1 else "post")
        for k, (seg, ch) in enumerate(parts, 1):
            seq += 1
            if base_dir:
                # 参照は群の全体ファイル（parts はその中の窓: post_range でスライス）
                rgp = base_dir + "/" + group_filename(plist)
            else:
                rgp = seg[0].get("raw_path")
            rg_sha = None
            if rgp:
                fp = RAW_ROOT / rgp
                if fp.exists():
                    rg_sha = sha1_of(fp)
                else:
                    MISSING_GROUP_FILES.append(rgp)
            chunks.append(
                {
                    "chunk_id": f"{unit_id}#c{seq:03d}",
                    "group_id": group_id,
                    "part": k,
                    "parts_total": len(parts),
                    "unit_id": unit_id,
                    "seq": seq,
                    "kind": kind,
                    "author": g["author"],
                    "post_range": [seg[0]["post_no"], seg[-1]["post_no"]],
                    "n_posts": len(seg),
                    "chars": ch,
                    "group_chars": group_chars,
                    "raw_group_path": rgp,
                    "raw_group_sha1": rg_sha,
                }
            )
    return chunks


def git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def main():
    ts = datetime.now().strftime("%Y%m%dT%H%M")
    run_id = f"{ts}_l0c"
    run_dir = OUT_BASE / run_id
    (run_dir / "units").mkdir(parents=True, exist_ok=True)
    (run_dir / "chunks").mkdir(parents=True, exist_ok=True)

    raw_commit = git_head(RAW_ROOT)
    units = []
    stats = {"sources": {}, "post_chars_max": 0, "post_chars_max_unit": None}
    mismatches = []

    def register_unit(unit, unit_posts, declared):
        unit_id = unit["unit_id"]
        with open(run_dir / "units" / f"{unit_id}.jsonl", "w", encoding="utf-8") as f:
            for p in unit_posts:
                rec = {"unit_id": unit_id, **p}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        base_dir = None
        if unit.get("raw_path") and unit["raw_path"].endswith(".md"):
            base_dir = str(PurePosixPath(unit["raw_path"]).parent) + "/posts"
            unit["split_dir"] = base_dir
        chunks = make_chunks(unit_id, unit_posts, CHAR_BUDGET, base_dir=base_dir)
        with open(run_dir / "chunks" / f"{unit_id}.jsonl", "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        unit["n_posts"] = len(unit_posts)
        unit["declared_posts"] = declared
        unit["total_chars"] = sum(p["chars"] for p in unit_posts)
        dates = [p["date"] for p in unit_posts if p["date"]]
        unit["first_date"] = dates[0] if dates else None
        unit["last_date"] = dates[-1] if dates else None
        unit["n_chunks"] = len(chunks)
        unit["n_groups"] = len({c["group_id"] for c in chunks})
        unit["n_chain_groups"] = len({c["group_id"] for c in chunks if c["kind"] == "chain"})
        units.append(unit)
        if declared is not None and declared != len(unit_posts):
            mismatches.append({"unit_id": unit_id, "declared": declared, "parsed": len(unit_posts)})
        for p in unit_posts:
            if p["chars"] > stats["post_chars_max"]:
                stats["post_chars_max"] = p["chars"]
                stats["post_chars_max_unit"] = unit_id
        s = stats["sources"].setdefault(
            unit["source"], {"units": 0, "posts": 0, "chars": 0, "chunks": 0,
                             "groups": 0, "chain_groups": 0, "deleted_posts": 0, "split_groups": 0}
        )
        s["units"] += 1
        s["posts"] += len(unit_posts)
        s["chars"] += unit["total_chars"]
        s["chunks"] += len(chunks)
        s["groups"] += unit["n_groups"]
        s["chain_groups"] += unit["n_chain_groups"]
        s["deleted_posts"] += sum(1 for c in chunks if c["kind"] == "deleted")
        s["split_groups"] += len({c["group_id"] for c in chunks if c["parts_total"] > 1})

    # ---- jbbs ----
    jbbs_root = RAW_BBS / "jbbs" / "movie-7039"
    for d in sorted(p for p in jbbs_root.iterdir() if p.is_dir()):
        m = re.match(r"(\d+)_", d.name)
        if not m:
            continue
        n = int(m.group(1))
        thread_md = d / "Thread.md"
        text = thread_md.read_text(encoding="utf-8", errors="replace")
        posts = parse_posts(text)
        decl = DECLARED_RE.search(text)
        tid = THREAD_ID_RE.search(text)
        url = THREAD_URL_RE.search(text)
        title = text.splitlines()[0].lstrip("# ").strip() if text else d.name
        unit = {
            "unit_id": f"YJ-T{n:03d}",
            "source": "jbbs",
            "source_id": tid.group(1) if tid else d.name,
            "title": title,
            "url": url.group(1) if url else None,
            "raw_path": "raw/bbs/jbbs/movie-7039/" + d.name + "/Thread.md",
            "raw_sha1": sha1_of(thread_md),
        }
        register_unit(unit, posts, int(decl.group(1)) if decl else None)

    # ---- mixi ----
    mixi_root = RAW_BBS / "mixi" / "373088"
    topics = sorted(
        (d for d in mixi_root.iterdir() if d.is_dir()),
        key=lambda d: int(re.search(r"【トピックID (\d+)】", (d / "Topic.md").read_text(encoding="utf-8", errors="replace")).group(1)),
    )
    for i, d in enumerate(topics, 1):
        topic_md = (d / "Topic.md").read_text(encoding="utf-8", errors="replace")
        comment_files = sorted(d.glob("*_topic_comment.md"))
        if not comment_files:
            continue
        cf = comment_files[0]
        text = cf.read_text(encoding="utf-8", errors="replace")
        posts = parse_posts(text)
        tid = TOPIC_ID_RE.search(topic_md)
        url = TOPIC_URL_RE.search(topic_md)
        ncom = TOPIC_COMMENTS_RE.search(topic_md)
        unit = {
            "unit_id": f"YJ-M{i:02d}",
            "source": "mixi",
            "source_id": tid.group(1) if tid else d.name,
            "title": topic_md.splitlines()[0].lstrip("# ").strip(),
            "url": url.group(1) if url else None,
            "community_id": "373088",
            "raw_path": "raw/bbs/mixi/373088/" + d.name + "/" + cf.name,
            "raw_sha1": sha1_of(cf),
            "topic_meta_sha1": sha1_of(d / "Topic.md"),
        }
        register_unit(unit, posts, int(ncom.group(1)) if ncom else None)

    # ---- hatena flicker BBS（ポータル自前の掲示板・汎用スレッド bbs/1）----
    hat_md = RAW_BBS / "hatena_flicker" / "md"
    page_re = re.compile(r"^flicker\.g\.hatena\.ne\.jp_bbs_(\d+)_(\d+)_(\d+)\.md$")
    pages = {}
    for f in hat_md.iterdir():
        m = page_re.match(f.name)
        if not m:
            continue
        board, pno, stamp = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if board != 1:
            continue
        if pno not in pages or stamp > pages[pno][1]:
            pages[pno] = (f, stamp)
    hposts = []
    for pno in sorted(pages):
        f = pages[pno][0]
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        offs, acc = [], 0
        for ln in lines:
            offs.append(acc)
            acc += len(ln)
        hi = di = None
        hdr = author = title = date = None
        for i, ln in enumerate(lines):
            mm = HATENA_HDR_RE.match(ln.rstrip("\r\n"))
            if mm and hi is None:
                hi = i
                hdr = mm
            if hi is not None and di is None:
                dm = HATENA_DATE_RE.search(ln)
                if dm:
                    di = i
                    date = dm.group(1)
                    break
        if hi is None:
            continue
        body_start = offs[hi] + len(lines[hi])
        body_end = offs[di] if di is not None else len("".join(lines))
        body = "".join(lines[hi + 1 : di]).strip() if di is not None else "".join(lines[hi + 1 :]).strip()
        hposts.append(
            {
                "post_no": pno,
                "author": (hdr.group(2) or "").strip(),
                "date": date or "",
                "body_start": body_start,
                "body_end": body_start + (body_end - body_start),
                "chars": len(body),
                "body_len_stripped": len(body),
                "raw_path": "raw/bbs/hatena_flicker/md/" + f.name,
                "raw_sha1": sha1_of(f),
            }
        )
    if hposts:
        unit = {
            "unit_id": "YJ-H01",
            "source": "hatena_bbs",
            "source_id": "bbs/1",
            "title": "ゆらぎの神話 ポータル 掲示板 汎用スレッド",
            "url": "http://flicker.g.hatena.ne.jp/bbs/1",
            "raw_path": "raw/bbs/hatena_flicker/md/（1ページ1レス・units 側にページ別 raw_path/raw_sha1）",
            "raw_sha1": None,
        }
        # per-post raw paths for hatena (page-per-post)
        with open(run_dir / "units" / "YJ-H01.jsonl", "w", encoding="utf-8") as f:
            for p in hposts:
                f.write(json.dumps({"unit_id": "YJ-H01", **p}, ensure_ascii=False) + "\n")
        hchunks = make_chunks("YJ-H01", hposts, CHAR_BUDGET)
        with open(run_dir / "chunks" / "YJ-H01.jsonl", "w", encoding="utf-8") as f:
            for c in hchunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        unit["n_posts"] = len(hposts)
        unit["declared_posts"] = None
        unit["total_chars"] = sum(p["chars"] for p in hposts)
        unit["first_date"] = hposts[0]["date"]
        unit["last_date"] = hposts[-1]["date"]
        unit["n_chunks"] = len(hchunks)
        units.append(unit)
        s = stats["sources"].setdefault("hatena_bbs", {"units": 0, "posts": 0, "chars": 0, "chunks": 0,
                                                       "groups": 0, "chain_groups": 0, "deleted_posts": 0, "split_groups": 0})
        s["units"] += 1
        s["posts"] += len(hposts)
        s["chars"] += unit["total_chars"]
        s["chunks"] += len(hchunks)
        s["groups"] += len({c["group_id"] for c in hchunks})
        s["chain_groups"] += len({c["group_id"] for c in hchunks if c["kind"] == "chain"})
        s["deleted_posts"] += sum(1 for c in hchunks if c["kind"] == "deleted")
        s["split_groups"] += len({c["group_id"] for c in hchunks if c["parts_total"] > 1})
        unit["n_groups"] = len({c["group_id"] for c in hchunks})
        unit["n_chain_groups"] = len({c["group_id"] for c in hchunks if c["kind"] == "chain"})

    # ---- outputs ----
    units.sort(key=lambda u: u["unit_id"])
    with open(run_dir / "units.jsonl", "w", encoding="utf-8") as f:
        for u in units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")

    total = {
        "units": len(units),
        "posts": sum(s["posts"] for s in stats["sources"].values()),
        "chars": sum(s["chars"] for s in stats["sources"].values()),
        "chunks": sum(s["chunks"] for s in stats["sources"].values()),
        "groups": sum(s["groups"] for s in stats["sources"].values()),
        "chain_groups": sum(s["chain_groups"] for s in stats["sources"].values()),
        "count_mismatches": len(mismatches),
        "missing_group_files": len(MISSING_GROUP_FILES),
    }
    with open(run_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump({"sources": stats["sources"], "totals": total,
                   "post_chars_max": stats["post_chars_max"],
                   "post_chars_max_unit": stats["post_chars_max_unit"],
                   "count_mismatch_detail": mismatches[:50]}, f, ensure_ascii=False, indent=2)

    run_meta = {
        "run_id": run_id,
        "wiki": "yuragi",
        "layer": "L0",
        "kind": "bbs-chunking-v2（1 投稿 = 1 チャンク・同一投稿者の隣接連投は 1 群・群の実体は raw 層 posts/）",
        "created": datetime.now(timezone.utc).isoformat(),
        "tool": "scripts/build_yuragi_l0_chunks.py",
        "params": {"char_budget": CHAR_BUDGET},
        "raw_split_layer": "YuragiWiki repo tools/split_posts.py（raw/bbs/**/posts/・連投群ファイル・無損失連結検証付き）",
        "derived_from": {
            "source_repo": "YuragiWiki (local Downloads/Code/YuragiWiki)",
            "raw_commit": raw_commit,
            "raw_retrieved": "2026-10-12",
            "inputs": ["raw/bbs/jbbs/movie-7039/", "raw/bbs/mixi/373088/", "raw/bbs/hatena_flicker/md/ (bbs_1_* pages only)"],
        },
        "anchor_convention": "unit_id + post_no（スレ・トピックのレス番号が原生アンカー）。本文引用は units/<unit>.jsonl の body_start/body_end char オフセットで raw ファイルから切片",
        "stats": total,
    }
    with open(run_dir / "run.json", "w", encoding="utf-8") as f:
        json.dump(run_meta, f, ensure_ascii=False, indent=2)

    (REPO / "work" / "yuragi" / "L0").joinpath("latest.txt").write_text(run_id + "\n", encoding="utf-8")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    idx_path = INDEX_DIR / "runs-index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    idx.setdefault("L0", {})[run_id] = {
        "path": "work/yuragi/L0/runs/" + run_id,
        "status": "complete",
        "wiki": "yuragi",
        "layer": "L0",
        "kind": "bbs-chunking",
        "created": run_meta["created"],
        "derived_from": run_meta["derived_from"],
        "stats": total,
    }
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"RUN {run_id}")
    print(json.dumps(total, ensure_ascii=False))
    print(f"units={len(units)} -> {run_dir}")


if __name__ == "__main__":
    main()
