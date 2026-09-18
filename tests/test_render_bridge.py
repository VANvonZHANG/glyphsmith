# tests/test_render_bridge.py
"""scripts/render_bridge.mjs 的降级契约（改名任务遗留：此前只手工验证过）。

桥接脚本按序解析引擎位置（KAGE_ENGINE → <repo>/node_modules/...，解析规则与
gsftool scripts/render_check.mjs 一致）。两处都没有时必须：stderr 输出 JSON
错误、退出码 2、stdout 保持干净（TSV 契约不得被污染）——交叉对拍的调用方
（tests/test_cross_engine.py）依赖这个退出码语义来区分「引擎缺失」与「渲染差异」。

本测试只需要 node 可执行文件，不需要 kage-engine：把脚本复制到 tmp 下，
node_modules 候选即解析到 tmp/node_modules（不存在），再用 KAGE_ENGINE 指向
一个不存在的路径把另一候选也堵死。test_cross_engine.py 的模块级 skipif 要求
引擎在场，无法覆盖这一分支，故独立成文件（写法参照 gsftool
tests/test_render_golden.py::test_missing_engine_reports_error_and_exits_2）。
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node executable not available")


@needs_node
def test_missing_engine_reports_json_error_and_exits_2(tmp_path):
    assert NODE is not None  # skipif 已保证；收窄类型使 subprocess.run 拿到 list[str]
    script = tmp_path / "render_bridge.mjs"
    shutil.copy(REPO / "scripts" / "render_bridge.mjs", script)
    env = {**os.environ, "KAGE_ENGINE": str(tmp_path / "no-such-engine.js")}
    r = subprocess.run([NODE, str(script)], input='{"name":"g","data":"1:0:0:10:10:100:60"}\n',
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 2, r.stderr
    payload = json.loads(r.stderr)          # stderr 必须是可解析的 JSON（非 traceback）
    assert payload["error"] == "kage-engine not found"
    assert str(tmp_path / "no-such-engine.js") in payload["tried"]
    assert "KAGE_ENGINE" in payload["hint"]
    assert r.stdout == ""                   # TSV 契约保持干净：不吐半行


@needs_node
def test_engine_candidate_order_prefers_kage_engine_env(tmp_path):
    # 解析顺序契约：KAGE_ENGINE 优先于 node_modules 候选——用一个只导出空对象的
    # 假引擎证明「env 指向者才是被 import 的那个」（缺失即上面的 exit 2 分支）。
    assert NODE is not None
    script = tmp_path / "render_bridge.mjs"
    shutil.copy(REPO / "scripts" / "render_bridge.mjs", script)
    fake = tmp_path / "fake-engine.mjs"
    fake.write_text("export const Kage = class {};\nexport const Polygons = class {};\n"
                    "export const KShotai = { kMincho: 0, kGothic: 1 };\n", encoding="utf-8")
    env = {**os.environ, "KAGE_ENGINE": str(fake)}
    r = subprocess.run([NODE, str(script)], input="", capture_output=True,
                       text=True, timeout=60, env=env)
    # 假引擎可 import（不是 exit 2 的「找不到」），空输入下正常收尾
    assert r.returncode == 0, r.stderr
    assert "kage-engine not found" not in r.stderr
