---
title: "Amplify Gen2 のビルドをカスタム Docker イメージで 10〜20% 高速化する"
emoji: "🐳"
type: "tech"
topics: ["aws", "amplify", "docker", "cicd", "pnpm"]
published: true
---

## はじめに

Amplify Gen2 のビルドを **カスタム Docker イメージ** に差し替えて、stagingのビルド時間が **中央値で 9m43s → 8m45s に縮みました**。率にして **約 10%、1 ビルドあたり 1 分の短縮** です。フレームワーク次第では **10〜20%、Next.js なら 50〜70% 短縮** が狙える施策で、さらに副次効果として **外部ダウンロード起因のビルド失敗がゼロ** になりました。

この記事は、Amplify Gen2 のカスタムビルドイメージ運用を実際に本番適用した知見を、設計 → 実装 → 実測 → 運用 Tips の順でまとめたものです。対象読者は、Amplify Gen2 でモノレポを運用していて「ビルドをもう少し速くしたい」「外部ダウンロード起因のビルド失敗を根本から潰したい」と感じている開発者です。

## なぜカスタムビルドイメージを作ったのか

対象の自社アプリは `apps/web-app` (Vite + React) と `packages/gen2-shared-backend` (Amplify Gen2 バックエンド、Hono Lambda、CDK カスタムリソース) を抱えた pnpm ワークスペースのモノレポです。デフォルトの Amplify ビルドイメージで走らせていた時期、毎ビルドで以下のコストを払っていました。

- `nvm install 22` で Node.js を入れ直す: 約 15 秒
- `corepack enable && corepack prepare pnpm@10.28.1 --activate`: 約 10 秒
- Chromium Lambda Layer ZIP (64MB) を GitHub Releases から `curl`: 約 20〜40 秒
- **`pnpm install --frozen-lockfile` を Store 空状態から回す: 60〜90 秒**

この合計だけで毎回 2〜3 分消えています。そして後述しますが、数字以上に厄介だったのは **安定性** の方でした。

### きっかけは深夜のビルド失敗

引き金になったのは `2026-03-22` にステージングのバックエンドビルドが壊れた件です。原因を追いかけたら、`curl` で取ってきた Chromium Layer ZIP が破損していて `Could not unzip uploaded file` で落ちていました。GitHub Releases の一時的な不調だったようですが、`curl` に `--fail` すら付いていなかったので、HTTP エラー本文がそのまま ZIP としてファイルに書き込まれていたのです。

ビルドログは `docs/build-fix-logs/2026-03-22-staging-backend-chromium-layer-download-failure.md` に残っていて、チーム内では「P4: 外部アセットダウンロードのサイレント失敗」パターンとして汎用チェックリスト入りしました。

この時点で打ち手は 2 択でした。

1. `curl` に `--fail --retry 3 --retry-delay 5` を付けて、ファイルサイズ検証も足して、`amplify.yml` を丁寧にしていく
2. **そもそも Chromium Layer をビルドイメージに焼き込んで、ダウンロード自体をなくす**

1 は毎回 20〜40 秒のダウンロードが残るしネットワーク失敗リスクもゼロにはならない。2 なら一度焼けば永続で、ついでに nvm や pnpm セットアップも丸ごと消せる。2 を選びました。

## マルチステージ Dockerfile の設計

`docker/Dockerfile` をマルチステージで切って、同じベースから 2 種類のイメージを生やしました。

| ステージ | タグ | 用途 | サイズ |
|---|---|---|---|
| `build` | `latest` | Amplify カスタムビルド + GitHub Actions の lint/build | 約 800MB |
| `e2e` | `e2e` | GitHub Actions の Playwright E2E | 約 1.4GB |

### ベースイメージ選定でやらかした話

最初は `node:22-bookworm-slim` で書き始めました。Debian ベースなので軽いし、Node.js の公式イメージだしで無難な選択に見えます。

