# Yuragi 作業層（AllusionistWiki_work / work/yuragi）

『ゆらぎの神話』BBS コーパスの解析台帳層。**リセット（2026-11-14）後の 5 層設計**。
原文実体はすべて YuragiWiki repo（raw 層）にあり、本層は本文を持たない台帳・索引・監査。

## raw 5 層（YuragiWiki repo・正）

| 層 | 実体 | 用途 |
|---|---|---|
| ① | `raw/bbs/**/Thread.md`・`*_topic_comment.md` | スレッド形式（取得記録・無改変） |
| ② | `raw/bbs/**/posts/pXXXX.md`（連投群 `p0123-0127.md`） | 各投稿チャンク（記事参照用） |
| ③ | `raw/bbs/**/structured.jsonl` | 各投稿構造化（全文省略なし・LLM 用） |
| ④ | `raw/bbs/**/chains.jsonl` | 同一作者＋同一話題で一まとめ |
| ⑤ | `raw/bbs/**/thread.json` | 一連の話題（スレッド全体）で一まとめ |

- ④ の話題規則（決定論）: 隣接＋同一作者＋【…】語彙が群語彙の部分集合で merge、新規【…】で新群、削除投稿（`<<…>>`）は連鎖を断つ。
- ⑤ の連結 = ③ 全文を投稿順に `"\n\n"` 連結（内容省略なし）。
- ③④⑤ 生成・検証: `YuragiWiki/tools/build_raw_layers.py`（篇 `_layers_manifest.json`）。
- unit ID: `YJ-T###`（したらば movie/7039・179 篇）/ `YJ-M<トピックID>`（mixi 373088・5 篇）/ `YJ-H01`（はてな portal BBS・10 投稿・1 ページ 1 投稿＝②はページそのもの）。

## 本層（work L0）の役割

台帳 v3（`L0/runs/<run>/`）: `units.jsonl`（篇メタ＋①〜⑤ SHA 参照）、`units/<unit>.jsonl`
（投稿台帳: ref `unit:post_no`・② ファイル内 body 座標（raw バイト基準）・chain_id）、
`chunks/<unit>.jsonl`（④ 台帳ビュー＋ 24,000 字超群の post 境界 LLM 窓）、検索索引（派生 run）、全量監査。

- アンカー規約: `unit_id + post_no`（原生のまま・再採番しない）、改版検知は raw SHA1。
- 座標規約（恒久）: 数値はすべて対象ファイルの raw バイト列（改行変換なし）上の char 座標。読み `read_bytes().decode('utf-8', errors='replace')`、書き `newline=""`。検証は disk round-trip（自己参照検証は不可）。
- 生成: `scripts/build_yuragi_l0.py` → `scripts/build_yuragi_l0_search_index.py`（派生・latest.txt 更新禁止）→ `scripts/audit_yuragi_l0.py`（全量 A1〜A5）。
- 旧 1 層設計（v1/v2）・全 run はリセット（work commit `838f412`）で撤去。来歴は git 履歴。

## 現況（2026-11-14）

- 台帳 = `20261114T0412_l0c`: 185 篇 / 48,891 投稿 / 16,271 群 / 16,284 チャンク / 6,222,075 字 / 2,332 著者
- 検索索引 = `20261114T0412_l0si`: posts 48,891 / ISO 48,629 / 無日付 262（削除投稿）/ 語彙 6,224・8,779 出
- 全量監査 = `20261114T0432_l0aud` → **PASS**（ISSUES=0。A5_POSTDATE_INV=5 は実況スレ採番抖りとして裁定＝出典 faithful）
- 未处理: はてなふりかー**日記ページ**（portal 記述の本体 1,300+ 頁）の unit 化（アンカー = ユーザ名＋日付＋pN）は次版決定。
