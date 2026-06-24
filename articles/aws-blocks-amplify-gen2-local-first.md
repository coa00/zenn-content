---
title: "AWS Blocks を実プロジェクトで試した — Amplify Gen2 にローカル開発を足す"
emoji: "🧱"
type: "tech"
topics: ["aws", "amplify", "awsblocks", "dynamodb", "cdk"]
published: true
---

## はじめに

Amplify Gen2 を実務でずっと使っているのですが、一番つらいのが「動作確認のたびにデプロイが要る」ことです。バックエンドをちょっと直して `ampx sandbox` で上げて、反映を待って、確認して、また直して・・というのを一日に何回も繰り返すと、地味に効いてきます。

そこに 2026-06-16、**AWS Blocks** が公開プレビューで出てきました。auth・database・file storage・real-time・async jobs・AI agents みたいな「バックエンドの部品（Building Blocks）」を組み合わせて使うやつで、売りは **AWS アカウントなしでローカル完結で開発できる** こと。

ただ、プレビューの発表文を読んでも、私が知りたいことは書いてありませんでした。具体的にはこの3つです。

- これ、**Amplify から移行するもの？** それとも今の Amplify Gen2 に足せるもの？
- **DynamoDB はローカルで作れるのか？**（ここが一番気になる）
- 結局 **開発ループはどれだけ速くなるのか**

なので発表文をにらんでいても仕方ないので、稼働中の実プロジェクト（40 以上のモデルを持つ Amplify Gen2 アプリ）に、隔離した git worktree の中で実際に入れてみました。ローカルで DynamoDB を動かして、`cdk synth` まで回して確認しています。

先に結論を書くと、**移行ではなく加算**、**DynamoDB はローカルで動く**、**検証ループは「数分のデプロイ往復」から「1秒のローカル反映」に変わった**、でした。以下はその検証ログです。プレビューなのでハマったところもそのまま書きます。

:::message
検証時点のバージョン: `@aws-blocks/create-blocks-app@0.1.7` / `@aws-blocks/blocks@0.1.5`。プレビューなので今後変わるはず。
:::

## まず「Amplify と別物なのか」から

公式の言い方ははっきりしていて、**「Blocks is not replacing Amplify. It's additive.（置き換えるんじゃなくて足すもの）」**。使い方は2通りです。

- **Amplify Gen2 アプリに個々の Block を足す** → デプロイは今まで通り Amplify。部品だけ増える。
- **standalone で使う** → フル所有・ローカル完結。AWS アカウントなしでも開発できる。

どっちも同じ Block で、パス間の書き直しはなし。底は全部 CDK construct なので、足りなくなったら生の CDK に落ちられます。

ここで勘違いしやすいのが、「standalone モードがある＝Amplify から引っ越すもの」だと思ってしまうこと。私も最初そう身構えました。ただ standalone はあくまで別の選択肢で、既存 Amplify を捨てる話ではない。とはいえ口で言われても信じきれないので、実プロジェクトに入れて確かめます。

## 実プロジェクトに入れてみる（auto-detect）

検証台は、`apps/*` と `packages/*` を抱えた pnpm ワークスペースのモノレポ。Amplify Gen2 バックエンドは `packages/gen2-shared-backend/amplify/backend.ts` にあって、`amplify/data/resource.ts` には `a.model()` で定義した 40 以上の DynamoDB モデル（User / Workspace / Project / BusinessModel / LeanCanvas …）が並んでいます。本番でも動いているやつなので、当然そのまま壊されたら困ります。

本体を汚さないよう、隔離した worktree を切ってから作業しました。

```zsh
git worktree add ./<repo>.worktrees/aws-blocks-test --detach staging
cd ./<repo>.worktrees/aws-blocks-test/packages/gen2-shared-backend
```

`amplify/backend.ts` がある場所で CLI を叩きます。AWS Blocks の CLI は実行先のディレクトリを見て、モードを自動で判定してくれます（Amplify 検出 / 既存プロジェクト / 空ディレクトリの3つ）。

```zsh
pnpm dlx @aws-blocks/create-blocks-app@latest . -y
```

出力はこう。

