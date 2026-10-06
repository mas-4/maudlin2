# Style book

How bignews.day looks and sounds, taken from the front page. Any new page should look like it belongs next to the front
page: loud, playful, full of emoji, and honest about what it knows. When in doubt, open `index.html` and copy what's
there.

The short version: **ink outlines, hard colored shadows, a little tilt, Bungee to shout, Comic Neue to talk, an emoji on
everything, and plain words.**

## Feel

- **Whimsy over polish.** Memphis-style 90s geometry drifts behind every page (`#memphis`, drawn by `index.js`).
  Things are a little crooked on purpose: stickers and banners tilt 1–5°, cards hop when you point at them.
- **Heavy use of emoji.** Every tracker, stage, button and empty state gets one. They are the site's icons; there is no
  icon font. Decorative emoji get `aria-hidden="true"` when the words beside them already say it.
- **Serious content, light frame.** The news is real and the measures are careful; the frame around them is fun. The
  whimsy never changes what a number says, and the words stay plain and exact.
- **Light only.** The site declares `color-scheme: light` and paints white behind everything.

## Type

| Use | Font | Notes |
|---|---|---|
| Shouting: section banners, kickers, the logo, big numbers on stickers | **Bungee** | uppercase by nature; short words only |
| Talking: card titles, buttons, labels, captions, chart text, "when" times, empty states | **Comic Neue** 700 | the accent voice; `'Comic Neue', 'Comic Sans MS', cursive` |
| Reading: body text, headline lists, long explanations | Helvetica / Arial | `#555` on white, line height 1.5 |

Both web fonts come from Google Fonts in `page.html` (`Bungee`, `Comic Neue:wght@700`). Don't add other fonts.

## Color

**Ink** `#1f1f2e` is the outline, shadow and text color for everything drawn: borders, banner text, chart outlines.

**Pops** (shadows, banners, sticker tints), in the order the front page's cards cycle through them:

| | Hex | Also used for |
|---|---|---|
| Pink | `#ff4fa3` | story pages' hero shadow, sagas (persistence) |
| Yellow | `#ffc400` | the "more" button shadow, kickers, checking |
| Teal | `#00c2a8` | section banners, spread, shows |
| Blue | `#3a86ff` | lean sticker |
| Orange | `#ff6b1a` | broadcast, peaks |
| Purple | `#8a5cff` | folklore, retelling, investigations |

The ambient shapes use their own set (`#1fc7b6`, `#ff3ea5`, `#8a5cff`, `#ffd21f`) at 75% opacity.

**Tints** for card and sticker backgrounds: `color-mix(in srgb, <pop> 10–25%, white)`. Banners use the pop at ~70%.

**Meaning colors** are fixed and never decorative:
- Lean: `graphing.bias_colors` (dark blue → grey → dark red, `#26357a` … `#7a0219`), with `bias_ink` for readable text
  on each. Unrated outlets are white with a dashed ink border; our own estimates are their lean color, dashed.
- TV channels: `page_tv.CHANNEL_INK` (CNN `#cc0000`, Fox `#003366`, MSNOW `#6a3fd1`, BBC `#b80000`).
- Links: `--color-hi` `#f56a6a`.

## Components

Copy these; don't invent near-copies.

- **Card** (`.story`, `.trending`, `.saga-card`): white or a light tint, `3px solid` ink border, `14px` radius, a hard
  shadow `6px 6px 0 <pop>` (no blur, ever). Hover: `translate(-2px, -2px)` and the shadow grows to 8px. Saga cards add
  a 10px left edge in their color.
- **Section banner** (`.section-divider`): a Bungee label in a tilted pill on a thick ink rule across the page. On story
  pages each stage gets its own color (`.stage-banner`, `--stage`) and a Comic Neue line under it (`.stage-sub`).
- **Sticker** (`.newsday-sticker`, `.story-stickers li`, `.story-kicker`): a small tilted card with a hard shadow, a big
  emoji, a Bungee number or word and a Comic Neue label. Alternate the tilt between neighbors.
