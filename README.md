# gsrender

GSF 字形渲染器：agent 原生 CLI + Python 库。双后端：legacy-kurgm（忠实移植）
与 pen（变宽描边，v2）。

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

    pip install -e ../gsftool -e .
    pytest
