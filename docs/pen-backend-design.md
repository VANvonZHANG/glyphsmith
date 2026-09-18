# pen 后端设计（v2 预留，v1 锁接口）

> 本文是 pen 后端的独立设计说明：不依赖任何仓外文档即可回答三个问题——
> **要做什么**（三模块与数据流）、**为什么这么设计**（双后端分工与词汇决议）、
> **需要哪些几何/学术依据**（平行曲线/弱-强正确/关系图/参数化先例）。
>
> v1 交付的只有它的接口占位实现 `pen-minimal`（`src/glyphsmith/pen_minimal.py`：
> 等宽描边 + butt 端帽，逐段四边形，nonzero 并集即 Levien「弱正确」级）——
> 它证明 Backend 协议不是 legacy 专属形状。graph/style/nib 三模块与风格文件
> 引擎均为 v2 范围。

## 一、为什么要有第二个后端

v1 的 `legacy-kurgm` 是忠实移植：写什么渲什么，与参考实现逐点全等（这是
研究基线）。它的代价是**风格不可参数化**——宋/黑之别来自 kagecd.js/kagedf.js
两套硬编码规则表，改一个笔画端部要改代码，且规则只覆盖这两族。

研究侧真正的诉求是**风格可声明、可对拍**：同一份骨架数据，换一份风格文件
就得到另一种书体，且「骨架 → 轮廓」的每一步都能被 agent 检视和干预。这不是
替代 legacy-kurgm，而是与它分工：

| | `legacy-kurgm`（v1） | `pen`（v2） |
|---|---|---|
| 目标 | 与 kage-engine 逐点全等 | 风格参数化、可解释、可迭代 |
| 规则来源 | kagecd/kagedf 硬编码规则表 | YAML 风格文件（声明式） |
| 宽度 | 由规则表与端部码决定 | 骨架 × w(t) 宽度剖面 × 端帽/装饰件 |
| 覆盖书体 | 宋（mincho）/黑（gothic） | 目标：serif/sans/round 的配方族 |
| 角色 | 回归基线、交叉验证参照 | 研究主战场 |

## 二、v1 已锁定的接口（v2 的施工面）

1. **`Backend` 协议**（`src/glyphsmith/protocol.py`）：`render(result)` 与
   `render_separated(result)` 两个方法，`Backend.register` 注册、`get_backend`
   查表。协议只要求「`ResolveResult` 进、`Outline` 出」，对内部实现零约束。
2. **`Outline` 共享结构**（`src/glyphsmith/outline.py`）：`[(x, y, off), …]`
   轮廓表，off=1 表示 off-curve（TrueType 惯例），负责 `to_path_d()` /
   `to_svg()` 与环绕规范化。两后端输出同一结构，故 `compare` /
   `scripts/smoke_full.py` / `batch` 对新后端开箱即用。
3. **`--backend` 全链路**：CLI `--backend legacy-kurgm|pen-minimal|both`、
   `Renderer(backend=…)`、`batch --backend` 均已就位，新增后端只需 register。
4. **`pen-minimal` 的证明**：ref 展开直接复用 legacy 的 `expand`（协议泛化性
   的第一个证据点），且它写回与 legacy 同款的 `result.warnings`
   （missing part / raw op 不因换后端而静默）。

v2 的新增工作全部落在 `pen/` 三模块内，不需要改动协议层——若需要改动，
说明协议设计有误，应先修协议。

## 三、v2 三模块

```
pen/
  graph.py   关系图（ARG 风格）：节点=笔画，边=meets/crosses/tee/parallel
             + 几何属性 → agent 可查询的中间产物
  style.py   风格文件加载（YAML）
  nib.py     笔模型：骨架 × w(t) 宽度剖面 × 端帽/装饰件 → 变宽偏移 → Outline
```

数据流（每一步都是可查询的中间产物，这是「agent 原生」的落点）：

```
GSF 骨架 ──expand──> 笔画序列 ──graph──> 关系图 ──style──> 风格规则求值
                                                              │
                              Outline <──nib（偏移+端帽+装饰）──┘
```

