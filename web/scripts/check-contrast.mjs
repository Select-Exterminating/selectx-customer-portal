// Fails when a theme token pair in src/app/globals.css drops below its WCAG 2.2 AA minimum.
// Text needs 4.5:1; UI component boundaries and focus indicators need 3:1.
// Tokens are read from the `:root` block, so this checks what actually ships.
import { readFile } from "node:fs/promises";

const TEXT = 4.5;
const UI = 3;

// [foreground token, background token, minimum, what it is]
const PAIRS = [
  ["foreground", "background", TEXT, "body text"],
  ["foreground", "muted", TEXT, "body text on the page grey"],
  ["foreground", "row", TEXT, "text on striped rows"],
  ["muted-foreground", "row", TEXT, "secondary text on striped rows"],
  ["primary", "row", TEXT, "links on striped rows"],
  ["foreground", "accent", TEXT, "text on hovered rows/menus"],
  ["card-foreground", "card", TEXT, "card text"],
  ["muted-foreground", "background", TEXT, "secondary text"],
  ["muted-foreground", "muted", TEXT, "secondary text on the page grey"],
  ["muted-foreground", "accent", TEXT, "secondary text on hover"],
  ["primary-foreground", "primary", TEXT, "primary button"],
  ["primary-foreground", "primary-hover", TEXT, "primary button hover"],
  ["primary", "background", TEXT, "green links and small green text"],
  ["secondary-foreground", "secondary", TEXT, "secondary button"],
  ["secondary-foreground", "secondary-hover", TEXT, "secondary button hover"],
  ["destructive", "background", TEXT, "error text"],
  ["destructive-foreground", "destructive", TEXT, "destructive button"],
  ["destructive", "destructive-muted", TEXT, "error badge/alert"],
  ["success", "success-muted", TEXT, "success badge"],
  ["pending", "pending-muted", TEXT, "pending (in progress) badge"],
  ["primary", "muted", TEXT, "green links and the active tab on the page grey"],
  ["primary-foreground", "chart-1", UI, "white marks on chart green"],
  ["muted-foreground", "background", TEXT, "inactive tab on white"],
  ["warning-foreground", "warning", TEXT, "warning badge"],
  ["foreground", "warning", TEXT, "text on highlighted rows"],
  ["primary", "warning", TEXT, "links on highlighted rows"],
  ["risk-critical-foreground", "risk-critical", TEXT, "critical risk chip"],
  ["risk-high-foreground", "risk-high", TEXT, "high risk chip"],
  ["risk-elevated-foreground", "risk-elevated", TEXT, "elevated risk chip"],
  ["risk-controlled-foreground", "risk-controlled", TEXT, "controlled risk chip"],
  ["highlight-foreground", "highlight", TEXT, "fill in the bright green"],
  ["background", "ink", TEXT, "white text on banners and statement bands"],
  ["ink-muted", "ink", TEXT, "secondary text on ink"],
  ["brand-green", "ink", TEXT, "eyebrows on ink"],
  ["highlight", "ink", TEXT, "emphasis on statement bands"],
  ["highlight", "ink-glow", TEXT, "emphasis on the band gradient"],
  ["ink-muted", "ink-glow", TEXT, "secondary text on the band gradient"],
  ["input", "background", UI, "form control border"],
  ["input", "muted", UI, "form control border on the page grey"],
  ["ring", "background", UI, "focus indicator"],
  ["ring", "muted", UI, "focus indicator on the page grey"],
];

function parseRoot(css) {
  const block = css.match(/:root\s*{([^}]*)}/);
  if (!block) throw new Error("No :root block found in globals.css");
  const tokens = {};
  for (const [, name, value] of block[1].matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    tokens[name] = value.trim();
  }
  return tokens;
}

function luminance(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`Expected a #rrggbb color, got ${hex}`);
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const css = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");
const tokens = parseRoot(css);
let failures = 0;
for (const [fg, bg, min, label] of PAIRS) {
  if (!(fg in tokens) || !(bg in tokens)) {
    console.error(`✗ missing token --${!(fg in tokens) ? fg : bg} (${label})`);
    failures++;
    continue;
  }
  const r = ratio(tokens[fg], tokens[bg]);
  const ok = r >= min;
  if (!ok) failures++;
  console.log(
    `${ok ? "✓" : "✗"} ${r.toFixed(2).padStart(5)}:1 ≥ ${min}  --${fg} on --${bg}  (${label})`,
  );
}
if (failures) {
  console.error(`\n${failures} contrast check(s) failed`);
  process.exit(1);
}
console.log("\nAll theme contrast checks passed");
