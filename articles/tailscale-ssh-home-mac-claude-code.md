---
title: "ポート開放ゼロで外から自宅Macに入る — Tailscale × SSH鍵でClaude Codeを動かす全手順"
emoji: "🔑"
type: "tech"
topics: ["tailscale", "ssh", "mac", "claudecode", "tmux"]
published: true
---

## はじめに

結論から書く。**自宅 Mac への外部 SSH は、ルーターのポートを 1 つも開けずに実現できる。** カギは Tailscale だ。

外出先から自宅の Mac に入って Claude Code を動かしたい。回線が切れても作業を消したくない。やりたいことはこれだけなのに、調べ始めると「DDNS」「ポート転送」「二重ルーター」「DMZ」と地雷が増えていく。

私の自宅は **NURO 光の配布ルーター + メッシュ Wi-Fi の二重ルーター構成**で、ポート転送ルートは早々に詰んだ。最終的に Tailscale + SSH 鍵認証に落ち着き、**ルーター設定を一切触らずに** `ssh home-mac → tmux → claude` の運用が成立した。

この記事では、経路の検討から Tailscale 導入、SSH 鍵認証、そして地味にハマった 2 つの落とし穴（`Too many authentication failures` と「端末がない」問題）まで、実際にやった順番で全部書く。

## なぜ画面共有ではなく SSH なのか

最初は「Apple Remote Desktop や VNC で画面ごと遠隔操作」を考えていた。が、**Claude Code は CLI で動く**。ターミナルに入れれば十分で、GUI 転送（重い・遅い）は要らない。

そして SSH には画面共有にない強みがある。**`tmux` と組み合わせればセッションを永続化できる**。回線が切れても Mac の中で Claude Code は動き続け、再接続すれば作業の続きから戻れる。外出先のモバイル回線は不安定なので、これは必須要件だった。

## 立ちはだかった「二重ルーター」

自宅のネットワーク環境はこうなっていた。

| 項目 | 内容 |
|------|------|
| 回線 | NURO 光 |
| 1 段目 | Huawei HG8045Q（NURO 配布の ONU 一体型ルーター） |
| 2 段目 | TP-Link Deco X50（メッシュ Wi-Fi） |
| 構成 | **二重ルーター（多段 NAT）** |
| グローバル IPv4 | あり（DDNS で解決可能） |

`nslookup` するとちゃんとグローバル IPv4 が引けた。CGNAT 帯（`100.64〜100.127`）でもプライベート帯でもない、正規のグローバル IP だ。「じゃあポート転送でいけるのでは？」と思うが、ここに罠がある。

**その入口は 1 段目の HG8045Q の WAN であって、Mac がぶら下がる Deco ではない。** つまり外から自宅 Mac に届かせるには、HG8045Q と Deco の**両方でポート転送（二段転送）**が要る。

### 検討した経路と評価

3 つの経路を比較した。

| 経路 | 内容 | 評価 |
|------|------|------|
| A: Deco の VPN サーバー + DDNS | ルーターの VPN 機能で入口を作る | ❌ Deco X50 に VPN サーバー項目が無く、そもそも入口は HG8045Q 側 |
| B: ポート転送で SSH を直接公開 | `ssh -p <port> coa@DDNS名` | ❌ 二段転送が必要 + NURO 配布機は管理権限が制限されポート転送/DMZ を設定できない可能性大 + SSH 直公開は総当たりの的 |
| C: **Tailscale** | 両端に入れてメッシュ VPN を張る | ✅ **採用** |

経路 B は仮に設定できても、SSH をインターネットに直接晒すことになる。鍵認証必須・ポート変更・fail2ban…と運用負荷が高い。そして何より、NURO 配布の HG8045Q は管理権限が絞られていてポート転送自体ができない見込みだった。

:::message
NordVPN / Surfshark のような「VPN クライアント機能」は、自宅の通信を業者経由で匿名化する**逆方向**の機能で、「外から自宅に入る」用途には使えない。混同しやすいので注意。
:::

## 採用構成：Tailscale で全部無視する

