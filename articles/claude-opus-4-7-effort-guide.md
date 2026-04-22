---
title: 'Opus 4.7 に移行するなら "effort" を理解してからにしよう'
emoji: "🎚"
type: "tech"
topics: ["claude", "claudecode", "anthropic", "llm", "ai"]
published: true
---

## はじめに

Claude Opus 4.7 は 4.6 から価格据え置きのまま、14 ベンチマーク中 12 で性能が上回る。パッと見は「黙ってアップグレードすればいい」話に思える。

ところが実際に触ると、4.6 向けに書いたプロンプトの挙動が微妙に変わる。ツール呼び出しの回数が減る。トークン課金が 1.3 倍になることもある。原因のほとんどは、4.7 で追加された新 effort レベル **`xhigh`** と、effort パラメータそのものの扱いが厳格化されたことにある。

この記事では、Opus 4.7 / 4.6 の差分を押さえた上で、実務で一番迷う「effort の使い分け」を、Playwright E2E と Amplify ビルド監視という 2 つの具体的なワークロードで整理する。最後に、Claude Code 上で effort がどう制御されるのか（結論: できない）まで触れる。

## Opus 4.7 と 4.6 の違い（3 分で押さえる）

公式の What's new を読むとかなり長いが、実務に影響するのは以下 7 点に集約できる。

| 観点                      | Opus 4.6                  | Opus 4.7                                           |
| ------------------------- | ------------------------- | -------------------------------------------------- |
| 価格                      | $5 / $25（1M tokens）     | **据え置き**                                       |
| コーディング（93 タスク） | —                         | **解決率 +13%**                                    |
| CursorBench               | 58%                       | **70%**                                            |
| 画像最大解像度            | 1,568 px（~1.15 MP）      | **2,576 px（~3.75 MP）**                           |
| ビジョン精度              | 54.5%                     | **98.5%**                                          |
| effort レベル             | low / medium / high / max | **+ `xhigh` 追加**                                 |
| 思考制御                  | `budget_tokens`           | **`adaptive` のみ**（budget_tokens は 400 エラー） |

これに加えて、実装時に地味に刺さる **Breaking Change** が 3 つある。

- `temperature` / `top_p` / `top_k` を指定すると 400 エラー
- `thinking` コンテンツがデフォルトで返ってこなくなった（`display: "summarized"` で opt-in）
- トークナイザーが更新され、**同じテキストで 1.0〜1.35 倍**のトークンを消費する

つまり「モデル ID だけ差し替えれば OK」ではない。特に思考中の UI を出しているアプリは、何も対策しないとストリーミング開始までの長い沈黙が発生する。

## effort パラメータとは「頭の使い方の強度ダイヤル」

effort は、**Claude が応答にどれだけトークンを費やすか**を制御するパラメータだ。

```python
response = client.messages.create(
    model="claude-opus-4-7",
    output_config={"effort": "xhigh"},  # ← ここ
    ...
)
```

ポイントは 3 つ。

### 1. 全トークンに効く

思考（extended thinking）だけでなく、**ツール呼び出しの回数・本文の長さ・コメントの充実度**まで一括で変わる。低くすれば簡潔になり、高くすれば「計画を説明してから動く」ようになる。

### 2. ハードリミットではなく行動シグナル

「このくらい頑張って」というヒントであって、厳密な上限ではない。ハード上限が欲しければ `max_tokens`（1 リクエスト上限）や `task_budget`（エージェントループ全体の目安、4.7 で追加されたβ機能）を併用する。

### 3. レベル表（Opus 4.7）

```
low < medium < high（既定）< xhigh < max
         ↑                         ↑
       コスト重視                品質最優先
```

| レベル   | 位置づけ                                  | 推奨用途                               |
| -------- | ----------------------------------------- | -------------------------------------- |
| `low`    | 最も効率的                                | 短く範囲限定のタスク、サブエージェント |
| `medium` | バランス型                                | 平均的ワークフロー、コスト重視         |
| `high`   | **API デフォルト**                        | 品質とトークン効率のスイートスポット   |
| `xhigh`  | **コーディング/エージェントの推奨開始点** | 反復ツール呼び出し、長時間エージェント |
| `max`    | 真のフロンティア問題のみ                  | 過剰思考リスクあり、コストが大幅増     |

