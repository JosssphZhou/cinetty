<p align="center">
  <a href="README.md">English</a> | <b>简体中文</b> | <a href="README.ja.md">日本語</a>
</p>

<p align="center">
  <p align="center"><img src="docs/logo.png" alt="cinetty" width="476"></p>
  <p align="center"><b>在终端直接流畅播放的系统架构动画引擎</b></p>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/许可-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/JosssphZhou/cinetty"><img src="https://img.shields.io/badge/终端-Kitty%20%7C%20ANSI-orange.svg" alt="终端 Kitty / ANSI"></a>
  <a href="https://x.com/openmys"><img src="https://img.shields.io/badge/作者-@openmys-black.svg" alt="X @openmys"></a>
</p>

<p align="center">
  <a href="docs/hero.mp4"><img src="docs/hero.gif" width="100%" alt="cinetty demo"></a>
</p>

<p align="center">
  选一个模板，用单份 YAML 文件填入系统配置与时序事件，校验网格约束，即可在终端字符格内欣赏生动流畅的架构动效。
</p>

<p align="center">
  <a href="#模板展厅">模板展厅</a> |
  <a href="#工作方式">工作方式</a> |
  <a href="#环境要求">环境要求</a> |
  <a href="#快速开始">快速开始</a> |
  <a href="#作为-agent-技能使用">作为 Agent 技能使用</a> |
  <a href="#制作你的专属动画">制作你的专属动画</a> |
  <a href="#开源许可">开源许可</a>
</p>

---

## 模板展厅

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

每个预览均直观呈现模板的运行状态。点击对应卡片即可查看该模板的参数规范、场景布局与示例工程。

🎬 **10 秒演示短片**：[docs/hero.mp4](docs/hero.mp4)

---

## 工作方式

cinetty 就像一套专为终端精心设计的 After Effects 模板库：

- **预置动画与节奏**：每个模板都是一支完整的动画作品，拥有固定的坐标系统、考究的配色和精确调节的动态节奏，并预留具名内容插槽。
- **YAML 声明式驱动**：你只需要在单份 YAML 文件中定义自己的模块、属性与时序事件，底层布局保持锁定与精准对齐。
- **终端原生与图形协议兼容**：纯文本模板直接渲染于终端字符格；照片模板则基于 Kitty 图形协议嵌入高品质图像资产。
- **面向 AI Agent 深度优化**：最轻松的用法是交给编程 Agent 处理。Agent 会自动分析你的代码仓库、挑选适配模板、生成项目 YAML、反复运行 `make check` 直至字符宽度完全达标，并在终端中播放。详细 Agent 指引请参阅 [AGENTS.md](AGENTS.md)。

---

## 环境要求

