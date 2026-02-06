# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the AddonManager.

import gzip
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import addonmanager_icon_utilities as iu

from PySideWrapper import QtCore, QtGui


class TestIsValidXML(unittest.TestCase):
    """Test the icon utilities. Many of these must be run with a QApplication running because the
    functions use some features of QIcon that require it."""

    def test_is_valid_xml_good_inputs(self):
        valid_xml_entries = [
            b"<svg/>",
            b'<?xml version="1.0" encoding="UTF-8"?><svg></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg"><g><path d="M0 0 L10 10"/></g></svg>',
            b'<root><child attr="value">text</child><empty/></root>',
            "<svg><text>Hello &amp; world</text></svg>".encode("utf-8"),
            "<root><![CDATA[<not>parsed</not> but kept as text]]></root>".encode("utf-8"),
            (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<svg xmlns='http://www.w3.org/2000/svg'>"
                "<!-- comment inside root -->"
                "<g><title>t</title></g>"
                "</svg>"
            ).encode("utf-8"),
        ]
        for entry in valid_xml_entries:
            with self.subTest(entry=entry):
                self.assertTrue(iu.is_valid_xml(entry))

    def test_is_valid_xml_bad_inputs(self):
        invalid_xml_entries = [
            b"",  # empty -> ParseError
            b"<svg>",  # unclosed tag -> ParseError
            b"<svg><g></svg>",  # mismatched tags -> ParseError
            b"<?xml version='1.0'?><svg><x></svg>",  # unclosed child -> ParseError
            b"<svg><",  # truncated -> ParseError
            b"not xml at all",  # plain text -> ParseError
            b"<svg>\x00</svg>",  # NUL char -> ParseError
            b"\xff",  # invalid UTF-8 -> UnicodeDecodeError
            b"\x80abc",  # invalid UTF-8 lead byte -> UnicodeDecodeError
            b"\xfe\xff<\x00s\x00v\x00g\x00/\x00>\x00",  # UTF-16LE/BE bytes, not UTF-8 -> UnicodeDecodeError
            b'<?xml version="1.0" encoding="ISO-8859-1"?><svg>\xa0</svg>',  # claims latin-1 but decoded as UTF-8 -> UnicodeDecodeError
        ]
        for entry in invalid_xml_entries:
            with self.subTest(entry=entry):
                self.assertFalse(iu.is_valid_xml(entry))


class TestIsSvgBytes(unittest.TestCase):

    def test_is_svg_bytes_detects_valid_svg(self):
        raw = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'
        with patch("addonmanager_icon_utilities.is_valid_xml", return_value=True) as m:
            self.assertTrue(iu.is_svg_bytes(raw))
            m.assert_called_once_with(raw)  # full bytes passed through

    def test_is_svg_bytes_raises_on_svgish_but_invalid(self):
        raw = b'<svg xmlns="http://www.w3.org/2000/svg"><unclosed>'
        with patch("addonmanager_icon_utilities.is_valid_xml", return_value=False):
            with self.assertRaises(iu.BadIconData):
                iu.is_svg_bytes(raw)

    def test_is_svg_bytes_returns_false_for_non_svg_header(self):
        raw = b"\x89PNG\r\n\x1a\n\x00\x00\x00IHDR"  # clearly not SVG header
        with patch("addonmanager_icon_utilities.is_valid_xml") as m:
            self.assertFalse(iu.is_svg_bytes(raw))
            m.assert_not_called()  # no XML parse if header doesn't match

    def test_is_svg_bytes_sniffs_only_first_MAX_ICON_BYTES(self):
        # Place "<svg" after the sniff window; should NOT be detected.
        raw = b"A" * 100 + b"<svg></svg>"
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", 64), patch(
            "addonmanager_icon_utilities.is_valid_xml"
        ) as m:
            self.assertFalse(iu.is_svg_bytes(raw))
            m.assert_not_called()

    def test_is_svg_bytes_calls_is_valid_xml_with_full_raw_not_head(self):
        # Ensure the function validates the full payload, not just the header slice.
        raw = (
            b'<?xml version="1.0"?>'
            b'<svg xmlns="http://www.w3.org/2000/svg">' + b"A" * 500 + b"</svg>"
        )
        calls = []

        def fake_is_valid_xml(arg):
            calls.append(arg)
            return True

        with patch(
            "addonmanager_icon_utilities.is_valid_xml", side_effect=fake_is_valid_xml
        ), patch("addonmanager_icon_utilities.MAX_ICON_BYTES", 32):
            self.assertTrue(iu.is_svg_bytes(raw))
            self.assertIs(calls[0], raw)
            self.assertEqual(len(calls[0]), len(raw))