```text
🔍 Detected Amplify Gen 2 project (amplify/backend.ts found)

  CREATE  aws-blocks/           (Blocks backend workspace)
  CREATE  amplify/blocks.ts     (wires Blocks into Amplify backend)
  MODIFY  amplify/backend.ts    (adds import for blocks.ts)
  MODIFY  package.json          (adds workspace, deps, scripts)
  MODIFY  .gitignore            (adds Blocks entries)
```

ちゃんと Amplify Gen2 として認識されました。私が気にしていたのは **既存の 40 モデルや auth・storage・大量の Lambda リゾルバがどうなるか**。`backend.ts` の差分を見て、ほっとしました。

```diff
-const backend = defineBackend({
+export const backend = defineBackend({
   auth,
   data,
   storage,
   // ... 既存の resolver 群はそのまま ...
 });

 backend.addOutput({ /* 既存 */ });
+
+// Blocks integration — adds Building Blocks to your Amplify backend
+import { initBlocks } from './blocks.js';
+await initBlocks(backend);
```

**書き換えじゃなくて追記です。** `const` を `export const` にして、末尾に `initBlocks(backend)` を1行足しただけ。548 行ある `backend.ts` の既存定義は1行も変わっていません。生成された `amplify/blocks.ts` を見ると、Blocks は **別の nested stack** として組み込まれて、Amplify の Cognito 設定（User Pool ID / Client ID）を Blocks 側の Lambda に環境変数で渡しています。

```typescript
// amplify/blocks.ts（生成物・抜粋）
export async function initBlocks(backend: any) {
  const blocksStack = backend.createStack('blocks');
  const blocks = await createBlocksBackend(blocksStack, sandboxMode);

  // Amplify の Cognito を Blocks の bearer-token 検証に流用
  if (backend.auth?.resources?.cfnResources) {
    const { cfnUserPool, cfnUserPoolClient } = backend.auth.resources.cfnResources;
    blocks.handler.addEnvironment('COGNITO_USER_POOL_ID', cfnUserPool.ref);
    blocks.handler.addEnvironment('COGNITO_CLIENT_ID', cfnUserPoolClient.ref);
  }
  // ...
}
```

というわけで **「移行ではなく加算」は本当**でした。既存の Amplify Data（＝既存の DynamoDB テーブル群）はそのまま残って、その横に Blocks のスタックが並ぶ。認証も Amplify の Cognito を使い回します。引っ越しではない、と。

## ハマりポイント: pnpm モノレポで install がコケる

ただ、ここで素直には終わりませんでした。CLI はファイル生成のあと、内部で勝手に `npm install` を走らせるんですが、これが落ちます。

```text
npm error code EUNSUPPORTEDPROTOCOL
npm error Unsupported URL Type "workspace:": workspace:*
```

原因は、検証台が **pnpm ワークスペース** で、依存に pnpm 独自の `workspace:*` プロトコルを使っているから。AWS Blocks の CLI は `npm install` 決め打ちで、しかも生成した `package.json` に npm 形式の `workspaces` 配列を足してくる。pnpm モノレポとは二重にケンカします。

ファイル生成（scaffold）自体は成功しているので、依存解決を手で pnpm に寄せれば前には進めます。ただ「`npx` 一発でOK」という体験ではない。**pnpm モノレポに入れるなら、install は自前で握る前提**で考えておくのが現実的でした。プレビューなのでこのへんは仕方ない、と割り切ります。

で、「ローカルで実際に DynamoDB を触る」検証は、この衝突がない **standalone の素プロジェクト**で別にやることにしました。Amplify への組み込み挙動（上）と、ローカル実行の実証（下）を分けて確かめる作戦です。

## 本題: ローカルで DynamoDB を作る

standalone のバックエンドテンプレートを作ります。こっちは npm 前提なので素直に通ります。

```zsh
pnpm dlx @aws-blocks/create-blocks-app@latest standalone --template backend -y
# → 284 packages を install して約 29 秒で完成
```

バックエンドのエントリは `aws-blocks/index.ts`。ここに **DynamoDB の Block** を足します。AWS Blocks のデータ系 Block は用途で分かれていて、

- `KVStore`（`@aws-blocks/bb-kv-store`）= 単純な key-value（DynamoDB バック）
- **`DistributedTable`（`@aws-blocks/blocks`）= DynamoDB そのもの**。複合キー・GSI・range クエリができて「most data の既定」と書いてある

今回は DynamoDB を正面から触りたいので `DistributedTable`。スキーマは zod で書きます。

