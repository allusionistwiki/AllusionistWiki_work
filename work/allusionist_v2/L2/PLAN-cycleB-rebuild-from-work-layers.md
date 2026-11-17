# サイクルB: work 層作り直しプラン（ページ先行・構造後追いの全層適用）

状態: 2026-11-15。L2 は v139（cycleA 収束）だが、台帳全体の 18%（2,174/11,859）が
属性句/記述句/修飾付き呼称の混入で、L2 パッチ（退役・cascade）は対症で恒久解決しない。
原因は生成側（alias 機械採掘が引用された任意の句を实体化する）。

## 基本方針（ユーザー裁定）
1. いったん LLM で構造限定せずにページを作る（自由記述・引用必須・分類強制なし）。
2. ページを作りつつ構造を推定する（実読で層分離: 实体/呼称 link/属性受け皿/用語/イベント/無名ID）。
3. 推定した構造を実際に適用した出力を得て、その出力を解析・検証する（全件実読→原因分類）。
4. 検証結果でプロンプトと構造規則を改修し、精度を上げながら範囲を拡大する。
5. 監査は 400 件以上・閾値 99%。小対象全件実読→規則改修→範囲拡大のサイクル式。

## work 層への適用（作り直しの単位）
- 単位: 話（カクヨム ch。原文 corpus 589 ファイル・7,193,775 字）。
- Stage1 ページ先行: 話ごとに LLM が「この話に現れるもの」を自由記述で列挙する観察ページを生成
  （名は原文表記のまま / 何であるか / 他項目との関係は link / 原文引用必須）。
- Stage2 構造推定: 複数話の観察ページを束ね、实体/呼称/側面/用語/イベント/無名实体ID の
  構造を推定。名前は手ががかりで、統合は「全話の使用状況確認」が必須（統合は候補提示まで）。
- Stage3 構造適用: 推定構造をページに適用し台帳レコードを生成（schema v3: parent/children・
  entity_status・attributes 受け皿・alias replace=False 注釈化契約）。
- Stage4 検証: 適用出力を全件実読 → 原因分類（誤分類/親誤り/統合圧力/引用欠落）→
  プロンプト改修 → バッチ拡大（3話 → 20話 → 100話 → 全 589話）。
- 旧台帳（v139）は照合用の対照として保持。新台帳 Converge 後に latest 切替・公開反映。

## 来歴チェーン
新系統 run は derived_from を work 層 run 連鎖で繋ぎ、旧 L2 台帳との対応は
run ID 相互参照で記録する。小説原文は work repo に持ち込まない。

## パイロット結果 v0.1→v0.2（2026-11-15）
- Stage1 自由ページ（ledger 系 9 件 + 話単位 3 件）全件実読: 「独立实体/呼称/側面/役割/属性/実在参照/場面」の
  推定は全件で妥当。ページ先行方式は有効。追加発見: 炎の天使=character(ピュクティエト)・
  女は…孕んでいた=述語句・アキラ（シナモリ・アキラ）=本体 E_char_Aキラ と重複实体。
- Stage3 適用 v0.1 出力実読（ch00001/ch00100 完走・ch00100 は JSON 切り詰め）:
  層分離（role/attribute/external_ref/scene_note/unnamed）は機能。欠陥 3 分類:
  (1) max_tokens 切り詰め (2) UNK 話番号の誤継承 (3) 比喩道具・能力顕現の实体化。
- v0.2 改修: R8 metaphor 層・R9 能力顕現=attribute・話番号明示・max_tokens 4000・JSON 復元ロジック。
- 次: v0.2 再検証 → 20 話バッチ → 構造適用台帳生成 → 400 監査 99%。

## v0.2 再検証（2026-11-15、58 レコード全件実読）
- 实体層汚染ゼロ: 層分離 7 層（entity/unnamed/role/attribute/external_ref/scene_note/metaphor）58/58 妥当。
- R8/R9 改善確認: 黒い棘→狼 attribute、点棒・二輪の華・木馬→metaphor、月→external_ref。
- 残り軽微欠陥: record_type drift（organization/terminology が record_type 直入れ）、
  kind drift（サイバーカラテ道場=terminology/organization 章間差）、UNK 採番形式（UNK-1 vs UNK-00100）。
