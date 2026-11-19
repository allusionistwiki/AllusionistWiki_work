#!/usr/bin/env python3
"""Yuragi L1 追加記事生成 — topics / authors / chrono（LLM・resume 可）。

python scripts/build_yuragi_l1_gen.py --scope topics [--min 4] [--workers 4] [--run-dir rid]
python scripts/build_yuragi_l1_gen.py --scope authors [--min 100]
python scripts/build_yuragi_l1_gen.py --scope chrono
出力: work/yuragi/L1/runs/<rid>/{topics|authors|chrono}/<slug>.md ＋ run.json
slug は slugify（ファイル名は英数＋_）。frontmatter に term/author 等の来歴を保持。
引用規定（注目投稿欄）: 単一投稿の本文から逐語コピーした連続部分文字列・100 字以内。
"""
import argparse
import datetime as dt
import hashlib
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

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
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
        "temperature": 0.3, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False},
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

def slug(s: str) -> str:
    t = re.sub(r"[^\w]+", "_", s, flags=re.U).strip("_")
    if not t:
        t = "a" + hashlib.sha1(s.encode()).hexdigest()[:8]
    return t[:60]

def unique_slug(base: str, used: set) -> str:
    """Windows 等的大文字小文字無視 FS で衝突しない slug（casefold 集合で連番付与）。"""
    sl = base
    i = 2
    while sl.casefold() in used:
        sl = f"{base}_{i}"
        i += 1
    used.add(sl.casefold())
    return sl

