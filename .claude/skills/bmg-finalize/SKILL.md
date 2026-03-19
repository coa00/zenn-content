---
name: bmg-finalize
description: 'BMG1 開発の完了処理を一貫して実行する。Linear報告→ドキュメント更新→E2Eテスト→動作確認→コードレビュー→PRマージ→デプロイ後E2E→worktree削除→Linear最終報告。"/bmg-finalize"、"BMG完了処理"、"BMGシップ"、"BMG開発完了" などで起動する。'
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

# BMG Finalize — 開発完了ワークフロー

BMG1 プロジェクトの開発完了処理を一貫して実行する。Linear 報告からworktree 削除まで、10 ステップの完了フローを自動化する。

## 使い方

```
/bmg-finalize
```

引数不要。現在の worktree とブランチから Linear issue を自動判定する。

---

## 前提条件

- BMG1 リポジトリの worktree 内で実行すること
- 機能実装が完了していること（コミット済み）
- worktree のブランチ名から Linear issue ID を抽出できること（例: `feature/BMG-123-some-feature`）

---

## Phase 0: 状態確認

### 0a. 現在の作業環境を把握

```bash
# 現在のディレクトリとブランチ
pwd
git branch --show-current

# 未コミットの変更がないか確認
git status

# 最近のコミットを確認
git log --oneline -10
```

### 0b. Linear issue ID の抽出

ブランチ名から Linear issue ID を抽出する（例: `feature/BMG-123-description` → `BMG-123`）。

抽出できない場合はユーザーに確認する:

```
AskUserQuestion: "対象の Linear issue ID を教えてください"
```

### 0c. バックエンド変更の有無を判定

`main`（または `develop`）との diff からバックエンド変更を判定する:

```bash
# main との差分ファイルを確認
git diff main --name-only
```

以下のいずれかに該当するファイルが含まれていればバックエンド変更ありと判定:

- `amplify/` 配下の変更
- `packages/backend/` や `packages/api/` 配下の変更
- `amplify/data/resource.ts` の変更
- Lambda 関数の変更
- `schema.graphql` の変更

判定結果をユーザーに提示して確認する:

```
バックエンド変更: あり / なし
変更ファイル概要: {主要な変更ファイル}
```

### 0d. 処理フローの提示

バックエンド変更の有無に応じた実行フローをユーザーに提示する:

**バックエンド変更あり:**

```
1. Linear に着手報告
2. docs ドキュメント更新
3. E2E テスト作成/更新
4. Sandbox でテスト（pnpm sandbox:once → dev:sandbox:app / dev:sandbox:admin）
5. /simplify + /build-fix-review + /bug-trend-review review + /structured-output-review でレビュー
6. PR 作成 → Sentry bot コメント確認 → マージ
7. デプロイ完了後、stg で E2E テスト
8. Worktree 削除
9. Linear に完了報告
```

**バックエンド変更なし:**

```
1. Linear に着手報告
2. docs ドキュメント更新
3. E2E テスト作成/更新
4. ehime-stg でテスト（dev:app:ehime-stg / dev:admin:ehime-stg）
5. /simplify + /build-fix-review + /bug-trend-review review + /structured-output-review でレビュー
6. PR 作成 → Sentry bot コメント確認 → マージ
7. Worktree 削除
8. Linear に完了報告
```

ユーザーの承認を得てから進める。

---

## Phase 1: Linear に着手報告

ToolSearch で Linear MCP ツールをロードし、issue にコメントを追加する:

```
ToolSearch: "+linear create_comment"

mcp__linear__create_comment(
  issueId: "${LINEAR_ISSUE_ID}",
  body: "## 完了処理を開始\n\n開発完了処理フローを開始します。\n- ドキュメント更新\n- E2Eテスト\n- コードレビュー\n- PR作成・マージ"
)
```

---

## Phase 2: docs ドキュメント更新

### 2a. 既存ドキュメントの確認

```
Glob: docs/**/*.md
```

変更内容に関連するドキュメントを特定する:

- ユースケース: `docs/usecase/`
- 画面仕様書: `docs/screen-design/`
- テストケース: `docs/testcase/`
- その他: `docs/` 配下

### 2b. ドキュメントの更新

今回の変更内容を反映する形でドキュメントを更新する。新規機能の場合は新規ドキュメントを作成する。

更新対象:

- 追加した機能やAPIの仕様
- 変更した画面の仕様
- 新しいユースケース

### 2c. 変更をコミット

```bash
git add docs/
git commit -m "docs: update documentation for ${FEATURE_NAME}"
```

---

## Phase 3: E2E テスト作成/更新

### 3a. 既存テストの確認

```
Glob: e2e/**/*.{ts,spec.ts}
```

### 3b. テストの作成/更新

今回の変更に対応する E2E テストを作成または更新する。

- Playwright を使用
- `e2e/` ディレクトリに配置
- 既存のテストパターンに合わせる
- CLAUDE.md のテストアカウント情報を使用

### 3c. 変更をコミット

