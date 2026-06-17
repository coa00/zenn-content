---
title: "ポート開放なしで外出先から自宅 Mac に SSH 接続し、Claude Code を動かす"
emoji: "🔑"
type: "tech"
topics: ["tailscale", "ssh", "mac", "claudecode", "tmux"]
published: true
---

## はじめに

自宅の Mac に外出先から入って、Claude Code を動かしたい。そう思って調べ始めたのですが、「DDNS」「ポート転送」「二重ルーター」「DMZ」と知らない言葉が次々に出てきて、なかなか前に進めませんでした。

最終的にたどり着いたのは、ルーターの設定を一切触らずに済む方法でした。結論を先にお伝えすると、**自宅 Mac への外部からの SSH は、ポートを 1 つも開けずに実現できます。** カギになったのは Tailscale です。

私の自宅は **NURO 光の配布ルーターとメッシュ Wi-Fi を重ねた二重ルーター構成**で、よくあるポート転送のやり方は早々に行き詰まりました。そこから Tailscale と SSH 鍵認証に切り替えたところ、`ssh home-mac → tmux → claude` という運用が問題なく成立しました。

この記事では、接続経路の検討から Tailscale の導入、SSH 鍵認証、そして地味にハマった 2 つの落とし穴（`Too many authentication failures` と「端末がない」問題）まで、私が実際にやった順番でお伝えしていきます。

## なぜ画面共有ではなく SSH なのか

はじめは「Apple Remote Desktop や VNC で画面ごと遠隔操作すればいいかな」と考えていました。ただ、**Claude Code はコマンドラインで動くツール**です。ターミナルに入れれば十分で、重くて遅くなりがちな GUI 転送は必要ありませんでした。

そして SSH には、画面共有にはない強みがあります。**`tmux` と組み合わせると、セッションを永続化できる**のです。回線が切れても Mac の中で Claude Code は動き続け、再接続すれば作業の続きから戻れます。外出先のモバイル回線は不安定なので、これは私にとって必須の要件でした。

## 立ちはだかった「二重ルーター」

自宅のネットワーク環境は、次のようになっていました。

| 項目 | 内容 |
|------|------|
| 回線 | NURO 光 |
| 1 段目 | Huawei HG8045Q（NURO 配布の ONU 一体型ルーター） |
| 2 段目 | TP-Link Deco X50（メッシュ Wi-Fi） |
| 構成 | **二重ルーター（多段 NAT）** |
| グローバル IPv4 | あり（DDNS で解決可能） |

`nslookup` してみると、グローバル IPv4 はちゃんと引けました。CGNAT 帯（`100.64〜100.127`）でもプライベート帯でもない、正規のグローバル IP です。「それならポート転送でいけそう」と思ったのですが、ここに落とし穴がありました。

**その入口は 1 段目の HG8045Q の WAN であって、Mac がぶら下がっている Deco ではありません。** そのため、外から自宅 Mac に届かせるには、HG8045Q と Deco の**両方でポート転送（二段転送）**が必要になります。

### 検討した経路と評価

検討したのは、次の 3 つの経路です。

| 経路 | 内容 | 評価 |
|------|------|------|
| A: Deco の VPN サーバー + DDNS | ルーターの VPN 機能で入口を作る | ❌ Deco X50 に VPN サーバー項目が無く、そもそも入口は HG8045Q 側 |
| B: ポート転送で SSH を直接公開 | `ssh -p <port> coa@DDNS名` | ❌ 二段転送が必要 + NURO 配布機は管理権限が制限されポート転送/DMZ を設定できない可能性大 + SSH 直公開は総当たりの的 |
| C: **Tailscale** | 両端に入れてメッシュ VPN を張る | ✅ **採用** |

経路 B は、仮に設定できたとしても SSH をインターネットに直接さらすことになります。鍵認証を必須にしたり、ポートを変更したり、fail2ban を入れたりと、運用の手間がかさみます。そして何より、NURO 配布の HG8045Q は管理権限が絞られていて、そもそもポート転送の設定自体ができない見込みでした。

:::message
NordVPN や Surfshark のような「VPN クライアント機能」は、自宅の通信を業者経由で匿名化する**逆方向**の機能で、「外から自宅に入る」用途には使えません。名前が似ていて混同しやすいので注意してください。
:::

