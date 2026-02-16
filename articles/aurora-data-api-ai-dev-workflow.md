---
title: "Aurora Data API を有効化したら、AI エージェントが DB を直接操作できるようになった話"
emoji: "🗄️"
type: "tech"
topics: ["aws", "aurora", "claudecode", "mcp", "devops"]
published: true
---

## はじめに

Aurora MySQL のデータベースにアクセスする方法として、多くのチームが「踏み台サーバー（Bastion Host）+ SSM Session Manager」を使っていると思います。私たちのチームも長らくそうでした。

2024年9月、AWS が Aurora MySQL で **RDS Data API** のサポートを発表しました。当初は「Lambda から VPC なしで DB に繋げるようになるのか、便利だな」程度の認識でしたが、実際に導入してみると **想定以上にチームの開発体験が変わりました**。

特に大きかったのが、Claude Code や Cursor といった AI コーディングツールから直接データベースを操作できるようになったことです。

本記事では、実際のプロダクション環境（Aurora MySQL Serverless v2）での導入経験をもとに、Data API と SSM Session Manager の使い分け、そして AI ツール連携がもたらすワークフローの変化についてまとめます。

## TL;DR

- **Data API** は Aurora 専用の HTTPS ベース SQL 実行 API。有効化はほぼゼロコスト
- **SSM 踏み台**と補完関係にあり、併用がベスト
- Data API を有効化すると **Claude Code / Cursor などの AI ツールが DB を直接操作**できるようになる
- チームの学習コスト削減、踏み台運用の簡素化、自動化の促進など、技術的負債の軽減に直結する
- Aurora を使っているなら、有効化しない理由がない

## RDS Data API とは

RDS Data API は、Aurora に対して **HTTPS 経由で SQL を実行できる REST API** です。

従来のデータベース接続が TCP/IP の MySQL プロトコルを前提とするのに対し、Data API は AWS SDK や CLI の HTTP リクエストだけで完結します。VPC 内にいる必要がありません。

### 対応エンジンと制約

Data API は **Aurora 専用**です。標準 RDS では利用できません。

| エンジン | Data API |
|---|---|
| Aurora MySQL（v3.07+） | 対応 |
| Aurora PostgreSQL（v13.12+, 14.9+, 15.4+） | 対応 |
| 標準 RDS MySQL / PostgreSQL | 非対応 |

主な制限は以下の通りです。

| 制限 | 値 |
|---|---|
| レスポンスサイズ | 最大 1 MB / リクエスト |
| 行サイズ | 最大 64 KB / 行 |
| タイムアウト | 最大 45 秒 / リクエスト |
| マルチステートメント | MySQL では非対応 |
| 接続先 | writer インスタンスのみ |

1 MB 制限があるため、大量データの SELECT やエクスポートには向きません。ここは SSM 踏み台の出番です。

### 料金

有効化は無料。利用料金は 100 万リクエストあたり $0.35 です。

月 1,000 回の SQL 実行で **$0.00035**。意思決定に影響するレベルの金額ではありません。

## Data API vs SSM Session Manager

ここが CTO として最も判断に迷うポイントだと思います。結論から言えば **「どちらか」ではなく「両方」** です。

### ユースケース別の使い分け

| ユースケース | Data API | SSM 踏み台 |
|---|---|---|
| Lambda からの DB 操作 | **最適**（VPC 不要） | 不可 |
| CI/CD からのマイグレーション | **適** | 可能だが複雑 |
| スクリプトによる定期バッチ | **適**（IAM 認証で安全） | セッション管理が必要 |
| アプリケーション統合 | **最適**（HTTP で完結） | 不向き |
| 手動でのデータ調査 | 制限あり | **最適**（GUI 使用可） |
| 大量データの EXPORT | 不向き（1 MB 制限） | **最適** |
| 緊急時の手動 UPDATE | 可能だが操作性低い | **最適** |

### 運用コストの比較

| 観点 | Data API | SSM 踏み台 |
|---|---|---|
| 初期構築 | ほぼゼロ（コンソールで 1 クリック） | EC2 + SSM + セキュリティグループ設定 |
| ランニングコスト | ~$0 / 月 | $3-8 / 月（t4g.nano 常時起動） |
| メンテナンス | 不要（フルマネージド） | OS パッチ、SSM Agent 更新 |
| 監査ログ | CloudTrail で全クエリ自動記録 | CloudTrail + DB 監査ログの二重管理 |
| 同時接続管理 | 不要（DB 接続プール内蔵） | max_connections の管理が必要 |