class TestIsGzip(unittest.TestCase):

    def test_is_gzip_true_minimal(self):
        self.assertTrue(iu.is_gzip(b"\x1f\x8b"))

    def test_is_gzip_true_with_extra_bytes(self):
        # Typical gzip header starts with 0x1f 0x8b 0x08 ...
        self.assertTrue(iu.is_gzip(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03extra"))

    def test_is_gzip_false_empty(self):
        self.assertFalse(iu.is_gzip(b""))

    def test_is_gzip_false_one_byte(self):
        self.assertFalse(iu.is_gzip(b"\x1f"))

    def test_is_gzip_false_wrong_first_byte(self):
        self.assertFalse(iu.is_gzip(b"\x00\x8b"))

    def test_is_gzip_false_wrong_second_byte(self):
        self.assertFalse(iu.is_gzip(b"\x1f\x00"))

    def test_is_gzip_false_swapped_bytes(self):
        self.assertFalse(iu.is_gzip(b"\x8b\x1f"))

    def test_is_gzip_false_zlib_header(self):
        # Common zlib/deflate header 0x78 0x9C should not be mistaken for gzip
        self.assertFalse(iu.is_gzip(b"\x78\x9c\x00\x00"))


def gz(payload: bytes) -> bytes:
    bio = io.BytesIO()
    with gzip.GzipFile(fileobj=bio, mode="wb") as f:
        f.write(payload)
    return bio.getvalue()


class TestDecompressGzipLimited(unittest.TestCase):
    def test_small_valid_within_ratio(self):
        raw = b"hello world"
        data = gz(raw)
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", len(data)), patch(
            "addonmanager_icon_utilities.MAX_GZIP_EXPANSION_RATIO", 16
        ), patch("addonmanager_icon_utilities.MAX_GZIP_OUTPUT_ABS", 512 * 1024):
            self.assertEqual(iu.decompress_gzip_limited(data), raw)

    def test_respects_input_cap_inclusive(self):
        raw = b"a" * 64
        data = gz(raw)
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", len(data)):
            self.assertEqual(iu.decompress_gzip_limited(data), raw)

    def test_rejects_when_compressed_exceeds_cap(self):
        raw = b"a" * 64
        data = gz(raw)
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", len(data) - 1):
            self.assertIsNone(iu.decompress_gzip_limited(data))

    def test_overflows_ratio_returns_none(self):
        # Choose caps so ratio*len(data) < len(uncompressed)
        payload = b"x" * 129
        data = gz(payload)
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", len(data)), patch(
            "addonmanager_icon_utilities.MAX_GZIP_EXPANSION_RATIO", 1
        ), patch(
            "addonmanager_icon_utilities.MAX_GZIP_OUTPUT_ABS", 10**9
        ):  # let ratio drive the bound
            self.assertIsNone(iu.decompress_gzip_limited(data))

    def test_overflows_absolute_cap_returns_none(self):
        payload = b"x" * 600_000  # >512 KiB default abs cap
        data = gz(payload)
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", len(data)), patch(
            "addonmanager_icon_utilities.MAX_GZIP_EXPANSION_RATIO", 1000
        ), patch("addonmanager_icon_utilities.MAX_GZIP_OUTPUT_ABS", 512 * 1024):
            self.assertIsNone(iu.decompress_gzip_limited(data))

    def test_truncated_or_non_gzip_returns_none(self):
        payload = b"abcdef"
        data = gz(payload)
        truncated = data[:-2]
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", len(data)):
            self.assertIsNone(iu.decompress_gzip_limited(truncated))
            self.assertIsNone(iu.decompress_gzip_limited(b"not-gzip"))

    def test_type_error_returns_none(self):
        with patch("addonmanager_icon_utilities.MAX_ICON_BYTES", 100):
            self.assertIsNone(iu.decompress_gzip_limited(None))  # type: ignore[arg-type]


# Solid “fills-everything” SVG: easy to assert non-transparent pixels.
SOLID_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
    b'<rect x="0" y="0" width="16" height="16" fill="#000000"/></svg>'
)

# Empty SVG: renders nothing; pixmap should remain fully transparent.
EMPTY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"></svg>'


def alpha_at(pm: QtGui.QPixmap, x: int, y: int) -> int:
    img = pm.toImage()
    return img.pixelColor(x, y).alpha()


