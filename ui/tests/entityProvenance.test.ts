/**
 * Provenance display rules.
 *
 * Three of these guard against a page stating more than the data supports: a
 * sentiment figure computed from posts nobody read, an event date borrowed
 * from when we happened to find it, and a vendor's own announcement counted
 * as somebody's opinion of them.
 *
 * Run with: npm test  (from ui/)
 */

import test from "node:test";
import assert from "node:assert/strict";

import {
  baselineDiffers, corroborationNote, eventDateLabel, isOwned, isSelfReported,
  provenanceLabel, splitMentions, statusNote,
} from "../src/components/newsfeed/entityProvenance";

test("a value is labelled with its source and the day it was read", () => {
  const label = provenanceLabel("linkedin_company_profile", "2026-08-14T09:00:00Z");
  assert.match(label, /LinkedIn company profile/);
  assert.match(label, /2026/);
});

test("an undated reading still names its source", () => {
  assert.equal(provenanceLabel("workbook", null), "imported workbook");
});

test("self-reported sources are identifiable", () => {
  assert.equal(isSelfReported("linkedin_jobs"), true);
  assert.equal(isSelfReported("vendor_web"), true);
  assert.equal(isSelfReported("crunchbase_company"), false);
});

test("a conflict says sources disagree rather than showing a bare colour", () => {
  assert.equal(statusNote("conflict", null).tone, "alert");
  assert.match(statusNote("conflict", null).text, /disagree/);
});

test("a stale field says when it was last read", () => {
  const note = statusNote("stale", "2026-06-01T00:00:00Z");
  assert.equal(note.tone, "warn");
  assert.match(note.text, /2026/);
});

// ---------------------------------------------------------------------------
// Baseline versus current
// ---------------------------------------------------------------------------

test("a newer reading beating the import is flagged as a difference", () => {
  assert.equal(baselineDiffers(122, 145), true);
});

test("a one-person drift is not a difference worth showing", () => {
  assert.equal(baselineDiffers(62, 63), false);
});

test("a missing value on either side is not a difference", () => {
  assert.equal(baselineDiffers(null, 145), false);
  assert.equal(baselineDiffers(122, null), false);
});

test("text differs or it does not", () => {
  assert.equal(baselineDiffers("Israel", "United States"), true);
  assert.equal(baselineDiffers("israel", " Israel "), false);
});

// ---------------------------------------------------------------------------
// Owned versus external
// ---------------------------------------------------------------------------

const ROWS = [
  { channel: "owned_social", total: 1209, unevaluated: 0, positive: 0,
    negative: 0, owned_claims: 1209 },
  { channel: "public_social", total: 10, unevaluated: 4, positive: 4,
    negative: 2, owned_claims: 0 },
  { channel: "earned_news", total: 15, unevaluated: 0, positive: 3,
    negative: 1, owned_claims: 0 },
];

test("a company's own posts are counted apart from what others said", () => {
  const split = splitMentions(ROWS);
  assert.equal(split.owned, 1209);
  assert.equal(split.external, 25);
});

test("sentiment is computed only over what was actually evaluated", () => {
  const split = splitMentions(ROWS);
  assert.equal(split.unevaluated, 4);
  assert.equal(split.denominator, 21);
  // (4 + 3 positive) - (2 + 1 negative) over 21 evaluated.
  assert.equal(split.netSentiment, 4 / 21);
});

test("no evaluated mentions gives unknown sentiment, not neutral", () => {
  const split = splitMentions([
    { channel: "public_social", total: 6, unevaluated: 6, positive: 0,
      negative: 0, owned_claims: 0 },
  ]);
  assert.equal(split.netSentiment, null);
  assert.equal(split.denominator, 0);
});

test("owned channels are recognised", () => {
  assert.equal(isOwned("owned_social"), true);
  assert.equal(isOwned("community"), false);
});

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

test("a vendor claim is shown as a claim", () => {
  const note = corroborationNote("vendor_claim", 0);
  assert.equal(note.tone, "warn");
  assert.match(note.text, /vendor says/);
});

test("independent confirmation reads differently and counts sources", () => {
  const note = corroborationNote("corroborated", 3);
  assert.equal(note.tone, "good");
  assert.match(note.text, /3 independent/);
});

test("an undated event says the source did not state a date", () => {
  assert.match(eventDateLabel(null, "unknown"), /not stated/);
  assert.match(eventDateLabel("2026-08-14T00:00:00Z", "unknown"), /not stated/);
});

test("a dated event shows its date", () => {
  assert.match(eventDateLabel("2026-08-14T00:00:00Z", "day"), /2026/);
});
