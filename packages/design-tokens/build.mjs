#!/usr/bin/env node
/**
 * Generates platform theme files from tokens.json:
 *   web/src/theme/tokens.js + tokens.d.ts + tokens.css   (React + Tailwind)
 *   mobile/src/theme/tokens.js + tokens.d.ts             (React Native + NativeWind)
 * `node build.mjs --check` fails if any generated file is out of date (used in CI).
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const tokens = JSON.parse(readFileSync(resolve(here, "tokens.json"), "utf8"));
const { $meta, contrast, ...theme } = tokens;

const HEADER = "// GENERATED from packages/design-tokens/tokens.json. Do not edit; run `npm run build` there.\n";

const js = `${HEADER}/* eslint-disable */\nmodule.exports = ${JSON.stringify(theme, null, 2)};\n`;
const dts = `${HEADER}declare const tokens: ${JSON.stringify(theme, null, 2)
  .replace(/"([^"]+)":/g, (_, k) => (/^[A-Za-z_$][\w$]*$/.test(k) ? `${k}:` : `"${k}":`))
  .replace(/: (".*?"|-?\d+(\.\d+)?)(,?)$/gm, ": $1$3")};\nexport = tokens;\n`;

function cssVars() {
  const lines = [];
  const walk = (obj, path) => {
    for (const [k, v] of Object.entries(obj)) {
      if (v && typeof v === "object" && !Array.isArray(v)) walk(v, [...path, k]);
      else if (typeof v === "string") lines.push(`  --hs-${[...path, k].join("-")}: ${v};`);
      else if (typeof v === "number" && path[0] !== "font") lines.push(`  --hs-${[...path, k].join("-")}: ${v}px;`);
    }
  };
  walk({ color: theme.color, space: theme.space, radius: theme.radius }, []);
  return `/* GENERATED from packages/design-tokens/tokens.json. Do not edit. */\n:root {\n${lines.join("\n")}\n}\n`;
}

const outputs = {
  "web/src/theme/tokens.js": js,
  "web/src/theme/tokens.d.ts": dts,
  "web/src/theme/tokens.css": cssVars(),
  "mobile/src/theme/tokens.js": js,
  "mobile/src/theme/tokens.d.ts": dts,
};

const check = process.argv.includes("--check");
let stale = [];
for (const [rel, content] of Object.entries(outputs)) {
  const file = resolve(root, rel);
  if (check) {
    if (!existsSync(file) || readFileSync(file, "utf8") !== content) stale.push(rel);
  } else {
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, content);
    console.log(`wrote ${rel}`);
  }
}
if (check && stale.length) {
  console.error(`Design tokens out of date: ${stale.join(", ")}\nRun: cd packages/design-tokens && npm run build`);
  process.exit(1);
}
if (check) console.log("Design tokens are in sync.");
