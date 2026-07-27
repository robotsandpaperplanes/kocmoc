from __future__ import annotations

from io import BytesIO
from pathlib import Path
import textwrap

import qrcode
from PIL import Image, ImageDraw, ImageFont


FONT_REGULAR_PATHS = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
)
FONT_BOLD_PATHS = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
)


def _font(paths: tuple[Path, ...], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def create_certificate_png(
    *,
    certificate_id: str,
    amount_text: str,
    comment: str | None,
    qr_data: str,
) -> BytesIO:
    width, height = 1280, 760
    image = Image.new("RGB", (width, height), "#F3EFE6")
    draw = ImageDraw.Draw(image)

    title_font = _font(FONT_BOLD_PATHS, 50)
    amount_font = _font(FONT_BOLD_PATHS, 76)
    label_font = _font(FONT_REGULAR_PATHS, 25)
    id_font = _font(FONT_BOLD_PATHS, 27)
    comment_font = _font(FONT_REGULAR_PATHS, 28)
    small_font = _font(FONT_REGULAR_PATHS, 21)

    draw.rounded_rectangle((30, 30, width - 30, height - 30), radius=28, outline="#262626", width=3)
    draw.text((75, 70), "ПОДАРОЧНЫЙ СЕРТИФИКАТ", fill="#262626", font=title_font)
    draw.text((75, 165), amount_text, fill="#262626", font=amount_font)

    draw.text((75, 285), "Уникальный ID", fill="#5A574F", font=label_font)
    draw.text((75, 326), certificate_id, fill="#262626", font=id_font)

    if comment:
        draw.text((75, 405), "Комментарий", fill="#5A574F", font=label_font)
        wrapped = textwrap.wrap(comment, width=45)[:4]
        draw.multiline_text((75, 445), "\n".join(wrapped), fill="#262626", font=comment_font, spacing=10)

    qr = qrcode.QRCode(version=None, box_size=10, border=3)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="#111111", back_color="#FFFFFF").convert("RGB")
    qr_image = qr_image.resize((330, 330), Image.Resampling.NEAREST)
    image.paste(qr_image, (875, 160))

    draw.text((887, 510), "Сканируйте в студии", fill="#262626", font=small_font)
    draw.text(
        (75, 675),
        "QR-код является ключом сертификата. Не публикуйте его в открытом доступе.",
        fill="#5A574F",
        font=small_font,
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