- **graph**：把「两笔相接/相交/成 T/平行」显式化。结字规则的输入是关系
  而不是像素——`when: {rel: meets, from: horizontal, to: vertical, at: head}`
  这类条件只有在图上才写得出来。参照 ARG（attributed relational graph）
  的联机汉字识别传统与 StrokeStrip 的笔画分组/tangency 判据。
- **style**：风格文件是**数据**而不是代码。同一份关系图喂不同风格文件得到
  不同书体；风格文件的 diff 可评审、可回归。
- **nib**：骨架 + 宽度剖面 + 端帽/装饰件 → 轮廓。等宽是 w(t)=const 的退化
  情形（pen-minimal 即此），变宽走平行曲线偏移。

## 四、风格文件语法草案（方向冻结，防 v2 漂移）

```yaml
# styles/serif-song.yaml
name: serif-song            # genre: serif；地区配方后缀：song/ming/mincho
width_profile:
  horizontal: {w0: 6,  w1: 6}
  vertical:   {w0: 14, w1: 12}
caps:
  horizontal-head: wedge    # uroko（鱗）= wedge serif
decorations:
  wedge: {shape: triangle, size: 1.4}
rules:                      # 声明式结字规则（作用于关系图）
  - when: {rel: meets, from: horizontal, to: vertical, at: head}
    then: {suppress: wedge}
```

三处设计意图，v2 不应偏离：

1. `width_profile` 按**笔画朝向**分档（横/竖各一组端点宽度），与书法实际
   相符（横细竖粗），也避免逐笔调参；
2. `caps`/`decorations` 用**词汇表里的词**（`wedge`、`hook`、`heel`…），
   不是数字码——风格文件的读者是人；
3. `rules` 作用于关系图，`when` 的条件是关系 + 朝向 + 端部位置，
   `then` 只允许抑制/替换/缩放已有装饰件（v2 明确不支持任意脚本）。

## 五、词汇决议

### 5.1 三层命名

| 层级 | 用词 | 例 |
|---|---|---|
| genre（字体大类） | 国际标准词 | `serif` / `sans` / `round` |
| 地区配方（后缀） | 地名 + 传统名 | `serif-song`（宋）、`serif-mincho`（明朝）、`sans-hei`（黑） |
| 细目（端部/装饰/端帽/连接） | 英语描述词 | `wedge` / `hook` / `heel` / `bend` / `cut` / `butt` / `miter` |

细目与 GSF v1 笔端枚举（`hook`、`heel-ll`…）对齐复用：同一个实物在数据层
（GSF）与风格层（pen）用同一个词，避免第二套译名。

### 5.2 术语对照（日 → 中 → 英）

KAGE 是日本项目，规则表术语全是日本字体工程行话。下表是 v2 词汇的出处，
只在文档首次出现处括注日语原词，代码与配置一律用英语描述词。

| 日语行话 | 中文 | 英语（本项目用词） | 说明 |
|---|---|---|---|
| うろこ uroko（鱗） | 三角衬线 | `wedge` | 拉丁字体学现成词（wedge serif），语义吻合 |
| 跳ね hane | 钩 | `hook` | GSF v1 已定 |
| 踵 kakato | 踵（底角出头） | `heel` | GSF v1 已定 |
| はらい harai | 撇捺出尖 | `tip` | GSF v1 已定 |
| 曲がり mage | 弯 | `bend` | 描述性 |
| 切り口 kirikuchi | 切头 | `cut` | 描述性 |
| とめ tome | 平收 | `flat` | GSF v1 已定 |
| 端帽族 | — | `butt` / `square` / `round` | SVG `stroke-linecap` + Levien 2024 |
| 连接族 | — | `bevel` / `miter` / `round` | SVG `stroke-linejoin` + Levien 2024 |

字体大类本身也有对照关系（`明朝体` = 中文「宋体/明體」= genre `serif`；
`ゴシック体` = 「黑体」= genre `sans`），软件内 genre 层一律合并为国际标准词，
宋/明/黑/圆之分留给配方参数层。

### 5.3 假朋友与陷阱

1. **Gothic**：日语 `ゴシック体` = 无衬线黑体；英语排版 Gothic = 黑字母体
   （blackletter）。软件内 genre 一律写 `sans`，`gothic` 只作别名进注册表。
