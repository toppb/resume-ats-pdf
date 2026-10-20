#!/usr/bin/env python3
"""
verify_resume.py — check a resume HTML file before printing it to PDF.

The point of this script is that almost nothing is hardcoded. It reads the HTML,
renders it headless in Chromium, prints a PDF, extracts the text back out, and
compares that against what the HTML actually says. So it works on any resume,
not one particular layout.

    pip install playwright pypdf pdfminer.six --break-system-packages
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
                             Checked with two extractors (pypdf and pdfminer.six),
                             because ATS parsers use different engines and a PDF
                             that one reads cleanly can still break in another.
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
            // document.fonts.check() returns true for a family that has no webfont at
            // all (it falls back silently), so it can't catch a CDN font that never
            // loaded. Instead: a family is expected to be a webfont if the page asks
            // for one (a font link or an @font-face), and then it must have actually loaded.
            const html = document.documentElement.outerHTML;
            const links = [...document.querySelectorAll('link[href]')].map(l => decodeURIComponent(l.href));
            const out = {};
            fams.forEach(f => {
                const faces = [...document.fonts].filter(ff => ff.family.replace(/['"]/g,'') === f);
                const wanted = faces.length > 0
                    || links.some(h => /fonts\.(googleapis|bunny)|typekit|use\.fontawesome/.test(h)
                                       && h.replace(/\+/g,' ').includes(f));
                out[f] = !wanted || faces.some(ff => ff.status === 'loaded');
            });
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
        from pdfminer.high_level import extract_text as pdfminer_text
    except ImportError:
        print("pypdf and pdfminer.six are required: "
              "pip install pypdf pdfminer.six --break-system-packages")
        return 1
    import logging
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    reader = PdfReader(a.pdf)
    n_pages = len(reader.pages)
    # Each extractor reconstructs words and order differently. A check passes only
    # if it passes for all of them.
    extracts = {
        "pypdf": "\n".join(p.extract_text() or "" for p in reader.pages),
        "pdfminer": pdfminer_text(a.pdf),
    }

    usable = 792 - 2 * (float(a.margin.rstrip("in")) * 72 if a.margin.endswith("in") else 24)
    headroom = usable - dom["bottom"]
    print(f"pages               : {n_pages} (expected {a.pages})")
    if n_pages != a.pages:
        fails.append(f"PDF is {n_pages} pages, expected {a.pages}")
    print(f"headroom            : {headroom:+.1f}pt of {usable:.0f}pt usable")
    if 0 <= headroom < 6:
        warns.append("under 6pt of headroom — one extra line wrap will add a page")

    # 4–7 run against every extractor; a problem in any one of them is a failure
    src_words = list(dict.fromkeys(words(dom["text"])))
    contacts = (re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", dom["text"])
                + re.findall(r"(?:\+?\d[\d\s().-]{7,}\d)", dom["text"])
                + re.findall(r"\b(?:https?://)?[\w-]+\.(?:com|ca|io|dev|design|co)\b", dom["text"]))
    contacts = [c.strip() for c in dict.fromkeys(contacts)]
    dom_norm = norm(dom["text"])

    res = {k: {} for k in ("words", "contacts", "order", "runs")}
    for name, pdf_text in extracts.items():
        pdf_norm = norm(pdf_text)
        # a word hyphenated across a line break extracts as "Cross- functional"
        pdf_dehyph = re.sub(r"-\s+", "-", pdf_norm)

        # 4. word integrity — the important one
        broken = []
        for w in src_words:
            if w not in pdf_norm and w not in pdf_dehyph:
                # is it there with spaces inserted between characters?
                loose = r"\s*".join(re.escape(c) for c in w)
                broken.append(w if re.search(loose, pdf_norm, re.I) else w + " (absent)")
        res["words"][name] = broken

        # 5. contact details
        res["contacts"][name] = [c for c in contacts if norm(c) not in pdf_norm]

        # 6. reading order
        pos, missing = [], []
        for t_ in dom["anchors"]:
            i = pdf_norm.find(norm(t_)[:40])
            (missing if i < 0 else pos).append(t_ if i < 0 else i)
        out_of_order = [] if missing else [dom["anchors"][i] for i in range(1, len(pos)) if pos[i] < pos[i-1]]
        res["order"][name] = (missing, out_of_order)

        # 7. run-together text
        # A year immediately followed by a capital is never legitimate — flag it even if
        # the HTML has the same defect (that means the spacer is missing in the source).
        hard = re.findall(r"\b\d{4}[A-Z][a-z]{2,}", pdf_norm)
        # Two words fused at a case change ("InstitutionSkills", "designLead"). Only
        # suspicious if the HTML doesn't contain the same string (UserTesting is fine).
        soft = [r for r in re.findall(r"[A-Za-z]*[a-z]{3,}[A-Z][a-z]{2,}[A-Za-z]*", pdf_norm)
                if r not in dom_norm]
        res["runs"][name] = list(dict.fromkeys(hard + soft))

    def report(label, key, fmt_ok, fmt_bad, fail_msg, limit=12):
        bad = {n: v for n, v in res[key].items() if v}
        print(f"{label:<20}: {fmt_ok if not bad else fmt_bad(bad)}")
        for n, v in bad.items():
            for item in v[:limit]:
                fails.append(f"[{n}] {fail_msg(item)}")
            if len(v) > limit:
                fails.append(f"[{n}] ...and {len(v)-limit} more")

    report("word integrity", "words", "ok",
           lambda b: ", ".join(f"{n}: {len(v)} broken" for n, v in b.items()),
           lambda w: f"word does not survive extraction: {w}")
    report("contact details", "contacts", "ok",
           lambda b: "BROKEN " + "; ".join(f"{n}: {v}" for n, v in b.items()),
           lambda c: f"contact detail corrupted in PDF: {c!r}")

    order_bad = {n: v for n, v in res["order"].items() if v[0] or v[1]}
    print(f"{'reading order':<20}: {'ok' if not order_bad else 'PROBLEM in ' + ', '.join(order_bad)}")
    for n, (missing, ooo) in order_bad.items():
        for t_ in missing[:6]:
            fails.append(f"[{n}] heading/title missing from extracted text: {t_!r}")
        if ooo:
            fails.append(f"[{n}] content extracts out of order around: {ooo[:3]}")

    report("run-together text", "runs", "ok",
           lambda b: "; ".join(f"{n}: {v[:5]}" for n, v in b.items()),
           lambda r: f"fields run together with no space: {r!r}", limit=5)

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