## 採用した構成：Tailscale でルーターの制約を回避する

Tailscale は WireGuard ベースのメッシュ VPN です。各端末に `100.x.x.x` の固定 IP が割り当てられ、**内側から接続を張る**仕組みのため、NAT もファイアウォールも越えられます。

```
外出先端末（Tailscale）
      │  Tailscale ネットワーク（暗号化・NAT 越え）
      ▼
自宅Mac（m2-macbook-air-black.tail46a9b1.ts.net / リモートログインON）
      └─ tmux 上で claude を実行
```

この構成なら、HG8045Q も Deco X50 も**一切設定変更する必要がありません**。二重ルーターも権限の制限も、まるごと関係なくなります。個人利用は無料で、外部に公開する入口を持たないため攻撃面もほぼありません。私にとっては、これが最適解でした。

### セットアップ：自宅 Mac 側（接続される側）

1. Tailscale をインストール → ログイン（`100.x.x.x` の IP と、MagicDNS 名 `m2-macbook-air-black.tail46a9b1.ts.net` が割り当てられる）
2. **システム設定 → 一般 → 共有 → リモートログイン（SSH）を ON**
3. `tmux` を用意（なければ `brew install tmux`）

### セットアップ：接続元の端末

私は最初、接続元の端末に Tailscale を入れ忘れていて接続できませんでした。**両端に入れて初めてメッシュが張られる**ので、忘れないようにしてください。

```bash
brew install --cask tailscale
# 起動して自宅 Mac と同一アカウントでログイン
```

cask 版はコマンドのパスが通らないことがあるので、エイリアスを張っておくと楽です。

```bash
alias tailscale="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
tailscale status   # 自宅Mac(m2-macbook-air-black.tail46a9b1.ts.net) が一覧に出れば疎通OK
```

これで `ssh coa@m2-macbook-air-black.tail46a9b1.ts.net` でログインできる状態になりました。ただ、毎回この長いホスト名を打つのは手間ですし、後述の terminfo 問題もあるので、`~/.ssh/config` に別名を切っておきます。

```ssh-config
Host home-mac
    HostName m2-macbook-air-black.tail46a9b1.ts.net
    User coa
    SetEnv TERM=xterm-256color
```

これ以降は `ssh home-mac` だけで入れるようになります。

:::message
**`missing or unsuitable terminal: xterm-ghostty` が出たら**
ローカルが Ghostty だと `TERM=xterm-ghostty` が SSH 越しに伝わります。しかし自宅 Mac 側に対応する terminfo が無いため、`tmux` などがこれを拒否してしまいます。上記の `SetEnv TERM=xterm-256color` を入れておくと回避できます。terminfo ごとコピーする恒久的な解決なら、`infocmp -x | ssh home-mac -- tic -x -` を一度実行しておきます。
:::

## ここからが本題：パスワードをやめて SSH 鍵に切り替える

ここまでで「パスワードを使った SSH」は通るようになりました。ただ、毎回パスワードを入力するのは面倒ですし、最終的にはパスワード認証そのものを切りたいところです。そこで**公開鍵認証**に切り替えます。

既存の鍵（`~/.ssh/id_rsa`）を使う場合、やることは 1 つだけです。**ローカルの公開鍵を、リモートの `~/.ssh/authorized_keys` に設置する**——これには `ssh-copy-id` を使います。

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub home-mac
```

ところが、ここで 2 つの落とし穴を続けて踏んでしまいました。

### 落とし穴① `Too many authentication failures`

実行すると、こう怒られました。

```text
Received disconnect from m2-macbook-air-black.tail46a9b1.ts.net port 22:2: Too many authentication failures
```

これは**鍵認証に失敗した回数が原因**です。ssh-agent に複数の鍵が載っていると、SSH はそれらを片っ端からサーバーに提示します。その結果、パスワード認証にたどり着く前に、サーバー側の試行回数の上限（`MaxAuthTries`、既定は 6）に達してしまうのです。

対処としては、**鍵のオファーを止めて、パスワードだけで接続させます**。

```bash
ssh-copy-id -o PubkeyAuthentication=no -o PreferredAuthentications=password \
  -i ~/.ssh/id_rsa.pub home-mac