Tailscale は WireGuard ベースのメッシュ VPN だ。各端末に `100.x.x.x` の固定 IP が付き、**内側から接続を張る**ので NAT もファイアウォールも越える。

```
外出先端末（Tailscale）
      │  Tailscale ネットワーク（暗号化・NAT 越え）
      ▼
自宅Mac（100.77.252.97 / リモートログインON）
      └─ tmux 上で claude を実行
```

HG8045Q も Deco X50 も**一切設定変更しない**。二重ルーターも権限制限も、まるごと関係なくなる。個人利用は無料。攻撃面はほぼゼロ。これが最適解だった。

### セットアップ：自宅 Mac 側（接続される側）

1. Tailscale をインストール → ログイン（IP `100.77.252.97` が発行される）
2. **システム設定 → 一般 → 共有 → リモートログイン（SSH）を ON**
3. `tmux` を用意（なければ `brew install tmux`）

### セットアップ：接続元の端末

最初、接続元に Tailscale を入れ忘れていて接続できなかった。**両端に入れて初めてメッシュが張られる**のを忘れずに。

```bash
brew install --cask tailscale
# 起動して自宅 Mac と同一アカウントでログイン
```

cask 版はコマンドのパスが通らないことがあるので、エイリアスを張っておくと楽。

```bash
alias tailscale="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
tailscale status   # 自宅Mac(100.77.252.97) が一覧に出れば疎通OK
```

これで `ssh coa@100.77.252.97` でログインできる状態になった。ただし IP 直打ちは味気ないし、後述の terminfo 問題もあるので `~/.ssh/config` に別名を切る。

```ssh-config
Host home-mac
    HostName 100.77.252.97
    User coa
    SetEnv TERM=xterm-256color
```

以後 `ssh home-mac` だけで入れる。

:::message
**`missing or unsuitable terminal: xterm-ghostty` が出たら**
ローカルが Ghostty だと `TERM=xterm-ghostty` が SSH 越しに伝わるが、自宅 Mac 側に terminfo が無く `tmux` 等が拒否する。上記の `SetEnv TERM=xterm-256color` で回避できる。terminfo ごとコピーする恒久解なら `infocmp -x | ssh home-mac -- tic -x -` を一度実行する。
:::

## ここからが本題：パスワードをやめて SSH 鍵にする

ここまでで「パスワード SSH」は通る。だが毎回パスワードは面倒だし、最終的にパスワード認証は切りたい。そこで**公開鍵認証**にする。

既存の鍵（`~/.ssh/id_rsa`）を使う場合、やることは 1 つ。**ローカルの公開鍵を、リモートの `~/.ssh/authorized_keys` に設置する**だけだ。これには `ssh-copy-id` を使う。

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub home-mac
```

…が、ここで 2 連続で地雷を踏んだ。

### 落とし穴① `Too many authentication failures`

実行するとこう怒られた。

```text
Received disconnect from 100.77.252.97 port 22:2: Too many authentication failures
```

これは**鍵認証が失敗した数のせい**だ。ssh-agent に複数の鍵が載っていると、SSH はそれを片っ端からサーバーに提示する。サーバー側の試行回数上限（`MaxAuthTries`、既定 6）に、パスワード認証へ到達する前に達してしまう。

対処は、**鍵のオファーを止めてパスワードだけで接続させる**こと。

```bash
ssh-copy-id -o PubkeyAuthentication=no -o PreferredAuthentications=password \
  -i ~/.ssh/id_rsa.pub home-mac
