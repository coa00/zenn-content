---
name: dev-kickoff
description: Linear issue や要望から機能開発をマルチエージェントチームで自律的に進行する。要件確認〜設計〜実装〜試験〜PR作成まで一気通貫。
argument-hint: <linear-issue-url または要望テキスト>
disable-model-invocation: true
allowed-tools:
  [
    Read,
    Write,
    Edit,
    Glob,
    Grep,
    Bash,
    Agent,
    ToolSearch,
    AskUserQuestion,
    Skill,
  ]
---

# 機能開発キックオフ — マルチエージェントチーム

Linear issue や要望を受け取り、マルチエージェントチームを編成して機能開発を自律的に進行する。

## 使い方

```
/dev-kickoff https://linear.app/team/issue/TEAM-123
/dev-kickoff ユーザープロフィール編集機能を追加したい
```

## チーム構成

| ロール                 | エージェント            | チームメンバー名 | 責務                                            |
| ---------------------- | ----------------------- | ---------------- | ----------------------------------------------- |
| オーケストレータ       | **このスキル自身**      | —                | 全体進行管理、フェーズ間の調整、Linear 報告     |
| PO                     | PO エージェント※       | `po`             | ユースケース作成・更新、画面仕様書の作成・更新  |
| フロントエンジニア     | FE エージェント※       | `frontend`       | UI コンポーネント実装                           |
| バックエンドエンジニア | BE エージェント※       | `backend`        | API・データモデル実装                           |
| インフラ管理           | Infra エージェント※    | `infra`          | 環境構築・Sandbox 起動・シードデータ投入        |
| ビルド監視             | `general-purpose`       | `build-monitor`  | ビルドの監視・エラー検知                        |
| Dev サーバ             | `general-purpose`       | `dev-server`     | ローカル開発サーバの起動・維持                  |
| AI デザイナー          | AI エージェント※       | `ai-designer`    | AI 機能の設計・プロンプト設計                   |
| テストエンジニア       | テストエージェント※    | `test-planner`   | 試験計画、試験項目の作成                        |
| E2E コード生成         | E2E エージェント※      | `e2e-writer`     | テスト計画書から Playwright spec.ts を生成      |
| テスター               | テスターエージェント※  | `tester`         | Playwright 等での試験実施                       |
| ファイナライザー       | `general-purpose`       | `finalizer`      | /dev-finalize の実行（PR作成・Linear報告等）    |
| アセット取得           | `/figma-asset-download` | —                | Figma から画像アセットをダウンロード・WebP 変換 |

※ プロジェクトの `.claude/agents/` に定義されたカスタムエージェントを使用する。
  存在しない場合は `general-purpose` で代替する。

---

## Phase 0: 入力の解析と要件確認

### 0a. 入力を解析

`$ARGUMENTS` を解析する:

- **Linear URL の場合**: ToolSearch で Linear MCP ツールをロードし、issue の詳細を取得
  ```
  ToolSearch: "+linear get"
  → mcp__linear__get_issue で issue 詳細を取得
  ```
- **テキストの場合**: 要望内容をそのまま要件として扱う

### 0b. プロジェクト特定

CLAUDE.md を読み取り、以下の情報を確認・特定する（ユーザーに質問が必要な場合は聞く）:

1. **対象リポジトリ**: どのリポジトリで作業するか
2. **対象ブランチ**: main / develop / feature ブランチ
3. **環境情報**: staging / prod / sandbox 等
4. **関連する既存機能**: 影響を受ける画面・API
5. **利用可能なエージェント**: `.claude/agents/` に定義されたカスタムエージェントを確認

### 0c. バックエンド変更の要否判定

要件・issue 内容からバックエンド変更が必要かを判定する。以下のいずれかに該当すればバックエンド変更 **あり**:

- データモデルの追加・変更
- API スキーマの変更
- サーバーサイド関数の追加・変更
- 認証・認可ルールの変更
- インフラリソース変更

判定結果を `BACKEND_REQUIRED: true/false` として以降のフェーズで参照する。

### 0d. 要件の整理・確認

解析結果をユーザーに提示して確認する:

