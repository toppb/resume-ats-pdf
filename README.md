# resume-ats-pdf

A Claude skill that turns a designed resume into an HTML file that prints to a clean, machine-readable one-page PDF, and verifies it before you send it.

**Want a one-click install?** [Get it on Agensi](https://www.agensi.io/skills/ats-resume-checker-figma-to-ats-friendly-pdf).

## What it does

**The problem.** Design tools write PDFs by placing glyphs at coordinates. Text
extractors then reconstruct words and reading order from geometry, and they frequently
get it wrong. The characteristic symptom is words splitting mid-token:

```
Led the rede sign of the onboar ding flow    ← "redesign", "onboarding"
hello @example.com                           ← email is now undeliverable
5 5 5 123 4 5 67                             ← phone is garbage
```

A fragmented email means every system that autofills from your PDF gets a dead address.
The failure is invisible to you, because the PDF looks perfect.

Most advice resolves this by telling designers to give up and use a Word template. That
isn't necessary.

**What this does.** Keeps your design tool as the source of truth, rebuilds the resume as
HTML, verifies the output automatically, and prints to PDF through Chrome — which writes
text that survives extraction.

## Install

```
/plugin marketplace add toppb/resume-ats-pdf
/plugin install resume-ats-pdf@resume-ats-pdf
```

## Use

Ask Claude to rebuild your resume for applications, or say your resume isn't parsing
properly. The skill triggers on its own.

To run the verifier directly:

```bash
pip install playwright pypdf pdfminer.six --break-system-packages
python3 -m playwright install chromium

python3 scripts/verify_resume.py resume.html --fonts ./fonts --expect 2,2,2,1,2,1
```

It renders the HTML headless, prints a PDF, extracts the text back out with two different
extractors (pypdf and pdfminer.six), and compares both against what the HTML actually
says. ATS parsers use different engines, so a check only passes if it passes in both.
Checks:

| Check | Catches |
|---|---|
| Word integrity | Character-level fragmentation (`rede sign`) |
| Contact details | A corrupted email or phone number |
| Reading order | Sections extracting out of sequence |
| Run-together fields | `2022Design Mentor` or `InstitutionSkills` — a missing space in the text stream |
| Orphan separators | A wrapped line starting with `·` |
| Page count + headroom | Silent overflow to a second page |
| Line counts | Blocks that wrap differently than your design file |
| Wrapped date cells | A date splitting across two lines |

Nothing is hardcoded to one resume — expectations are derived from the HTML itself.

`--fonts` points at a directory of font files named `Family-weight.woff2` (e.g.
`Inter-400.woff2`). Without it, the verifier relies on the CDN, and fails the font check
if the font can't load, rather than measuring a fallback.

## Contents

```
plugins/resume-ats-pdf/skills/figma-resume-to-ats-pdf/
├── SKILL.md                        workflow and guidance
├── scripts/verify_resume.py        the verifier
├── assets/resume-template.html     starting template, load-bearing rules commented
└── references/failure-modes.md     8 failure modes, causes, fixes, and dead ends
```

`references/failure-modes.md` is worth reading on its own if you're debugging a resume
PDF, whatever tooling you use.

## Notes

- **Chrome specifically.** Other browsers use different print engines.
- **Print settings matter.** Margins: None. Scale: 100%. Anything else adds margins on top
  of the page rule and causes extra line wraps.
- **This isn't a silver bullet.** Greenhouse, Ashby and Lever don't auto-reject on keyword
  scores — they parse into fields for a recruiter to search. This removes a failure mode.
  It doesn't fix a weak resume or a bad application channel.

## License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — free to use, share, and adapt for non-commercial purposes with credit. Reselling or relisting it is not permitted. See [LICENSE](LICENSE).

Versions published before October 20, 2026 were released under the MIT License.
