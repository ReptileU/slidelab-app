"""SlideLab engine (прототип): deck.json → редактируемый PPTX + PDF + отчёт проверки.

Макет выбирается по смыслу слайда. Текст подгоняется по реальным метрикам шрифта:
если не влезает даже на минимальном кегле — слайд попадает в отчёт как ошибка.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

W, H = 13.333, 7.5  # дюймы, 16:9
LINE_K = 1.22  # высота строки Montserrat/Unbounded относительно кегля
M = 0.8  # поля
FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILES = {
    ("Montserrat", 400): "Montserrat-Regular.ttf",
    ("Montserrat", 500): "Montserrat-Medium.ttf",
    ("Montserrat", 700): "Montserrat-Bold.ttf",
    ("Montserrat", 800): "Montserrat-ExtraBold.ttf",
    ("Montserrat", 900): "Montserrat-Black.ttf",
    ("Unbounded", 400): "Unbounded-Regular.ttf",
    ("Unbounded", 700): "Unbounded-Bold.ttf",
    ("Unbounded", 900): "Unbounded-Black.ttf",
    ("PT Serif", 400): "PTSerif-Regular.ttf",
    ("PT Serif", 700): "PTSerif-Bold.ttf",
}
# имя семейства в PPTX для веса, который не Regular/Bold
PPTX_FACE = {500: " Medium", 800: " ExtraBold", 900: " Black"}


def rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr.lstrip("#"))


@dataclass
class Theme:
    bg: str
    ink: str
    muted: str
    accent: str
    accent2: str
    paper: str  # фон карточек
    dark: str  # тёмный фон для акцентных слайдов
    on_dark: str
    title_font: str = "Montserrat"
    title_weight: int = 800
    body_font: str = "Montserrat"
    body_weight: int = 500
    num_font: str = "Unbounded"
    num_weight: int = 900


@dataclass
class Issue:
    slide: int
    level: str  # error | warn
    text: str


@dataclass
class Ctx:
    prs: Presentation
    theme: Theme
    assets: Path
    issues: list[Issue] = field(default_factory=list)
    n: int = 0
    words: int = 0


# ---------- метрики текста ----------
_font_cache: dict = {}


def _pil_font(family: str, weight: int, size_pt: float) -> ImageFont.FreeTypeFont:
    key = (family, weight, round(size_pt * 4))
    if key not in _font_cache:
        fname = FONT_FILES.get((family, weight)) or FONT_FILES[(family, 400)]
        # 1 pt = 1/72 in; измеряем в «точках × 4» для точности
        _font_cache[key] = ImageFont.truetype(str(FONT_DIR / fname), int(size_pt * 4))
    return _font_cache[key]


def wrap_lines(text: str, family: str, weight: int, size: float, width_in: float) -> list[str]:
    f = _pil_font(family, weight, size)
    maxw = width_in * 72 * 4
    out: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            cand = (line + " " + w).strip()
            if f.getlength(cand) <= maxw * 0.96 or not line:
                line = cand
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def text_height(text: str, family: str, weight: int, size: float, width_in: float, spacing: float) -> float:
    lines = wrap_lines(text, family, weight, size, width_in)
    widest = max((_pil_font(family, weight, size).getlength(x) / 288 for x in lines), default=0)
    if widest > width_in * 0.94:  # одно слово шире блока (запас на разницу рендеров)
        return 1e9
    return len(lines) * size * spacing * LINE_K / 72


def fit_size(text, family, weight, w, h, start, minimum, spacing) -> tuple[float, bool]:
    s = start
    while s >= minimum:
        if text_height(text, family, weight, s, w - 0.02, spacing) <= h:
            return s, True
        s -= 1
    return minimum, False


# ---------- примитивы ----------
def face(family: str, weight: int) -> tuple[str, bool]:
    if weight in (400, 700):
        return family, weight == 700
    return family + PPTX_FACE.get(weight, ""), False


def add_text(
    ctx: Ctx,
    slide,
    x,
    y,
    w,
    h,
    text: str,
    *,
    size: float,
    min_size: float | None = None,
    family: str | None = None,
    weight: int | None = None,
    color: str | None = None,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    spacing: float = 1.15,
    caps: bool = False,
    tracking: int = 0,
    role: str = "body",
):
    t = ctx.theme
    family = family or t.body_font
    weight = weight or t.body_weight
    color = color or t.ink
    shown = text.upper() if caps else text
    fitted, ok = fit_size(shown, family, weight, w, h, size, min_size or size, spacing)
    if not ok:
        ctx.issues.append(Issue(ctx.n, "error", f"Текст не помещается ({role}): «{text[:40]}…»"))
    if fitted < (min_size or size) or (role == "body" and fitted < 14):
        ctx.issues.append(Issue(ctx.n, "warn", f"Мелкий шрифт {fitted:.0f} pt ({role})"))
    if role in ("body", "title", "lead"):
        ctx.words += len(text.split())
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    name, bold = face(family, weight)
    for i, para in enumerate(shown.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run()
        r.text = para
        r.font.size = Pt(fitted)
        r.font.name = name
        r.font.bold = bold
        r.font.color.rgb = rgb(color)
        if tracking:
            r._r.get_or_add_rPr().set("spc", str(tracking))
    return box


def rect(slide, x, y, w, h, fill: str, shape=MSO_SHAPE.RECTANGLE, line: str | None = None, radius: float | None = None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def line(slide, x1, y1, x2, y2, color: str, width: float = 1.5, arrow: bool = False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    if arrow:
        ln = c.line._get_or_add_ln()
        tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
        ln.append(tail)
    return c


def background(ctx: Ctx, slide, color: str | None = None, image: Path | None = None):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(color or ctx.theme.bg)
    if image is not None:
        slide.shapes.add_picture(str(image), 0, 0, Inches(W), Inches(H))


def page_no(ctx: Ctx, slide, dark: bool = False):
    t = ctx.theme
    add_text(ctx, slide, W - M - 1, H - 0.55, 1, 0.3, f"{ctx.n:02d}", size=11, family=t.body_font, weight=700,
             color=t.on_dark if dark else t.muted, align=PP_ALIGN.RIGHT, role="meta")


def source(ctx: Ctx, slide, text: str, dark: bool = False, x: float = M, w: float | None = None):
    t = ctx.theme
    add_text(ctx, slide, x, H - 0.6, (w or W - 2 * M - 1.2), 0.4, "Источник: " + text, size=11, min_size=9,
             weight=500, color=t.on_dark if dark else t.muted, anchor=MSO_ANCHOR.BOTTOM, role="meta")


def kicker(ctx: Ctx, slide, x, y, w, text: str, color: str | None = None):
    add_text(ctx, slide, x, y, w, 0.35, text, size=13, weight=700, color=color or ctx.theme.accent, caps=True,
             tracking=200, role="meta")


# ---------- картинки ----------
def image_or_placeholder(ctx: Ctx, slide, x, y, w, h, spec: dict | None, dark_overlay: float = 0.0, caption: bool = True):
    """Фото из assets (обрезка под рамку) или аккуратная заглушка с описанием — что сюда встанет."""
    t = ctx.theme
    spec = spec or {}
    px_w, px_h = int(w * 160), int(h * 160)
    path = ctx.assets / spec["file"] if spec.get("file") else None
    if path and path.exists():
        img = Image.open(path).convert("RGB")
        fx, fy = spec.get("focus", (0.5, 0.5))
        sr = img.width / img.height
        tr = px_w / px_h
        if sr > tr:
            nw = int(img.height * tr)
            left = int((img.width - nw) * fx)
            img = img.crop((left, 0, left + nw, img.height))
        else:
            nh = int(img.width / tr)
            top = int((img.height - nh) * fy)
            img = img.crop((0, top, img.width, top + nh))
        img = img.resize((px_w, px_h), Image.LANCZOS)
    else:
        ctx.issues.append(Issue(ctx.n, "warn", f"Нет фото: {spec.get('want', 'изображение')}"))
        img = Image.new("RGB", (px_w, px_h), t.paper)
        d = ImageDraw.Draw(img)
        a = Image.new("RGB", (px_w, px_h), t.accent2)
        mask = Image.linear_gradient("L").resize((px_w, px_h)).point(lambda v: int(v * 0.35))
        img = Image.composite(a, img, mask)
        d = ImageDraw.Draw(img)
        for i in range(-px_h, px_w, 28):
            d.line([(i, px_h), (i + px_h, 0)], fill=t.bg, width=1)
        f = ImageFont.truetype(str(FONT_DIR / FONT_FILES[(t.body_font, 700)]), 26)
        label = "ФОТО · " + spec.get("want", "")
        words, lines, cur = label.split(), [], ""
        for wd in words:
            c = (cur + " " + wd).strip()
            if f.getlength(c) > px_w * 0.7 and cur:
                lines.append(cur); cur = wd
            else:
                cur = c
        lines.append(cur)
        yy = px_h / 2 - len(lines) * 18
        for ln in lines:
            tw = f.getlength(ln)
            d.text(((px_w - tw) / 2, yy), ln, font=f, fill=t.ink)
            yy += 36
    if dark_overlay:
        black = Image.new("RGB", img.size, ctx.theme.dark)
        if spec.get("_uniform"):
            mask = Image.new("L", img.size, int(255 * dark_overlay))
        else:  # слева темно (там текст), справа видно фото
            grad = Image.linear_gradient("L").rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT).resize(img.size)
            mask = grad.point(lambda v: int(255 * (0.25 + (dark_overlay - 0.25) * (v / 255) ** 1.4)))
        img = Image.composite(black, img, mask)
    out = ctx.assets / f"_s{ctx.n:02d}_{int(x*100)}_{int(y*100)}.jpg"
    img.save(out, quality=88)
    pic = slide.shapes.add_picture(str(out), Inches(x), Inches(y), Inches(w), Inches(h))
    if caption and spec.get("credit"):
        add_text(ctx, slide, x, y + h + 0.06, w, 0.3, spec["credit"], size=10, min_size=8, weight=500,
                 color=t.muted, role="meta")
    return pic


# ---------- макеты ----------
def L_cover(ctx: Ctx, s, d):
    t = ctx.theme
    image_or_placeholder(ctx, s, 0, 0, W, H, d.get("image"), dark_overlay=0.82, caption=False)
    kicker(ctx, s, M, 1.0, 8, d.get("kicker", ""), color=t.accent2)
    add_text(ctx, s, M, 1.5, 8.2, 2.9, d["title"], size=60, min_size=36, family=t.title_font, weight=t.title_weight,
             color="#FFFFFF", spacing=0.95, role="title", anchor=MSO_ANCHOR.BOTTOM)
    add_text(ctx, s, M, 4.6, 6.6, 1.2, d.get("subtitle", ""), size=20, min_size=15, color="#E9E3D8", role="lead")
    plate = d.get("plate") or {}
    if plate:
        txt = "\n".join(f"{k}: {v}" for k, v in plate.items())
        rect(s, W - M - 3.6, H - 1.75, 0.05, 1.1, t.accent2)
        add_text(ctx, s, W - M - 3.4, H - 1.75, 3.4, 1.1, txt, size=13, min_size=10, color="#FFFFFF", role="meta",
                 anchor=MSO_ANCHOR.MIDDLE)
    if d.get("image", {}).get("credit"):
        add_text(ctx, s, M, H - 0.5, 6, 0.3, d["image"]["credit"], size=9, color="#BDB6AA", role="meta")


def L_hook(ctx: Ctx, s, d):
    t = ctx.theme
    background(ctx, s, t.dark)
    if d.get("image"):
        image_or_placeholder(ctx, s, W * 0.52, 0, W * 0.48, H, d["image"], caption=False)
    kicker(ctx, s, M, 1.2, 6, d.get("kicker", ""), color=t.accent2)
    add_text(ctx, s, M, 1.7, W * 0.52 - M - 0.4, 3.2, d["title"], size=44, min_size=30, family=t.title_font,
             weight=t.title_weight, color=t.on_dark, spacing=1.0, role="title")
    add_text(ctx, s, M, 5.0, W * 0.52 - M - 0.4, 1.6, d.get("text", ""), size=20, min_size=16, color="#D8D2C6",
             role="body")
    if d.get("image", {}).get("credit"):
        add_text(ctx, s, W * 0.52 + 0.2, H - 0.45, 6, 0.3, d["image"]["credit"], size=9, color="#FFFFFF", role="meta")
    page_no(ctx, s, dark=True)


def L_bignum(ctx: Ctx, s, d):
    """Одна цифра + с чем сравнить + что это значит."""
    t = ctx.theme
    background(ctx, s)
    kicker(ctx, s, M, 0.75, 8, d.get("kicker", ""))
    add_text(ctx, s, M, 1.15, W - 2 * M, 1.3, d["title"], size=36, min_size=26, family=t.title_font,
             weight=t.title_weight, spacing=1.0, role="title")
    cmp = d.get("compare")
    num_w = 6.4
    if cmp:
        k0 = 3.4 / math.sqrt(max(cmp["a_value"], cmp["b_value"]))
        num_w = W - 2 * M - (math.sqrt(cmp["a_value"]) * k0 + 0.25 + max(math.sqrt(cmp["b_value"]) * k0, 1.6)) - 0.4
    add_text(ctx, s, M, 2.7, num_w, 2.0, d["number"], size=110, min_size=60, family=t.num_font, weight=t.num_weight,
             color=t.accent, spacing=0.9, role="number", anchor=MSO_ANCHOR.MIDDLE)
    add_text(ctx, s, M, 4.75, 6.0, 0.5, d.get("unit", ""), size=20, weight=700, role="lead")
    add_text(ctx, s, M, 5.3, 6.0, 1.3, d.get("text", ""), size=18, min_size=15, role="body")
    # сравнение — квадраты в масштабе
    cmp = d.get("compare")
    if cmp:
        y0, side_max = 2.75, 3.4
        big, small = cmp["a_value"], cmp["b_value"]
        k = side_max / math.sqrt(max(big, small))
        sa, sb = math.sqrt(big) * k, math.sqrt(small) * k
        x0 = W - M - (sa + 0.25 + max(sb, 1.6))
        rect(s, x0, y0 + side_max - sa, sa, sa, t.accent2)
        add_text(ctx, s, x0 + 0.15, y0 + side_max - sa + 0.12, sa - 0.3, 0.8, cmp["a_label"], size=15, weight=700,
                 color="#FFFFFF", role="label")
        bx = x0 + sa + 0.25
        rect(s, bx, y0 + side_max - sb, sb, sb, t.muted)
        add_text(ctx, s, bx, y0 + side_max + 0.1, 2.4, 0.8, cmp["b_label"], size=13, min_size=11, weight=700,
                 role="label")
        add_text(ctx, s, x0, y0 + side_max + 0.1, sa, 0.5, cmp.get("note", ""), size=12, min_size=10,
                 color=t.muted, role="meta")
    if d.get("source"):
        source(ctx, s, d["source"])
    page_no(ctx, s)


def _style_chart(ctx: Ctx, chart, colors: list[str], percent_labels: bool = False, fmt: str = '#,##0'):
    t = ctx.theme
    chart.has_title = False
    chart.has_legend = len(chart.plots[0].series) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(13)
    for ax in (chart.category_axis, chart.value_axis):
        ax.tick_labels.font.size = Pt(13)
        ax.tick_labels.font.color.rgb = rgb(t.muted)
        ax.tick_labels.font.name = t.body_font + " Medium"
        ax.format.line.color.rgb = rgb(t.paper)
    chart.value_axis.has_major_gridlines = True
    chart.value_axis.major_gridlines.format.line.color.rgb = rgb(t.paper)
    chart.value_axis.tick_labels.number_format = fmt
    chart.value_axis.tick_labels.number_format_is_linked = False
    for i, ser in enumerate(chart.plots[0].series):
        c = colors[i % len(colors)]
        f = ser.format
        if chart.chart_type in (XL_CHART_TYPE.LINE_MARKERS, XL_CHART_TYPE.LINE):
            f.line.color.rgb = rgb(c)
            f.line.width = Pt(4)
            ser.smooth = False
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = rgb(c)
            ser.marker.size = 9
        else:
            f.fill.solid()
            f.fill.fore_color.rgb = rgb(c)


def L_chart(ctx: Ctx, s, d):
    """График: вывод в заголовке, подпись главной точки, пояснение справа."""
    t = ctx.theme
    background(ctx, s)
    kicker(ctx, s, M, 0.75, 8, d.get("kicker", ""))
    add_text(ctx, s, M, 1.15, W - 2 * M, 1.3, d["title"], size=34, min_size=26, family=t.title_font,
             weight=t.title_weight, spacing=1.0, role="title")
    cd = CategoryChartData()
    cd.categories = d["categories"]
    for name, vals in d["series"]:
        cd.add_series(name, vals)
    kind = {"line": XL_CHART_TYPE.LINE_MARKERS, "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "hbar": XL_CHART_TYPE.BAR_CLUSTERED}[d.get("kind", "line")]
    cw = 8.0 if d.get("text") else W - 2 * M
    gf = s.shapes.add_chart(kind, Inches(M - 0.1), Inches(2.55), Inches(cw), Inches(4.2), cd)
    ch = gf.chart
    colors = d.get("colors") or [t.accent2, t.accent]
    _style_chart(ctx, ch, colors, fmt=d.get("fmt", "#,##0"))
    plot = ch.plots[0]
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.font.size = Pt(14)
    dl.font.bold = True
    dl.font.color.rgb = rgb(t.ink)
    dl.number_format = d.get("fmt", "#,##0")
    dl.number_format_is_linked = False
    if kind == XL_CHART_TYPE.LINE_MARKERS:
        dl.position = XL_LABEL_POSITION.ABOVE
    else:
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        plot.gap_width = 60
        if d.get("highlight") is not None:  # одна колонка — акцентом, остальные серые
            ser = plot.series[0]
            for i in range(len(d["categories"])):
                pt = ser.points[i]
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = rgb(t.accent if i in d["highlight"] else t.muted)
    ch.font.name = t.body_font + " Medium"
    if d.get("text"):
        rect(s, 9.0, 2.75, W - 9.0 - M + 0.2, 3.7, t.paper)
        add_text(ctx, s, 9.25, 2.95, W - 9.25 - M - 0.05, 0.9, d.get("callout", ""), size=34, min_size=24,
                 family=t.num_font, weight=t.num_weight, color=t.accent, role="number")
        add_text(ctx, s, 9.25, 3.95, W - 9.25 - M - 0.05, 2.35, d["text"], size=17, min_size=14, role="body")
    if d.get("source"):
        source(ctx, s, d["source"])
    page_no(ctx, s)


def L_flow(ctx: Ctx, s, d):
    """Процесс/причина → следствие: шаги со стрелками, у каждого шага объяснение."""
    t = ctx.theme
    background(ctx, s)
    kicker(ctx, s, M, 0.75, 8, d.get("kicker", ""))
    add_text(ctx, s, M, 1.15, W - 2 * M, 1.3, d["title"], size=34, min_size=26, family=t.title_font,
             weight=t.title_weight, spacing=1.0, role="title")
    steps = d["steps"]
    n = len(steps)
    gap = 0.55
    bw = (W - 2 * M - gap * (n - 1)) / n
    y = 2.8
    for i, st in enumerate(steps):
        x = M + i * (bw + gap)
        hot = i == n - 1
        fill = t.dark if hot else t.paper
        ink = t.on_dark if hot else t.ink
        rect(s, x, y, bw, 3.4, fill, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        add_text(ctx, s, x + 0.25, y + 0.25, bw - 0.5, 0.9, st["value"], size=34, min_size=20, family=t.num_font,
                 weight=t.num_weight, color=t.accent if not hot else t.accent2, role="number")
        add_text(ctx, s, x + 0.25, y + 1.2, bw - 0.5, 0.65, st["label"], size=18, min_size=14, weight=700, color=ink,
                 role="title")
        add_text(ctx, s, x + 0.25, y + 1.9, bw - 0.5, 1.35, st["text"], size=15, min_size=12, color=ink, role="body")
        if i < n - 1:
            line(s, x + bw + 0.08, y + 1.7, x + bw + gap - 0.08, y + 1.7, t.accent, 3, arrow=True)
    if d.get("source"):
        source(ctx, s, d["source"])
    page_no(ctx, s)


def L_story(ctx: Ctx, s, d):
    """История места/человека: большое фото слева, рассказ и 2 факта справа."""
    t = ctx.theme
    background(ctx, s)
    image_or_placeholder(ctx, s, 0, 0, 5.6, H, d.get("image"), caption=False)
    x = 6.2
    kicker(ctx, s, x, 0.75, 6, d.get("kicker", ""))
    add_text(ctx, s, x, 1.15, W - x - M, 1.5, d["title"], size=32, min_size=24, family=t.title_font,
             weight=t.title_weight, spacing=1.0, role="title")
    add_text(ctx, s, x, 2.8, W - x - M, 1.8, d["text"], size=17, min_size=14, role="body")
    facts = d.get("facts", [])
    fw = (W - x - M - 0.3) / max(1, len(facts))
    for i, f in enumerate(facts):
        fx = x + i * (fw + 0.3)
        line(s, fx, 4.85, fx + fw, 4.85, t.accent, 2)
        add_text(ctx, s, fx, 5.0, fw, 0.75, f["value"], size=30, min_size=20, family=t.num_font, weight=t.num_weight,
                 color=t.accent, role="number")
        add_text(ctx, s, fx, 5.8, fw, 0.9, f["label"], size=14, min_size=12, role="body")
    if d.get("image", {}).get("credit"):
        add_text(ctx, s, 0.3, H - 0.45, 5, 0.3, d["image"]["credit"], size=9, color="#FFFFFF", role="meta")
    if d.get("source"):
        source(ctx, s, d["source"], x=x, w=W - x - M - 1.2)
    page_no(ctx, s)


def L_three(ctx: Ctx, s, d):
    """Три цифры с объяснением каждой — на тёмном фоне (или на фото)."""
    t = ctx.theme
    background(ctx, s, t.dark)
    if d.get("image"):
        image_or_placeholder(ctx, s, 0, 0, W, H, {**d["image"], "_uniform": True}, dark_overlay=0.8, caption=False)
    kicker(ctx, s, M, 0.75, 8, d.get("kicker", ""), color=t.accent2)
    add_text(ctx, s, M, 1.15, W - 2 * M, 1.4, d["title"], size=36, min_size=26, family=t.title_font,
             weight=t.title_weight, color=t.on_dark, spacing=1.0, role="title")
    items = d["items"]
    cw = (W - 2 * M - 0.6) / 3
    for i, it in enumerate(items):
        x = M + i * (cw + 0.3)
        line(s, x, 3.15, x + cw, 3.15, t.accent2, 2)
        add_text(ctx, s, x, 3.35, cw, 1.1, it["value"], size=46, min_size=28, family=t.num_font, weight=t.num_weight,
                 color=t.accent2, role="number")
        add_text(ctx, s, x, 4.5, cw, 0.5, it["label"], size=18, min_size=15, weight=700, color=t.on_dark,
                 role="title")
        add_text(ctx, s, x, 5.05, cw, 1.4, it["text"], size=15, min_size=13, color="#D8D2C6", role="body")
    if d.get("source"):
        source(ctx, s, d["source"], dark=True)
    page_no(ctx, s, dark=True)


def L_timeline(ctx: Ctx, s, d):
    t = ctx.theme
    background(ctx, s)
    kicker(ctx, s, M, 0.75, 8, d.get("kicker", ""))
    add_text(ctx, s, M, 1.15, W - 2 * M, 1.3, d["title"], size=34, min_size=26, family=t.title_font,
             weight=t.title_weight, spacing=1.0, role="title")
    ev = d["events"]
    y = 3.55
    line(s, M, y, W - M, y, t.muted, 2)
    cw = (W - 2 * M) / len(ev)
    for i, e in enumerate(ev):
        x = M + i * cw
        hot = e.get("hot")
        dot = 0.32 if hot else 0.22
        rect(s, x + 0.05, y - dot / 2, dot, dot, t.accent if hot else t.ink, MSO_SHAPE.OVAL)
        add_text(ctx, s, x, 2.75, cw - 0.25, 0.6, e["year"], size=26, min_size=18, family=t.num_font,
                 weight=t.num_weight, color=t.accent if hot else t.ink, role="number")
        add_text(ctx, s, x, 3.95, cw - 0.3, 0.55, e["label"], size=16, min_size=13, weight=700, role="title")
        add_text(ctx, s, x, 4.6, cw - 0.3, 1.9, e["text"], size=14, min_size=12, color=t.ink, role="body")
    if d.get("source"):
        source(ctx, s, d["source"])
    page_no(ctx, s)


def L_split(ctx: Ctx, s, d):
    """Понятие/объяснение: текст слева, фото или схема справа."""
    t = ctx.theme
    background(ctx, s)
    kicker(ctx, s, M, 0.75, 6, d.get("kicker", ""))
    add_text(ctx, s, M, 1.15, 6.0, 1.9, d["title"], size=34, min_size=24, family=t.title_font,
             weight=t.title_weight, spacing=1.0, role="title")
    add_text(ctx, s, M, 3.15, 6.0, 2.2, d["text"], size=18, min_size=14, role="body")
    if d.get("facts"):
        fx = M
        for f in d["facts"]:
            add_text(ctx, s, fx, 5.45, 2.9, 0.7, f["value"], size=28, min_size=18, family=t.num_font,
                     weight=t.num_weight, color=t.accent, role="number")
            add_text(ctx, s, fx, 6.12, 2.9, 0.6, f["label"], size=13, min_size=11, role="body")
            fx += 3.1
    image_or_placeholder(ctx, s, 7.3, 0.75, W - 7.3 - M + 0.3, 5.7, d.get("image"))
    if d.get("source"):
        source(ctx, s, d["source"], w=6.0)
    page_no(ctx, s)


def L_end(ctx: Ctx, s, d):
    t = ctx.theme
    background(ctx, s, t.dark)
    if d.get("image"):
        image_or_placeholder(ctx, s, 0, 0, W, H, d["image"], dark_overlay=0.9, caption=False)
    kicker(ctx, s, M, 1.0, 8, d.get("kicker", "Главное"), color=t.accent2)
    add_text(ctx, s, M, 1.5, 9.5, 2.6, d["title"], size=44, min_size=30, family=t.title_font, weight=t.title_weight,
             color=t.on_dark, spacing=1.0, role="title")
    rect(s, M, 4.55, 0.08, 1.3, t.accent2)
    add_text(ctx, s, M + 0.35, 4.5, 9, 0.4, "Вопрос для обсуждения", size=14, weight=700, color=t.accent2,
             role="meta")
    add_text(ctx, s, M + 0.35, 4.95, 9, 1.0, d["question"], size=22, min_size=17, color=t.on_dark, role="body")
    add_text(ctx, s, M, H - 0.7, 6, 0.4, "Спасибо за внимание", size=13, color="#BDB6AA", role="meta")


def L_sources(ctx: Ctx, s, d):
    t = ctx.theme
    background(ctx, s)
    add_text(ctx, s, M, 0.75, W - 2 * M, 0.8, "Источники", size=32, family=t.title_font, weight=t.title_weight,
             role="meta")
    colw = (W - 2 * M - 0.5) / 2
    add_text(ctx, s, M, 1.75, colw, 5.0, "\n".join(d["texts"]), size=13, min_size=10, spacing=1.25, role="meta")
    add_text(ctx, s, M + colw + 0.5, 1.75, colw, 5.0, "\n".join(d.get("images", [])), size=13, min_size=10,
             spacing=1.25, role="meta")
    page_no(ctx, s)


LAYOUTS = {
    "cover": L_cover, "hook": L_hook, "bignum": L_bignum, "chart": L_chart, "flow": L_flow, "story": L_story,
    "three": L_three, "timeline": L_timeline, "split": L_split, "end": L_end, "sources": L_sources,
}
WORD_LIMIT = {"cover": 40, "hook": 45, "bignum": 70, "chart": 80, "flow": 110, "story": 110, "three": 110,
              "timeline": 120, "split": 110, "end": 50, "sources": 999}


def build(deck_path: Path, out_pptx: Path) -> list[Issue]:
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    ctx = Ctx(prs, Theme(**deck["theme"]), deck_path.parent / "assets")
    ctx.assets.mkdir(exist_ok=True)
    blank = prs.slide_layouts[6]
    prev = None
    for i, sd in enumerate(deck["slides"], 1):
        ctx.n = i
        ctx.words = 0
        s = prs.slides.add_slide(blank)
        LAYOUTS[sd["layout"]](ctx, s, sd)
        if sd.get("notes"):
            s.notes_slide.notes_text_frame.text = sd["notes"]
        if ctx.words > WORD_LIMIT[sd["layout"]]:
            ctx.issues.append(Issue(i, "warn", f"Много текста: {ctx.words} слов (норма {WORD_LIMIT[sd['layout']]})"))
        if prev == sd["layout"] == deck["slides"][i - 3]["layout"] if i >= 3 else False:
            ctx.issues.append(Issue(i, "warn", "Три одинаковых макета подряд"))
        prev = sd["layout"]
    prs.core_properties.title = deck.get("title", "")
    prs.core_properties.author = "SlideLab"
    prs.save(out_pptx)
    return ctx.issues


if __name__ == "__main__":
    deck = Path(sys.argv[1])
    out = deck.with_suffix(".pptx")
    issues = build(deck, out)
    for it in issues:
        print(f"[{it.level}] слайд {it.slide}: {it.text}")
    print("OK", out)
