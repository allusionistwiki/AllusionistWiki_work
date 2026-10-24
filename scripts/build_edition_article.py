#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版対応表記事生成: なろう ch → カクヨム episode 対応 + 引用 ¶ 確定統計。
   出力: vault wiki/references/edition-map.md（Quartz CI で公開）。
   データ源: work L0 run 20261017T2011_f863 / L1 run 20261018T0040_588c。"""
import json, re, sys
from pathlib import Path
from collections import defaultdict

WORK = Path(r"C:\Users\d5dx\Downloads\Code\AllusionistWiki_work")
RAW = Path(r"C:\Users\d5dx\Downloads\Code\AllusionistWiki_raw\raw\novel")
KDIR = RAW / "kakuyomu/16816927859268545348_幻想再帰のアリュージョニスト"
SDIR = RAW / "syosetu/n9073ca_幻想再帰のアリュージョニスト"
VAULT = Path(r"C:\Users\d5dx\Downloads\Code\AllusionistLLMWiki2\wiki\references\edition-map.md")

L0 = WORK / "work/allusionist_v2/L0/runs/20261017T2011_f863"
L1 = WORK / "work/allusionist_v2/L1/runs/20261018T0040_588c"

# --- カクヨム話メタ: 番号 → (章題, ep_id, url, 段落数) ---
K = {}
for f in sorted(KDIR.glob("ch*.md")):
    n = int(re.match(r"ch(\d+)", f.name).group(1))
    m = re.match(r"ch\d+__(.+)\.md$", f.name)
    title = m.group(1) if m else f.name
    head = f.read_text(encoding="utf-8", errors="ignore")[:2000]
    ep = re.search(r"【kakuyomu ep(\d+)】", head)
    url = re.search(r"【URL (\S+)】", head)
    para = re.search(r"【段落数 (\d+)】", head)
    pub = re.search(r"【公開 (\S+)】", head)
    K[n] = {"title": title, "ep": ep.group(1) if ep else "",
            "url": url.group(1) if url else "", "paras": para.group(1) if para else "",
            "pub": pub.group(1)[:10] if pub else ""}

# --- なろう章題（ch 番号から、ファイル名プレフィックス） ---
S = {}
for f in SDIR.glob("ch*.md"):
    n = int(re.match(r"ch(\d+)", f.name).group(1))
    m = re.match(r"ch\d+_[^ ]*\- (.+?)(?:_\d+)?\.md$", f.name)
    if m and n not in S:
        S[n] = m.group(1).strip()

# --- エピソード対応 ---
EMAP = {}
for l in (L0/"episode-map.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        r = json.loads(l)
        EMAP[r["syosetu_ch"]] = r

# --- 章別引用統計: quote-map(全文一致ヒット) + needs-reanalysis(再解析) + reanchored + deleted（ユニーク単位） ---
stat = defaultdict(lambda: {"total": 0, "hit": 0, "rec": 0, "del": 0, "del_reasons": defaultdict(int)})
seen = {}
for f in (L0/"quote-map").glob("ch*.jsonl"):
    n = int(re.match(r"ch(\d+)", f.name).group(1))
    seen[n] = set()
    for l in f.read_text(encoding="utf-8").splitlines():
        if not l.strip(): continue
        r = json.loads(l)
        key = (r["s_para"], r["quote_head"])
        if key in seen[n]: continue
        seen.setdefault(n, set()).add(key)
        stat[n]["total"] += 1
        stat[n]["hit"] += 1
for l in (L0/"needs-reanalysis.jsonl").read_text(encoding="utf-8").splitlines():
    if not l.strip(): continue
    r = json.loads(l)
    n = r.get("ch") or r.get("episode")
    if n is None: continue
    key = (str(r.get("s_para")), r.get("quote_head", ""))
    seen.setdefault(n, set()).add(key)
    stat[n]["total"] += 1
for l in (L1/"reanchored-final.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        r = json.loads(l)
        stat[r["episode"]]["rec"] += 1
for l in (L1/"deleted-ledger.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        r = json.loads(l)
        stat[r["episode"]]["del"] += 1
        stat[r["episode"]]["del_reasons"][r["reason"]] += 1

REASON_JA = {"appendix": "付録", "interlude_narou_only": "なろう専用幕間",
             "interlude_shortened": "幕間短縮", "scene_removed": "改稿削除",
             "verify_failed": "検証不可", "structure_meta": "章構造メタ",
             "interlude_title": "幕間題", "author_note": "作者注記"}

konly = [json.loads(l) for l in (L0/"kakuyomu-only.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

def klink(n):
    k = K.get(n)
    if not k or not k["url"]:
        return f"{n}"
    return f"[{n}]({k['url']})"

def krange(ns):
    ns = sorted(ns)
    if not ns:
        return "—"
    if len(ns) == 1:
        return klink(ns[0])
    if ns[-1] - ns[0] + 1 == len(ns):  # 連続レンジ
        return f"{klink(ns[0])}–{klink(ns[-1])}（{len(ns)}話）"
    return "、".join(klink(n) for n in ns)

lines = []
lines.append("---")
lines.append("title: 版対応表（なろう版 ⇔ カクヨム版）")
lines.append("id: references/edition-map")
lines.append("description: 解析の典拠を結ぶ、なろう版272話とカクヨム版589話の話対応・段落（¶）アンカー対応表")
lines.append("---")
lines.append("")
lines.append("# 版対応表（なろう版 ⇔ カクヨム版）")
lines.append("")
lines.append("当 wiki の原文典拠は**カクヨム版を正典**とし、段落は **¶N**（カクヨム episode ページの段落 ID）で参照します。")
lines.append("¶N は `https://kakuyomu.jp/works/16816927859268545348/episodes/<episodeId>#pN` の段落直リンクになります。")
lines.append("下表は解析 baseline（なろう版引用）をカクヨム版 ¶ へ写し替えた対応表で、生成来歴は run `20261017T2011_f863`（L0 引用検索）・`20261018T0040_588c`（L1 再アンカー4パス+裁定）です。")
lines.append("")
lines.append("## 数字")
lines.append("")
lines.append("- baseline 引用 **38,288** 件のうち **33,725（88.1%）** はカクヨム版で全文一致し即 ¶ 確定")
lines.append("- 残り **4,528 件（ユニーク 4,036）** を再解析 → **回収 3,693（91.5%）/ 削除台帳 343（8.5%）**")
lines.append("- 削除台帳の内訳（カクヨム正典に非存在を全巻全文検索で確認、理由付きで `deleted-ledger.jsonl`（work repo）に保存）: 付録 160・なろう専用幕間 104・改稿削除 73・検証不可 3・章構造メタ 3・幕間題/作者注記 2")
lines.append("- 対応ゼロ章 5・カクヨム専用 27 話（2022 年・第三巻まわりの本文 6 話 + 2025 年・5-70 以降の続編 21 話。なろうは 5-69 凍結）")
lines.append("")
lines.append("> **注意**: なろう版 ch 番号・p 番号は正典ではありません。引用参照は必ずカクヨム ¶N で行ってください（なろう版 URL は歴史的参照用）。")
lines.append("")
lines.append("## 章対応表（なろう 272 話）")
lines.append("")
lines.append("| # | なろう版（歴史的参照） | カクヨム版 episode | 確定・削除/ユニーク | 削除 |")
lines.append("|---|---|---|---|---|")
for n in sorted(set(list(EMAP.keys()) + [k for k in stat if stat[k]["total"]])):
    e = EMAP.get(n, {})
    st = stat.get(n, {"total": 0, "hit": 0, "rec": 0, "del": 0, "del_reasons": {}})
    title = e.get("title") or S.get(n, "")
    sy = f"[{title}](https://ncode.syosetu.com/n9073ca/{n}/)" if title else f"ch{n:05d}"
    kaku = krange(e.get("kakuyomu", []))
    ok = st["hit"] + st["rec"]
    rate = f"{ok}/{st['total']}" if st["total"] else "—"
    note = ""
    if st["del"]:
        note = " ".join(f"{REASON_JA.get(r, r)}{c}" for r, c in sorted(st["del_reasons"].items()))
    lines.append(f"| {n:03d} | {sy} | {kaku} | {rate} | {note} |")
lines.append("")
lines.append("## カクヨム専用話（27 話・なろう側に該当話なし）")
lines.append("")
lines.append("| カクヨム | 章題 | 公開 | 段落 | 解析 |")
lines.append("|---|---|---|---|---|")
for r in sorted(konly, key=lambda x: x["kakuyomu_ch"]):
    k = K.get(r["kakuyomu_ch"], {})
    lines.append(f"| {klink(r['kakuyomu_ch'])} | {k.get('title','')} | {k.get('pub','')} | {k.get('paras','')} | 未着手 |")
lines.append("")
lines.append("## 参照")
lines.append("")
lines.append("- 生成: `AllusionistWiki_work/scripts/build_edition_article.py`（データ: `work/allusionist_v2/L0/runs/20261017T2011_f863/`、`work/allusionist_v2/L1/runs/20261018T0040_588c/`）")
lines.append("- ¶ アンカー: カクヨム episode ページの段落 ID `#pN` と 1:1。なろう版 p 番号（baseline 旧来歴）とは巻内で非対応。")
lines.append("- 削除台帳の理由分類: 付録=キャラ一覧・プロフィール・章構造メタ・作者注記（カクヨム正典は本文のみ）/ なろう専用幕間=カクヨムに同名作品なし / 幕間短縮=同名カクヨム話で削除された場面 / 改稿削除=カクヨム全巻全文検索で非存在確認。")
lines.append("")

VAULT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", VAULT, VAULT.stat().st_size, "bytes")