## 新 effort レベル `xhigh` の正体

`xhigh` は 4.7 で新設された **`high` と `max` の中間レベル**。Anthropic は以下のようなワークロードをメインターゲットに据えている。

- 30 分以上走る長時間エージェント
- トークン予算が数百万規模のタスク
- 反復的なツール呼び出し
- 詳細な Web 検索 / ナレッジベース検索

公式推奨は **「コーディングとエージェント用途は `xhigh` から始めろ」**。`max` は「真のフロンティア問題のみ」で、過剰思考によりむしろ品質が落ちるケースがあると明記されている。

### `xhigh` で気をつけること

- `max_tokens` を **64k 以上**に設定する（サブエージェント・ツール呼び出しの余地確保）
- トークン消費は `high` より**顕著に**増える
- 並行して `task_budget` を設定すると、モデルが自己抑制しながら仕事を終える

## ユースケース別の使い分け表

ここから実務の話。私の環境（Amplify Gen2 のモノレポ、React/Vite + AWS + Stripe）で頻出する 2 つのワークロードで整理する。

### Playwright E2E の場合

Playwright は以下の特徴がある。

- `navigate` / `click` / `fill` / `snapshot` を**何度も反復**
- モーダル・非同期表示への**適応的対処**が必要
- セレクタが取れない等の**失敗リカバリ**に推論が要る

これは `xhigh` の設計意図と完全に一致する。

| シナリオ                                   | 推奨 effort      |
| ------------------------------------------ | ---------------- |
| 探索的テスト / 新規シナリオ作成 / デバッグ | **`xhigh`**      |
| 安定した既存シナリオを 1〜2 ケース流す     | `high`           |
| 単純な画面遷移スモーク                     | `medium`         |
| flaky テストの根因調査                     | `max` を一時的に |

### Amplify ビルド監視の場合

Amplify のビルド監視は大きく 2 フェーズに分かれる。ここが面白いところで、**フェーズによって最適な effort が違う**。

| フェーズ                 | 内容                                     | 推奨 effort      |
| ------------------------ | ---------------------------------------- | ---------------- |
| ステータスポーリング     | `aws amplify get-job` を定期的に叩く     | `low` / `medium` |
| ログ解析・原因特定       | CloudWatch / ビルドログから原因を追う    | **`xhigh`**      |
| CFn 循環依存などの難案件 | スタック依存を静的解析しつつ修正案を練る | `max`            |

Playwright と同じく「反復ツール呼び出し＋仮説検証」フェーズが入るので、そこは `xhigh` が刺さる。一方、ただ完了を待つだけのポーリングに `xhigh` を使うのは完全な無駄遣いになる。

### 意思決定のフローチャート

```
そのタスクは
├─ ツール呼び出しを何度も繰り返すか？
│    YES → xhigh（4.7 ならここから）
│    NO
│     └─ 複雑な推論が要るか？
│           YES → high
│           NO
│            └─ 短く範囲限定か？
│                  YES → medium or low
│                  NO  → high（迷ったらこれ）
```

## Claude Code では effort をどう制御するか（結論: できない）

ここが今回の記事で一番伝えたい話。Claude Code（Cursor や Zed のエージェントモード含む）でコードを書いていて、「今どの effort で動いてるんだろう？」と気になったことはないだろうか。

### 公式の立場

Anthropic ドキュメントには、Claude Managed Agents について以下の一文しかない。

> Claude Managed Agents handles effort automatically.

**アルゴリズムは非公開**。ユーザー側で指定する手段も提供されていない。

### セッション内から観測できること

| 項目                  | 観測可否                          |
| --------------------- | --------------------------------- |
| 現在のモデル ID       | ✅ `claude-opus-4-7[1m]` 等わかる |
| **現在の effort 値**  | ❌ API レスポンスにも出ない       |
| effort が変わった瞬間 | ❌ 通知されない                   |
| 手動での effort 指定  | ❌ 不可                           |

### 間接的に使えるトグル

