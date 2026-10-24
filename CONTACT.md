# CONTACT — LLM2 パイプライン側への連絡事項（2026-10-13）

Wiki 側（AllusionistWiki_obsidian / Quartz 公開系）で行った変更のうち、LLM2 側の作業に影響する事項の連絡。

> **L0〜L7 層設計はアリュージョニスト Wiki 2（『幻想再帰のアリュージョニスト』解析 Wiki）専用設計。**
> スキーマ・命名規則・来歴チェーン・公開層はすべて Wiki 2 前提。他 Wiki への一般再利用は想定しない（詳細は README.md）。

## 1. Repo の所在が変更になった

| 用途 | 現在（正） | 旧（archive 済み・読み取り専用） |
|---|---|---|
| 作業データ（facts/candidates 等） | **`allusionistwiki/AllusionistWiki_work`**（この repo） | `AllusionistLLMWiki2_Work`（archive・書込み禁止） |
| L1 公開サイト元（markdown） | `AllusionistLLMWiki2_Obsidian`（変更なし・稼働中） | — |
| L1 公開サイトビルド | `AllusionistWiki`（本家 Quartz）が担う | `AllusionistLLMWiki2`（Quartz・archive・書込み禁止） |

- 旧 Work repo の最終状態（`054f7a2a`）は **L1 ベースライン run `20261012T0000_baseline`** として本 repo `work/allusionist_v2/L1/runs/` に取り込み済み。以後の産出物は**必ず本 repo へ**。

## 2. Work repo の運用則（守るべきもの）

- **run 追加専用**: 産出物は `work/allusionist_v2/<層>/runs/<run_id>/` に新規フォルダで追記。`run_id = YYYYMMDDTHHMM_<hash4>`。旧 run の書き換え禁止。
- run 内に `run.json`（実行メタ: 日時・入力 run ID/manifest 版・ツール版・パラメータ・`derived_from` 来歴）を必須同梱。
- 産出物は**話単位ファイル**（単一巨大 JSON 禁止）。run は既定**増分**（触れた話だけ）。
- 追記後に `work/allusionist_v2/<層>/latest.txt` と `work/allusionist_v2/index/runs-index.json`（run ID → path/status/derived_from）を更新。**相互参照はパスでなく run ID**。
- コミット規約: `L1: run 20261013T1530_a1f3 (ch00271-280)`。
- 退役 run は `work/allusionist_v2/<層>/archive/` へ物理移動（削除しない）。
- **原文（小説全文）を本 repo に持ち込まないこと**。引用は既存 facts 内の引用範囲まで（L0 は private repo `AllusionistWiki_raw`、参照は manifest ID + chNNNNN + ¶N）。

## 3. L1 公開サイトが `/AllusionistWiki/l1/` に統合された

- 旧サイト `allusionistwiki.github.io/AllusionistLLMWiki2/` は archive（URL は生存するが更新停止）。**新 URL: `https://allusionistwiki.github.io/AllusionistWiki/l1/`**。外部への案内は新 URL へ。
- 公開コンテンツの変更 = `AllusionistLLMWiki2_Obsidian` の `wiki/` を push すれば、本家 Quartz デプロイが自動で取り込む（毎時 schedule / `repository_dispatch: vault-updated` / Quartz main push）。デプロイマーカーは **vault SHA + L1 SHA の連合キー（v3）** — L1 側の push だけで再ビルドされる。
- L1 内リンク規約（2026-10-13 確定・v3）: 層内は相対 markdown（`./claims/`）か wikilink（層内で解決）。**節インデックス・層跨ぎリンクは完全修飾 URL `https://allusionistwiki.github.io/AllusionistWiki/l1/...` のみ安全**（root-absolute `/AllusionistWiki/...` は Quartz が層相対へ書き換えて層外脱出 404 化、相対 `../X/index.md` は basename `index` 曖昧で 404 化。完全修飾 URL は Quartz の書き換え対象外）。
- Quartz FolderNotes 仕様: 全サブフォルダに `index.md` が必要（欠くと breadcrumb リンクが 404）。新サブフォルダ作成時は `AllusionistLLMWiki2/scripts/build_folder_indexes.py` の対象に追加すること。公開検証の基準: 300 ページサンプルクロール broken 0（2026-10-13 達成、commit `99124536`）。

## 4. L2（名前統合）の初 run 設計が確定している

`work/allusionist_v2/L2/README.md` 参照。要点: `entities.json`（安定 ID 不変・aliases・kind・first_seen L0 アンカー・`l1_refs` 来歴）、統合根拠の**確度ラベル必須**（明言/蓋然性高/要検証）。初 run は移行戦略（README 下記節・2026-10-24 確定）に従い L1 run 和集合（baseline + 5xxx 全話 861 話）の名義棚卸し、以後増分。

## 5. 確認作業で見てほしい点（今回の検証で確認済みの基準値）

- baseline run 収受ファイル数: 1,504（git ls-files 基準、run.json 含む）
- L1 公開サイト: `/AllusionistWiki/l1/` 200、クロール 300 ページ broken 0（2026-10-13 時点）
- 統計（index 記載）: 解析済み ch00001〜ch00272 / claims 1,106 / 伏線 495 / 外部参照 1,060
- 旧 LLMWiki2_Obsidian `wiki/` 直下: appearances, arcs, characters, claims, deferrals, entities, episodes, index.md, mysteries, nav, references, reflections, relationships（13 項目）

## 6. 来歴チェーン（公開サイトの再現性主張の根拠）

L7 クレーム（本家 wiki）→ L3 run → L2 run → L1 run（`run.json.derived_from`）→ L0（`AllusionistWiki_obsidian/tools/data/raw_manifest.json` + chNNNNN + ¶N）。**この連鎖が切れないよう**、産出物には必ず元 run ID / 元 fact ID を記録すること。