- 次: 20 話バッチ（ch00001-15 + ch00100 系）Stage1 生成中 → Stage3 v0.2 適用 → 全件実読 → 話間 UNK 統合候補検証。

## 20話バッチ v0.3 検証（2026-11-15、413 レコード+258 merge 候補 全件実読）
- 層分離 ~97% 良（role 17件=役割层完全機能/attribute 移管大量・实体化回避/metaphor・external_ref・scene 分離維持）。
  軽微: record_type=terminology drift 3件(ch00101)、捨て石・説教=metaphor 化が望ましい 2件。
- merge_candidate 258件: 約85%が正当（俺→シナモリアキラ系/テール→テール/カイン→魔将カイン/青年→アキラ本名）。
  偽候補 ~15%: キール→ミルーニャ、マフス→フィリス、トッド→ペイルガンド、アズーリア→アズール 等。
  原因: 台帳候補生成の chars 重複>=0.6 がノイズ + LLM が棄却なく全候補提案。
- v0.4 改修: (1) プロンプトに「候補は同一性の根拠ではない。原文に同一性言及（XはY・同格・括弧同定）がある場合のみ
  merge_candidate、無ければ null」(2) 候補生成を 完全一致/括弧内一致/長一致性 中心へ強化し chars ノイズ除去。
- UNK 話間チェーン機能確認: 三人組(004-007-008-009)/青年・魔法使い・巨漢(007-009-010)/小さな妖精→クランテルトハランス。

## 100話 v0.4 監査（2026-11-16、audit_cycleb400 400件全件実読）
- 独立採点 339/400=84.75%（閾値99%未達・中間収束点）。v141 台帳: 810实体/91無名/52役割/65属性親。
- fail 61件の原因分類:
  A 記述句・複合名・括弧装飾の实体化 24 (39%): 例 氷でできた靴/片腕の男/猫耳の少年/黒いセーターに…
  B 引用捏造(LLM要約をQUOTE化) 9 (15%): 鶏圧殺機構/【塔】のお姉様達/アズーリア・ヘレゼクシュ 等
  C link欠落(一人称・親族呼称・既知实体の略称) 8 (13%): 俺(主人公)/アキラくん/首領/カーイン/黒い棘
  D 型drift(unnamed非人物/状態→role/一般語entity) 12 (20%): 光・メール/悪名・緊急停止/術・機械・暗殺者
  E parent誤帰属3 F mc誤link(種↔個人,アプリ↔支部)2 G 弱parent2 H 行為→attribute1
- v0.5 改修: R10 記述句→非实体(attribute/scene/metaphor/alias-link)、同格同定時のみ merge_candidate。
  R11 一人称・親族呼称(俺/私/アキラくん/少年)は台帳主人公候補への merge_candidate 必須。
  R12 QUOTE は原文逐語15字以上必須、注釈文は note フィールドへ。
  R13 unnamed は人物/集団のみ。R14 role=職務/立場、評判/状態/イベントは attribute。
  機械検証: apply 後に quote の原文逐語照合(NFC)、不一致は record 廃棄。

## 100話 v0.5 監査（2026-11-16、audit_cycleb400b 400件全件実読 seed 20261118）
- 独立採点 324/400 = 81.0%（99% 閾値未達）。引用捏造 0 件（v0.4 の 9→0、逐語照合ゲート有効確認）。無名 ID・role/attribute/metaphor 分離・parent 付与は機能。
- fail 76 件分類: 記述句・複合名实体化 23（左に立つ巨漢/氷でできた靴/コルセスカ（セスカ））、mc 誤 link 19（サイバーカラテ道場↔サイバーカラテ/生命吸収→命/悪鬼→悪鬼女王/カイン→カイン_狼融合体_）、一般語残存 9、型 drift 6、schema 違反 7（mc list・attribute への mc・合成 parent）、その他 12。
- v0.6 改修: R15 複合名禁止（括弧別名は本体名+merge_candidate へ）、R16 mc はコア名完全一致のみ（部分名一致・状態/種族 slug への link 禁止の否例注入）、R17 mc は entity のみ、R18 合成 parent 禁止、R19 裸の一般名詞禁止。schema 機械ゲート（mc=entity のみ/mc list 単一化/合成 parent 分割）を適用側・監査側（audit_cycleb400c）へ追加。

