---
title: "1Password CLI で Claude Code のトークンを複数 Mac に安全に配る"
emoji: "🔐"
type: "tech"
topics: ["ClaudeCode", "1Password", "MCP", "セキュリティ", "bash"]
published: true
---

## はじめに

気づいたら Mac が3台になっていました。

デスクのメイン機、持ち出し用の MacBook、検証用の1台。Claude Code はどの Mac でも同じように動いてほしいんですが、地味に困るのが **トークンの扱い** です。Notion や Linear、GitHub の MCP サーバーを動かすには API トークンが要る。それを `.mcp.json` に直接書くと平文が設定ファイルに残るし、かといって3台に手でコピペして回るのもしんどい。

「このトークン、結局どこに置くのが正解なんだ・・」としばらく悩んで、最終的に普段使っている 1Password に落ち着きました。先に結論だけ書くと、**トークンの保管先を 1Password ひとつに集約して、各 Mac へは 1Password CLI（`op`）で同期する**。これで「平文が散らばる」「台数分コピペする」が両方消えました。

以下、何に困って、なぜ 1Password CLI にして、実際に動かしているスクリプト2本がどうなっているか、私がやった順に書いていきます。

## 何に困っていたか

Claude Code を本格的に使い出すと、MCP サーバーの設定（`.mcp.json`）にトークンが要ります。最初、私はここに値を直接書いていました。

```jsonc
{
  "mcpServers": {
    "github": {
      "headers": { "Authorization": "Bearer ghp_xxxxxxxxxxxx" }  // ← 平文
    }
  }
}
```

これがいくつも問題を抱えていて、

- **平文トークンが設定ファイルに混ざる**。private リポジトリとはいえ、`git` の履歴に残るのは普通に気持ち悪い。
- **複数台で同じ値を共有しないといけない**。台数が増えるほどコピペの手間と貼り間違いが増える。
- **ローテーションのたびに全台を直す**。トークンを更新したら3台ぜんぶ書き換え。考えただけで気が重い。

そして一番悩んだのが「**そもそもトークンをどこに保管するか**」です。`.env` を各機に配るのか、dotfiles に暗号化して入れるのか、クラウドの secrets サービスを使うのか。どれも「新しい仕組みを増やす」感じがして、なかなか踏み切れませんでした。

## なぜ 1Password CLI にしたか

で、あるとき気づいたんですが、**答えはもう手元にありました**。パスワードもクレカも何年も 1Password に入れている。トークンだって同じ「秘密」なら、わざわざ別の置き場所を用意する理由がない。

しかも 1Password には CLI（`op`）があって、`op item get` でアイテムを読み出せます。MCP も出ているのでエコシステム的にも将来性がある。並べてみると、私のユースケースには 1Password が一番素直に収まりました。

| 保管方法 | 共有 | セキュリティ | 評価 |
|----------|------|------------|------|
| `.env` を各機に手で配る | 手作業 | ファイルが平文で残る | ❌ 台数分の手間と貼り間違い |
| dotfiles に暗号化して入れる | git 経由 | 復号鍵の管理が別途必要 | ❌ 仕組みが増える |
| クラウドの secrets サービス | API 経由 | 良好 | △ 新規導入・ログイン管理が増える |
| **1Password CLI** | `op` で同期 | Touch ID + Vault | ✅ **採用**：普段使いの延長で済む |

決め手は3つ。**普段から使っていて新しく覚えることが少ない**、**Touch ID で承認できる**、**秘密の置き場所を1箇所に集約できる**。要は「持ってる道具で済ませる」のが一番ラクでした。

## 全体設計：秘密のソースは 1Password だけ

仕組みの核は、**秘密の流れを一方向にする**ことです。実値は 1Password にしか置かず、そこから各 Mac の環境変数へ、設定ファイルの参照へと、下流にだけ流す。

```
1Password（唯一のソース）
   │  op item get（sync スクリプト）
   ▼
~/.config/claude/secrets.env  ← 自動生成・git 管理外・chmod 600
   │  source（シェル起動時に読み込み）
   ▼
環境変数  $GITHUB_MCP_PAT など
   │  ${VAR} 参照
   ▼
.mcp.json / settings.json  ← git 追跡。実値は持たず参照のみ
```

ポイントは、**git で追跡するファイルには実トークンを一切書かない**こと。`.mcp.json` には `${GITHUB_MCP_PAT}` みたいな環境変数参照だけ置いて、実体は 1Password から流し込みます。これなら設定ファイルをコミットしても秘密は漏れない。

支えているのは、保存側と読み出し側のスクリプト2本だけです。