```typescript
// aws-blocks/index.ts
import { ApiNamespace, Scope, DistributedTable } from '@aws-blocks/blocks';
import { z } from 'zod';

const scope = new Scope('my-app');

// DistributedTable = DynamoDB。
// ローカル dev では in-process モック / synth・deploy では本物の DynamoDB。同じコード。
const noteSchema = z.object({
  userId: z.string(),
  noteId: z.string(),
  body: z.string(),
  createdAt: z.number(),
});

const notes = new DistributedTable(scope, 'notes', {
  schema: noteSchema,
  key: { partitionKey: 'userId', sortKey: 'noteId' },
});

export const api = new ApiNamespace(scope, 'api', (context) => ({
  async putNote(userId: string, noteId: string, body: string) {
    await notes.put({ userId, noteId, body, createdAt: Date.now() });
    return { ok: true };
  },
  async getNote(userId: string, noteId: string) {
    return await notes.get({ userId, noteId });
  },
  async listNotes(userId: string) {
    return await Array.fromAsync(
      notes.query({ where: { userId: { equals: userId } } }),
    );
  },
}));
```

型は最後まで通ります（`tsc --noEmit` で約 2.7 秒）。スキーマからキーの型が推論されるので、`get({ userId, noteId })` のキー要求まで TypeScript が面倒を見てくれる。コード生成のステップはなし。地味にうれしいやつです。

ローカルサーバを起動します。

```zsh
npm run dev
# Loading backend...
# Deploying local resources...
# 📝 Generating client code...
# AWS Blocks local server running on http://localhost:3001
```

`Deploying local resources` と言っていますが、**AWS には一切繋いでいません**。`.blocks-sandbox/config.json` を見ると `"environment": "local"` で、API はローカルの `http://localhost:3001/aws-blocks/api` を向いています（3000 が別プロセスで埋まっていたので勝手に 3001 に逃げてくれました）。

この状態で、型付きクライアント経由で DynamoDB の Block を叩きます。

```text
getNote(alice,n1): {"userId":"alice","noteId":"n1","body":"first note","createdAt":1782292043870}
listNotes(alice) count: 2
listNotes(bob): [{"userId":"bob","noteId":"n1","body":"bob note",...}]
put×3 + get + query×2 の往復: 31ms
```

**動きました。** AWS アカウントなし・デプロイなしで、DynamoDB の put / get / partition key クエリが回って、`alice` と `bob` のパーティション分離もちゃんと効いている。3回の書き込み＋読み＋2回のクエリで往復 **31ms**。これがデプロイだと数分待たされていた部分です。

### 「ローカルのモックでしょ？」を synth で確かめる

ここで疑うべきは「ローカルで動くのは分かった。でもデプロイしたら本当に DynamoDB になるの？」です。ここが AWS Blocks の肝で、`@aws-blocks/blocks` の `package.json` は **conditional exports** を使って、同じ import を文脈ごとに別物に解決します。

```json
".": { "browser": "...client...", "cdk": "...construct...", "default": "...local/lambda..." }
```

- ローカル dev（`default`）→ in-process モック
- `cdk synth`（`cdk`）→ CDK construct（＝CloudFormation）
- ブラウザ（`browser`）→ 型付き RPC クライアント

なので **同じ `index.ts` のまま** `cdk synth` を回します（デプロイじゃないので AWS 認証は不要）。

```zsh
npx cdk synth --quiet
```

生成された CloudFormation テンプレートを覗くと、ちゃんといました。

```text
AWS::DynamoDB::Table count: 1
 logicalId: myappnotestable...
   BillingMode: PAY_PER_REQUEST
   KeySchema: userId:HASH, noteId:RANGE
```

`new DistributedTable(..., { key: { partitionKey: 'userId', sortKey: 'noteId' } })` の1行が、**ローカルでは即時モック、synth では本物の `AWS::DynamoDB::Table`（HASH=userId / RANGE=noteId、オンデマンド課金）** に解決される。コードは1文字も変えていません。これが「ローカルで DynamoDB が作れる」の中身でした。

## GSI と LSI はどうなるのか（ここで一回ハマった）

DynamoDB を使うとなると、当然インデックスが気になります。`DistributedTable` には `indexes` オプションがあるので、GSI を2本張って、ついでに LSI も作れるのか試しました。