- **Pill button** (`.more-link a`, the trend boxes' "show all"): ink border, 999px radius, Comic Neue 700, a yellow
  shadow; it hops on hover and presses in on click.
- **Chips**: outlet chips (`.edit-chip`, `chip_style()`) in lean colors with the outlet's icon; show chips
  (`.show-chip`, `--chip`) outlined in the source's color; quote and wording chips for phrases. Chips never break inside.
- **Wavy rule** under titles (`.story h4::after`, `.story-hero .story-page-title::after`): an SVG wave as a mask, in the
  card's pop color.
- **Paper backing** (`.table-intro`): text that sits straight on the page gets a white, 92% opaque rounded backing so
  the shapes behind it don't fight it.
- **Empty state** (`.stage-empty`): a dashed grey card in Comic Neue with an emoji and one honest, friendly line: what
  isn't there and why it might not be ("🦗 Nobody's retelling it online yet, as far as the daily report can tell").
- **Journey** (`.story-flow`): stops down a dashed road, each a little tinted card with a big emoji and a time.

## Emoji vocabulary

One emoji per thing, the same everywhere. Reuse these before picking a new one.

| | | | |
|---|---|---|---|
| 📰 front pages, outlets | 📡 wire copy, broadcast | 📺 TV | 📻 radio newscasts |
| 🎙️ shows, podcasts | 🕵️ investigations | 🃏 satire | 📌 aggregators |
| 💬 quotes | 🗣️ names, one-side wording | ✏️ headline edits | 📈 peaks, trends |
| 🧶 retold online (folklore) | 🧩 motifs | 🔎 fact-checks | 🧵 sagas |
| 🫏 left | 🐘 right | ⚖️ lean overall | ⏱️ how long |
| 🗞️ a story file | 👣 how it traveled | 🦗 / 🤷 / 🧐 / 🌱 empty states | 🔥 trending |

## Charts

- **Inline SVG drawn in Python** for anything on many pages (`app/site/story_charts.py`): no script, nothing to load,
  and hover titles for details. matplotlib PNGs only where a page already uses them (polling).
- Inside a white card with a 3px ink border, 10px radius and a hard pop shadow; labels in Comic Neue 700, 10–11px,
  ink or `#666`; grid lines a whisper (`#e6e6ee`).
- Lean always in the lean colors; channels in their channel ink; everything outlined thinly in ink.
- Times on axes in Eastern (`8 AM`, the day at midnight and on the first tick). Captions say exactly what is drawn,
  in a sentence, under the chart.
- On a phone a dense chart keeps a readable size and scrolls sideways inside its figure (`min-width` on the SVG,
  `overflow-x: auto` on the figure); the page itself never scrolls sideways.

## Words

- **Plain and exact.** Say what a number counts ("front pages at once, at its peak"), in sentence case, with ET on
  every time. No jargon on the public site; the methods page explains the machinery.
- **Honest about the tools.** Matched by our tools means a link can be wrong: say so where it matters, and say where a
  tracker might have missed something rather than implying it didn't happen.
- **Playful in the frame, not in the facts.** A joke can live in a banner, a kicker or an empty state, never in a
  headline, a claim or a measure.

## Code rules (so pages don't clash)

- **One CSS partial per page or component** in `app/site/styles/`, numbered; later files win at equal specificity.
  New pages take the next free number.
- **Prefix class names with the page** (`story-`, `tv-`, `radio-`, `saga-`, `folk-`). Before naming a class, grep the
  styles: on Oct 6 a story page bar reused `.tv-bar`, picked up the On TV page's rule and was stretched across the
  page.
- Reuse the shared components above by their existing classes rather than copying their rules.
- Respect `prefers-reduced-motion`: no drifting or popping for readers who ask for stillness.
- Check every new page at phone width (375px): no sideways page scroll, tap targets at least ~40px.
