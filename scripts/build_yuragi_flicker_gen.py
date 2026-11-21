#!/usr/bin/env python
"""hatena_flicker 日記 unit の L1 自由記述記事生成（LLM・free 層同型規律）。

対象: raw/bbs/hatena_flicker/units.jsonl の YJ-F 作者日記（原文逐語チャンク）。
産出: work/yuragi/L1/runs/<rid>/flicker/<uid>.md
  frontmatter(title/run/source) ＋ 散文（自然な日本語解析記事・150-400 字・見出しなし可）
  ＋ 「## 注目投稿（原文逐語引用）」: 2〜6 件（投稿本文からの逐語のみ・引用 100 字以内）
  ＋ 各引用に投稿 permalink リンク（hatena 元 URL）。
機械ゲート: 引用 ⊆ 原文逐語集合（空白除去 substring）、引用 100 字以内、
CN_CHAR（簡体字専用 CP・引用外）0、CN 混入時は 1 回整序再生成（最大 3 回）。
"""
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / "scripts"))
import build_yuragi_l1_gen as _G
import build_yuragi_reorder as _R
call_llm = _R.call_llm

RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki/raw/bbs/hatena_flicker")
L1 = WORK / "work" / "yuragi" / "L1"
RUNS = L1 / "runs"
CN = set("实气时门关开语说话请谢过义习乡乐齐头图圆园员资货邮译议军队丰艺节丛兰标网吗呢吧们这她它您哥币儿什呀呗哒咯咱么长记载举织练纫级统众页颜历劳报构极应邻术阴圈围婴")
QU = re.compile(r"「[^「」]*」")
QUSET = re.compile(r"[「「]([^「」]+)[」」]")

def jl(p: Path):
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if l.strip():
            r = json.loads(l)
            if not r.get("_meta"):
                out.append(r)
    return out

def strip_fm(t: str) -> str:
    m = re.match(r"^---\r?\n.*?\r?\n---\r?\n", t, re.S)
    return t[m.end():] if m else t

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)   # 画像装飾
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # markdown リンク → ラベルのみ
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[#*_`>|]+", "", s)
    return re.sub(r"\s+", "", s)

def cn_outside(body: str) -> str:
    return "".join(sorted(set(c for c in QU.sub("", body) if c in CN)))

def load_unit(uid: str):
    u = {json.loads(l)["unit_id"]: json.loads(l)
         for l in (RAW / "units.jsonl").read_bytes().decode("utf-8").splitlines() if l.strip()}[uid]
    d = RAW / u["path"]
    posts = []
    for r in jl(d / "structured.jsonl"):
        body = (d / "posts" / f"p{r['post_no']:04d}.md").read_bytes().decode("utf-8")
        posts.append({"n": r["post_no"], "date": r["date_iso"], "url": r["url"], "body": body})
    return u, posts

def gate(uid: str, posts, txt: str) -> list:
    issues = []
    verbs = [norm(p["body"]) for p in posts]
    for q in QUSET.findall(txt):
        qn = norm(q)
        if len(q) > 100:
            issues.append(f"LONG_QUOTE:{len(q)}:{q[:30]}")
        if not any(qn in v for v in verbs):
            issues.append(f"NOT_VERBATIM:{q[:40]}")
    cn = cn_outside(txt)
    if cn:
        issues.append("CN_CHAR:" + cn)
    return issues

def build_prompt(u, posts):
    lines = []
    for p in posts:
        b = p["body"]
        if len(b) > 900:
            b = b[:900] + "…"
        lines.append(f"[投稿{p['n']}｜{p['date']}｜{p['url']}]\n{b}")
    corpus = "\n\n".join(lines)
    if len(corpus) > 24000:
        corpus = corpus[:24000]
    return (
        "あなたは同人文学『ゆらぎの神話』関連コーパスの Wiki 記事作成者です。"
        "以下は作者 " + u["author"] + " の Hatena Flicker 日記の全文（原文逐語・投稿番号付き）です。\n"
        "この作者の日記について、コーパスにない事実は書かない Wiki 記事散文を 1 本書いてください。\n"
        "要求:\n"
        "- 散文のみ（見出しは「## 注目投稿」節の 1 見出しのみ）。日本語の自然な文体（翻訳調・機械調・中国語風味禁止）。"
        "散文中に簡体字中国語専用文字（実・时・门・长・网・这 等）を一切使わないこと。\n"
        "- 「## 注目投稿（原文逐語引用）」節に 2〜6 件の引用を置く。引用は「」で囲み、必ず上記投稿本文からの"
        "**逐語コピー**（100 字以内・改変/連結/要約禁止）。引用の直後にその投稿の URL を markdown リンクで添える。\n"
        "- 散文は日記の内容（何を語った作者か・特徴的な表現・作品世界の描写）を簡潔に。\n"
        "- 出力は Markdown 本文のみ（コードフェンス・前置き・説明不要）。\n\n"
        f"=== 日記全文（{u['author']}・{u['n_posts']} 件・{u.get('first')}〜{u.get('last')}） ===\n"
        f"{corpus}\n"
    )

def strip_codefence(t: str) -> str:
    t = strip_fm(t)
    t = re.sub(r"^```[a-zA-Z]*\n", "", t)
    t = re.sub(r"\n```$", "", t.rstrip())
    t = re.sub(r"^===.*?===\n", "", t, flags=re.S)
    return t

def gen_article(uid: str, rid: str) -> tuple:
    u, posts = load_unit(uid)
    outp = L1 / "runs" / rid / "flicker" / f"{uid}.md"
    outp.parent.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(u, posts)
    temp = 0.3
    issues = ["NOT_GEN"]
    for _ in range(3):
        raw = call_llm(prompt, max_tokens=1600, temperature=temp)
        body = strip_codefence(raw)
        issues = gate(uid, posts, body)
        if not issues:
            break
        temp = 0.15
    if issues:
        return uid, "GATE:" + ";".join(issues[:2])
    fm = (f'---\ntitle: "{u["author"]} の日記"\nrun: {rid}\n'
          f'source: "hatena_flicker"\nauthor: "{u["author"]}"\n'
          f'n_posts: {u["n_posts"]}\n---')
    outp.write_bytes((fm + "\n" + body.strip() + "\n").encode("utf-8"))
    return uid, "ok"

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    rid = a.run_dir
    units = [json.loads(l) for l in (RAW / "units.jsonl").read_bytes().decode("utf-8").splitlines() if l.strip()]
    uids = [u["unit_id"] for u in units]
    if a.only:
        uids = [u for u in uids if u in a.only]
    t0 = time.time()
    fails = []
    ok = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for uid, st in ex.map(lambda x: gen_article(x, rid), uids):
            if st == "ok":
                ok += 1
            else:
                fails.append((uid, st))
            print(f"{uid} {st}", flush=True)
    print(json.dumps({"rid": rid, "ok": ok, "fail": len(fails), "fails": fails,
                      "secs": round(time.time() - t0)}, ensure_ascii=False))
    print(f"FLICKER-GEN[{rid}] done ok={ok} fail={len(fails)}")

if __name__ == "__main__":
    main()