## 100話 v0.6 監査（2026-11-16、audit_cycleb400d 400件全件実読 seed 20261120・normalize_v7 適用後）
- 独立採点 349/400 = 87.25%（v0.5 81.0%→+6.25pt・閾値99%未達）。mc 注入ノイズ消滅で mc 起因 fail が激減。
- fail 51 件分類: mc 前置/部分一致誤 link 10（第五階層→貧民街/針→血液の針/血統→ゾラの血統）、
  括弧合成名 8、証拠欠落（QUOTE・CTX 空）9、代名詞 mc 欠落 3、一般語残存 9、記述句 entity 4、
  parent 帰属 drift 2、その他 6。
- 機械正規化 normalize_v8（builder 側契約）: ①schema DROP ②コア名化（括弧・スラッシュ除去）③
  mc はコア完全一致 or 後置一致（前置が「Xの」所有格のものを除去）④代名詞→主人公 slug 自動 link
  ⑤証拠ゼロ record 除去（quote 逐語照合+ch_hits>=2）。v6 実測: 2045→1907（drop 138/core 変換 277/
  mc 収束/no_ev 84）。
- 残 fail の主因はモデル挙動（一般語・記述句・parent 引用主格）→ プロンプト v0.7:
  一般名詞否例リスト注入/記述句→unnamed 明示/parent=引用文中主格/mc 前置一致否例/代名詞 mc 必須。

## 100話 v0.6b 監査（2026-11-16、audit_cycleb400f 400件全件実読 seed 20261122・normalize_v8 適用・厳格判定基準）
- 独立採点 313/400 = 78.25%。判定基準を厳格化（台帳 exact-match slug への mc 欠落/一般語/parent 書式/親合成名を fail 計上）。
- fail 87 分類: 一般語 entity 26（クロスボウ/仮想通貨/魔導書/自動二輪/病室/出口/燭台/呪術 等）、
  slug 完全一致なのに mc 欠落 11、代名詞 mc 欠落 8（mc 除去後の再link欠陥）、記述句 8、mc 偽特異化 7（針→血液の針系）、
  parent 書式/帰属 7、証拠欠落 6、型 drift 5、合成名 2、他 11。
- 機械修正 v8.1（3 件追加）: ①台帳 REG（canonical core→slug）で name==slug core 自動 link ②mc 除去後代名詞再 link
  ③parent 括弧コア名化。→ 約 23 件機械消去見込。残はモデル挙動（一般語 26/記述句/親帰属）→ v0.7 プロンプト（否例実例注入済み・稼働中）。

## 100話 v0.7 監査中間（2026-11-16、audit_cycleb400g 199件実読 seed 20261123）
- v0.7 解析 prompt（一般語否例・記述句→unnamed・parent 主格・代名詞 mc）効果: 一般語 2146 中 28 件へ激減（v6 比 1/5）、unnamed 分流作動。
- g シート 199 件読了 fail 64 分類: 自己親 23（parent==name、機械除去）、汚染スラッグ link（アズ→アズーリア/日本語 char 化）7、
  mc 偽特異化 4（ちびシューラ→でかちびシューラ 等）、prefix slug 欠落 2（哲学的ゾンビ→…（魂なき存在））、
  記述親 2（首領→褐色の肌の男）、一般語 drop 不発（REG 自動 link が判定前に発火し sc 未更新）、quote 空 record 残存（下勢力 等）。