## 前提：1Password CLI のセットアップ

スクリプトを動かす前に、これだけ済ませておきます。

- **1Password CLI（`op`）をインストール**（macOS なら `brew install 1password-cli`）
- **デスクトップアプリと CLI を連携**：1Password アプリ → 設定 → 開発者 → 「Integrate with 1Password CLI」を ON。これで `op` 実行時に Touch ID で承認できます。
- **保管用のアイテムを用意**：Vault `Personal` に `Claude Code MCP` という名前のアイテム（カテゴリ: パスワード）を作って、トークンごとにフィールドを足す。

スクリプト側では、環境変数名と 1Password のフィールド名をこう対応づけています（両スクリプト共通）。

```bash
# ENV_VAR=1Passwordフィールド名
declare -a MAP=(
  "NOTION_API_KEY=notion_api_key"
  "LINEAR_API_KEY=linear_api_key"
  "GITHUB_MCP_PAT=github_pat"
  "SLACK_MCP_XOXB_TOKEN=slack_xoxb"
  "GOOGLE_TOKEN_JSON=google_token_json"
  "STRIPE_SECRET_KEY=stripe_secret_key"
)
```

Vault と Item は環境変数で上書きできます（`OP_VAULT` / `OP_ITEM`）。デフォルトは `Personal` / `Claude Code MCP`。

## 保存側：env のトークンを 1Password に入れる

まず、いま手元のシェルにあるトークンを 1Password に保存するスクリプト `save-to-1password.sh`。値は `~/.zshrc` の `export` から拾って、**コマンドラインに直接べた書きしない**のがコツです（履歴に残さないため）。

肝は 1Password に渡すフィールドの組み立て方。`${フィールド名}[password]=値` の形で並べて、アイテムが既にあれば `op item edit`、なければ `op item create` で作ります。

```bash
# 6フィールドの器を作る。env に値があれば入れ、無ければ空フィールド。
fields=()
for pair in "${MAP[@]}"; do
  var="${pair%%=*}"; field="${pair#*=}"
  val="${!var-}"
  if [ -z "$val" ]; then
    fields+=( "${field}[password]=" )         # 空の器だけ作る
  else
    fields+=( "${field}[password]=${val}" )    # 値を入れる
  fi
done

# 既存なら更新、なければ作成
if op item get "$ITEM" --vault "$VAULT" >/dev/null 2>&1; then
  op item edit "$ITEM" --vault "$VAULT" "${fields[@]}" >/dev/null
else
  op item create --category=password --title="$ITEM" --vault "$VAULT" "${fields[@]}" >/dev/null
fi
```

地味に効いているのが、**値が無いフィールドは空の器だけ作る**ところ。最初から6種類すべてのトークンが揃ってなくていい。空フィールドだけ先に作っておけば、あとで 1Password の GUI にローテ後の値を貼るだけで埋まります。一気に完璧を目指さず、ちょっとずつ移行できる形にしました。

実行は対話ターミナルから（Touch ID 承認が要るので）。Claude Code 内からなら `!` を付けてそのまま叩けます。

```bash
! bash ~/claudecode/scripts/save-to-1password.sh
```

## 読み出し側：1Password から env を再生成する

次が本命、各 Mac で実行する `sync-claude-secrets.sh`。1Password からトークンを読み出して、git 管理外の env ファイルに書き出します。**各 Mac でこれを叩けば、どの機でも同じ値が揃う**。今回やりたかったのはまさにこれです。

ここで一回ハマりました。最初はフィールドごとに `op read` を叩いていたんですが、途中で 1Password が再ロックして何度も Touch ID を求められたり、一部だけ取得に失敗したり・・。なので、アイテム全体を `--format json` で一度に取って、あとは `jq` で各フィールドを抜く方式にしました。`op` の呼び出しは1回だけ。

```bash
# アイテムを1回だけ取得（途中再ロックの影響を受けにくい）
json="$(op item get "$ITEM" --vault "$VAULT" --format json)"

umask 177  # 生成ファイルは 600
got=0; miss=()
for pair in "${MAP[@]}"; do
  var="${pair%%=*}"; field="${pair#*=}"
  # label が field に一致するフィールドの value を取得
  val="$(printf '%s' "$json" | jq -r --arg f "$field" \
        '.fields[] | select(.label==$f) | .value // empty')"
  if [ -z "$val" ]; then
    miss+=("$field"); continue
  fi
  printf 'export %s=%q\n' "$var" "$val" >> "$tmp"
  got=$((got+1))
done
```