2. **明朝/宋/明體**：三地兄弟名，不是三种字体；差异（字面率、假名配套等）
   属配方层。
3. **serif 的歧义**：CJK 语境说 serif 指「宋体类」整体，拉丁语境指字脚。
   涉及具体三角衬线时用 `wedge`，不用泛称。
4. **长音拼写**：`minchō` 在 ASCII 环境常写作 `mincho`——别名注册表两种都收。

别名注册表收日语罗马字（含长短音变体）与中文拼音，供检索与文献对读；
代码与配置不出现别名。

## 六、几何与学术依据

**(a) 描边 → 填充轮廓：Levien & Uguray「GPU-friendly Stroke Expansion」
（SIGGRAPH Asia 2024，arXiv:2405.00127 <https://arxiv.org/abs/2405.00127>）**
把「描边→填充」整理为**平行曲线 + join
（bevel/miter/round）+ cap（butt/square/round）** 的干净词汇，并区分：

- **弱正确**（weak correctness）：平行曲线 + 端帽 + 外连接，工程够用；
  `pen-minimal` 就在这一级（等宽、butt 端帽、逐段四边形、无布尔并集）；
- **强正确**（strong correctness）：连渐屈线（evolute）一起处理，只在曲率
  半径小于半宽时才需要。v2 的 nib 层要处理变宽，**必须**给出强/弱正确的
  明确取舍并在文档里写清楚哪一级。

**(b) 变宽 w(t) 的形式几何**：variable-radius offset curve 的三次贝塞尔逼近
（细分 + 法向偏移 + 误差控制）是可行工程路线；`nib` 的宽度剖面即以
分段常值/线性函数逼近 w(t)。

**(c) 参数化汉字的直系先例**：John Hobby《A Chinese Meta-Font》（TUGboat,
1984，<https://tug.org/TUGboat/tb05-2/tb10hobby.pdf>）用 Metafont 笔模型 +
参数化笔画例程做汉字，不同笔画例程吃不同字体参数——本节的管线在 42 年前已被
验证过一次。谱系：Knuth《The Concept of a Meta-Font》（1980）→ Hobby（1984）
→ 可变字体「风格=参数向量」→ CSS `stroke-linecap`/`stroke-linejoin`
（端帽/连接词汇的标准化）。

**(d) 关系图的历史与实践**：ARG（attributed relational graph）联机汉字识别
（IET 1996）与层级属性图（Pattern Recognition 1991）是「笔画=节点、关系=边」
的经典用法；StrokeStrip（2022，<https://www.davepagurek.com/programming/strokestrip/>）
给出笔画分组与 tangency/连接判据的现代实现；Berio et al.《StrokeStyles》
（ACM TOG 2022，<https://doi.org/10.1145/3505246>）证明「轮廓 ↔ 笔画」双向转换
+ 换风格是活跃方向。v2 的 graph 模块取前者的关系词汇、后者的分组判据。

## 七、明确不做（v2 非目标）

- **任意脚本的结字规则**：`rules.then` 只允许抑制/替换/缩放已有装饰件；
- **自动风格拟合**（从轮廓反推风格文件）——属远期「逆向造字」，不在 v2；
- **替代 legacy-kurgm**：pen 后端不接入 golden 对拍基线，两者是分工不是替代；
- 数据层、IDS 布局层、SFD/OTF 导出等 v1 明确的仓外项，同样不在 v2 初版。

## 八、v2 验收草案（写下来，防止「做完了但说不清做了什么」）

1. `styles/` 下至少一份 serif、一份 sans 风格文件，各自渲染同一份语料；
2. 同一骨架换风格文件，`compare` 的 IoU 显著变化，且变化方向与风格参数
   一致（如竖笔加粗 → 与基准的 IoU 下降但笔画覆盖面积上升）；
3. `graph` 的中间产物可由 CLI 导出为 JSON（agent 可查询）；
4. 变宽偏移给出强/弱正确的书面取舍，并对退化输入（零长笔画、共线控制点、
   曲率半径 < 半宽）不产生 NaN——沿用 v1 冒烟口径的 err=0 判据。
