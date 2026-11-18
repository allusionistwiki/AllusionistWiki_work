# YuragiWiki 充実 10 日計画（2026-11-18〜、ユーザー裁量委任）

目的: 「原文確認可能」を最上位に、wiki を充実にする。各日: 生成→監査→公開→検証を完了させる。
品質基準（恒久）: LLM 全量監査 100% 収束・機械照合・引用 100 字以内・ref 連鎖 L1→投稿 permalink。

## D1 — 投稿単位公開基盤（最優先・ユーザー明示要求）
- `build_yuragi_l1_full.py` v2: 100 投稿/ページ分页、全投稿に HTML アンカー `#post-N` + `[#N]` permalink 表示。
- 検証拡張 `verify_yuragi_l1_full.py`: 篇×ページ単位の投稿収容数・body SHA 一致（48,891 全件）。
- publish: `full/<uid>.md`（索引＝篇記事＋原文 p1）+ `full/<uid>/pK.md`。CI ビルド時間/サイズ確認（Pages 1GB 软限）。

## D2 — 投稿 permalink 結線
- L1 篇記事「注目投稿」の `投稿N` → full 版該当ページアンカー URL（`/full/<uid>/pK#post-N`、決定論 linkify）。
- topics/authors/entities の注目投稿も同様に結線。
- 全リンク健全性機械検査（解決不能リンク 0）。

## D3 — 創作記述レイヤー（site 中核意義: 散在記述のインデックス化）
ユーザー指示: 「創作的な記述はすべてたどれる形で公開すべき。当サイトの意義は各所に散らばった記述の整理（インデックス作成）」
- **抽出分類**: 全 16,271 群を対象に LLM 分類（詩/短編/脚本/設定文/劇中ゲーム・メディア文/歌詞/販促文/その他創作/非創作）＋作品名・断片ヒント付き。→ `works.jsonl` 台帳。
- **作品ページ生成**: 作品（作品名で名寄せしない＝別表記は別ページ＋リンク）ごとに、
  収録投稿の**原文全文**（逐語・投稿 permalink 付き＝追跡可能）＋ 投稿者・日時・掲載篇の文脈 ＋ BBS 上の反応（群要約由来）。
- **創作索引ページ**: 类型別・作品別・投稿者別インデックス（散在記述の横断索引）。
- entity/topic ページへ「関わる創作文」欄を機械結線（同一篇共起）。
- 全量 LLM 監査（収録投稿の逐語性・来歴・文脈忠実）＋機械ゲートで 100% 収束。

## D4 — 作者層の拡張・实体/語句の拡張
- authors min 50（20→増加）→ 生成→監査→収束。
- entities 対象拡張: 出現 3 以上（min 3 再分類）→ 生成→LLM 全量監査→収束。
- topics min 3 拡張分（count=3）→ 生成→監査→収束。

## D5 — 篇記事→实体 被言及 backlink（決定論）
- L0 語句索引の term→units_touched を使い、篇記事末に「本篇で言及される实体」節＋entity 相互リンク（機械生成・照合）。

## D6 — 实体台帳（L2 lite）
- 各实体に「言及篇一覧（索引由来の機械リスト＋リンク）」「共起实体（篇共起回数）」「年代分布」節を追加（決定論生成＋LLM 監査）。
- entities 索引を类型別＋言及数順に強化。

## D7 — 年表の精緻化
- 年月別集計（raw ③ date_iso 決定論）→ 月次セクション＋重要語句の初出/最終言及アンカー付き年表。

## D8 — 検索・導線の充実
- Quartz 検索に entities/索引を含める（excludePrefixes 再調整、iOS DOM 制限は分页済 full で解消）。
- nav: 实体索引・篇・topics・authors・年表・full をカード状トップへ整理。

## D8b — 見た目・UX 品質（ユーザー指示: グラフビューは不要＝無効化して軽量化）
- `quartz.config.ts`: `enableGlobalGraph/enableLocalGraph` を false（グラフは重いだけ）、
  fontSize/読行の最適化、`enableContentIndex` 対象見直し。
- カスタム CSS: 投稿アンカー（`:target` で該当投稿をハイライト）、注目の投稿リンク装い、
  分页 nav の見出し化、モバイル（iOS Safari/Firefox iOS）での行間・フォント確認。
- トップ index を案内パネル化（層の説明・検索導線・更新記録）。
- 全ページ title/breadcrumb 整合、frontmatter 来歴表示の整理。

## D9 — 全体ゲート
- サイト内リンク解決検査（ローカル public 全 HTML の相対/絶対 link 検査）、投稿収容 48,891 全件照合、
  clean URL 全ページ 200 抽出検査、iOS 負荷（1 ページ DOM 上限）、CI ビルド時間/公開サイズ、run 来歴連鎖検査。

## D10 — 仕上げ
- README/skill/runs-index 反映、portal カード更新、報告。バッファ（遅延分の回収）。

## 恒久運用則（本ミッション）
- LLM 生成物は必ず全量 LLM 監査＋機械ゲートで 100% 収束させてから公開。
- 原文テキストは work repo に持込まない（full 版 md は YuragiWiki 側 content のみ・raw 由来）。
- 長時間 job は background+notify。flagged 収束は引用機械修復ループ（恒久則 4 点遵守）。
