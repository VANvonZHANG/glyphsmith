# glyphsmith

**GSF 字形骨架渲染器**——把 [GlyphWiki](https://glyphwiki.org) 背后的 KAGE/2 笔画骨架数据
（经 [gsftool](https://github.com/VANvonZHANG/gsftool) 无损转成 GSF）渲染成轮廓与 SVG，
并提供 agent 友好的 CLI 与 Python 库。

[![CI](https://github.com/VANvonZHANG/glyphsmith/actions/workflows/ci.yml/badge.svg)](https://github.com/VANvonZHANG/glyphsmith/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)
[English (英文主 README)](README.md)

三个后端共用同一套轮廓结构与同一条 CLI：

| 后端 | 定位 |
|---|---|
| `legacy-kurgm` | [kage-engine](https://github.com/kurgm/kage-engine)（TypeScript）的逐行 Python 移植，与参考实现**逐点全等**（见[验证](#验证)）——回归基线 |
| `pen` | v2 风格引擎：笔画关系图 + 声明式风格文件（`--style serif-song\|sans-hei\|sans-round\|<路径>`）。变宽笔尖；端部形状来自数据，加饰来自风格 |
| `pen-minimal` | 等宽描边骨架预览（butt 端帽、逐段四边形；Levien「弱正确」级）。预览级，是 v1 接口占位，保留作等价性锚点 |

`--backend both` 把 `legacy-kurgm` 与 `pen` 各渲一次并排返回——有意义的对照现在是
忠实实现 vs pen，而不再是 忠实实现 vs 预览。

## 为什么有这个项目

GlyphWiki 存的是骨架，`gsftool` 负责无损地把骨架转成 GSF，`glyphsmith` 负责把它画出来。
做这件事有三个理由。

**一、忠实渲染，而且是量出来的。** `legacy-kurgm` 是 kurgm/kage-engine 的忠实移植，连它的
怪癖一起移植。忠实度不靠肉眼比对，靠指纹（轮廓数 + 顶点数 + 全部坐标的 sha1，ε = 0）：
kage-engine 自带的 golden 矩阵 7,614/7,614，真实 dump 随机抽样 1,000 例与 Node 原版
1,000/1,000。见[验证](#验证)。

**二、写什么渲什么，不「顺手纠错」。** 学习型字体生成模型有一处已被记录在案的偏置：
当字形与训练分布存在微妙差异时，"the bias is prone to either correcting or ignoring these
subtle variations"（[SFGN, arXiv:2501.08062](https://arxiv.org/abs/2501.08062)）。
这对俗字、喃字这类变体字形研究是致命的——研究对象常常正是「标准字形 + 多一点」。
规则引擎不做这种"纠正"，本项目的立足点就在这里。

**三、agent 原生。** 库与 CLI 在同一个进程内覆盖完整闭环：解析引用闭包 → 渲染 → 与目标
比对 → 改参数 → 再渲染。`compare` 给出栅格 IoU 与逐笔结构度量（bbox IoU、顶点数、
Hausdorff 距离）；CLI 在 stdout 恒输出单行 JSON、退出码有语义、失败时把下一步该执行的
命令放进 `hints`。

## 安装

`glyphsmith` 需要 Python ≥ 3.11、`numpy`、`pillow`，以及 **gsftool**（GSF 解析/写回器，
尚未发布到 PyPI）：

```sh
pip install git+https://github.com/VANvonZHANG/gsftool
pip install git+https://github.com/VANvonZHANG/glyphsmith
glyphsmith --help
```

或者从仓库克隆开发（两个仓需并排放置）：

```sh
git clone https://github.com/VANvonZHANG/gsftool
git clone https://github.com/VANvonZHANG/glyphsmith
pip install -e gsftool -e "glyphsmith[dev]"    # [dev] 只加 pytest
cd glyphsmith && pytest -q
```

console script 不在 `PATH` 时，`python -m glyphsmith.cli …` 与 `glyphsmith …` 等价。
全量语料不随仓分发：`--corpus` 指向 GSF 文件或 GlyphWiki 的 `dump_newest_only.txt`。
唯一例外是 8 字形示例文件 [`examples/showcase.gsf`](examples/showcase.gsf)（见
[许可证与谱系](#许可证与谱系)），下文所有示例都用它——**这些示例假设你在本仓的克隆里
操作**，`pip install` 不会带上 `examples/` 目录。

## 快速开始

### 渲染一个字形

```sh
$ glyphsmith render u4e00-j --corpus examples/showcase.gsf
{"status": "ok", "data": {"name": "u4e00-j", "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 200 200\" width=\"200\" height=\"200\"><path d=\"M 14,99 L 186,99 L 186,103 L 14,103 Z M 186,99 L 162,101 L 174,89 Z\" fill=\"black\" fill-rule=\"nonzero\"/></svg>"}, "warnings": [], "hints": []}

$ glyphsmith render u6f22-j --out png --corpus examples/showcase.gsf
{"status": "ok", "data": {"name": "u6f22-j", "path": "u6f22-j.png"}, "warnings": [], "hints": []}
```

`--out` 取 `svg`（缺省，结果内联返回、不落盘）、`png`（写到当前目录 `<名字>.png`）或
`outline.json`。`--backend` 取 `legacy-kurgm`（缺省）、`pen`、`pen-minimal` 或 `both`
（legacy-kurgm 与 pen 各渲一次，分别放在 `svg_legacy` / `svg_pen`）。`--font` 取
`serif`/`mincho` 或 `sans`/`gothic`，属于 `legacy-kurgm`；pen 后端不看 `--font`，改用
`--style <名字|路径>`——三个内置风格由 `glyphsmith styles` 列出：

```sh
$ glyphsmith render u4e00-j --corpus examples/showcase.gsf --backend pen --style sans-hei
$ glyphsmith styles
{"status": "ok", "data": {"styles": [{"name": "sans-hei", "genre": "sans", "path": "…/styles/sans-hei.yaml", "description": "sans style with 0 decoration(s) and 0 rule(s)"}, …]}, "warnings": [], "hints": []}
```

`--style` 为空、未知，或指向读不出来的文件，都是用法错误（退出码 2，消息在 `data.error`），
不会静默回退到缺省风格。

### 解析引用闭包

GlyphWiki 的字形由部件引用拼成，所以渲染一个字要先解析它的闭包：

```sh
$ glyphsmith resolve u6f22 --corpus examples/showcase.gsf
{"status": "ok", "data": {"name": "u6f22", "closure": ["u26c29-02", "u6c35-01", "u6f22", "u6f22-j"], "dangling": [], "depth": 3}, "warnings": [], "hints": []}
```

`closure` 是参与渲染的全部字形，`depth` 是最深引用链，`dangling` 列出语料里找不到目标的
引用。引用成环在解析期即被检出：命令以退出码 4 结束，`data.error` 携带环路径——渲染器
不会无限递归。

### 比对两个字形

```sh
$ glyphsmith compare u6f22-j u6f22-v --corpus examples/showcase.gsf
{"status": "ok", "data": {"iou": 0.5289900575614861, "per_stroke": []}, "warnings": ["stroke count mismatch: 15 vs 16; per_stroke skipped"], "hints": []}
```

`u6f22-j` 与 `u6f22-v` 是「漢」的两个真实变体（部件切法不同），栅格 IoU 0.53。两者笔画数
不等，逐笔度量无意义，于是 CLI 把它写进 `warnings` 而不是返回一份静默的空列表。

### 用库

```python
from glyphsmith import Corpus, Renderer, compare

corpus = Corpus.from_gsf("examples/showcase.gsf")     # 或 Corpus.from_dump("dump_newest_only.txt")
han = corpus.resolve("u6f22-j")                       # 引用闭包（含环检测）

serif = Renderer(backend="legacy-kurgm", font="mincho").render(han)
gothic = Renderer(backend="legacy-kurgm", font="gothic").render(han)     # 同一骨架换书体
pen = Renderer(backend="pen", style="serif-song").render(han)            # v2 风格引擎
preview = Renderer(backend="pen-minimal").render(han)

print("contours:", len(serif.contours))               # contours: 28
print("mincho vs gothic  IoU:", round(compare(serif, gothic).iou, 3))    # 0.635
print("mincho vs preview IoU:", round(compare(serif, preview).iou, 3))   # 0.548
svg = serif.to_svg()                                  # Outline -> SVG；或 to_path_d() 取路径
```

`Renderer.render()` 返回 `Outline`：一组轮廓，每个点是 `(x, y, off)`，坐标在 GlyphWiki 的
200×200 网格上、y 向下，`off=1` 表示 off-curve 点（TrueType 惯例）。

## 架构

| 模块 | 职责 |
|---|---|
| `glyphsmith.protocol` | `Backend` 协议 + 注册表、`Renderer`（公开 API）、`RenderOptions` |
| `glyphsmith.corpus` | `Corpus`：装载 GSF 文件或 GlyphWiki dump、缓存解析结果、解析引用闭包、检环、报告悬空引用 |
| `glyphsmith.legacy_kurgm` | 忠实移植：宋/黑规则表（直线与曲线两种）、笔画几何、变换、指纹 |
| `glyphsmith.pen` | v2 后端：关系图、声明式风格文件、变宽笔尖（`style.py`、`graph.py`、`nib.py`、`backend.py`） |
| `glyphsmith.pen_minimal` | 预览后端：把每段控制线段按等宽描出轮廓 |
| `glyphsmith.outline` | 两后端共用的 `Outline` 结构（`to_svg`、`to_path_d`） |
| `glyphsmith.compare` | 栅格 IoU + 逐笔结构度量 |
| `glyphsmith.batch` | 多进程整库渲染到 `outdir/<名字>.svg` |
| `glyphsmith.cli` | JSON 契约 CLI |

数据流刻意收得很窄：`Corpus.resolve(name)` → `ResolveResult`（字形 + 部件 + 警告）→
`Backend.render(result)` → `Outline`。下游的一切——SVG、PNG、`compare`、`batch`、冒烟
脚本——都只消费 `Outline`，因此与后端无关。

新增后端 = 在一个会被 import 的模块里调 `Backend.register`（`glyphsmith/__init__.py` 就是
这样挂上两个自带后端的）；之后 CLI、`compare` 与库都能按名字用它。但有两处**不是**自动的，
写新后端前值得知道：`batch` 在独立进程里跑 worker，新后端必须同时加进
`glyphsmith.batch._BACKEND_MODULES`（后端名 → 模块名，worker 内按名 import；否则 worker 侧
按未注册后端报错，逐字形计入 `errors`），`scripts/smoke_full.py` 复用同一张表。

## CLI 契约

`glyphsmith` 在 stdout 恒输出一行 JSON，信封固定：

```json
{"status": "ok|error", "data": {…}, "warnings": ["…"], "hints": [{"action": "…", "reason": "…"}]}
```

| 退出码 | 含义 |
|---|---|
| 0 | 成功——结果在 `data` |
| 2 | 用法错误：参数非法、未知后端/字体、语料打不开、写盘失败 |
| 3 | 未知字形——`hints` 附 `glyphsmith list --like '<前缀>*'` 补救命令 |
| 4 | 引用成环——`data.error` 携带环路径 |

诊断信息绝不进 stdout，所以 `glyphsmith … | jq .data.svg` 可直接用。警告是数据不是失败：
悬空引用、版本兜底等情形写进 `warnings`，命令仍以 0 退出。

## 验证

下表的每个数字都可在本仓复现；外部输入缺失时相关用例**跳过而非失败**。

| 层级 | 判据 | 结果 |
|---|---|---|
| golden 矩阵 | kage-engine 自带的 7,614 用例，逐字符指纹 | **7,614/7,614** |
| 交叉引擎 | 真实 dump 随机抽样 1,000 字形，与 Node 版 kage-engine 指纹对拍 | **1,000/1,000** |
| 全量冒烟 | `dump_newest_only.txt` 全部字形（2,221,895）渲染并计数、不写盘 | **2,221,895 字形，err=0** |
| 测试套件 | `pytest` | **7,783 passed** |

golden 夹具是 kage-engine 自带的 `test/strokes.js` 快照
（`tests/fixtures/kurgm-strokes-golden.tsv`）——是**参考实现的期望值**，不是我们自己写的期望。

```sh
pytest -q                                                   # 7,775 passed, 8 skipped（无外部数据时）
pytest -m golden -q                                         # 7,614 passed —— golden 矩阵
GSF_DUMP=<dump>/dump_newest_only.txt \
  KAGE_ENGINE=<kage-engine>/lib/esm/index.js pytest -q      # 7,783 passed —— 零跳过
```

无外部资源时跳过的 8 条，是需要 318MB dump、Node.js 或 kage-engine 检出物的用例；它们
由环境变量启用，从不需要改测试代码：

| 环境变量 | 使用方 | 含义 |
|---|---|---|
| `GSF_DUMP` | `pytest`、`scripts/smoke_full.py` | `dump_newest_only.txt` 路径。未设 ⇒ 依赖 dump 的用例跳过 |
| `KAGE_ENGINE` | `pytest`、`scripts/render_bridge.mjs` | kage-engine 的 ESM 入口路径（`<kage-engine>/lib/esm/index.js`，或 `npm install @kurgm/kage-engine` 后的 `node_modules/@kurgm/kage-engine/lib/esm/index.js`）。未设 ⇒ 交叉对拍用例跳过，`render_bridge.mjs` 以退出码 2 + stderr JSON 结束 |

全量冒烟两口径（`scripts/smoke_full.py`，16 workers，`legacy-kurgm`/mincho）：

| 口径 | 总数 | ok | empty | err | 耗时 |
|---|---:|---:|---:|---:|---:|
| stroke-only（parts 只含字形自身） | 2,221,895 | 166,755 | 2,055,140 | **0** | 串行 82s / 8 workers 17s |
| closure（每字形 `Corpus.resolve`） | 2,221,895 | 2,221,576 | 319 | **0** | 16 workers 213s |

两口径度量不同的问题：stroke-only 问「渲染器对任意数据崩不崩」（纯 ref 字形必然为空——
它的部件没有展开），closure 问「每个字形最终轮廓是否非空」。耗时与机器有关，计数无关
——仓库的测试把串行与并行的计数钉成必须一致。快速抽验：

```sh
$ GSF_DUMP=<dump> python scripts/smoke_full.py --limit 20000 --workers 8
scope=stroke-only backend=legacy-kurgm workers=8 total=20000 ok=165 empty=19835 err=0 elapsed=2.7s rate=7322/s
```

## 已知限制

- **`legacy-kurgm` 只画宋与黑**（`--font serif|sans` → mincho/gothic），继承自 kage-engine
  的两套规则表（`kagecd.js`/`kagedf.js`）。楷、圆、隶等书体不在覆盖范围——这正是 v2 pen
  后端的动机。
- **`pen-minimal` 是预览级。** 等宽 `WIDTH = 8.0`、仅 butt 端帽、逐段四边形、无布尔并集、
  跳过变换。它的存在是为了证明 `Backend` 协议不是 legacy 专属形状，兼作快速预览工具。
  它当初占位的 v2 引擎现已落地为 `--backend pen`（关系图 + 风格文件 + 变宽笔模型，
  设计与公式见 [`docs/pen-backend-design.md`](docs/pen-backend-design.md)）。
- **`batch` 不解析引用。** 与冒烟口径一致，它只拿字形自身的部件渲染（全库吞吐下的取舍），
  因此纯 ref 字形会输出空 SVG。需要闭包渲染时用 `render`。batch 的统计里有 `empty` 计数。
- **没有 SFD/OTF 导出。** 输出只有 SVG、PNG 与 `outline.json`，没有字体文件写回器。
- **没有 IDS 布局层。** 组字只按 GlyphWiki 存的显式 `ref` + box，不做左右/上下结构推断。
- **1 个已知残差字形。** `hkcs_m730b-p01-s00` 里 `116p` 处应为数字，是源数据笔误：
  kage-engine 让 `NaN` 参与笔画绘制，我们跳过该畸形行、照画其余。对另外 2,221,894 个字形
  零渲染影响；把 `116p` 改成 `116` 后两侧全等。残余畸形行清单见
  `scripts/audit_gap_glyphs.py::KNOWN_RESIDUAL_GLYPHS`。
- **版本兜底语义与 kage-engine 不同，且是有意为之。** 引用了 `X@N` 但该版本行不在
  newest dump 时，glyphsmith 回退渲染 newest `X` 并发 `version ref fallback` 警告；
  kage-engine 精确匹配、查不到即静默不画。这是语料层的长期差异（已披露），不在渲染器内。

## 许可证与谱系

`glyphsmith` 按 **GNU General Public License v3.0 or later**（GPL-3.0-or-later）发布，
见 [`LICENSE`](LICENSE)。Copyright (C) 2026 Fan Zhang。

`legacy-kurgm` 后端是移植，谱系具体如下：

- **[kurgm/kage-engine](https://github.com/kurgm/kage-engine)**（TypeScript，npm
  `@kurgm/kage-engine`）——移植基准，glyphsmith 与它逐点一致；
- **[kamichikoichi/kage-engine](https://github.com/kamichikoichi/kage-engine)**——原版引擎，
  笔画规则表 `kagecd.js`（宋）/`kagedf.js`（黑）的最终出处；
- **[HowardZorn/kage-engine](https://github.com/HowardZorn/kage-engine)**——Python 移植先例，
  用作参考；
- **[takushun-wu/kage-cpp](https://github.com/takushun-wu/kage-cpp)**——环检测（`CheckGlyph`）
  思路回移植自这里。

**由 GlyphWiki 数据渲染出的字形输出不受 GPLv3 约束**：GlyphWiki 的数据文件是另一件作品，
由 [GlyphWiki 项目](https://glyphwiki.org)按其自由许可分发（"These data files are free
software. Unlimited permission is hereby granted to use, copy, and distribute these files,
with or without modification, either commercially or non-commercially." — Copyright 2009
GlyphWiki Project）。语料本体不在本仓——但本仓也并非零数据：唯一打包的字形数据是
[`examples/showcase.gsf`](examples/showcase.gsf)，即上文各示例所用的 8 个字形，按同一份
GlyphWiki 许可再分发，文件头注明了来源与许可。其余语料需自行用 `--corpus` 指定。

## 相关项目

- **[gsftool](https://github.com/VANvonZHANG/gsftool)**——KAGE/2 ⇄ GSF 转换器与往返验证器，
  glyphsmith 读到的每个字形都来自它。**存骨不存肉**：gsftool 存骨架，glyphsmith 画肉。
- **[GlyphWiki](https://glyphwiki.org)**——本项工作所用的社区字形数据库，也是测试语料的来源。
- **[kage-engine](https://github.com/kurgm/kage-engine)**——参考渲染器，本项目用它作为
  golden 与交叉引擎的判据来源。
