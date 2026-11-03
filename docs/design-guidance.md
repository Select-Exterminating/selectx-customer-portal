# Select Exterminating — Design Guidance

Pulled from the live site (selectexterminating.com) on Oct 21, 2026: colors sampled from the logo artwork and the site's computed CSS / Elementor global tokens, fonts and component styles read from the rendered page.

---

## 1. Core palette — Black, Green, Yellow

| Role | Name | Hex | RGB | Where it comes from |
|---|---|---|---|---|
| **Black** | Select Black | `#000000` | 0, 0, 0 | Logo wordmark, header overlays, footer |
| Black (UI) | Ink | `#171C1A` | 23, 28, 26 | Dark section backgrounds (a green-tinted near-black) |
| **Green** | Select Green | `#2B935C` | 43, 147, 92 | Primary CTA buttons, links, accents (Elementor global color) |
| Green (deep) | Forest | `#186839` | 24, 104, 57 | Hover / pressed states, small green text on white (Elementor global color) |
| Green (logo) | Logo Green | `#098543` | 9, 133, 67 | Logo shield / mark — use for brand marks, not UI |
| Green (icon) | Vivid Green | `#009868` | 0, 152, 104 | Favicon / app icon |
| **Yellow** | Select Gold | `#FDCF0E` | 253, 207, 14 | Most saturated yellow in the logo — highlights, badges, rules |
| Yellow (soft) | Honey | `#FED95A` | 254, 217, 90 | Average logo yellow — tints, gradient end |

## 2. Supporting neutrals

| Name | Hex | Use |
|---|---|---|
| Charcoal | `#353E43` | Secondary button ("Residential" toggle), dark UI chrome |
| Body Text | `#333333` | All paragraph text on light backgrounds |
| Graphite | `#1F2124` | Deep text / form labels |
| Stone | `#878B89` | Muted UI, dividers on dark |
| Mist | `#D9D9D9` | Borders, rules on light |
| Paper | `#F8F7F7` | Light section background (alternate with white) |
| White | `#FFFFFF` | Default page background, text on black/green |

## 3. Color rules

- **Proportion: ~60 / 30 / 10.** 60% white + black/ink (structure), 30% green (action and brand), 10% yellow (highlight only).
- **Green is the action color.** Every primary CTA ("GET A QUOTE TODAY") is Select Green with white text. Don't introduce a second CTA color.
- **Yellow is an accent, never a field.** Use it for underlines, rules, badges, stat numbers on black, or a single highlighted word. Never large yellow backgrounds behind body copy, and never yellow text on white (fails contrast).
- **Black carries authority.** Hero panels, statement sections, and the footer sit on black/Ink with white headlines.
- **Contrast checks (WCAG):**
  - White on Select Green `#2B935C` ≈ 3.9:1 → OK for buttons/large text (18px bold or 24px+); **not** for small body text.
  - White on Forest `#186839` ≈ 6.8:1 → use Forest when green carries small white text.
  - Forest on white ≈ 6.8:1 → use Forest (not Select Green) for small green links/text on white.
  - Select Gold on black ≈ 13:1 → excellent.
  - Black/Ink text on Select Gold → excellent; white text on yellow → never.

## 4. Typography

| Role | Typeface | Weight | Size (web) | Notes |
|---|---|---|---|---|
| Hero headline (H1) | **Oswald** | 700 | ~48–56px | ALL CAPS, white on black/photo |
| Section headline (H2) | **Oswald** | 700 | 25–36px | ALL CAPS, `#333333` on light |
| Card / feature title (H3) | **Oswald** | 700 | 22px | Title case OK |
| Body | **Lato** | 400 | 18px / 27px line-height (1.5) | `#333333` |
| Small / links | **Lato** | 400 | 14px | Green links |
| Buttons | System sans (or Lato) | 500 | 18px | See components |

Google Fonts: `https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;700&family=Lato:wght@400;700&display=swap`

Rules:
- Headlines are condensed, bold, and shouted: Oswald, uppercase, tight leading (~1.1).
- Body copy stays calm and readable: Lato regular at 18px, 1.5 line height.
- Don't mix in additional display faces. Two families only.

## 5. Components

**Primary button** — bg `#2B935C`, text `#FFFFFF`, 18px / 500, padding `10px 28px`, **border-radius 0** (square corners), uppercase label ("GET A QUOTE TODAY"). Hover: bg `#186839`.

**Secondary button** — bg `#353E43`, text white, same geometry. Used for toggles (Residential / Commercial).

**Text link** — `#2B935C` (or `#186839` on white for small text), Lato 14–18px, arrow suffix allowed ("Get Your Quote Today →").

**Industry / service tiles** — line icon (single color) + Oswald H3 title; grid of 5 across on desktop.

**Stat strip** — big Oswald numbers + small Lato labels: "70+ Years In Business · 9 Branches · 900+ Technicians". On black, numbers can go Select Gold.

**Corners** — square everywhere (buttons, cards). If a radius is needed, max 3px.

## 6. Layout

- Full-bleed photo heroes with a black overlay (`rgba(0,0,0,0.8)`) and white Oswald headline.
- Alternate section backgrounds: White → Paper `#F8F7F7` → Black/Ink statement band.
- Generous padding; centered content column; CTA repeated at top of page, mid-page and in the closing band.
- Photography: real technicians, facilities, warehouses — documentary, not stock-cute bugs.

## 7. Voice & messaging

- Confident, protective, established. Short declarative lines.
- Proof points to reuse: *since 1959*, *70+ years of family leadership*, *PCT Top 100 — 29th largest in the USA*, *largest family-owned pest control company in the Northeast*, *9 branches*, *900+ technicians*.
- Taglines in use: "We lead the Northeast in pest control" · "Big enough to back you, small enough to know you." · "We don't just service accounts. We engineer protection."
- Named programs carry ™: Select Sense™, The Select Assurance™.
- Contact: 800-311-6655.