```bash
git add e2e/
git commit -m "test: add/update E2E tests for ${FEATURE_NAME}"
```

---

## Phase 4: 動作確認

### バックエンド変更ありの場合

#### 4a. Sandbox セットアップ

```bash
pnpm sandbox:once
```

Sandbox のデプロイ完了を待つ。

#### 4b. アプリのテスト

```bash
# アプリ側
pnpm dev:sandbox:app
```

Playwright MCP またはブラウザで動作確認を行う。

#### 4c. 管理画面のテスト

```bash
# 管理画面側
pnpm dev:sandbox:admin
```

Playwright MCP またはブラウザで動作確認を行う。

#### 4d. E2E テスト実行（Sandbox）

```bash
E2E_ENV=sandbox pnpm exec playwright test --config e2e/playwright.config.ts
```

### バックエンド変更なしの場合

#### 4a. アプリのテスト

```bash
pnpm dev:app:ehime-stg
```

#### 4b. 管理画面のテスト

```bash
pnpm dev:admin:ehime-stg
```

#### 4c. E2E テスト実行（ehime-stg）

```bash
E2E_ENV=ehime-stg pnpm exec playwright test --config e2e/playwright.config.ts
```

### テスト結果の確認

テスト失敗があれば修正し、全件 Pass になるまで繰り返す。
3 ラウンドで解決しない場合はユーザーに相談する。

---

## Phase 5: コードレビュー

### 5a. コード品質レビュー

`/simplify` スキルを使ってコードレビューを実行する:

```
Skill: simplify
```

レビュー結果に指摘事項があれば修正し、再度テストを通す。

### 5b. ビルドエラーパターンチェック

`/build-fix-review` スキルで過去のビルドエラーログと差分を照合し、既知のリスクパターンがないか確認する:

```
Skill: build-fix-review
```

CRITICAL / WARNING レベルの指摘があれば、該当箇所を修正してからコミットする。

### 5c. バグ傾向ベースのレビュー

`/bug-trend-review review` スキルで過去のバグ傾向レポートと差分を照合し、同じパターンのリスクがないか確認する:

```
Skill: bug-trend-review review
```

CRITICAL / WARNING レベルの指摘があれば、該当箇所を修正してからコミットする。

### 5d. Structured Output 互換性レビュー

差分に Zod スキーマや LLM 呼び出しコード（`generateObject`, `z.object`, `schema.ts` 等）が含まれている場合、`/structured-output-review` スキルでモデル別の structured output 制約との互換性をチェックする:

```bash
# 差分に Zod スキーマ / LLM 関連の変更があるか確認
git diff ${baseBranch}...HEAD --name-only | grep -E "(schema|z\.object|generate|llm)" || true
```

該当ファイルがある場合:

```
Skill: structured-output-review <対象ファイルパス>
```

主なチェック項目:

- `.optional()` が単体で使われていないか（OpenAI でエラー）→ `.nullable()` に変更
- ネスト深度が 5 レベル以内か
- `.min()` / `.max()` が OpenAI で無視されることを認識しているか
- 全フィールドに `.describe()` が付いているか

CRITICAL レベルの指摘があれば修正してからコミットする。

### 5e. Lint & Type チェック

レビュー修正が完了したら、差分に応じて Lint と型チェックを実行する。

差分ファイルから対象を判定:

```bash
git diff ${baseBranch}...HEAD --name-only
```

**フロントエンド変更あり**（`apps/` 配下の変更がある場合）:

```bash
pnpm check:frontend
```

**バックエンド変更あり**（`packages/` 配下の変更がある場合）:

```bash
pnpm check:backend
```

エラーがあれば修正してコミットする。3 ラウンドで解消しない場合はユーザーに相談する。

---

## Phase 6: PR 作成とマージ

### 6a. リモートにプッシュ

```bash
git push -u origin $(git branch --show-current)
```

### 6b. PR 作成

```bash
gh pr create --title "${LINEAR_ISSUE_ID}: ${FEATURE_NAME}" --body "$(cat <<'EOF'
## Summary
- {変更概要}

## Linear Issue
https://linear.app/.../issue/${LINEAR_ISSUE_ID}/...

## Changes
- {主要な変更点}

## Test Results
- E2E: 全件 Pass

## Test plan
- [ ] E2E テスト全件 Pass
- [ ] 動作確認完了

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### 6c. Sentry bot コメントの確認

PR 作成後、Sentry bot が PR にリアクション・コメントを投稿する。リアクションでステータスを判定する:

| リアクション     | 意味           | 対応                                       |
| ---------------- | -------------- | ------------------------------------------ |
| 👀               | まだレビュー中 | 待機する（30秒おきにリアクションを再確認） |
| 🎉               | 問題なし       | そのまま次のステップに進む                 |
| コメント投稿あり | 指摘事項あり   | 内容を確認し対応する                       |

```bash
# PR のリアクションとコメントを確認
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments
```

**👀（レビュー中）の場合:**

30秒おきにリアクションを再確認し、🎉 またはコメントに変わるまで待機する。最大5分待っても変わらない場合はスキップしてマージ確認に進む。

**🎉（問題なし）の場合:**

そのまま次のステップに進む。

**Sentry bot のコメントに指摘事項がある場合:**

1. 指摘内容を確認し、対応が必要か判断する
2. 対応が必要な場合はコードを修正してコミット・プッシュする
3. Sentry bot のコメントに対応内容を返信する:
   ```bash
   # Sentry bot のコメント ID を取得して返信
   gh pr comment --body "Sentry 指摘への対応:\n- {対応内容の要約}\n- 修正コミット: {commit hash}"
   ```
4. 修正後、再度 Sentry bot のコメントが更新されるのを待って確認する
5. 指摘が解消されない場合はユーザーに相談する

Sentry bot のコメントがない場合はそのまま次に進む。

### 6d. ユーザーにマージ確認

PR の URL と差分サマリーを提示し、マージの承認を得る:

```
AskUserQuestion:
  question: "PR をマージしてよいですか？"
  options:
    - label: "マージする"
    - label: "修正が必要"
    - label: "マージしない（手動で対応）"