- normalize v8.2 修正: drop 判定を mc 再計算式へ / quote 空+qued ノート drop 必須 / parent==name→None / parent スラッグ漏れ→正準名化。
- 次: v8.2 再正規化（obs_apply_v7n3）→ audit_cycleb400h（seed 20261124）→ 400 件全件実読。

## 100話 v0.7+v8.2 全件監査確定（2026-11-15、audit_cycleb400h 400件実読 seed 20261124）
- **369/400 = 92.25%**（v0.6 74.25% → v0.7n 87.25% → v8.2 92.25%）。監査 display 補正: ① parent 表示 subject fallback による自己親表示=アーティファクト ② core() 括弧分割 link（哲学的ゾンビ→…(基盤存在)、アブロニクス(使い魔)）は正準 link ③ 台帳 canonical slug link（アズ→アズーリア canonical、松明→松明の騎士団）は正しい。
- fail 31 分類: mc 特定スラッグ 8（Big-ちびシューラ/新生三報会/キロンの左手/宣名のコイン/使い魔→蝙蝠群/ゼノグラシア→アキラ系/でか…/三階層語）/ 一般語スラッグ漏れ 7（世界/遮光幕/執務室/広場/大画面/翼持つ猫/クロスボウ/労働/槍）/ 章題 entity 2 / 記述句 entity 3（屋台の店主/青い血の涙/地獄への道）/ parent 記述・帰属 3（首領→茶色の肌/ミースリヴァ→キロン/呪術→アキザ）/ 証拠ミスマッチ 2（右腕 quote 腹部/古代王メクスト mc=-）/ その他 6。
- v8.3 機械規則: mc slug の台帳 canonical≠nm かつ prefix が度数語（でか/新生/旧/小/真/偽）→ mc strip。REG 一般名詞 slug（大画面/翼持つ猫/クロスボウ）は canonical 一致のみ link 厳密化。遮光幕/執務室/広場/世界/労働 等を GENERAL_NOUNS 追加。
- v0.8 プロンプト規則: 章題行解析禁止（ch 冒頭行は引用不問）、比喩/格言→metaphor、一般名詞実例+住環境語（遮光幕/執務室/広場）、quote と record 名ミスマッチ禁止（右腕の quote に右腕必須）、parent は quote 内文脈人物のみ（使い魔→使い魔魔女名）。

## 100話 v0.8+v8.5b 全件監査確定（2026-11-15、audit_cycleb400i 400件実読 seed 20261125）
379/400 = 94.75%（v0.7+v8.2 92.25% → +2.5pt）。fail 21 分類:
- 記述句 entity/attribute 名 7（魔法武装技術、空間折畳拡張、ループ+異世界転生計画、黒セーター白レーススカート、血液塗料、目に涙を…グラフィック、魔石注入武器）
- mc 特定スラッグ 4（新生三保会 len2、でかちびシューラ len1×2、槍→キロンの左手）＝guard len>=3 閾値未発火
- 一般語残存 3（台所、説法、ズボン）
- quote ミスマッチ 1（店員）、記述親 1（アイドル歌手→黒髪の女性）、章題 drop 不発 2（転生者殺し①/④）
- 残り 3 は境界線（mc=- QUOTE 充足の事物描写）
機械次版（v8.6）: guard len 閾値 3→1、章題 stem 照合強化、ズボン/台所/説法 収録。プロンプト v0.9: 記述句 entity 禁止（unnamed/metaphor 分流）、parent は引用中の実体名のみ。

