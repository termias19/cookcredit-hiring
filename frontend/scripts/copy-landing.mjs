import { cpSync, existsSync } from "node:fs";

/**
 * Copy the standalone marketing landing page into the build output.
 *
 * `landing/` is plain HTML/CSS with no bundling step, so it is neither a Vite input nor inside
 * `public/`. Vite empties `dist/` on every build, which means a `vite build` deletes `dist/landing/`
 * and the next `firebase deploy` takes https://cookcredit.com/landing/ offline — verified by
 * building to a scratch outDir and finding no `landing/` in it. Until now `dist/landing/` only
 * survived because nobody had rebuilt since it was hand-copied there.
 *
 * Kept as an explicit build step rather than moving the source into `public/` so the page stays
 * where it is edited.
 */
const from = "landing";
const to = "dist/landing";

if (!existsSync(from)) {
  throw new Error(`copy-landing: "${from}" not found — run this from frontend/.`);
}
cpSync(from, to, { recursive: true });
// eslint-disable-next-line no-console
console.log(`copied ${from} -> ${to}`);
