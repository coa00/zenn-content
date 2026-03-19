# Structured Output 制約リファレンス（マルチプロバイダ）

> 最終更新: 2026-03-19
> ソース: OpenAI SDK / Google AI SDK / Anthropic API ドキュメント

---

## 1. プロバイダ別クイック比較

| 制約 | OpenAI (strict) | Gemini | Claude (Bedrock/API) |
|------|----------------|--------|---------------------|
| **optional フィールド** | **不可（全 required）** | 可能 | 可能 |
| **100% スキーマ準拠保証** | **あり（constrained decoding）** | なし（best-effort） | Bedrock `strict:true` で**あり** / tool_use は best-effort |
| **スキーマ形式** | JSON Schema subset | **OpenAPI 3.0 subset** | JSON Schema（柔軟） |
| **`anyOf` / `oneOf`** | YES | **限定的/NO** | YES |
| **`$ref` / `$defs`** | YES | **NO** | YES |
| **nullable 構文** | `anyOf` with null | **`nullable: true`** | 両方 OK |
| **`additionalProperties: false`** | 必須 | 不要 | 不要 |
| **ネスト深度制限** | 5 レベル | 明確な制限なし | 明確な制限なし |
| **プロパティ数制限** | 100 | 明確な制限なし | 明確な制限なし |
| **バリデーション制約** | 無視 | 無視 | best-effort |
| **discriminatedUnion** | YES (anyOf) | **NO** | YES |
| **propertyOrdering** | NO | YES（Gemini 固有） | NO |

---

## 2. OpenAI 制約

### 2.1 対応モデル

| モデル | 対応 | 備考 |
|--------|------|------|
| gpt-4o-2024-08-06 以降 | YES | 初導入 |
| gpt-4o-mini | YES | |
| gpt-4.1 / 4.1-mini / 4.1-nano | YES | |
| gpt-5 / gpt-5-mini / gpt-5.4-mini | YES | |
| o1 / o3 / o3-mini / o4-mini | YES | reasoning モデル |
| gpt-4-turbo 以前 | NO | json_object モードのみ |

### 2.2 全フィールド required 必須（最重要）

`strict: true` では **全プロパティが `required`** でなければならない。

```typescript
// NG: エラー
z.object({ rate: z.string().optional() });

// OK: nullable で代替
z.object({ rate: z.string().nullable().describe('不明な場合は null') });
```

SDK エラー: `Zod field uses .optional() without .nullable() which is not supported by the API.`

### 2.3 additionalProperties: false 必須

全 `object` に `additionalProperties: false` が必要。SDK が自動付与。

### 2.4 サポートされる機能

`type` (string/number/integer/boolean/null/object/array), `enum`, `const`, `anyOf`, `allOf`, `$ref`/`$defs`, `description`

### 2.5 サポートされない機能

- `additionalProperties: true`, `patternProperties`, `if`/`then`/`else`
- **バリデーション制約**: `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `minItems`, `maxItems`, `format`

### 2.6 複雑度制限

| 制限 | 値 |
|------|-----|
| 最大ネスト深度 | 5 |
| 最大プロパティ数 | 100 |
| 最大 enum 値数 | 500 |
| 最大 $defs 数 | 100 |

---

## 3. Gemini 制約

### 3.1 対応モデル

| モデル | 対応 | 備考 |
|--------|------|------|
| gemini-2.5-pro / 2.5-flash | YES | |
| gemini-2.0-flash / flash-lite | YES | |
| gemini-1.5-pro / 1.5-flash | YES | |
| gemini-1.0-pro | NO | |

### 3.2 スキーマ形式: OpenAPI 3.0 Subset

Gemini は **JSON Schema ではなく OpenAPI 3.0 Schema Object** のサブセットを使用。これが最大の違い。

```
// Gemini はこの形式
{ "type": "STRING", "nullable": true }

// OpenAI はこの形式
{ "anyOf": [{ "type": "string" }, { "type": "null" }] }
```

AI SDK が自動変換するが、以下の機能は **Gemini で非対応**:

### 3.3 Gemini で非対応の機能（Critical）

| 機能 | 状況 | 影響 |
|------|------|------|
| **`$ref` / `$defs`** | **非対応** | 再帰スキーマ不可 |
| **`anyOf` / `oneOf`** | **限定的〜非対応** | discriminatedUnion 不可 |
| **`allOf`** | **非対応** | intersection 不可 |
| **`const`** | **非対応** | literal が制限される |
| **`additionalProperties`** | **不要/非対応** | |

### 3.4 optional フィールド

Gemini では **optional は許容される**（OpenAI と逆）。`required` 配列に含めないフィールドはオプショナル扱い。

ただし、省略されたフィールドのハンドリングが必要。

### 3.5 nullable の構文

```typescript
// Gemini: nullable: true プロパティを使用
{ "type": "STRING", "nullable": true }