```
## 要件確認

### 概要
- **Issue**: {LINEAR-ID}: {タイトル}
- **リポジトリ**: {リポジトリ名}
- **スコープ**: {機能概要}
- **バックエンド変更**: あり / なし

### 要件
1. {要件1}
2. {要件2}
3. ...

### 影響範囲
- {影響する画面・機能}

### 除外事項
- {今回のスコープ外}

→ この内容で進めてよいですか？
```

ユーザーの承認を得てから次のフェーズに進む。

---

## Phase 0.5: チーム作成（tmux 環境では必須）

> **重要**: tmux セッション内で実行されている場合、Phase 1 に進む **前に** 必ずチームを作成する。
> チームを作成せずに Phase 1 以降に進むことは **禁止** する。

### 0.5a. tmux 検出

```bash
# tmux 内で実行されているか確認
echo $TMUX
```

`$TMUX` が設定されていれば tmux 環境。

### 0.5b. チーム作成

tmux 環境の場合、TeamCreate でチームを作成する:

```
TeamCreate:
  team_name: "kickoff-{LINEAR-ID}"
  description: "{LINEAR-ID}: {タイトル} の機能開発チーム"
```

### 0.5c. インフラ系メンバーの先行スポーン

チーム作成後、以下の 3 メンバーを **先行スポーン** する（実装フェーズで必要になるため早めに準備）:

#### インフラ管理メンバー

```
Agent(subagent_type: "{infra-agent}", team_name: "kickoff-{LINEAR-ID}", name: "infra"):
  "あなたはインフラ管理担当です。
  チームのタスクリストを確認し、環境構築関連のタスクが割り当てられるまで待機してください。
  タスクが割り当てられたら、指示に従って環境のセットアップを行います。"
```

#### ビルド監視メンバー

```
Agent(subagent_type: "general-purpose", team_name: "kickoff-{LINEAR-ID}", name: "build-monitor"):
  "あなたはビルド監視担当です。
  チームのタスクリストを確認し、ビルド監視タスクが割り当てられるまで待機してください。
  タスクが割り当てられたら、ビルドの状況を監視し、エラーがあれば即座にチームに報告します。
  CLAUDE.md のビルドコマンドセクションを参照して適切なコマンドを実行してください。"
```

#### Dev サーバメンバー

```
Agent(subagent_type: "general-purpose", team_name: "kickoff-{LINEAR-ID}", name: "dev-server"):
  "あなたは開発サーバ担当です。
  チームのタスクリストを確認し、dev サーバ起動タスクが割り当てられるまで待機してください。
  タスクが割り当てられたら、指定された環境の dev サーバを起動し、動作確認可能な状態を維持します。
  CLAUDE.md の開発コマンドセクションを参照して適切なコマンドを実行してください。"
```

### 0.5d. 非 tmux 環境の場合

tmux 環境でない場合はチーム作成をスキップし、従来通り Agent tool の `run_in_background` で並列実行する。

---

## Phase 1: 環境セットアップ（必須ゲート）

> **重要**: どんな小さい変更でも、必ず worktree を作成してから作業を開始する。
> worktree を作成せずに Phase 2 以降に進むことは **禁止** する。
> これにより、親リポジトリの作業ブランチに別タスクの PR が混在することを防ぐ。

### 1a. Git Worktree 作成

CLAUDE.md の worktree 規約に従って作業環境を作成する:

```bash
# プロジェクトディレクトリに移動
cd {プロジェクトディレクトリ}/{リポジトリ名}

# feature ブランチで worktree を作成
git worktree add -b {ブランチ名} ../{リポジトリ名}.worktrees/{ブランチ名}
```

ブランチ名の規約: `feature/{LINEAR-ID}-{短い説明}` (例: `feature/TEAM-123-user-profile-edit`)

### 1b. 作業ディレクトリに移動・検証

```bash
cd {プロジェクトディレクトリ}/{リポジトリ名}.worktrees/{ブランチ名}
```

**worktree 検証**: 以下のコマンドで worktree 内にいることを必ず確認する。確認できない場合は Phase 2 に進まない:

```bash
test -f .git && echo "OK: worktree内で作業中" || echo "ERROR: worktree内ではありません"
git branch --show-current
```

