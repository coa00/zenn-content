---
title: "Amplify Gen2 のサーバーサイドで「Content unavailable」エラーが出たら authMode を疑え"
emoji: "🔐"
type: "tech"
topics: ["amplify", "nextjs", "aws", "appsync", "cognito"]
published: true
---

## はじめに

AWS Amplify Gen2 + Next.js（App Router）で開発中、サーバーサイドから GraphQL API を呼び出したところ、こんなエラーに遭遇しました。

```
Content unavailable. Resource was not cached
```

「キャッシュ？なにそれ？」と思いながら調べた結果、**サーバーサイドクライアントの `authMode` 未指定**が原因でした。

この記事では、なぜこのエラーが発生するのか、Amplify Gen2 の認可の仕組みとともに解説します。

## 再現する状況

以下のような構成を想定します。

- **Amplify Gen2** でバックエンドを構築
- **Next.js App Router** の Server Actions でデータ操作
- Cognito User Pool を使ったユーザー認証
- モデルに `allow.group()` や `allow.ownerDefinedIn()` の認可ルールを設定

例えば、こんなスキーマがあるとします。

```ts
// amplify/data/resource.ts
const schema = a.schema({
  Owner: a.model({
    name: a.string().required(),
    email: a.string().required(),
    ownerId: a.string().required(),
  })
  .authorization((allow) => [
    allow.group('Admin'),
    allow.ownerDefinedIn('ownerId').identityClaim('custom:ownerId'),
  ]),
});
```

このモデルに対して、Server Actions からデータを作成しようとすると…

```ts
// Server Action
const client = generateServerClientUsingCookies<Schema>({
  config: outputs,
  cookies,
});

// ここでエラー！
const { data } = await client.models.Owner.create({
  name: "テストオーナー",
  email: "test@example.com",
  ownerId: "owner-123",
});
// → "Content unavailable. Resource was not cached"
```

## 原因：IAM 認証へのフォールバック

### Amplify Gen2 では IAM が常に有効

Amplify Gen2 には、あまり知られていない（でも重要な）仕様があります。