```

### 6e. マージ実行

承認を得たらマージする:

```bash
gh pr merge --squash --delete-branch
```

---

## Phase 7: デプロイ後 E2E（バックエンド変更ありの場合のみ）

バックエンド変更がない場合はこのフェーズをスキップする。

### 7a. デプロイ完了の確認

マージ後、CI/CD のデプロイ完了を確認する:

```bash
# GitHub Actions のステータスを確認
gh run list --limit 5
gh run watch  # 最新の実行を監視
```

### 7b. Staging で E2E テスト実行

デプロイ完了後、Staging 環境で E2E テストを実行する:

```bash
E2E_ENV=stg pnpm exec playwright test --config e2e/playwright.config.ts
```

テスト失敗があればユーザーに報告し、対応方針を相談する。

---

## Phase 8: Worktree 削除

### 8a. 親リポジトリに移動して worktree を削除

```bash
# 現在の worktree パスを記録
WORKTREE_PATH=$(pwd)
BRANCH_NAME=$(git branch --show-current)

# 親リポジトリに移動
cd $(git worktree list | head -1 | awk '{print $1}')

# worktree を削除
git worktree remove "${WORKTREE_PATH}"

# ローカルブランチも削除（リモートは PR マージ時に削除済み）
git branch -d "${BRANCH_NAME}" 2>/dev/null || true
```

---

## Phase 9: Linear に完了報告

### 9a. 完了コメントを投稿

```
mcp__linear__create_comment(
  issueId: "${LINEAR_ISSUE_ID}",
  body: "## 完了報告\n\n### PR\n- ${PR_URL}\n\n### 実施内容\n1. ドキュメント更新\n2. E2Eテスト作成/更新\n3. コードレビュー（/simplify）\n4. 動作確認 Pass\n5. PRマージ完了\n${BACKEND_CHANGED ? '6. デプロイ後 stg E2E Pass' : ''}\n7. Worktree削除\n\n### テスト結果\n- E2E: 全件 Pass"
)
```

### 9b. ステータス更新

```
ToolSearch: "+linear save_issue"

mcp__linear__save_issue(
  id: "${LINEAR_ISSUE_ID}",
  stateId: "Done のステータス ID"
)
```

---

## Phase 10: ユーザーへの最終報告

```markdown
## BMG 開発完了

| 項目                  | 結果                      |
| --------------------- | ------------------------- | ------------- | ------- |
| Linear                | ${LINEAR_ISSUE_ID} → Done |
| PR                    | ${PR_URL} → Merged        |
| ドキュメント          | 更新済み                  |
| E2E テスト            | 全件 Pass                 |
| ビルドリスクチェック  | /build-fix-review 完了    |
| コードレビュー        | /simplify 完了            |
| Worktree              | 削除済み                  |
| ${BACKEND_CHANGED ? ' | デプロイ後 E2E            | stg 全件 Pass | ' : ''} |
```

---

## エラー時の対応

| 状況                          | 対応                                                    |
| ----------------------------- | ------------------------------------------------------- |
| sandbox:once 失敗             | エラーログを確認し、Amplify の設定を見直す              |
| E2E テスト失敗                | 失敗箇所を修正して再実行（最大3回）                     |
| PR マージ失敗                 | コンフリクトを解消して再試行                            |
| デプロイ失敗                  | GitHub Actions のログを確認し報告                       |
| Linear API エラー             | MCP 接続を確認、手動で報告する旨を案内                  |
| Sentry bot が👀リアクション   | まだレビュー中。30秒おきに再確認、最大5分でスキップ     |
| Sentry bot が🎉リアクション   | 問題なし。そのままマージ確認に進む                      |
| Sentry bot コメントに指摘あり | 指摘内容を確認し修正、3回で解消しなければユーザーに相談 |
| Sentry bot コメントが来ない   | 5分以上待っても来ない場合はスキップしてマージ確認に進む |
| worktree 削除失敗             | 未コミットの変更がないか確認                            |
