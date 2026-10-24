# L2 — 名前統合・正規化層

L1（機械抽出）の産出物から、**同一実体の名前のゆらぎを統合した正規化エンティティ台帳**を作る層。

## 入力 / 出力

- 入力: L1 run（`work/allusionist_v2/L1/runs/<id>/facts/` の人物・用語エンティティ、`_merged/` の統合履歴）
- 出力（run 産出物）:
  - `clusters.json` — 名相関グループ（エッジ型・統合裁定・kind・確度。下記 方針 P2/P5）
  - `entities.json` — 正規化エンティティ台帳（台帳は単一ファイル可、run 内で完結。裁定確定後の clusters の射影）
  - `aliases/chNNNNN.json` — 話単位：L1 名義 → 正規名 対応（来歴）
  - `rejected.jsonl` — 非エンティティ除外台帳（理由付き）

## entities.json スキーマ（初 run 設計）

```json
{
  "schema": "l2-entities/1",
  "entities": [
    {
      "id": "E_<slug>",                  // 安定 ID（正規名 slug、以後不変）
      "canonical": "トリシューラ",        // 正規名
      "aliases": ["トリシーラ", "トリシュラ"],   // 統合された名義（誤記・prefix 付き含む）
      "kind": "character|term|org|item|motif",
      "kind_votes": {"character": 100, "terminology": 44},   // facts entity_type 集計（決定根拠）
      "first_seen": {"ch": "ch00001", "para": 12},   // L0 アンカー
      "l1_refs": ["<run_id>:facts/chNNNNN#<fact_id>", "..."],
      "merge_evidence": "明言|蓋然性高|要検証",       // 統合根拠の確度
      "notes": "prefix 修正・一人多名称・多面（派生用法）の判定メモ"
    }
  ]
}
```

## 運用則

- **統合は追加専用**: 一度発行した `id` は不変。名前の再分割・再統合・kind の変更は新 run の差分として記録（旧 run は書き換えない）。
- 確度ラベルなしの統合・kind 確定は禁止（vault の「推測はラベル付き」鉄則と同一）。
- 一人多名称（別名・あだ名・prefix 付き表記）は 1 entity + aliases。別人同名は別 id + `notes` に区別根拠。同一実体の多面（人物＋その名を冠する組織・語）は本体 1 entity 1 kind + 派生用法は別 entity（関連エッジで結ぶ）か notes の側面記述。
- 来歴: `l1_refs` で L1 fact → L0（chNNNNN + ¶N）まで辿れること。
- 初 run は下記 実行計画 の通り L1 run 和集合（baseline + 5xxx 全話）の名義棚卸し（初回のみ全量）。以後は新話着時のみ増分 run。

---

# L1⇒L2 実行計画（2026-10-24 確定版・戦略 / 方針 / 手順）

数値はすべて実測（L1 二 run の facts・vault `wiki/entities/` 公開ページ）。実装は LLM パイプライン側（S1/S2/S4 = work repo `scripts/`、S3 = Strata 直列）。

## 1. 根拠実測

- L1 稼働: baseline `20261012T0000_baseline`（ch0001〜ch0264・facts 20,070 件）+ カクヨム全話再生成 `20261021T1727_9c2e`（ch5001〜・facts 18,670 件、来歴は f863 経由で L0 ¶N に接続）。
- 名義 surface: facts subject ユニーク **14,897**（両 run 和集合、共通 3,470）。表記正規化（NFKC+空白除去）で統合できるのは **24 件のみ** → 名義ゆらぎはエンコード問題ではなく実体同一性判定の問題。
- kind 分布: 14,897 名義のうち **90%（13,432）は単一 kind のみ**、明確多数派（3 倍差・5 票以上）+208。裁定が必要なのは contested 687 + 完全同数 570 ≈ **1,257 名義**。
- 既存公開エンティティ: vault `wiki/entities/` に **5,969 ページ**（E_char 3,774・E_term 1,062・E_item 620・E_org 401・E_motif 74・E_phrase 32）= 事実上の L2 断片が先に公開されている。
- 断片: 正規化表示名グループ 3,728 のうち **610 グループが複数ページ（1,464 ページ）**、全て同一名の kind 横断（例: ちびシューラ = char/item/org/term の 4 ページ、Spear = char/item/term）。facts subject と完全一致する公開名は 1,270 のみ → 残り ~13.6k は台帳外の未整理 surface（多くは文・句レベルの非エンティティ）。