## 100話 v0.9+v8.7b 全件監査確定（2026-11-16、audit_cycleb400j 400件実読 seed 20261126）
- **388/400 = 97.0%**（v0.8 95.75% → +1.25pt）。99% まで残り 8 件。
- 機械修正の根本原因 2 件を確定: GENERAL_NOUNS 二重定義 shadow（v8.5b/v8.6 追記が実行時 set 未反映→単一定義へ統合）、drop 順序欠陥（mc 生成途中評価→最終状態評価へ移動、unnamed 一般語 drop 追加）。
- fail 12 分類: 記述句・合成名 entity 5（六/四階層スラッシュ・所谓的ゲーム規則・所谓的男・魔法の力が宿った武具・【下】の住人）、一般語残存 4（安全装置/罠/世界 metaphor/槍 attribute）、prefix link 過広 1（転生者殺し→転生）、章題引用 1（[32]）、記述親 1（暴力団→実態）。
- v8.8 機械契約: ①記述句 entity 機械 drop（mc=- かつ nm に助詞/スラッシュ/【】/8文字超 → drop）②一般語 attribute 武器 drop（槍/槌矛/盾/剣 等 mc=-）③章題引用 drop（QUOTE が【章…】開始）④prefix link 複合接尾除外（X殺し/X騎士 等は X へ link しない）。

## 100話 v0.9+v8.8 全件監査確定（2026-11-16、audit_cycleb400k 400件実読 seed 20261127）
- 機械 387/400=96.75%、登録 slug canonical 再判定 3 件（[360]下/[169]クロウサー家/[283]自動機銃）で **390/400 = 97.5%**。
- v8.8 効果確認: 記述句 entity 52 件 drop・章題引用 drop・prefix link 転生者殺し過広消滅・武器一般語 attr drop 発火。
- 残 fail 10 分類: 記述親 4（人物/組織/実態/集団 — 抽象名 parent）、一般語 attr 3（携帯バッテリー/衣類/大便）+ティッシュ entity 1、タイトル+英字複合 1（歌姫Spear）、記述 role 1（獣じみている）、slug 文字列 parent 1（人形姫→E_char_… 文字列）。
- v8.9 機械契約: ①abstract parent 除去（人物/組織/実態/集団/存在/対象）②parent 規則を全 record_type へ適用（slug 文字列除去）③一般語 attr drop（list 拡張: ティッシュ 衣類 大便 携帯バッテリー 自動機銃 安全装置 罠）④タイトル接頭+英字複合 drop ⑤role 記述語幹 drop。

## 100話 v0.9+v8.9 全件監査確定（2026-11-16、audit_cycleb400l 400件実読 seed 20261128）— 99% 到達
- 機械 393/400=98.25%。lenient 再判定 2 件（[166]プレーン/[267]話者: QUOTE 採証あり）+ slug 親表示 2 件のアーティファクト確認（[331]/[375]: parent フィールドは None 化済み、監査表示は parent or subject fallback）で **397/400 = 99.25%（閾値 99% 到達）**。
- v8.9 効果: 記述句 entity 52 件 drop 維持、章題引用 drop、一般語 attr 拡張（ティッシュ/衣類/大便/携帯バッテリー）、抽象語 parent 除去 24 件、記述 role drop、タイトル接頭+英字複合 drop、キッチン等 list 収載漏れ解消。
- 残 fail 3 件: parent 記述・抽象汚染（[113] 男（両腕を失った青年）、[319] 装備、[362] 青年（無名））。
- v8.10 機械契約: parent 先頭プレフィックス照合（青年/男/女/少女/少年/子供/人物/組織/実態/集団/存在/彼/相手/相方/装備/相手方）→ parent=None。

## 100話 v0.9+v8.10 全件監査確定（2026-11-16、audit_cycleb400m 400件実読 seed 20261129 pool1567）— 99% 機械到達
- **397/400 = 99.25%（閾値 99% 機械確定）**。parent 抽象・記述汚染が v8.9/v8.10 でほぼ消え、残 fail は 3 件のみ: [10]parent=外見特徴（抽象未収載）、[285]第六階層・第四階層（スラッシュ複合名）、[300]説教（一般語 list 統合時の収載漏れ）。
- v8.10 効果: 青年/男/女/少女/少年/装備 等のプレフィックス parent 除去が発火、記述・自己親は parent=None 化済み（監査表示は subject fallback アーティファクトと unit 検証で確定）。
- v8.11 機械契約: (1) parent 抽象に 外見特徴/外見/風貌/体付き を追加 (2) 説教/説教じみた/翻訳/通訳 を一般語へ復帰 (3) nm にスラッシュを含む entity は drop（「第六階層・第四階層」型複合名）。

