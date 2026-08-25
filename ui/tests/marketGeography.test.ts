/**
 * Vendor map scaling and labelling.
 *
 * A map is a persuasive object, so the tests here are about the two ways this
 * one could persuade someone of something untrue: exaggerating a difference
 * through circle size, and drawing "nobody published a figure" as though it
 * meant "there is no money here".
 *
 * Run with: npm test  (from ui/)
 */

import test from "node:test";
import assert from "node:assert/strict";

import {
  centroid, colorFor, formatMusd, fundingCaveat, isUndisclosed, maxValue,
  radiusFor, unplaceable, valueFor, UNDISCLOSED_COLOR,
  type CountryRow,
} from "../src/components/newsfeed/map/marketGeography";

function row(over: Partial<CountryRow> = {}): CountryRow {
  return {
    country: "United States", vendors: 53, vendors_with_amount: 31,
    not_disclosed: 22, status_unknown: 0, total_musd: 949.8,
    largest_musd: 105, funding_coverage: 31 / 53, staff: 4000, ...over,
  };
}

const INDIA = row({
  country: "India", vendors: 5, vendors_with_amount: 0, not_disclosed: 5,
  total_musd: null, largest_musd: null, funding_coverage: 0, staff: null,
});

// ---------------------------------------------------------------------------
// Scale
// ---------------------------------------------------------------------------

test("circle area, not radius, carries the count", () => {
  // 53 vendors against 5. By radius that would be ~11x wider and ~120x the
  // area, which is what the eye reads.
  const big = radiusFor(53, 53);
  const small = radiusFor(5, 53);
  const ratio = (big - 8) / (small - 8);      // discount the minimum radius
  assert.ok(ratio > 3 && ratio < 3.7,
    `expected roughly sqrt(53/5)≈3.3, got ${ratio.toFixed(2)}`);
});

test("a country with no figure still gets a visible circle", () => {
  // Vanishing would read as "no vendors here", the opposite of the truth.
  assert.equal(radiusFor(null, 949.8), 8);
});

test("scaling is safe when everything is zero or missing", () => {
  assert.equal(radiusFor(0, 0), 8);
  assert.equal(radiusFor(10, 0), 8);
});

test("the largest value sets the top of the scale", () => {
  const rows = [row(), INDIA];
  assert.equal(maxValue(rows, "concentration"), 53);
  assert.equal(maxValue(rows, "funding"), 949.8);
});

// ---------------------------------------------------------------------------
// Undisclosed is not zero
// ---------------------------------------------------------------------------

test("no disclosed amount is undisclosed on the funding overlay", () => {
  assert.equal(isUndisclosed(INDIA, "funding"), true);
});

test("the same country is not undisclosed when counting vendors", () => {
  // It has five vendors. That number is known and complete.
  assert.equal(isUndisclosed(INDIA, "concentration"), false);
  assert.equal(valueFor(INDIA, "concentration"), 5);
});

test("undisclosed gets its own colour, not the bottom of the ramp", () => {
  const faintest = colorFor(row({ total_musd: 1 }), "funding", 949.8);
  assert.equal(colorFor(INDIA, "funding", 949.8), UNDISCLOSED_COLOR);
  assert.notEqual(colorFor(INDIA, "funding", 949.8), faintest);
});

test("an undisclosed total never formats as a number", () => {
  assert.equal(formatMusd(null), "not disclosed");
  assert.equal(formatMusd(949.8), "$950m");
  assert.equal(formatMusd(3.3), "$3.3m");
  assert.equal(formatMusd(1200), "$1.2bn");
});

// ---------------------------------------------------------------------------
// Every figure states what it covers
// ---------------------------------------------------------------------------

test("a total names its denominator", () => {
  const caveat = fundingCaveat(row());
  assert.match(caveat, /31 of 53/);
  assert.match(caveat, /22 undisclosed/);
});

test("a country with nothing disclosed says so in words", () => {
  assert.match(fundingCaveat(INDIA), /None of the 5/);
});

test("the singular case reads properly", () => {
  const one = row({ country: "Turkey", vendors: 1, vendors_with_amount: 0,
                    not_disclosed: 1, total_musd: null });
  assert.match(fundingCaveat(one), /The one vendor/);
});

// ---------------------------------------------------------------------------
// Nothing is dropped silently
// ---------------------------------------------------------------------------

test("every country in the current data can be placed", () => {
  for (const country of ["United States", "Israel", "United Kingdom", "India",
                         "France", "Spain", "Italy", "Netherlands", "Romania",
                         "Turkey", "Saudi Arabia", "United Arab Emirates",
                         "Bahrain", "Australia"]) {
    assert.ok(centroid(country), `no centroid for ${country}`);
  }
});

test("a country we cannot place is reported rather than dropped", () => {
  const rows = [row(), row({ country: "Atlantis", vendors: 2 })];
  const missing = unplaceable(rows);
  assert.equal(missing.length, 1);
  assert.equal(missing[0].country, "Atlantis");
});
