---
title: "忘れるとクリティカルな AWS SES の申請を、誰でもできるように Claude Code Skill で自動化した話"
emoji: "📧"
type: "tech"
topics: ["AWS", "SES", "ClaudeCode", "自動化", "インフラ"]
published: true
---

## はじめに

新環境にデプロイした翌日、「ユーザー登録のメールが届かない」と報告が来ました。原因は SES がサンドボックスのまま。検証済みアドレスにしかメールが送れない状態だったのです。

AWS SES（Simple Email Service）のサンドボックス解除は、やること自体は単純です。しかし「環境ごと・アカウントごと・リージョンごと」に個別申請が必要で、申請文の書き方が悪いと容赦なく却下されます。新環境を立てるたびにこの作業が発生し、毎回「前どうやったっけ？」と調べ直すことになります。

この記事では、SES のサンドボックス解除を **Claude Code の Skill + シェルスクリプト** で自動化し、最終的にプラグインとして公開するまでの過程をご紹介します。DENIED を4回食らった試行錯誤も含めてお伝えします。

## SES サンドボックス解除の何が面倒か

SES の本番アクセス申請で面倒なポイントは3つあります。

**1. 環境の数だけ申請が必要**

SES のサンドボックスは **AWS アカウント × リージョン** 単位で管理されます。staging と production が別アカウントなら、それぞれ個別に申請が必要です。

私たちの場合、あるプロダクトに4つの環境があります。

| 環境 | 当初の状態 |
|---|---|
| staging | GRANTED |
| production | GRANTED |
| 顧客A向け-stg | **DENIED** |
| 顧客A向け-prod | **未申請（ID 0件）** |

上2つは過去に申請済みでしたが、下2つは顧客向けの新環境で未対応でした。

**2. 却下理由が分かりにくい**

AWS は却下しても「DENIED」としか返してくれません。サポートケースの詳細を見ようにも、Premium Support が必要で参照できないこともあります。何が悪かったのか推測するしかないのが現状です。

**3. 前提条件を見落とすと即却下**

申請文をいくら丁寧に書いても、DKIM が未設定だったり、ドメインが SES に登録されていなかったりすると即却下されます。顧客A向け-prod はまさにこれで、メール ID が **0件** の状態で申請して即 DENIED でした。

## 4回の DENIED から学んだこと

### 1回目: 申請文が曖昧すぎた（顧客A向け-stg）

最初の申請では、日本語でざっくりとした説明を書きました。

```
バウンス対応
・メールが配信されない場合は、その都度弊社カスタマーサポートに
  お問い合わせをいただき、迷惑メールフォルダに振り分けられていないかや
  登録したメールアドレスが間違っていないかを確認してもらう
```

これでは AWS の審査チームに「技術的なバウンス対策をしていない」と判断されてしまいます。実際に DENIED されました。

### 2回目: ドメイン未登録で即却下（顧客A向け-prod）

`put-account-details` API で申請を送信し、一見成功したように見えました。しかしアカウントのステータスを確認すると即座に DENIED になっていました。

原因を調べると、このアカウントには **SES のメール ID が1つも登録されていなかった** のです。

```bash
$ aws sesv2 list-email-identities --profile customer-a-prod
{
    "EmailIdentities": []
}
```

ドメイン認証（DKIM）すらしていない状態で申請しても、門前払いされるのは当然でした。

### 3回目: ConflictException で申請できない

DENIED された後に改善した内容で再申請しようとしたら、別のエラーが出ました。

```
ConflictException: None
```

一度 DENIED されると `put-account-details` API では再申請できません。**Service Quotas API** 経由で Sending Quota の引き上げをリクエストする必要があります。

```bash
aws service-quotas request-service-quota-increase \
  --service-code ses \
  --quota-code L-804C8AE8 \
  --desired-value 50000
```

### 4回目: 既に申請済みで重複エラー

Service Quotas 経由で再申請したら、今度は `ResourceAlreadyExistsException`。前回の申請がまだ PENDING 状態で残っていました。

ここまでの失敗をすべてスクリプトに落とし込むことにしました。

