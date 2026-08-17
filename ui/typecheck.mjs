#!/usr/bin/env node
/**
 * Type-check the UI and fail only on errors that are new.
 *
 * This tree was exported from Figma and has never been type-checked, so it
 * starts with a few hundred pre-existing errors — most of them union-narrowing
 * complaints in App.tsx and PAMDashboard.tsx that work fine at runtime. Failing
 * on all of them would mean the check is switched off within a week. Instead
 * the known set is recorded in tsconfig.baseline.txt and only errors outside it
 * fail the run.
 *
 *   node typecheck.mjs            check; exit 1 if anything new appears
 *   node typecheck.mjs --update   rewrite the baseline from the current state
 *
 * Baseline entries drop the line and column numbers, so editing a file above an
 * existing error does not manufacture a false failure.
 */
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(fileURLToPath(import.meta.url));
const BASELINE = join(ROOT, 'tsconfig.baseline.txt');
const update = process.argv.includes('--update');

const tsc = spawnSync(
  join(ROOT, 'node_modules', '.bin', 'tsc'),
  ['--noEmit', '-p', join(ROOT, 'tsconfig.json')],
  { encoding: 'utf8', cwd: ROOT }
);

if (tsc.error) {
  console.error('Could not run tsc:', tsc.error.message);
  console.error('Run `npm install` in ui/ first.');
  process.exit(2);
}

const output = `${tsc.stdout || ''}${tsc.stderr || ''}`;

// "src/App.tsx(485,15): error TS2339: Property 'x' does not exist ..."
// -> "src/App.tsx: error TS2339: Property 'x' does not exist ..."
const ERROR_LINE = /^(\S+?)\((\d+),(\d+)\): (error TS\d+: .*)$/;
// tsc prints absolute paths inside some messages. Strip the checkout root so a
// baseline recorded here still matches in another tree.
const portable = (s) => s.split(ROOT + '/').join('');
const keys = [];
for (const line of output.split('\n')) {
  const m = line.match(ERROR_LINE);
  if (m) keys.push(`${m[1]}: ${portable(m[4])}`);
}

if (update) {
  writeFileSync(BASELINE, [...keys].sort().join('\n') + (keys.length ? '\n' : ''));
  console.log(`Baseline written: ${keys.length} known errors -> tsconfig.baseline.txt`);
  process.exit(0);
}

const baseline = existsSync(BASELINE)
  ? readFileSync(BASELINE, 'utf8').split('\n').filter(Boolean)
  : [];

// Count occurrences, so a second copy of an already-known error still fails.
const tally = (list) => list.reduce((m, k) => m.set(k, (m.get(k) || 0) + 1), new Map());
const now = tally(keys);
const known = tally(baseline);

const added = [];
for (const [key, count] of now) {
  const extra = count - (known.get(key) || 0);
  for (let i = 0; i < extra; i++) added.push(key);
}
let fixed = 0;
for (const [key, count] of known) fixed += Math.max(0, count - (now.get(key) || 0));

if (added.length) {
  console.error(`\n${added.length} new type error(s):\n`);
  // Print the full tsc lines for the new ones, so line numbers are visible.
  const wanted = new Set(added);
  for (const line of output.split('\n')) {
    const m = line.match(ERROR_LINE);
    if (m && wanted.has(`${m[1]}: ${portable(m[4])}`)) console.error('  ' + line);
  }
  console.error(
    `\n${keys.length} errors total, ${baseline.length} known. Fix the new ones, or run` +
    `\n  npm run typecheck:update\nif they are genuinely pre-existing.\n`
  );
  process.exit(1);
}

console.log(
  `Type check clean: ${keys.length} errors, all ${baseline.length} known` +
  (fixed ? `, ${fixed} baseline error(s) now fixed — run npm run typecheck:update to bank that` : '')
);
process.exit(0);
