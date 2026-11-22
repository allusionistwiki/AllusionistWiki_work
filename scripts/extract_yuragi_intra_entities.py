# -*- coding: utf-8 -*-
"""Lane M: 作中創作实体の体系的抽出（v0.14 基準・185 篇全走）。

抽出側プロンプトは allusion（実世界参照）専用だったため、作中創作語
（精霊魔術・紀文字・作中組織/事件/地名）が候補化されていなかった。
本作中側抽出で 1 篇ずつ LLM 抽出（Strata 直列 workers=1）→
run 20261122T1600_l1intra/extract/<uid>.jsonl へ追記専用書込み。
progress: data/yuragi_intra_progress.txt（unit 済行）。
生成は gen_yuragi_entity_articles.py（seed 注入）で別途。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
OUT = W / "work" / "yuragi" / "L1" / "runs" / "20261122T1600_l1intra"
PROG = W / "data" / "yuragi_intra2_progress.txt"

PROMPT = """あなたは『ゆらぎの神話』の**作中創作实体**抽出者です（実世界参照の抽出は別レーンで済んでいます。ここでは作中側のみの抽出）。
対象: 参加者の創作活動によって作中世界に存在するもの — 登場人物・作中国家/組織・制度・魔法体系や技術用語（精霊魔術・言語魔術・因縁呪術・順正化処理 型）・武器/道具・作中地名・作中戦争/事件・作中の創作物（架空ゲーム/書籍）・思想/概念（万民友和 型）・作中ブランド商品。
規則:
- 一般名詞単体（精霊・武器・魔力・国家 など、修飾のない語）は抽出しない。**複合語・固有化された語**のみ。
- 実世界対象への参照（実在神話・作品・人物名）は抽出しない。
- 創作活動がない単純言及は抽出しない（一度触れる小道具・会話の一語）。
出力 JSON のみ:
{"items":[{"term":"作中名義/概念名","usage":"使用状況 1〜2 文（日本語・原文の事実）","quotes":[{"q":"原文逐語 100 字以内","ref":"YJ-xxx:投稿番号"}]}]}
- 抽出は本篇に実在する語のみ。引用は原文逐語。日本語のみ（簡体字不可）。
- **引用は原文 character 単位のコピー＆ペースト**（単語途中での切捨て・省略記号での省略・改変・全角半角変換・空白除去は不可。15〜100字）。完全なコピーが取れない語は quotes を空配列にする。
- **出力本文に簡体字・中国語表記（的・实・网・时・长・门・话・语・们・这 等）が 1 文字でも出る項はその項を出力から削除**。
--- 本篇窓 ---
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


def main():
    (OUT / "extract").mkdir(parents=True, exist_ok=True)
    done = set()
    if PROG.is_file():
        done = {l.strip() for l in PROG.read_text(encoding="utf-8").splitlines() if l.strip()}
    led = json.loads((W / "work/yuragi/L0/runs/20261117T2021_l0c/units.jsonl").read_bytes().decode("utf-8", "replace").splitlines()[0]) if False else None
    units = []
    for l in (W / "work/yuragi/L0/runs/20261117T2021_l0c/units.jsonl").read_bytes().decode("utf-8", "replace").splitlines():
        if l.strip():
            units.append(json.loads(l)["unit_id"])
    todo = [u for u in sorted(units) if u not in done]
    print(f"[laneM] units={len(units)} todo={len(todo)}", flush=True)
    ok = errs = 0
    for i, uid in enumerate(todo):
        try:
            sd, meta = ex.unit_dir(uid)
            rows = jl(sd / "structured.jsonl")
            body = "\n".join(f"【{r.get('post_no')}】{str(r.get('body',''))[:600]}" for r in rows)[:46000]
            raw = None
            for att in range(6):
                try:
                    raw = ex.call_llm(PROMPT.replace("{BODY}", body), max_tokens=2500)
                    break
                except Exception:
                    time.sleep(5 * (2 ** att))
            data = ex.parse_json_lenient(raw) if raw else None
            items = []
            if isinstance(data, dict):
                for it in data.get("items", []):
                    if isinstance(it, dict) and str(it.get("term", "")).strip():
                        items.append(it)
            with (OUT / "extract" / f"{uid}.jsonl").open("a", encoding="utf-8") as fd:
                for it in items:
                    fd.write(json.dumps(it, ensure_ascii=False) + "\n")
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write(uid + "\n")
            ok += 1
            if (i + 1) % 10 == 0:
                print(f"[laneM] {i + 1}/{len(todo)} ok={ok} err={errs} last={uid} items={len(items)}", flush=True)
        except Exception as e:
            errs += 1
            print(f"[laneM] ERR {uid}: {type(e).__name__} {e}", flush=True)
            if errs >= 8:
                print("[laneM] abort: 8 連続エラー", flush=True)
                return 1
    print(f"[laneM] FINISH ok={ok} err={errs}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
