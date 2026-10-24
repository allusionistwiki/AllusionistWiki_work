# L2 — 名前統合・正規化層

L1（機械抽出）の産出物から、**同一実体の名前のゆらぎを統合した正規化エンティティ台帳**を作る層。

## 入力 / 出力

- 入力: L1 run（`work/allusionist_v2/L1/runs/<id>/facts/` の人物・用語エンティティ、`_merged/` の統合履歴）
- 出力（run 産出物）:
  - `entities.json` — 正規化エンティティ台帳（台帳は単一ファイル可、run 内で完結）
  - `aliases/chNNNNN.json` — 話単位：L1 名義 → 正規名 対応（来歴）

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
      "first_seen": {"ch": "ch00001", "para": 12},   // L0 アンカー
      "l1_refs": ["<run_id>:facts/chNNNNN#<fact_id>", "..."],
      "merge_evidence": "明言|蓋然性高|要検証",       // 統合根拠の確度
      "notes": "prefix 修正・一人多名称の判定メモ"
    }
  ]
}
```

## 運用則

- **統合は追加専用**: 一度発行した `id` は不変。名前の再分割・再統合は新 run で行い、`aliases` の移動として記録（旧 run は書き換えない）。
- 確度ラベルなしの統合は禁止（vault の「推測はラベル付き」鉄則と同一）。
- 一人多名称（別名・あだ名・prefix 付き表記）は 1 entity + aliases。別人同名は別 id + `notes` に区別根拠。
- 来歴: `l1_refs` で L1 fact → L0（chNNNNN + ¶N）まで辿れること。
- 初 run は `20261012T0000_baseline` を入力に ch00001〜ch00272 の名義棚卸し（初回のみ全量）。以後は新話着時のみ増分 run。

## 状態

- [ ] 初 run 未実行（設計のみ）。実行は LLM パイプライン側で行い、産出物を `runs/<run_id>/` に収め、`work/allusionist_v2/index/runs-index.json` と `latest.txt` を更新する。
