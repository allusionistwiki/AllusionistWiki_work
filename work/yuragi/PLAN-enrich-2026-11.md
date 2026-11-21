# PLAN-enrich 2026-11（9 日自律タスク台帳・2026-11-22 開始）

ユーザー指示: 9 日間の予算で自律実行。wiki の内容・構成・見た目を拡充。
30 分以上の長時間 job は background（persist_on_release）で並列レーン化し、
30 分毎の現状確認（ウォッチ cron）で停滞しないこと。方針変更はユーザーが随時コメントする。

## 常設則（このタスクの運用）
- LLM 系は Strata（127.0.0.1:8080/v1・単一スロット）直列: 同時に 1 本の extract/audit のみ。
- 非 LLM（publish・git・索引生成・見た目 patch・web 調査）は LLM レーンと並列可。
- 30 分超 job は terminal background + persist_on_release=true + notify。ターンを/end して通知を待つ。
- 全产出は run 台帳（run.json 来歴）＋ runs-index に登録。公開は全量監査収束後（EDITING.md）。
- 台帳 `data/yuragi_allud_batches.json` が laneA の進行状態。status: queued → running → done（失敗 failed）。
- 公開面の変更は YuragiWiki repo commit/push → CI 3 段（差分ビルド）で自動反映。

## レーン表
| レーン | 内容 | LLM? | 状態 |
|---|---|---|---|
| A1 | allusion 抽出 179 篇（31 バッチ・台帳 b1..b31） | LLM 直列 | b1 起動 |
| A2 | 監査: バッチ完了→ 400+ サンプリング実読（小バッチ全件実読）→ suppressions 裁定 → 収束 | LLM+実読 | b1 完了後 |
| B1 | 対象名寄せページ（篇横断 allusion term ページ・規則ベース） | 非 LLM | 未着手 |
| B2 | 索引拡張: topics 閾値 3→2・authors 閾値 10→5 | 非 LLM | 未着手 |
| B3 | 見た目: 全文検索(flexsearch)確認・Explorer・OG・mobile | 非 LLM | 未着手 |
| B4 | 相互リンク強化: allusion↔entities↔units | 非 LLM | 未着手 |
| B5 | CI 3 段の実測検証（次回 content push で mode=diff 確認） | — | a8c160856 待ち |
| C1 | flicker/free/works の追加要望（ユーザーコメント対応分） | 混合 | コメント待ち |

## A1 バッチ進行表
台帳: `data/yuragi_allud_batches.json`（b1=20261122T2200 … b31=20261126T1600・179 篇 47,370 投稿）

起動コマンド（watchdog もこれを使う・run_dir/uids は台帳から）:
```
cd C:/Users/d5dx/Downloads/Code/AllusionistWiki_work && \
python scripts/extract_yuragi_allusions.py --uids <uids...> --run-dir <run_dir> \
  --workers 1 --window 60 --max-calls 8
```

## A2 監査プロトコル（収束基準）
- 抽出完了バッチから: gate_drops.jsonl 双向実読＋採用 item の 400+ サンプリング実読
  （小バッチは全件）。閾値 99%（ユーザー恒久基準）。
- 裁定は run dir の suppressions.json（drop/fix_usage・理由付き）に追記、publish が恒久適用。
- 新傾向の欠陥は prompt/ゲート規則へ反映（v0.6 まで収束済み、変更は run 記録）。
- 179 篇完了後に全篇 allusions_index 再生成＋B1 名寄せ → site 公開（CI 差分ビルド）。

## 収束済み（前提知識）
- allusion 規則 v0.6: 原文明示基準（坂本型=対象外・芦屋道満型=対象）、usage 自白 drop、
  EXPLICIT 例外で過剰抑制回収、命名用途 keep / 使用描写 drop。pilot 6 篇 216 件公開済み。
- 公開 SHA: YuragiWiki a8c160856（CI 3 段導入後）。flicker/flaud12・flicker 監査 PASS。
- CI 高速化 3 段: マーカー(tree SHA 連合)→差分ビルド→full。ローカル 4m19s→1m18s。

## ウォッチ（30 分毎）
- cronjob「YuragiWiki 9日 enrichment 现状确认」: monitor スクリプト `yuragi_watch_status.py`
  （進行が変わった tick だけエージェント起動・変化なしはスキップ）。