踏み台サーバーの年間運用コストは金額だけ見れば $36-96 と小さいですが、**OS パッチ適用、SSM Agent の更新、インスタンス停止時の復旧対応といった人的コスト**を含めると無視できません。少人数チームであればなおさらです。

### セキュリティの比較

| 観点 | Data API | SSM 踏み台 |
|---|---|---|
| 攻撃面 | HTTPS（IAM 保護） | SSM 経由のみ（インバウンド不要） |
| 認証情報管理 | Secrets Manager（自動ローテーション可） | DB パスワードを手元に持つ必要あり |
| 権限制御 | IAM ポリシーで API 呼び出しを制御 | SSM 権限 + DB ユーザー権限の二重管理 |

Data API は認証情報を Secrets Manager に完全に委任できるため、**開発者が DB パスワードを知る必要がない**のはセキュリティ上の大きな利点です。

## 有効化の手順

Aurora MySQL v3.07 以上であれば、有効化は非常にシンプルです。

### CLI での有効化

```bash
# Serverless v2 / Provisioned クラスターの場合
aws rds enable-http-endpoint \
  --resource-arn <cluster-arn> \
  --profile <profile>
```

:::message alert
Serverless v2 / Provisioned では `enable-http-endpoint` コマンドを使います。`modify-db-cluster --enable-http-endpoint` は Serverless v1 専用です。ドキュメントが分かりにくいので注意してください。
:::

### 動作確認

```bash
aws rds-data execute-statement \
  --resource-arn "<cluster-arn>" \
  --secret-arn "<secret-arn>" \
  --database "<db-name>" \
  --sql "SELECT 1 AS test" \
  --profile <profile>

# → {"records": [[{"longValue": 1}]], "numberOfRecordsUpdated": 0}
```

### CDK でのドリフト防止

CLI で有効化しただけだと、次回の CDK デプロイで `false` にリセットされるリスクがあります。

```typescript
const cluster = new rds.DatabaseCluster(this, 'Cluster', {
  engine: rds.DatabaseClusterEngine.auroraMysql({
    version: rds.AuroraMysqlEngineVersion.VER_3_08_0,
  }),
  // ... 既存の設定 ...
  enableDataApi: true,  // ← これを追加
});
```

:::message
CLI での有効化と CDK コードの更新はセットで行いましょう。CDK のドリフトでせっかく有効化した設定が巻き戻ると、Data API に依存した MCP サーバーや自動化スクリプトが一斉に壊れます。
:::

## AI コーディングツール連携：Data API が変えるチーム開発

ここからは個人的な意見を多く含みますが、Data API 導入で最もインパクトがあったのが AI ツールとの連携です。

### Claude Code が DB を直接叩けるようになる

従来の SSM 踏み台方式では、AI ツールからデータベースにアクセスするのは事実上不可能でした。SSH ポートフォワーディングを張り、MySQL クライアントで接続するという手順は、人間が手動で行うことを前提とした設計だからです。

Data API を使えば、`aws rds-data execute-statement` というシェルコマンド 1 本で SQL が実行できます。つまり **Claude Code の Bash ツールから直接データベースを参照・操作**できるようになります。

```bash
# Claude Code が実行するコマンドの例
aws rds-data execute-statement \
  --resource-arn "arn:aws:rds:ap-northeast-1:xxx:cluster:dev-cluster" \
  --secret-arn "arn:aws:secretsmanager:ap-northeast-1:xxx:secret:dbsecret" \
  --database "my_database" \
  --sql "SHOW TABLES" \
  --profile dev
```

これにより、以下のようなワークフローが実現します。

**デバッグ**
「ステージングの users テーブルで status が null のレコードを確認して」→ Claude Code が Data API で即座にクエリ実行 → 原因特定 → 修正コードの提案まで一気通貫

**マイグレーション作成**
「dev 環境の現在のスキーマを確認して、この仕様に合うマイグレーション SQL を書いて」→ 現在のテーブル定義を自動取得 → 差分 SQL を生成

**データ確認**
「本番の Office テーブルのレコード数と最終更新日を教えて」→ 即座に回答

従来であればエンジニアが踏み台を経由して手動で確認し、その結果を AI に伝えて...というラウンドトリップが必要でした。Data API はこの **人間がボトルネックになっていた部分を完全に排除** します。

### MCP サーバーで自然言語 DB アクセス

AWS Labs が公式に提供している **MySQL MCP Server** を組み合わせると、さらに強力になります。

```json
{
  "mcpServers": {
    "awslabs.mysql-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.mysql-mcp-server@latest",
        "--resource_arn", "<cluster-arn>",
        "--secret_arn", "<secret-arn>",
        "--database", "<db-name>",
        "--region", "ap-northeast-1",
        "--readonly", "True"
      ],
      "env": {
        "AWS_PROFILE": "dev",
        "AWS_REGION": "ap-northeast-1"
      }
    }
  }
}
```