## 2. 戦略（目標と原則）

- **G1 単一の権威台帳**: `clusters.json` + `entities.json` を L3 以降・全生成器が読む正規化の唯一の権威にする。
- **G2 断片解消**: 610 グループ（1,464 ページ）の同一名 kind 横断を、根拠付き裁定で解消する。
- **G3 名相関の提示**: 特定の名義を入力すると相関する全名義が「エッジ型・統合状態・kind・確度」付きで提示される（人間用索引 + `clusters.json` 機械 API）。
- **G4 来歴**: 統合も kind 決定も根拠（facts→¶N）に辿れること。
- 原則: 追加専用・ID 不変・確度ラベル必須・**LLM は機械で決まらない最小集合だけを裁く**。

## 3. 方針（設計決定 P1〜P7）

- **P1 初 run 対象 = 和集合 861 話の全量棚卸し**。`run.json.derived_from = ["20261021T1727_9c2e", "20261012T0000_baseline"]`。以後増分。
- **P2 裁定単位は相関グループ**（ペア裁定にしない — A=B, B=C, A≠C の移行的矛盾をグループ同時裁定のみ回避できる。例: シナモリアキラ＝シナモリ・アキラ＋アキラ の鎖をゾーイ・アキラで正しく切る）。エッジ型 4 種を機械検出する:

| エッジ型 | 検出手法 | 例（実データ シナモリ/アキラ 171 名義 572 facts） | 統合規定 |
|---|---|---|---|
| **表記ゆれ** | NFKC＋中点/空白/全半角同一化、括弧注記解析 | シナモリアキラ x165 ＝ シナモリ・アキラ x37、`俺（シナモリアキラ）`、`アキラ（シナモリアキラ）` | 自動統合（確度 蓋然性高） |
| **省略・敬称・あだ名** | 接頭辞/接尾辞除去一致・edit 距離 ≤2・部分一致 | アキラ x91（根拠 quote「アキラ。シナモリ、アキラ」）、アキラくん、ちびアキラ | 裁定対象（個別証拠で判断） |
| **同人名** | 部分一致するが票・文脈が別 | ゾーイ・アキラ x15（【力士】のゾーイ・アキラだ。） | 統合禁止（別 id + notes） |
| **派生・関連語** | 名＋接尾（X選）・所有（Xの右腕）・冠（紀人都市X） | シナモリアキラ選 x7、紀人都市シナモリアキラ x5、アキラの右腕 x5 | 統合せず**関係エッジ**として保持（alias にしない） |

→ 「相関する語の提示」と「統合の可否」は別物: 提示は全エッジ、統合は表記ゆれ＋裁定で同一と判定した省略形のみ。関連語は台帳の関係として保持し L3/L5 で使う。