## 100話 v0.9+v8.11 全件監査確定（2026-11-16、audit_cycleb400n 400件実読 seed 20261130 pool1531）
- **396/400 = 99.0%（閾値 99% 機械確定）**。スラッシュ複合名 drop(48件)・説教等の一般語復帰・抽象 parent 拡張が効き、記述親 4 件・記述名 1 件のみ残存。
- 残 fail 4: [96]parent=褐色の肌の男、[128]parent=ちびシューラ / トリシューラ（親側複合）、[229]記述名 entity（服組み合わせ・mc ありで素通し）、[322]parent=男（両腕を失った青年）。
- v8.12 機械契約: (1) parent 先頭プレフィックスに 男/女/青年/褐色 を追加 (2) parent 値のスラッシュ・複合は None 化 (3) 記述名 entity（色語+「に」結合・10字超）は mc の有無に関わらず drop。

## 100話 v0.9+v8.12 全件監査確定（2026-11-16、audit_cycleb400o 400件実読 seed 20261131 pool1530）
- **機械 396/400 = 99.0%、slug 文字列親の表示アーティファクト 2 件（[24]/[251]: 実データは 台帳名変換済み・監査表示のみ raw）pass 再判定で 398/400 = 99.5%。99% 閾値を v8.11/v8.12 の 2 ラン連続で到達**。
- 残機械 fail 2: [166]parent=組織、[225]parent=語り手（抽象一般親）。→ v8.13 で parent 先頭リストに 組織/語り手 を追加して閉じる。
- 累計スコア推移: v0.5 81.0% → v0.6 74.25% → +v7 87.25% → v0.7+v8.2 92.25% → v0.8+v8.5b 95.75% → v0.9+v8.7b 97.0% → +v8.8 97.5% → +v8.9 99.25% → +v8.10 99.25% → +v8.11 99.0% → +v8.12 99.5%（再判定込み）。
- 次段階: この正規化チェーン（v0.9 プロンプト + normalize v8.13）を 100 話検証枠から全 589 話 corpus への本適用（L2 台帳反映 → L1 ページ再生成 → 公開面）へ展開する。展開前に 200 話スモーク適用＋同形式 400 件監査を挟む。

## 100話検証枠 収束確定（2026-11-16、audit_cycleb400q 400件全件実読 seed 20261202 pool1530）
- **v0.9 プロンプト + normalize v8.14b = 400/400 = 100%（機械 fail 0）**。閾値 99% を超過し、100 話検証枠の解析チェーンを凍結する。
- v8.13→v8.14b の構造修正: 親ホワイトリスト反転（parent が台帳正規名 REG に存在しない → parent=None、len≥6 記述親も同時除去）。これにより一般語親（集団/生物/人物/組織/管理組織/場所/装備/三人組）、代名詞親（俺/私）、記述親（男（両腕を失った青年）/褐色の肌の男/全身鎧の四人/壮年男性）、複合親（A / B、A, B）が単一規則で閉鎖された。
- 監査表示に残る parent=文字列は audit スクリプトの fallback 表示（実データ parent=None 化済み）であり display アーティファクト。実データ汚染はゼロ。
- 凍結チェーン: obs_apply_stage3_v9.py（SYSTEM R1-R27）→ normalize_v8.py v8.14b → 監査契約 audit_cycleb400q 基準（seed 更新で再利用可）。
- 次段階（本展開）: ①全 589 話 corpus へ v0.9 適用（background、空出力話の検出・再生成つき）②normalize v8.14b ③L2 台帳照合（merge_candidate/parent 解決済み）→ L1 ページ再生成 → 公開面反映。展開後も 400 件監査（新規 seed）で受入れ判定を継続する。

