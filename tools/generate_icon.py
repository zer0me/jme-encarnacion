"""Generate civic-style icon: stylized open document with check mark seal.

Outputs:
- quartz/static/icon.png      200x200 favicon
- quartz/static/og-image.png  1200x630 social preview

Palette (matches quartz.config.ts light mode):
  bg:       navy   #1e3a5f
  page:     cream  #faf5e6
  accent:   mustard #c9a227
  text:     dark   #1a1a1a
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

NAVY = "#1e3a5f"
CREAM = "#faf5e6"
MUSTARD = "#c9a227"
DARK = "#1a1a1a"


def draw_document_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
    """Draw a stylized open page with horizontal lines and a check seal."""
    page_w = size
    page_h = int(size * 1.25)
    x0 = cx - page_w // 2
    y0 = cy - page_h // 2
    x1 = cx + page_w // 2
    y1 = cy + page_h // 2

    fold = int(page_w * 0.18)
    page = [
        (x0, y0),
        (x1 - fold, y0),
        (x1, y0 + fold),
        (x1, y1),
        (x0, y1),
    ]
    draw.polygon(page, fill=CREAM)

    folded_corner = [(x1 - fold, y0), (x1, y0 + fold), (x1 - fold, y0 + fold)]
    draw.polygon(folded_corner, fill="#e8d8a8")

    line_color = DARK
    line_thickness = max(2, size // 50)
    margin = int(page_w * 0.18)
    line_x0 = x0 + margin
    line_x1 = x1 - margin
    line_start_y = y0 + int(page_h * 0.28)
    line_gap = int(page_h * 0.10)
    for i in range(4):
        ly = line_start_y + i * line_gap
        if i == 0:
            draw.rectangle([line_x0, ly, line_x1, ly + line_thickness], fill=line_color)
        else:
            short_end = line_x1 - (i * line_gap // 2)
            draw.rectangle([line_x0, ly, short_end, ly + line_thickness], fill=line_color)

    seal_r = int(page_w * 0.22)
    seal_cx = x1 - int(page_w * 0.22)
    seal_cy = y1 - int(page_h * 0.20)
    draw.ellipse(
        [seal_cx - seal_r, seal_cy - seal_r, seal_cx + seal_r, seal_cy + seal_r],
        fill=MUSTARD,
    )

    check_thickness = max(3, size // 25)
    check_color = CREAM
    p1 = (seal_cx - seal_r * 0.45, seal_cy + seal_r * 0.05)
    p2 = (seal_cx - seal_r * 0.10, seal_cy + seal_r * 0.40)
    p3 = (seal_cx + seal_r * 0.50, seal_cy - seal_r * 0.35)
    draw.line([p1, p2], fill=check_color, width=check_thickness)
    draw.line([p2, p3], fill=check_color, width=check_thickness)


def make_icon(out: Path, size: int) -> None:
    canvas_size = size * 4
    img = Image.new("RGBA", (canvas_size, canvas_size), NAVY)
    draw = ImageDraw.Draw(img)
    pad = canvas_size // 8
    draw_document_icon(draw, canvas_size // 2, canvas_size // 2, canvas_size - 2 * pad - canvas_size // 6)
    img = img.resize((size, size), Image.LANCZOS)
    img.save(out, "PNG")
    print(f"  -> wrote {out} ({size}x{size})")


def make_og_image(out: Path) -> None:
    w, h = 1200, 630
    img = Image.new("RGBA", (w, h), NAVY)
    draw = ImageDraw.Draw(img)

    icon_size = 280
    icon_cx = 200
    icon_cy = h // 2
    draw_document_icon(draw, icon_cx, icon_cy, icon_size)

    text_x = 440
    try:
        font_title = ImageFont.truetype("arial.ttf", 56)
        font_sub = ImageFont.truetype("arial.ttf", 32)
        font_small = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font_title = ImageFont.load_default()
        font_sub = font_title
        font_small = font_title

    draw.text((text_x, 200), "Archivo público", font=font_title, fill=CREAM)
    draw.text((text_x, 270), "JM Encarnación", font=font_title, fill=MUSTARD)
    draw.text((text_x, 360), "Actas, minutas y análisis", font=font_sub, fill=CREAM)
    draw.text((text_x, 405), "ciudadano de la Junta Municipal.", font=font_sub, fill=CREAM)
    draw.text((text_x, 480), "zer0me.github.io/jme-encarnacion", font=font_small, fill="#a8b8c8")

    img.save(out, "PNG")
    print(f"  -> wrote {out} (1200x630)")


def main() -> None:
    static_dir = Path(__file__).resolve().parent.parent / "quartz" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    print("Generating icons...")
    make_icon(static_dir / "icon.png", 200)
    make_og_image(static_dir / "og-image.png")
    print("Done.")


if __name__ == "__main__":
    main()
