# L0 層（yuragi）— 台帳・索引・監査

5 層設計（`work/yuragi/README.md` 参照）における台帳層。v2wiki L0 と同一構図:
`README.md` / `latest.txt` / `runs/`（追加専用）/ `archive/`（退役 run の物理移動先）。

## 層定義

- 台帳 v3: 篇メタ（①〜⑤ SHA）・投稿台帳（ref・② 内 body 座標・chain_id）・chunks（④ ビュー＋ LLM 窓）。
- 検索索引 run（派生）: posts / by-author / by-date / terms。
- 監査 run（派生）: 全量 A1〜A5（下記ゲート）。

## 検証ゲート（監査 A1〜A5・全件・サンプリング禁止）

- A1 台帳×raw: ① 再パース一致（post_no/author/date）、② slice == ③ body 全 48,891 件 disk 実測
- A2 ④ chains: 純分割・単一作者・台帳列順連続・話題規則（【…】部分集合）再生成一致
- A3 ⑤ thread: body_full == ③ 全文連結（投稿順）全 185 篇
- A4 chunks: 全 post ちょうど 1 窓・群窓連続・② manifest SHA 一致（disk 再読）
- A5 索引: posts 完全性・スニペット全件再生成一致・by-date 単調・terms 全件再集計一致・投稿番号順逆行 counter（裁定事項は adjudication 記録）

## 規約（恒久）

- 座標 = raw バイト基準（改行変換なし）。読み `read_bytes().decode('utf-8', errors='replace')`、書き `newline=""`。
- 生成側検証は disk round-trip。latest.txt は台帳チェーン専用（派生 run で更新禁止）。
- run 産出は `runs/<run_id>/` 追加専用・`run.json`（derived_from 来歴）必須。退役は `archive/` へ物理移動。

## 現況

- 台帳 `20261114T0412_l0c`・索引 `20261114T0412_l0si`・監査 `20261114T0432_l0aud` PASS。
- 旧 1 層設計（v1/v2・2026-11-11 系）はリセット（`838f412`）で撤去済み・来歴は git 履歴。
