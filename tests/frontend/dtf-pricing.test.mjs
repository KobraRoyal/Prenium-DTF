import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../../backend/static_src/js/dtf-pricing.js", import.meta.url),
  "utf8",
);
const { estimateVolume } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
const config = {
  pricePerSqmCents: 2500,
  widthCm: 55,
  tiers: [
    { minimum: "25.0000", percent: "5.00" },
    { minimum: "50", percent: "8" },
    { minimum: "100", percent: "12" },
    { minimum: "250", percent: "15" },
  ],
};

test("Each threshold uses the new rate, and its preceding metre does not", () => {
  for (const [before, at, rate] of [
    [24, 25, 5],
    [49, 50, 8],
    [99, 100, 12],
    [249, 250, 15],
  ]) {
    assert.ok(estimateVolume(config, before).percent < rate);
    assert.equal(estimateVolume(config, at).percent, rate);
  }
});
test("Totals use the exact sqm price and laize before rounding", () => {
  const quote = estimateVolume(config, 25);
  assert.equal(quote.unitCents, 1306);
  assert.equal(quote.totalCents, 32656);
  assert.equal(quote.savingsCents, 1719);
  assert.notEqual(quote.totalCents, quote.unitCents * 25);
});
test("DB tiers can change independently of the frontend", () => {
  const db = {
    ...config,
    tiers: [
      { minimum: "5", percent: "10" },
      { minimum: "10", percent: "20" },
      { minimum: "25", percent: "25" },
    ],
  };
  assert.equal(estimateVolume(db, 10).unitCents, 1100);
  assert.equal(estimateVolume(db, 25).totalCents, 25781);
  assert.equal(estimateVolume(db, 25).percent, 25);
});
test("Missing tiers, decimal thresholds, and invalid or extreme inputs remain bounded", () => {
  assert.equal(estimateVolume({ ...config, tiers: [] }, 100).savingsCents, 0);
  assert.equal(
    estimateVolume(
      { ...config, tiers: [{ minimum: "2.5", percent: "2.25" }] },
      3,
    ).percent,
    2.25,
  );
  for (const value of [undefined, "bad", 0, -7])
    assert.equal(estimateVolume(config, value).volume, 1);
  assert.equal(estimateVolume(config, 9999).volume, 500);
});
