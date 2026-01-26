#!/usr/bin/env python3
"""Anonymise chat HTML files by replacing message content with labelled lorem ipsum.

Each message gets a unique label like [OPENAI-USER-1] or [CLAUDE-ASST-3] so extraction
can be validated.

Usage: uv run scripts/anonymise_chats.py
"""

from pathlib import Path

from bs4 import BeautifulSoup
from lorem_text import lorem


def get_lorem() -> str:
    """Generate a paragraph of lorem ipsum."""
    return lorem.paragraphs(1)


OUTPUT_DIR = Path(__file__).parent.parent / "output"


def has_class(tag, cls: str) -> bool:
    """Check if tag has a class containing the substring."""
    classes = tag.get("class", [])
    return any(cls in c for c in classes)


def anonymise_openai(html: str, source_name: str) -> str:
    """Anonymise OpenAI chat HTML."""
    soup = BeautifulSoup(html, "html.parser")
    user_count = 0
    asst_count = 0

    for msg in soup.find_all(attrs={"data-message-author-role": True}):
        role = msg["data-message-author-role"]
        if role == "user":
            user_count += 1
            label = f"[{source_name.upper()}-USER-{user_count}]"
            # Find the whitespace-pre-wrap div or innermost content
            content_div = msg.find(
                class_=lambda c: c and "whitespace-pre-wrap" in c if c else False
            )
            if content_div:
                content_div.string = f"{label} {get_lorem()}"
        elif role == "assistant":
            asst_count += 1
            label = f"[{source_name.upper()}-ASST-{asst_count}]"
            # Find markdown div
            content_div = msg.find(
                class_=lambda c: c and "markdown" in c if c else False
            )
            if content_div:
                # Clear and replace with simple paragraph
                content_div.clear()
                p = soup.new_tag("p")
                p.string = f"{label} {get_lorem()}"
                content_div.append(p)

    print(f"  {source_name}: {user_count} user, {asst_count} assistant messages")
    return str(soup)


def anonymise_claude(html: str, source_name: str) -> str:
    """Anonymise Claude chat HTML."""
    soup = BeautifulSoup(html, "html.parser")
    user_count = 0
    asst_count = 0

    # User messages
    for msg in soup.find_all(attrs={"data-testid": "user-message"}):
        user_count += 1
        label = f"[{source_name.upper()}-USER-{user_count}]"
        msg.string = f"{label} {get_lorem()}"

    # Assistant messages - font-claude-response
    for msg in soup.find_all(
        "div", class_=lambda c: c and "font-claude-response" in c if c else False
    ):
        asst_count += 1
        label = f"[{source_name.upper()}-ASST-{asst_count}]"
        msg.clear()
        p = soup.new_tag("p")
        p.string = f"{label} {get_lorem()}"
        msg.append(p)

    print(f"  {source_name}: {user_count} user, {asst_count} assistant messages")
    return str(soup)


def anonymise_gemini(html: str, source_name: str) -> str:
    """Anonymise Gemini chat HTML."""
    soup = BeautifulSoup(html, "html.parser")
    user_count = 0
    asst_count = 0

    # User queries
    for msg in soup.find_all(
        "div", class_=lambda c: c and "user-query" in c if c else False
    ):
        # Find the query-text or query-content
        content = msg.find(
            class_=lambda c: c and ("query-text" in c or "query-content" in c)
            if c
            else False
        )
        if content:
            user_count += 1
            label = f"[{source_name.upper()}-USER-{user_count}]"
            content.string = f"{label} {get_lorem()}"

    # Response containers
    for msg in soup.find_all(
        "div", class_=lambda c: c and "response-container" in c if c else False
    ):
        asst_count += 1
        label = f"[{source_name.upper()}-ASST-{asst_count}]"
        # Find and replace the first text-bearing element
        for child in msg.descendants:
            child_str = getattr(child, "string", None)
            if child_str and len(child_str.strip()) > 20:
                child.string = f"{label} {get_lorem()}"  # type: ignore[union-attr]
                break

    print(f"  {source_name}: {user_count} user, {asst_count} assistant messages")
    return str(soup)


