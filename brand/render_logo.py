"""Render waterfall blue W mark to PNG/ICO."""
from pathlib import Path

from PIL import Image, ImageDraw

BOARD = (11, 18, 32, 255)
BOARD2 = (18, 32, 61, 255)
ACCENT = (94, 198, 255, 255)
ACCENT_HI = (154, 224, 255, 255)
ACCENT_LO = (58, 168, 232, 255)


def draw_logo(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = int(size * 0.21)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BOARD)
    # subtle top glow
    d.ellipse(
        [int(size * 0.15), int(size * -0.05), int(size * 0.95), int(size * 0.55)],
        fill=BOARD2,
    )

    # Stylized W polygon (normalized 0..1 then scaled)
    # Mirrors brand/logo.svg path
    pts = [
        (96, 128),
        (148, 128),
        (196, 320),
        (256, 168),
        (316, 320),
        (364, 128),
        (416, 128),
        (348, 384),
        (292, 384),
        (256, 268),
        (220, 384),
        (164, 384),
    ]
    scale = size / 512.0
    poly = [(int(x * scale), int(y * scale)) for x, y in pts]
    d.polygon(poly, fill=ACCENT)

    # small highlight on left leg for depth
    hi = [
        (int(110 * scale), int(140 * scale)),
        (int(145 * scale), int(140 * scale)),
        (int(185 * scale), int(300 * scale)),
        (int(170 * scale), int(300 * scale)),
    ]
    d.polygon(hi, fill=ACCENT_HI)
    return img


def main() -> None:
    brand = Path(__file__).resolve().parent
    master = draw_logo(1024)
    master.save(brand / "logo.png")
    master.save(brand / "logo-1024.png")
    for s in (512, 256, 128, 64, 32):
        draw_logo(s).save(brand / f"logo-{s}.png")
    draw_logo(32).save(brand / "favicon-32.png")
    sizes = (16, 32, 48, 64, 128, 256)
    icos = [draw_logo(s) for s in sizes]
    icos[-1].save(
        brand / "logo.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=icos[:-1],
    )
    print("ok", brand)


if __name__ == "__main__":
    main()
