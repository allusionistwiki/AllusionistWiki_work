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

## 検証ゲート（run 完結時に必須）

1. 全篇 `declared_posts == n_posts`（篇マニフェスト自己照合）。
2. アンカー往復復元：raw を `body_start:body_end` でスライスし長さが一致（サンプルでよい）。
3. チャンク分割：post_no の**集合**で gaps/overlap ゼロ・複数レスチャンクは budget 内。

## 再生成

`python scripts/build_yuragi_l0_chunks.py`（YuragiWiki raw が同一 commit であること。冪等・新 run として追加）。
run は追加専用・退役は `archive/` へ物理移動。latest.txt / index/runs-index.json の更新は run 完結時のみ。

## 現況

- 現行 = `20261111T0311_l0c`（post-unit+連投群セマンティクス・185 篇 / 48,891 レス / 12,399 群 / 12,508 チャンク・全ゲート通過）。
- 退役 = `20261111T0252_l0c`（v1・chars-budget チャンク方式。`archive/` に物理移動・runs-index に retired 記録）。
- 群ファイル実体 = YuragiWiki repo commit `f0362d6`（12,389 ファイル + 篇 `_manifest.json`・連結無損失検証）。
- 未处理: はてなふりかー**日記ページ**（`raw/bbs/hatena_flicker/md` の bbs 以外）は本層の unit ではない。unit 化（アンカー = ユーザ名 + 日付 + pN）を決めるか対象外を宣言するのは L0 の次版の決定事項。