以降のすべてのエージェント操作はこの worktree ディレクトリで行う。
**親リポジトリのディレクトリで直接作業してはいけない。**

### 1c. ブランチのクリーン状態を確認

```bash
git log main..HEAD --oneline
```

差分コミットが存在する場合は、誤ったブランチから分岐している可能性がある。

### 1d. 依存関係インストール

```bash
pnpm install  # or yarn install / npm install
```

### 1e. 環境先行起動（BACKEND_REQUIRED = true の場合）

> **重要**: 環境のデプロイには時間がかかるため、バックエンド変更がある場合は設計フェーズと **並列** で環境を先行起動する。

#### tmux（チームモード）の場合

`infra` メンバーにタスクを割り当てる:

```
TaskCreate:
  title: "環境セットアップ"
  description: |
    以下のワークツリーで開発環境をセットアップしてください。
    ## 作業ディレクトリ
    {worktree パス}
    ## CLAUDE.md の環境情報を参照してセットアップコマンドを実行
  owner: "infra"
```

`dev-server` と `build-monitor` にもタスクを割り当て、SendMessage で通知する。

#### 非 tmux の場合

**別エージェント（バックグラウンド）** で環境を起動する:

```
Agent(subagent_type: "{infra-agent}", run_in_background: true, name: "infra-setup"):
  "以下のワークツリーで開発環境をセットアップしてください。
  ## 作業ディレクトリ
  {worktree パス}
  ## CLAUDE.md の環境情報を参照してセットアップコマンドを実行"
```

---

## Phase 2: 設計（並列実行）

PO と AI デザイナーを **並列** で起動する。

### 2a. PO — ユースケース・画面仕様

```
Agent(subagent_type: "{po-agent}"):
  "以下の要件に基づき、ユースケースと画面仕様書を作成・更新してください。

  ## 要件
  {Phase 0 で確認した要件}

  ## 対象プロジェクト
  - リポジトリ: {リポジトリパス}
  - 既存ユースケース: docs/usecase/
  - 既存画面仕様書: docs/screen-design/

  ## 成果物
  1. ユースケース（docs/usecase/{ファイル名}.md）
  2. 画面仕様書（docs/screen-design/{ファイル名}.md）"
```

### 2b. AI デザイナー — AI 機能設計（AI 機能がある場合のみ）

```
Agent(subagent_type: "{ai-agent}"):
  "以下の要件に含まれる AI 機能の設計を行ってください。

  ## 要件
  {AI 関連の要件}

  ## 成果物
  - AI 機能設計書（プロンプト設計、モデル選定、データフロー）"
```

### 2c. 設計レビュー

両エージェントの成果物を統合し、ユーザーに確認する。

→ **ユーザー承認ゲート**

---

## Phase 3: 試験計画

### 3a. テストエンジニア — 試験項目作成

Phase 2 の設計成果物をもとに、テストエンジニアを起動:

```
Agent(subagent_type: "{test-planner-agent}"):
  "以下のユースケースと画面仕様書からテストケースを作成してください。

  ## 入力ドキュメント
  - ユースケース: docs/usecase/{ファイル名}.md
  - 画面仕様書: docs/screen-design/{ファイル名}.md

  ## 出力先
  - docs/testcase/{画面名}.md

  ## 基準
  - 正常系・異常系・権限・UI表示・ナビゲーションを網羅
  - 優先度（High/Medium/Low）を設定"
```

---

## Phase 4: 実装（並列実行）

フロントエンド、バックエンド、インフラを **並列** で起動する。

### 4a. 環境完了確認（BACKEND_REQUIRED = true の場合）

Phase 1e で先行起動した環境エージェントの完了を待つ。

### 4b. バックエンドエンジニア — API・データモデル実装

```
Agent(subagent_type: "{backend-agent}"):
  "以下のユースケースと画面仕様に基づき、バックエンド実装を行ってください。

  ## 入力
  - ユースケース: docs/usecase/{ファイル名}.md
  - 画面仕様書: docs/screen-design/{ファイル名}.md

  ## 実装範囲
  - データモデル
  - API エンドポイント / リゾルバー
  - 認可ルール
  - バリデーション"
```

