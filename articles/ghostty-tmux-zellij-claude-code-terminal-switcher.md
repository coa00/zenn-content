---
title: "Mac 環境の Claude Code の実行環境について"
emoji: "👻"
type: "tech"
topics: ["claudecode", "ghostty", "tmux", "zellij", "fzf"]
published: true
---

## はじめに

筆者は Claude Codeを中心に開発しており、IDE は起動しなくなってきました。確認のために VSCode を起動するぐらいです。

また[エージェントチーム機能](https://code.claude.com/docs/ja/agent-teams)を日常的に利用しています。エージェントチームは複数の Claude Code インスタンスがチームとして連携して動作する仕組みで、1つのセッションがリーダーとして作業を調整し、各チームメンバーが独立したコンテキストウィンドウで並列に作業を進めます。調査・レビュー・新機能開発・デバッグなど、並列探索が有効な場面で特に効果を発揮します。

エージェントチームには「in-process モード」と「分割ペインモード」の2つの表示モードがあります。in-process モードは任意のターミナルで動作しますが、各チームメンバーの状況を一覧で確認するには**分割ペインモード**が有用です。分割ペインモードの利用には tmux または iTerm2 が必要になります。

この分割ペインモードを快適に使えるターミナル環境を探す中で、4つの環境を検証しました。Ghostty は速いが tmux を重ねると制約がある。iTerm2 は安定しているが描画が重い。zellij はモダンだが tmux の方が対応範囲が広い。**それぞれ一長一短があり1つに絞ることが難しい**状況でした。

そこで、場面に応じて使い分ける方針にしました。Ghostty で新しいウィンドウを開くたびに fzf で環境を選択できるスクリプトを作成しています。

## 4つのターミナル環境を試してみた

Claude Code を本格的に使う場合、ターミナルに対する要件が増えます。

- Claude が出力した **URL やファイルパスをクリック**してすぐ開きたい
- **[エージェントチーム](https://code.claude.com/docs/ja/agent-teams)** で複数エージェントを並列で動かしたい
- 作業を中断して翌日再開したい → **セッション永続化**が必要
- **日本語プロンプト**をストレスなく入力したい

1つの環境ですべてを満たすことは難しいため、以下の4パターンを検証しました。

## メリット・デメリット比較

◎ = 標準対応　○ = 設定/プラグインで対応　△ = 制限あり　× = 非対応

| 機能 | Ghostty 単体 | iTerm2 | Ghostty + tmux | Ghostty + zellij |
|------|:---:|:---:|:---:|:---:|
| 描画速度 | ◎ | △ 重い | ◎ | ◎ |
| URL / ファイルを開く | ◎ Cmd+Click | ◎ | ◎ Cmd+Shift+Click | ◎ Cmd+Shift+Click |
| 日本語入力 | ◎ | ◎ | ○ Ghostty設定 | ◎ |
| Shift+Enter 改行 | ◎ | ◎ | ○ Ghostty設定 | ◎ |
| セッション永続化 | × | × | ○ プラグイン | ◎ 組み込み |
| ステータスライン表示 | × | × | ○ tmux設定 | × |
| エージェントチーム分割ペイン | × | ○ it2 CLI+Python API | ◎ | × |
| 操作の分かりやすさ | ◎ | ◎ | △ キーバインド多い | ◎ UI ガイド付き |

### Ghostty 単体 — 最も軽量

[Ghostty](https://ghostty.org/)（v1.3.1）は GPU アクセラレーション対応（macOS は Metal、Linux は OpenGL）のクロスプラットフォームターミナルエミュレータです。プラットフォームネイティブの UI を採用しており、macOS ではクイックターミナル（メニューバーからアニメーション表示）や Quick Look などの専用機能も備えています。起動は体感 0.1 秒以下で、ウィンドウを開いた直後から操作可能です。

Claude Code との組み合わせで特に有用なのは **URL のクリック対応**です。`link-url` 機能により、Cmd を押しながらホバーするとURLがハイライトされ、クリックでブラウザが開きます。PR の URL、ドキュメントリンク、デプロイ先の URL など、Claude Code は URL を頻繁に出力するため、この機能の有無は作業効率に影響します。

日本語入力も安定しており、Claude への日本語プロンプト入力で問題は確認されていません。

**弱点**: セッション管理機能がないので、ターミナルを閉じたら作業状態は消えます。エージェントチームは in-process モード（全チームメンバーが1つのターミナル内で動作）なら使えますが、各チームメンバーを独立ペインで表示する分割ペインモードには対応していません。

### iTerm2 — 機能が豊富で対応範囲が広く、設定も不要

macOS ターミナルの定番 [iTerm2](https://iterm2.com/) です。ネイティブ対応で安定性が高く、エージェントチームの分割ペインモードにも対応しています（[`it2` CLI](https://github.com/mkusaka/it2) のインストールと Python API の有効化が必要）。URL クリック、日本語入力にも対応しています。

**弱点**: Ghostty と比較すると描画が重い傾向があります。Claude Code の長い出力が流れる場面で、Ghostty では発生しない描画の遅延が iTerm2 では確認されました。

### Ghostty + tmux — 設定・プラグインで拡張

[エージェントチーム](https://code.claude.com/docs/ja/agent-teams)は、複数の Claude インスタンスを並列で動かす仕組みです。どのターミナルでも in-process モードで使えますが、各チームメンバーを独立したペインで表示する **分割ペインモード** を使うには [tmux](https://github.com/tmux/tmux/wiki/Installing) または iTerm2 が必要です。

tmux のもう1つの利点はセッションの永続化です。[tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect) と [tmux-continuum](https://github.com/tmux-plugins/tmux-continuum) プラグインを組み合わせることで、ウィンドウ構成・ペイン配置・作業ディレクトリの保存・復元が可能です。

また、tmux の**ステータスバーに [Claude Code のステータスライン変数](https://code.claude.com/docs/ja/status-line)を表示**できる点も実用的です。Claude Code はステータス情報をファイルに書き出す機能があり、tmux の `status-left` / `status-right` から `cat` で読み込むことで、ステータスバーへの常時表示が可能です。

```bash
# tmux.conf — Claude Code ステータスライン連携
# 左側: プロジェクト名
set -g status-left "#[fg=#89b4fa,bold] #(cat ~/.claude/tmux-status-left.txt 2>/dev/null || echo '#S') "
# 右側: モデル名・コンテキスト使用率・レート制限・コスト
set -g status-right "#[fg=#a6e3a1]#(cat ~/.claude/tmux-status-right.txt 2>/dev/null)#[default]"
```

これにより、複数の Claude Code インスタンスを並列で動かしている場合でも、プロジェクト名・モデル名・コンテキスト使用率をステータスバーで確認できます。

```bash
# tmux.conf — セッション永続化設定
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'

# ペイン内容も保存
set -g @resurrect-capture-pane-contents 'on'

# 15分ごとに自動保存、起動時に自動復元
set -g @continuum-restore 'on'
set -g @continuum-save-interval '15'
```

**注意点**: tmux 越しだと Ghostty のネイティブ機能が一部制限されますが、以下の方法で対応可能です。

**URL クリック**: tmux の `mouse on` がマウスイベントを横取りするため Cmd+Click は効きませんが、**Cmd+Shift+Click** で Ghostty に直接渡せます。設定不要で Ghostty のデフォルト動作です。

**Shift+Enter 改行**: tmux 越しだと Claude Code で Shift+Enter による改行が効かないため、Ghostty 側で以下の設定が必要です。

```
# ~/.config/ghostty/config
keybind = shift+enter=text:\x1b[13;2u
```

### Ghostty + zellij — 組み込み機能が充実

[zellij](https://zellij.dev/)（v0.43.1）は Rust 製のターミナルワークスペースで、「シンプルさとパワーの両立」を掲げています。UI にガイドが表示されるため、tmux のようにキーバインドを暗記する必要がありません。フローティングペインやスタックペインなど、モダンな UI 機能も備えています。WebAssembly プラグインシステムにより、任意の言語で拡張機能を作成できます。

セッションの永続化も組み込みで対応しています。

```kdl
// zellij config.kdl
session_serialization true
serialize_pane_viewport true
```

操作性は全体的に tmux より直感的で、マルチプレクサの経験が少ない場合にも導入しやすい環境です。

**弱点**: エージェントチームの分割ペインモードには非対応です。

なお、URL クリックについては tmux と同様に **Cmd+Shift+Click** で Ghostty にマウスイベントを直接渡せます。設定不要です。

## 結局どれを使えばいいのか

| 用途 | おすすめ |
|------|---------|
| 普段の Claude Code 利用 | **Ghostty 単体**（URL クリック・日本語入力が快適） |
| エージェントチーム分割ペインで並列作業 | **Ghostty + tmux**（Shift+Enter は設定で解決） |
| セッション保存 + 直感的な操作 | **Ghostty + zellij** |
| 安定重視・そこまで並列作業をしない | **iTerm2** |

用途によって最適解が変わるため、都度選択できる仕組みを用意しました。

## fzf セッションセレクタで「毎回選べる」ようにする

この考えに基づいて作成したのが `zellij-sessionizer` スクリプトです。

Ghostty で新しいウィンドウを開くと、fzf の選択画面が起動します。既存のセッション一覧と、新規作成オプションが表示されます。

```
┌──────────────────────────────────────┐
│ session >                            │
│ Select a session or create new       │
│──────────────────────────────────────│
│ [zellij] my-project                  │
│ [tmux] claude-team                   │
│ [tmux] dev-server                    │
│ [new] Ghostty (plain shell)          │
│ [new] tmux                           │
│ [new] zellij                         │
└──────────────────────────────────────┘
```

エージェントチームを使う場合は tmux セッションを、普段使いなら Ghostty（plain shell）を選択します。前日のセッションが残っていれば一覧に表示されるため、選択するだけで作業を再開できます。

### 仕組み

1. Ghostty の `command` 設定でスクリプトを起動
2. スクリプトが zellij と tmux の既存セッションを列挙
3. fzf で選択 → 選んだセッションにアタッチ or 新規作成
4. Esc/Ctrl+C で fzf をキャンセルすると素のシェルが起動

### Ghostty の設定

設定は1行です。

```
# ~/.config/ghostty/config
command = /Users/you/.local/bin/zellij-sessionizer
```

### セッションセレクタスクリプト

スクリプトは GitHub で公開しています。

https://github.com/coa00/ghostty-session-picker

```bash
# インストール
curl -fsSL https://raw.githubusercontent.com/coa00/ghostty-session-picker/main/ghostty-session-picker \
  -o ~/.local/bin/ghostty-session-picker
chmod +x ~/.local/bin/ghostty-session-picker
```

主な機能:

- zellij / tmux の既存セッション一覧と新規作成を fzf で選択
- tmux / zellij がインストールされていなければ自動的に非表示
- 新規セッション作成時に直前の作業ディレクトリを自動復元（`~/.last_working_dir` から読み込み。tmux 内では直前ペインのパスを優先）

作業ディレクトリの自動復元を有効にするには、`~/.zshrc` に以下を追加します:

```bash
# ディレクトリ変更時に記録
chpwd() {
  echo "$PWD" > ~/.last_working_dir
}
```

### Ghostty のキーバインド調整

tmux や zellij を使う場合、Ghostty 側のキーバインドが競合することがあります。以下の設定で Cmd+T/N/W を tmux/zellij にパススルーできます。

```
# ~/.config/ghostty/config

# macOS ショートカットの競合を回避
keybind = super+t=unbind
keybind = super+n=unbind
keybind = super+w=unbind

# コピー&ペーストは維持
keybind = super+c=copy_to_clipboard
keybind = super+v=paste_from_clipboard
keybind = super+q=quit
```

## Before / After

**Before**: ターミナル選びに悩む → 1つに決める → 別のが必要な場面で不便 → また悩む

**After**: Ghostty を開く → fzf で今の用途に合った環境を選ぶ → 選択コストがなくなる

普段は Ghostty の素のシェルで Claude Code を使い、エージェントチームで並列作業する場合のみ tmux を選択しています。セッションが残っていれば一覧に表示されるため、前日の作業への復帰も容易です。

### 筆者の現在の運用

余談ですが、設定を整えて tmux を使い込むうちに操作に慣れてきたため、現在は **Ghostty + tmux** の組み合わせをメインで使用しています。エージェントチームの分割ペインだけでなく、セッション永続化やステータスライン表示も含めて tmux に集約しつつあります。ここは活用レベルと理想によってわかれてくるかと思います。比較しながら用途に合わせて選択するのが良いのではないかと思います。

## まとめ

4つの環境を検証した結果、「Claude Code に最適なターミナルは何か」という問いに対する単一の答えは存在しませんでした。用途によって最適解が変わるため、**選択できる仕組みを用意する**という方針に落ち着きました。

- **普段の Claude Code** → Ghostty 単体（速い・URL が開ける・日本語OK）
- **エージェントチーム分割ペイン** → Ghostty + tmux（セッション管理・並列実行）
- **セッション保存 + 直感的な操作** → Ghostty + zellij（モダン UI・導入しやすい）
- **安定重視・そこまで並列作業をしない** → iTerm2（設定不要・対応範囲が広い）

fzf セッションセレクタは 80 行程度のシェルスクリプトで、Ghostty の `command` に1行追加するだけで動作します。ターミナル環境の選択を都度行いたい場合に有用です。

## 参考

- [ghostty-session-picker](https://github.com/coa00/ghostty-session-picker) — この記事で紹介した fzf セッションセレクタ
- [Ghostty](https://ghostty.org/) — GPU アクセラレーション対応クロスプラットフォームターミナル
- [tmux](https://github.com/tmux/tmux) — ターミナルマルチプレクサ
- [zellij](https://zellij.dev/) — Rust 製ターミナルワークスペース
- [fzf](https://github.com/junegunn/fzf) — コマンドラインファジーファインダー
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic 公式 CLI
- [エージェントチーム](https://code.claude.com/docs/ja/agent-teams) — Claude Code の並列エージェント機能
- [ステータスライン](https://code.claude.com/docs/ja/status-line) — Claude Code のステータス情報表示機能
- [tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect) — tmux セッション保存・復元プラグイン
- [tmux-continuum](https://github.com/tmux-plugins/tmux-continuum) — tmux セッション自動保存プラグイン
- [`it2` CLI](https://github.com/mkusaka/it2) — iTerm2 分割ペインモードに必要な CLI ツール
