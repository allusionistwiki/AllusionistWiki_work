# AllusionistLLMWiki2_Work

AllusionistLLMWiki2（vault 知識核リポジトリ）の**作業派生物リポジトリ**（v5.2 三層分離の第1層・第2層）。

| ディレクトリ | 内容 |
|:---|:---|
| `events/` | 第1層: イベント層（LLM抽出 JSONL、検証通過分のみ） |
| `staging/` | 第2層: 中間集約層（章単位 YAML） |
| `changesets/` | 変更セット |
| `reports/` | マージレポート |
| `_merged/` | 統合済みアーカイブ |
| `search/` | SQLite 検索インデックス（第1層派生物） |

- 原文（`raw/`）は**どのリポジトリにも置かない**（gitignore 済み）。
- 整合性は**相互コミット参照**で保証: 各コミットに `vault-ref:` / `vault` 側は `work-ref:` を記載し、対応関係を `SYNC_LOG.md` に記録する。
- 統合コミットは vault 側の `python scripts/commit_all.py -m "..." [--push]`。

## 相互参照

- 本体: https://github.com/allusionistwiki/AllusionistLLMWiki2
- 公開サイト: https://github.com/allusionistwiki/AllusionistLLMWiki2_Quartz