が、これで組んだ Dockerfile を Amplify に食わせたところ、ビルドが通ったり通らなかったりしました。決定打は **Amplify のデフォルトビルドイメージが Amazon Linux 2 (現行は 2023) ベース** だという事実です。glibc のバージョン差で `ampx` や `aws-cdk` が拾うネイティブモジュールの挙動がブレるリスクがある。

ということで早々に `amazonlinux:2023` に書き直しました (`ae41ffd1`)。Amplify のデフォルトと同じ OS を選ぶ、これが一番シンプルで安全です。

```dockerfile
FROM amazonlinux:2023 AS build

ENV PNPM_HOME="/root/.local/share/pnpm" \
    PNPM_STORE_DIR="/root/.local/share/pnpm/store" \
    BUN_INSTALL="/root/.bun" \
    NVM_DIR="/root/.nvm" \
    CHROMIUM_LAYER_DIR="/opt/chromium-layer" \
    CHROMIUM_LAYER_VERSION="v127.0.0"

ENV PATH="$PNPM_HOME:$BUN_INSTALL/bin:$PATH"

RUN dnf update -y && dnf install -y \
    git openssh-clients bash jq tar wget zip unzip gzip \
    which findutils procps-ng ca-certificates \
    && dnf clean all && rm -rf /var/cache/dnf
```

### 同梱ツール

- **Node.js 22 LTS**: nvm 経由でインストール
- **pnpm 10.28.1**: corepack で固定。ワークスペース管理には引き続き pnpm を使う
- **bun**: `--filter` や CDK/ampx 互換性の観点から完全移行は無理だが、hono Lambda の isolated install と tsx 実行だけ bun に寄せて高速化
- **AWS CLI v2**: `ampx`・`appsync`・`ssm` など Amplify 運用コマンドで必須
- **aws-cdk**: グローバルインストール
- **Chromium Lambda Layer v127.0.0**: ZIP を `/opt/chromium-layer/` にプリベイク。ダウンロード後にファイルサイズを検証して 1MB 未満なら即ビルド失敗にする

```dockerfile
RUN mkdir -p "$CHROMIUM_LAYER_DIR" \
    && curl -fSL --retry 3 --retry-delay 5 \
       -o "$CHROMIUM_LAYER_DIR/chromium-${CHROMIUM_LAYER_VERSION}-layer.zip" \
       "https://github.com/Sparticuz/chromium/releases/download/${CHROMIUM_LAYER_VERSION}/chromium-${CHROMIUM_LAYER_VERSION}-layer.zip" \
    && LAYER_SIZE=$(stat -c%s "$CHROMIUM_LAYER_DIR/chromium-${CHROMIUM_LAYER_VERSION}-layer.zip") \
    && if [ "$LAYER_SIZE" -lt 1000000 ]; then \
         echo "ERROR: Chromium layer is only ${LAYER_SIZE} bytes"; exit 1; \
       fi
```

ポイントは **`curl -fSL --retry 3` + サイズ検証** をイメージビルド時点で走らせることです。ここで失敗すればそのバージョンのイメージが ECR に上がらないだけなので、本番 Amplify ビルドが夜中に壊れる経路を根本から潰せます。

### pnpm Store パスを全コンテキストで固定する

これが一番効く小技です。pnpm のインストール速度は、tarball が Content-Addressable Store にあるか否かで決まります。

- Store 空 → 60〜90 秒 (毎回フルダウンロード)
- Store あり → **5〜15 秒** (ハードリンクを張るだけ)

Dockerfile・Amplify ビルド・GitHub Actions の 3 コンテキストすべてで `PNPM_STORE_DIR` を同じパスに揃えて、Amplify の `cache.paths` にそのパスを追加します。ここが揃っていないと 2 回目以降もフルダウンロードになるので要注意。

```dockerfile
RUN . "$NVM_DIR/nvm.sh" \
    && corepack enable \
    && corepack prepare pnpm@10.28.1 --activate \
    && pnpm config set store-dir "$PNPM_STORE_DIR" \
    && pnpm --version
```

