---
name: structured-output-review
description: "OpenAI/Gemini/Claude のモデル別 structured output 制約を踏まえて Zod スキーマやLLM呼び出しコードをレビューするスキル。「structured output レビュー」「Zodスキーマチェック」「LLMスキーマ互換性」「generateObject レビュー」「structured output 確認」「スキーマ互換性チェック」「OpenAI スキーマエラー」「Gemini スキーマ」「optional エラー」「マルチプロバイダ互換性」などで使用。"
argument-hint: "<レビュー対象ファイルパス or Zodスキーマの質問>"
allowed-tools:
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Bash
  - WebFetch
  - Agent
---

# Structured Output Review スキル

OpenAI / Gemini / Anthropic (Bedrock Claude) の structured output 制約に精通したエキスパートとして、Zod スキーマと LLM 呼び出しコードをレビューする。

## リファレンスドキュメント

- **制約リファレンス**: `~/.claude/skills/structured-output-review/references/openai-structured-output-constraints.md`

必ず最初にこのドキュメントを Read で読み込んでからレビューを行うこと。

## プロバイダ別制約サマリー（クイックリファレンス）

| 制約 | OpenAI | Gemini | Claude |
|------|--------|--------|--------|
| optional | **NG** | OK | OK |
| discriminatedUnion | OK | **NG** | OK |
| $ref / 再帰 | OK | **NG** | OK |
| anyOf / oneOf | OK | **限定的** | OK |
| ネスト深度 | **5** | 制限なし | 制限なし |
| 100% 準拠保証 | **あり** | なし | なし |

## モード判定

`{argument}` の内容から以下のモードを判定して実行する:

### 1. レビューモード（デフォルト）

キーワード: 「レビュー」「チェック」「確認」「問題ない？」、またはファイルパスが指定された場合

**手順:**

1. リファレンスドキュメントを Read で読み込む
2. 対象ファイルを Read で読む
3. プロジェクトで使われるプロバイダを確認:
   ```
   Grep: pattern="isClaude|getLlmModelId|LlmModels|@ai-sdk/google|@ai-sdk/openai|@ai-sdk/amazon-bedrock" type="ts"
   ```
4. Zod スキーマがどのプロバイダで使われるか特定
5. 以下の観点でレビューする

**レビュー観点（マルチプロバイダ）:**

| カテゴリ | チェック項目 | OpenAI | Gemini | Claude | 重要度 |
|----------|-------------|--------|--------|--------|--------|
| **optional** | `.optional()` 単体使用 | NG | OK | OK | Critical |
| **nullable** | `.nullable()` で代替しているか | 必須 | 推奨 | 任意 | Critical |
| **discriminatedUnion** | `z.discriminatedUnion()` 使用 | OK | **NG** | OK | Critical |
| **union** | `z.union()` 使用 | OK | **制限あり** | OK | Warning |
| **再帰スキーマ** | `z.lazy()` 使用 | OK | **NG** | OK | Critical |
| **record** | `z.record()` 使用 | **NG** | **NG** | OK | Critical |
| **バリデーション** | `.min()` `.max()` `.regex()` 等 | 無視 | 無視 | best-effort | Warning |
| **ネスト深度** | 5 レベル超え | **NG** | 注意 | OK | Critical |
| **プロパティ数** | 100 超え | **NG** | 注意 | OK | Warning |
| **非対応型** | `z.any()`, `z.date()`, `z.transform()` | NG | NG | NG | Critical |
| **describe** | `.describe()` 未設定 | 品質低下 | 品質低下 | 品質低下 | Info |
| **providerOptions** | `generateObject` に渡している | エラー | - | - | Warning |

**レビュー出力フォーマット:**

```markdown
## Structured Output レビュー結果

### 対象ファイル
- `path/to/file.ts`

### 使用プロバイダ
- OpenAI: gpt-5, gpt-5-mini, gpt-5.4-mini
- Bedrock Claude: claude-sonnet-4-6, claude-haiku-4-5
- Gemini: (使用なし / gemini-2.5-flash 等)

### 検出された問題

#### 🔴 Critical: optional フィールド [OpenAI NG] (L42-46)
```typescript
// 現在のコード
rate: z.string().optional()

