// scripts/render_bridge.mjs —— stdin 读 JSON 行，stdout 出 TSV: name<TAB>fingerprint
//
// 引擎位置按序解析（不硬编码绝对路径；解析规则与 gsftool scripts/render_check.mjs 一致）：
//   1. 环境变量 KAGE_ENGINE —— kage-engine 的 ESM 入口，即 <kage-engine>/lib/esm/index.js
//   2. <repo>/node_modules/@kurgm/kage-engine/lib/esm/index.js（npm i @kurgm/kage-engine）
// 两处都不存在时，stderr 输出 JSON 错误并以退出码 2 结束（stdout 的 TSV 契约保持干净）。
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import * as readline from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ENGINE_CANDIDATES = [
  process.env.KAGE_ENGINE,
  resolve(HERE, "..", "node_modules", "@kurgm", "kage-engine", "lib", "esm", "index.js"),
].filter((p) => typeof p === "string" && p !== "");
const engine = ENGINE_CANDIDATES.find((p) => existsSync(p));

if (!engine) {
  console.error(JSON.stringify({
    error: "kage-engine not found",
    tried: ENGINE_CANDIDATES,
    hint: "set KAGE_ENGINE=<kage-engine>/lib/esm/index.js, or run "
        + "`npm install @kurgm/kage-engine` in the repository root",
  }, null, 2));
  process.exit(2);
}

const { Kage, Polygons, KShotai } = await import(pathToFileURL(engine).href);

const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const { name, data, shotai = "m", useCurve = false, buhin = null } = JSON.parse(line);
  const kage = new Kage();
  kage.kShotai = shotai === "m" ? KShotai.kMincho : KShotai.kGothic;
  kage.kUseCurve = useCurve;
  if (buhin) for (const [k, v] of Object.entries(buhin)) kage.kBuhin.push(k, v);
  let fp;
  try {
    const polygons = new Polygons();
    kage.makeGlyph2(polygons, data);
    const hash = createHash("sha1");
    let pc = 0;
    for (const poly of polygons.array) {
      hash.update("|");
      for (const p of poly.array) {
        hash.update(`${p.x},${p.y},${p.off ? 1 : 0};`);
        pc++;
      }
    }
    fp = `${polygons.array.length} ${pc} ${hash.digest("hex")}`;
  } catch {
    fp = "ERROR";
  }
  process.stdout.write(`${name}\t${fp}\n`);
});
