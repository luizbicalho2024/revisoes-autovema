from src.appearance import detect_image_mime, normalize_appearance


def test_invalid_color_falls_back():
    theme = normalize_appearance(
        {"primary_color": "red; background:url(x)"}
    )
    assert theme["primary_color"] == "#B5121B"


def test_layout_limits():
    theme = normalize_appearance(
        {"border_radius": 999, "sidebar_width": 1}
    )
    assert theme["border_radius"] == 28
    assert theme["sidebar_width"] == 260


def test_logo_magic_bytes():
    assert detect_image_mime(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert detect_image_mime(b"\xff\xd8\xffrest") == "image/jpeg"
    assert detect_image_mime(b"RIFF1234WEBPrest") == "image/webp"
    assert detect_image_mime(b"<svg></svg>") is None