この MCP サーバーは内部的に Data API を使用しています。設定後は Cursor や Claude Code から自然言語でクエリが実行できます。

- 「今月の問い合わせ件数を教えて」
- 「東京都にあるオフィスの一覧を表示して」
- 「直近 7 日間で更新されたレコードを確認して」

`--readonly True` を設定しておけば、SELECT のみに制限されるため、本番環境でも安心して使えます。

### チームの学習コストが激減する

これは CTO として見逃せないポイントです。

従来の DB アクセスでチームメンバーが習得すべきだったこと：

1. AWS SSO ログインの仕組みと手順
2. SSM Session Manager のインストール・設定
3. ポートフォワーディングの概念と実行方法
4. MySQL クライアントのインストール・接続設定
5. Secrets Manager からのパスワード取得

Data API + AI ツールの場合：

1. AWS CLI のプロファイル設定（多くのエンジニアが既に知っている）
2. 「○○のデータを見せて」と AI に聞く

**5 ステップが実質 1 ステップになります**。新しいメンバーのオンボーディングでも「AWS SSO でログインして、あとは Claude に聞いて」で済むのは大きい。

非インフラエンジニアやフロントエンドエンジニアが「ちょっとデータを確認したい」ときのハードルが劇的に下がります。

### 運用負荷の軽減

踏み台サーバーの運用から解放される可能性があるのは、少人数チームにとって大きなメリットです。

もちろん、完全に踏み台を廃止できるかはチームの要件次第です。大量データのエクスポートや複雑な調査作業では依然として SSM 踏み台が有用です。しかし、**日常的な「ちょっとデータを確認したい」「数レコード更新したい」という用途の大半は Data API で代替可能**です。

踏み台の利用頻度が下がれば、常時起動をやめてオンデマンド起動に切り替える判断もしやすくなります。

## 導入にあたっての判断ポイント

### 前提条件の確認

| 項目 | 必要条件 |
|---|---|
| DB エンジン | Aurora MySQL v3.07+ または Aurora PostgreSQL v13.12+ |
| インスタンスクラス | T インスタンスクラス以外 |
| Secrets Manager | DB 認証情報が格納されていること |

標準 RDS を使っている場合は Data API が使えません。Data API のために Aurora にマイグレーションするかどうかは、他のメリット（Serverless v2 によるオートスケーリング等）も含めて判断してください。

### リスク評価

Data API の有効化自体にリスクはほぼありません。

- 既存のアプリケーションやデータベース接続に影響なし
- 有効化しても、IAM 権限がなければアクセスできない
- 無効化もコマンド 1 つで即時可能
- 料金はほぼゼロ

唯一の注意点は **CDK でのドリフト防止**です。`enableDataApi: true` をコードに追加し忘れると、次回デプロイで設定が巻き戻ります。

## まとめ

Aurora を使っているなら、Data API の有効化は **「やらない理由がない」改善** の一つです。

- 有効化はほぼノーリスク・ノーコスト
- SSM 踏み台との併用で、あらゆるユースケースをカバー
- AI コーディングツールとの連携により、チーム全体の開発速度が向上
- 学習コスト・運用コストの削減に直結

個人的には、Data API は「インフラの改善」というよりも **「チームの働き方を変えるツール」** だと感じています。AI ツールがデータベースに直接アクセスできるかどうかで、デバッグやデータ確認の速度が桁違いに変わります。

まだ有効化していない Aurora クラスターがあれば、まずは dev 環境から試してみてください。コマンド 1 つ、5 秒で完了します。

## 参考資料

- [Amazon Aurora MySQL now supports RDS Data API](https://aws.amazon.com/about-aws/whats-new/2024/09/amazon-aurora-mysql-rds-data-api/)
- [Using the Amazon RDS Data API - Amazon Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.html)
- [Enabling the Amazon RDS Data API](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.enabling.html)
- [Limitations for the Amazon RDS Data API](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.limitations.html)
- [AWS Labs MySQL MCP Server](https://github.com/awslabs/mcp/blob/main/src/mysql-mcp-server/README.md)

## 最後に

株式会社ピュアポムメディアラボ（PML）では、AI を活用した開発支援やプロダクト開発に取り組んでいます。

Claude Code をはじめとする AI ツールを活用した開発に興味のある方、一緒に働きませんか？

- 採用情報・お問い合わせ: https://purpom-media-lab.com/

お気軽にお声がけください。
