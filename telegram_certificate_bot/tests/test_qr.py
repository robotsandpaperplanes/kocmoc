from app.qr import create_certificate_png


def test_certificate_image_is_png() -> None:
    buffer = create_certificate_png(
        certificate_id="f14db52e-f180-4a3e-a82f-e27dfd4e661b",
        amount_text="10 000 ₽",
        comment="Подарок для Анны",
        qr_data="https://t.me/example_bot?start=cert_secret",
    )
    assert buffer.read(8) == b"\x89PNG\r\n\x1a\n"
