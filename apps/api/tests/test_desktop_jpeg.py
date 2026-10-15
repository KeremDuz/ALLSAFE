"""JPEG metadata bounds without screen capture or image decoding."""

from pathlib import Path

import pytest

from allsafe_api.remote_desktop.jpeg import baseline_dimensions


def frame(
    width: int = 1920,
    height: int = 1080,
    *,
    marker: int = 0xC0,
    precision: int = 8,
    entropy: bytes = b"\x00",
) -> bytes:
    sof = (
        bytes([0xFF, marker, 0, 11, precision])
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    sos = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
    return b"\xff\xd8" + sof + sos + entropy + b"\xff\xd9"


def test_real_system_drawing_baseline_encoder_is_supported():
    # Fixture contains only a generated solid color, never a desktop capture.
    value = (Path(__file__).parent / "fixtures" / "desktop-solid-2x2.jpg").read_bytes()
    assert baseline_dimensions(value) == (2, 2)


@pytest.mark.parametrize("width,height", [(1, 1), (1920, 1080), (1280, 720)])
def test_bounded_baseline_dimensions(width, height):
    assert baseline_dimensions(frame(width, height)) == (width, height)


@pytest.mark.parametrize(
    "width,height", [(0, 1), (1, 0), (1921, 1080), (1920, 1081), (65535, 65535)]
)
def test_decode_dimension_bombs_rejected(width, height):
    assert baseline_dimensions(frame(width, height)) is None


@pytest.mark.parametrize("marker", [0xC1, 0xC2, 0xC3, 0xC9])
def test_only_baseline_sof_supported(marker):
    assert baseline_dimensions(frame(marker=marker)) is None


def test_single_scan_allows_stuffing_and_restart_markers():
    assert baseline_dimensions(frame(entropy=b"a\xff\x00b\xff\xd0c")) == (1920, 1080)


@pytest.mark.parametrize(
    "value",
    [
        b"\xff\xd8\xff\xd9",  # no dimensions or scan
        b"\xff\xd8\xff\xc0\xff\xff\xff\xd9",  # out-of-bounds segment
        b"\xff\xd8\xff\xe0\x00\x01\xff\xd9",  # invalid short segment
        frame(precision=12),
        frame() + frame(),  # second image
        frame(entropy=b"\xff\xc0\x00\x0b"),  # hidden second SOF
        frame(entropy=b"\xff\xda\x00\x08"),  # second scan
        frame()[:-1],
        b"\xff\xd8" + b"\xff\xfe\x00\x02" * 257 + frame()[2:],
    ],
)
def test_malformed_or_ambiguous_image_rejected(value):
    assert baseline_dimensions(value) is None
