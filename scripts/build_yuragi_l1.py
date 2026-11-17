#!/usr/bin/env python3
"""Yuragi L1 篇記事生成パイロット — 185 篇の wiki 記事を LLM で生成（resume 可）。

入力: L0 台帳 units.jsonl + raw ③④（篇メタ・chains 要約・本文抜粋）。
出力: work/yuragi/L1/runs/<rid>/units/<unit_id>.md ＋ run.json（来歴）。
制約: 引用 100 字以内・ref アンカー（unit:post_no）・文中に無い事を書かない。
Strata（swift-1.5-iq3_xxs）・max_tokens 3000・5 再試行・既存 md スキップ（resume）。
使い方: python scripts/build_yuragi_l1.py [--limit N] [--workers K] [--unit U]
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

import yaml

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

def unit_dir(u):
    if u["source"] == "jbbs":
        return RAW / u["raw_path"].rsplit("/", 1)[0]
    if u["source"] == "mixi":
        return RAW / "mixi/373088" / u["title"]
    return RAW / "hatena_flicker"

def build_prompt(u, chains, posts):
    by_no = {p["post_no"]: p for p in posts}
    lines = [
        "『ゆらぎの神話』(BBS 実況コーパス) の wiki 記事を書いてください。",
        f"スレッド: {u['title']}  (source={u['source']} / unit={u['unit_id']})",
        "",
        "=== 群索引（連投チャンク: 番号 投稿範囲 作者 話題 要約） ===",
    ]
    for c in chains:
        t = ",".join(c.get("topics", [])) or "—"
        lines.append(
            f"{c['chain_id'].split('#')[1]} [{c['post_range'][0]}-{c['post_range'][1]}] "
            f"{c['author']} 話題:{t} 要約: {c.get('summary','')}")
    lines.append("")
    lines.append("=== 本文サンプル（冒頭群ほか、抜粋） ===")
    shown = 0
    for c in chains:
        if shown >= 6:
            break
        if c["kind"] == "deleted":
            continue
        txt = "\n".join(by_no[n]["body"] for n in c["post_nos"] if n in by_no)
        lines.append(f"[chain {c['chain_id'].split('#')[1]} 投稿{c['post_range'][0]}] {txt[:350]}")
        shown += 1
    lines += ["", "出力規定:",
              "1. `## 概要`（3〜5 文、そのスレッドで何が語り合われたか）",
              "2. `## 流れ`（群索引を踏まえた展開の要約、群番号 gNNN を参照）",
              "3. `## 主要な話題・設定`（【…】語彙を中心に、文中の事実だけ）",
              "4. `## 注目投稿`（3〜6 件、`投稿番号 (作者): 「引用」` 形式。引用は**単一投稿の本文から逐語コピーした連続部分文字列**・100 字以内。投稿をまたいだ合成・省略・改変・文末截断は禁止。抜粋途中の文を途中で切らないこと）",
              "5. 文中に無い事実を作らない。見出しは上記 4 個だけ。日本語。"]
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--unit", default=None)
    ap.add_argument("--run-dir", default=None)
    a = ap.parse_args()

    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units = jl(L0 / "runs" / latest / "units.jsonl")
    seen, urows = set(), []
    for u in units:
        if u["unit_id"] in seen:
            continue
        seen.add(u["unit_id"])
        urows.append(u)
    if a.unit:
        urows = [u for u in urows if u["unit_id"] == a.unit]
    if a.limit:
        urows = urows[:a.limit]

    rid = a.run_dir or (dt.datetime.now().strftime("%Y%m%dT%H%M") + "_l1u")
    out = L1 / "runs" / rid
    (out / "units").mkdir(parents=True, exist_ok=True)
    if not (out / "run.json").exists():
        (out / "run.json").write_text(json.dumps({
            "run_id": rid, "layer": "L1/units", "model": CFG["model"],
            "derived_from": {"L0_ledger": latest},
            "created": dt.datetime.now().isoformat(), "units_total": len(urows),
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    def work(u):
        md = out / "units" / f"{u['unit_id']}.md"
        if md.exists():
            return 0
        d = unit_dir(u)
        chains = jl(d / "chains.jsonl")
        posts = jl(d / "structured.jsonl")
        art = call_llm(build_prompt(u, chains, posts))
        if not art.strip():
            return 0
        head = (f"---\ntitle: \"{u['title']}\"\nunit: {u['unit_id']}\nsource: {u['source']}\n"
                f"url: {u['url']}\nmodel: {CFG['model']}\nrun: {rid}\n---\n\n"
                f"# {u['title']}\n\n")
        md.write_text(head + art + "\n\n---\nraw: YuragiWiki/raw ③④・L0 台帳 `L0/runs/"
                      + latest + "`\n", encoding="utf-8")
        return 1

    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(work, urows))
    done = sum(res)
    (L1 / "latest.txt").write_text(rid, encoding="utf-8")
    print(json.dumps({"rid": rid, "units_total": len(urows), "emitted": done}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