```typescript
const notes = new DistributedTable(scope, 'notes', {
  schema: noteSchema, // userId, noteId, status, createdAt, body
  key: { partitionKey: 'userId', sortKey: 'noteId' },
  indexes: {
    // 同じ PK(userId) + 別 SK(createdAt) → 素の DynamoDB なら LSI 候補
    byCreatedAt: { partitionKey: 'userId', sortKey: 'createdAt' },
    // 別 PK(status) → 明確に GSI
    byStatus: { partitionKey: 'status', sortKey: 'createdAt' },
  },
});
```

ローカルでは普通に動きました。`byCreatedAt` で createdAt 昇順（100, 200, 300）、`byStatus` で status 横断の取得もOK。

ところが `cdk synth` した CloudFormation を見て、一瞬「あれ？」となりました。

```text
GlobalSecondaryIndexes: []
LocalSecondaryIndexes: []
AttributeDefinitions: [userId, noteId]   # createdAt も status も無い
```

テーブル本体に **GSI も LSI も無い**。最初は「インデックス、synth に乗らないのか・・」と早とちりしました。ただテンプレート全体を漁ると、別のところにいました。`Custom::CloudFormation::CustomResource`（`my-app-notes-gsi-resource`）の `Indexes` プロパティに、`byCreatedAt` と `byStatus` がちゃんと載っている。さらに `BlocksGsiManager` という Lambda 一式（Provider framework の onEvent / isComplete / Step Functions waiter）が生成されていました。

つまり **GSI はインライン CFN ではなく、専用の custom resource ＋ GSI Manager Lambda が管理する** 仕組みでした。理由は DESIGN.md に書いてあって、なるほどと思いました。

> DynamoDB は1回の `UpdateTable` で GSI 変更を1つしか許さない。標準 CDK の `Table` では複数 GSI 変更を1デプロイで表現できない。だから custom resource で宣言的に管理する。

本番デプロイでは GSI を1つずつ順番に適用（DynamoDB の制約どおり）、sandbox では「テーブルごと drop して全 GSI 付きで作り直す」高速パスを使い分ける、と。GSI 1本を増やすのに本番で数分〜数時間かかる現実に、けっこう真面目に向き合った設計です。

一方で **LSI はサポートされていません**。`indexes` は名前のとおり Global secondary index 専用で、私が「LSI 候補」のつもりで書いた `byCreatedAt`（同じ PK + 別 SK）も、扱いは GSI です。DESIGN.md も "partition key + optional sort key + GSIs" としか書いていないし、GSI Manager が叩くのも `GlobalSecondaryIndexUpdates` だけ。DynamoDB の LSI はテーブル作成時にしか張れない制約があって、後付け UpdateTable のパスに振り切っている以上、**LSI を作る手段が無い**、というのが実態でした。

| | サポート | デプロイ時の実体 | ローカル |
|---|---|---|---|
| **GSI** | ○ あり | Custom Resource + GSI Manager Lambda（`UpdateTable` を順次） | クエリ動作（in-memory filtering） |
| **LSI** | ✕ 実質なし | 生成手段なし（同 PK+SK も GSI 扱い） | インデックス指定クエリ自体は動くが LSI ではない |

ひとつ注意。ローカルのインデックスは「全件 in-memory フィルタ」で実装されているので、**実 GSI の結果整合性（ローカルは即時整合）やスループットのスロットリングは再現されません**。アクセスパターンの正しさはローカルで確認できるけど、整合性・性能まわりは sandbox で見てね、と DESIGN.md にも明記されていました。ここは素直に従うのが良さそうです。

## 速度: 検証ループはどう変わったか

実測値です（standalone・依存 install 済みの状態）。

| 項目 | 実測 |
|---|---|
| scaffold + 依存 install（cold） | 約 29s（284 packages） |
| `tsc --noEmit`（型チェック） | 約 2.7s |
| `npm run dev` 起動 → ローカル ready | **約 1.23s** |
| ハンドラ1行編集 → 再反映（HMR） | **約 1.03s** |
| DynamoDB ローカル往復（put×3+get+query×2） | **31ms** |

効くのは数字そのものより、**動作確認に AWS が要らない**こと。Amplify Gen2 を普通に開発していると、バックエンドを少し直すたびに `ampx sandbox` のデプロイ往復（数十秒〜数分）を待つ羽目になります。冒頭で書いた「つらい」の正体はこれでした。AWS Blocks のローカルファースト開発は、その往復を **1秒のファイル反映** に置き換えてくれます。