## amplify.yml の簡素化

カスタムイメージ適用後の amplify.yml がどう変わったかが、読み手にとって一番わかりやすい Before / After です。

### Before

```yaml
version: 1
backend:
  phases:
    preBuild:
      commands:
        - nvm install 22 && nvm use 22
        - corepack enable && corepack prepare pnpm@10.28.1 --activate
        - |
          curl -L \
            -o packages/gen2-shared-backend/layer/chromium-v127.0.0-layer.zip \
            https://github.com/Sparticuz/chromium/releases/download/v127.0.0/chromium-v127.0.0-layer.zip
        - pnpm install --frozen-lockfile
```

毎回 Node.js を入れ直し、pnpm をセットアップし、64MB の ZIP を GitHub Releases から落としてから本題のインストールに入っています。`curl` には `--fail` もリトライもサイズ検証もありません。

### After

```yaml
version: 1
backend:
  phases:
    preBuild:
      commands:
        # カスタムイメージ前提なら pnpm は既にある。念のため fallback
        - command -v pnpm >/dev/null 2>&1 || { nvm install && nvm use && corepack enable && corepack prepare pnpm@10.28.1 --activate; }
        # Chromium Layer はイメージに焼き込み済み。コピーだけ
        - |
          LAYER_DIR=/opt/chromium-layer
          if [ -f "$LAYER_DIR/chromium-v127.0.0-layer.zip" ]; then
            cp "$LAYER_DIR/chromium-v127.0.0-layer.zip" packages/gen2-shared-backend/layer/
          fi
        - pnpm install --frozen-lockfile
cache:
  paths:
    - /root/.local/share/pnpm/store
    - node_modules/.pnpm
    - apps/web-app/.build-cache
    - packages/gen2-shared-backend/.build-cache
```

`command -v pnpm` のフォールバックを残しているのは **カスタムイメージ未設定の環境でも壊れないため** です。実際これを入れ忘れてステージングを一度壊しました (`BMG-2075`)。`d29d16bd` でフォールバックを消した瞬間、Amplify が諸事情で標準イメージにフォールバックしていたブランチが `pnpm: command not found` で全滅します。カスタムイメージは **有れば速く、無ければ従来通り動く** 設計にしておくのが安全です。

## 実測結果

`aws amplify list-jobs` から staging のビルド時間を引いて、カスタムイメージ適用前後の成功ジョブで集計したのがこちらです。

| 区間 | 件数 | 中央値 | トリム平均 (上下 10% 除外) |
|---|---:|---:|---:|
| **Before** (適用前 38 ジョブ) | 38 | **9m43s** | 9m48s |
| **After** (適用後 57 ジョブ) | 57 | **8m45s** | 8m53s |

**短縮は中央値で約 58 秒、率にして 10.0%**。1 ビルドあたり 1 分、週 50 本のビルドが回るリポジトリなら週 50 分のリードタイム短縮になります。

### フレームワーク特性が効果を左右する

ここで重要なのは **効果の上限はフレームワーク特性で決まる** という点です。PR #1179 の設計時にフレームワーク別の期待短縮率を整理してあって、実測はちょうどその Vite 帯の中心に着地しました。

| フレームワーク | 初回ビルド | 2 回目以降 | 短縮率 |
|---|---|---|---|
| Next.js (SSR) | 90〜150s | 30〜60s | **50〜70%** |
| React Router v7 / Remix | 30〜60s | 25〜50s | 10〜20% |
| **Vite (自社アプリの現行構成)** | 60〜90s | 50〜80s | **10〜15%** |

実測値 10.0% は Vite 帯の中心に着地。**自分のプロジェクトがどの帯に入るか** を判断することで、この施策をやる価値があるかを事前に見積もれます。

Vite がキャッシュの恩恵を受けにくい理由はシンプルで、**Vite がプロダクションビルド用の永続キャッシュを持っていないから** です (`vitejs/vite#15092`)。`node_modules/.vite/` は dev server 用の依存プリバンドルで、`pnpm build` 側では効きません。結果として、pnpm Store キャッシュで稼げる分だけが純粋な改善になります。

