#!/usr/bin/env python3
"""Spike S: Test selectolax text node iteration for char span injection.

Run: uv run python scripts/spike_selectolax_text.py

Success criteria:
1. Can iterate over text nodes in HTML
2. Can wrap each character in a span
3. Preserves HTML structure (headings, lists, tables)
4. Handles whitespace correctly
5. Handles <br> tags as newline chars
"""

from selectolax.lexbor import LexborHTMLParser


def inject_char_spans(html: str) -> tuple[str, int]:
    """Walk HTML DOM, wrap each text character in data-char-index span.

    Returns:
        (html_with_spans, total_char_count)
    """
    tree = LexborHTMLParser(html)
    char_index = 0

    # Find all text nodes
    def process_node(node) -> None:
        nonlocal char_index

        if node.tag == "-text":
            text = node.text() or ""
            if not text:
                return

            # Build replacement HTML with char spans
            spans = []
            for char in text:
                spans.append(
                    f'<span class="char" data-char-index="{char_index}">{char}</span>'
                )
                char_index += 1

            # Note: This is a simplified approach - real implementation needs
            # to handle the replacement properly
            print(
                f"Text node: {text[:50]!r} -> {len(text)} chars "
                f"starting at {char_index - len(text)}"
            )

    # Walk the tree
    if tree.root is not None:
        for node in tree.root.traverse():
            process_node(node)

    return tree.html or "", char_index


def test_simple() -> None:
    """Test with simple HTML."""
    html = "<p>Hello <strong>world</strong>!</p>"
    print("\n=== Simple HTML ===")
    print(f"Input: {html}")
    _, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_nested() -> None:
    """Test with nested structure."""
    html = """
    <div>
        <h1>Title</h1>
        <p>First <em>paragraph</em> here.</p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
    </div>
    """
    print("\n=== Nested HTML ===")
    _, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_whitespace() -> None:
    """Test whitespace handling."""
    html = "<p>Word1   Word2\n\tWord3</p>"
    print("\n=== Whitespace ===")
    print(f"Input: {html!r}")
    _, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_br_tags() -> None:
    """Test <br> tag handling."""
    html = "<p>Line 1<br>Line 2<br/>Line 3</p>"
    print("\n=== BR tags ===")
    print(f"Input: {html}")
    _, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_chatbot_sample() -> None:
    """Test with realistic chatbot HTML."""
    html = """
    <div class="conversation">
        <div class="turn user">
            <p>What is the capital of France?</p>
        </div>
        <div class="turn assistant">
            <p>The capital of France is <strong>Paris</strong>.</p>
            <p>Paris is known for:</p>
            <ul>
                <li>The Eiffel Tower</li>
                <li>The Louvre Museum</li>
                <li>Notre-Dame Cathedral</li>
            </ul>
        </div>
    </div>
    """
    print("\n=== Chatbot Sample ===")
    _, count = inject_char_spans(html)
    print(f"Char count: {count}")


if __name__ == "__main__":
    print("Spike S: selectolax Text Node Iteration")
    print("=" * 50)

    test_simple()
    test_nested()
    test_whitespace()
    test_br_tags()
    test_chatbot_sample()

    print("\n" + "=" * 50)
    print("Evaluation checklist:")
    print("[ ] Text nodes discovered correctly")
    print("[ ] Character indices are sequential")
    print("[ ] Whitespace characters counted")
    print("[ ] Structure preserved")
    print("[ ] BR tags handled")
