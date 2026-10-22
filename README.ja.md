<p align="center">
  <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a> | <b>日本語</b>
</p>

<p align="center">
  <h1 align="center">cinetty</h1>
  <p align="center"><b>ターミナル上で美しく再生されるシステムアーキテクチャアニメーションエンジン</b></p>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/ライセンス-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/JosssphZhou/cinetty"><img src="https://img.shields.io/badge/ターミナル-Kitty%20%7C%20ANSI-orange.svg" alt="Terminal Kitty / ANSI"></a>
  <a href="https://x.com/openmys"><img src="https://img.shields.io/badge/作者-@openmys-black.svg" alt="X @openmys"></a>
</p>

<p align="center">
  <a href="docs/hero.mp4"><img src="docs/hero.gif" width="100%" alt="cinetty demo"></a>
</p>

<p align="center">
  テンプレートを選び、1つの YAML ファイルにシステム構成と時系列イベントを記述し、制約をチェックするだけで、ターミナル上で生き生きとしたアーキテクチャアニメーションが再生されます。
</p>

<p align="center">
  <a href="#テンプレートギャラリー">テンプレートギャラリー</a> |
  <a href="#仕組み">仕組み</a> |
  <a href="#システム要件">システム要件</a> |
  <a href="#クイックスタート">クイックスタート</a> |
  <a href="#agent-スキルとして利用">Agent スキルとして利用</a> |
  <a href="#オリジナルの作成手順">オリジナルの作成手順</a> |
  <a href="#ライセンス">ライセンス</a>
</p>

---

## テンプレートギャラリー

<table>
<tr>
<td align="center" valign="top">
  <a href="templates/loop-landscape/"><img src="templates/loop-landscape/preview/clip.gif" width="420" alt="loop-landscape"></a><br>
  <a href="templates/loop-landscape/"><code>loop-landscape</code></a>
</td>
<td align="center" valign="top">
  <a href="templates/circuit-flow/"><img src="templates/circuit-flow/preview/clip.gif" width="420" alt="circuit-flow"></a><br>
  <a href="templates/circuit-flow/"><code>circuit-flow</code></a>
</td>
</tr>
<tr>
<td align="center" valign="top" colspan="2">
  <a href="templates/screen-flow/"><img src="templates/screen-flow/preview/clip.gif" width="420" alt="screen-flow"></a><br>
  <a href="templates/screen-flow/"><code>screen-flow</code></a>
</td>
</tr>
<tr>
<td align="center" valign="top">
  <a href="templates/loop-portrait/"><img src="templates/loop-portrait/preview/clip.gif" width="270" alt="loop-portrait"></a><br>
  <a href="templates/loop-portrait/"><code>loop-portrait</code></a>
</td>
<td align="center" valign="top">
  <a href="templates/photo-loop/"><img src="templates/photo-loop/preview/clip.gif" width="270" alt="photo-loop"></a><br>
  <a href="templates/photo-loop/"><code>photo-loop</code></a>
</td>
<td align="center" valign="top">
  <a href="templates/pipeline/"><img src="templates/pipeline/preview/clip.gif" width="270" alt="pipeline"></a><br>
  <a href="templates/pipeline/"><code>pipeline</code></a>
</td>
</tr>
</table>

各プレビューはテンプレートの実際の動作を示しています。カードをクリックすると、スキーマ定義、シーン構成、サンプルプロジェクトを確認できます。

🎬 **10秒デモ動画**：[docs/hero.mp4](docs/hero.mp4)

---

## 仕組み

cinetty は、ターミナル向けに厳選された After Effects テンプレート集のように機能します：

- **計算されたアニメーションとリズム**：各テンプレートは、固定の座標グリッド、統一感のある配色、精密に設計されたアニメーションリズム、名前付きコンテンツスロットを備えた完成度の高いアニメーションです。
- **YAML による宣言的定義**：1つの YAML ファイルにコンポーネントやメトリクス、時間軸のイベントを定義するだけで、崩れることなくピクセルパーフェクトな配置が維持されます。
- **ターミナルネイティブ描画と画像プロトコル対応**：標準のテキストセルに直接描画します。写真テンプレートでは Kitty グラフィックスプロトコル経由で高解像度画像を埋め込み表示します。
- **AI Agent ファースト設計**：最も快適な方法はコーディング Agent に任せることです。Agent がリポジトリを解析し、最適なテンプレートを選定し、プロジェクト YAML を記述し、`make check` で文字幅の制約をクリアするまで修正を繰り返して再生します。Agent 向けのガイドラインは [AGENTS.md](AGENTS.md) に記載されています。

