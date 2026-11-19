"""build_yuragi_reorder.py — 引用保全式プロース再構成（LLM はプロースのみ出力、引用は機械が原位置へ復元）。

記事の引用マーカー化:
  - 「」引用を順に {Q:i} へ置換（引用は原文文字列のまま保持）
  - 本文 uid:N 参照を {R:i} へ置換（uid:N 文字列を保持）
LLM にはマーカー付き本文を書き直させ、機械で引用・参照を元の位置（文の直後）へ復元する。
ゲート: 引用集合逐語一致・参照集合一致・見出し一致・簡体字 0。
"""
import argparse, concurrent.futures as cf, json, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_yuragi_l1_gen as G
from collections import Counter
CFG = G.CFG

W = Path(__file__).resolve().parents[1]
L1 = W / "work" / "yuragi" / "L1"
TRUE_CN = set("实气时长门关开语说话请谢过义习乡乐齐头图圆园员资货邮译议军队丰艺节丛兰标网吗呢吧们这她它您哥币儿什呀呗哒咯")
QU = re.compile(r"「[^「」]*」", re.S)
REF2 = re.compile(r"(?<![A-Za-z0-9:_-])(YJ-[A-Za-z0-9]+:\d+)")
REF = re.compile(r"YJ-[A-Za-z0-9]+:\d+")

def call_llm(prompt, max_tokens=4000, temperature=0.3):
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

def markers(txt):
    # frontmatter は無傷で保持（title 等の「」は引用ゲートの対象外）。本文のみマーカー化。
    fm, body = split_fm(txt)
    quotes, refs, keys = [], [], []
    def qsub(m):
        i = len(quotes)
        quotes.append(m.group(0))
        return f"⟦Q{i}⟧"
    t = QU.sub(qsub, body)
    KQ = re.compile(r"『[^『』]*」|「[^「」]*』")
    def rsub(m):
        i = len(refs)
        refs.append(m.group(0))
        return f"⟦R{i}⟧"
    t = REF2.sub(rsub, t)
    def ksub(m):
        i = len(keys)
        keys.append(m.group(0))
        return f"⟦K{i}⟧"
    t = KQ.sub(ksub, t)
    return fm, t, quotes, refs, keys

def restore(text, quotes, refs, keys):
    def ksub(m):
        i = int(m.group(1))
        return keys[i] if 0 <= i < len(keys) else m.group(0)
    text = re.sub(r"⟦K(\d+)⟧", ksub, text)
    def qsub(m):
        i = int(m.group(1))
        return quotes[i] if 0 <= i < len(quotes) else m.group(0)
    def rsub(m):
        i = int(m.group(1))
        return refs[i] if 0 <= i < len(refs) else m.group(0)
    t = re.sub(r"⟦Q(\d+)⟧", qsub, text)
    t = re.sub(r"⟦R(\d+)⟧", rsub, t)
    return t

