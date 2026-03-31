---
title: "Mac 環境の Claude Code の実行環境について"
emoji: "👻"
type: "tech"
topics: ["claudecode", "ghostty", "tmux", "zellij", "fzf"]
published: true
---

## はじめに

筆者は Claude Code を中心に開発しており、IDE はほぼ起動しなくなりました。確認のために VSCode を開く程度です。

中でも[エージェントチーム機能](https://code.claude.com/docs/ja/agent-teams)を日常的に利用しています。エージェントチームは複数の Claude Code インスタンスがチームとして連携する仕組みで、調査・レビュー・新機能開発・デバッグなど並列探索が有効な場面で活用しています。

エージェントチームには「in-process モード」と「分割ペインモード」の2つの表示モードがあります。in-process モードは任意のターミナルで動作しますが、各チームメンバーの状況を一覧で確認するには**分割ペインモード**が有用です。分割ペインモードには tmux または iTerm2 が必要です。

この分割ペインモードを快適に使えるターミナル環境を探す中で、4つの環境を検証しました。それぞれ一長一短があり1つに絞ることが難しかったため、場面に応じて使い分ける方針にしています。

## ターミナルに求める要件

Claude Code を本格的に使う場合、ターミナルに対する要件が増えます。

- Claude が出力した **URL やファイルパスをクリック**してすぐ開きたい
- **[エージェントチーム](https://code.claude.com/docs/ja/agent-teams)** の分割ペインモードで並列作業したい
- 作業を中断して翌日再開したい → **セッション永続化**が必要
- **日本語プロンプト**をストレスなく入力したい

## 4環境の比較

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

[Ghostty](https://ghostty.org/)（v1.3.1）は GPU アクセラレーション対応のクロスプラットフォームターミナルエミュレータです。macOS では Metal を使用し、起動は体感 0.1 秒以下です。

Claude Code との組み合わせで特に有用なのは **URL のクリック対応**です。`link-url` 機能により、Cmd+Click でブラウザが開きます。Claude Code は URL を頻繁に出力するため、この機能の有無は作業効率に影響します。

**弱点**: セッション管理機能がなく、エージェントチームの分割ペインモードにも非対応です。

### iTerm2 — 機能が豊富で設定不要

macOS ターミナルの定番 [iTerm2](https://iterm2.com/) です。ネイティブ対応で安定性が高く、エージェントチームの分割ペインモードにも対応しています（[`it2` CLI](https://github.com/mkusaka/it2) のインストールと Python API の有効化が必要）。

**弱点**: Ghostty と比較すると描画が重い傾向があります。Claude Code の長い出力が流れる場面で、Ghostty では発生しない描画の遅延が確認されました。

### Ghostty + tmux — 設定・プラグインで拡張

[tmux](https://github.com/tmux/tmux/wiki/Installing) を組み合わせることで、エージェントチームの分割ペインモードが利用可能になります。加えて以下の機能も得られます。

- **セッション永続化**: [tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect) + [tmux-continuum](https://github.com/tmux-plugins/tmux-continuum) でウィンドウ構成・ペイン配置・作業ディレクトリの保存・復元が可能
- **[ステータスライン表示](https://code.claude.com/docs/ja/status-line)**: tmux のステータスバーに Claude Code のプロジェクト名・モデル名・コンテキスト使用率を常時表示可能

**注意点**: tmux 越しだと Ghostty のネイティブ機能が一部制限されます。URL クリック（Cmd+Shift+Click で対応）、Shift+Enter 改行（Ghostty 設定で対応）については、後述の設定セクションを参照してください。

### Ghostty + zellij — 組み込み機能が充実

[zellij](https://zellij.dev/)（v0.43.1）は Rust 製のターミナルワークスペースです。UI にガイドが表示されるため、tmux のようにキーバインドを暗記する必要がありません。セッション永続化も組み込みで対応しています。

操作性は全体的に tmux より直感的で、マルチプレクサの経験が少ない場合にも導入しやすい環境です。

**弱点**: エージェントチームの分割ペインモードには非対応です。URL クリックは tmux と同様に Cmd+Shift+Click で対応可能です。

## 用途別おすすめ

| 用途 | おすすめ |
|------|---------|
| 普段の Claude Code 利用 | **Ghostty 単体**（URL クリック・日本語入力が快適） |
| エージェントチーム分割ペインで並列作業 | **Ghostty + tmux**（Shift+Enter は設定で解決） |
| セッション保存 + 直感的な操作 | **Ghostty + zellij** |
| 安定重視・そこまで並列作業をしない | **iTerm2** |

## Ghostty + tmux/zellij の設定

tmux や zellij を Ghostty と組み合わせる場合に必要な設定をまとめます。

### tmux: Shift+Enter 改行

tmux 越しだと Claude Code で Shift+Enter による改行が効かないため、Ghostty 側で以下の設定が必要です。

```
# ~/.config/ghostty/config
keybind = shift+enter=text:\x1b[13;2u
```

### tmux: セッション永続化

```bash
# tmux.conf
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'
set -g @resurrect-capture-pane-contents 'on'
set -g @continuum-restore 'on'
set -g @continuum-save-interval '15'
```

### tmux: Claude Code ステータスライン

```bash
# tmux.conf
# 左側: プロジェクト名
set -g status-left "#[fg=#89b4fa,bold] #(cat ~/.claude/tmux-status-left.txt 2>/dev/null || echo '#S') "
# 右側: モデル名・コンテキスト使用率・レート制限・コスト
set -g status-right "#[fg=#a6e3a1]#(cat ~/.claude/tmux-status-right.txt 2>/dev/null)#[default]"
```

### zellij: セッション永続化

```kdl
// zellij config.kdl
session_serialization true
serialize_pane_viewport true
```

### Ghostty: キーバインド調整（共通）

tmux や zellij を使う場合、Ghostty 側のキーバインドが競合することがあります。

```
# ~/.config/ghostty/config
keybind = super+t=unbind
keybind = super+n=unbind
keybind = super+w=unbind
keybind = super+c=copy_to_clipboard
keybind = super+v=paste_from_clipboard
keybind = super+q=quit
```

## fzf セッションセレクタ

用途によって最適解が変わるため、Ghostty で新しいウィンドウを開くたびに fzf で環境を選択できるスクリプトを作成しました。

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

### 仕組み

1. Ghostty の `command` 設定でスクリプトを起動
2. スクリプトが zellij と tmux の既存セッションを列挙
3. fzf で選択 → 選んだセッションにアタッチ or 新規作成
4. Esc/Ctrl+C で fzf をキャンセルすると素のシェルが起動

### インストール

スクリプトは GitHub で公開しています。

https://github.com/coa00/ghostty-session-picker

```bash
curl -fsSL https://raw.githubusercontent.com/coa00/ghostty-session-picker/main/ghostty-session-picker \
  -o ~/.local/bin/ghostty-session-picker
chmod +x ~/.local/bin/ghostty-session-picker
```

Ghostty の設定に1行追加します。

```
# ~/.config/ghostty/config
command = /Users/you/.local/bin/zellij-sessionizer
```

作業ディレクトリの自動復元を有効にするには、`~/.zshrc` に以下を追加します:

```bash
chpwd() {
  echo "$PWD" > ~/.last_working_dir
}
```

## まとめ

4つの環境を検証した結果、用途によって最適解が変わるため、**選択できる仕組みを用意する**という方針に落ち着きました。

- **普段の Claude Code** → Ghostty 単体
- **エージェントチーム分割ペイン** → Ghostty + tmux
- **セッション保存 + 直感的な操作** → Ghostty + zellij
- **安定重視・そこまで並列作業をしない** → iTerm2

筆者自身は、設定を整えて tmux を使い込むうちに操作に慣れてきたため、現在は **Ghostty + tmux** をメインで使用しています。エージェントチームの分割ペインだけでなく、セッション永続化やステータスライン表示も含めて tmux に集約しつつあります。ここは活用レベルと理想によってわかれてくるかと思います。比較しながら用途に合わせて選択するのが良いのではないかと思います。

## 参考

- [ghostty-session-picker](https://github.com/coa00/ghostty-session-picker) — fzf セッションセレクタ
- [Ghostty](https://ghostty.org/) — GPU アクセラレーション対応ターミナル
- [iTerm2](https://iterm2.com/) — macOS 定番ターミナル
- [tmux](https://github.com/tmux/tmux) — ターミナルマルチプレクサ
- [zellij](https://zellij.dev/) — Rust 製ターミナルワークスペース
- [fzf](https://github.com/junegunn/fzf) — コマンドラインファジーファインダー
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic 公式 CLI
- [エージェントチーム](https://code.claude.com/docs/ja/agent-teams) — Claude Code の並列エージェント機能
- [ステータスライン](https://code.claude.com/docs/ja/status-line) — Claude Code のステータス情報表示機能
- [tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect) — tmux セッション保存・復元プラグイン
- [tmux-continuum](https://github.com/tmux-plugins/tmux-continuum) — tmux セッション自動保存プラグイン
- [`it2` CLI](https://github.com/mkusaka/it2) — iTerm2 分割ペインモード用 CLI