---

## システム要件

- **OS**：macOS または Linux（Bash、Make が必要）
- **ターミナル環境**：テキストテンプレートは標準的なターミナルで動作します。写真テンプレート（`photo-loop`）には Kitty グラフィックスプロトコル対応ターミナル（Ghostty、Kitty、WezTerm など）が必要です。
- **Python 環境**：Python 3.12 以上、または [uv](https://docs.astral.sh/uv/)。
- **ディスク容量**：
  - テキストテンプレート：`make setup` で必要な3つの軽量パッケージのみインストール（約 73 MB、数秒で完了）。
  - 写真テンプレート：`make setup-photo` で PyTorch と2つのビジョンモデルを導入（約 2 GB）。
- **推奨フォント（任意）**：CJK 文字の表示幅最適化には Sarasa Term SC（`brew install --cask font-sarasa-gothic`）を推奨します。未導入の場合、macOS ではシステムの標準フォントが使用されます。

---

## クイックスタート

```sh
# リポジトリをクローンして移動
git clone https://github.com/JosssphZhou/cinetty.git cinetty && cd cinetty

# 高速セットアップ：テキストテンプレート用の依存関係をインストール（約 73 MB）
make setup

# サンプルアニメーションの再生
make play INPUT=examples/circuit-flow/project.en.yaml
```

写真テンプレート（`photo-loop`）を実行する場合はモデルをセットアップします：

```sh
# PyTorch とビジョンモデルを追加インストール（約 2 GB）
make setup-photo

# 写真を準備してサンプルを再生
make play INPUT=examples/harness-photo/project.en.yaml
```

### 再生操作と補足

- **再生停止**：いつでも `Ctrl-C` で終了できます。
- **ループ再生**：`LOOP=1` を指定（例：`make play INPUT=... LOOP=1`）。
- **コマンド別名**：`make preview` は `make play` のエイリアスです。
- **画面サイズ調整**：ターミナルのセル数が不足している旨の警告が出た場合は、ウィンドウを最大化するか文字サイズを縮小（`Cmd -`）してください。
- **画面録画**：お好みのターミナル録画ツールを使用して、アニメーションを動画や GIF として書き出せます。

---

## Agent スキルとして利用

リポジトリルートには `SKILL.md` が含まれており、リポジトリ全体を Claude Code や OpenAI Codex のネイティブスキルとして利用できます。ツールのスキルディレクトリにクローンして `make setup` を実行すると、アーキテクチャアニメーションの作成を指示した際に Agent が自動的に cinetty を呼び出します。他の AI アシスタントには同様のワークフローを記載した [AGENTS.md](AGENTS.md) を参照させてください。

| 環境 | すべてのプロジェクト（グローバル） | 単一プロジェクトのみ |
|---|---|---|
| Claude Code | `~/.claude/skills/cinetty` | プロジェクト内の `.claude/skills/cinetty` |
| Codex | `~/.agents/skills/cinetty` | プロジェクト内の `.agents/skills/cinetty` |

```sh
git clone https://github.com/JosssphZhou/cinetty.git ~/.claude/skills/cinetty && make -C ~/.claude/skills/cinetty setup
```

> 2026-10-21 時点で [Claude Code スキル仕様](https://code.claude.com/docs/en/skills) および [Codex スキル仕様](https://developers.openai.com/codex/skills) と整合性を確認済みです。

---

## テンプレート一覧

以下のコマンドで使用可能なすべてのテンプレートを確認できます：

```sh
make templates
```

| テンプレート | 概要 | ターミナル規格 | 再生時間 |
|---|---|---|---|
| [`loop-landscape`](templates/loop-landscape/) | 意思決定コアによるスコアリングを受けながら3ラウンド自己改善する Agent harness | 120 × 40 セル | 約 35 秒 |
| [`loop-portrait`](templates/loop-portrait/) | 上部に高速リアルタイム意思決定ループ、下部に改善を続ける低速学習ループを配置 | 66 × 48 セル | 約 37 秒 |
| [`photo-loop`](templates/photo-loop/) | ビジョンモデルが実際の写真を解析し動的検出枠を表示しながらバックグラウンドで自己改善 | 66 × 48 セル（Kitty 画像） | 約 36 秒（2ラウンド時 約 28 秒） |
| [`pipeline`](templates/pipeline/) | メイン Agent が計画立案し、ルーターが1から3のワーカーにタスクを配信、アドバイザーが要所で介入 | 90 × 46 セル | 1サイクル 15 秒 |
| [`screen-flow`](templates/screen-flow/) | Agent によるスマートフォン操作：OCR、意思決定モデル、ピクセル単位フォールバック、2台連動 | 94 × 37 セル | 26 秒 |
| [`circuit-flow`](templates/circuit-flow/) | バス配線上を信号が伝播するにつれて8つのモジュールが順次点灯 | 120 × 40 セル | 44 秒 |

各テンプレートディレクトリの構成：
- `template.yaml`：フィールドスキーマ、データ型、文字幅上限。
- `scene.yaml`：レイアウト定義、座標系、カラー指定。
- `preview/`：静止画プレビュー（`still.png`）とデモ動画（`clip.gif` / `clip.mp4`）。

`examples/` 配下に各テンプレートの実行可能なサンプルが用意されています。例えば `examples/web-service/` では、回路図テンプレートをマイクロサービス構成に適用した実例を確認できます。

---

## オリジナルの作成手順

### 1. テンプレートを選ぶ
`make templates` で一覧を確認し、選んだテンプレートの `template.yaml` を読み込みます。

### 2. プロジェクト YAML を作成する
サンプルプロジェクトをコピーし、ご自身のシステム構成に合わせて編集します：

```yaml
template: circuit-flow
template_version: 1
name: my-service
credit: false   # 任意：画面下部の "made with cinetty" 表示を非表示にする場合は false
fields:
  title: MY SERVICE
  # ...
events:
  - {t: 3.0, type: light, box: A, until: 7.0}
  # ...
```

### 3. レイアウト制約を検証する
指定されたセル幅にテキストが収まっているかテストします：

```sh
make check INPUT=my-service.yaml
```

文字数オーバーが発生した場合、対象フィールドのパスと超過数が具体的に出力されます：

```text
too_long: fields.modules.B.name (38 > 34): shorten to at most 34 cells (a CJK character counts as 2)
```

文字幅はターミナルの半角セル単位でカウントされます（全角 CJK 文字は2セル）。チェッカーが自動でテキストを切り詰めることはありません。

### 4. 再生する
ターミナル上で再生を実行します：

```sh
make play INPUT=my-service.yaml
```

`screen-flow` はターミナルボード単体を再生します。

### 発展ガイド
- **多言語対応**：1つのプロジェクトファイルには1言語を記述します。多言語展開する場合はファイルをコピーして文言を翻訳してください。
- **カスタムレイアウト**：テキストだけでなく画面レイアウト自体を編集したい場合は [docs/scene-reference.md](docs/scene-reference.md) を参照してください。
- **エンジンアーキテクチャ**：各コンポーネントの連携仕様については [docs/design.md](docs/design.md) を参照してください。

---

## 作者

Joseph Zhou（[@openmys](https://x.com/openmys)）によって作成され、メンテナンスされています。

ご意見、Issue 報告、新しいテンプレートのコントリビューションを心より歓迎します。

---

## ライセンス

- **コードおよびテンプレート**：MIT ライセンス（[LICENSE](LICENSE) 参照）
- **サンプル写真**：CC0（パブリックドメイン）
- **ビジョンモデル**：Apache-2.0 ライセンス
- **サードパーティ著作物**：完全な一覧と出典は [LICENSES.md](LICENSES.md) に記載されています。