class TestSvgIconEngine(unittest.TestCase):
    def test_pixmap_size_and_opaque_content(self):
        eng = iu.SvgIconEngine(SOLID_SVG)
        size = QtCore.QSize(32, 32)
        pm = eng.pixmap(size, QtGui.QIcon.Normal, QtGui.QIcon.Off)  # type: ignore[arg-type]

        self.assertEqual(pm.size(), size)
        self.assertTrue(pm.hasAlphaChannel())
        self.assertGreater(alpha_at(pm, 16, 16), 0)  # center is painted

    def test_pixmap_starts_transparent_when_svg_empty(self):
        eng = iu.SvgIconEngine(EMPTY_SVG)
        pm = eng.pixmap(QtCore.QSize(20, 20), QtGui.QIcon.Normal, QtGui.QIcon.Off)  # type: ignore[arg-type]

        # Spot-check a few pixels; all should be transparent
        self.assertEqual(alpha_at(pm, 10, 10), 0)
        self.assertEqual(alpha_at(pm, 0, 0), 0)
        self.assertEqual(alpha_at(pm, 19, 19), 0)

    def test_paint_respects_rect(self):
        eng = iu.SvgIconEngine(SOLID_SVG)
        pm = QtGui.QPixmap(40, 40)
        pm.fill(QtCore.Qt.transparent)  # type: ignore[arg-type]

        painter = QtGui.QPainter(pm)
        rect = QtCore.QRect(10, 10, 20, 20)  # paint into the middle 20x20 square
        eng.paint(painter, rect, QtGui.QIcon.Normal, QtGui.QIcon.Off)  # type: ignore[arg-type]
        painter.end()

        # Outside the rect stays transparent
        self.assertEqual(alpha_at(pm, 5, 5), 0)
        self.assertEqual(alpha_at(pm, 35, 35), 0)

        # Inside the rect is painted (non-transparent)
        self.assertGreater(alpha_at(pm, 20, 20), 0)

    def test_renderer_is_valid(self):
        eng = iu.SvgIconEngine(SOLID_SVG)
        self.assertTrue(eng.renderer.isValid())


def _qpix_icon():
    pm = QtGui.QPixmap(2, 2)
    pm.fill(QtCore.Qt.white)  # type: ignore[arg-type]
    return QtGui.QIcon(pm)


def _valid_xpm_bytes():
    img = QtGui.QImage(2, 2, QtGui.QImage.Format_ARGB32)  # type: ignore[arg-type]
    img.fill(QtCore.Qt.black)  # type: ignore[arg-type]
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)  # type: ignore[arg-type]
    img.save(buf, "XPM")
    return bytes(buf.data())  # type: ignore[arg-type]


