// scripts/render_bridge.mjs —— read JSON lines on stdin, write TSV: name<TAB>fingerprint
//
// The engine location is resolved in order (never hard-coded; the resolution rule
// matches gsftool scripts/render_check.mjs):
//   1. the KAGE_ENGINE environment variable — kage-engine's ESM entry, i.e.
//      <kage-engine>/lib/esm/index.js
//   2. <repo>/node_modules/@kurgm/kage-engine/lib/esm/index.js (npm i @kurgm/kage-engine)
// When neither exists, a JSON error goes to stderr and the process exits with code 2
// (keeping the stdout TSV contract clean).
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
