# Failure modes

Every entry here was found by breaking something and watching the extracted text.
Read before "cleaning up" the template CSS — most of these fixes look arbitrary.

## Contents

1. Character-level fragmentation
2. Column interleaving and grouping
3. Fields running together
4. Line counts differing from the design
5. Orphaned separators and short trailing lines
6. Wrapped fixed-width cells
7. Misaligned hanging indents
8. Dead ends — do not retry

---

## 1. Character-level fragmentation

**Symptom:** `rede sign`, `categor y`, `Certi fication`, `hello @example.com`, `5 5 5 123`.

**Cause:** kerning pairs and ligatures are written as separate glyph-positioning
operations. Extractors insert a space wherever the horizontal offset crosses a threshold.

**Fix:** disable kerning and ligatures in CSS.

```css
font-kerning: none;
font-feature-settings: "kern" 0, "liga" 0;
text-rendering: optimizeSpeed;
```

**This does not fix design-tool exports.** Tested across three typefaces (including
Helvetica, which barely kerns) and two layouts — a Figma PDF fragments regardless. The
defect is in the export path, not the font. Removing letter-spacing doesn't help either;
it just changes which pairs cross the threshold.

Side benefit: killing ligatures stops `fi` splitting "Certification".

---

## 2. Column interleaving and grouping

**Symptom A (interleaving):** sections read across the page instead of down —
`Work Experience Education`, then a role, then a degree.

**Symptom B (grouping):** every date collects together, away from its label —
`2021 2019 2018 2016 Youth in Tech Mentor…`

**Cause:** the extractor reconstructs order from coordinates. Side-by-side content is
ambiguous, and different readers resolve it differently. A fixed-width cell beside text
reads as its own column.

**Fixes:**
- Work experience gets a full-width column with nothing beside it. This is the one that
  matters — interleaving *into* the employment history can truncate it.
- Make date/label rows a single inline flow, not a two-column flex.
- Accept that secondary sections may still group. See dead ends.

---

## 3. Fields running together

**Symptom:** `Mar 2024—PresentSenior Product Designer`, `2022Design Mentor`.

**Cause:** flexbox strips whitespace between flex items, so no space character exists in
the text stream — the visual gap is layout, not text.

**Fix:** put a real character in the markup — `&nbsp;` at the end of the date span, or
em/en spaces (`&#8195;&#8194;`) between year and label.

This matters more than it looks: the date/title boundary is exactly the field a résumé
parser most wants to split.

---

## 4. Line counts differing from the design

**Symptom:** a block that's 2 lines in Figma renders as 3 in the browser, pushing the
document to two pages.

**Cause:** browsers set type slightly wider than design tools, and disabling kerning
widens it further.

**Fix:** tighten `letter-spacing` in 0.1pt steps before reducing font size. A hundredth
of an em is invisible and usually enough.

**Check the tolerance, not just the current state.** A block can be correct and have
*zero* margin — widening by 0.05pt/char flips it. Test by adding positive letter-spacing
until it breaks; if it breaks immediately, apply negative tracking to buy slack, because
someone else's renderer will differ from yours.

---

## 5. Orphaned separators and short trailing lines

**Symptom A:** a wrapped line begins with `·`.
**Fix:** bind each separator to the word before it — `word&nbsp;&middot; word`.

**Symptom B:** a body block whose last line is one short word, and that word gets hoisted
elsewhere in the extracted text.
**Fix:** `text-wrap: pretty` helps but doesn't guarantee. Editing the sentence so it
doesn't end on a lone short word is the reliable fix.

---

## 6. Wrapped fixed-width cells

**Symptom:** `Sep 2019—Nov / 2022` — a date splits across two lines.

**Cause:** the column was sized for a typical string, not the longest one. Adding a
trailing `&nbsp;` (see §3) makes the content wider than it looks.

**Fix:** size to the longest string and add `white-space: nowrap`.

---

## 7. Misaligned hanging indents

**Symptom:** a wrapped label doesn't line up under the first line.

**Cause:** the leading space added for extraction (§3) indents only the first line.

**Fixes, in order of preference:**
- Single inline flow with `padding-left` + negative `text-indent`, tuned to where the
  first line's text *actually* starts. Measure it; don't calculate it.
- Or keep the flex layout and cancel the indent with `text-indent: -0.278em` on the
  label — exactly one space width.

---

## 8. Dead ends — do not retry

**Hanging indent with an `inline-block` year.** Renders correctly and silently drops the
years from the extracted text entirely. Fails invisibly, which makes it worse than an
obvious bug.

**Chasing column grouping in secondary sections.** Chrome's print engine emits **every
glyph as its own positioned drawing operation** — inspect the content stream and you'll
see `<0030> Tj  13 0 Td <0060> Tj …`. There are no text runs, so reading order is not
stored in the file at all; each reader reconstructs it from coordinates. No HTML
structure changes this. The only real fix is a fully single-column layout, which usually
doesn't fit. Leave it: it affects sections no parser maps to a structured field.

**Trusting one extractor.** `pypdf` read a lower section correctly while the user's
reader grouped it — same file, different heuristics. If someone reports a problem your
script says isn't there, believe them and check with a second tool.

**Fixing it in the design tool.** Every combination of font and layout tested still
fragmented. Don't spend another afternoon on it.

---

## Diagnostic method

The paste test is the ground truth, and it takes ten seconds: open the PDF, select all,
copy, paste into a plain text editor. What you see is roughly what a parser sees.

When a fix doesn't work, inspect the PDF content stream before trying another one. It
tells you whether you're fighting the markup or the renderer — and in most of these
cases, it's the renderer.