## なぜスクリプト化するのか — トークン節約

Claude Code に SES の操作を毎回ゼロから指示すると、環境調査・ステータス確認・エラーハンドリングのたびに大量のトークンを消費します。実際、今回の調査〜申請の一連の流れでは、4環境の `sesv2 get-account` や `get-email-identity` を何度も呼び出し、JSON の解析も Claude に任せていました。

シェルスクリプトにまとめておけば、`ses-status.sh` の1回の呼び出しで全環境の結果が返ります。Claude が個別に API を叩いて結果を解釈する必要がなくなるため、**同じ作業でもトークン消費が大幅に減ります**。スクリプト化は再利用性だけでなく、AI エージェント時代のコスト最適化でもあるのです。

## スクリプトの設計

3つのスクリプトを作りました。

| スクリプト | 役割 |
|---|---|
| `ses-status.sh` | 全環境のSESステータスを一覧表示 |
| `ses-request.sh` | サンドボックス解除を申請（Pre-flight チェック付き） |
| `ses-verify-identity.sh` | メールアドレス / ドメインの認証 |

### Pre-flight チェックが肝

`ses-request.sh` の核心は、申請前の Pre-flight チェックです。過去の失敗パターンをすべて事前に検証します。

```bash
=== Pre-flight checks for customer-a-prod ===
  [1/3] Domain identity (example-app.com): NOT FOUND

  >>> Domain example-app.com is not registered in SES.
  >>> Register it first:
  >>>   aws sesv2 create-email-identity --profile customer-a-prod ...
  >>> Then add the 3 DKIM CNAME records to your DNS.

=== Pre-flight FAILED. Fix the issues above and retry. ===
```

チェック項目は3つです。

1. **送信元ドメインが SES に登録済み + DKIM が SUCCESS** であること
2. **Suppression List（BOUNCE + COMPLAINT）** が有効であること
3. **メール ID が1つ以上** 登録されていること

不備があればスクリプトが止まり、具体的な修正コマンドを表示します。これで「申請したけど即 DENIED」がなくなります。

### DENIED 後の自動リトライ

申請ロジックは現在のステータスに応じて分岐します。

| 現在のステータス | 動作 |
|---|---|
| 本番アクセス済み | スキップ |
| PENDING（審査中） | スキップ |
| DENIED | Service Quotas API で再申請 |
| 未申請 | `put-account-details` で申請 |

さらに Service Quotas で `ResourceAlreadyExistsException` が出た場合は、既存リクエストのステータスを表示します。

```bash
  Service Quotas request already exists (pending). Checking status...
  +---------------+--------------------------------------------+
  |  Created      |  2026-03-05T18:17:21.662000+09:00          |
  |  DesiredValue |  50000.0                                   |
  |  Id           |  27667e78531142e0bb33fe30f5b25c64eF1DFYuf  |
  |  Status       |  CASE_OPENED                               |
  +---------------+--------------------------------------------+
```

### 申請文テンプレート（英語）

リサーチの結果、AWS の審査で重視されるポイントは以下だと分かりました。

1. 具体的なサービス内容とメールの種類
2. メールアドレスの取得方法と受信者の同意プロセス
3. バウンス・苦情の**技術的な**対応策（SNS + Suppression List）
4. DKIM / SPF / DMARC の設定状況
5. 配信停止（オプトアウト）の仕組み
6. 別アカウントで承認済みなら Case ID を明記

これらを9セクションの英語テンプレートにしました。日本語で書くより英語の方が審査が速いという知見もあります。

## Claude Code Skill 化

スクリプトだけでも便利ですが、Claude Code の Skill にすると「SES の申請をして」と自然言語で指示するだけで実行できるようになります。

### SKILL.md

```markdown
---
name: ses-manage
description: AWS SES sandbox removal, status checks, and email identity
  verification. Use when asked about "SES request", "SES status",
  "sandbox removal", or "email sending authorization".
---

# AWS SES Management Skill

Manage AWS SES production access using the scripts in this plugin.

## Available Scripts

| Script | Purpose |
|---|---|
| `ses-status.sh` | Check SES account status |
| `ses-request.sh` | Request sandbox removal with pre-flight checks |
| `ses-verify-identity.sh` | Verify email addresses or domains |
```