:::message
公平のために書くと、これは同一条件の頭付き比較ではありません。Amplify の `ampx sandbox` 実デプロイは今回計測していません（クラウドに変更を加えるので）。比較の前提は「ローカル秒オーダー vs デプロイ数分オーダー」という構造の差です。Amplify のフルビルドの実測は、別記事「Amplify Gen2 のビルドをカスタム Docker イメージで高速化する」で 9m43s→8m45s という数字を出しています。
:::

## 余談: AI エージェントとの相性

主軸からは外れますが、個人的に一番おもしろかったのがここ。AWS Blocks は「agent-native」を名乗っていて、npm パッケージに **steering files** が同梱されています。scaffold すると `AGENTS.md` が置かれて、`node_modules/@aws-blocks/blocks/docs/<package>.md` に Block ごとの使い方が入っている。

`AGENTS.md` にはこんなルールが書いてあります。

> - **Use Building Blocks** for all persistence — never local files, in-memory arrays, or local databases.
> - **Read block docs** at `node_modules/@aws-blocks/blocks/docs/<package-name>.md` before using a block.
> - **The JSON-RPC transport is invisible** — do not construct RPC payloads manually.

要は「永続化は必ず Block を使え」「ローカルファイルやインメモリ配列でごまかすな」と、エージェントに先回りで釘を刺してある。実際さっきの GSI の話でも、`DistributedTable` のドキュメントには「データメソッドはハンドラの中で呼べ。トップレベルは synth 文脈なので `table.get is not a function` で落ちる」という、AI が踏みがちな罠まで書いてありました。コードを書く前にこの作法が手元（`node_modules`）に揃っているので、エージェントに任せても変な方向に転びにくい。ローカルで即検証できるのと合わせて、AI に書かせる→すぐ回す、のサイクルが締まります。

## まとめ

実プロジェクトで試した結論です。

- **移行ではなく加算**。Amplify Gen2 の `backend.ts` には `initBlocks(backend)` が1行足されるだけで、既存の 40 モデル・auth・storage・リゾルバ群は無変更。Blocks は別の nested stack で併存し、認証は Amplify の Cognito を流用する。standalone は「別の選択肢」で、引っ越しではない。
- **DynamoDB はローカルで作れる**。`DistributedTable` 1つで、ローカル dev は in-process モック（put/get/query が 31ms・AWS アカウント不要）、`cdk synth` では本物の `AWS::DynamoDB::Table` に解決される。同じコードのまま。
- **GSI は使える、ただし custom resource 経由**。インライン CFN ではなく GSI Manager Lambda が `UpdateTable` で順次適用する設計。**LSI はサポートなし**。インデックス重視のテーブル設計をしている人は、ここは事前に知っておくと事故らないです。
- **検証ループが変わる**。dev 起動 1.2 秒、ハンドラ編集の反映 1 秒。「デプロイしないと動作確認できない」が、ローカル即反映になる。
- ただし **プレビュー相応の摩擦**はある。pnpm モノレポでは CLI 内部の `npm install` が `workspace:*` で落ちるので、install は自前で握る前提に。

「Amplify を捨てて乗り換える」ではなく、「Amplify Gen2 にローカル開発を足して、動作確認をクラウドから手元に取り戻す」。AWS Blocks をひとことで言うとそういう道具でした。重い Amplify 開発に心当たりがある人は、まず standalone テンプレートで `npm run dev` を1回回してみるのが、たぶん一番早い。GSI/LSI まわりで「こう使えたよ」みたいな話があれば、ぜひ教えてください。

## 参考

- [AWS Blocks（公式プロダクトページ）](https://aws.amazon.com/products/developer-tools/blocks/)
- [AWS Blocks 公開プレビュー発表（2026-06-16）](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-blocks-preview/)
- [AWS Blocks 開発者ガイド: Concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html)
- [aws-devtools-labs/aws-blocks（GitHub）](https://github.com/aws-devtools-labs/aws-blocks)
- [AWS Blocks を試した（DevelopersIO）](https://dev.classmethod.jp/en/articles/20260620-aws-blocks-preview/)
- [AWS Blocks framework preview（InfoQ）](https://www.infoq.com/news/2026/06/aws-blocks-framework-preview/)