一方、Next.js の `.next/cache/webpack` は Webpack/SWC コンパイル済みチャンクを永続化する本物のビルドキャッシュです。2 回目以降の短縮率が桁違いで、**Next.js 運用中のチームはこの施策をやる価値が桁違い** と言い切れます。

## 時間短縮以外の 3 つのリターン

実は 1 分の短縮自体より、以下 3 つの副次効果の方が体感的には大きいリターンでした。

### 1. ビルド失敗がゼロになった

これが一番大きい。導入前は月に数回、Chromium Layer の `curl` 失敗や GitHub Releases のレート制限でビルドが赤く染まっていました。深夜にリリースを止め、朝の会議前にリトライする、というやつです。

導入後、**外部ダウンロード起因のビルド失敗は一件も起きていません**。ZIP はイメージに焼き込み済みで、イメージはビルド時にサイズ検証付きで作っているので、本番 Amplify ビルドが走る時点では「ファイルが存在することが数学的に保証された状態」です。

1 分の平均短縮よりも、**ビルド失敗を踏まない安心感** の方が、体感的な開発速度への寄与は大きいと思っています。

### 2. 環境変数「どの Node.js バージョンで動いてますか」が消えた

Amplify の標準イメージは定期的に中身が更新されます。ある日突然 Node.js のマイナーバージョンが上がっていたり、プリインストールツールが入れ替わったりする。これまで何度か「ローカルでは通るのに Amplify で落ちる」を踏んでいました。

カスタムイメージに切り替えた後は、`amazonlinux:2023` + `Node.js 22 LTS` + `pnpm 10.28.1` が **全環境で同一バージョンに固定** されます。ローカル・CI・4 つの Amplify 環境 (prod / staging / enbase-prod / ehime-stg) が同じ Dockerfile から派生したランタイムで動く。再現性の基盤として地味に効きます。

### 3. 次のプロジェクトで効果が倍増する

次に走らせるプロジェクトが Next.js になる予定です。同じイメージを使い回せば、Next.js 側では設計通り **50〜70% の短縮** が狙えます。Vite 現行プロジェクトでの 10% はあくまで最初の一歩で、プロジェクトが増えるほど投資対効果が加速する構造です。

カスタムイメージは **一度作れば横展開のコストがほぼゼロ** という性質があるので、モノレポを複数持つ組織ほど効きます。

## 余談: GitHub Actions にもそのまま使える

今回作った Docker イメージは Amplify 専用ではありません。**GitHub Actions の `container:` にそのまま指定できます**。ランナーの `setup-node` / `setup-pnpm` を丸ごと省略できるので、CI 側でも数十秒〜 1 分程度の短縮になります。

```yaml
jobs:
  e2e:
    runs-on: ubuntu-latest
    container:
      image: public.ecr.aws/<your-ecr>/amplify-build:e2e
    steps:
      - uses: actions/checkout@v6
      - uses: actions/cache@v5
        with:
          path: /root/.local/share/pnpm/store
          key: pnpm-store-${{ hashFiles('pnpm-lock.yaml') }}
          restore-keys: pnpm-store-
      - run: pnpm install --frozen-lockfile
      - run: pnpm test:e2e
```

`e2e` ステージには Playwright + Chromium も焼き込んであるので、CI 側の `npx playwright install` も不要になります。**「Amplify と GitHub Actions でランタイムがズレてる問題」が構造的に消える** のが一番のメリットで、`actions/cache` の pnpm Store キーを Amplify と合わせれば、そのままキャッシュ設計も共通化できます。

Amplify のためだけに Dockerfile を書くのは腰が重い、という人ほど「どうせ CI でも使うから」という理由で投資判断しやすいと思います。

## 運用 Tips

最後に、実際に運用して引っかかったポイントをいくつか。

### NODE_OPTIONS の罠