> All Amplify Gen 2 projects enable IAM authorization for data access.
> — [Customize your auth rules - AWS Amplify Gen 2 Documentation](https://docs.amplify.aws/javascript/build-a-backend/data/customize-authz/)

**全プロジェクトで IAM 認証が有効化されている**のです。これは Amplify コンソールのデータマネージャーがアクセスできるようにするためですが、副作用があります。

### サーバーサイドで authMode を省略するとどうなるか

`generateServerClientUsingCookies` で `authMode` を指定しないと、サーバーサイドのコンテキストでは **IAM 認証（サーバーの IAM ロール）にフォールバックする可能性**があります。

スキーマで `defaultAuthorizationMode: 'userPool'` を設定していても、それはクライアントサイドでの話。サーバーサイドでは必ずしもそうなりません。

### エラー発生の流れ

```
Server Action が実行される
  ↓
generateServerClientUsingCookies で client を生成（authMode 未指定）
  ↓
サーバーサイドコンテキストで IAM 認証が使用される
  ↓
Owner.create() を実行
  ↓
AppSync が Owner モデルの認可ルールをチェック:
  - allow.group('Admin')             ← Cognito トークンが必要
  - allow.ownerDefinedIn('ownerId')  ← Cognito トークンが必要
  ↓
IAM 認証には対応する認可ルールがない
  ↓
deny-by-default により拒否
  ↓
"Content unavailable. Resource was not cached"
```

### deny-by-default 原則

ここがポイントです。AppSync の認可ルールは **deny-by-default** で動作します。

> Authorization rules operate on the deny-by-default principle. Meaning that if an authorization rule is not specifically configured, it is denied.
> — [Customize your auth rules - AWS Amplify Gen 2 Documentation](https://docs.amplify.aws/javascript/build-a-backend/data/customize-authz/)

IAM 認証でリクエストが送られても、モデルに IAM 用の認可ルール（`allow.resource()` 等）がなければ、アクセスは拒否されます。エラーメッセージが「キャッシュがない」という一見無関係な内容なのが厄介ですが、実体は認可エラーです。

## authMode と認可ストラテジーの対応関係

どの認可ルールがどの authMode に対応するかを理解しておくと、この手の問題を防げます。

| 認可ストラテジー | 対応する authMode |
|---|---|
| `publicApiKey` | `apiKey` |
| `guest` | `identityPool` |
| `owner` / `ownerDefinedIn` / `ownersDefinedIn` | **`userPool`** / `oidc` |
| `authenticated` | `userPool` / `oidc` / `identityPool` |
| `group` / `groups` / `groupDefinedIn` / `groupsDefinedIn` | **`userPool`** / `oidc` |
| `custom` | `lambda` |
| `resource` | IAM（Lambda 関数等） |

> When combining multiple authorization rules, they are "logically OR"-ed. On the client side, make sure to always authenticate with the corresponding authorization mode.
> — [Customize your auth rules - AWS Amplify Gen 2 Documentation](https://docs.amplify.aws/javascript/build-a-backend/data/customize-authz/)

つまり `allow.group()` や `allow.ownerDefinedIn()` を使っているモデルには、`userPool` の authMode でアクセスしなければなりません。

## 解決策

`authMode: 'userPool'` と ID Token を明示的に指定します。

```ts
import { generateServerClientUsingCookies } from '@aws-amplify/adapter-nextjs/data';
import { fetchAuthSession } from 'aws-amplify/auth/server';
import { cookies } from 'next/headers';

export async function getCookiesClientWithIdToken() {
  const token = await runWithAmplifyServerContext({
    nextServerContext: { cookies },
    operation: async (contextSpec) => {
      const session = await fetchAuthSession(contextSpec);
      return session?.tokens?.idToken?.toString() || '';
    },
  });

  return generateServerClientUsingCookies<Schema>({
    config: outputs,
    cookies,
    authMode: 'userPool',  // 明示的に指定
    authToken: token,       // ID Token を渡す
  });
}
```

### なぜ Access Token ではなく ID Token なのか

Cognito は Access Token と ID Token の2種類のトークンを発行します。

| | Access Token | ID Token |
|---|---|---|
| `cognito:groups` | あり | あり |
| カスタム属性（`custom:ownerId` 等） | **なし** | **あり** |

`allow.ownerDefinedIn('ownerId').identityClaim('custom:ownerId')` のように**カスタム属性**を使った認可ルールがある場合、ID Token でないとその属性が含まれないため認可に失敗します。

`allow.group()` だけであれば Access Token でも動作しますが、owner ベースの認可と併用する場合は **ID Token を使うのが安全**です。

## authMode 指定あり・なしの比較

| | 指定なし（デフォルト） | `authMode: 'userPool'` |
|---|---|---|
| 認証方式 | IAM ロール（サーバーのロール） | ユーザーの Cognito トークン |
| Authorization ヘッダー | AWS SigV4 署名 | Cognito トークン文字列 |
| `allow.group('Admin')` | 評価不可（グループ情報なし） | 評価可能 |
| `allow.ownerDefinedIn(...)` | 評価不可（`custom:ownerId` なし） | 評価可能 |

## 公式ドキュメントの罠

公式ドキュメントの `generateServerClientUsingCookies` の基本例では `authMode` が省略されています。

```ts
// 公式ドキュメントの例
export const cookieBasedClient = generateServerClientUsingCookies<Schema>({
  config: outputs,
  cookies,
});
```

> — [Next.js server runtime - AWS Amplify Gen 2 Documentation](https://docs.amplify.aws/nextjs/build-a-backend/data/connect-from-server-runtime/nextjs-server-runtime/)

この例をそのまま使うと、`defaultAuthorizationMode` の設定に依存した動作になります。owner ベースや group ベースの認可を使っている場合、この例だけでは不十分です。

## まとめ

- Amplify Gen2 のサーバーサイドで `generateServerClientUsingCookies` を使う際は、**`authMode: 'userPool'` を明示的に指定**する
- 指定しないと IAM 認証にフォールバックし、`allow.group()` / `allow.ownerDefinedIn()` の認可ルールが評価されない
- 「Content unavailable. Resource was not cached」は**認可エラー**のサイン
- カスタム属性を使った認可がある場合は、**ID Token**（Access Token ではなく）を使用する
- 公式ドキュメントの基本例は `authMode` を省略しているので注意

「Content unavailable. Resource was not cached」というエラーメッセージは認可と関係なさそうに見えるので、ハマるとなかなか原因に辿り着けません。同じエラーに遭遇した方の助けになれば幸いです。

## 参考

- [Connect your app code to API - AWS Amplify Gen 2 Documentation](https://docs.amplify.aws/nextjs/build-a-backend/data/connect-to-API/)
- [Next.js server runtime - AWS Amplify Gen 2 Documentation](https://docs.amplify.aws/nextjs/build-a-backend/data/connect-from-server-runtime/nextjs-server-runtime/)
- [Customize your auth rules - AWS Amplify Gen 2 Documentation](https://docs.amplify.aws/javascript/build-a-backend/data/customize-authz/)

## 最後に

株式会社ピュアポムメディアラボ（PML）では、AI を活用した開発支援やプロダクト開発に取り組んでいます。

Claude Code をはじめとする AI ツールを活用した開発に興味のある方、一緒に働きませんか？

- 採用情報・お問い合わせ: https://purpom-media-lab.com/

お気軽にお声がけください。
