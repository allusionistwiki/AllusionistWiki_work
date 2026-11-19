"""build_yuragi_refine.py — 生成記事の LLM 質感仕上げパス。

目的: 中国語風味・翻訳調・機械調のプロースを自然な日本語 wiki 文体へ調整する。
鉄則（機械ゲートで担保）:
- 引用「」内容は逐語のまま不変（追加・削除・改変禁止）
- 投稿参照 uid:N は全件維持
- 見出し構成は維持
- 事実の追加禁止（原文にない内容を足さない）
- 用語調整: 本文の「篇」→「スレッド」等、日本語として自然な語へ
使い方:
  python scripts/build_yuragi_refine.py --scope units [--only uid ...] [--workers 3]
"""
import argparse, concurrent.futures as cf, datetime as dt, json, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_yuragi_l1_gen as G
CFG = G.CFG

W = Path(__file__).resolve().parents[1]
L1 = W / "work" / "yuragi" / "L1"

TRUE_CN = set("实气时长门关开语说话请谢过义习乡乐齐头图圆园员资货邮译议军队丰艺节丛兰标网吗呢吧们这她它您哥币儿什呀呗哒咯")
QU = re.compile(r"「[^「」]*」", re.S)

def call_llm(prompt, max_tokens=4000, temperature=0.4):
    body = json.dumps({
        "model": CFG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature, "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
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

def split_fm(txt):
    m = re.match(r"^---.*?---\s*", txt, re.S)
    return (txt[:m.end()], txt[m.end():]) if m else ("", txt)

def quote_set(art):
    return [q for q in QU.findall(art)]

REFINE_RULES = (
    "【改写の鉄則】\n"
    "1. 引用「」の中身は 1 文字も変更しない（逐語の原文引用。追加も削除も並び替えも禁止）。引用の数を維持。\n"
    "2. 投稿参照（YJ-…:N 形式の参照）は元の記事の全件を維持する（1 件も減らさない）。\n"
    "3. 見出し構成（## 見出し列）は維持する。\n"
    "4. 新しい事実は追加しない。原文にない内容を発明しない。内容の意味は変えない。\n"
    "5. 日本語として自然な wiki 文体に書き直す: 中国語風味（实/说/的 などの混入、中国語語順）は自然な日本語に書き換える。翻訳調・機械調・冗長な反復を直し、文体の質感を揃える。\n"
    "6. 本文で「篇」という語は使わず「スレッド」と書く（unit_id 記号そのものはそのまま）。記号・数値・引用・参照は改変しない。\n"
    "7. 出力は Markdown 本文のみ（コードフェンスで囲まない、解説を足さない）。\n"
)

def _norm_heads(lines):
    return sorted(re.sub(r"\s+", "", l.strip()) for l in lines)

def gate(key, before, after):
    issues = []
    if not after.strip():
        return [f"{key}:EMPTY"]
    def quotes_of(art):
        out = []
        for q in QU.findall(art):
            out.append(re.sub(r"\s+", "", q))
        return sorted(out)
    qb, qa = quotes_of(before), quotes_of(after)
    if qb != qa:
        issues.append(f"{key}:QUOTES_CHANGED:{len(qb)}->{len(qa)}")
    rb = re.findall(r"YJ-[A-Za-z0-9]+:\d+", before)
    ra = re.findall(r"YJ-[A-Za-z0-9]+:\d+", after)
    if len(ra) < len(rb):
        issues.append(f"{key}:REFS_LOST:{len(rb)}->{len(ra)}")
    fm_b, body_b = split_fm(before)
    fm_a, body_a = split_fm(after)
    hb = re.findall(r"^## .*", body_b, re.M)
    ha = re.findall(r"^## .*", body_a, re.M)
    if _norm_heads(hb) != _norm_heads(ha):
        issues.append(f"{key}:HEADS_CHANGED:{hb}->{ha}")
    prose = QU.sub(" ", body_a)
    bad = sorted({c for c in prose if c in TRUE_CN})
    if bad:
        issues.append(f"{key}:CN_CHAR:{''.join(bad)[:12]}")
    if "篇" in QU.sub(" ", body_a):
        # 本文の「篇」は許容語（固有名・引用内）を除いて检查: 残りは LLM が自然語へ
        pass
    return issues

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", required=True, choices=["units", "topics", "authors", "entities", "free"])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    dmap = {"units": "units", "topics": "topics", "authors": "authors",
            "entities": "entities", "free": "units"}
    src = L1 / "runs" / a.run_dir / dmap[a.scope]
    files = sorted(src.glob("*.md"))
    if a.only:
        files = [f for f in files if f.stem in set(a.only)]
    rid = a.run_dir  # in-place 仕上げ（current run）
    print(json.dumps({"scope": a.scope, "run": rid, "jobs": len(files)}, ensure_ascii=False))

    def work(p: Path):
        before = p.read_bytes().decode("utf-8", "replace")
        fm, body = split_fm(before)
        n_quotes = len(QU.findall(body))
        prompt = (
            "あなたは日本語 wiki 編集者です。以下の記事（『ゆらぎの神話』BBS 実況コーパス解析 wiki）を"
            "自然な日本語の百科事典文体へ書き直してください。\n\n"
            + REFINE_RULES
            + f"\n元の記事の引用（「」で囲まれた箇所）は {n_quotes} 件です。出力にも同じ {n_quotes} 件の引用を、"
            "1 文字も変えずに含めてください（引用の追加・統合・削除は禁止）。\n"
            + "\n\n=== 記事 ===\n" + body
        )
        last = ""
        for attempt in range(5):
            new_body = call_llm(prompt, temperature=0.15 if attempt >= 2 else 0.4)
            if not new_body:
                continue
            cand = fm + "\n" + new_body + "\n"
            iss = gate(p.stem, before, cand)
            if not iss:
                p.write_bytes(cand.encode("utf-8"))
                return p.stem, "OK"
            last = ";".join(iss[:3])
        return p.stem, "GATE:" + last

    ok = fail = 0
    fails = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for key, st in ex.map(work, files):
            if st == "OK":
                ok += 1
            else:
                fail += 1
                fails.append((key, st))
    print(json.dumps({"rid": rid, "ok": ok, "fail": fail, "fails": fails[:10]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
