/**
 * Run the TypeScript unit tests under ui/tests/ with node:test.
 *
 * There is no test framework in this project's dependencies, and adding one
 * pulls in a large tree for a handful of pure-function tests. esbuild is
 * already here (Vite depends on it), so each test file is transpiled to a temp
 * ESM bundle and handed to Node's built-in test runner.
 *
 * Usage: npm test   (from ui/)
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const uiRoot = resolve(here, "..");
const testsDir = join(uiRoot, "tests");
const esbuild = join(uiRoot, "node_modules", ".bin", "esbuild");

const testFiles = readdirSync(testsDir).filter((f) => f.endsWith(".test.ts"));
if (testFiles.length === 0) {
  console.error("No *.test.ts files found in ui/tests/");
  process.exit(1);
}

const outDir = mkdtempSync(join(tmpdir(), "ui-tests-"));
try {
  const bundles = [];
  for (const file of testFiles) {
    const out = join(outDir, file.replace(/\.ts$/, ".mjs"));
    execFileSync(
      esbuild,
      [
        join(testsDir, file),
        "--bundle",
        "--platform=node",
        "--format=esm",
        "--target=node20",
        "--external:node:*",
        `--outfile=${out}`,
      ],
      { stdio: "inherit" },
    );
    bundles.push(out);
  }

  execFileSync(process.execPath, ["--test", ...bundles], { stdio: "inherit" });
} finally {
  rmSync(outDir, { recursive: true, force: true });
}
