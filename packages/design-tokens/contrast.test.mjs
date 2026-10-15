import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tokens = JSON.parse(readFileSync(new URL("./tokens.json", import.meta.url), "utf8"));

function lookup(path) {
  const value = path.split(".").reduce((o, k) => o?.[k], tokens.color);
  assert.ok(typeof value === "string", `unknown colour token ${path}`);
  return value;
}

/** WCAG 2.1 relative luminance of a #RRGGBB colour. */
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function ratio(fg, bg) {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

test("luminance maths matches WCAG reference values", () => {
  assert.equal(ratio("#000000", "#FFFFFF").toFixed(1), "21.0");
  assert.equal(ratio("#777777", "#FFFFFF").toFixed(2), "4.48");
});

for (const { fg, bg, ratio: min, use } of tokens.contrast.pairs) {
  test(`${use}: ${fg} on ${bg} meets ${min}:1`, () => {
    const r = ratio(lookup(fg), lookup(bg));
    assert.ok(r >= min, `${fg} on ${bg} is ${r.toFixed(2)}:1, needs ${min}:1`);
  });
}

test("every colour is a valid hex", () => {
  const walk = (o, p) =>
    Object.entries(o).forEach(([k, v]) =>
      typeof v === "object" ? walk(v, `${p}.${k}`) : assert.match(v, /^#[0-9A-F]{6}([0-9A-F]{2})?$/i, `${p}.${k}`),
    );
  walk(tokens.color, "color");
});
