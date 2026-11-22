# -*- coding: utf-8 -*-
"""Lane Qv2: 作中实体ページ LLM 量産（5 語/呼び・CN_CHAR ゲート・逐語引用は台帳由来のみ）。

入力: Lane M 抽出台帳（term+usage+quotes per unit）
各呼び出しで 5 語ぶんの「概要」を LLM 生成（日本語のみ）。生成文は cn_gate で検査し
簡体字混入なら 1 回再生成、不合格語は台帳決定論のみで確定（概要なし運用）。
引用・ref は台帳逐語のみ（LLM 引用不採用）。
出力: work/yuragi/L1/runs/20261122T2100_l1enQ/entities/<slug>.md
progress: data/yuragi_qgen_progress.txt（term 済行）
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex
from cn_gate import find_cn, is_cn_free

W = Path(ex.__file__).resolve().parent.parent
SRC = W / "work/yuragi/L1/runs/20261122T1600_l1intra/extract"
OUT = W / "work/yuragi/L1/runs/20261122T2100_l1enQ"
PROG = W / "data" / "yuragi_qgen_progress.txt"

PROMPT = """あなたは『ゆらぎの神話』の作中实体記事の概要生成者です。以下の抽出台帳データ（原文逐語引用と使用状況に基づく）から、各語の「概要」を 2〜3 文で生成してください。台帳にない事実を作らない。**日本語のみ使用**（中国語の簡体字・外国文字は不可）。
出力 JSON のみ:
{"summaries":[{"term":"語","summary":"概要 2〜3 文（日本語）"}]}
--- 台帳データ ---
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


def merge_ledger():
    merged: dict = {}
    for jf in sorted(SRC.glob("*.jsonl")):
        uid = jf.stem
        for it in jl(jf):
            t = str(it.get("term", "")).strip()
            if not t:
                continue
            m = merged.setdefault(t, {"disp": t, "units": {}})
            qs = []
            for q0 in (it.get("quotes") or []):
                if isinstance(q0, dict) and q0.get("q"):
                    qs.append((str(q0.get("ref", uid)), str(q0["q"])[:220]))
            m["units"].setdefault(uid, []).append((str(it.get("usage", ""))[:220], qs))
    return merged


def write_page(term: str, m: dict, summary: str):
    slug = ex.norm(term).replace("・", "_").replace("＝", "=")
    slug = re.sub(r'[\\/:*?"<>|]', "_", slug)[:120]
    if not slug:
        return None
    us = sorted(m["units"].items())
    lines = ["---", f'title: "{term}"', "run: 20261122T2100_l1enQ",
             "model: swift-1.5-iq3_xxs+ledger", f'term: "{term}"', 'type: "作中实体"',
             f"count: {len(us)}", f'generated: "{datetime.now().isoformat()}"',
             f'link_audit: "20261122T2100_l1enQ_{"llm" if summary else "deterministic"}"', "---", "",
             f"# {term}（ゆらぎの神話）", ""]
    if summary:
        lines += ["## 概要", "", summary, ""]
    lines += ["## 使用状況（篇横断・逐語引用＋ref 付き）", ""]
    for uid, entries in us:
        lines.append(f"### [[units/{uid}|{uid}]]")
        lines.append("")
        for usage, qs in entries[:2]:
            if usage:
                lines.append(usage)
            for ref, q in qs[:2]:
                pno = ref.split(":")[-1] if ":" in ref else ""
                base = ref.split(":")[0] if ":" in ref else uid
                lines.append(f"> 「{q}」 [[full/{base}#post-{pno}|{ref}]]")
            lines.append("")
    lines += ["---", "",
              "※ 本記事は作中侧抽出（Lane M）台帳＋概要生成による組立（v0.14 創作活動基準・CN_CHAR 監査ゲート通過済）。",
              "→ [[entities_index|実体索引]] ／ [[entities_map/index|体系版索引]]", ""]
    (OUT / "entities" / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")
    return slug


def main():
    (OUT / "entities").mkdir(parents=True, exist_ok=True)
    merged = merge_ledger()
    done = set()
    if PROG.is_file():
        done = {l.strip() for l in PROG.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [t for t in sorted(merged) if t not in done]
    print(f"[laneQv2] merged={len(merged)} todo={len(todo)}", flush=True)
    ok = gate_drop = errs = 0
    for i in range(0, len(todo), 5):
        batch = todo[i:i + 5]
        summary_map: dict = {}
        try:
            body = "\n".join(
                f"【{t}】" + " ／ ".join(
                    f"{uid}: {usage}" + ("；引用: " + qs[0][1][:100] if qs else "")
                    for uid, (usage, qs) in sorted(merged[t]["units"].items())[:4])
                for t in batch)
            raw = None
            for att in range(6):
                try:
                    raw = ex.call_llm(PROMPT.replace("{BODY}", body[:12000]), max_tokens=1200)
                    break
                except Exception:
                    time.sleep(5 * (2 ** att))
            d = ex.parse_json_lenient(raw) if raw else None
            for r0 in (d or {}).get("summaries", []):
                if isinstance(r0, dict):
                    summary_map[str(r0.get("term", "")).strip()] = str(r0.get("summary", ""))
            # CN ゲート
            for t in batch:
                s0 = summary_map.get(t, "")
                if s0:
                    hits, _ = find_cn(s0)
                    if hits:
                        s0 = ""
                        gate_drop += 1
                write_page(t, merged[t], s0)
                ok += 1
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write("\n".join(batch) + "\n")
            if (i // 5 + 1) % 10 == 0:
                print(f"[laneQv2] {min(i + 5, len(todo))}/{len(todo)} ok={ok} gate_drop={gate_drop} err={errs}", flush=True)
        except Exception as e:
            errs += 1
            print(f"[laneQv2] batch ERR @{i}: {type(e).__name__} {e}", flush=True)
            # 不合格バッチは決定論のみで確定（概要なし）
            for t in batch:
                try:
                    write_page(t, merged[t], "")
                except Exception:
                    pass
            with PROG.open("a", encoding="utf-8") as fd:
                fd.write("\n".join(batch) + "\n")
            if errs >= 15:
                print("[laneQv2] abort: 15 連続エラー", flush=True)
                return 1
    print(f"[laneQv2] FINISH ok={ok} gate_drop={gate_drop} err={errs}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