def l0_paths():
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    sdir = max(p for p in (L0 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l0si"))
    return latest, sdir / "search"

def unit_dirs(latest):
    dirs = {}
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        uid = u["unit_id"]
        if uid in dirs:
            continue
        d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
             else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
             else RAW / "hatena_flicker")
        dirs[uid] = (u, d)
    return dirs

QUOTE_RULE = ("引用は単一投稿の本文から逐語コピーした連続部分文字列・100 字以内"
              "（省略・改変・文末截断・投稿跨ぎ合成は禁止、抜粋途中の文を切らない）")

def term_context(term, unit_dirs_):
    lines = []
    n = 0
    for uid, (u, d) in sorted(unit_dirs_.items()):
        posts = jl(d / "structured.jsonl")
        for p in posts:
            i = p["body"].find(term)
            if i < 0:
                continue
            s = max(0, i - 80)
            frag = p["body"][s:i + 120].replace("\n", " ")
            lines.append(f"[{uid}:{p['post_no']}] {p['author']}: …{frag}…")
            n += 1
            if n >= 18:
                return lines
    return lines

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", required=True, choices=["topics", "authors", "chrono", "entities"])
    ap.add_argument("--min", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--only", nargs="*", default=None,
                    help="entities 等: 生成対象 term をファイル（空白区切り）で指定。done.txt 既存分は自動スキップ")
    a = ap.parse_args()
    code = {"topics": "tp", "authors": "au", "chrono": "ch", "entities": "en"}[a.scope]
    rid = a.run_dir or (dt.datetime.now().strftime("%Y%m%dT%H%M") + f"_l1{code}")
    out = L1 / "runs" / rid
    (out / a.scope).mkdir(parents=True, exist_ok=True)
    latest, sp = l0_paths()
    udirs = unit_dirs(latest)
    if not (out / "run.json").exists():
        (out / "run.json").write_text(json.dumps({
            "run_id": rid, "layer": f"L1/{a.scope}", "model": CFG["model"],
            "derived_from": {"L0_ledger": latest, "L0_search": sp.parent.name},
            "created": dt.datetime.now().isoformat()}, ensure_ascii=False, indent=1), encoding="utf-8")

    jobs = []  # (slug, fm_extra, prompt)
    used = {p.stem.casefold() for p in (out / a.scope).glob("*.md")}
    if a.scope == "topics":
        mn = a.min or 4
        for r in jl(sp / "terms.jsonl"):
            if r["count"] < mn:
                continue
            ctx = term_context(r["term"], udirs)
            prompt = (f"『ゆらぎの神話』(BBS 実況コーパス) の語句「{r['term']}」に関する wiki 記事を書いてください。\n"
                      f"登場 {r['count']} 件。=== 出現文脈（unit:post_no 付き抜粋） ===\n" + "\n".join(ctx) +
                      "\n\n出力規定:\n1. `## 概要`（この語句が何か、世界における位置づけ）\n"
                      "2. `## 記述の流れ`（どのスレッドでどのように語られたか、unit_id を参照）\n"
                      "3. `## 主要な設定`（文中の事実だけ）\n"
                      f"4. `## 注目投稿`（2〜5 件、`unit_id:post_no (作者): 「引用」` 形式。{QUOTE_RULE}）\n"
                      "5. 文中に無い事実を作らない。見出しは上記 4 個だけ。日本語のみ使用（簡体字混入 实・气・时・门・话・语 等は禁止。「〜的」は日本語として使用可）。")
            jobs.append((unique_slug(slug(r["term"]), used), f'term: "{r["term"]}"\ncount: {r["count"]}', prompt))
    elif a.scope == "entities":
        mn = a.min or 5
        ent_rows = [r for r in jl(L1 / "entities.jsonl") if r.get("is_entity") and r["count"] >= mn]
        if a.only:
            only = set(Path(a.only[0]).read_bytes().decode("utf-8", "replace").split()) if len(a.only) == 1 and a.only[0].endswith(".txt") else set(a.only)
            prev = {p.stem for rid2 in [p2.name for p2 in (L1/"runs").iterdir() if p2.is_dir() and p2.name.endswith("_l1en")] for p in (L1/"runs"/rid2/"entities").glob("*.md")}
            ent_rows = [r for r in ent_rows if r["term"] in only and slug(r["term"]) not in prev]
        chain_cache = {}
        def chains_of(uid):
            if uid not in chain_cache:
                p = udirs[uid][1] / "chains.jsonl"
                chain_cache[uid] = jl(p) if p.exists() else []
            return chain_cache[uid]
        for r in ent_rows:
            term = r["term"]
            ctx = term_context(term, udirs)
            units_t = sorted({ln.split(":")[0].strip("[") for ln in ctx})
            summ = []
            for uid in units_t[:12]:
                for c in chains_of(uid):
                    tops = c.get("topics") or []
                    summ_txt = c.get("summary") or ""
                    if (term in tops) or (summ_txt and term in summ_txt):
                        summ.append(f"[{c['chain_id']}] {summ_txt}")
                    if len(summ) >= 18:
                        break
                if len(summ) >= 18:
                    break
            prompt = (f"『ゆらぎの神話』(BBS 実況コーパス) の作中实体「{term}」（类型: {r['type']}）の wiki 記事を書いてください。\n"
                      f"登場 {r['count']} 件（スレッド: {', '.join(units_t[:40])}）\n"
                      "=== 出現文脈（unit:post_no 付き抜粋） ===\n" + "\n".join(ctx[:24]) +
                      "\n=== 語られている内容（投稿群の LLM 要約） ===\n" + "\n".join(summ) +
                      "\n\n出力規定:\n1. `## 概要`（この实体が何か。类型: " + r["type"] + " の観点で簡潔に）\n"
                      "2. `## 記述の流れ`（どのスレッドでどのように語られたか、unit_id を参照）\n"
                      "3. `## 関連する実体`（一緒に語られる人物・物品・場所など、コーパス内の名を挙げる）\n"
                      f"4. `## 注目投稿`（2〜5 件、`unit_id:post_no (作者): 「引用」` 形式。{QUOTE_RULE}）\n"
                      "5. 文中に無い事実を作らない。見出しは上記 4 個だけ。日本語のみ使用（簡体字混入 实・气・时・门・话・语 等は禁止。「〜的」は日本語として使用可）。")
            jobs.append((unique_slug(slug(term), used),
                         f'term: "{term}"\ntype: "{r["type"]}"\ncount: {r["count"]}', prompt))
    elif a.scope == "authors":
        mn = a.min or 100
        by_unit = {uid: (u, d) for uid, (u, d) in udirs.items()}
        body_cache = {}
        def get_post(uid, no):
            if uid not in body_cache:
                body_cache[uid] = {x["post_no"]: x for x in jl(by_unit[uid][1] / "structured.jsonl")}
            return body_cache[uid].get(no)
        for r in jl(sp / "by-author.jsonl"):
            if r["n"] < mn:
                continue
            refs = r["refs"]
            ctx, n = [], 0
            for ref in refs:
                uid, no = ref.split(":")
                p = get_post(uid, int(no))
                if not p:
                    continue
                frag = p["body"][:150].replace("\n", " ")
                ctx.append(f"[{ref}] {by_unit[uid][0]['title']}: {frag}…")
                n += 1
                if n >= 25:
                    break
            units_t = sorted({ref.split(":")[0] for ref in refs})
            prompt = (f"『ゆらぎの神話』BBS コーパスの投稿者「{r['author']}」に関する wiki 記事を書いてください。\n"
                      f"投稿数 {r['n']}、登場スレッド: {', '.join(units_t[:40])}\n"
                      "=== 投稿サンプル ===\n" + "\n".join(ctx) +
                      "\n\n出力規定:\n1. `## 概要`（この投稿者は誰で何を語ったか）\n"
                      "2. `## 活動の流れ`（時系列・主要スレッド）\n"
                      "3. `## 主な作品・設定`（この投稿者が生んだ記述）\n"
                      f"4. `## 注目投稿`（3〜5 件、`unit_id:post_no (作者): 「引用」` 形式。{QUOTE_RULE}）\n"
                      "5. 文中に無い事実を作らない。見出しは上記 4 個だけ。日本語のみ使用（簡体字混入 实・气・时・门・话・语 等は禁止。「〜的」は日本語として使用可）。")
            jobs.append((unique_slug(slug(r["author"]), used), f'author: "{r["author"]}"\nn: {r["n"]}', prompt))
    else:  # chrono
        import datetime as D
        rows = [r for r in jl(sp / "by-date.jsonl") if r.get("epoch")]
        per_year = {}
        for r in rows:
            y = D.datetime.fromtimestamp(r["epoch"], D.timezone(D.timedelta(hours=9))).year
            per_year[y] = per_year.get(y, 0) + 1
        tbl = "\n".join(f"{y}: {n} 投稿" for y, n in sorted(per_year.items()))
        top_terms = sorted((r for r in jl(sp / "terms.jsonl") if r["count"] >= 15),
                           key=lambda r: -r["count"])[:30]
        tt = "\n".join(f"{r['term']} ({r['count']})" for r in top_terms)
        prompt = ("『ゆらぎの神話』BBS 実況コーパスの年表 wiki 記事を書いてください。\n"
                  "=== 年別投稿数 ===\n" + tbl + "\n=== 高頻度語（15 件以上） ===\n" + tt +
                  "\n\n出力規定:\n1. `## 概要`\n2. `## 編年`（年ごとに、その時期の主な活動・語られた話題）\n"
                  "3. `## 主要な出来事`（データから読み取れる転換点）\n"
                  "見出しは上記 3 個だけ。データに無い事実を作らない。日本語のみ使用（簡体字混入 实・气・时・门・话・语 等は禁止。「〜的」は日本語として使用可）。")
        jobs.append(("chronology", "kind: chronology", prompt))

    def work(job):
        sl, fm_extra, prompt = job
        md = out / a.scope / f"{sl}.md"
        if md.exists():
            return 0
        art = call_llm(prompt)
        if not art.strip():
            return 0
        head = (f"---\nrun: {rid}\nmodel: {CFG['model']}\n{fm_extra}\n"
                f"generated: {dt.datetime.now().isoformat()}\n---\n\n")
        md.write_text(head + art + "\n\n---\n出典: L0 台帳 `L0/runs/" + latest +
                      "`・検索索引 `" + sp.parent.name + "`\n", encoding="utf-8")
        return 1

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        emitted = sum(ex.map(work, jobs))
    (L1 / "latest.txt").write_text(rid, encoding="utf-8")
    print(json.dumps({"rid": rid, "scope": a.scope, "jobs": len(jobs), "emitted": emitted},
                     ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