class TestGetIconForAddon(unittest.TestCase):
    def setUp(self):
        # Keep tests deterministic & small
        self.maxbytes = patch("addonmanager_icon_utilities.MAX_ICON_BYTES", 16).start()
        self.addCleanup(patch.stopall)

        # Reset cache every test
        iu.cached_default_icons.clear()

        # Common mocks
        self.warn = patch(
            "addonmanager_icon_utilities.fci.Console.PrintWarning", autospec=True
        ).start()
        self.icon_from = patch("addonmanager_icon_utilities.icon_from_bytes", autospec=True).start()

        # Handy enum values
        self.KIND_MACRO = iu.Addon.Kind.MACRO
        self.KIND_WORKBENCH = iu.Addon.Kind.WORKBENCH

    # --- Early return / update flag ---

    def test_returns_existing_icon_when_not_updating(self):
        existing = _qpix_icon()
        addon = SimpleNamespace(
            icon=existing,
            icon_data=None,
            macro=None,
            repo_type=self.KIND_WORKBENCH,
            display_name="A",
        )
        out = iu.get_icon_for_addon(addon, update=False)  # type: ignore[arg-type]
        self.assertIs(out, existing)
        self.icon_from.assert_not_called()
        self.warn.assert_not_called()

    def test_update_true_ignores_existing_and_uses_icon_data(self):
        existing = _qpix_icon()
        new_icon = _qpix_icon()
        self.icon_from.return_value = new_icon
        data = b"x" * 8
        addon = SimpleNamespace(
            icon=existing,
            icon_data=data,
            macro=None,
            repo_type=self.KIND_WORKBENCH,
            display_name="A",
        )
        out = iu.get_icon_for_addon(addon, update=True)  # type: ignore[arg-type]
        self.assertIs(out, new_icon)
        self.assertIs(addon.icon, new_icon)
        self.icon_from.assert_called_once_with(data)
        self.warn.assert_not_called()

    def test_addon_icon_data_under_limit_success(self):
        data = b"x" * 8
        result_icon = _qpix_icon()
        self.icon_from.return_value = result_icon

        addon = SimpleNamespace(
            icon=None, icon_data=data, macro=None, repo_type=self.KIND_WORKBENCH, display_name="Pkg"
        )
        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        self.assertIs(out, result_icon)
        self.assertIs(addon.icon, result_icon)
        self.warn.assert_not_called()

    def test_addon_icon_data_over_limit_warns_then_uses_icon(self):
        data = b"x" * 20  # > MAX_ICON_BYTES (patched to 16)
        result_icon = _qpix_icon()
        self.icon_from.return_value = result_icon

        addon = SimpleNamespace(
            icon=None, icon_data=data, macro=None, repo_type=self.KIND_WORKBENCH, display_name="Pkg"
        )
        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        self.assertIs(out, result_icon)
        self.warn.assert_called_once()
        self.assertIn("too large", self.warn.call_args[0][0].lower())

    def test_addon_icon_data_invalid_warns_and_falls_to_default(self):
        self.icon_from.side_effect = iu.BadIconData("nope")
        data = b"x" * 8
        addon = SimpleNamespace(
            icon=None, icon_data=data, macro=None, repo_type=self.KIND_WORKBENCH, display_name="Pkg"
        )

        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        # Default icons initialized and workbench → "package"
        self.assertIn("package", iu.cached_default_icons)
        self.assertIs(out, iu.cached_default_icons["package"])
        self.warn.assert_called_once()
        self.assertIn("invalid", self.warn.call_args[0][0].lower())

    def test_macro_icon_data_under_limit_success(self):
        self.icon_from.return_value = _qpix_icon()
        macro = SimpleNamespace(icon_data=b"x" * 8, xpm=None, author="Auth")
        addon = SimpleNamespace(
            icon=None, icon_data=None, macro=macro, repo_type=self.KIND_MACRO, display_name="Macro"
        )
        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        self.assertIs(out, addon.icon)
        self.icon_from.assert_called_once_with(macro.icon_data)
        self.warn.assert_not_called()

    def test_macro_icon_data_over_limit_warns_then_uses_icon(self):
        self.icon_from.return_value = _qpix_icon()
        macro = SimpleNamespace(icon_data=b"x" * 64, xpm=None, author="Auth")
        addon = SimpleNamespace(
            icon=None, icon_data=None, macro=macro, repo_type=self.KIND_MACRO, display_name="Macro"
        )
        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        self.assertIs(out, addon.icon)
        self.warn.assert_called_once()
        self.assertIn("too large", self.warn.call_args[0][0].lower())

    def test_macro_icon_data_invalid_warns_then_falls_through(self):
        self.icon_from.side_effect = iu.BadIconData("boom")
        macro = SimpleNamespace(icon_data=b"x" * 8, xpm=None, author="Auth")
        addon = SimpleNamespace(
            icon=None, icon_data=None, macro=macro, repo_type=self.KIND_MACRO, display_name="Macro"
        )
        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        # With invalid macro icon_data and no XPM, we fall to defaults (macro kind)
        self.assertIn("macro", iu.cached_default_icons)
        self.assertIs(out, iu.cached_default_icons["macro"])
        self.warn.assert_called_once()
        self.assertIn("invalid", self.warn.call_args[0][0].lower())

    def test_macro_xpm_invalid_warns_and_fallback(self):
        macro = SimpleNamespace(icon_data=None, xpm="not-xpm", author="Auth")
        addon = SimpleNamespace(
            icon=None, icon_data=None, macro=macro, repo_type=self.KIND_MACRO, display_name="Macro"
        )
        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        self.assertIs(out, iu.cached_default_icons["macro"])
        self.assertTrue(self.warn.called)
        self.assertIn("invalid", self.warn.call_args[0][0].lower())

    def test_macro_xpm_valid_returns_icon(self):
        macro = SimpleNamespace(
            icon_data=None, xpm=_valid_xpm_bytes().decode("utf-8"), author="Auth"
        )
        addon = SimpleNamespace(
            icon=None, icon_data=None, macro=macro, repo_type=self.KIND_MACRO, display_name="Macro"
        )
        out = iu.get_icon_for_addon(addon)  # type: ignore[arg-type]
        self.assertIsInstance(out, QtGui.QIcon)
        self.assertFalse(out.isNull())

    def test_defaults_initialized_once_and_selected_by_repo_type(self):
        # First call: init cache and return "package" for WORKBENCH
        addon1 = SimpleNamespace(
            icon=None, icon_data=None, macro=None, repo_type=self.KIND_WORKBENCH, display_name="WB"
        )
        a1 = iu.get_icon_for_addon(addon1)  # type: ignore[arg-type]
        self.assertIs(a1, iu.cached_default_icons["package"])

        # Second call: same cache, MACRO → "macro"
        addon2 = SimpleNamespace(
            icon=None, icon_data=None, macro=None, repo_type=self.KIND_MACRO, display_name="M"
        )
        a2 = iu.get_icon_for_addon(addon2)  # type: ignore[arg-type]
        self.assertIs(a2, iu.cached_default_icons["macro"])

        # Third: unknown kind → "package"
        addon3 = SimpleNamespace(
            icon=None, icon_data=None, macro=None, repo_type=None, display_name="Other"
        )
        a3 = iu.get_icon_for_addon(addon3)  # type: ignore[arg-type]
        self.assertIs(a3, iu.cached_default_icons["package"])
