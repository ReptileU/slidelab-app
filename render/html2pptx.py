"""Свободная вёрстка → PPTX с редактируемым текстом + векторный PDF.

Каждый слайд — свой HTML 1920×1080 с любой композицией. Элементы с атрибутом data-t становятся
текстовыми полями PowerPoint на тех же местах (их можно править), всё остальное (фото, формы,
наложения, эффекты) — картинка-подложка слайда.

    python3 html2pptx.py decks/gta2        # slides/*.html → deck.pptx, deck.pdf, r/sNN.png, r/all.png
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

PX = 1920, 1080
EMU_PER_PX = 12192000 / 1920  # ширина слайда 13,333 дюйма
FACE = {500: " Medium", 600: " SemiBold", 800: " ExtraBold", 900: " Black"}

JS_COLLECT = """
() => [...document.querySelectorAll('[data-t]')].map(el => {
  const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
  return {text: el.innerText, x: r.left, y: r.top, w: r.width, h: r.height,
    family: cs.fontFamily.split(',')[0].replace(/["']/g,'').trim(), size: parseFloat(cs.fontSize),
    weight: parseInt(cs.fontWeight), color: cs.color, align: cs.textAlign, lh: cs.lineHeight,
    ls: cs.letterSpacing, upper: cs.textTransform === 'uppercase', italic: cs.fontStyle === 'italic',
    valign: el.dataset.valign || 'top', role: el.dataset.t || 'text'};
})
"""

JS_CHECK = """
() => { const bad = []; const els = [...document.querySelectorAll('[data-t]')];
  const R = els.map(el => { const r = document.createRange(); r.selectNodeContents(el);
    const b = r.getBoundingClientRect(); return {el, b}; });
  R.forEach(({el, b}) => {
    if (el.scrollWidth > el.clientWidth + 2) bad.push('не влезает по ширине: ' + el.innerText.slice(0, 40));
    if (b.right > 1920 - 16 || b.bottom > 1080 - 8 || b.left < 16 || b.top < 8) bad.push('у края: ' + el.innerText.slice(0, 40));
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 22 && el.dataset.t !== 'meta') bad.push('мелко ' + fs + 'px: ' + el.innerText.slice(0, 30));
  });
  for (let i = 0; i < R.length; i++) for (let j = i + 1; j < R.length; j++) {
    const a = R[i].b, c = R[j].b;
    const ox = Math.min(a.right, c.right) - Math.max(a.left, c.left), oy = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top);
    if (ox > 4 && oy > 4) bad.push('наезжают: «' + R[i].el.innerText.slice(0, 25) + '» и «' + R[j].el.innerText.slice(0, 25) + '»');
  }
  return bad; }
"""


def css_rgb(c: str) -> tuple[str, float]:
    nums = [float(v) for v in c[c.index("(") + 1 : c.index(")")].replace("/", ",").split(",")]
    alpha = nums[3] if len(nums) > 3 else 1.0
    return "".join(f"{int(v):02X}" for v in nums[:3]), alpha


def face(family: str, weight: int) -> tuple[str, bool]:
    if family in ("Press Start 2P",):
        return family, False
    if weight >= 650 and weight < 750:
        return family, True
    if weight < 450:
        return family, False
    return family + FACE.get(round(weight / 100) * 100, ""), False


def build(deck: Path) -> list[str]:
    slides = sorted((deck / "slides").glob("s*.html"))
    out = deck / "r"
    out.mkdir(exist_ok=True)
    issues: list[str] = []
    data = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": PX[0], "height": PX[1]}, device_scale_factor=1.5)
        for i, f in enumerate(slides, 1):
            page.goto(f.resolve().as_uri())
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(250)
            for bad in page.evaluate(JS_CHECK):
                issues.append(f"слайд {i}: {bad}")
            texts = page.evaluate(JS_COLLECT)
            notes = page.evaluate("document.body.dataset.notes || ''")
            page.screenshot(path=str(out / f"s{i:02d}.png"))
            page.pdf(path=str(out / f"p{i:02d}.pdf"), width="1920px", height="1080px", print_background=True)
            page.add_style_tag(content="[data-t]{visibility:hidden!important}")
            page.screenshot(path=str(out / f"bg{i:02d}.jpg"), type="jpeg", quality=90)
            data.append((texts, notes))
        b.close()
    subprocess.run(["pdfunite", *[str(out / f"p{i:02d}.pdf") for i in range(1, len(slides) + 1)], str(deck / "deck.pdf")],
                   check=True)

    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    for i, (texts, notes) in enumerate(data, 1):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.shapes.add_picture(str(out / f"bg{i:02d}.jpg"), 0, 0, prs.slide_width, prs.slide_height)
        for t in texts:
            if not t["text"].strip():
                continue
            pad = 6  # запас по ширине: PowerPoint переносит строки чуть раньше браузера
            box = s.shapes.add_textbox(Emu(int((t["x"] - 1) * EMU_PER_PX)), Emu(int(t["y"] * EMU_PER_PX)),
                                       Emu(int((t["w"] + pad) * EMU_PER_PX)), Emu(int(t["h"] * EMU_PER_PX)))
            tf = box.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = {"middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}.get(t["valign"], MSO_ANCHOR.TOP)
            name, bold = face(t["family"], t["weight"])
            col, alpha = css_rgb(t["color"])
            lh = t["lh"]
            spacing = float(lh[:-2]) / t["size"] if lh.endswith("px") else 1.2
            text = t["text"].upper() if t["upper"] else t["text"]
            for j, line in enumerate(text.split("\n")):
                para = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                para.alignment = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "end": PP_ALIGN.RIGHT}.get(
                    t["align"], PP_ALIGN.LEFT)
                para.line_spacing = round(spacing, 2)
                r = para.add_run()
                r.text = line
                r.font.size = Pt(t["size"] * 0.5)
                r.font.name = name
                r.font.bold = bold
                r.font.italic = t["italic"]
                r.font.color.rgb = RGBColor.from_string(col)
                if t["ls"] not in ("normal", "0px"):
                    r._r.get_or_add_rPr().set("spc", str(int(float(t["ls"][:-2]) * 50)))
        if notes:
            s.notes_slide.notes_text_frame.text = notes
    prs.save(deck / "deck.pptx")

    ims = [Image.open(out / f"s{i:02d}.png").convert("RGB").resize((640, 360)) for i in range(1, len(slides) + 1)]
    sheet = Image.new("RGB", (640 * 3 + 40, (360 + 20) * ((len(ims) + 2) // 3) + 20), "white")
    for k, im in enumerate(ims):
        sheet.paste(im, (10 + (k % 3) * 650, 10 + (k // 3) * 380))
    sheet.save(out / "all.png")
    return issues


if __name__ == "__main__":
    for line in build(Path(sys.argv[1])) or ["проверка пройдена"]:
        print(line)
