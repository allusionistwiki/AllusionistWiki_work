# L0 — 版対応層（edition map）

なろう版（正典 baseline・¶N = vault raw `【pN】` 章通し）とカクヨム版（¶N 原生）の
対応を「引用全文一致」で導出する層。**原文テキストは置かない**（引用は facts 内の引用範囲まで）。

## 方針（2026-10-17 確定）

- **カクヨム参照は ¶N 原生**。カクヨムサイトは段落 DOM アンカー `#pN` を持つ
  （`https://kakuyomu.jp/works/{work_id}/episodes/{ep_id}#pN` で段落直リン可）。
  したがって ¶N は外部解決可能なアンカーであり、vault 流 `pN` への変換・再採番は行わない。
- 対応表は**引用単位**: baseline facts の引用文をカクヨム版巻別コーパスで全文検索し、
  完全一致した引用はカクヨム `(ch, ¶N)` を確定。**不一致のみ再解析**（LLM 抽出）に回す。
- 話対応（episode map）はタイトル照合ではなく**引用ヒットから導出**する
  （カクヨム巻1は 31話すべて同一タイトル「無彩色の左手、鎧の右手①..㉛」であり、
  タイトルがなろう章境界を持たないため）。
- 来歴: `run.json.derived_from` = L1 baseline run ID + raw 台帳所在。連鎖を切らない。

## 産出物（runs/<run_id>/）

| ファイル | 内容 |
|---|---|
| `run.json` | 実行メタ・`derived_from`・統計 |
| `quote-map/chNNNNN.jsonl` | 1引用1行 `{s_para, quote_head, k:[kc,¶start,kc,¶end], type}` |
| `episode-map.jsonl` | なろう ch → ヒットしたカクヨム ch 集合（`hit-derived` / `needs_review`） |
| `kakuyomu-only.jsonl` | 引用ヒットのないカクヨム話（新解析対象 = 5-70 以降など） |
| `needs-reanalysis.jsonl` | 完全一致しなかった引用の再解析キュー |

## 再生成

`python scripts/build_quote_map.py`（台帳・vault raw・baseline run が同一であること）。
run は追加専用・退役は `archive/` へ。
