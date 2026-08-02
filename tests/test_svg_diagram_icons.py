import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
RECT_PATTERN = re.compile(
    r'<rect[^>]*x="(?P<x>[0-9.]+)"[^>]*y="(?P<y>[0-9.]+)"'
    r'[^>]*width="(?P<width>[0-9.]+)"[^>]*height="(?P<height>[0-9.]+)"'
    r'[^>]*data-card="true"[^>]*/>'
)
TEXT_PATTERN = re.compile(
    r'<text[^>]*x="(?P<x>[0-9.]+)"[^>]*'
    r'(?:font-size="(?P<size>[0-9.]+)")?[^>]*>(?P<label>.*?)</text>'
)
USE_PATTERN = re.compile(
    r'<use href="#icon-[^"]+" transform="translate\((?P<x>[0-9.]+) '
    r'(?P<y>[0-9.]+)\) scale\((?P<scale>[0-9.]+)\)"'
)


def _svg_files() -> list[Path]:
    return sorted(DOCS_DIR.glob("*.svg"))


def test_docs_svg_diagrams_use_inline_icons_only() -> None:
    svg_files = _svg_files()
    assert svg_files

    for svg_path in svg_files:
        content = svg_path.read_text(encoding="utf-8")
        assert "<image" not in content, f"{svg_path.name} must not link external images"
        assert 'id="icon-web"' in content, f"{svg_path.name} must define inline icons"


def test_marked_svg_cards_have_representative_icons() -> None:
    for svg_path in _svg_files():
        lines = svg_path.read_text(encoding="utf-8").splitlines()
        card_count = 0
        for index, line in enumerate(lines):
            if 'data-card="true"' not in line:
                continue

            card_count += 1
            if "<rect" in line:
                following = "\n".join(lines[index + 1 : index + 3])
                assert '<use href="#icon-' in following, (
                    f"{svg_path.name}:{index + 1} card rect is missing an icon"
                )
                continue

            if "<g" in line:
                block = "\n".join(lines[index : index + 16])
                assert '<use href="#icon-' in block, (
                    f"{svg_path.name}:{index + 1} card group is missing an icon"
                )

        assert card_count > 0, f"{svg_path.name} should mark semantic cards"


def test_svg_card_icons_do_not_collide_with_titles() -> None:
    for svg_path in _svg_files():
        lines = svg_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            rect_match = RECT_PATTERN.search(line)
            if not rect_match:
                continue

            width = float(rect_match.group("width"))
            if width >= 300:
                continue

            icon_match = USE_PATTERN.search(lines[index + 1])
            assert icon_match, f"{svg_path.name}:{index + 1} card is missing an icon"
            icon_right = float(icon_match.group("x")) + (40 * float(icon_match.group("scale")))

            for text_line in lines[index + 2 : index + 8]:
                if 'font-weight="700"' not in text_line and "cardTitle" not in text_line:
                    continue

                text_match = TEXT_PATTERN.search(text_line)
                assert text_match, f"{svg_path.name}:{index + 1} title is not parseable"
                text_x = float(text_match.group("x"))
                if 'text-anchor="start"' in text_line:
                    title_left = text_x
                else:
                    title = re.sub(r"<[^>]+>", "", text_match.group("label"))
                    font_size = float(text_match.group("size") or 14)
                    title_left = text_x - (len(title) * font_size * 0.55 / 2)

                assert title_left - icon_right >= 24, (
                    f"{svg_path.name}:{index + 1} icon/title gap is too small"
                )
                break