// 修正案（全プロバイダ対応）
rate: z.string().nullable().describe('...。不明な場合は null')
```
**影響**: OpenAI モデル使用時にエラーになる

#### 🔴 Critical: discriminatedUnion [Gemini NG] (L80-95)
```typescript
// 現在のコード
z.discriminatedUnion('type', [...])

// Gemini 対応が必要な場合の修正案
z.object({
  type: z.enum([...]),
  fieldA: z.string().nullable(),
  fieldB: z.string().nullable(),
})
```
**影響**: Gemini モデル追加時にエラーになる

#### 🟡 Warning: バリデーション制約 [OpenAI/Gemini 無視] (L90)
```typescript
z.array(...).min(5).max(5) // OpenAI/Gemini で無視される
```
**影響**: プロンプトでも件数を指定すること

#### ℹ️ Info: describe 未設定 [全プロバイダ] (L25)

### プロバイダ互換性サマリー
| プロバイダ | 互換性 |
|-----------|--------|
| OpenAI | ⚠️ N件の修正必要 |
| Gemini | ❌ discriminatedUnion 使用で非互換 |
| Claude | ✅ 問題なし |

### 総合
- Critical: X件
- Warning: X件
- Info: X件
```

### 2. 実装支援モード

キーワード: 「実装」「書いて」「作って」「スキーマ」「修正」

**手順:**

1. リファレンスドキュメントを Read で読み込む
2. プロジェクトで使われるプロバイダを確認
3. 既存の Zod スキーマパターンを調査:
   ```
   Grep: pattern="z\.object\(" glob="**/routes/**/*.ts"
   ```
4. ターゲットプロバイダに合わせた Zod スキーマを書く

**実装時のルール（全プロバイダ安全）:**

- **optional は使わない** → `.nullable()` で代替
- **discriminatedUnion は避ける**（Gemini 対応が必要な場合）→ フラット object + nullable に変換
- **再帰スキーマ（z.lazy）は避ける**（Gemini 非対応）
- **z.record() は避ける**（OpenAI + Gemini 非対応）
- **バリデーション制約（min/max 等）は信頼しない** → describe でも制約を記述
- **ネスト 5 レベル以内** に収める（OpenAI 制限）
- **プロパティ 100 以内** に収める（OpenAI 制限）
- 全フィールドに `.describe()` を付ける
- 「値がない場合」は `.describe('...。不明な場合は null')` で明示

**Gemini 対応が不要な場合:**

discriminatedUnion, union, $ref は使ってよい（OpenAI + Claude で動作）。

### 3. 質問・調査モード

上記に当てはまらない場合、structured output に関する質問として回答する。

**手順:**

1. リファレンスドキュメントから該当箇所を検索
2. 必要に応じて最新の公式ドキュメントを WebFetch で確認:
   ```
   OpenAI: https://platform.openai.com/docs/guides/structured-outputs
   Gemini: https://ai.google.dev/gemini-api/docs/structured-output
   Anthropic: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
   ```
3. コード例を含めて回答

## プロジェクト固有の適応

BMG プロジェクト（lean_quest）での主要パターン:

1. **モデル切り替え**: `llmModels.ts` の `LlmModels` enum → `isClaude()` で分岐
2. **LLM 呼び出し**: `generateObjectWithTracing()` → Vercel AI SDK `generateObject()`
3. **スキーマ定義場所**: 各ルートの `index.ts` 内、または `schema.ts` に分離
4. **使われるモデル**: gpt-5, gpt-5-mini, gpt-5.4-mini, claude-sonnet-4-6, claude-haiku-4-5
5. **注意**: generate-slide は 26 discriminatedUnion を使用 → Gemini 追加時に要リファクタ

コードを書く際は、プロジェクトの既存パターンに従う:

1. 既存スキーマの書き方を `Grep` で調査
2. `generateObjectWithTracing` のインターフェースに合わせる
3. temperature は `isClaude(llmModel) ? X : 1` パターン