- 起動時役割: 進行報告／停滞検出（running なのに items 不変 + プロセス無し = 打ち切り、
  次バッチ起動）／strata=DOWN 報告／全バッチ done 報告。
- Strata 起動手順（DOWN 時）: ユーザーへ報告（自走再起動はしない・PC 環境に依存）。

## 状態更新ログ（追記式）
- 2026-11-22 22:00 台帳生成・b1 起動・ウォッチ cron 登録。
- 2026-11-22 b1 完了（20 篇 44 件・fails 0）・全件実読監査: keep 42・drop 2（T117 バッファロー/桃太郎＝usage 自白穴）。gate 過剰抑制 1（T044 魔法少女＝ジャンル名）→ EXPLICIT に「ジャンル」追加＋自白検出 `原文に明示…ない` 正则追加（v0.7）。b2 起動（20261123T0100・510 投稿）。
- 2026-11-23 b2 完了（78 件）全件実読: 裁定 drop 9（自白 TRPG×3・ノア解釈・Iカップ・職業分類・ライオン・イスラム語捏造・中南亜）。gate 過剰抑制 4（共産主義/ディラックの海/ポジトロン/バハムート＝FICTION が EXPLICIT 語で回収）→ FICTION ゲートに EXPLICIT 例外追加・gate_drops 記録を全文化（v0.8）。b3 起動（926 投稿）。回収: b3 完了後に YJ-T036 単篇再生成（同一 run_dir 上書き・約 20 分）。
- 2026-11-23 b4 完了（129 件）全件実読: 裁定 drop 16（自白×4・場面描写/一般名 8・解釈帰属 3・作中創作 2）。自白検出の穴（「原文に固有名詞の明示はない」）→ 正则を `原文に.{0,18}明示.{0,10}ない` に拡幅（v0.9）。T036 単篇再生成起動（FICTION 回収: 共産主義/ディラックの海/ポジトロン/バハムート/ネバーランド）。publish multi-run 化完了（pilot+done run 全部→55 篇公開 261f6c59a）。
- 2026-11-23 b5 完了（132 件）全件実読: 裁定 drop 13（食用/用品 scene 9・推測 1・一般語 3）。gate drop 7 件は全て妥当（想起させる型は v0.6 自白ゲートが機能）。b6 起動（1283 投稿）。
- 2026-11-23 b6 完了（194 件）全件実読: 裁定 drop 16（scene/一般語 13・自白/作中 3）。gate drop 20 件全件妥当（v0.6-0.9 自白/FICTION ゲート定着を確認、ゴダール/2001/タイタニック等の想起系を LLM 自白側でも自律排除）。M2557927 神話コミュ談義 38 件は全件 keep（高品質）。b7 起動。
- 2026-11-23 b7 完了（55 件）全件実読: 裁定 drop 4。gate 過剰抑制 2（T008 シャベル/スコップ＝呼称討論なのに OBJ 発動）→ EXPLICIT に 呼称/定義/論争 追加（v0.10）。b8 起動（1348 投稿）。b8 完了後に T008 単篇再生成（回収）。

## 状態ログ 2026-11-23（b8 収束）
- b8 全件実読 233 件 → 裁定 17 drop（捏造単位 MCU 解釈帰属 場面物体 食品/素材/生物/施設一般名 作中創作書名）。gate 29 件は全件妥当（食品 listing・作中創作・自白 regex 正常動作）。ゲート改修不要。
- b9 1 回目 Strata 404（chat 同一サーバーの slot 競合で 8/8 呼出 404）→ T011 部分欠損、rm -f jsonl 後 max-calls 10 で再走（proc_c935d17fd6ee）。
- 教訓: バッチ実行中は agent 側 chat 呼出が slot を占有するため 404 多発。再走は低頻度ターン＋max-calls 増で対応。
- b9 収束（2026-11-24）: 6 篇 220 件（T011 再走込）→ 裁定 11 drop（野菜/兵器/種族一般名、类别語）。gate 21 件全件妥当（桃太郎 4 件・命名想起系自白 regex 正常）。台帳 b9 done（124/179 篇）。
- 注意: b9 で run 二重起動による jsonl 追記（T012/T109/T143 重複 47 行）→ publish norm で統合され出力は正常。以後 run_dir は起動前に proc 状態を確認し単一起動。