## 8. Do / Don't

| Do | Don't |
|---|---|
| Green for every primary action | Yellow buttons or yellow body text |
| Oswald caps for headlines | Script, rounded or novelty fonts |
| Square corners | Pill buttons, big rounded cards |
| Black statement bands with gold highlights | Gradients across green→yellow as a background |
| Forest green for small text on white | Select Green small text on white (low contrast) |
| Real crew & facility photos | Cartoon bugs |

---

## 9. Application UI (customer portal)

Sections 1–8 describe the marketing site. The portal follows the RAMP portal's conventions (`../select-ramp-portal/public/index.html`), not those sections, where they differ: Arial, rounded corners, a green accent, and no gold. Tokens live in `web/src/app/globals.css`; `pnpm lint` runs `scripts/check-contrast.mjs`, which fails if any token pair drops below WCAG 2.2 AA.

**Color mapping (semantic tokens → values)**

| Token | Value | Why |
|---|---|---|
| `primary` | `#0F7D3F` (hover `#0B6432`) | The RAMP portal's `#108644` is 4.22:1 on the page grey, so small text and links use this slightly darker green. |
| `chart-1`, `risk-controlled` | `#108644` | The RAMP portal's green, for fills, rules, and charts. |
| `secondary` | Charcoal `#1A1A1A` (hover `#2C2C2C`) | Secondary buttons and table header rows. |
| `ink` | `#1A1A1A`, with `ink-glow` `#24372B` | The header banner and statement bands. |
| `ink-muted` | `#B9BDB7` | Secondary text on ink. |
| `highlight` | `#3FBF5F` | Emphasis on ink only. |
| `brand-green` | `#2F9E44` | Eyebrows and tile rules on ink only (3.45:1 on white). |
| `foreground` | `#1A1A1A` | |
| `muted` | `#F3F4F2` | App page background; cards are white. |
| `row` | `#F7F8F6` | Striped table rows. |
| `muted-foreground` | `#5E6461` | |
| `border` | `#E1E4E0` | Decorative dividers only. |
| `input` | `#858987` | Form-control borders need 3:1; the RAMP portal's hairline is 1.28:1. |
| `ring` | `#0F7D3F` | Focus indicator. |
| `destructive` | `#9E2B20` (tint `#F8E1DE`) | Errors and destructive actions. |
| `warning` | `#805C0C` text (`warning-foreground`) on tint `#FBF1DA` (`warning`) | Needs attention. |
| `success` | `#0F7D3F` on tint `#E7F1EB` | Status only. Never a filled green chip, so status can't be mistaken for a button. |
| `pending` | `#3F4442` on tint `#E4E7E3` | In-progress status (Open, Draft, Queued, Syncing). |
| `risk-*` | Critical `#C0392B`, High `#E07B24`, Elevated `#C9971C`, Controlled `#108644` | Risk and activity fills. High and Elevated take dark text: white fails AA on both. Each has a `-foreground` token. |

**Typography:** Arial throughout. Body is 14px (`text-sm`); tables, captions, and notes are 12px. Page titles (`h1`) are bold and uppercase; section headings are bold, as written; card titles are bold 15px.

**Case:** Title Case for tabs and card titles, with small words lowercase unless first or last (a, and, by, of, vs., and so on). Sentence case for buttons, labels, table headers, notes, and body text. Eyebrows are uppercase with wide tracking.

**Buttons:** primary and secondary are bold. Ghost, outline, and link actions are regular weight.

**Tabs:** `@/components/page-tabs`, not `components/ui/tabs` directly: shadcn's line style, a full-width rule under the list, inactive labels in `muted-foreground`, and the active tab bold green with a green underline.

**Tables:** `DataTable` and `DataTableFrame` from `@/components/data-table`: a sticky charcoal header row, striped rows, 12px tabular text. Don't style a table by hand.

**Stat tiles:** `StatTile` from `@/components/stat-tile` inside a `dl`: a 3px green top rule, a small label, a bold 28px value, and an optional note.

**Statement bands:** dashboard tabs open with `STATEMENT_BAND`: the ink gradient, a `brand-green` eyebrow, a bold headline with `highlight` emphasis, and `ink-muted` notes. Tiles on a band are translucent with a `brand-green` top rule.

**Badges:** one meaning per style, in a pill.
- State of a record or job: `pending` (in progress or waiting: Open, Draft, Queued, Syncing, Received), `success` (done: Worked, Final, Synced, Verified, Processed), `warning` (needs attention: Partly synced, Not verified, Inactive in PestPac, medium severity, a balance), `destructive` (failed, invalid, high severity).
- Finished history and plain labels: `outline` (Billed, Superseded, Inactive, Deleted; document type, category, On portal, revision, "You").
- Never `default` or `secondary` (filled green or charcoal): they're the button colours. Sync statuses also carry an icon, since they're scanned in passing. Store Watch's attention pills carry a dot.

**Shape:** `--radius: 0.375rem` (6px). Every component radius derives from it.

**Logo:** `web/public/brand/select-logo-white.png` (white lettering on transparency) goes on ink only. The header is an ink banner with a 4px green bottom rule (`chart-1`).

**Public pages:** the login and landing pages use the same banner and an ink statement band with a white headline and `highlight` proof-point numbers, next to the form.

**Co-branding:** the RAMP portal's Chipotle watermark and badge aren't used here: the app serves every customer.

**Favicon:** the site's own icons (`cropped-…-VIVID-GREEN` 32/180/192px from selectexterminating.com), installed as `web/src/app/icon1.png`, `icon2.png`, and `apple-icon.png`.

**Not yet defined:** a dark theme.
