---
title: "Claude Code の Team 機能で「設計→実装→テスト→PR」を一気通貫で回した話"
emoji: "🤖"
type: "tech"
topics: ["ClaudeCode", "AI開発", "Playwright", "コードレビュー", "開発プロセス"]
published: true
cover: "/images/claude-code-team-workflow.webp"
---

## はじめに

Claude Code に Team 機能（`TeamCreate`）が実装されて、複数の AI エージェントを並列で動かせるようになりました。

自分たちは [Purpom Media Lab](https://purpom-media-lab.com/) で BMG（Business Model Generator）というビジネスモデル支援 SaaS を開発しています。今回、スライド生成機能に新しいデータソース（UniqueInsight）を反映する機能追加を行うにあたり、Claude Code の Team 機能を使って **設計 → 実装 → テスト → コードレビュー → PR 作成** までを一気通貫で回してみました。

この記事では、その開発プロセスの全体像と、各フェーズでどう Claude Code を活用したかを共有します。

## 対象読者

- Claude Code を使った開発に興味がある人
- AI エージェントを使ったチーム開発ワークフローを検討している人
- Playwright や Chrome DevTools MCP を活用したテスト自動化に興味がある人

## 今回のタスク概要

BMG では、ユーザーが入力したビジネスモデル情報をもとに AI がピッチ資料（スライド）を自動生成する機能があります。今回のタスクは以下の通り。

- **UniqueInsight（独自のインサイト）** というデータをスライド生成に反映する
- バックエンドのプロンプトとAPIルート、フロントエンドのペイロード構築を変更（4ファイル）
- 既存のスライドタイプを活用し、新スライドタイプは追加しない

変更自体はそこまで大きくないですが、「設計→テスト項目の作成→実装→テスト→レビュー→PR」という一連のプロセスを Team 機能でどう回すかがポイントです。

## 全体フロー

```
1. Plan Mode で設計（プロンプト・フロント・バックエンド）
2. 設計レビュー → 承認
3. 実装（4ファイルの変更）
4. TeamCreate でチームを構成
5. 各エージェントが並列で作業
   - change-analyzer: 変更内容の分析
   - test-planner: テスト項目の作成
   - playwright-tester: Playwright でE2Eテスト実行
6. コードレビューと修正
7. ESLint / Prettier の実行
8. PR の作成
```

## 1. Plan Mode で設計する

まず Claude Code の **Plan Mode** を使って実装計画を立てます。

Plan Mode では、コードベースを `Glob` / `Grep` / `Read` で探索しながら、既存の設計パターンを把握し、変更方針を決めていきます。今回は「スライド生成に UniqueInsight を反映する」というタスクに対して、**プロンプト設計・バックエンド設計・フロントエンド設計**の 3 レイヤーを一気に設計しました。

### プロンプト設計

スライド生成の核心は LLM に渡すプロンプトです。Plan Mode でまず `prompt.ts` を読み、既存のスライド構成を把握します。

```
## スライド構成の流れ（既存）
0. 表紙
1. エレベータピッチ
2. 課題
3. ソリューション
4. ビジネスモデル
5. 市場規模
6. 競合優位性
  ← ここに UniqueInsight を挿入したい
7. 顧客について
8. トラクション
9. クロージング
```

設計で決めたこと：

- **新スライドタイプは作らない** — 既存の `quote` / `content` パターンで十分表現できる
- **セクション 6b として挿入** — 競合優位性の後、顧客の前。FoundX のピッチ構成で「Secret」が来る位置
- **データがある場合のみ生成** — 既存セクションと同じ「データがなければスキップ」ルールに従う

システムプロンプトに追加する指示はこう設計しました：

```markdown
### 6b. ユニークインサイト — 秘密（UniqueInsight データがある場合）
- section パターンで「あなただけが知っている真実」等の結論タイトル
- 審査員や投資家がまだ気づいていない重要な真実（秘密）を伝える
- 推奨パターン: quote（第一候補）、content（第二候補）
- 1枚
```

### バックエンド設計

バックエンドは 2 ファイルの変更で済む設計にしました。

**`prompt.ts`（プロンプト生成）：**
- `GenerateSlideInput` インターフェースに `uniqueInsight?: string` を追加
- `buildUniqueInsightSection()` ヘルパー関数を新設（既存の `buildMarketResearchSection()` 等と同じパターン）
- システムプロンプトにセクション 6b の指示を追加
- ユーザープロンプトに UniqueInsight データセクションを追加（市場調査の後、KPI の前）

**`index.ts`（API ルート）：**
- payload の destructuring に `uniqueInsight` を追加
- `GenerateSlideInput` オブジェクトに渡す

既存コードのパターンを踏襲することで、変更の影響範囲を最小化しています。

### フロントエンド設計

フロントエンドも 2 ファイルの変更です。

**`use-generate-slide.ts`（payload 型定義）：**
- `GenerateSlidePayload` 型に `uniqueInsight?: string` を追加

**`business-model-view.tsx`（payload 構築）：**
- `buildSlidePayload()` の return に `uniqueInsight: uniqueInsight?.content ?? undefined` を追加
- `useCallback` の依存配列に `uniqueInsight` を追加

ここで重要なのは、`uniqueInsight` プロップはすでにコンポーネントに渡されていたこと。Plan Mode でコードを読んだ時点で `Props` 型に `uniqueInsight?: Schema['UniqueInsight']['type'] | null` が存在することを確認できていたので、**データの取得は不要、渡すだけ**という判断ができました。

### 設計レビューと承認

Plan Mode のメリットは、**実装前にユーザー（自分）が設計をレビューできる**こと。AI が「こう実装します」と宣言して突っ走るのではなく、変更ファイル・変更内容・方針を確認してから `ExitPlanMode` で承認する流れです。

```
Plan Mode → コード探索 → 3レイヤーの設計 → 設計レビュー → 承認 → 実装開始
```

今回の設計レビューでは以下を確認しました：

- 変更ファイルが 4 ファイルに収まっていること（影響範囲の妥当性）
- 既存パターンを踏襲していること（コードの一貫性）
- 新スライドタイプを追加しないこと（スキーマ変更なし＝リスク低）
- データがない場合のスキップロジックが入っていること

## 2. 実装する

設計を承認すると、Claude Code が即座に実装に入ります。今回は 4 ファイルの変更で、すべて `Edit` ツールで行いました。

### 実装の実際

Claude Code は設計で決めた内容を、ファイルごとに順次編集していきます。

**Step 1: `prompt.ts` — インターフェース拡張とヘルパー関数追加**

```typescript
// GenerateSlideInput に追加
uniqueInsight?: string;

// 新設したヘルパー関数
function buildUniqueInsightSection(input: GenerateSlideInput): string {
  if (!input.uniqueInsight) return '';
  return `- ユニークインサイト（秘密）: ${input.uniqueInsight}`;
}
```

既存の `buildMarketResearchSection()` と同じ「データがなければ空文字を返す」パターンに統一。

**Step 2: `prompt.ts` — システムプロンプトとユーザープロンプトにセクション追加**

システムプロンプトには LLM への指示を、ユーザープロンプトにはデータを追加。この 2 つを分けるのが既存の設計パターンです。

**Step 3: `index.ts` — API ルートでの受け渡し**

```typescript
const { ...既存フィールド, uniqueInsight } = data;
// ...
const input: GenerateSlideInput = { ...既存フィールド, uniqueInsight };
```

**Step 4: フロントエンド 2 ファイル — 型追加と payload 構築**

```typescript
// use-generate-slide.ts
uniqueInsight?: string;

// business-model-view.tsx
uniqueInsight: uniqueInsight?.content ?? undefined,
```

### 実装のポイント

4 ファイルの編集はすべて並列ではなく**順次実行**されます。これは依存関係があるため。

ただし、Claude Code は各ファイルの編集前に `Read` でファイル内容を取得しているので、**設計時の想定と実際のコードにズレがないか**を暗黙的に検証しています。Plan Mode で読んだ時点からファイルが変更されていた場合、ここで気づけます。

実装完了後、変更内容を確認してコミット：

```bash
git commit -m "feat: UniqueInsight をスライド生成に反映"
```

## 3. Claude Code Team の構成

実装が終わった後、PR 前の品質チェックを Team 機能で実施しました。`TeamCreate` でチームを作り、役割の異なるエージェントを並列で動かします。

```typescript
// チーム構成
TeamCreate({
  team_name: "bmg-review",
  description: "BMG スライド生成機能のレビューとテスト"
})
```

### エージェント構成

| エージェント名 | 役割 | 主な使用ツール |
|---------------|------|--------------|
| **change-analyzer** | コード変更の分析・影響範囲の特定 | Read, Grep, Glob |
| **test-planner** | 変更内容に基づくテスト項目の作成 | Read, Write |
| **playwright-tester** | Playwright MCP でE2Eテスト実行 | Playwright MCP |

各エージェントは `Task` ツールで起動し、`SendMessage` で結果を連携します。

### エージェント間の依存関係

```
change-analyzer（変更分析）
    ↓ 分析結果を連携
test-planner（テスト項目作成）
    ↓ テスト項目を連携
playwright-tester（テスト実行）
```

依存関係のある箇所は順次実行、独立した作業は並列実行。これが Team 機能の肝です。

## 4. Playwright MCP でE2Eテストを実行する

テスト実行は **Playwright MCP** を使います。Playwright MCP は Claude Code から直接ブラウザを操作できる MCP サーバーで、以下のような操作が可能です。

### テストの流れ

```
1. browser_navigate → ログイン画面に遷移
2. browser_fill_form → テストアカウントでログイン
3. browser_navigate → ビジネスモデル詳細画面に遷移
4. browser_click → 「資料出力」ボタンをクリック
5. browser_wait_for → スライド生成完了を待機
6. browser_snapshot → アクセシビリティツリーで内容を検証
7. browser_take_screenshot → スクリーンショットを保存
```

### テスト項目の例

- UniqueInsight 入力済みのビジネスモデルでスライド生成 → 「ユニークインサイト」スライドが含まれること
- UniqueInsight 未入力のビジネスモデルでスライド生成 → 該当スライドがスキップされること
- フリープランで「資料出力」をクリック → アップグレードダイアログが表示されること

### Chrome DevTools MCP でデバッグ

テストで問題が見つかった場合、**Chrome DevTools MCP** を使ってデバッグします。

```
- list_console_messages → コンソールエラーの確認
- list_network_requests → API リクエスト/レスポンスの確認
- evaluate_script → DOM の状態を直接確認
```

Playwright MCP でテストを回しつつ、失敗したら Chrome DevTools MCP でブラウザの内部状態を確認する。この組み合わせが非常に強力でした。

## 5. PR 前のコードレビューと修正

Team のエージェントがテストを回している間に、別のエージェント（または自分）がコードレビューを実施します。

今回のレビューで見つかった指摘と修正の例：

```diff
# SlidePresentation の VTL 認可テンプレート登録漏れ
+ 新モデルの VTL ファイルを追加

# EOF の改行漏れ
+ ファイル末尾に改行を追加

# import の順序
+ ESLint の import/order ルールに従って修正
```

コードレビューも Claude Code に任せると、人間が見落としがちな細かい点（EOF、import 順序、型の整合性など）を網羅的にチェックしてくれます。

## 6. ESLint / Prettier の実行

PR 作成前に lint チェックを実行します。BMG プロジェクトでは以下のコマンドを使っています。

```bash
# フロントエンド
yarn check:frontend

# バックエンド
yarn check:backend

# 自動修正
yarn fix:frontend
yarn fix:backend
```

Husky + lint-staged が設定されているのでコミット時にも自動実行されますが、PR 前にまとめて確認しておくのが安全です。

Claude Code は lint エラーが出たら自動で修正してコミットする、というフローも対応できます。

```
eslint エラー検出 → 自動修正 → 差分確認 → コミット
```

## 7. PR の作成

最後に PR を作成します。Claude Code は `gh` CLI を使って PR を作成できます。

```bash
gh pr create \
  --title "feat: UniqueInsight をスライド生成に反映" \
  --body "..."
```

PR の本文には、以下の情報を自動生成して含めます。

- **変更の要約** — change-analyzer の分析結果
- **テスト結果** — playwright-tester の実行結果
- **変更ファイル一覧** — git diff から抽出

チームのエージェントが生成した成果物をそのまま PR に組み込めるのが Team 機能のメリットです。

## Team 機能を使って感じたこと

### 良かった点

**1. 並列作業による時間短縮**

コード分析、テスト項目作成、テスト実行を並列で進められるので、直列で全部やるよりもかなり速い。特にPlaywright のテスト実行は待ち時間が長いので、その間に別の作業を進められるのが大きいです。

**2. 役割の明確化**

エージェントに明確な役割を与えることで、各タスクの品質が上がります。「コード分析もテストもレビューも全部やって」と1つのエージェントに頼むよりも、専門化させた方が良い結果になりました。

**3. コンテキストの分離**

各エージェントが独立したコンテキストを持つので、1つのエージェントの作業が膨大になってもコンテキストウィンドウを圧迫しません。特にテスト実行は大量のブラウザ操作ログが出るので、分離していないとすぐにコンテキストが溢れます。

### 注意点

**1. エージェント間の連携コスト**

`SendMessage` でのやり取りは非同期なので、タイミングの制御が必要です。依存関係を事前に `TaskUpdate` の `addBlockedBy` で定義しておくとスムーズです。

**2. エージェントの起動コスト**

各エージェントの起動にはそれなりのトークンコストがかかります。小さなタスクを細かく分割しすぎると、起動コストの方が大きくなることもあります。

**3. Playwright MCP の安定性**

ブラウザ操作は環境依存が大きいので、テストが不安定になることがあります。`browser_wait_for` を適切に使って、要素の表示を待ってから操作する必要があります。

## まとめ

Claude Code の Team 機能を使うことで、**設計 → 実装 → テスト → レビュー → PR** という開発サイクルを、以下のように効率化できました。

| フェーズ | 従来 | Claude Code Team |
|---------|------|-----------------|
| 設計 | 手動でコード調査・設計書作成 | Plan Mode で探索・3レイヤー設計 |
| 実装 | 手動でコーディング | 設計承認後に自動実装・コミット |
| テスト項目 | 手動で作成 | test-planner が自動生成 |
| E2Eテスト | 手動 or テストコード記述 | Playwright MCP で対話的に実行 |
| デバッグ | ブラウザで手動確認 | Chrome DevTools MCP で自動化 |
| コードレビュー | 人間がレビュー | AI が網羅的にチェック |
| PR 作成 | 手動で記述 | チームの成果物を自動反映 |

特に **Playwright MCP + Chrome DevTools MCP** の組み合わせは、テストコードを書かなくても対話的にE2Eテストを実行・デバッグできるので、プロトタイピングやスモールチームでの開発に非常に有効です。

AI エージェントは「コードを書いてくれるツール」という認識が強いですが、Team 機能を使うことで **開発プロセス全体をオーケストレーションする存在** として活用できるようになります。

## 参考

- [Claude Code 公式ドキュメント](https://docs.anthropic.com/en/docs/claude-code)
- [Playwright MCP](https://github.com/anthropics/playwright-mcp)
