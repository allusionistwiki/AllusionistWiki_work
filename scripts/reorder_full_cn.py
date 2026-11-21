#!/usr/bin/env python3
"""full 層 CN 整序: 篇記事散文のみ LLM 再構成（引用・参照・『』は機械マーカーで原位置復元・逐語保証）。
full run units md を「frontmatter+散文」と「## スレッド原文 以降」に分離し、散文だけ LLM へ。
frontmatter と原文節は逐語無傷で機械引継ぎ。ゲート: build_yuragi_refine.gate（引用逐語一致・参照保持・見出し一致・引用外 CN 0）。
出力: work/yuragi/L1/runs/<rid>/units/<uid>.md（full 形式同一）。"""
import argparse, concurrent.futures as cf, json, sys
from pathlib import Path
sys.path.insert(0, r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/scripts")
import build_yuragi_reorder as R
import build_yuragi_refine as B

L1 = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/work/yuragi/L1")
SRC_RUN = "20261118T1948_l1full"
SEC = "\n\n## スレッド原文（全文・制約なし版）\n"
CNMAP = {"时":"時","门":"門","这":"這","说":"説","语":"語","义":"義","变":"変","儿":"児",
         "长":"長","记":"記","载":"載","实":"実","气":"気","开":"開","关":"関","过":"過",
         "习":"習","乐":"楽","齐":"斉","头":"頭","图":"図","圆":"円","园":"園","员":"員",
         "资":"資","货":"貨","邮":"郵","译":"訳","议":"議","军":"軍","队":"隊","丰":"豊",
         "艺":"芸","节":"節","丛":"叢","兰":"蘭","标":"標","网":"網","们":"們","币":"幣",
         "呗":"唄","哒":"噠","么":"麼","婴":"嬰"}

def cn_norm(s):
    return "".join(CNMAP.get(c, c) for c in s)

import re as _re
QUR = _re.compile(r"「[^「」]*」", _re.S)

def unit_posts(name):
    m = _re.match(r"YJ-T(\d+)", name)
    if not m:
        return ""
    n = int(m.group(1))
    for d in L1.parent.parent.parent.glob("**/") if False else []:
        pass
    RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki/raw/bbs")
    texts = []
    for d in RAW.rglob(f"*{n:03d}_*"):
        if d.is_dir() and (d / "structured.jsonl").exists():
            for line in (d / "structured.jsonl").read_bytes().decode("utf-8", "replace").splitlines():
                if line.strip():
                    try:
                        texts.append(_re.sub(r"\s+", "", json.loads(line).get("body", "")))
                    except Exception:
                        pass
            break
    return "\n".join(texts)

def norm_quotes(text, verbatim):
    # 引用外散文は常に CN 正規化。引用は逐語原文（posts 由来）はそのまま、群要約引用は正規化。
    body = QUR.sub(lambda m: m.group(0) if _re.sub(r"\s+", "", m.group(0)[1:-1]) in verbatim
                   else cn_norm(m.group(0)), text)
    return cn_norm(body)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    src = L1 / "runs" / SRC_RUN / "units"
    out = L1 / "runs" / a.run_dir / "units"
    out.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in src.glob("*.md"))
    if a.only:
        names = [n for n in names if n in a.only]
    print(json.dumps({"jobs": len(names)}, ensure_ascii=False), flush=True)

    def fix(name):
        txt = (src / f"{name}.md").read_bytes().decode("utf-8", "replace")
        i = txt.find(SEC)
        if i < 0:
            return name, "NO_SRC_SEC"
        head, srcsec = txt[:i], txt[i:]
        verbatim = unit_posts(name)
        fm, marked_body, quotes, refs, keys = R.markers(head)
        for att in range(2):
            prompt = (
                "次は実在作品の解説記事の散文です。次の規則だけで書き直してください:\n"
                "1. ⟦Q0⟧ ⟦Q1⟧ … ⟦R0⟧ … ⟦K0⟧ … のマーカーは1つも増やさず削除せず、文章中に必ず1回そのまま残す。\n"
                "2. 中国語簡体字を日本語正字体へ: 时→時, 门→門, 这→這, 说→説, 语→語, 义→義, 变→変, 儿→児, 长→長, 记载→記載, 婴儿→嬰児, 气→気。日本語の正常な漢字・熟語（写本など）は変更しない。\n"
                "3. 日本語として破綻した語順を、意味を変えずに自然な語順へ整える。\n"
                "4. 見出し・文意・事実・投稿参照は変えない。出力は書き直した散文のみ（frontmatter・説明・コードブロック不要）。\n\n"
                + marked_body)
            new_body = R.call_llm(prompt, max_tokens=4000, temperature=0.3)
            if not new_body.strip():
                continue
            new_head = fm + "\n" + norm_quotes(R.restore(new_body.strip(), quotes, refs, keys), verbatim) + "\n"
            # LLM が追加した引用符は括弧のみ除去（内容は保持・原文引用集合に無いもの限定）
            orig_q = { _re.sub(r"\s+", "", q[1:-1]) for q in quotes }
            def unwrap(m):
                inner = m.group(0)[1:-1]
                return inner if _re.sub(r"\s+", "", inner) not in orig_q else m.group(0)
            new_head = QUR.sub(unwrap, new_head)
            issues = B.gate(name, norm_quotes(head, verbatim), new_head)
            if issues:
                return name, "GATE:" + ",".join(issues)
            (out / f"{name}.md").write_bytes((new_head + srcsec).encode("utf-8"))
            return name, "ok"
        return name, "EXHAUSTED"

    ok = fail = 0; fails = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(fix, n) for n in names]
        for i, fu in enumerate(cf.as_completed(futs)):
            n, st = fu.result()
            if st == "ok":
                ok += 1
            else:
                fail += 1; fails.append([n, st])
            if (i + 1) % 20 == 0:
                print(json.dumps({"done": i + 1, "ok": ok, "fail": fail}, ensure_ascii=False), flush=True)
    print(json.dumps({"rid": a.run_dir, "ok": ok, "fail": fail, "fails": fails[:8]}, ensure_ascii=False))
    print("REORDER-FULL-DONE")

main()