### 4c. Figma アセットのダウンロード（画像が必要な場合）

Figma デザインにアイコン・イラスト・画像素材が含まれている場合:

```
Skill: figma-asset-download
args: "{Figma URL} {出力先ディレクトリ}"
```

### 4d. フロントエンジニア — UI 実装

```
Agent(subagent_type: "{frontend-agent}"):
  "以下の画面仕様に基づき、フロントエンド実装を行ってください。

  ## 入力
  - 画面仕様書: docs/screen-design/{ファイル名}.md
  - Figma URL: {あれば}
  - ダウンロード済みアセット: {アセットパス一覧（あれば）}

  ## 実装範囲
  - ページコンポーネント
  - フォーム
  - API 連携
  - ルーティング設定"
```

### 4e. 実装の統合確認

全エージェントの実装完了後、ビルドが通ることを確認:

```bash
pnpm build  # or yarn build
pnpm lint   # or yarn lint
```

---

## Phase 5: 試験実施

### 5a. E2E テストコード生成

Phase 3 のテストケースをもとに、E2E テストコードを生成する。

```
Agent(subagent_type: "{e2e-writer-agent}"):
  "以下のテスト計画をもとに、Playwright spec.ts を生成・保存してください。

  ## テスト計画書
  - docs/testcase/{画面名}.md

  ## 出力先
  - e2e/{testname}/specs/{testname}.spec.ts

  ## 注意事項
  - ソースコードを調査して実際の UI セレクタを使う
  - 自動化可能なテストケースのみ spec.ts に含める"
```

### 5b. テスター — E2E テスト実行

```
Agent(subagent_type: "{tester-agent}"):
  "Playwright spec.ts を実行し、E2E テストを実施してください。

  ## テスト環境
  - URL: CLAUDE.md の環境情報を参照
  - テストアカウント: CLAUDE.md のテストアカウント情報を参照

  ## 報告
  - 各テストケースの結果（Pass/Fail）
  - Fail の場合はスクリーンショットと原因分析"
```

### 5c. 不具合修正ループ

テスト結果に Fail がある場合:

1. 原因を分析
2. 該当エージェント（Frontend / Backend）に修正を依頼
3. 再テストを実行
4. 全件 Pass になるまで繰り返す（最大 3 ラウンド）

3 ラウンドで解決しない場合はユーザーに相談する。

---

## Phase 6: Linear 報告（中間）

ToolSearch で Linear MCP ツールをロードし、issue にコメントを追加:

```
ToolSearch: "+linear create_comment"

コメント内容:
## 実装・テスト完了報告

### 実装内容
- {実装した機能の概要}

### テスト結果
- 全 {N} ケース: {Pass 数} Pass / {Fail 数} Fail

### 次のステップ
- コードレビュー → PR 作成
```

---

## Phase 7: コードレビュー・整形

### 7a. コード品質レビュー

`/simplify` スキルを使ってコードレビューを実行する:

```
Skill: simplify
```

レビュー結果に指摘事項があれば修正し、再度テストを通す。

### 7b. プロジェクト固有レビュー（あれば）

プロジェクトに以下のようなレビュースキルがあれば順次実行する:

- `/build-fix-review` — 過去のビルドエラーパターン照合
- `/bug-trend-review review` — 過去のバグ傾向パターン照合
- `/structured-output-review` — LLM スキーマ互換性チェック（Zod 変更時のみ）

CRITICAL / WARNING レベルの指摘があれば修正してからコミットする。

### 7c. リント・型チェック

```bash
pnpm lint --fix
pnpm format
pnpm typecheck
```

エラーがあれば修正してコミットする。

---

## Phase 8: コミット整理

```bash
git add -A
git status
```

コミットは機能単位で分割する:

- `docs: add use case and screen design for {機能名}`
- `feat(backend): add {機能名} data model and resolvers`
- `feat(frontend): add {機能名} page and components`
- `test: add test cases for {機能名}`
- `test(e2e): add Playwright spec for {機能名}`

### 8a. PR 前のコミット検証（必須）

```bash
git log main..HEAD --oneline
git diff main..HEAD --stat
```