```

### 落とし穴②「端末がない」とパスワードが入力できない

こちらが本当の原因でした。何度 `ssh-copy-id` を実行しても、パスワードが弾かれ続けます。`-v` を付けて様子を見ると、こんな行が出ていました。

```text
Pseudo-terminal will not be allocated because stdin is not a terminal.
Permission denied, please try again.
```

`ssh-copy-id`（内部で動く `ssh`）は、パスワードを**対話的な端末（TTY）から読み取ります**。私は TTY を持たない自動化ツール越しに実行していたため、**そもそもパスワードを入力する先がありませんでした**。入力したつもりの文字はどこにも届かず、空のまま弾かれ続けていたわけです。

ここでの教訓はシンプルです。

> **`ssh-copy-id` は普通のターミナル（Terminal.app / iTerm / Ghostty など）で実行する。** 端末を持たないラッパー越しには実行しない。

通常のターミナルで実行し直したところ、一発でパスワードが通り、`Number of key(s) added: 1` と表示されました。

### 鍵だけで入れることを検証する

「鍵で入れた**つもり**」になっているのが、いちばん危ない状態です。実はパスワードにフォールバックしているだけ、ということもあり得るからです。そこで `BatchMode=yes`（パスワード入力を完全に禁止するオプション）で確かめます。

```bash
ssh -o BatchMode=yes home-mac 'echo KEY_AUTH_OK; hostname; whoami'
```

返ってきた出力が、こちらです。

```text
KEY_AUTH_OK
m2-macbook-air-black.local
coa
```

パスワードが使えない状態でホスト名とユーザーが返ってきました。これで、**純粋に鍵だけで認証が通っている**ことが確認できます。Before / After で並べると、次のとおりです。

- **Before**: `Permission denied (publickey,password,keyboard-interactive)`（鍵は提示されるがサーバーが拒否＝authorized_keys に無い）
- **After**: `KEY_AUTH_OK`（鍵のみで認証成立）

### 仕上げ：パスワード認証を無効化（ハードニング）

鍵認証が安定したら、リモート側でパスワードログインを切ると、さらに安全になります。`/etc/ssh/sshd_config.d/` に設定を足して、`sshd` を再起動します。

```bash
# リモート（自宅Mac）側で
echo "PasswordAuthentication no" | sudo tee /etc/ssh/sshd_config.d/100-no-password.conf
sudo launchctl kickstart -k system/com.openssh.sshd
```

:::message alert
パスワードの無効化は、**鍵で確実に入れることを確認してから**行ってください。先に切ってしまうと締め出されます。心配であれば、別のターミナルで鍵接続を 1 本張ったまま作業すると安心です。
:::

## 運用：tmux で Claude Code を永続化する

ここが最終的なゴールです。`tmux` の中で `claude` を起動しておけば、SSH が切れても Mac の中で動き続けてくれます。

```bash
ssh home-mac
tmux attach -t cc || tmux new -s cc   # 既存セッションに入る／無ければ作る
cd ~/path/to/project
claude
```

セッションから抜けるときは `Ctrl+b` → `d`（detach）です。これで Claude Code は動いたまま、SSH だけが切れます。再接続するときは `ssh home-mac` のあと `tmux attach -t cc` で、元の画面に戻れます。

| 操作（プレフィックス `Ctrl+b`） | 動作 |
|------|------|
| `d` | detach（抜ける） |
| `c` | 新規ウィンドウ |
| `n` / `p` | 次 / 前のウィンドウ |
| `%` / `"` | 左右 / 上下分割 |

### おまけ：ローカルで入力が二重になったら

接続元のシェルで、`a` が `aa`、`ls` が `llss` のように二重表示されることがあります。これは SSH の接続が一時的に乱れたときに起きる端末エコーの問題で、リモート側は健全です。`stty sane`（または `reset`）で直ります。改善しないときは、ターミナルを開き直してください。

## 画面共有（VNC）でも接続する

CLI だけでなく、GUI ごと操作したい場面もあります。Tailscale で経路が通っているので、SSH と同じように **macOS の画面共有（VNC）もルーター設定なしで**つながります。SSH（リモートログイン）と画面共有は別々の設定なので、自宅 Mac 側で画面共有を有効にするだけです。

