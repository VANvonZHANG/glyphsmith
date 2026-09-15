# gsrender

GSF 字形渲染器：agent 原生 CLI + Python 库。双后端：legacy-kurgm（忠实移植）
与 pen-minimal（等宽描边骨架预览，v2 pen 后端的接口占位）。

## 许可证与谱系（重要）

本项目按 **GPLv3** 发布。`src/gsrender/legacy_kurgm/` 是以下引擎算法的忠实
Python 移植，行为基准为 kurgm 版：

- **kurgm/kage-engine**（TypeScript，npm `@kurgm/kage-engine`）——移植基准
- **kamichikoichi/kage-engine**——原版引擎，笔画规则表
  `kagecd.js`（宋）/`kagedf.js`（黑）的最终出处
- **HowardZorn/kage-engine**——Python 移植先例（参考）
- **takushun-wu/kage-cpp**——环检测（CheckGlyph）思路回移植来源

由 GlyphWiki 数据渲染输出的字形不受 GPLv3 约束（GlyphWiki 数据自身为自由许可）。

## 安装

    pip install -e ../gsftool -e .     # gsftool 提供 gsf.kage2 解析

（本机 shell 若把 `gsr` 别名占用，如 `git svn rebase`，可用
`python -m gsrender.cli` 等价调用。）

## 用法（gsr CLI）

stdout 恒单行 JSON：`{"status","data","warnings","hints"}`；退出码
0 ok / 2 usage（含写盘失败、参数非法）/ 3 unknown glyph / 4 cycle。

    # 语料：GSF 文本文件或 GlyphWiki dump_newest_only.txt（自动识别）
    gsr render u4e2d --corpus data/dump_newest_only.txt            # stdout 出 SVG
    gsr render u4e2d --out png --corpus data/dump_newest_only.txt  # 写 u4e2d.png
    gsr render u4e2d --backend pen-minimal --font sans ...         # 双后端切换
    gsr resolve u4e2d --corpus ...          # ref 闭包 / 悬空引用 / 最深链
    gsr inspect u4e2d --corpus ...          # ops 计数（stroke/ref/raw）+ 名字 meta
    gsr list --like 'u6f2*' --corpus ...    # 名字前缀检索
    gsr sample --n 8 --seed 1 --corpus ...  # 可复现随机抽样
    gsr compare a b --corpus ...            # 栅格 IoU + 逐笔结构 diff
    gsr batch --out outdir --workers 8 --corpus data/dump_newest_only.txt
                                           # 整库批量渲染（multiprocessing）

字形名含 `/` 等路径分隔符时写盘名自动清洗（`a/b` → `a_b.png`）。批量口径：
单字形渲染异常或写盘失败计入 `errors` 不中断；`mkdir` 失败 → exit 2。

## 双后端

| 后端 | 定位 |
| --- | --- |
| `legacy-kurgm` | kurgm/kage-engine 忠实移植：golden 矩阵 7614/7614 指纹全等（宋/黑 × 直线/曲线 × 头尾型），真实 dump 1000 例与 Node 原版指纹全等 |
| `pen-minimal` | 等宽描边骨架预览（Levien 词汇最小子集），验证 Backend 协议的通用性；v2 变宽 pen 后端见 `docs/pen-backend-design.md` |

两者经同一 `Backend` 协议注册（`gsrender.protocol.get_backend`），CLI
`--backend` 与 `Renderer(backend=...)` 全链路可切换。

## 测试

    pytest                    # 全套（含 golden + cross，本机需 node + dump）
    pytest -m golden          # 只跑 golden 矩阵（7614 例，kurgm 逐指纹对拍）
    pytest -m "not cross"     # 跳过需要 node/dump 的交叉对拍

## 全量冒烟（M4 口径）

`scripts/smoke_full.py` 渲染整库 dump（222 万字形）只计数不写盘，验收
「零崩溃」：`err` 为单字形渲染异常计数（记录不中断），门槛 err=0。

两口径（数字都进报告）：

- **stroke-only**（默认）：parts 只含字形自身，ref 行不走闭包——纯 ref
  字形必然 empty，度量「渲染器对任意数据不崩溃」；
- `--closure`：`corpus.resolve(name)` 全闭包——度量「每个字形最终轮廓非空」。

    python scripts/smoke_full.py --limit 20000          # 确定性子集
    python scripts/smoke_full.py --workers 16           # 多进程版（数字与串行一致）
    python scripts/smoke_full.py --closure --workers 16 # 全闭包口径全量

全量基准（2,221,895 字形，legacy-kurgm/mincho）：stroke-only 串行 73s /
8 workers 15s（ok=166,694 empty=2,055,201 err=0）；closure 16 workers
142s（ok=2,221,552 empty=343 err=0）。

冒烟抓出并已修复的移植缺口（共 241 字形，204 例与 kurgm Node 指纹全等；
余 37 例闭包含 101:/102: 白名单缺口行——gsftool 解析侧已知限制，T12
口径披露排除，gsrender 修复范围外）：

- `push_polygon`：Python `math.floor(NaN)` 抛异常（27 字形）；
- self@N 历史快照自引用被 @版本兜底成假环（94 字形）；
- `stretch` 退化 box 除零 + `mincho_cd` 曲线体除零：IEEE-754 语义
  （0 除数 → ±Inf/NaN，120 字形）；
- box 聚合 min/max：JS `Math.min` 的 NaN 传染语义（84 字形多画）；
  与 `_round`/指纹 `js_num` 的 NaN/Infinity 穿透。

非自身引用 `X@N`（该版本行不在 newest dump）时，gsrender 回退渲染 newest X
并发 `version ref fallback` 警告（corpus.py），而 kurgm 的 kBuhin 为精确匹配、
查不到即静默跳过该部件——两侧长期存在的语义差异面。