**チェック項目**:
- 今回のタスクに関係のないコミットが含まれていないか
- 他のタスクのファイル変更が混入していないか

**この検証を通過するまで Phase 9 に進まない。**

---

## Phase 9: 完了処理（/dev-finalize）

Phase 8 までの開発・コミット整理が完了したら、`/dev-finalize` を **別エージェント** で実行する。

#### tmux（チームモード）の場合

`finalizer` メンバーをスポーンして実行:

```
Agent(subagent_type: "general-purpose", team_name: "kickoff-{LINEAR-ID}", name: "finalizer"):
  "あなたは完了処理担当です。
  以下のワークツリーで /dev-finalize スキルを実行してください。

  ## 作業ディレクトリ
  {worktree パス}

  ## 実行手順
  1. まず Skill tool で dev-finalize を呼び出す
  2. スキルの指示に従って完了処理を進める
  3. 全処理が完了したらオーケストレータに報告する

  ## 注意
  - /dev-finalize は worktree のブランチ名から Linear issue ID を自動判定する
  - ユーザー確認が必要なステップ（PR マージ等）では必ずユーザーに確認を取る"
```

#### 非 tmux の場合

別エージェント（バックグラウンド）で実行:

```
Agent(subagent_type: "general-purpose", run_in_background: true, name: "finalizer"):
  "以下のワークツリーで /dev-finalize スキルを実行してください。

  ## 作業ディレクトリ
  {worktree パス}

  ## 実行手順
  1. まず Skill tool で dev-finalize を呼び出す
  2. スキルの指示に従って完了処理を進める
  3. 完了したら結果を報告する"
```

`/dev-finalize` が実行する内容:

1. Linear に着手報告
2. docs ドキュメント更新
3. E2E テスト作成/更新
4. 動作確認
5. `/simplify` + プロジェクト固有レビュー
6. PR 作成 → コンフリクト確認 → Lint 確認 → CI bot 確認 → マージ
7. デプロイ後 E2E テスト（バックエンド変更ありの場合）
8. Worktree 削除（プロセス停止後）
9. Linear に完了報告・ステータス更新

**注意**: `/dev-finalize` は現在の worktree とブランチ名から Linear issue ID を自動判定する。Phase 1 で作成した worktree 内から実行すること。

---

## 重要ルール

1. **各フェーズの完了を確認してから次へ進む**: エージェントの出力を必ず確認し、問題があれば修正してから次のフェーズに進む
2. **並列実行を最大活用**: Phase 2（設計）と Phase 4（実装）では複数エージェントを並列起動して効率化する
3. **ユーザー確認ポイント**: Phase 0（要件確認）と Phase 2c（設計レビュー）では必ずユーザーの承認を得る
4. **worktree は必須**: どんな小さい変更でも worktree を作成してから作業する。親リポジトリで直接作業しない。worktree 検証（`test -f .git`）が OK にならない限り Phase 2 以降に進まない
5. **既存コードとの整合**: 新規実装は既存のコーディング規約・パターンに合わせる
6. **AI 機能がない場合**: Phase 2b（AI デザイナー）はスキップする
7. **Linear 連携**: 進捗は Linear issue にコメントとして記録する
8. **不具合修正は 3 ラウンドまで**: 3 ラウンドで解決しない場合はユーザーに相談する
9. **tmux 環境ではチーム必須**: tmux セッション内で実行されている場合、Phase 0.5 でチームを作成してから作業を開始する。チーム作成せずに Phase 1 以降に進むことは禁止
10. **インフラ系は別メンバーに委任**: 環境構築（`infra`）、ビルド監視（`build-monitor`）、Dev サーバ起動（`dev-server`）はチームメンバーに委任し、オーケストレータが直接実行しない
11. **チームのシャットダウン**: 全フェーズ完了後、`SendMessage(message: {type: "shutdown_request"})` で全メンバーをシャットダウンする
12. **多段レビュー**: Phase 7 では `/simplify` + プロジェクト固有レビュースキル（あれば）の全レビューを通す
13. **CLAUDE.md 参照**: 環境情報・テストアカウント・ビルドコマンドは CLAUDE.md から読み取る。ハードコードしない
