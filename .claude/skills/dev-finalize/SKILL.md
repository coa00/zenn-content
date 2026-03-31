---
name: dev-finalize
description: '開発の完了処理を一貫して実行する。Linear報告→ドキュメント更新→E2Eテスト→動作確認→コードレビュー→PRマージ→デプロイ後E2E→worktree削除→Linear最終報告。"/dev-finalize"、"完了処理"、"シップ"、"開発完了" などで起動する。'
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

# Dev Finalize — 開発完了ワークフロー

開発完了処理を一貫して実行する。Linear 報告から worktree 削除まで、10 ステップの完了フローを自動化する。

## 使い方

```
/dev-finalize
```

引数不要。現在の worktree とブランチから Linear issue を自動判定する。

---

## 前提条件

- リポジトリの worktree 内で実行すること
- 機能実装が完了していること（コミット済み）
- worktree のブランチ名から Linear issue ID を抽出できること（例: `feature/TEAM-123-some-feature`）

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

ブランチ名から Linear issue ID を抽出する（例: `feature/TEAM-123-description` → `TEAM-123`）。

抽出できない場合はユーザーに確認する:

```
AskUserQuestion: "対象の Linear issue ID を教えてください"
```

### 0c. プロジェクト情報の読み取り

CLAUDE.md を読み取り、以下を特定する:

- 使用可能な dev スクリプト（`pnpm dev:*`）
- テスト環境（staging / sandbox / その他）
- テストアカウント情報
- ビルド・Lint コマンド

### 0d. バックエンド変更の有無を判定

`main`（または `develop`）との diff からバックエンド変更を判定する:

```bash
git diff main --name-only
```

以下のようなパターンに該当するファイルが含まれていればバックエンド変更ありと判定:

- `amplify/` 配下の変更
- `packages/backend/` や `packages/api/` 配下の変更
- データモデル定義ファイルの変更
- Lambda 関数の変更
- スキーマファイルの変更

判定結果をユーザーに提示して確認する:

```
バックエンド変更: あり / なし
変更ファイル概要: {主要な変更ファイル}
```

### 0e. 処理フローの提示

バックエンド変更の有無に応じた実行フローをユーザーに提示する:

**バックエンド変更あり:**

```
1. Linear に着手報告
2. docs ドキュメント更新
3. E2E テスト作成/更新
4. 動作確認（CLAUDE.md の環境情報に基づく）
5. /simplify + プロジェクト固有レビュー
6. PR 作成 → コンフリクト確認 → Lint 確認 → CI bot 確認 → マージ
7. デプロイ完了後、stg で E2E テスト
8. Worktree 削除
9. Linear に完了報告
```

**バックエンド変更なし:**

```
1. Linear に着手報告
2. docs ドキュメント更新
3. E2E テスト作成/更新
4. 動作確認（CLAUDE.md の環境情報に基づく）
5. /simplify + プロジェクト固有レビュー
6. PR 作成 → コンフリクト確認 → Lint 確認 → CI bot 確認 → マージ
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

変更内容に関連するドキュメントを特定する。

### 2b. ドキュメントの更新

今回の変更内容を反映する形でドキュメントを更新する。新規機能の場合は新規ドキュメントを作成する。

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

CLAUDE.md の環境情報を参照し、適切な dev スクリプトで起動してテストする。

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

### 5b. プロジェクト固有レビュー（あれば）

プロジェクトに `/build-fix-review`, `/bug-trend-review`, `/structured-output-review` 等のレビュースキルがあれば順次実行する。

CRITICAL / WARNING レベルの指摘があれば修正してからコミットする。

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

### 6c. コンフリクトの確認

```bash
gh pr view --json mergeable,mergeStateStatus
```

コンフリクトがある場合:

1. ベースブランチをフェッチしてマージ:
   ```bash
   git fetch origin ${baseBranch} && git merge origin/${baseBranch}
   ```
2. コンフリクトを解消してコミット・プッシュ
3. 再度コンフリクトがないことを確認

### 6d. Lint & Type チェック（PR 後の最終確認）

```bash
git diff ${baseBranch}...HEAD --name-only
```

プロジェクトの Lint / Type チェックコマンドを実行。エラーがあれば修正してコミット・プッシュする。

### 6e. CI bot コメントの確認

PR 作成後、CI bot（Sentry bot 等）がリアクション・コメントを投稿する場合がある:

| リアクション     | 意味           | 対応                                       |
| ---------------- | -------------- | ------------------------------------------ |
| 👀               | レビュー中     | 30秒おきに再確認、最大5分でスキップ        |
| 🎉               | 問題なし       | そのまま次へ                               |
| コメント投稿あり | 指摘事項あり   | 修正して再プッシュ、3回で解消しなければ相談 |

CI bot がない場合はスキップ。

### 6f. ユーザーにマージ確認

PR の URL と差分サマリーを提示し、マージの承認を得る:

```
AskUserQuestion:
  question: "PR をマージしてよいですか？"
  options:
    - label: "マージする"
    - label: "修正が必要"
    - label: "マージしない（手動で対応）"
```

### 6g. マージ実行

```bash
gh pr merge --squash --delete-branch
```

---

## Phase 7: デプロイ後 E2E（バックエンド変更ありの場合のみ）

バックエンド変更がない場合はこのフェーズをスキップする。

### 7a. デプロイ完了の確認

```bash
gh run list --limit 5
gh run watch
```

### 7b. Staging で E2E テスト実行

テスト失敗があればユーザーに報告し、対応方針を相談する。

---

## Phase 8: Worktree 削除

### 8a. プロセスの停止

worktree 削除前に、起動中のプロセスを停止する:

```bash
WORKTREE_PATH=$(pwd)

# この worktree で動いているプロセスを検出・停止
lsof +D "${WORKTREE_PATH}" 2>/dev/null | grep -E 'node|vite|sandbox|ampx' | awk '{print $2}' | sort -u | xargs -r kill 2>/dev/null || true

sleep 2

# まだ残っている場合は強制終了
lsof +D "${WORKTREE_PATH}" 2>/dev/null | grep -E 'node|vite|sandbox|ampx' | awk '{print $2}' | sort -u | xargs -r kill -9 2>/dev/null || true
```

### 8b. 親リポジトリに移動して worktree を削除

```bash
WORKTREE_PATH=$(pwd)
BRANCH_NAME=$(git branch --show-current)

cd $(git worktree list | head -1 | awk '{print $1}')

git worktree remove "${WORKTREE_PATH}"
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
## 開発完了

| 項目             | 結果                      |
| ---------------- | ------------------------- |
| Linear           | ${LINEAR_ISSUE_ID} → Done |
| PR               | ${PR_URL} → Merged        |
| ドキュメント     | 更新済み                  |
| E2E テスト       | 全件 Pass                 |
| コードレビュー   | /simplify 完了            |
| Worktree         | 削除済み                  |
```

---

## エラー時の対応

| 状況                    | 対応                                                    |
| ----------------------- | ------------------------------------------------------- |
| E2E テスト失敗          | 失敗箇所を修正して再実行（最大3回）                     |
| PR マージ失敗           | コンフリクトを解消して再試行                            |
| デプロイ失敗            | CI/CD のログを確認し報告                                |
| Linear API エラー       | MCP 接続を確認、手動で報告する旨を案内                  |
| CI bot コメントに指摘   | 修正、3回で解消しなければユーザーに相談                  |
| worktree 削除失敗       | 未コミットの変更やロック中プロセスがないか確認           |