- **P3 自動統合ゲート**: 表記ゆれエッジのみ自動。それ以外は必ず裁定。
- **P4 グループ裁定プロトコル**: 1 グループの全変種＋根拠 quote を 1 回の提示に出し、変種ごとに `alias（同一）/別 entity/要検証` + 確度を出力。判定不能は review キュー（reanchor の収束パターン踏襲、窓拡大の複数パスで完全収束させる）。
- **P5 kind 決定**: facts entity_type 票 + 公開ページ prefix prior の**機械投票**で、単一 kind（90%）・明確多数派を確定（票割合いは `kind_votes` に保持、確度 蓋然性高）。contested/同数の ~1,257 名義のみ P4 の裁定で canonical kind を判定（根拠 quote に「その名が何として振る舞っているか」が写る）。多面名義（シナモリアキラ char100/term44/org12、ちびシューラ char112/item34）は「本体 1 kind、派生用法は別 entity（関連エッジ）か notes の側面記述」を裁定で決める。公開 ID の kind は不変の canonical、矛盾は notes に記録しページ側は S7 で整理。
- **P6 ID 則**: 既存公開 ID（E_char_* 等）を canonical として採用・不変。統合は aliases 移動のみ、ID 再発行・ページ削除なし。
- **P7 非エンティティ**: 長い述語文・引用断・句は台帳外 → `rejected.jsonl`（理由付き、観測対象）。

## 4. 手順（Runbook S0〜S7・各段に検証ゲート）

| 段 | 内容 | 産出物 | 検証ゲート | 負荷 |
|---|---|---|---|---|
| **S0 入力凍結** | L1 二 run の facts・公開 prefix prior・episodes_meta を読み込み順に固定 | 入力 manifest | facts 行数 38,740・名義 14,897 と一致 | 機械 |
| **S1 Stage A シード** | 公開 ID 5,969 を骨格に、facts subject↔公開表示名 完全一致 1,270 を紐付け（`scripts/build_l2_seed.py` 新規） | seed ledger | シード 5,969・ID 衝突 0 | 機械・分 |
| **S2 Stage B 相関グラフ** | エッジ型 4 種の検出＋kind 投票＋非エンティティフィルタ → 裁定キュー抽出（`scripts/build_l2_clusters.py` 新規） | `clusters_draft.json`・裁定キュー・rejected 候補 | 610 断片グループのキュー内包率 100%・kind 裁定キュー ≈1,257 | 機械・分 |
| **S3 Stage C グループ裁定** | 裁定キューを Strata 直列でグループ同時裁定（`scripts/adjudicate_l2.py` 新規・resume 対応・detached 起動・ログに DONE 行）。解析ループと同時実行しない | `clusters.json`（統合裁定・kind・確度） | review キュー 0 収束・全裁定に根拠 quote 付 | LLM 1〜2 時間 |
| **S4 台帳射影** | 裁定確定 clusters から台帳生成（`scripts/build_l2_entities.py` 新規） | `entities.json`・`aliases/chNNNNN.json`・`rejected.jsonl` | 全 entity に kind 確定・l1_refs サンプリング→facts→¶N 到達 | 機械 |
| **S5 run 登録** | `run.json`（derived_from 二 run ID）同梱、`latest.txt`・`runs-index.json` L2 更新、コミット `L2: run <id> (名義棚卸し 861 話)` | run フォルダ | 来歴チェーン検証（→f863→L0 ¶N 到達） | 機械 |
| **S6 公開連鎖** | `build_l2_pages.py`（新規）→ vault `wiki/l2/`（index.md＋相関索引ページ＋台帳一覧。個別ページは必要時に台帳から生成）＋ build_folder_indexes LABELS 追加 → vault push → CI 配置 → 下層Wiki索引 L2 を「稼働中」へ | L2Wiki | 公開ページ broken 0（cache-bust クロール） | 機械 |
| **S7 第 2 ラウンド** | 610 断片（1,464 ページ）の alias リダイレクト・kind 矛盾ページ整理（L7/L1 側） | 置換差分 | lint 緑・旧 URL 生存（削除しない） | LLM 少量 |

## 5. 状態

- [x] 層設計（入力/出力・スキーマ・運用則）
- [x] 移行戦略 → 統合実行計画（本節、2026-10-24 確定版）
- [ ] S1〜S4 スクリプト実装（work repo `scripts/`）
- [ ] 初 run 実行（S0→S5）→ S6 公開 → S7 第 2 ラウンド
