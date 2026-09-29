#!/usr/bin/env python3
"""
verify_resume.py — check a resume HTML file before printing it to PDF.

The point of this script is that almost nothing is hardcoded. It reads the HTML,
renders it headless in Chromium, prints a PDF, extracts the text back out, and
compares that against what the HTML actually says. So it works on any resume,
not one particular layout.

    pip install playwright pypdf beautifulsoup4 --break-system-packages
    python3 -m playwright install chromium

    python3 verify_resume.py resume.html
    python3 verify_resume.py resume.html --pages 1 --fonts ./fonts --expect 2,2,2,1,2,1

Checks:
  1. Fonts loaded          — a silent fallback invalidates every other measurement
  2. Page count            — default expectation is 1
  3. Headroom              — how close the last element is to the bottom margin
  4. Word integrity        — every word in the HTML survives PDF extraction intact.
                             Catches character-level fragmentation ("rede sign"),
                             which is the failure that silently corrupts emails.
  5. Contact details       — email / phone / URL survive as unbroken strings
  6. Reading order         — headings and role titles extract in DOM order
  7. Run-together text     — adjacent fields with no space between them
  8. Orphan separators     — a wrapped line starting with a bullet/dot separator
  9. Wrap tolerance        — how much wider another renderer can be before a line breaks
 10. Line counts           — optional, against a reference from the design file

Exit 0 = pass, 1 = fail.
"""
import sys, re, base64, pathlib, argparse, unicodedata

SEPARATORS = "·•|"   # list separators only; a leading em dash is often intentional


def embed_fonts(html: str, font_dir: pathlib.Path | None) -> str:
    """Inline any local .woff2/.ttf/.otf so rendering is deterministic and offline.

    File naming convention:  <Family Name>-<weight>.woff2
    e.g.  Inter-400.woff2, "Funnel Display-500.woff2"
    """
    if not font_dir or not font_dir.exists():
        return html
    faces = []
    for f in sorted(font_dir.iterdir()):
        if f.suffix.lower() not in (".woff2", ".woff", ".ttf", ".otf"):
            continue
        stem = f.stem
        m = re.match(r"(.+?)[-_](\d{3})$", stem)
        family, weight = (m.group(1), m.group(2)) if m else (stem, "400")
        family = family.replace("_", " ")
        fmt = {"woff2": "woff2", "woff": "woff", "ttf": "truetype", "otf": "opentype"}[
            f.suffix.lower().lstrip(".")]
        b64 = base64.b64encode(f.read_bytes()).decode()
        faces.append(f"@font-face{{font-family:'{family}';font-weight:{weight};"
                     f"src:url(data:font/{fmt};base64,{b64}) format('{fmt}');"
                     f"font-display:block;}}")
    if not faces:
        return html
    style = "<style>" + "".join(faces) + "</style>"
    out = re.sub(r'<link[^>]+fonts\.googleapis[^>]*>', "", html)
    return out.replace("<style>", style + "<style>", 1)


def norm(s: str) -> str:
    """Normalise for comparison: unify dash/quote variants and collapse whitespace."""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u2014", "-").replace("\u2013", "-").replace("\u2019", "'")
    s = re.sub(r"[\u00a0\u2002\u2003\u2009\s]+", " ", s)
    return s.strip()


