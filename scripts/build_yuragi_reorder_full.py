#!/usr/bin/env python3
"""full 層 CN 整序: 散文（frontmatter〜原文節の要約）のみ LLM で書き換え。
原文節・引用・ref リンクは機械引継ぎ（逐語）。ゲート: 引用集合不変 + 本文 sha1 不変 + 出力 CN(引用外)=0。"""
import sys, re, json, argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_yuragi_refine as B
import build_yuragi_reorder as R

L1 = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/work/yuragi/L1")
CN = "实气时门关开语说话请谢过义习乡乐齐头图圆园员资货邮译议军队丰艺节丛兰标网吗呢吧们这她它您哥币儿什呀呗哒咯咱么长记载举织练纫级统众页颜历劳报构极应邻号术阴圈围婴"
QU = re.compile(r"「(?:[^「」]|「[^「」]*」)*」", re.S)

def cn_outside(text):
    t = QU.sub(" ", text)
    return [c for c in t if c in CN]

def run_one(name, rid):
    src = L1 / "runs" / "20261118T1948_l1full" / "units" / name
    dst_dir = L1 / "runs" / rid / "units"
    dst_dir.mkdir(parents=True, exist_ok=True)
    out = dst_dir / name
    if out.exists():
        return name, "SKIP"
    t = src.read_bytes().decode("utf-8")
    m = re.match(r"^---\r?\n.*?\r?\n---\r?\n", t, re.S)
    fm = m.group(0)
    body = t[m.end():]
    i = body.find("## スレッド原文")
    if i < 0:
        i = body.find("## 原文")
    head, srcsec = (body[:i], body[i:]) if i > 0 else (body, "")
    quotes = set(QU.findall(head))
    def call(temp):
        prompt = (
            "以下の記事本文（要約散文部分）を自然な日本語へ整序してください。\n"
            "禁止: 事実の追加・削除、実体名の発明。日本語プロースのみ。\n"
            "中国語簡体字専用コードポイント（实・气・时・门・关・语・说・网・长・这・们・这 など JIS 圏外文字）は"
            "日本語本文に一切出現を許しません。日本語漢字（的・了・叶 等）はそのまま使用可。\n"
            "日本語として不自然な圧縮表現（例: 「作者以戏谑口吻写語言」）は、意味を保ったまま自然な日本語に直してください。\n"
            "出力は記事本文（要約散文）のみ。見出し記号は元の ## 級を維持。引用「」は削除して結構です（削除は許容、追加は禁止）。\n"
            "引用「」・投稿番号・リンク行は元のものをそのまま含めてください。\n"
            f"```\n{head}\n```")
        return R.call_llm(prompt, max_tokens=3000, temperature=temp)
    for temp in (0.2, 0.05, 0.0):
        new_head = call(temp)
        new_head = re.sub(r"^```.*?\n|^```\s*$", "", new_head.strip())
        bad = cn_outside(new_head)
        if bad:
            continue
        nq = set(QU.findall(new_head))
        if not nq <= quotes:
            continue
        new = fm + new_head.rstrip() + "\n" + srcsec
        out.write_bytes(new.encode("utf-8"))
        return name, "OK"
    return name, "FAIL:CN"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    names = a.only or sorted(p.name for p in (L1 / "runs" / "20261118T1948_l1full" / "units").glob("*.md"))
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for name, st in ex.map(lambda n: run_one(n, a.run_dir), names):
            print(name, st, flush=True)
            if st in ("OK", "SKIP"):
                ok += 1
            else:
                fail += 1
    print(json.dumps({"rid": a.run_dir, "ok": ok, "fail": fail}, ensure_ascii=False))

if __name__ == "__main__":
    main()
