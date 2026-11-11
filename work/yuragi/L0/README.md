# L0 — 原文アンカー層（unit / post 台帳）

『ゆらぎの神話』BBS コーパス（したらば・mixi・portal BBS）の観測単位とアンカーを定義する層。
allusionist_v2 の L0（版対応・¶N 台帳）に相当する**原文テキストを持たない台帳層**。
原文は YuragiWiki repo `raw/` にのみ置く（投稿者に著作権・CC0 対象外。本文は引用範囲ですら work に写さない）。

## 方針（2026-11-11 確定）

- **unit = 1 つの「場」**（1 スレ / 1 トピック / 1 掲示板スレッド）。unit ID は `YJ-T###`（したらば movie/7039・目录番号順）/ `YJ-M##`（mixi コミュ 373088・トピック ID 昇順）/ `YJ-H##`（はてなふりかー portal BBS）。
- **アンカー = unit_id + post_no は原生**。スレ・トピックのレス番号がそのサイトの原生番号であり、再採番・住区変換は行わない（¶N 原生方針と同断）。本文切片は `units/<unit>.jsonl` の `body_start`/`body_end`（raw ファイル内 char オフセット）で復元し、改版検知は `raw_sha1` による。
- **レス番号の欠番は正常**（したらば削除投稿 `## N ：<<妖精は口を噤んだ>> ：` は日付なし・番号は飛ぶ）。件数整合は「宣言取得レス数 = 解析ヘッダ数」で行い、番号の連続性は検査に使わない。削除投稿（投稿者不明）は連投連結を断つ。
- **チャンク意味論（2026-11-11 確定）**: 1 投稿 = 1 チャンク、同一投稿者の隣接連投は 1 群（group）。**群の実体（本文ファイル）は raw 層 = YuragiWiki repo の `raw/bbs/**/posts/` に置く**（`tools/split_posts.py` が生成・無損失連結検証付き）。L0 の chunks 台帳は群ファイルへの参照（raw_group_path + sha1）を持ち、1 群が char_budget を超えるときのみ post 境界の窓（parts・同一 group_id 共有）に分割する。
- 日時はサイト別形式（jbbs `2006/06/30(金) 16:50:56` / mixi `2005年11月02日 01:42`・秒なし）をそのまま記録する（正規化台帳は上位層の責務）。
- 来歴: `run.json.derived_from.raw_commit` = 取得時点の YuragiWiki repo HEAD。連鎖を切らない（L1 産出物は必ず unit_id + post_no を引用する）。

## 産出物（runs/<run_id>/）

| ファイル | 内容 |
|---|---|
| `run.json` | 実行メタ・`derived_from`（raw HEAD）・統計 |
| `units.jsonl` | 篇マニフェスト 1 篇 1 行（unit_id・source・url・raw_path・raw_sha1・n_posts・first/last_date・n_chunks） |
| `units/<unit_id>.jsonl` | レス台帳 1 レス 1 行（post_no・author・date・body_start/body_end・chars） |
| `chunks/<unit_id>.jsonl` | チャンク台帳 1 チャンク 1 行（group_id・kind=post/chain/deleted・author・post_range・chars・**raw_group_path/sha1**（実体は raw 層 posts/）・parts 情報） |
| `stats.json` | 件数照合（declared vs parsed）・最大レス長・篇別集計 |

### 検索索引（kind=search-index run・2026-11-11〜）

| ファイル | 内容 |
|---|---|
| `search/posts.jsonl` | 全文投稿マスタ 1 投稿 1 行（ref=unit:post_no・篇タイトル・著者・**ISO 日時（索引側で正規化）**・60字スニペット・group_id/raw_group_path） |
| `search/by-author.jsonl` | 著者 → 投稿参照一覧（件数順） |
| `search/by-date.jsonl` | 時系列全量（JST epoch ソート・削除投稿の無日付は除外） |
| `search/terms.jsonl` | `【…】` 表記索引（ゆらぎ文化の用語記法）→ 出現数・篇分布・参照 |
| `stats.json` | 総数・上位投稿者/用語ランキング |

生成: `scripts/build_yuragi_l0_search_index.py`（現行 latest の chunk run を input し、派生 run として登録・`derived_from.l0_run` 記録）。

## 検証ゲート（run 完結時に必須）

1. 全篇 `declared_posts == n_posts`（篇マニフェスト自己照合）。
2. アンカー往復復元：raw を `body_start:body_end` でスライスし長さが一致（サンプルでよい）。
3. チャンク分割：post_no の**集合**で gaps/overlap ゼロ・複数レスチャンクは budget 内。

## 再生成

`python scripts/build_yuragi_l0_chunks.py`（YuragiWiki raw が同一 commit であること。冪等・新 run として追加）。
run は追加専用・退役は `archive/` へ物理移動。latest.txt / index/runs-index.json の更新は run 完結時のみ。

## 現況

- 現行 = `20261111T0955_l0c`（**raw 基準座標**（CRLF 保存バイト座標で全脚本統一）・185 篇 / 48,891 レス / 12,399 群 / 12,513 チャンク）。
- 検索索引 = `20261111T0955_l0si`（48,891 投稿マスタ / 2,332 著者 / 6,225 語・10,159 出）。
- 全量監査 = `20261111T0056_l0aud` → **PASS**（A1 台帳 / A2 群分割 / A3 disk round-trip 184/184 / A4 分割+参照 / A5 索引全文一致。A5_CHRONO 5 件は実況スレのサーバ採番抖りと裁定＝出典 faithful、台帳に adjudication 記録）。
- 退役 = `20261111T0252_l0c`（v1 budget チャンク）、`20261111T0311_l0c`（v2・改行正規化非対称）、`20261111T0928_l0si`、`20261111T0041_l0aud`（初回監査）。すべて `archive/`。
- 座標規約（恒久）: 数値はすべて raw ファイルのバイト列（改行変換なし）上の char 座標。読み = `read_bytes().decode('utf-8', errors='replace')`、書き = `newline=""`。生成側検証は disk round-trip（自己参照検証は不可）。
- 群ファイル実体 = YuragiWiki repo commit `0826648e`（12,389 ファイル + 篇 `_manifest.json`・disk round-trip 検証・CRLF 保存）。
- 未处理: はてなふりかー**日記ページ**（`raw/bbs/hatena_flicker/md` の bbs 以外）は本層の unit ではない。unit 化（アンカー = ユーザ名 + 日付 + pN）を決めるか対象外を宣言するのは L0 の次版の決定事項。