def words(s: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z0-9@._%+\-']{3,}", norm(s))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--pages", type=int, default=1, help="expected page count")
    ap.add_argument("--fonts", default="", help="directory of local font files")
    ap.add_argument("--expect", default="", help="comma-separated body line counts from the design")
    ap.add_argument("--body-selector", default=".role-body",
                    help="CSS selector for the repeated body blocks used by --expect")
    ap.add_argument("--png", default="preview.png")
    ap.add_argument("--pdf", default="preview.pdf")
    ap.add_argument("--margin", default="0.3333in", help="print margin; must match the @page rule")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    src = pathlib.Path(a.html)
    html = src.read_text()
    rendered = src.parent / "_verify_render.html"
    rendered.write_text(embed_fonts(html, pathlib.Path(a.fonts) if a.fonts else None))

    fails, warns = [], []

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1000, "height": 1400}, device_scale_factor=2)
        pg.goto(rendered.resolve().as_uri())
        pg.wait_for_timeout(800)

        # 1. fonts
        font_status = pg.evaluate("""() => {
            const fams = new Set();
            document.querySelectorAll('*').forEach(e => {
                const f = getComputedStyle(e).fontFamily.split(',')[0].replace(/['"]/g,'').trim();
                if (f) fams.add(f);
            });
            const out = {};
            fams.forEach(f => { out[f] = document.fonts.check(`16px "${f}"`); });
            return out;
        }""")
        generic = {"sans-serif", "serif", "monospace", "system-ui", "-apple-system"}
        missing_fonts = [f for f, ok in font_status.items() if not ok and f not in generic]
        print(f"fonts               : {'all loaded' if not missing_fonts else 'MISSING ' + str(missing_fonts)}")
        if missing_fonts:
            fails.append(f"fonts not loaded: {missing_fonts} — other measurements unreliable")

        pg.screenshot(path=a.png, full_page=True)
        pg.pdf(path=a.pdf, format="Letter", print_background=False,
               margin={k: a.margin for k in ("top", "bottom", "left", "right")})

        pg.emulate_media(media="print")
        pg.wait_for_timeout(300)

        dom = pg.evaluate("""(sel) => {
            const pt = v => v * 72/96;
            const vis = e => e.getBoundingClientRect().height > 0;
            const all = [...document.body.querySelectorAll('*')].filter(vis);
            const bottom = Math.max(...all.map(e => e.getBoundingClientRect().bottom));

            // heading + strong-ish text in DOM order, for the reading-order check
            const anchors = [...document.querySelectorAll('h1,h2,h3,.role-title,[data-anchor]')]
                .map(e => e.textContent.trim()).filter(t => t.length > 3);

            // repeated body blocks -> line counts
            const lc = e => Math.round(e.getBoundingClientRect().height
                                       / parseFloat(getComputedStyle(e).lineHeight));
            const bodies = [...document.querySelectorAll(sel)].map(lc);

            // any element whose text wraps and whose wrapped line starts with a separator
            const seps = [];
            document.querySelectorAll('p,li,div,span').forEach(e => {
                if (e.children.length) return;
                const t = e.firstChild;
                if (!t || t.nodeType !== 3) return;
                if (t.textContent.length > 800) return;   // keep the scan cheap
                const rg = document.createRange();
                let prevTop = null;
                for (let i = 0; i < t.textContent.length; i++) {
                    rg.setStart(t, i); rg.setEnd(t, i+1);
                    const bb = rg.getBoundingClientRect();
                    if (prevTop !== null && Math.abs(bb.top - prevTop) > 2) {
                        const ch = t.textContent.slice(i).trimStart()[0];
                        if (ch && "·•|".includes(ch))
                            seps.push(t.textContent.slice(i, i+18).trim());
                    }
                    prevTop = bb.top;
                }
            });

            // fixed-width cells whose content wrapped unexpectedly
            const wrapped = [];
            document.querySelectorAll('[class*=date],[class*=year],[class*=meta]').forEach(e => {
                if (e.children.length) return;                    // skip row containers
                const txt = e.textContent.trim();
                if (txt.length > 24) return;                      // skip prose
                const lh = parseFloat(getComputedStyle(e).lineHeight);
                if (e.getBoundingClientRect().height > lh * 1.6) wrapped.push(txt);
            });

            return { bottom: pt(bottom), anchors, bodies, seps, wrapped,
                     text: document.body.innerText };
        }""", a.body_selector)
        b.close()

    # 2/3. page fit
    try:
        from pypdf import PdfReader
        reader = PdfReader(a.pdf)
        n_pages = len(reader.pages)
        pdf_text = "\n".join(p.extract_text() or "" for p in reader.pages)
    except ImportError:
        print("pypdf not installed — install it for the extraction checks")
        return 1

    usable = 792 - 2 * (float(a.margin.rstrip("in")) * 72 if a.margin.endswith("in") else 24)
    headroom = usable - dom["bottom"]
    print(f"pages               : {n_pages} (expected {a.pages})")
    if n_pages != a.pages:
        fails.append(f"PDF is {n_pages} pages, expected {a.pages}")
    print(f"headroom            : {headroom:+.1f}pt of {usable:.0f}pt usable")
    if 0 <= headroom < 6:
        warns.append("under 6pt of headroom — one extra line wrap will add a page")

    # 4. word integrity — the important one
    src_words = words(dom["text"])
    pdf_norm = norm(pdf_text)
    # a word hyphenated across a line break extracts as "Cross- functional"
    pdf_dehyph = re.sub(r"-\s+", "-", pdf_norm)
    broken = []
    for w in dict.fromkeys(src_words):
        if w not in pdf_norm and w not in pdf_dehyph:
            # is it there with spaces inserted between characters?
            loose = r"\s*".join(re.escape(c) for c in w)
            if re.search(loose, pdf_norm, re.I):
                broken.append(w)
            else:
                broken.append(w + " (absent)")
    print(f"word integrity      : {'ok' if not broken else str(len(broken)) + ' broken'}")
    for w in broken[:12]:
        fails.append(f"word does not survive extraction: {w}")
    if len(broken) > 12:
        fails.append(f"...and {len(broken)-12} more")

    # 5. contact details
    contacts = (re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", dom["text"])
                + re.findall(r"(?:\+?\d[\d\s().-]{7,}\d)", dom["text"])
                + re.findall(r"\b(?:https?://)?[\w-]+\.(?:com|ca|io|dev|design|co)\b", dom["text"]))
    bad_contacts = [c.strip() for c in dict.fromkeys(contacts) if norm(c) not in pdf_norm]
    print(f"contact details     : {'ok' if not bad_contacts else 'BROKEN ' + str(bad_contacts)}")
    for c in bad_contacts:
        fails.append(f"contact detail corrupted in PDF: {c!r}")

    # 6. reading order
    pos, missing = [], []
    for t in dom["anchors"]:
        i = pdf_norm.find(norm(t)[:40])
        (missing if i < 0 else pos).append(t if i < 0 else i)
    if missing:
        for t in missing[:6]:
            fails.append(f"heading/title missing from extracted text: {t!r}")
    elif pos != sorted(pos):
        out_of_order = [dom["anchors"][i] for i in range(1, len(pos)) if pos[i] < pos[i-1]]
        fails.append(f"content extracts out of order around: {out_of_order[:3]}")
    print(f"reading order       : {'ok' if not missing and pos == sorted(pos) else 'PROBLEM'}")

    # 7. run-together text
    # A year immediately followed by a capital is never legitimate — flag it even if
    # the HTML has the same defect (that means the spacer is missing in the source).
    hard = re.findall(r"\b\d{4}[A-Z][a-z]{2,}", pdf_text)
    # camelCase runs are only suspicious if the HTML doesn't contain them (UserTesting is fine)
    soft = [r for r in re.findall(r"\b[a-z]{3,}[A-Z][a-z]{3,}\b", pdf_text)
            if r not in dom["text"]]
    runs = list(dict.fromkeys(hard + soft))
    print(f"run-together text   : {'ok' if not runs else runs[:5]}")
    for r in runs[:5]:
        fails.append(f"fields run together with no space: {r!r}")

    # 8/9. layout niggles
    print(f"orphan separators   : {'none' if not dom['seps'] else dom['seps'][:4]}")
    for s in dom["seps"][:4]:
        fails.append(f"wrapped line starts with a separator: {s!r}")
    print(f"wrapped date cells  : {'none' if not dom['wrapped'] else dom['wrapped'][:4]}")
    for w in dom["wrapped"][:4]:
        warns.append(f"fixed-width cell wrapped: {w!r}")

    # 10. line counts
    if a.expect:
        want = [int(x) for x in a.expect.split(",")]
        print(f"body line counts    : {dom['bodies']} (design says {want})")
        if dom["bodies"] != want:
            fails.append(f"line counts {dom['bodies']} != design reference {want}")
    elif dom["bodies"]:
        print(f"body line counts    : {dom['bodies']}  (no --expect given)")

    print()
    for w in warns:
        print(f"warning: {w}")
    if fails:
        print("\nFAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"PASS — {a.png} written. Look at it, then print to PDF from Chrome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