Skill の `description` に「SES request」「sandbox removal」「email sending authorization」などのキーワードを入れておくと、Claude がコンテキストから自動的にこのスキルを選択してくれます。

### 実際の使用フロー

```
ユーザー: SES のステータスを確認して
Claude:   → ses-status.sh を全環境で実行 → テーブル表示

ユーザー: 顧客A向け-prod のサンドボックスを解除して
Claude:   → ses-request.sh を実行
          → Pre-flight FAILED（ドメイン未登録）
          → ドメイン登録 + DKIM CNAME を DNS に追加
          → 再度 ses-request.sh → 申請完了
```

人間が覚えておく必要があるのは「SES の申請をして」という指示だけです。Pre-flight チェック、API の使い分け、エラーハンドリングはすべてスクリプトが担います。

## プラグイン化して公開

Skill をチーム内だけでなく外部にも共有するため、Claude Code Plugin として構成しました。

```
claude-ses-plugin/
├── .claude-plugin/
│   └── plugin.json         # プラグインマニフェスト
├── skills/
│   └── ses-manage/
│       └── SKILL.md        # スキル定義
├── scripts/
│   ├── ses-status.sh
│   ├── ses-request.sh
│   └── ses-verify-identity.sh
└── README.md
```

インストールは1行で済みます。

```bash
/plugin marketplace add purpom-media-lab/claude-ses-plugin
/plugin install ses-manage@purpom-media-lab
```

ローカルでのテストも簡単です。

```bash
claude --plugin-dir ./claude-ses-plugin
```

## Before / After

| 項目 | Before | After |
|---|---|---|
| ステータス確認 | 環境ごとに AWS CLI を手打ち | `ses-status.sh` で全環境を一覧表示 |
| 申請作業 | コンソールで手動入力、何を書くか毎回調べる | `ses-request.sh PROFILE URL DOMAIN` の1コマンド |
| DENIED 対応 | 原因不明、再申請方法も不明 | Pre-flight で事前検出 + 自動リトライ |
| ドメイン認証 | 手順を調べて手動で CNAME 追加 | `ses-verify-identity.sh` で確認・登録 |
| 新メンバーへの引き継ぎ | 手順書を書いて共有 | 「SES の申請をして」で完了 |

## まとめ — 「確実にやるべきこと」ほど Skill にする

SES のサンドボックス解除は、やり方を知っていれば10分で終わります。しかし「やり方を知っている人」がチームにいないと、半日ハマります。そして一度設定すると数ヶ月〜数年触らないので、次にやるときにはまた忘れています。

開発には2種類のタスクがあります。毎日やるタスクと、たまにしかやらないタスクです。毎日やるタスクは体が覚えます。問題は後者——**確実に実施すべきだが、頻度が低いから忘れてしまう**タスクです。SES の申請、DNS の設定、SSL 証明書の更新、IAM ポリシーの付与。どれもサボると本番障害に直結しますが、手順を覚えている人はチームに1人いるかいないかではないでしょうか。

こういうタスクこそ、Skill 化して時短すべきです。

スクリプトに失敗パターンを全部埋め込んでおけば、誰が実行しても同じ結果になります。Claude Code の Skill にしておけば、AWS CLI の使い方を知らないメンバーでも「SES の申請をして」の一言で完了します。手順書を書いて共有するより、動くスクリプトを渡す方がはるかに確実です。

皆さんのチームにも「あの人しかできない運用タスク」はありませんか？ まずはシェルスクリプトにして、次に Skill にしてみてください。次にそのタスクが必要になったとき、半日ではなく30秒で終わるはずです。

## 参考

- [Request production access - Amazon SES](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html)
- [FAQs: Amazon SES production access requests - AWS re:Post](https://repost.aws/knowledge-center/ses-production-access-request-faq)
- [Create plugins - Claude Code Docs](https://code.claude.com/docs/en/plugins)
- [claude-ses-plugin - GitHub](https://github.com/purpom-media-lab/claude-ses-plugin)