```

### 落とし穴②「端末がない」とパスワードが入力できない

これが本当の犯人だった。何度 `ssh-copy-id` を実行してもパスワードが弾かれ続ける。`-v` で見ると、こんな行が出ていた。

```text
Pseudo-terminal will not be allocated because stdin is not a terminal.
Permission denied, please try again.
```

`ssh-copy-id`（内部の `ssh`）は、パスワードを**対話的な端末（TTY）から読む**。私は自動化ツール（TTY を持たない実行環境）越しに走らせていたため、**そもそもパスワードを入力する先が無かった**のだ。入力したつもりの文字はどこにも届かず、空のまま弾かれ続けていた。

教訓はシンプルだ。

> **`ssh-copy-id` は普通のターミナル（Terminal.app / iTerm / Ghostty 等）で実行する。** 端末を持たないラッパー越しに走らせない。

通常のターミナルで実行し直したら、一発でパスワードが通って `Number of key(s) added: 1` が出た。

### 鍵だけで入れることを検証する

「鍵で入れた**つもり**」が一番危ない。パスワードにフォールバックしているだけかもしれないからだ。そこで `BatchMode=yes`（パスワード入力を完全に禁止）で確かめる。

```bash
ssh -o BatchMode=yes home-mac 'echo KEY_AUTH_OK; hostname; whoami'
```

返ってきた出力がこれ。

```text
KEY_AUTH_OK
Koheinonotobukkukonpyuta.local
coa
```

パスワード不可の状態でホスト名とユーザーが返った＝**純粋に鍵だけで認証が通っている**ことが確定した。Before / After で言えば、

- **Before**: `Permission denied (publickey,password,keyboard-interactive)`（鍵は提示されるがサーバーが拒否＝authorized_keys に無い）
- **After**: `KEY_AUTH_OK`（鍵のみで認証成立）

### 仕上げ：パスワード認証を無効化（ハードニング）

鍵認証が安定したら、リモート側でパスワードログインを切るとさらに堅い。`/etc/ssh/sshd_config.d/` に設定を足して `sshd` を再起動する。

```bash
# リモート（自宅Mac）側で
echo "PasswordAuthentication no" | sudo tee /etc/ssh/sshd_config.d/100-no-password.conf
sudo launchctl kickstart -k system/com.openssh.sshd
```

:::message alert
パスワード無効化は**鍵で確実に入れることを確認してから**行うこと。先に切ると締め出される。心配なら別ターミナルで鍵接続を 1 本張ったまま作業する。
:::

## 運用：tmux で Claude Code を永続化する

ゴールはここ。`tmux` の中で `claude` を起動しておけば、SSH が切れても Mac の中で動き続ける。

```bash
ssh home-mac
tmux attach -t cc || tmux new -s cc   # 既存セッションに入る／無ければ作る
cd ~/path/to/project
claude
```

セッションから抜けるのは `Ctrl+b` → `d`（detach）。これで Claude Code は動いたまま、SSH だけ切れる。再接続は `ssh home-mac` → `tmux attach -t cc` で元の画面に戻る。

| 操作（プレフィックス `Ctrl+b`） | 動作 |
|------|------|
| `d` | detach（抜ける） |
| `c` | 新規ウィンドウ |
| `n` / `p` | 次 / 前のウィンドウ |
| `%` / `"` | 左右 / 上下分割 |

### おまけ：ローカルで入力が二重になったら

接続元のシェルで `a` が `aa`、`ls` が `llss` のように二重表示されることがある。SSH が中途半端に乱れたときの端末エコーの問題で、リモート側は健全だ。`stty sane`（または `reset`）で直る。改善しなければターミナルを開き直す。

## まとめ

二重ルーター（NURO 配布機 + メッシュ Wi-Fi）かつ配布機の管理権限が制限される、という条件下では、DDNS + ポート転送ルートは不利を通り越して**詰む**。結局のところ、

- **入口を作る発想（ポート転送）を捨て、内側から張る発想（Tailscale）に切り替える**のが正解だった。ルーターを 1 つも触らずに済む。
- **SSH 鍵認証の最大のハマりどころは暗号でも設定でもなく「端末（TTY）」**。`ssh-copy-id` は普通のターミナルで叩く。
- 「鍵で入れたつもり」は `BatchMode=yes` で必ず**検証**する。

外出先のカフェから `ssh home-mac` 一発で自宅の Claude Code に戻れるようになると、開発のモビリティが一段変わる。同じ「二重ルーターで詰んでいる」人の役に立てば嬉しい。

## 参考

- [Tailscale 公式ドキュメント](https://tailscale.com/kb/)
- [OpenSSH ssh-copy-id(1)](https://man.openbsd.org/ssh-copy-id)
- [tmux wiki](https://github.com/tmux/tmux/wiki)
