# AllusionistWiki_work

『幻想再帰のアリュージョニスト』解析パイプライン（L0〜L7）の**作業データ repo**。wiki あたり 1 個、層はフォルダで切る。

> **本 repo の L0〜L7 層設計は「アリュージョニスト Wiki 2」専用設計である。**
> 各層のスキーマ・命名規則・来歴チェーン・公開層（`/AllusionistWiki/l1/`）はすべて
> アリュージョニスト Wiki 2（『幻想再帰のアリュージョニスト』解析 Wiki）を前提とした専用設計であり、
> 他作品・他 Wiki への一般再利用を想定しない。他 Wiki で同じ層構造を流用する場合は、
> 本設計を参照として新規設計し直すこと。

## 層

| 層 | 内容 |
|---|---|
| L1 | 機械抽出メイン（facts / candidates / 審査データ） |
| L2 | 名前統合・prefix 修正（正規化済みエンティティ台帳） |
| L3 | 整合性検証（検証済みクレーム集） |
| L4 | LLM 単話内容整理 |
| L5 | 各話統合内容整理 |
| L6 | 内容統合 |

L0（原文）は `AllusionistWiki_raw`（private）、L7（人間訂正済み公開層）は `AllusionistWiki_obsidian` の `wiki/`。

## 構成と運用則（git がスナップショット機構）

```
work/
└── allusionist_v2/        # アリュージョニスト Wiki 2 専用の作業ツリー（1 Wiki = 1 サブフォルダ）
    ├── L1/
    │   ├── runs/          # 追加専用・不変。1実行=1フォルダ=1コミット
    │   ├── archive/       # compaction で退役した旧 run（削除しない・監査用）
    │   └── latest.txt     # 現行 run ID
    ├── L2/ … L6/          # 同構造
    └── index/runs-index.json  # run ID → path/status/derived_from（参照はパスでなく run ID）
```

- 他 Wiki 用の層ツリーは `work/<wiki_id>/` の形で並列に新設する（例: YuragiWiki 用は `work/yuragi_v1/`）。既存の `work/allusionist_v2/` 配下は触らない。

- 旧 run は書き換えない。訂正・再実行・フィードバックは必ず**新 run として追記**し `run.json.derived_from` で来歴を辿る。
- run は既定**増分**（触れた話だけ）。全量はベースラインのみ。退役 run は `archive/` へ物理移動（compaction）。
- コミット規約: `L1: run 20261012T1530_a1f3 (ch00271-280)`。

## 来歴の連鎖

L7 クレーム → L3 run → L2 run → L1 run → L0（`raw_manifest.json` の ID + chNNNNN + ¶N）。

## 出典・履歴

- L1 ベースライン: `AllusionistLLMWiki2_Work@054f7a2a`（2026-10-12 取り込み）
- 設計: AllusionistWiki_obsidian/DESIGN_NOTES.md（L0〜L7・Work 構成・増殖抑制）

## ライセンス

- code・config・データ構造定義: CC0
- 産出データ（facts 等）: 公開（再現性・審査根拠の公開方針）。原文からの引用を含む部分は原作者の著作権が残る。
