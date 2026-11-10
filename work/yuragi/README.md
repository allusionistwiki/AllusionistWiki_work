# YuragiWiki 作業層（work/yuragi）

『ゆらぎの神話』BBS 解析 Wiki の work 層。層設計は allusionist_v2 と同じ骨格（L0=raw アンカー台帳 → L1=機械抽出 …）を準用するが、**設計は YuragiWiki 専用**（BBS 投稿コーパス前提）。

## 原文（L0 raw）の所在

- 原文は **YuragiWiki repo の `raw/` にのみ**置く（著作権は各投稿者に帰属・CC0 対象外。work repo に本文を持ち込まない）。
- ローカル `Downloads/Code/YuragiWiki` / GitHub `allusionistwiki/YuragiWiki`。取得日 2026-10-12。

## 解析単位（unit）とアンカー

- `unit` = 1 つの「場」: 1 スレ（したらば）/ 1 トピック（mixi）/ 1 掲示板スレッド（はてなふりかー portal BBS）。
- unit ID: `YJ-T###`（したらば movie/7039 スレ・目录番号順）/ `YJ-M##`（mixi コミュ 373088 トピック・ID 昇順）/ `YJ-H##`（portal BBS）。
- **アンカー = `unit_id + post_no`**（スレ・トピックのレス番号が原生アンカー）。版対応・再採番は行わない。
- 本文引用は `units/<unit>.jsonl` の `body_start`/`body_end`（raw ファイル内の char オフセット）でスライスして得る（work には本文を写さない）。`raw_sha1` で原文改版検知。
- 削除投稿（したらば `<<名前削除>>` 系）はレス番号が欠番で現れる。件数検査は「declared 取得レス数 = parsed ヘッダ数」で行う（番号連続性は使わない）。

## L0 runs

- 産出は `work/yuragi/L0/runs/<run_id>/` 追加専用。`run.json`（`derived_from.raw_commit` = YuragiWiki HEAD）同梱。
- 初 run `20261111T0252_l0c`（bbs-chunking・生成スクリプト `scripts/build_yuragi_l0_chunks.py`）:
  - `units.jsonl` 185 篇（jbbs 179 / mixi 5 / portal BBS 1）
  - `units/<unit>.jsonl` 48,891 レス（post_no・投稿者・日時・char オフセット）
  - `chunks/<unit>.jsonl` 618 チャンク（連続レス群 ≤12,000 字・LLM 入力単位）
  - `stats.json`（件数一致 0 崩れ・チャンク分割検証済み）
- 索引: `work/yuragi/index/runs-index.json` + `work/yuragi/L0/latest.txt`。

## 未处理（次の検討）

- はてなふりかーの**日記ページ**（`raw/bbs/hatena_flicker/md` の bbs 以外 1,300+ ページ・portal 記述の本体）は掲示板ではないため本 run 対象外。unit 化の設計は別途（日記アンカー = ユーザ名+日付+ページ番号 pN）。
- mention 群（他サイトからの参照 14 件）は被引用側の対応付けに使う。