書き出し先は `~/.config/claude/secrets.env`。`umask 177` と `chmod 600` で**所有者しか読めない**ようにして、値は `printf '%q'` でシェル安全にエスケープしています。

それと、**1件も取れなければ失敗、一部欠けても成功**というフェイルソフトにしました。

```bash
if [ "$got" -eq 0 ]; then
  echo "✗ 1件も取得できませんでした。フィールド名を確認してください。" >&2
  exit 1
fi
# 一部欠けていても、取れた分だけ書き出して成功扱い
```

まだ Stripe のトークンは入れてない、みたいな状態でも sync は通ります。揃った分だけ env に入って、足りないのは警告で教えてくれる。「全部揃ってないと動かない」をやめたら、運用がだいぶ楽になりました。

env ができたら、新しいシェルを開くか `source ~/.config/claude/secrets.env` で反映。

## 設定ファイル側は「参照」だけ

env に値が入れば、あとは `.mcp.json` 側が `${VAR}` で受け取るだけです。

```jsonc
{
  "mcpServers": {
    "github": {
      "headers": { "Authorization": "Bearer ${GITHUB_MCP_PAT}" }
    }
  }
}
```

実値はどこにも書いてないので、このファイルはそのままコミットできます。あわせて `.gitignore` で、うっかり秘密が混ざりやすいファイルはまとめて除外。

```gitignore
# 秘密情報（private repo・自分専用のため .mcp.json は追跡する）
CLAUDE.local.md
**/.env
**/.env.*
*.pem
*.key
```

## 実運用：新規 Mac とローテーション

仕組みができてみると、日々のオペレーションは拍子抜けするくらい単純になりました。

**新しい Mac をセットアップするとき**は、`op` の連携を ON にして sync を1回叩くだけ。

```bash
bash ~/claudecode/scripts/sync-claude-secrets.sh
# → ~/.config/claude/secrets.env が生成される。新しいシェルを開けば完了。
```

**トークンをローテーションしたとき**は、1Password のアイテムを1箇所だけ更新して、各 Mac で sync を再実行。設定ファイルには一切触りません。

```bash
# 1. 1Password GUI で該当フィールドの値を更新
# 2. 各 Mac で sync を再実行するだけ
bash ~/claudecode/scripts/sync-claude-secrets.sh
```

「全台を手で直す」が「1Password を1回直して各機で sync」になっただけ。ただ、これだけで心理的な負担はぜんぜん違いました。

## ハマったところ

きれいに動くまでに、小さい落とし穴がいくつかありました。

- **1Password CLI のアンエスケープ**：シェルの裸の変数を全角文字の直前に置くと、変数名の境界がうまく切れず `unbound variable` で落ちることがありました。`${ITEM}` のように波括弧で囲って回避。
- **一部フィールド未入力の扱い**：最初は全フィールド揃わないと失敗する作りで、移行の初期につまずきました。前述の「取れた分だけ成功」に変えて解決。
- **Touch ID が出ない**：非対話シェルから `op` を叩くと承認ダイアログが出ず認証に失敗します。保存・同期はかならず対話ターミナルから。

:::message alert
平文トークンを設定ファイルに書いていた期間がある場合、**git の履歴には過去の値が残ったまま**です。env 参照に置き換えても履歴は消えないので、移行後は念のため**該当トークンをローテーション**しておくのが安全です（サービス側と 1Password の両方を更新）。
:::

## まとめ

トークンの保管先を 1Password ひとつに集約したら、ずっと悩みの種だった「平文が散らばる」「台数分コピペ」「ローテのたびに全台直す」が、まとめて消えました。やってることは `op item get` と `jq`、`export` を書き出すだけの素朴な bash です。派手さはゼロ。ただ **秘密のソースを1箇所に絞る**という原則が、効いてる実感があります。

MCP が増えるほど扱うトークンの種類も増えます。もう信頼して使ってるパスワードマネージャを「鍵の単一ソース」に使い回すのは、新しい仕組みを増やさずに済む、わりと現実的な手だと思います。

ところで、みなさんは Claude Code のトークンをどこに置いてますか？ もっといいやり方があれば、ぜひ教えてください。まだ設定ファイルに直書きしてるなら、まず1種類だけ 1Password に逃がしてみるところからどうぞ。

## 参考

- [1Password CLI ドキュメント](https://developer.1password.com/docs/cli/)
- [op item get リファレンス](https://developer.1password.com/docs/cli/reference/management-commands/item/)
- [Claude Code MCP ドキュメント](https://docs.anthropic.com/en/docs/claude-code/mcp)
