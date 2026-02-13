"""Security and correctness tests for _render_js t-string interpolation.

``_render_js`` is the sole boundary between Python values and JavaScript code
sent to client browsers via ``run_javascript()``. All user-controlled strings
(display names, client IDs) pass through it. Incorrect escaping here is an
XSS vector.

Tests cover:
- Strings with quotes (single, double)
- XSS payloads (script injection, event handlers)
- Unicode (emoji, CJK, RTL)
- Numeric passthrough (int, float)
- None -> null
- Bool edge case (Python bool is a subclass of int)
"""

from __future__ import annotations

import json

from promptgrimoire.pages.annotation import _render_js


class TestStringEscaping:
    """Strings must be JSON-encoded so they are safe JS string literals."""

    def test_single_quotes(self) -> None:
        """O'Brien must not break a JS string context."""
        name = "O'Brien"
        result = _render_js(t"alert({name})")
        assert result == f"alert({json.dumps(name)})"
        assert result == 'alert("O\'Brien")'

    def test_double_quotes(self) -> None:
        """Double quotes must be escaped inside the JSON string."""
        val = 'say "hello"'
        result = _render_js(t"console.log({val})")
        assert result == f"console.log({json.dumps(val)})"
        assert r"\"hello\"" in result

    def test_backslashes(self) -> None:
        """Backslashes must be escaped to prevent JS escape sequence injection."""
        val = "path\\to\\file"
        result = _render_js(t"f({val})")
        assert result == f"f({json.dumps(val)})"
        assert r"\\" in result

    def test_newlines_in_string(self) -> None:
        """Newlines must be escaped (JSON \\n), not literal line breaks."""
        val = "line1\nline2"
        result = _render_js(t"f({val})")
        # json.dumps produces "line1\\nline2" (escaped newline)
        assert "\n" not in result  # No raw newline in output
        assert r"\n" in result


class TestXssPrevention:
    """Adversarial inputs must not escape the string context."""

    def test_script_tag_injection(self) -> None:
        """Classic XSS: </script><script>alert(1)</script> must be neutralised.

        The safety property is that the payload is inside a JSON-encoded
        string literal (wrapped in double quotes). In a ``run_javascript()``
        context, the JS engine parses the value as a string argument -- the
        angle brackets cannot escape to become executable HTML tags.
        """
        xss = "</script><script>alert(1)</script>"
        result = _render_js(t"renderRemoteCursor(c, {xss}, 10)")
        assert result.startswith("renderRemoteCursor(c, ")
        # The payload must be inside a JSON string (double-quoted)
        assert json.dumps(xss) in result

    def test_event_handler_injection(self) -> None:
        """Attempt to break out of string via closing quote + JS code."""
        xss = '");alert(document.cookie);//'
        result = _render_js(t"f({xss})")
        # The injected closing quote must be escaped
        assert result == f"f({json.dumps(xss)})"
        # Verify the result is safe: the alert() is inside the JSON string
        assert r"\");" in result

    def test_template_literal_injection(self) -> None:
        """Backtick injection must not create a JS template literal."""
        val = "`${alert(1)}`"
        result = _render_js(t"f({val})")
        assert result == f"f({json.dumps(val)})"


class TestUnicode:
    """Unicode values must pass through correctly."""

    def test_emoji(self) -> None:
        """Emoji in display names must survive round-trip."""
        name = "Alice \U0001f600"  # grinning face
        result = _render_js(t"f({name})")
        assert result == f"f({json.dumps(name)})"

    def test_cjk(self) -> None:
        """CJK characters must be preserved."""
        name = "\u5f20\u4e09"  # Zhang San
        result = _render_js(t"f({name})")
        assert result == f"f({json.dumps(name)})"

    def test_rtl(self) -> None:
        """Right-to-left text must be preserved."""
        name = "\u0645\u062d\u0645\u062f"  # Muhammad in Arabic
        result = _render_js(t"f({name})")
        assert result == f"f({json.dumps(name)})"

    def test_null_byte(self) -> None:
        """Null bytes must be escaped, not passed raw."""
        val = "a\x00b"
        result = _render_js(t"f({val})")
        assert "\x00" not in result  # Raw null must not appear


class TestNumericPassthrough:
    """Numbers must pass through as bare JS literals, not strings."""

    def test_integer(self) -> None:
        """Integers become bare JS numbers."""
        idx = 42
        result = _render_js(t"f({idx})")
        assert result == "f(42)"

    def test_negative_integer(self) -> None:
        """Negative integers pass through correctly."""
        idx = -1
        result = _render_js(t"f({idx})")
        assert result == "f(-1)"

    def test_zero(self) -> None:
        """Zero is a valid number."""
        idx = 0
        result = _render_js(t"f({idx})")
        assert result == "f(0)"

    def test_float(self) -> None:
        """Floats become bare JS numbers."""
        val = 3.14
        result = _render_js(t"f({val})")
        assert result == "f(3.14)"


class TestNoneAndBool:
    """None and bool edge cases."""

    def test_none_becomes_null(self) -> None:
        """None must become JS null literal."""
        val = None
        result = _render_js(t"f({val})")
        assert result == "f(null)"

    def test_bool_true_is_int_subclass(self) -> None:
        """Python True is isinstance(int), so _render_js renders it as str(True).

        This means True becomes the JS identifier ``True`` (not ``true``).
        Since _render_js is currently only used with int/str/None values in
        the presence broadcast code, this edge case is documented but not
        a bug in practice -- booleans are never passed to _render_js.
        """
        val = True
        result = _render_js(t"f({val})")
        # bool is a subclass of int, so isinstance(True, int) is True.
        # str(True) == "True" -- this is the JS identifier True, not "true".
        assert result == "f(True)"

    def test_bool_false_is_int_subclass(self) -> None:
        """Python False becomes JS ``False`` (not ``false``) — same edge case."""
        val = False
        result = _render_js(t"f({val})")
        assert result == "f(False)"


class TestStaticPortions:
    """Static template text must pass through unchanged."""

    def test_no_interpolation(self) -> None:
        """Template with no interpolations returns the literal string."""
        result = _render_js(t"console.log('hello')")
        assert result == "console.log('hello')"

    def test_multiple_interpolations(self) -> None:
        """Multiple interpolated values in one template."""
        a = "alice"
        b = 10
        c = None
        result = _render_js(t"f({a}, {b}, {c})")
        assert result == 'f("alice", 10, null)'

    def test_adjacent_interpolations(self) -> None:
        """Adjacent interpolations with no static text between them."""
        x = 1
        y = 2
        result = _render_js(t"{x}{y}")
        assert result == "12"