初期の Dockerfile に `ENV NODE_OPTIONS="--max-old-space-size=6144"` を入れていたら、Amplify の STANDARD_8GB コンピュートでも OOM Killer に刺されました。原因は pnpm と Vite と tsx を同時起動した時の瞬間的なピークメモリが 6GB を超えていたことと、`NODE_OPTIONS` がすべての Node プロセスに継承されてしまうこと。

一度 `6144 → 4096` に下げて様子を見て、最終的には **Dockerfile から `NODE_OPTIONS` を消す** のが正解でした (`482b0137`)。Amplify 側の実行環境が必要に応じて制御してくれます。カスタムイメージで環境変数を固定しすぎると Amplify の知恵を無効化してしまうので、悩ましい場合は **イメージ側は素の状態にしておく** のが無難です。

### rsync は入っていない前提で書く

postBuild で `.map` ファイルを除外コピーするのに `rsync --exclude='*.map'` を使っていたら、Amplify のデフォルト環境に rsync が入っておらずエラーになりました (`42ec162c`)。

```bash
# Before
rsync -a --exclude='*.map' dist/ out/

# After (find + cp の組み合わせで代替)
mkdir -p out && (cd dist && find . -type f ! -name '*.map' -exec cp --parents {} ../out/ \;)
```

カスタムイメージに rsync を足せば済む話ですが、「Amplify 環境で動くことを保証する amplify.yml」はカスタムイメージ前提に書きすぎると壊しやすい。**カスタムイメージがなくても動く** ラインは極力守る方が運用は楽です。

### 段階導入はコミットメッセージで見分けがつくようにする

ECR Public リポジトリにプッシュするタグを `v1.0.0` / `v1.1.0` と振っておいて、Amplify 側の環境変数 `_CUSTOM_IMAGE` で切り替えられるようにしました。`latest` 固定だとロールバックが効かないし、どの Amplify ジョブがどのイメージで走ったか後から辿れません。

```bash
# staging だけ新バージョンで様子を見たい時
aws amplify update-app \
  --app-id <YOUR_STAGING_APP_ID> \
  --environment-variables _CUSTOM_IMAGE=public.ecr.aws/<YOUR_ECR>/amplify-build:v1.1.0
```

`list-jobs` で `jobSummaries[].commitMessage` と突き合わせれば、どの施策がどのビルドで効いたかを後から定量評価できます。まさにこの記事の計測がそれでした。

## まとめ

- Amplify Gen2 × モノレポ × Vite の環境で、カスタム Docker ビルドイメージへの差し替えは **ビルド時間を中央値で約 1 分 (10%) 短縮** しました。フレームワークによっては **10〜20%、Next.js なら 50〜70%** が現実的な射程です
- 期待短縮率はフレームワーク特性で決まります。Vite は 10〜15%、React Router v7 / Remix は 10〜20%、Next.js は 50〜70%。**自分のプロジェクトがどの帯かを見極めた上でやる価値を判断** できます
- 時間短縮と合わせて、**外部ダウンロード起因のビルド失敗がゼロ**、**全環境のランタイムバージョン統一**、**次のプロジェクトで横展開コストゼロ** という副次効果が大きい
- カスタムイメージを入れる時は、**「無くても動く」 amplify.yml** を残しておくのが安全策。`command -v pnpm` フォールバックと `/opt/chromium-layer/` の存在チェック、この 2 つだけで本番が死なない設計にできます

ビルド時間の短縮は「速くするための施策」として語られがちですが、実運用では **失敗しないこと** とセットで効いてきます。カスタム Docker イメージはその両方を低コストで手に入れられる、コスパの良い投資だと思っています。

## 参考

- [Sparticuz/chromium](https://github.com/Sparticuz/chromium) — Lambda 用 Chromium Layer
- [pnpm Store の仕組み](https://pnpm.io/symlinked-node-modules-structure)
- [Vite プロダクションビルドの永続キャッシュ議論 (vitejs/vite#15092)](https://github.com/vitejs/vite/issues/15092)