def anonymise_aistudio(html: str, source_name: str) -> str:
    """Anonymise AI Studio chat HTML."""
    soup = BeautifulSoup(html, "html.parser")
    user_count = 0
    asst_count = 0

    for turn in soup.find_all(
        "div", class_=lambda c: c and "chat-turn-container" in c if c else False
    ):
        classes = turn.get("class") or []
        is_user = any("user" in c for c in classes)
        is_model = any("model" in c for c in classes)

        if is_user:
            user_count += 1
            label = f"[{source_name.upper()}-USER-{user_count}]"
        elif is_model:
            asst_count += 1
            label = f"[{source_name.upper()}-ASST-{asst_count}]"
        else:
            continue

        # Find ms-cmark-node and replace its content
        cmark = turn.find("ms-cmark-node")
        if cmark:
            text = cmark.get_text(strip=True)
            if text:
                cmark.clear()
                cmark.string = f"{label} {get_lorem()}"

    print(f"  {source_name}: {user_count} user, {asst_count} assistant messages")
    return str(soup)


def anonymise_scienceos(html: str, source_name: str) -> str:
    """Anonymise ScienceOS chat HTML."""
    soup = BeautifulSoup(html, "html.parser")
    user_count = 0
    asst_count = 0

    # Bot responses have prose class
    for msg in soup.find_all(
        "div",
        class_=lambda c: c and "prose" in c and "not-prose" not in " ".join(c)
        if c
        else False,
    ):
        asst_count += 1
        label = f"[{source_name.upper()}-ASST-{asst_count}]"
        msg.clear()
        p = soup.new_tag("p")
        p.string = f"{label} {get_lorem()}"
        msg.append(p)

    # User messages - look for elements with _prompt_ in class (user input display)
    # Note: BeautifulSoup class_ lambda doesn't work reliably, so filter manually
    for elem in soup.find_all(True):
        classes = elem.get("class") or []
        if any("_prompt_" in c for c in classes):
            text = elem.get_text(strip=True)
            if text:
                user_count += 1
                label = f"[{source_name.upper()}-USER-{user_count}]"
                elem.string = f"{label} {get_lorem()}"

    print(f"  {source_name}: {user_count} user, {asst_count} assistant messages")
    return str(soup)


def main():
    # Clean up old anonymised files first
    for old_file in OUTPUT_DIR.glob("chat_*_anon.html"):
        old_file.unlink()
        print(f"Removed {old_file.name}")

    print("Anonymising chat HTML files...")

    # Process each source type
    processors = {
        "openai": anonymise_openai,
        "claude": anonymise_claude,
        "gemini": anonymise_gemini,
        "aistudio": anonymise_aistudio,
        "scienceos": anonymise_scienceos,
    }

    for chat_file in OUTPUT_DIR.glob("chat_*.html"):
        # Skip already anonymised files
        if "_anon" in chat_file.stem:
            continue

        # Determine source from filename
        name = chat_file.stem  # e.g., "chat_openai_simple"
        parts = name.split("_")
        if len(parts) < 2:
            continue
        source = parts[1]  # e.g., "openai"
        source_name = "_".join(parts[1:])  # e.g., "openai_simple"

        if source not in processors:
            print(f"  Skipping {chat_file.name} (unknown source: {source})")
            continue

        print(f"Processing {chat_file.name}...")
        html = chat_file.read_text()
        anonymised = processors[source](html, source_name)

        # Write to new file with _anon suffix
        output_file = chat_file.with_stem(chat_file.stem + "_anon")
        output_file.write_text(anonymised)
        print(f"  → {output_file.name}")


if __name__ == "__main__":
    main()