| 操作       | 実体                                                                      |
| ---------- | ------------------------------------------------------------------------- |
| 通常モード | Opus 4.7（effort はハーネス任せ）                                         |
| `/fast`    | **Opus 4.6 に切り替え**（これは effort 調整ではない。モデル自体が変わる） |

つまり Claude Code ユーザーが実用上できるのは「4.7（効率も品質も）」か「4.6（速さ重視）」の 2 択だけ。effort を細かく指定したければ、**自分のコードから Messages API を直接叩く**しかない。

### 自前コードで effort を指定するケース

BMG（Lean Quest）では、LLM 呼び出しは `packages/gen2-shared-backend/amplify/custom/hono/utils/llm-with-tracing.ts` に集約されている。ここは Vercel AI SDK 経由で Messages API を叩いているので、`effort` を明示指定できる。

```typescript
// Before（4.6 時代、adaptive thinking に乗る前）
const result = await generateObjectWithTracing({
  llmModel: "claude-opus-4-6",
  // thinking は budget_tokens で制御していた
});

// After（4.7、effort で制御）
const result = await generateObjectWithTracing({
  llmModel: "claude-opus-4-7",
  providerOptions: {
    anthropic: {
      output_config: { effort: "xhigh" }, // ビジネスモデル生成は重いので xhigh
    },
  },
});
```

ビジネスモデル生成のような長文出力タスクは `xhigh`、タイトル候補生成のような軽いものは `medium` と使い分けるのが素直。

## 移行でハマる 3 つのポイント

最後に 4.6 → 4.7 移行で踏みがちな地雷を 3 つ。

### 1. 字義通り解釈でプロンプトが機能しなくなる

4.7 は effort を**厳格に**尊重し、指示を**字義通り**に取る。4.6 時代は `low`/`medium` でも気を利かせて複数項目に一般化してくれたが、4.7 は言われた範囲でしか動かない。

**対策**: 指示は具体的に書く。推論が浅いと感じたら、プロンプトを盛るより先に effort を上げる。

### 2. トークン課金が 1.0〜1.35 倍に増える

新トークナイザーにより、同じ入出力でも課金量が増える。特に日本語・多言語・コードを多く含むワークロードで顕著。

**対策**: 本番切替前に 1 週間ほど並行運用して実コストを計測する。compaction トリガーや `max_tokens` に余裕を持たせる。

### 3. thinking 非表示で UI が沈黙する

4.7 はデフォルトで `thinking` 内容を返さない。ストリーミング UI で「考え中…」を出していると、実装によっては**真っ白な沈黙時間**が発生する。

**対策**: `thinking: { type: "adaptive", display: "summarized" }` を明示する。レスポンスタイムは若干犠牲になるが、UX は大きく改善する。

## まとめ

- Opus 4.7 は「価格据え置きで性能アップ」だが、**effort を理解しないとコストも挙動も変わる**
- 新 `xhigh` は**コーディング・反復ツール呼び出し・長時間エージェント**の新デフォルト
- `max` は万能ではない。過剰思考でむしろ品質が落ちるケースがあるので、**評価で頭打ちを確認してから**使う
- **Claude Code では effort を直接制御できない**。細かく効率化したければ Messages API 直叩き
- 4.6 → 4.7 移行で踏みがちな地雷は「字義通り解釈」「トークン 1.3 倍」「thinking 沈黙」の 3 つ

「速い最新モデルが出たら乗り換える」で済んだ時代は、4.7 で少し終わった。effort というダイヤルが増えた分、**ワークロードごとに設計する手間が 1 ステップ増えた**と思ったほうがいい。その代わり、ちゃんと使い分ければ品質もコストも同時に改善できる。

手元の LLM 呼び出しコードで、まず 1 箇所だけ `xhigh` を試してみるところから始めてみてほしい。

## 参考

- [Introducing Claude Opus 4.7 — Anthropic](https://www.anthropic.com/news/claude-opus-4-7)
- [What's new in Claude Opus 4.7 — Claude API Docs](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7)
- [Effort — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Task budgets (beta) — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/task-budgets)
- [Adaptive thinking — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)
