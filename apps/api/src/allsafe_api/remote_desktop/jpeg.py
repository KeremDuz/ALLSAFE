"""Bound JPEG decode dimensions without decoding pixels or allocating an image."""

SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


def baseline_dimensions(data: bytes) -> tuple[int, int] | None:
    """Accept the helper's single-scan 8-bit baseline JPEG, with one bounded SOF.

    This validates structural bounds and dimensions, not pixel correctness. Only
    one image and one scan are accepted; progressive/arithmetic/multi-frame files
    are unnecessary for System.Drawing's baseline encoder and are rejected.
    """
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        return None
    offset = 2
    dimensions: tuple[int, int] | None = None
    components = 0
    markers = 0
    while offset < len(data) - 2:
        markers += 1
        if markers > 256 or data[offset] != 0xFF:
            return None
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            return None
        marker = data[offset]
        offset += 1
        if marker in {0, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            return None
        if offset + 2 > len(data):
            return None
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data) - 2:
            return None
        payload = offset + 2
        end = offset + length
        if marker in SOF_MARKERS:
            if marker != 0xC0 or dimensions is not None or length < 8:
                return None
            precision = data[payload]
            height = int.from_bytes(data[payload + 1 : payload + 3], "big")
            width = int.from_bytes(data[payload + 3 : payload + 5], "big")
            components = data[payload + 5]
            if (
                precision != 8
                or components not in {1, 3}
                or length != 8 + 3 * components
                or not 1 <= width <= 1920
                or not 1 <= height <= 1080
            ):
                return None
            dimensions = (width, height)
        if marker == 0xDA:
            if dimensions is None or length < 6:
                return None
            scan_components = data[payload]
            if scan_components != components or length != 6 + 2 * scan_components:
                return None
            # Entropy-coded data escapes FF as FF00. Restart markers are the only
            # other permitted markers before the final EOI in this baseline scan.
            cursor = end
            while cursor < len(data):
                position = data.find(b"\xff", cursor)
                if position < 0 or position + 1 >= len(data):
                    return None
                cursor = position + 1
                while cursor < len(data) and data[cursor] == 0xFF:
                    cursor += 1
                if cursor >= len(data):
                    return None
                next_marker = data[cursor]
                cursor += 1
                if next_marker == 0 or 0xD0 <= next_marker <= 0xD7:
                    continue
                if next_marker == 0xD9 and cursor == len(data):
                    return dimensions
                return None
            return None
        offset = end
    return None
