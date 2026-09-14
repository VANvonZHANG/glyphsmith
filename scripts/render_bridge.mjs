// scripts/render_bridge.mjs —— stdin 读 JSON 行，stdout 出 TSV: name<TAB>fingerprint
import { createHash } from "node:crypto";
import { Kage, Polygons, KShotai } from "/home/zhangfan/Project/20260909_KAGE/repos/kage-engine/lib/esm/index.js";
import * as readline from "node:readline";

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
