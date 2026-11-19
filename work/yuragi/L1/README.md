# yuragi / L1 — 解析層（記事層）

対象: 『ゆらぎの神話』BBS コーパス（L0 台帳 185 篇・48,891 投稿・16,284 群・語句 6,224）。
位置づけ: L0（台帳・索引・監査）→ **L1（記事）** → 公開（L1 版 wiki / 制約なし版 wiki）。

## 恒久構造（全層同一構図）

層トップ ＋ 要素ページ群。公開配置は `/L1/` 直下⇒各要素（中間入れ子禁止）。

| 要素 | 内容 |
|---|---|
| `top` | 層トップ（発入口・統計・更新記録） |
| `nav` | 篇索引（185 篇の一覧） |
| `units/` | 篇（スレッド）記事 — 概要・流れ・主要投稿（ref アンカー） |
| `topics/` | 話題・語句記事（【…】タグ高頻度語） |
| `authors/` | 作者記事（主要投稿者） |
| `chronology/` | 年表・活動編年 |

## 生成方法（検索→LLM→監査）

1. 検索: `scripts/search_yuragi.py`（語句/作者/日付/全文/要約）で対象投稿群を ref 集合として確定。
2. 入力組立: `scripts/read_yuragi.py`（篇ヘッダ 1 回＋投稿本文）。**生の structured.jsonl を LLM に直接渡さない**。
3. 生成: Strata（swift-1.5-iq3_xxs）。run 単位で `runs/<rid>/` に追記専用保存（run.json 来歴必須）。
4. 監査: LLM 全量品質監査（生成独立パス・判定=引用の忠実性/要約の一致）→ 不合格は再生成。閾値 100%（L0 実務に準拠）。

## 記事の二階梯（公開の二版）

- **L1 版（制約あり）**: 要約・整理・アンカー（`YJ-T031:1245` 形式の ref）＋ 100 字以内の短引用 ＋ YuragiWiki raw へのリンク。原文の著作権は各投稿者に帰属。
- **制約なし版**: L1 ＋ 生スレッド情報をもとに引用の長短・分量の制約なしで記述した記事版。公開範囲はユーザー（管理人）の判断で確定する。

## 現況（2026-11-19）

- 篇記事 `runs/20261117T2115_l1u`（units 185 篇・Strata swift-1.5-iq3_xxs 生成）— LLM 全量監査＋機械ゲート `runs/20261117T2300_l1aud` **PASS・一致 185/185（100%）**。
- 实体記事 `runs/20261118T0948_l1en`（entities 108 篇・語句出現 5 以上を LLM 分類: 实体 108/非实体 34、`work/yuragi/L1/entities.jsonl`）— 監査 `runs/20261118T1023_l11enaud` **PASS・一致 108/108（100%）**。見出し: 概要/記述の流れ/関連する实体/注目投稿。関連する实体は公開面で entity 相互リンク（wikilink 397 本）。
- 話題記事 `runs/20261118T0158_l1tp`（topics 220 篇・語句出現 4 以上）— 監査 `runs/20261118T0354_l11tpaud` **PASS・一致 220/220（100%）**。
- 作者記事 `runs/20261118T0148_l1au`（authors 20 名・投稿 100 以上、slug は casefold 連番）— 監査 `runs/20261118T0319_l11auaud` **PASS・一致 20/20（100%）**。
- 年表 `runs/20261118T0149_l1ch/chrono/chronology.md` — 決定論照合（記事内全年カウント=③投稿 date_iso 集計と一致・乖離 0）。
- 制約なし版 `runs/20261118T0222_l1full`（185 ページ・原文 48,891 投稿全文を決定論埋め込み）— `scripts/verify_yuragi_l1_full.py` **PASS・決定論再構成バイト一致 185/185**（改行変換バグの旧 run `0151_l1full` は `archive/0151_l1full_newlinebug` へ退役）。
- 監査の機械ゲート: 注目投稿欄の引用=原文∪chain 要約の連続部分文字列（省略記号は分節照合・読点正規化・入れ子「」対応）・100 字以内・規定見出し 4 個。引用修復は `scripts/fix_yuragi_l1_quotes.py`（sec 全体一括・文境界トリム＋unit 限定 LCS）。
- 検索: `scripts/search_yuragi.py`（term/author/date/grep/chain/unit）＋ `scripts/read_yuragi.py`（LLM ペイロード）。
- 制約なし**自由記述**層（free）`runs/20261119T0014_l1free`（185 篇・L1＋原文から構造制約なしで自由記述、引用は原文逐語のみ・`uid:N` ref≥3）— LLM 全量監査 `runs/20261119T0009_l11freeaud` **PASS・一致 185/185（100%）**（機械ゲート `mech_gate_free`: 全文逐語照合・8 字未満/名称ラベル除外）。品質サイクル: 小対象 8 篇で v1→v3→機械修復→PASS → 全量拡大→収束 89→5→2→1→0。旧 v1 8 篇は `archive/free_v1_p8`。公開=`/free/`＋`/free_index`（site 7ba8c78c・units↔free↔full 相互リンク）。
- 創作記述レイヤー（works）`runs/20261119T0453_l1works`（6,453 ページ・`(作品名,作者)` 単位・名寄せなし）— 台帳 `works.jsonl`（全 16,271 群 LLM 分類: 創作 7,621/非 8,650・型は設定文 4,236/短編 1,527/脚本 358/詩 184）。収録投稿 26,710 件は原文逐語＋full 投稿页への permalink（26,710 本全 live・empty 0）— `scripts/verify_yuragi_works.py` **PASS 群 7,621/7621・issues 0**。公開=`/works_top`＋`/works_index/<型>`＋`/works/<slug>`（CI run12）。
- 实体拡張 min3: 台帳 `entities.jsonl` 429 語（实体 321・min5 台帳は `archive/entities_ledger_min5.jsonl` に保全）— 生成 `runs/20261119T0932_l1en`（321 件）。
- 公開: **https://allusionistwiki.github.io/YuragiWiki/**（L1 版=site 直下・制約なし版=`/full/`・portal カード直リンク・CI=Pages workflow／YuragiWiki repo content/ git 管理）。
- 残作業: 特になし（公開完了）。将来の更新は `scripts/publish_yuragi_site.py`（run ID 定数更新→再実行→YuragiWiki commit/push→CI 自動デプロイ）。
- 退役: 監査 `2216_l1aud`（ゲート誤検出）は run 外へ移動。旧 1 層設計（v1/v2・2026-11-11 系）はリセット（`838f412`）で撤去済み・来歴は git 履歴。
