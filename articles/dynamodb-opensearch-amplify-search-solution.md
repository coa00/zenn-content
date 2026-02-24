---
title: "DynamoDB の検索が辛すぎて Aurora 移行を決めかけた。でも月額 $27 で全部解決した話"
emoji: "🔍"
type: "tech"
topics: ["AWS", "DynamoDB", "OpenSearch", "Amplify", "アーキテクチャ"]
published: true
---

## はじめに

Aurora への移行を本気で検討していた。見積もりも取った。Amplify の Data モデルを捨てて SQL スキーマを書き直す段取りまで考えた。

きっかけは、不動産検索のフィルタ条件が 5 つを超えたあたりだった。DynamoDB の Query/Scan では対応しきれない。全文検索はそもそもできない。ソート順を変えるたびに GSI を追加する羽目になる。「もう DynamoDB じゃ無理だ」——チーム全員がそう思っていた。

結論から言うと、**Aurora には移行しなかった**。OpenSearch を「検索レイヤー」として追加するだけで、月額 $27 の追加コストで全文検索・複雑なフィルタ・柔軟なソートを手に入れた。Amplify の DynamoDB 中心の開発体験を維持したまま、検索機能だけをスケールアップできる。

この記事では、[Purpom Media Lab](https://purpom-media-lab.com/) で開発している不動産テックプロダクト（propform / soho-tokyo）での実装経験をもとに、DynamoDB の検索の弱点を OpenSearch で補った方法と、Aurora に移行しなかった判断の背景を共有します。

## DynamoDB だけで運用していた頃の課題

propform と soho-tokyo は、Amplify Gen2 で構築した不動産テックプロダクトです。物件データ・区画データを DynamoDB に保存し、ユーザーに一覧表示・検索機能を提供しています。

初期は DynamoDB の Query と GSI（グローバルセカンダリインデックス）で対応していましたが、プロダクトの成長とともに以下の課題が顕在化しました。

### 1. 複雑なフィルタ条件に対応できない

不動産検索では「エリア × 価格帯 × 面積 × 駅徒歩分 × 築年数」のような複数条件の組み合わせが当たり前です。DynamoDB の Query はパーティションキーとソートキーの 2 軸でしかフィルタできません。

FilterExpression を使えば追加条件は指定できますが、**フィルタは Query の結果に対して適用される**ため、1,000 件取得して 10 件に絞る、といった非効率な処理になります。

### 2. 全文検索ができない

「渋谷 オフィス ペット可」のようなキーワード検索は DynamoDB では不可能です。contains 演算子はありますが、Scan が前提で実用的ではありません。

### 3. 柔軟なソート・ページネーションが困難

DynamoDB のソートはソートキーに依存します。「価格順」「面積順」「新着順」を切り替えるには、それぞれ別の GSI が必要。GSI の上限は 20 個ですが、フィルタ条件との組み合わせを考えると全然足りません。

ページネーションも `ExclusiveStartKey` ベースのカーソル方式のみで、「3 ページ目に直接ジャンプ」ができません。

## DynamoDB を活かしたまま、検索の弱点を補う

「検索が辛いなら RDB に移行すればいい」という選択肢は当然検討しました。Aurora Serverless v2 は AWS のマネージド RDB としてはもっとも有力です。しかし、DynamoDB + Amplify の開発体験を捨ててまで移行する必要はないと判断しました。理由は 3 つあります。

### コスト比較

| | DynamoDB + OpenSearch | Aurora Serverless v2 |
|---|---|---|
| **月額コスト（最小構成）** | DynamoDB: 従量課金（少量なら $5 以下）+ OpenSearch t3.small: **約 $27** | 最小 0.5 ACU: **約 $60〜70**（東京リージョン） |
| **合計** | **約 $30〜50/月** | **約 $60〜100/月** |
| **ストレージ** | DynamoDB: $0.25/GB + OpenSearch: $0.122/GB（gp3） | $0.12/GB（Aurora ストレージ） |
| **スケール特性** | DynamoDB: 自動スケール、OpenSearch: インスタンス固定 | ACU ベースの自動スケール |

Aurora Serverless v2 は「最小 0.5 ACU でも常時課金」が発生します。東京リージョンでは ACU あたり約 $0.20/時で、0.5 ACU × 730 時間 = **月額約 $73**。アイドル時でもこのコストがかかります。

一方、DynamoDB は従量課金でアイドル時はほぼゼロ、OpenSearch の t3.small.search は **月額約 $27**。合計で Aurora の半額以下に収まります。

### Amplify との親和性

Amplify Gen2 は DynamoDB をデフォルトのデータストアとして使います。`defineData()` でスキーマを定義すれば、GraphQL API と DynamoDB テーブルが自動生成される。この開発体験は非常に快適です。

Aurora に移行すると、この恩恵を捨てることになります。Amplify の Data モデルから離れ、自前で SQL スキーマ管理・マイグレーション・ORM 設定を行う必要がある。**DynamoDB を「メインのデータストア」として維持したまま、OpenSearch を「検索レイヤー」として追加する方が、アーキテクチャの変更が最小限**で済みます。

### 検索性能

そもそも検索に特化したサービスである OpenSearch は、全文検索・ファセット検索・地理検索・スコアリングなど、Aurora の LIKE 句や全文インデックスでは及ばない検索体験を提供できます。不動産検索のように複雑な条件で絞り込むユースケースでは、OpenSearch の方が圧倒的に有利です。

## アーキテクチャ：DynamoDB Streams + Lambda + OpenSearch

採用したアーキテクチャはシンプルです。

```
[DynamoDB] → DynamoDB Streams → [Lambda] → [OpenSearch]
                                                ↑
                                        検索 API が参照
```

### データの流れ

1. **書き込み**: アプリケーションは従来通り DynamoDB に書き込む（Amplify の Data モデルをそのまま使う）
2. **同期**: DynamoDB Streams がレコードの変更を検知し、Lambda 関数をトリガー
3. **インデックス**: Lambda が OpenSearch にドキュメントを upsert/delete
4. **検索**: 検索 API は OpenSearch に対してクエリを実行し、結果を返す

このアーキテクチャのメリットは、**既存の書き込みパスを一切変更しない**こと。DynamoDB への CRUD は Amplify の GraphQL API をそのまま使い、検索だけ OpenSearch を参照する構成です。

### Lambda の同期処理（イメージ）

```typescript
// DynamoDB Streams → Lambda → OpenSearch
export const handler = async (event: DynamoDBStreamEvent) => {
  for (const record of event.Records) {
    const tableName = extractTableName(record.eventSourceARN);
    const indexName = tableToIndex(tableName); // テーブル名 → index 名のマッピング

    switch (record.eventName) {
      case 'INSERT':
      case 'MODIFY':
        await opensearchClient.index({
          index: indexName,
          id: record.dynamodb.Keys.id.S,
          body: unmarshall(record.dynamodb.NewImage),
        });
        break;
      case 'REMOVE':
        await opensearchClient.delete({
          index: indexName,
          id: record.dynamodb.Keys.id.S,
        });
        break;
    }
  }
};
```

DynamoDB の各テーブルに対応する OpenSearch index を用意し、Streams の INSERT/MODIFY/REMOVE イベントに応じてドキュメントを同期します。

### 検索クエリの Before / After

DynamoDB だけだった頃と、OpenSearch 導入後のクエリの違いを見ると、検索体験の変化がわかります。

**Before: DynamoDB（複数条件の絞り込み）**

```typescript
// DynamoDB: パーティションキー + FilterExpression で無理やり対応
const result = await dynamoClient.query({
  TableName: 'Properties',
  KeyConditionExpression: '#area = :area',
  FilterExpression: '#price BETWEEN :minPrice AND :maxPrice AND #size >= :minSize',
  ExpressionAttributeValues: { ':area': '渋谷区', ':minPrice': 5000000, ':maxPrice': 10000000, ':minSize': 50 },
  // → 1,000 件取得して FilterExpression で 10 件に絞る非効率な処理
});
```

**After: OpenSearch（同じ条件 + 全文検索 + ソート）**

```typescript
// OpenSearch: 任意の条件を組み合わせ + 全文検索 + ソートが 1 クエリで完結
const result = await opensearchClient.search({
  index: 'propform-prod-properties',
  body: {
    query: {
      bool: {
        must: [
          { match: { description: 'ペット可 オフィス' } },  // 全文検索
          { term: { area: '渋谷区' } },
          { range: { price: { gte: 5000000, lte: 10000000 } } },
          { range: { size: { gte: 50 } } },
        ],
      },
    },
    sort: [{ price: 'asc' }],  // 任意フィールドでソート
    from: 0, size: 20,         // ページネーション
  },
});
// → 条件に合う 20 件だけを直接取得。100〜200ms で返る
```

DynamoDB では実現できなかった「全文検索 + 複数条件フィルタ + ソート + ページネーション」が、1 つのクエリで完結します。

## ハマったポイント：日本語検索が動かない

OpenSearch を導入して最初にぶつかったのが、**日本語の全文検索が正しく動かない**問題でした。

「渋谷 オフィス」で検索しても結果が 0 件。原因は、OpenSearch のデフォルトの analyzer（standard analyzer）が日本語の形態素解析に対応していないことでした。「渋谷オフィス」が 1 つのトークンとして扱われ、部分一致しない。

解決策は、index 作成時に **ICU analyzer + kuromoji tokenizer** を設定すること。

```json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "japanese_analyzer": {
          "type": "custom",
          "tokenizer": "kuromoji_tokenizer",
          "filter": ["kuromoji_baseform", "lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "description": { "type": "text", "analyzer": "japanese_analyzer" }
    }
  }
}
```

この設定を入れた瞬間、「渋谷 オフィス ペット可」のような日本語キーワード検索が正常に動き始めました。**OpenSearch の日本語検索は、デフォルトでは動かない**。これを知らずに「OpenSearch も検索できないじゃないか」と焦った時間が一番の無駄でした。

## 運用で意識すべきこと

DynamoDB Streams + Lambda の同期には、いくつか運用上の注意点があります。

- **同期遅延**: Streams → Lambda → OpenSearch の伝播には通常 数百ms〜数秒かかる。リアルタイム性が必要な画面では「書き込み直後にDynamoDB を直接参照する」フォールバックを用意
- **Lambda エラー時のリトライ**: Streams トリガーの Lambda がエラーになるとリトライされるが、繰り返し失敗するとレコードが期限切れで消える。DLQ（Dead Letter Queue）を設定して取りこぼしを防止
- **インデックス再構築**: OpenSearch のマッピングを変更した場合、既存データの再インデックスが必要。DynamoDB の全件 Scan → OpenSearch に Bulk Insert するスクリプトを用意しておくと安心

## 1 インスタンス × index 分離：Amplify sandbox 問題の解決

### 問題：sandbox ごとに OpenSearch が作られる

Amplify Gen2 の開発フローでは、各開発者が `npx ampx sandbox` で個人の開発環境を立ち上げます。ここで OpenSearch のリソース定義がバックエンドに含まれていると、**開発者の数だけ OpenSearch インスタンスが作られてしまう**。

t3.small.search が 1 台 $27/月とはいえ、5 人のチームなら $135/月。sandbox を立ち上げっぱなしにすればさらに膨らみます。OpenSearch のインスタンスは起動にも時間がかかるため、sandbox の起動時間も長くなる。

### 解決策：1 インスタンスを共有し、index で分離

この問題を、**環境ごとに OpenSearch インスタンスを作るのではなく、1 つのインスタンスを全環境で共有し、index 名で分離する**方式で解決しました。

```
OpenSearch ドメイン（1 インスタンス）
├── propform-stg-properties     ← propform staging の物件
├── propform-stg-sections       ← propform staging の区画
├── propform-prod-properties    ← propform prod の物件
├── propform-prod-sections      ← propform prod の区画
├── sohotokyo-stg-properties    ← soho-tokyo staging の物件
├── sohotokyo-prod-properties   ← soho-tokyo prod の物件
└── sandbox-{user}-properties   ← sandbox は必要な場合のみ
```

**ポイント:**

- **sandbox では OpenSearch リソースを作成しない** — CDK / Amplify のバックエンド定義で、sandbox 環境の場合は OpenSearch 関連のリソース作成をスキップ
- **sandbox の Lambda は開発用の共有 OpenSearch を参照** — 環境変数で OpenSearch のエンドポイントとindex 名を注入し、sandbox では stg 環境の OpenSearch を参照するか、DynamoDB を直接参照するフォールバックを用意
- **index 名にプロジェクト名と環境名を含める** — `{project}-{env}-{entity}` の命名規則で衝突を防止

この方式により、**OpenSearch のインスタンス数を最小限（stg/prod で各 1 台、または共有で 1 台）に抑えつつ**、複数プロジェクト・複数環境を安全に運用できています。

## DynamoDB + OpenSearch で得られたもの

Before / After を整理すると、以下の通りです。

| | Before（DynamoDB のみ） | After（DynamoDB + OpenSearch） |
|---|---|---|
| **フィルタ** | GSI + FilterExpression（2〜3 条件が限界） | 任意の条件を組み合わせ可能 |
| **全文検索** | 不可 | 日本語形態素解析に対応 |
| **ソート** | ソートキー依存（GSI が必要） | 任意のフィールドでソート |
| **ページネーション** | カーソル方式のみ | from/size で任意ページにジャンプ |
| **レスポンス** | Scan 時は数秒かかることも | 複雑なクエリでも 100〜200ms |
| **月額コスト** | DynamoDB のみ: $5 以下 | + OpenSearch: 約 $27 |

月額 $27 の追加コストで、検索体験が根本的に変わりました。

## 導入ステップ：5 ステップで始められる

OpenSearch の追加は、以下の手順で進められます。

1. **OpenSearch ドメインを作成** — t3.small.search の 1 インスタンス構成で十分。月額約 $27
2. **日本語 analyzer 付きの index を作成** — kuromoji tokenizer を設定。これを忘れると日本語検索が動かない
3. **DynamoDB Streams を有効化** — 対象テーブルの Streams を `NEW_AND_OLD_IMAGES` で有効化
4. **同期 Lambda をデプロイ** — Streams トリガーで OpenSearch に upsert/delete する Lambda を作成。DLQ も忘れずに設定
5. **検索 API を追加** — OpenSearch にクエリを投げる API を追加。既存の DynamoDB CRUD API はそのまま維持

GSI が 5 個を超えた、FilterExpression で絞り込み後のヒット率が 10% を切った——そのあたりが OpenSearch 導入を検討するタイミングです。

## まとめ

Aurora への移行を本気で考えていた。見積もりも取った。でも結局、**DynamoDB を捨てる必要はなかった**。

OpenSearch を検索レイヤーとして追加するだけで、DynamoDB の弱点は補える。書き込みは DynamoDB、検索は OpenSearch。DynamoDB Streams + Lambda で同期し、データの整合性を保つ。Amplify Gen2 の DynamoDB 中心の開発体験はそのまま維持しながら、検索機能だけを段階的にスケールアップできる構成です。

この「弱点を補う」アプローチの良さは、**一気にアーキテクチャを作り変えなくていい**ことです。最初は DynamoDB だけで運用し、検索要件が増えてきたら OpenSearch を追加する。プロダクトの成長に合わせて、必要な時に必要な分だけ検索機能を強化できる。

「DynamoDB じゃ検索できない → RDB に移行しよう」と考える前に、OpenSearch で弱点を補う選択肢を試してみてください。DynamoDB を活かしたまま、検索を継続的にスケールさせることができます。

## 参考

- [Amazon OpenSearch Service 料金](https://aws.amazon.com/opensearch-service/pricing/)
- [Amazon Aurora 料金](https://aws.amazon.com/rds/aurora/pricing/)
- [DynamoDB Streams を使用した変更データキャプチャ](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)
- [AWS Amplify Gen2 ドキュメント](https://docs.amplify.aws/)