// Zod での書き方は z.string().nullable() → AI SDK が自動変換
```

### 3.6 100% 準拠保証なし

Gemini は best-effort。複雑なスキーマでは非準拠の出力が返る可能性がある。必ずバリデーションすること。

### 3.7 複雑度制限

公式ドキュメントに明確な制限値はないが、実用上は OpenAI の制限（ネスト 5、プロパティ 100）に合わせるのが安全。

---

## 4. Claude (Anthropic / Bedrock) 制約

### 4.1 対応モデル

| モデル | 対応 | 備考 |
|--------|------|------|
| Claude Sonnet 4.6 | YES | tool_use 経由 |
| Claude Haiku 4.5 | YES | tool_use 経由、精度はやや低い |
| Claude Opus 4.6 | YES | |
| 旧モデル (3.5 Sonnet 等) | YES | |

### 4.2 構造化出力の2つのモード

#### モード A: tool_use（従来方式・AI SDK デフォルト）

- AI SDK の `generateObject()` → tool 定義として Zod スキーマを送信 → Claude が tool_use で応答
- **標準 JSON Schema に近い形式**で、最も柔軟
- **best-effort**（100% 保証なし）

#### モード B: Bedrock Constrained Decoding（`strict: true`）

- Bedrock Converse API の tool 定義に `strict: true` を設定
- **grammar-based constrained decoding** で **100% スキーマ準拠を保証**（OpenAI と同等）
- 初回スキーマコンパイルに**数分**かかる場合あり（コンパイル済みは 24 時間キャッシュ）
- `additionalProperties: false` が必要（OpenAI と同じ）
- **citations と併用不可**（400 エラー）
- 対応モデル: Claude Haiku 4.5, Claude Sonnet 4.5, Claude Opus 4.5/4.6

> 注意: AI SDK が Bedrock の `strict: true` を自動的に有効にするかは AI SDK バージョンによる。明示的な設定が必要な場合がある。

### 4.3 サポート状況（tool_use モード）

| 機能 | 状況 |
|------|------|
| optional フィールド | **OK** |
| `anyOf` / `oneOf` | **OK** |
| `$ref` / `$defs` | **OK** |
| `additionalProperties` | 制約なし |
| discriminatedUnion | **OK** |
| バリデーション制約 | best-effort（従う場合もある） |
| nested objects | **制限なし** |

### 4.4 準拠保証

| モード | 保証 |
|--------|------|
| tool_use（従来） | best-effort |
| Bedrock `strict: true` | **100% 保証**（constrained decoding） |

### 4.5 Bedrock 固有の注意

- `jp.anthropic.claude-sonnet-4-6`（クロスリージョン推論）: structured output 対応（追加設定不要）
- `jp.anthropic.claude-haiku-4-5-20251001-v1:0`: constrained decoding 対応確認済み
- Bedrock Converse API 経由でも tool_use で構造化出力を行う
- AI SDK `@ai-sdk/amazon-bedrock` が自動的に処理

### 4.6 Claude Haiku vs Sonnet の違い

- Haiku 4.5: 高速だが、複雑なスキーマ（20+ フィールド、深いネスト）での精度がやや低い
- Sonnet 4.6: スキーマ追従精度が高い
- 両方とも optional / nullable / discriminatedUnion をサポート
- constrained decoding (`strict: true`) を有効にすれば両方とも 100% 準拠

---

## 5. Zod 型のプロバイダ別サポート

| Zod 型 | OpenAI | Gemini | Claude |
|--------|--------|--------|--------|
| `z.string()` | OK | OK | OK |
| `z.number()` | OK | OK | OK |
| `z.boolean()` | OK | OK | OK |
| `z.null()` | OK | **NG** (nullable: true) | OK |
| `z.literal()` | OK | **制限あり** (enum 変換) | OK |
| `z.enum()` | OK | OK | OK |
| `z.object()` | OK | OK | OK |
| `z.array()` | OK | OK | OK |
| **`z.optional()`** | **NG（単体）** | OK | OK |
| `z.nullable()` | OK | OK | OK |
| `z.union()` | OK (anyOf) | **NG** | OK |
| `z.discriminatedUnion()` | OK (anyOf) | **NG** | OK |
| `z.intersection()` | OK (allOf) | **NG** | OK |
| `z.lazy()` (再帰) | OK ($ref) | **NG** | OK |
| `z.record()` | **NG** | **NG** | OK |
| `z.any()` / `z.unknown()` | NG | NG | NG |
| `z.date()` / `z.bigint()` | NG | NG | NG |
| `z.transform()` / `z.refine()` | 無視 | 無視 | 無視 |
| `.min()` / `.max()` | **無視** | **無視** | best-effort |

---

## 6. マルチプロバイダ対応のベストプラクティス

### 全プロバイダで安全な Zod パターン

```typescript
const schema = z.object({
  // 必須フィールド: そのまま
  name: z.string().describe('名前'),

  // オプショナルフィールド: .nullable() を使う（.optional() は使わない）
  rate: z.string().nullable().describe('率。不明な場合は null'),

  // 配列: min/max はプロンプトでも指定する
  items: z.array(z.object({
    label: z.string().describe('ラベル'),
    value: z.string().describe('値'),
  })).describe('項目一覧。3〜5件で生成'),

  // enum: OK
  status: z.enum(['active', 'inactive']).describe('ステータス'),
});
```

### 避けるべきパターン

```typescript
// NG: optional 単体 → OpenAI エラー
rate: z.string().optional()

