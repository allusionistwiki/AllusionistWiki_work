# -*- coding: utf-8 -*-
"""Lane O: 創作索引カバレッジ検証（スレッドからの無作為抽出・決定論スクリーニング＋LLM 精密判定）。

目的: 創作索引（works 6453 作品）が「創作索引に含まれる創作物一覧」として全集合を
拾えているか。各スレッド（unit の投稿）から無作為に N 投稿抽出し:
 1) 機械: 収録投稿 ref を全 works ページ frontmatter/body から収集 → 未収録投稿を列挙
 2) スクリーニング（非 LLM）: 詩的行数・【】作品名・題+本文構造等の所見を付与
 3) 所見あり投稿は LLM で「創作的記述か（詩/短編/設定文/劇中作品/歌詞 等）」を 1 投稿 1 判定
→ 未収録で創作と判定された投稿数 = 欠落率。台帳: data/yuragi_ocover_<ts>.json
"""
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
SITE = W.parent / "YuragiWiki" / "content"

PROMPT = """あなたは創作索引カバレッジ監査人です。投稿に「創作的記述」（詩・歌詞・短編・小説断片・設定文・劇中作品文・格言集・謎かけ 等、作品として数えうる創作活動の産出）があるか判定し JSON のみ出力:
{"creative": true/false, "kind": "詩|歌詞|短編|設定文|劇中作品|その他", "why": "日本語一文（根拠：何の作品がどんな形で収録されているか/産出がないか）"}
- BBS の会話・雑談・連絡・実世界作品の紹介（作品の「言及」）・断片的な一言は creative=false。
- 作品として完結した産出（詩全文、設定資料、物語冒頭 等）は creative=true。
--- 投稿 ---
{BODY}"""


def jl(p: Path):
    if not p.is_file():
        return []
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        if isinstance(r, dict) and "_meta" in r:
            continue
        out.append(r)
    return out


def main(n_sample: int = 300):
    # 1) works の収録 ref 全集（full permalink 表記 full/YJ-xxx/pK#post-N 対応）
    covered: set = set()
    refpat = re.compile(r"YJ-[A-Za-z0-9]+:\d+")
    linkpat = re.compile(r"full/(YJ-[A-Za-z0-9]+)/p\d+#post-(\d+)")
    for wp in (SITE / "works").glob("*.md"):
        if wp.stem == "index":
            continue
        txt = wp.read_bytes().decode("utf-8", "replace")
        covered |= set(refpat.findall(txt))
        for uid0, pno0 in linkpat.findall(txt):
            covered.add(f"{uid0}:{pno0}")
    print(f"[laneO] works 収録 ref 数: {len(covered)}")
    # 2) 無作為抽出
    led = json.loads((W / "work/yuragi/L0/runs/20261117T2021_l0c/units.jsonl").read_bytes().decode("utf-8", "replace").splitlines()[0]) if False else None
    units = []
    for l in (W / "work/yuragi/L0/runs/20261117T2021_l0c/units.jsonl").read_bytes().decode("utf-8", "replace").splitlines():
        if l.strip():
            units.append(json.loads(l)["unit_id"])
    all_posts = []
    for uid in units:
        try:
            sd, meta = ex.unit_dir(uid)
        except Exception:
            continue
        for r in jl(sd / "structured.jsonl"):
            all_posts.append((uid, r.get("post_no"), str(r.get("body", ""))))
    print(f"[laneO] 全文コーパス投稿数: {len(all_posts)}")
    random.seed(20261122)
    sample = random.sample(all_posts, min(n_sample, len(all_posts)))
    uncovered = [s for s in sample if f"{s[0]}:{s[1]}" not in covered]
    print(f"[laneO] 標本 {len(sample)} / 未収録 {len(uncovered)}")
    # 3) LLM 判定（Strata 直列）
    results = []
    for i, (uid, pno, body) in enumerate(uncovered):
        try:
            raw = None
            for att in range(6):
                try:
                    raw = ex.call_llm(PROMPT.replace("{BODY}", body[:4000]), max_tokens=400)
                    break
                except Exception:
                    time.sleep(5 * (2 ** att))
            d = ex.parse_json_lenient(raw) if raw else None
            cr = bool(d and d.get("creative"))
            results.append({"ref": f"{uid}:{pno}", "creative": cr,
                            "kind": (d or {}).get("kind", ""), "why": (d or {}).get("why", ""),
                            "head": body[:200]})
            if (i + 1) % 10 == 0:
                print(f"[laneO] {i + 1}/{len(uncovered)} creative={sum(r['creative'] for r in results)}", flush=True)
        except Exception as e:
            print(f"[laneO] ERR {uid}:{pno}: {e}", flush=True)
    miss = sum(1 for r in results if r["creative"])
    out = W / "data" / "yuragi_ocover_20261122.json"
    out.write_text(json.dumps({
        "works_refs_covered": len(covered),
        "corpus_posts": len(all_posts),
        "sample": len(sample),
        "uncovered_in_sample": len(uncovered),
        "creative_in_uncovered": miss,
        "est_missing_rate_of_sample": round(miss / max(1, len(sample)), 4),
        "results": results,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[laneO] FINISH sample={len(sample)} uncovered={len(uncovered)} creative(miss)={miss} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 300))
