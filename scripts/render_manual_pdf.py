"""Render a maintained Markdown manual to PDF, and CLI text captures to PNG.

Authoring tool only: requires `reportlab` and `Pillow`, which are not product
dependencies (`pip install reportlab pillow`). Supports the subset used by
docs/manuals: `#`/`##` headings, paragraphs, `- ` bullets, fenced code blocks,
inline code and images.

    python scripts/render_manual_pdf.py pdf docs/manuals/X/usage.md docs/manuals/X/usage.pdf
    python scripts/render_manual_pdf.py capture capture.txt docs/manuals/X/capture.png
"""
import re
import sys
from pathlib import Path

MONO_FONTS = ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/Library/Fonts/Courier New.ttf"]


def capture(text_path, png_path):
    from PIL import Image, ImageDraw, ImageFont
    lines = Path(text_path).read_text().rstrip("\n").splitlines()
    font = next((ImageFont.truetype(f, 22) for f in MONO_FONTS if Path(f).exists()), ImageFont.load_default())
    width = max(int(font.getlength(line)) for line in lines) + 60
    height = 34 * len(lines) + 50
    image = Image.new("RGB", (width, height), (30, 33, 39))
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        color = (152, 195, 121) if line.startswith("$") else (171, 178, 191)
        draw.text((30, 25 + 34 * i), line, font=font, fill=color)
    image.save(png_path)


def pdf(md_path, pdf_path):
    from PIL import Image as PILImage
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer

    base = Path(md_path).parent
    title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=14)
    h2 = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=14, leading=18, spaceBefore=10, spaceAfter=10)
    body = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=13, spaceAfter=8)
    bullet = ParagraphStyle("l", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=3)
    code = ParagraphStyle("c", fontName="Courier", fontSize=8, leading=10, leftIndent=8, spaceAfter=8,
                          backColor="#f2f2f2")

    def inline(text):
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
        return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    story, para, items, fence = [], [], [], None

    def flush():
        if para:
            story.append(Paragraph(inline(" ".join(para)), body))
            para.clear()
        for item in items:
            story.append(Paragraph(inline(item), bullet, bulletText="•"))
        items.clear()

    for line in Path(md_path).read_text().splitlines():
        if fence is not None:
            if line.startswith("```"):
                story.append(Preformatted("\n".join(fence), code))
                fence = None
            else:
                fence.append(line)
            continue
        if line.startswith("```"):
            flush()
            fence = []
        elif line.startswith("# "):
            flush()
            story.append(Paragraph(inline(line[2:]), title))
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(inline(line[3:]), h2))
        elif m := re.match(r"!\[[^\]]*\]\(([^)]+)\)", line):
            flush()
            path = base / m.group(1)
            w, h = PILImage.open(path).size
            width = A4[0] - 40 * mm
            story += [Spacer(1, 4), Image(str(path), width, width * h / w), Spacer(1, 6)]
        elif line.startswith("- "):
            if para:
                flush()
            items.append(line[2:].strip())
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()
        elif line.strip():
            if items:
                flush()
            para.append(line.strip())
        else:
            flush()
    flush()
    first = Path(md_path).read_text().splitlines()[0].lstrip("# ")
    SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                      bottomMargin=20 * mm, title=first, author="kis-hl-trading-system", invariant=1).build(story)


if __name__ == "__main__":
    command, source, target = sys.argv[1:4]
    {"pdf": pdf, "capture": capture}[command](source, target)