// NG: discriminatedUnion → Gemini エラー
z.discriminatedUnion('type', [
  z.object({ type: z.literal('a'), ... }),
  z.object({ type: z.literal('b'), ... }),
])

// NG: 再帰スキーマ → Gemini エラー
const TreeNode = z.lazy(() => z.object({
  children: z.array(TreeNode),
}))

// NG: record → OpenAI + Gemini エラー
z.record(z.string(), z.number())

// 注意: min/max → OpenAI + Gemini で無視
z.array(...).min(5).max(5) // プロンプトでも件数を指定すること
```

### optional フィールドの推奨対処法

```typescript
// 推奨: .nullable() + describe で null 時の挙動を明示
rate: z.string().nullable().describe('絞り込み率（例: "10%"）。不明な場合は null')

// 代替: デフォルト値
rate: z.string().default('').describe('絞り込み率。不明な場合は空文字')
```

### discriminatedUnion の代替（Gemini 対応が必要な場合）

```typescript
// NG: Gemini 非対応
z.discriminatedUnion('slideType', [
  z.object({ slideType: z.literal('title'), title: z.string() }),
  z.object({ slideType: z.literal('content'), body: z.string() }),
])

// OK: フラットな object + nullable フィールド
z.object({
  slideType: z.enum(['title', 'content']),
  title: z.string().nullable().describe('slideType=title の場合のみ'),
  body: z.string().nullable().describe('slideType=content の場合のみ'),
})
```

---

## 7. Vercel AI SDK (generateObject) での注意点

AI SDK の `generateObject` は内部で各プロバイダの structured output を利用する。

| プロバイダ | 内部実装 | 制約 |
|-----------|---------|------|
| `@ai-sdk/openai` | `response_format` + `strict: true` | OpenAI の全制約が適用 |
| `@ai-sdk/google` | `responseMimeType` + `responseSchema` | Gemini の全制約が適用 |
| `@ai-sdk/google-vertex` | 同上 | 同上 |
| `@ai-sdk/amazon-bedrock` | tool_use (forced) | Claude の制約（最も緩い） |
| `@ai-sdk/anthropic` | tool_use (forced) | 同上 |

### AI SDK 固有の注意

- `generateObject` に `providerOptions` (textVerbosity 等) を渡すと OpenAI で `AI_NoObjectGeneratedError` になることがある
- `output: 'array'` を使う場合も同じスキーマ制約が適用
- `Output.object({ schema })` を `generateText` 内で使う場合も同様の制約が適用
- AI SDK は Zod → JSON Schema → プロバイダ固有形式 の2段変換を行うため、変換エラーの可能性あり

---

## 8. BMG プロジェクト固有情報

### モデルマッピング (llmModels.ts)

| LlmModels enum | 実際のモデル ID | プロバイダ |
|----------------|----------------|-----------|
| `claude` | `jp.anthropic.claude-sonnet-4-6` | Bedrock |
| `claudeHaiku` | `jp.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock |
| `gpt` | `gpt-5-2025-08-07` | OpenAI |
| `gptMini` | `gpt-5-mini-2025-08-07` | OpenAI |
| `gpt54Mini` | `gpt-5.4-mini-2026-03-17` | OpenAI |

### ルート別スキーマ一覧（structured output 使用箇所）

| ルート | スキーマ複雑度 | optional 使用 | 注意点 |
|--------|--------------|--------------|--------|
| business-model-canvas | 12 fields | なし | OK |
| revise-canvas-field | 10 fields | なし | OK |
| market-research | 7 fields | なし | OK |
| market-research (enhanced/BMG-1822) | 20+ fields, nested | **要確認** | samFilters.rate 等 |
| kpi | nested array | なし | OK |
| journey / journeyElement | nested | なし | OK |
| generate-slide | 26 discriminated unions | なし | **Gemini 追加時は要注意** |
| lean-canvas | 14 fields | なし | OK |
| persona | nested array (max 3) | なし | `.max(3)` は OpenAI/Gemini で無視 |
| elevator-pitch | 1 field | なし | OK |
| generate-business-description | Output.object | なし | generateText + web_search |

### Temperature 戦略

- **Claude**: タスクごとに 0.3〜0.7
- **GPT-5 系**: 固定 1（GPT-5 の制約）
- **パターン**: `isClaude(llmModel) ? X : 1`

### 依存バージョン

- `ai`: ~4.3.16 (Vercel AI SDK)
- `@ai-sdk/amazon-bedrock`: ~2.2.12
- `@ai-sdk/openai`: ~1.3.24
- `zod`: ^3.25.76