接続元が Mac であれば、Finder で `⌘K`（移動 → サーバへ接続）から `vnc://coa@m2-macbook-air-black.tail46a9b1.ts.net` を開き、`coa` のログインパスワードを入力します。

### ハマりどころ：「リモートマネージメント」だとアカウントのパスワードで入れない

私の環境では、ID とパスワードを入れても画面共有に入れませんでした。SSH で自宅 Mac の状態を調べたところ、有効になっていたのは「画面共有」ではなく **「リモートマネージメント（ARD）」**でした。

```bash
# 自宅Mac側の状態を SSH 経由で確認
launchctl print system/com.apple.screensharing | grep "state ="   # → not running
pgrep -lf ARDAgent                                                  # → ARDAgent が稼働中
```

リモートマネージメントが有効なときの VNC ログインは、アカウントのパスワードではなく **ARD のアクセス権限**で制御されます。そのため、その権限が割り当てられていないと、正しいパスワードを入れても弾かれてしまいます。

対処は、リモートマネージメントを止めて、素直に「画面共有」を有効化することです。自宅 Mac に SSH で入り、次を実行します（`sudo` のパスワードが必要なので、TTY のある通常のターミナルから実行します）。

```bash
# リモートマネージメント(ARD)を停止
sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart -deactivate -stop
# 画面共有を有効化
sudo launchctl enable system/com.apple.screensharing
sudo launchctl bootstrap system /System/Library/LaunchDaemons/com.apple.screensharing.plist
```

画面共有は**オンデマンド起動**のため、有効化した直後は `screensharingd` が動いておらず、ポート 5900 も待機していないように見えることがあります。実際に接続を試みると起動するので、慌てずに `vnc://coa@m2-macbook-air-black.tail46a9b1.ts.net` へつないでみてください。認証がアカウント方式に変わっているので、今度は `coa` とログインパスワードで入れます。

:::message
システム設定からも切り替えられます（システム設定 → 一般 → 共有）。「リモートマネージメント」と「画面共有」は同時に有効化できないため、画面共有だけをオンにします。外出先で GUI を触れないときは、上記のように SSH 経由で切り替えます。
:::

### CLI と GUI の使い分け

これで、外部から自宅 Mac へ 2 通りの方法でアクセスできるようになりました。

| 用途 | 方法 | 接続 |
|------|------|------|
| CLI 作業（Claude Code など） | SSH ＋ tmux | `ssh home-mac` |
| GUI 操作・画面確認 | 画面共有（VNC） | `vnc://coa@m2-macbook-air-black.tail46a9b1.ts.net` |

モバイル回線だと VNC は描画が重くなりがちです。コーディングは SSH + tmux のほうが軽快で、回線が切れても作業が続きます。画面の確認や GUI 操作が必要なときだけ VNC を使う、という併用がおすすめです。

## まとめ

二重ルーター（NURO 配布機 + メッシュ Wi-Fi）で、かつ配布機の管理権限が制限されている、という条件のもとでは、DDNS + ポート転送のルートはかなり分が悪く、現実的には行き詰まってしまいます。今回やってみて感じたのは、次の 3 点です。

- **入口を作る発想（ポート転送）をやめ、内側から張る発想（Tailscale）に切り替える**のがよかったということ。ルーターを 1 つも触らずに済みます。
- **SSH 鍵認証でいちばんハマったのは、暗号でも設定でもなく「端末（TTY）」だった**ということ。`ssh-copy-id` は普通のターミナルで実行するのが確実です。
- 「鍵で入れたつもり」は、`BatchMode=yes` で必ず**検証**しておくと安心です。

外出先のカフェからでも、`ssh home-mac` の一発で自宅の Claude Code に戻れるようになると、開発の身軽さが一段変わります。同じように二重ルーターで困っている方の参考になれば嬉しいです。

## 参考

- [Tailscale 公式ドキュメント](https://tailscale.com/kb/)
- [OpenSSH ssh-copy-id(1)](https://man.openbsd.org/ssh-copy-id)
- [tmux wiki](https://github.com/tmux/tmux/wiki)