- **操作系统**：macOS 或 Linux，内置 Bash 与 Make。
- **终端支持**：纯文本模板支持各类标准终端；照片模板（`photo-loop`）需支持 Kitty 图形协议的终端（如 Ghostty、Kitty、WezTerm 等）。
- **Python 环境**：Python 3.12 或更新版本，亦可使用 [uv](https://docs.astral.sh/uv/)。
- **磁盘空间**：
  - 文字模板：`make setup` 仅安装文字模板所需的三个轻量依赖（约 73 MB，数秒即可装完）。
  - 照片模板：运行 `make setup-photo` 补装 PyTorch 与两个视觉模型（约 2 GB）。
- **中文字体（可选）**：推荐安装 Sarasa Term SC（`brew install --cask font-sarasa-gothic`），以获得最优的中西文字符对齐效果；未安装时 macOS 将使用系统自带中文字体。

---

## 快速开始

```sh
# 克隆代码仓库并进入目录
git clone https://github.com/JosssphZhou/cinetty.git cinetty && cd cinetty

# 快速安装：安装文字模板所需的轻量依赖（约 73 MB）
make setup

# 播放示例动画
make play INPUT=examples/circuit-flow/project.en.yaml
```

若需运行照片模板（`photo-loop`），请先补装模型依赖：

```sh
# 补装 PyTorch 与视觉模型（约 2 GB）
make setup-photo

# 准备照片并播放照片示例
make play INPUT=examples/harness-photo/project.zh.yaml
```

### 播放控制与实用技巧

- **停止播放**：随时按下 `Ctrl-C` 即可退出。
- **循环播放**：指定参数 `LOOP=1`（例如 `make play INPUT=... LOOP=1`）。
- **命令别名**：`make preview` 与 `make play` 功能完全一致。
- **窗口尺寸适配**：若终端提示格数不足，请放大终端窗口或缩小字体显示（`Cmd -`）。
- **屏幕录制**：可使用任意习惯的终端录屏工具录制动画并导出为视频或 GIF。

---

## 作为 Agent 技能使用

仓库根目录下包含 `SKILL.md`，整个仓库可作为独立技能直接接入 Claude Code 与 OpenAI Codex。将其克隆至对应工具的技能目录并执行 `make setup`，之后在提出架构动画需求时，Agent 会自动调用它。其他 Agent 请参考内容一致的 [AGENTS.md](AGENTS.md)。

| 工具类型 | 全局可用（所有项目） | 仅单个项目可用 |
|---|---|---|
| Claude Code | `~/.claude/skills/cinetty` | 对应项目下的 `.claude/skills/cinetty` |
| Codex | `~/.agents/skills/cinetty` | 对应项目下的 `.agents/skills/cinetty` |

```sh
git clone https://github.com/JosssphZhou/cinetty.git ~/.claude/skills/cinetty && make -C ~/.claude/skills/cinetty setup
```

> 目录路径于 2026-10-21 依据 [Claude Code 技能文档](https://code.claude.com/docs/en/skills) 与 [Codex 技能文档](https://developers.openai.com/codex/skills) 核对。

---

## 模板一览

运行以下命令查看全部六个模板：

```sh
make templates
```

| 模板名称 | 展示内容 | 终端格数规格 | 动画时长 |
|---|---|---|---|
| [`loop-landscape`](templates/loop-landscape/) | 自我迭代三轮的 Agent harness，由决策核心评分 | 120 × 40 格 | 约 35 秒 |
| [`loop-portrait`](templates/loop-portrait/) | 上层为实时决策快循环，下层为持续优化的慢循环 | 66 × 48 格 | 约 37 秒 |
| [`photo-loop`](templates/photo-loop/) | 视觉模型读取真实照片并带有动态检测框，后台循环持续迭代 | 66 × 48 格（Kitty 图像） | 约 36 秒（两轮模式约 28 秒） |
| [`pipeline`](templates/pipeline/) | 主 Agent 负责规划，路由分发至一到三个工作节点，顾问在关键节点介入 | 90 × 46 格 | 每轮周期 15 秒 |
| [`screen-flow`](templates/screen-flow/) | Agent 操作手机：OCR、决策模型、像素兜底及双设备联动 | 94 × 37 格 | 26 秒 |
| [`circuit-flow`](templates/circuit-flow/) | 八个模块随总线信号的传递依次点亮 | 120 × 40 格 | 44 秒 |

每个模板目录均包含：
- `template.yaml`：字段定义、数据类型及字符长度上限。
- `scene.yaml`：界面布局与网格排布。
- `preview/`：静态预览帧（`still.png`）与演示短片（`clip.gif` / `clip.mp4`）。

`examples/` 目录下为每个模板都提供了至少一份可运行的示例；其中 `examples/web-service/` 演示了如何将电路图模板应用于 Web 微服务架构。

---

## 制作你的专属动画

### 1. 选择模板
运行 `make templates` 挑选合适的模板，并阅读该模板下的 `template.yaml` 规格定义。

### 2. 编写项目 YAML 文件
复制现有示例文件，将字段内容替换为你自己的系统信息：

```yaml
template: circuit-flow
template_version: 1
name: my-service
credit: false   # 可选：设为 false 可隐藏画面底部 "made with cinetty" 水印
fields:
  title: MY SERVICE
  # ...
events:
  - {t: 3.0, type: light, box: A, until: 7.0}
  # ...
```

### 3. 校验布局规格与字符限制
运行 `make check` 验证文字宽度是否符合终端网格预算：

```sh
make check INPUT=my-service.yaml
```

任何超限问题均会明确指出字段路径与超出数值：

```text
too_long: fields.modules.B.name (38 > 34): shorten to at most 34 cells (a CJK character counts as 2)
```

宽度按终端字符格计算，一个汉字占两格。检查工具仅报告超长位置，不会自动截断文本。

### 4. 播放动画
在当前终端执行播放：

```sh
make play INPUT="my-service.yaml"
```

手机模板在终端中仅播放操作看板。

### 进阶参考
- **多语言适配**：单个项目文件专用于一种语言；如需第二种语言，直接复制该 YAML 文件并翻译文本内容。
- **自定义布局**：如需调整视觉布局而非仅修改文本，请阅读 [docs/scene-reference.md](docs/scene-reference.md)。
- **底层架构**：关于引擎内部设计与模块协作机制，详见 [docs/design.md](docs/design.md)。

---

## 作者

由 Joseph Zhou（[@openmys](https://x.com/openmys)）创建与维护。

欢迎反馈建议、提交 Issue 或分享新的模板实现！

---

## 开源许可

- **代码与模板**：采用 MIT 许可证（详见 [LICENSE](LICENSE)）。
- **示例图片**：采用 CC0（公有领域）许可。
- **预置模型**：采用 Apache-2.0 许可证。
- **第三方文件**：完整的第三方依赖清单与来源说明请查阅 [LICENSES.md](LICENSES.md)。