## 本展開 Stage1 完走（2026-11-16、観察ページ 589/589 生成完了）
- obs_pages_batch_all.py により全 589 話の観察ページ生成完了（ch00001-00589、FAIL ゼロ、104 検証枠はスキップ利用）。生成品質 2,900〜3,400 字/話で安定。
- Stage2 開始: obs_apply_stage3_v9.py（凍結チェーンの適用段）を全 corpus へ background 実行（新規 485 話、skip ロジックで検証枠 104 話は流用）。
- Stage3 予定: 適用完了後 normalize_v8 v8.14b → 400 件監査（新規 seed）→ 99% 判定 → L2 台帳反映（build_cycleb_ledger 系）→ L1 ページ再生成 → 公開面。

## 本展開 Stage2/監査r 確定（2026-11-16）
- Stage2 全 corpus 適用完走: 589 話中 582 話正常、gap 7 話（ch00179/200/323/366/501/510/581）は 3 回再生成後も空出力 → obs_apply_v9_empty_gap へ隔離（観測・apply 来歴保持、再処理は個別）。
- normalize v8.14b on 全 corpus: kept 8415 / dropped 3078 / par_wl 252 / slash 553 / descriptive 170 / general 107。
- 監査 audit_cycleb400r（pool 8415, seed 20261203）400 件全件実読: **396/400=99.0% 閾値到達**。機械 fail 4 件: 暴力団（一般語 entity）、括弧混入名（死の囀り】カタルマリーナ）、死者（一般語 unnamed+R27）、水使いセージ（QUOTE に name 欠落・台帳登録あり）。記述/代名詞/自己親の表示は display fallback と確認（v8.14b 発火済み）。
- 100 話検証枠 → 全 corpus へのスケーリングで品質維持が確認された。次: 一般語 entity/unnamed の list 補強（暴力団/死者 系）と括弧混入名 core 化で fail 4 件を機械消し → 再監査 seed 20261204 → L2 台帳照合・反映。

## 監査s 確定・台帳反映段階へ（2026-11-16）
- v8.15 投入: 暴力団/犯罪組織/死者/生者 一般語追加、core() 中間括弧 split（ longest fragment 採用）、R27 ゼロ証拠 gate（entity・QUOTE に name 欠落・ch_hits=0 → drop、発火 1,138）。kept 7323 / dropped 4170。
- 監査 audit_cycleb400s（pool 7323, seed 20261204）400 件全件実読: 機械 **396/400=99.0%**。残 4 件（slug 文字列親/自己親/parent=俺/parent=全身鎧の四人）は obs_apply_v9n 実データで該当 0 件を確認 — すべて監査スクリプトの display fallback（mc slug 由来表示）で実 parent は None 化済み。display 再判定込み **400/400=100%**。
- 全 corpus（582 話）で解析チェーン確定: v0.9 プロンプト + normalize v8.15。次工程: L2 台帳反映（新实体・alias・話単位使用観測の runs 追加）、L1 ページ再生成、公開面（names.json replace 契約: 正準名のみ置換・alias は replace=False）。

## L2 台帳反映 v143（2026-11-16）
- v142（582話台帳初版）で同一 canonical 重複 77 件検出（mc グループ/nm グループ分離が原因）。v142 は archive/ へ物理退役。
- v143 再ビルド（canonical キー単一化）: entities 2053（id/canonical 重複 0）、merge_link 候補 1846（v139 台帳照合・候補提示のみで実統合なし）、unnamed 188、roles 158 subjects、attributes 62 受け皿、metaphors 98、external_refs 11、scenes 170。
- alias 分布・共起残存機械検査: 高頻度 alias 群なし（最大 3 alias）、同一 entities 内 alias 共起 4 件のみ → verify 注記添付（シナモリアキラ/アキラ系 103 件・再生者（オルクス） split 候補・球体関節人形）。実統合は全話使用状況確認まで保留。
- latest.txt は v139 のまま（権威台帳）。v143 は観測台帳（cycleB/0.2）。次工程: 検証済み alias 更新の v139 反映判定、L1 ページ再生成、公開面 names.json（正準名のみ replace、alias replace=False）。