def norm_heads(b):
    return sorted(re.sub(r"\s+", "", l) for l in re.findall(r"^## .*", b, re.M))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", required=True, choices=["units", "topics", "authors", "entities", "free"])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    dmap = {"units": "units", "topics": "topics", "authors": "authors", "entities": "entities", "free": "units"}
    src = L1 / "runs" / a.run_dir / dmap[a.scope]
    files = sorted(src.glob("*.md"))
    if a.only:
        files = [f for f in files if f.stem in set(a.only)]
    print(json.dumps({"scope": a.scope, "run": a.run_dir, "jobs": len(files)}, ensure_ascii=False))

    def work(p: Path):
        before = p.read_bytes().decode("utf-8", "replace")
        fm, marked, quotes, refs, keys = markers(before)
        body = split_fm(before)[1]
        heads = "\n".join(re.findall(r"^## .*", body, re.M))
        prompt = (
            "あなたは日本語 wiki 編集者です。以下の記事本文を、自然な日本語の百科事典文体へ書き直してください。\n"
            "【絶対規則】\n"
            "1. ⟦Q数値⟧（引用マーカー）は各 1 回ずつ、同じ見出しセクション内に必ず 1 回だけ含めること。削除・統合・追加・並べ替え（セクション間移動）は禁止。\n"
            "2. ⟦R数値⟧（投稿参照マーカー）は全て 1 回ずつ含めること。位置は対応する記述の直後。\n"
            "3. 見出し行（## 〜）は元の構成をそのまま維持。\n"
            "4. 新しい事実は追加しない。意味を変えない。中国語風味・翻訳調・機械調を自然な日本語へ。本文で「篇」は「スレッド」と書く。\n"
            "5. 出力に新しい「」を一切作らないこと。固有名・造語・用語は括弧なしで平文に書く。\n"
            "6. 出力は本文 Markdown のみ。\n"
            f"（引用マーカー {len(quotes)} 個・参照マーカー {len(refs)} 個・固有名マーカー {len(keys)} 個）\n\n"
            "=== 見出し構成 ===\n" + heads +
            "\n\n=== 記事本文（マーカー付き） ===\n" + marked
        )
        last = ""
        for attempt in range(4):
            out = call_llm(prompt, temperature=0.2 if attempt >= 2 else 0.35)
            if not out:
                continue
            for i in range(len(quotes)):
                if out.count(f"⟦Q{i}⟧") != 1:
                    last = f"Q{i}x{out.count(f'Q{i}x'.replace('x',''))}" if False else f"QMARK:{i}x{out.count('⟦Q'+str(i)+'⟧')}"
                    break
            else:
                for i in range(len(refs)):
                    if out.count(f"⟦R{i}⟧") != 1:
                        last = f"RMARK:{i}x{out.count('⟦R'+str(i)+'⟧')}"
                        break
                else:
                    for i in range(len(keys)):
                        if out.count(f"⟦K{i}⟧") != 1:
                            last = f"KMARK:{i}x{out.count('⟦K'+str(i)+'⟧')}"
                            break
                    else:
                        # marker をセンチネルで保護し、LLM 発明の「」のみ『』へ正規化（引用はマーカーのまま保護）
                        body_cand = out
                        for i, q in enumerate(quotes):
                            body_cand = body_cand.replace(f"⟦Q{i}⟧", f"\x00Q{i}\x01")
                        for i, k in enumerate(keys):
                            body_cand = body_cand.replace(f"⟦K{i}⟧", f"\x00K{i}\x01")
                        for i, r in enumerate(refs):
                            body_cand = body_cand.replace(f"⟦R{i}⟧", f"\x00R{i}\x01")
                        n = 0
                        while True:
                            new = re.sub(r"「([^「」\n]{1,40})」(?=「\1」|\x00Q\d+\x01)", "", body_cand)
                            if new == body_cand: break
                            body_cand = new; n += 1
                            if n > 50: break
                        body_cand = re.sub(r"「([^「」]*)」", lambda m: "『" + m.group(1) + "』", body_cand)
                        for i, q in enumerate(quotes):
                            body_cand = body_cand.replace(f"\x00Q{i}\x01", q)
                        for i, k in enumerate(keys):
                            body_cand = body_cand.replace(f"\x00K{i}\x01", k)
                        for i, r in enumerate(refs):
                            body_cand = body_cand.replace(f"\x00R{i}\x01", r)
                        cand = fm + "\n" + body_cand + "\n"
                        _, cbody = split_fm(cand)
                        iss = []
                        if Counter(QU.findall(body)) != Counter(QU.findall(cbody)):
                            iss.append("QUOTES")
                        if Counter(REF.findall(body)) != Counter(REF.findall(cbody)):
                            iss.append("REFS")
                        if norm_heads(body) != norm_heads(cbody):
                            iss.append("HEADS")
                        prose = QU.sub(" ", cbody)
                        if any(c in TRUE_CN for c in prose):
                            iss.append("CN")
                    if not iss:
                        p.write_bytes(cand.encode("utf-8"))
                        return p.stem, "OK"
                    last = "+".join(iss)
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
    print(json.dumps({"rid": a.run_dir, "ok": ok, "fail": fail, "fails": fails[:15]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
