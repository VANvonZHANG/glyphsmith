# pen 后端设计（v2 预留，v1 锁接口）

> 摘自父研究仓库的设计规格 §4.2（该设计文档不随本仓分发）。
> v1 的交付物只有 pen-minimal 预览后端（`src/glyphsmith/pen_minimal.py`：等宽
> 描边 + butt 端帽，逐段四边形，nonzero 并集即 Levien「弱正确」级）——它证明
> Backend 协议不是 legacy 专属形状；graph/style/nib 三模块与风格文件引擎
> 均为 v2 范围（设计 §8「明确不做」）。

## 三模块职责

```
pen/
  graph.py   关系图（ARG 风格）：节点=笔画，边=meets/crosses/tee/parallel
             + 几何属性 → agent 可查询的中间产物
  style.py   风格文件加载（YAML）
  nib.py     笔模型：骨架 × w(t) 宽度剖面 × 端帽/装饰件 → 变宽偏移 → Outline
```

## 风格文件语法草案（方向冻结，防 v2 漂移）

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

## 词汇决议

词汇规范：genre 用国际标准（`serif`/`sans`/`round`）；细目用英语描述词
（wedge/hook/heel/bend/cut），与 GSF v1 笔端枚举（hook、heel-ll…）对齐复用；
端帽/连接沿用 SVG+Levien 词汇；日语行话与拼音进别名注册表。

三语对照决议（日中英书法字体术语 ↔ GSF 枚举 ↔ v2 词汇）见父仓库笔记 15：
[`../15-书法字体术语三语对照.md`](../15-书法字体术语三语对照.md)
（路径相对 glyphsmith 仓库根目录）。

## v1 三件预留

① Backend 协议 + Outline 共享结构（legacy 是第一个实现者，协议合身与否立见）
② `--backend` 参数全链路就位 ③ stretch：`pen-minimal`（等宽描边 + butt/round
端帽，Levien 词汇最小子集，无结字规则无风格文件）——证明协议非 legacy 专属
形状，兼作 agent 快速预览工具。

v1 已落地 ①②③：pen-minimal 端帽词汇目前仅 butt（round 端帽属 v2 nib 层），
等宽 `WIDTH = 8.0`；ref 展开直接复用 legacy 的 `expand`（协议泛化性的证明点）。