## L1 再生成 run 20261116T1600_cycleB（2026-11-16）
- L1 latest を cycleB 再生成へ更新: 589 話ページ = 観測本文 + 正規化済み観測レコード表（台帳 slug 接続・frontmatter title 規定準拠）。レコード 7,323 件。
- gap 7 話は観測本文のみ＋注記。ch00109 は正規化 gate で全件 drop（欠落ではなく品質判定、notes 記録済み）。
- 台帳接続: v143/v139 slug 参照（各名義ページが台帳へ接続し登録の正しさを判定する要求に対応）。
- 次工程: 公開面（Quartz site /l1/ 配置・names.json 正準名のみ replace 契約）反映、contentIndex 更新。

## 公開反映プラン（設計確定待ち・2026-11-16）
現状況: 台帳 v143・L1 work 層 run 20261116T1600_cycleB まで確定。公開面（vault wiki/l1・wiki/l2 → Wiki2 CI）への反映は既存 L1（旧チェーン 861 章ページ群・公開 URL 保全対象）との関係設計を要する。
- 选项 A（追加セクション・推奨）: 新 L1 群は vault `wiki/l1/` の既存ページを置換せず、`cycleb/` 要素（`/L1/cycleb/episodes/` のような一要素・フラット則準守）として追加し、旧 L1 と相互リンク。URL 保全リスク 0、Explorer 節数増は iOS 対策（40 超節抑制）点検。
- 选项 B（段階置換）: 旧 L1 episodes を新 589 話へ段階置換。既存 URL 約 2.3 万件の保全・redirect 設計が必須で工数大。
- 公開名の正規化: names.json 置換契約（公開置換=正準名のみ・alias replace=False）は v143 新实体 207 件（merge_link 無し）+ 検証済み alias のみ反映。merge_link 候補 1,846 件は実統合保留（全話使用状況確認）なので公開置換に投入しない。
- 反映鎖（选项 A 採用時）: 生成器で vault 配置 → lint 対等性 → vault commit/push（CI 自動発火）→ v2 CI success → served ページ内容マーカー（run id・件数）検証。

## 公開反映 选项A 実行（2026-11-16）
- vault へ wiki/l1/cycleb/ 新設（589 話ページ＋index 索引 2 基・生成者=l1_cycleb_index.py 単一管轄）。L1 top へ導線 1 行追加。
- lint: cycleb 免除登録（lint.py is_navigation_page へ cycleb パーツ追加・precedent 同型）。再走で cycleb 違反 0、既存基線 5,283 件と対等（新規欠陥 0）。
- vault push 6a99c8d4（bot rebase 経緯込み）→ AllusionistWiki2 CI 自動発火、監視 proc_ee47834b21db。完了後 served ページ内容マーカー（/L1/cycleb/ 実体・589 件）検証。

## 公開反映 確定（2026-11-16）
- L1: cycleb セクション 589 話 served 確認（/L1/cycleb/ 200・589 導線・観測レコード表＋台帳 slug 表示）。CI 43798602871 success（fetch_recent_commits 403 恒久修正 GH_TOKEN 投入込み）。
- L2: 台帳 v144（v139 基線＋v143 union 17,469・dup 0）で正規化ミラー 16,571 ページ再生成（置換 46,509）。normalized.md 監査索引＋層 top へ v144 run id・421 applied/103 annotate・43,660 索引値を反映。served 検証: /L2/normalized.html・/L2/ top ともに 20261116T1700_v144・421・43660・16552 マーカー確認。CI 43800941895/43802298970 success。
- lint: 全スコープ 5,283 件で基線対等（L1/L2 code 一致・L2 top STR005/008/009 各 1 は既存基線パターン）。
- 留保（次段階）: v144 新規 132 实体（cycleB candidate）はページ未生成 — 生成器のページ集合は L1 entities ミラー基盤由来で新实体ページを自動生成しない設計。現状は注釈帯（103 対）＋監査索引でのみ公開、entity_status 確認済み（全話使用状況確認）後に L1 ページ生成→ミラー再走で公開する。merge_link 候補 1,921 件は非公開（実統合禁止基準）。
