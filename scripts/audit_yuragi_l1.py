#!/usr/bin/env python3
"""Yuragi L1 記事品質監査（二層・scope 対応）— 機械ゲート＋LLM 全量監査（生成独立パス）。

python scripts/audit_yuragi_l1.py --scope units   [--workers K] [--max N] [--run-dir rid]
python scripts/audit_yuragi_l1.py --scope topics
python scripts/audit_yuragi_l1.py --scope authors

機械ゲート: 注目投稿欄の引用「…」が照合コーパスの連続部分文字列（省略記号は分節・読点/空白正規化）、
            100 字超なし、規定見出し presence。照合コーパス = units: 篇本文∪群要約 / topics,authors: 全文∪全群要約。
LLM 監査: 記事＋出典コンテキストを読みさせ 一致/一部一致/不一致 判定（判定は生成と独立な別実行）。
出力: work/yuragi/L1/runs/<audit_rid>/ {judged.jsonl, flagged.jsonl, audit.json}
不合格は該当 md 削除 → 生成スクリプト resume → 再監査（機械ゲートは集計時に決定論再適用）。
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"
THRESHOLD = 1.0

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue  # 並列追記による破損行は復旧不能なので無視（該当キーは再判定される）
        if isinstance(r, dict) and r.get("_meta"):
            continue
        out.append(r)
    return out

def load_llm_config():
    cfg = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistLLMWiki2/config.yaml").read_text(encoding="utf-8")
    sec = cfg.split("llm:", 1)[1]
    def grab(key):
        m = re.search(rf'^\s*{key}:\s*"?([^"#\n]+?)"?\s*(#.*)?$', sec, re.M)
        return m.group(1).strip() if m else None
    return {"base_url": grab("base_url").rstrip("/"), "api_key": grab("api_key"), "model": grab("model")}

CFG = load_llm_config()

def call_llm(prompt: str, max_tokens: int = 3000) -> str:
    body = json.dumps({
        "model": CFG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                CFG["base_url"] + "/chat/completions", data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {CFG['api_key']}"})
            resp = json.loads(urllib.request.urlopen(req, timeout=600).read().decode("utf-8"))
            ch = resp["choices"][0]
            txt = (ch.get("message") or {}).get("content") or ch.get("content") or ""
            if txt.strip():
                return txt.strip()
        except Exception:
            pass
        time.sleep(2 + 3 * attempt)
    return ""

def unit_dir(u):
    if u["source"] == "jbbs":
        return RAW / u["raw_path"].rsplit("/", 1)[0]
    if u["source"] == "mixi":
        return RAW / "mixi/373088" / u["title"]
    return RAW / "hatena_flicker"

import unicodedata

def norm(s: str) -> str:
    return re.sub(r"[\s\u3000,、,]+", "", unicodedata.normalize("NFKC", s))

QUOTE_RE = re.compile(r"「((?:[^「」]|「[^」]*」)+)」")

ELLIPSIS = re.compile(r"…+|\.\.\.+|⋯+")

def quote_in(q: str, *corpora: str) -> bool:
    if any(q in c for c in corpora):
        return True
    segs = [s for s in ELLIPSIS.split(q) if s]
    if len(segs) >= 1:
        for c in corpora:
            pos = 0
            ok = True
            for s in segs:
                i = c.find(s, pos)
                if i < 0:
                    ok = False
                    break
                pos = i + len(s)
            if ok:
                return True
    return False

SCOPES = {
    "units":   {"suffix": "_l1u",   "dir": "units",
                "heads": ["## 概要", "## 流れ", "## 主要な話題・設定", "## 注目投稿"]},
    "topics":  {"suffix": "_l1tp",  "dir": "topics",
                "heads": ["## 概要", "## 記述の流れ", "## 主要な設定", "## 注目投稿"]},
    "authors": {"suffix": "_l1au",  "dir": "authors",
                "heads": ["## 概要", "## 活動の流れ", "## 主な作品・設定", "## 注目投稿"]},
    "entities": {"suffix": "_l1en", "dir": "entities",
                 "heads": ["## 概要", "## 記述の流れ", "## 関連する实体", "## 注目投稿"]},
    "free":    {"suffix": "_l1free", "dir": "units", "heads": []},
}

def mech_gate(key, art, corpora, heads):
    issues = []
    corpora_n = [norm(c) for c in corpora if c]
    m = re.search(r"##\s*注目投稿(.*?)(?=\n##|\Z)", art, re.S)
    sec = m.group(1) if m else ""
    for q in QUOTE_RE.findall(sec):
        if len(q) > 100:
            issues.append(f"{key}:QUOTE_LONG:{len(q)}")
        elif not quote_in(norm(q), *corpora_n):
            issues.append(f"{key}:QUOTE_NOTFOUND:{q[:30]}")
    for h in heads:
        if h not in art:
            issues.append(f"{key}:HEAD_MISSING:{h}")
    issues += cn_prose_issues(key, art)
    return issues

CN_ONLY = set("实气时长门关开语说话请谢过义习乡乐齐头图圆园员资货邮译议军队丰艺节丛兰标网吗呢吧们这她它您哥币儿什呀呗哒咯咱么")
# 的(U+7684)・了・叶・马(U+9A6C 旧字体)・乌(U+4E4C 烏)・风(U+98A0 風)・飞(U+98DB)・书(U+66F8)・东(U+6771)・车(U+8ECA) は
# 日本語標準漢字と同一コードポイント → 混入判定しない（実務上 实 がほぼ全事例、次いで 话/气/时）。
# 「了」は日本漢字（両/了）のため除外。実務上 的/实 がほぼ全事例。

def cn_prose_issues(key, art):
    """中国語専用/簡体字（JIS 圏外文字）のプロース混入検査。
    引用「」内は原文コーパス側の実在文字を許容（原文逐語ゲートが担保）。"""
    body = re.sub(r"^---.*?---\s*", "", art, count=1, flags=re.S)
    prose = re.sub(r"「[^「」]*」", " ", body, flags=re.S)
    bad = sorted({c for c in prose if c in CN_ONLY})
    if bad:
        return [f"{key}:CN_CHAR:{''.join(bad)[:12]}"]
    return []

def mech_gate_free(key, art, corpora, min_len=8, min_refs=3, names=None):
    """free 層: 全文の「」引用をコーパス（原文∪群要約）で逐語検証。
    - 8 字未満は名称・用語の引用符使用とみなし対象外
    - names（投稿者名・話題語・篇名）と完全一致する引用はラベル使用として除外
    - 引用長は無制限（制約なし版）
    - 投稿参照 uid:N が min_refs 件以上あること"""
    issues = []
    corpora_n = [norm(c) for c in corpora if c]
    names_n = set(norm(n) for n in (names or set()) if n)
    for q in QUOTE_RE.findall(art):
        qn = norm(q)
        if len(qn) < min_len or qn in names_n:
            continue
        if not quote_in(qn, *corpora_n):
            issues.append(f"{key}:QUOTE_NOTFOUND:{q[:30]}")
    n_refs = len(re.findall(r"YJ-[A-Za-z0-9]+:\d+", art))
    if n_refs < min_refs:
        issues.append(f"{key}:REFS_MISSING:{n_refs}")
    issues += cn_prose_issues(key, art)
    return issues

def judge(key, title, art, ctx, mx=300):
    out = call_llm(f"=== 記事（{title}） ===\n{art}\n\n=== 出典コーパス側コンテキスト ===\n{ctx}\n\n"
                   "判定任务: この L1 記事は出典コーパスに忠実か。\n"
                   "- 概要/流れ/設定が本文事実と一致しているか（文中に無い創作がないか）\n"
                   "- 引用が実在し文脈を曲げていないか\n"
                   "- 参照（群番号・unit:post_no）が索引と矛盾しないか\n"
                   '出力: 「判定: 一致」/「判定: 一部一致」/「判定: 不一致」の 1 行目＋2 行目に理由 1 文')
    m = re.search(r"判定[:：]\s*(一致|一部一致|不一致)", out)
    verdict = m.group(1) if m else "未判定"
    reason = out.splitlines()[1].strip() if len(out.splitlines()) > 1 else out[:80]
    return verdict, reason

_GLOBAL = {}

def global_corpus(l0_latest):
    if "corpora" not in _GLOBAL:
        bodies, sums = [], []
        seen = set()
        for u in jl(L0 / "runs" / l0_latest / "units.jsonl"):
            if u["unit_id"] in seen:
                continue
            seen.add(u["unit_id"])
            d = unit_dir(u)
            bodies.append("\n".join(p["body"] for p in jl(d / "structured.jsonl")))
            sums.append("\n".join(c.get("summary", "") for c in jl(d / "chains.jsonl")))
        _GLOBAL["corpora"] = ["\n".join(bodies), "\n".join(sums)]
    return _GLOBAL["corpora"]

def frontmatter(art):
    m = re.match(r"^---\n(.*?)\n---", art, re.S)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"')
    return fm

def term_context(term, l0_latest):
    lines, n = [], 0
    seen = set()
    for u in jl(L0 / "runs" / l0_latest / "units.jsonl"):
        if u["unit_id"] in seen:
            continue
        seen.add(u["unit_id"])
        d = unit_dir(u)
        for p in jl(d / "structured.jsonl"):
            i = p["body"].find(term)
            if i < 0:
                continue
            s = max(0, i - 80)
            lines.append(f"[{u['unit_id']}:{p['post_no']}] {p['author']}: …{p['body'][s:i+120]}…".replace("\n", " "))
            n += 1
            if n >= 18:
                return "\n".join(lines)
    return "\n".join(lines)

def author_context(author, l0_latest, sp):
    refs = []
    for r in jl(sp / "by-author.jsonl"):
        if r["author"] == author:
            refs = r["refs"]
            break
    lines, n = [], 0
    cache = {}
    for ref in refs:
        uid, no = ref.split(":")
        if uid not in cache:
            u = [x for x in jl(L0 / "runs" / l0_latest / "units.jsonl") if x["unit_id"] == uid]
            cache[uid] = {p["post_no"]: (p["body"], u[0]["title"]) for p in jl(unit_dir(u[0]) / "structured.jsonl")} if u else {}
        got = cache[uid].get(int(no))
        if not got:
            continue
        lines.append(f"[{ref}] {got[1]}: {got[0][:150]}…".replace("\n", " "))
        n += 1
        if n >= 25:
            break
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="units", choices=list(SCOPES))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--run-dir", default=None)
    a = ap.parse_args()
    sc = SCOPES[a.scope]
    names_for = lambda key: set()

    run = max(p for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith(sc["suffix"]))
    arts = {p.stem: rd(p) for p in sorted((run / sc["dir"]).glob("*.md"))}
    l0_latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    sp = max(p for p in (L0 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l0si")) / "search"

    # 監査対象行の構築
    if a.scope in ("units", "free"):
        rows_in, seen = [], set()
        for u in jl(L0 / "runs" / l0_latest / "units.jsonl"):
            if u["unit_id"] in seen:
                continue
            seen.add(u["unit_id"])
            rows_in.append((u["unit_id"], u["title"]))
        rows_in = [(k, t) for (k, t) in rows_in if k in arts] if a.scope == "free" else rows_in
        def corpora_for(key):
            d = unit_dir([u for u in jl(L0 / "runs" / l0_latest / "units.jsonl") if u["unit_id"] == key][0])
            return ["\n".join(p["body"] for p in jl(d / "structured.jsonl")),
                    "\n".join(c.get("summary", "") for c in jl(d / "chains.jsonl"))]
        def names_for(key):
            u = [x for x in jl(L0 / "runs" / l0_latest / "units.jsonl") if x["unit_id"] == key][0]
            d = unit_dir(u)
            names = {u.get("title", ""), u.get("thread_title", "")}
            for c in jl(d / "chains.jsonl"):
                if c.get("author"):
                    names.add(c["author"])
                names.update(c.get("topics", []))
            for p in jl(d / "structured.jsonl"):
                if p.get("author"):
                    names.add(p["author"])
            return names
        def ctx_for(key):
            u = [x for x in jl(L0 / "runs" / l0_latest / "units.jsonl") if x["unit_id"] == key][0]
            d = unit_dir(u)
            chains = jl(d / "chains.jsonl")
            by_no = {p["post_no"]: p for p in jl(d / "structured.jsonl")}
            lines = ["=== 群索引 ==="]
            for c in chains:
                t = ",".join(c.get("topics", [])) or "—"
                lines.append(f"{c['chain_id'].split('#')[1]} [{c['post_range'][0]}-{c['post_range'][1]}] "
                             f"{c['author']} 話題:{t} 要約: {c.get('summary','')}")
            lines.append("=== コーパス本文（抜粋） ===")
            for c in chains:
                txt = "\n".join(by_no[n]["body"] for n in c["post_nos"] if n in by_no)
                lines.append(f"[g{c['chain_id'].split('#')[1]}] {txt[:a.max]}")
            return "\n".join(lines)
    elif a.scope in ("topics", "entities"):
        rows_in = [(s, frontmatter(arts[s]).get("term", s)) for s in sorted(arts)]
        corpora_for = lambda key: global_corpus(l0_latest)
        def ctx_for(key):
            term = frontmatter(arts[key]).get("term", key)
            return term_context(term, l0_latest)
    else:  # authors
        rows_in = [(s, frontmatter(arts[s]).get("author", s)) for s in sorted(arts)]
        corpora_for = lambda key: global_corpus(l0_latest)
        def ctx_for(key):
            author = frontmatter(arts[key]).get("author", key)
            return author_context(author, l0_latest, sp)

    rid = a.run_dir or (dt.datetime.now().strftime("%Y%m%dT%H%M") + "_l1" + sc["suffix"][2:] + "aud")
    out = L1 / "runs" / rid
    out.mkdir(parents=True, exist_ok=True)
    done = {}
    jf = out / "judged.jsonl"
    if jf.exists():
        for r in jl(jf):
            done[r["key"]] = r

    def work(row):
        key, title = row
        if key in done:
            return
        art = arts.get(key)
        if not art:
            with jf.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "verdict": "未判定", "reason": "記事なし"},
                                   ensure_ascii=False) + "\n")
            return
        body_md = re.sub(r"^---.*?---\s*", "", art, count=1, flags=re.S)
        mech = (mech_gate_free(key, body_md, corpora_for(key),
                               names=names_for(key)) if a.scope == "free"
                else mech_gate(key, body_md, corpora_for(key), sc["heads"]))
        verdict, reason = judge(key, title, body_md, ctx_for(key), a.max)
        if mech:
            verdict = "不一致"
            reason = "機械ゲート: " + "; ".join(mech[:3])
        with jf.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "verdict": verdict, "reason": reason,
                                "model": CFG["model"], "ts": dt.datetime.now().isoformat()},
                               ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(work, rows_in))

    rows = {r["key"]: r for r in jl(jf)}
    for key, title in rows_in:
        r = rows.get(key)
        if not r or r["reason"].startswith("機械ゲート") or r["verdict"] == "未判定":
            continue
        art = arts.get(key)
        if not art:
            continue
        body_md = re.sub(r"^---.*?---\s*", "", art, count=1, flags=re.S)
        mech = (mech_gate_free(key, body_md, corpora_for(key),
                               names=names_for(key)) if a.scope == "free"
                else mech_gate(key, body_md, corpora_for(key), sc["heads"]))
        if mech:
            r = dict(r)
            r["verdict"] = "不一致"
            r["reason"] = "機械ゲート: " + "; ".join(mech[:3])
            with jf.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            rows[key] = r
    counts = {}
    for r in rows.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    n = len(rows)
    ok = counts.get("一致", 0) + counts.get("一部一致", 0)
    rate = ok / n if n else 0.0
    flagged = [r["key"] for r in rows.values() if r["verdict"] not in ("一致", "一部一致")]
    (out / "flagged.jsonl").write_text("".join(u + "\n" for u in flagged), encoding="utf-8")
    passed = rate >= THRESHOLD and len(flagged) == 0
    (out / "audit.json").write_text(json.dumps({
        "run_id": rid, "scope": a.scope, "l1_run": run.name, "articles": n, "counts": counts,
        "pass_rate": round(rate, 4), "flagged": len(flagged), "model": CFG["model"]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"L1-AUDIT[{a.scope}] {rid} {'PASS' if passed else 'ISSUES'} flagged={len(flagged)} "
          f"rate={rate:.4f} {json.dumps(counts, ensure_ascii=False)}")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
