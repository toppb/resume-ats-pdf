---
name: figma-resume-to-ats-pdf
description: Turn a designed resume (Figma, Sketch, InDesign, Canva) into an HTML file that prints to a clean, machine-readable one-page PDF, and verify the result before it's sent anywhere. Use this skill whenever a designer wants their resume to survive applicant tracking systems, says their resume "isn't getting read" or "gets rejected instantly", pastes text copied out of a resume PDF that looks garbled or out of order, asks whether their resume is ATS-friendly, asks how to export a resume so it parses correctly, or wants to keep a designed resume without giving up parseability. Also use it when someone is deciding between a designed PDF, a Word document, and a plain resume for job applications.
---

# Designed resume → parseable PDF

A designed resume has two jobs that pull against each other: look like the work of
someone who can design, and survive being read by software. Most advice resolves this
by telling designers to give up and use a Word template. That isn't necessary.

**The core problem is not layout — it's the export.** Design tools write PDFs by placing
glyphs at coordinates. Text extractors then have to reconstruct words and reading order
from geometry, and they frequently get it wrong. The characteristic symptom is words
splitting mid-token:

```
Led the rede sign of the onboar ding flow    ← "redesign", "onboarding"
hello @example.com                           ← email is now undeliverable
5 5 5 123 4 5 67                             ← phone is garbage
```

An email that fragments means every system that autofills from the PDF gets a dead
address. That failure is invisible to the person sending it — the PDF looks perfect.

The pipeline that fixes it: **design tool (source of truth) → HTML (build) → verify →
Chrome print-to-PDF (deliver).**

## Set expectations first

Before doing the work, be honest about what it buys. Greenhouse, Ashby, Lever and
similar systems do **not** auto-reject on a keyword score — they parse the file into
fields and let a recruiter search and filter. So "ATS-friendly" really means *parses
cleanly enough that a human sees complete information, and shows up in recruiter
searches*. The auto-rejection robot is mostly a myth.

This work removes a failure mode. It does not fix a weak resume or a bad channel. If
someone's cold applications aren't converting, a parseable PDF moves the needle a
little; referrals move it far more. Say so.

## Workflow

### 1. Read the design

Pull the current design — Figma MCP `get_design_context`, an export, or a screenshot.
Record: content, layout geometry (column widths, gaps, margins), the type scale, and
**the line count of each repeated body block**. That last one is the reference you'll
verify against, because line counts are where browser and design-tool rendering diverge.

### 2. Build the HTML

Start from `assets/resume-template.html`. Its comments mark which rules are load-bearing
and why. Read `references/failure-modes.md` before improvising — most of these bugs look
like sloppiness and are actually fixes.

Work in `pt`. A design drawn at 612×792px maps 1:1 onto pt on a Letter page.

**The one structural rule that matters most: work experience gets its own full-width
column, with nothing beside it.** Anything adjacent can be interleaved into it by a PDF
reader, which can truncate the employment history partway through. Secondary sections
(education, skills, tools) go below, where interleaving is cosmetic rather than costly.

### 3. Verify

```bash
pip install playwright pypdf --break-system-packages
python3 -m playwright install chromium

python3 scripts/verify_resume.py resume.html --fonts ./fonts --expect 2,2,2,1,2,1
```

It renders headless, prints a PDF, extracts the text back, and compares it against what
the HTML actually says. Checks: fonts loaded, page count, headroom, **every word survives
extraction intact**, contact details unbroken, reading order preserved, no run-together
fields, no orphaned separators, no wrapped date cells, and line counts against the design.

Nothing is hardcoded to one person's resume — expectations are derived from the HTML.

Two notes:
- `--fonts` should point at a directory of `.woff2`/`.ttf` files named
  `Family-weight.woff2` (e.g. `Inter-400.woff2`). Without it, webfonts loaded from a CDN
  can't be checked reliably and the font check will report a false pass.
- It writes `preview.png`. **Look at it.** Measurements miss visual problems; this is how
  you catch a date wrapping or a heading colliding.

Iterate until it passes. Don't hand over a file that hasn't.

### 4. Deliver

Give them the HTML plus the print settings, which are not optional:

> Chrome → Print → Save as PDF. **Margins: None. Scale: 100%.** Background graphics off.

Margins on "Default" adds the browser's margins on top of the `@page` margin, narrowing
the text column and causing extra line wraps. This is the first thing to check when
someone reports a layout that doesn't match. **Chrome specifically** — other browsers use
different print engines.

Then recommend keeping two artifacts, which is standard practice rather than a compromise:

| Version | Used for |
|---|---|
| Design-tool PDF | Portfolio site, direct email to a person |
| HTML-generated PDF | Application forms, any unknown system |

## When to recommend something else

If someone is sending a high volume of cold applications, a plain single-column **.docx**
is the most reliably parsed artifact that exists — there's no text-positioning layer to
reconstruct, because the document *is* structured text. It costs them their typography.
That trade is worth naming rather than deciding for them.

If they're mostly going through referrals, the designed PDF is fine and this whole
exercise is insurance.

## Content, not just format

If they're rebuilding anyway, the format is usually not why the resume isn't working.
Two things worth raising once:

- **Outcomes over scope.** "Led design for X" says they were assigned something. What
  changed because they were there? Most designed resumes are entirely scope statements.
- **Borrowed credit reads as none.** "Contributed to the acquisition" discounts to "was
  employed there" for any skeptical reader. Own a mechanism or leave it out.

Don't lecture. Raise it, then follow their lead.
