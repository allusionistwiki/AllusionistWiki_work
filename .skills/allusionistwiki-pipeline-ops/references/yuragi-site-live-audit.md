# YuragiWiki site live 監査（content md 直読み・2 段）

公開面: https://allusionistwiki.github.io/YuragiWiki/ 。live HTML を這う監査は
rate limit（GitHub blob 連発 429→status 0 化）と trailing slash 404 偽陽性で全数完走が困難。
**content md を直接読む 2 段監査（site_audit3.py 型）**に収斂した。

## 手順
1. **page 全数 GET**: YuragiWiki repo `content/**/*.md` から URL を機械生成 → GET 200 全数。生成規則（live 判定は git 管理の content から導出する — public/ 由来・ローカル build 由来・push 済み HEAD 由来のどれでもない集合で検証すると全数 LINKFAIL/0 件の偽結果になる）:
   - `content/index.md` → `/YuragiWiki/`（site 直下は `/YuragiWiki/` 直。root bare `/index` は 404）
   - `<dir>/index.md` → `/<dir>`（trailing slash なしで照会）
   - その他 `<slug>.md` → `/<slug>`（percent-encode 必須・拡張子なし・trailing slash なし）
2. **href 全数 GET**: 全ページ本文の href を絶対化（`/YuragiWiki/` 接頭→BASE、相対→ページ URL 基準）→ 静的アセット（.css/.js/.json/.png 等・`static/`）除外 → 200 全数。
3. CI deploy 完了（run success）を待ってから走らせる（deploy 中の Pages 部分 404 は過渡。判定は成功確定後）。

## 実測（2026-11-19）
- **page 全数**: content 8229 ページ → 8229/8229 200（8 スレッド低速＋再試行）。
- **local md 直読み href 全数**: 3930 unique ターゲット → markdown リンク全 48,881 投稿 blob 参照＋site 内部リンク実在確認。github status 0 連発 = 10 スレッド以上の連発は GitHub 429 rate limit。blob 実在は 12/12 200 サンプルで担保済み（raw パスは `posts/` 込み `…/<dir>/posts/pNNNN.md` 形式、publish の `ref_url` は ③ 行 `file` 基準で正しい）。
- **trailing slash 404 規則**: `/<slug>/`（スラッシュ付き）は Pages で 404 になり得る。`/YuragiWiki/nav` 200。URL 生成は trailing slash なし。live href は Quartz が相対 `./` 出力（ブラウザ 301 解決で実運用は健全）。
- pageFail 301 検出例: frontmatter YAML 死の 301 works ページ（content−CI emitted 件数照合で検出→ yq() 生成時サニタイズで解消→ 差 0）。
- 収束後: pageFail 0・linkFail 0（full 分页・works permalink 含む site 内 href 全数）。

## 恒久則
- href 監査は live HTML 巡回でなく **content md を直接読んで href を機械抽出→GET**。live 巡回は rate limit とスラッシュ正規化で偽陽性が支配する。
- GitHub 参照の bulk GET は低速（≤8 スレッド・インターバル・429 再試行）。連発すると status 0 が大量に出て「壊链接」を装う。実在性の担保はランダムサンプリング 200 確認＋publish 生成規則の照合で十分。
- 大規模層追加時は「content ツリー件数 vs CI `Emitted N files` 件数」を機械照合（差>0＝frontmatter YAML 死）。
- local build（bootstrap-cli.mjs）は background 非 tty で `stdin is not a tty` 死。検証は CI 側ビルド＋live HTTP。
