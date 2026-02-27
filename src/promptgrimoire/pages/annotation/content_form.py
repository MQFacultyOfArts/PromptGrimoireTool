"""Content paste/upload form for the annotation page.

Handles the add-content UI with paste interception, file upload,
and content type detection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from nicegui import events, ui

from promptgrimoire.config import get_settings
from promptgrimoire.db.workspace_documents import add_document
from promptgrimoire.input_pipeline.html_input import (
    detect_content_type,
    process_input,
)
from promptgrimoire.input_pipeline.paragraph_map import (
    build_paragraph_map_for_json,
    detect_source_numbering,
)
from promptgrimoire.pages.dialogs import show_content_type_dialog

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.input_pipeline.html_input import ContentType

logger = logging.getLogger(__name__)


def _detect_type_from_extension(filename: str) -> ContentType | None:
    """Detect content type from file extension.

    Returns None if extension is not recognized.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext_to_type: dict[str, ContentType] = {
        "html": "html",
        "htm": "html",
        "rtf": "rtf",
        "docx": "docx",
        "pdf": "pdf",
        "txt": "text",
        "md": "text",
        "markdown": "text",
    }
    return ext_to_type.get(ext)


def _get_file_preview(
    content_bytes: bytes, detected_type: ContentType, filename: str
) -> str:
    """Get preview text for file content."""
    try:
        if detected_type in ("html", "text"):
            return content_bytes.decode("utf-8")[:500]
        return f"[Binary file: {filename}]"
    except UnicodeDecodeError:
        return f"[Binary file: {filename}]"


def _detect_paragraph_numbering(
    processed_html: str,
) -> tuple[bool, dict[str, int]]:
    """Detect paragraph numbering mode and build the paragraph map.

    Returns:
        Tuple of (auto_number_paragraphs, paragraph_map) ready for
        persistence (map keys converted to strings for JSON storage).
    """
    auto_number = not detect_source_numbering(processed_html)
    para_map = build_paragraph_map_for_json(processed_html, auto_number=auto_number)
    return auto_number, para_map


def _annotation_url(workspace_id: UUID) -> str:
    """Build the annotation page URL for a workspace."""
    return f"/annotation?{urlencode({'workspace_id': str(workspace_id)})}"


def _render_add_content_form(workspace_id: UUID) -> None:
    """Render the add content form with editor and file upload.

    Extracted from _render_workspace_view to reduce function complexity.
    """
    ui.label("Add content to annotate:").classes("mt-4 font-semibold")

    # HTML-aware editor for paste support (Quasar QEditor)
    content_input = (
        ui.editor(placeholder="Paste HTML content or type plain text here...")
        .classes("w-full min-h-32")
        .props('toolbar=[] data-testid="content-editor"')
    )  # Hide toolbar for minimal UI

    # Intercept paste, strip CSS client-side, store cleaned HTML.
    # Browsers include computed CSS (2.7MB for 32KB text). Strip it here.
    paste_var, platform_var = (
        f"_pastedHtml_{content_input.id}",
        f"_platformHint_{content_input.id}",
    )
    ui.add_body_html(f"""
    <script>
        window.{paste_var} = null;
        window.{platform_var} = null;
        document.addEventListener('DOMContentLoaded', function() {{
            const sel = '[id="c{content_input.id}"] .q-editor__content';
            const tryAttach = () => {{
                const editorEl = document.querySelector(sel);
                if (!editorEl) {{
                    setTimeout(tryAttach, 50);
                    return;
                }}
                console.log('[PASTE-INIT] Editor found, attaching handler');
                editorEl.addEventListener('paste', function(e) {{
                    let html = e.clipboardData.getData('text/html');
                    const text = e.clipboardData.getData('text/plain');
                    if (!html && !text) return;

                    e.preventDefault();
                    e.stopPropagation();

                    let cleaned = text || '';
                    const origSize = (html || text).length;

                    if (html) {{
                        // Capture raw paste HTML when
                        // ?debug_paste=1 is in the URL
                        if (new URLSearchParams(
                            location.search)
                            .get('debug_paste')) {{
                            window.__rawPasteHTML = html;
                            console.log('[PASTE] Raw HTML'
                                + ' saved ('
                                + html.length + ' chars)');
                        }}
                        // Inject speaker labels into raw HTML
                        // BEFORE stripping (attrs needed for
                        // detection get stripped later)
                        const mk = (role) =>
                            '<div data-speaker="' +
                            role + '"></div>';
                        const sp = {{}};
                        // Build attr/class regex helpers
                        const ar = (a) =>
                            '(<[^>]*' + a + '[^>]*>)';
                        const cr = (c) =>
                            '(<[^>]*class="[^"]*'
                            + c + '[^"]*"[^>]*>)';
                        if (/font-user-message/.test(html)) {{
                            window.{platform_var} = 'claude';
                            sp.u = new RegExp(
                                ar('data-testid="user-message"'),
                                'gi');
                            // Match ONLY the primary response
                            // container (class starts with
                            // font-claude-response). Exclude:
                            // - font-claude-response-body (per-para)
                            // - secondary divs where font-claude-
                            //   response appears mid-class (these
                            //   are UI chrome, not content)
                            sp.a = new RegExp(
                                '(<[^>]*class="'
                                + 'font-claude-response'
                                + '(?!-)[^"]*"[^>]*>)', 'gi');
                        }} else if (/conversation-turn/.test(html)) {{
                            window.{platform_var} = 'openai';
                            sp.u = new RegExp(
                                ar('data-message-author-role="user"'),
                                'gi');
                            sp.a = new RegExp(
                                ar('data-message-author-role="assistant"'),
                                'gi');
                        }} else if (/chat-turn-container/.test(html)) {{
                            window.{platform_var} = 'aistudio';
                            sp.u = new RegExp(
                                ar('data-turn-role="User"'),
                                'gi');
                            sp.a = new RegExp(
                                ar('data-turn-role="Model"'),
                                'gi');
                            if (window.Quasar)
                                Quasar.plugins.Notify.create({{
                                    message: 'AI Studio uses'
                                        + ' virtual scrolling'
                                        + ' \u2014 turns not'
                                        + ' visible when you'
                                        + ' copied will be'
                                        + ' empty. Scroll'
                                        + ' through the entire'
                                        + ' conversation before'
                                        + ' copying, or paste'
                                        + ' shorter segments.',
                                    type: 'warning',
                                    timeout: 15000,
                                    position: 'top',
                                }});
                        }} else if (/message-actions/.test(html)) {{
                            window.{platform_var} = 'gemini';
                            // Match only exact tags, not
                            // user-query-content etc.
                            // Negative lookahead (?!-) prevents
                            // matching user-query-content.
                            sp.u = new RegExp(
                                '(<user-query(?!-)(?:\\\\s[^>]*)?>)',
                                'gi');
                            sp.a = new RegExp(
                                '(<model-response(?!-)(?:\\\\s[^>]*)?>)',
                                'gi');
                        }} else if (/headroom/.test(html)) {{
                            window.{platform_var} = 'scienceos';
                            sp.u = new RegExp(
                                cr('_prompt_'), 'gi');
                            sp.a = new RegExp(
                                cr('_markdown_'), 'gi');
                        }} else if (/data-testid="playground-container"/.test(html)) {{
                            window.{platform_var} = 'openrouter';
                            sp.u = new RegExp(
                                ar('data-testid="user-message"'),
                                'gi');
                            sp.a = new RegExp(
                                ar('data-testid="assistant-message"'),
                                'gi');
                        }} else if (/chakra-card/.test(html)
                            && /chatcraft\\.org/i.test(html)) {{
                            window.{platform_var} = 'chatcraft';
                            // Speaker labels injected in iframe
                            // DOM section below — classification
                            // requires span[title] inspection
                        }} else if (/mw-parser-output|mw-body-content/.test(html)) {{
                            window.{platform_var} = 'wikimedia';
                            // No speaker labels — wiki content
                            // has no user/assistant turns
                        }}
                        if (sp.u) {{
                            html = html.replace(
                                sp.u, mk('user') + '$1');
                            html = html.replace(
                                sp.a, mk('assistant') + '$1');
                        }}
                        console.log('[PASTE] Platform:',
                            window.{platform_var});

                        // Parse HTML in hidden iframe
                        const iframe = document.createElement('iframe');
                        iframe.style.cssText = 'position:absolute;left:-9999px;';
                        document.body.appendChild(iframe);

                        iframe.contentDocument.open();
                        iframe.contentDocument.write(html);
                        iframe.contentDocument.close();

                        // P2: Collapse Claude thinking blocks
                        // BEFORE stripping classes — we need them
                        // to identify thinking containers.
                        if (window.{platform_var} === 'claude') {{
                            // Find the thinking toggle div by
                            // its text content and class
                            const iDoc = iframe.contentDocument;
                            iDoc.querySelectorAll('div').forEach(
                                el => {{
                                const cls = el.className || '';
                                const txt = el.textContent.trim();
                                // The toggle container has
                                // "Thought process" as text.
                                // It also contains time (18s)
                                // and an SVG icon.
                                if (/^Thought process/i.test(txt)
                                    && txt.length < 200) {{
                                    // Extract just "Thought process"
                                    // and time if present
                                    const timeM = txt.match(
                                        /(\\d+s)/);
                                    const label = 'Thought process'
                                        + (timeM
                                            ? ' ' + timeM[1] : '');
                                    const p = iDoc.createElement(
                                        'p');
                                    // Use data-thinking attr to
                                    // survive style stripping;
                                    // CSS handles presentation
                                    p.setAttribute(
                                        'data-thinking', 'true');
                                    p.textContent = '[' + label
                                        + ']';
                                    el.replaceWith(p);
                                }}
                            }});
                            // Also remove thinking CONTENT divs
                            // Claude wraps thinking text in divs
                            // with class containing "grid-cols"
                            // directly after the toggle
                        }}

                        // P4: Flatten KaTeX/MathML to plain text
                        // BEFORE stripping classes — we need
                        // .katex/.katex-display selectors.
                        {{
                            const iDoc = iframe.contentDocument;
                            iDoc.querySelectorAll(
                                '.katex, .katex-display'
                            ).forEach(el => {{
                                const ann = el.querySelector(
                                    'annotation[encoding='
                                    + '"application/x-tex"]'
                                );
                                const txt = ann
                                    ? ann.textContent
                                    : el.textContent;
                                const span =
                                    iDoc.createElement('span');
                                span.textContent = txt;
                                el.replaceWith(span);
                            }});
                            // Also handle bare <math> elements
                            iDoc.querySelectorAll('math')
                                .forEach(el => {{
                                const span =
                                    iDoc.createElement('span');
                                span.textContent = el.textContent;
                                el.replaceWith(span);
                            }});
                        }}

                        // Properties to preserve from inline styles
                        const keepStyleProps = ['margin-left', 'margin-right',
                            'margin-top', 'margin-bottom', 'text-indent',
                            'padding-left', 'padding-right'];
                        // Also handle margin/padding shorthand
                        const shorthandProps = ['margin', 'padding'];

                        // Strip style/script/img tags
                        iframe.contentDocument.querySelectorAll('style, script, img')
                            .forEach(el => el.remove());

                        // Strip MediaWiki chrome (if wikimedia platform)
                        if (window.{platform_var} === 'wikimedia') {{
                            const mwChrome = [
                                'nav', '.vector-header-container',
                                '.vector-main-menu-landmark',
                                '.vector-main-menu-container',
                                '.vector-sidebar', '.mw-portlet',
                                '#footer', '.mw-footer',
                                '.mw-editsection', '#toc', '.toc',
                                '#catlinks', '.vector-column-start',
                                '.vector-column-end', '#mw-navigation',
                                '.vector-page-toolbar',
                                '.vector-page-titlebar',
                                '.vector-sitenotice-container',
                                '.vector-dropdown',
                                '.vector-sticky-header',
                                '#p-search', '.vector-search-box',
                                '.vector-user-links',
                                '.mw-jump-link',
                                '#mw-aria-live-region',
                            ];
                            const iDoc = iframe.contentDocument;
                            for (const sel of mwChrome) {{
                                iDoc.querySelectorAll(sel)
                                    .forEach(el => el.remove());
                            }}
                        }}

                        // Strip OpenRouter chrome & metadata
                        if (window.{platform_var} === 'openrouter') {{
                            const iDoc = iframe.contentDocument;
                            iDoc.querySelectorAll(
                                '[data-testid="playground-composer"]'
                            ).forEach(el => el.remove());
                            // OpenRouter assistant-message structure:
                            //   child 0: timestamp (text-muted-foreground)
                            //   child 1: model link (<a> to /model/name)
                            //   child 2: content wrapper containing:
                            //     - thinking div (has border+rounded)
                            //     - response div (last child)
                            //   child 3: actions (empty)
                            iDoc.querySelectorAll(
                                '[data-testid="assistant-message"]'
                            ).forEach(msg => {{
                                // Extract model name from link URL
                                const modelLink = msg.querySelector(
                                    'a[href*="/openrouter.ai/"]');
                                if (modelLink) {{
                                    const href =
                                        modelLink.getAttribute(
                                            'href') || '';
                                    const parts =
                                        href.replace(/\\/+$/, '')
                                            .split('/');
                                    const name =
                                        parts[parts.length - 1];
                                    if (name) msg.setAttribute(
                                        'data-speaker-name', name);
                                }}
                                // Get direct children as array
                                const kids = Array.from(
                                    msg.querySelectorAll(':scope > *'));
                                // Remove timestamp (child 0),
                                // model link (child 1),
                                // actions (child 3+)
                                kids.forEach((child, i) => {{
                                    if (i !== 2) child.remove();
                                }});
                                // Inside content wrapper (child 2),
                                // keep only the LAST child (response)
                                // and remove thinking (first child)
                                const wrapper = msg.querySelector(
                                    ':scope > *');
                                if (wrapper) {{
                                    const wKids = Array.from(
                                        wrapper.querySelectorAll(
                                            ':scope > *'));
                                    if (wKids.length > 1) {{
                                        // Keep only the last child
                                        wKids.slice(0, -1).forEach(
                                            c => c.remove());
                                    }}
                                }}
                            }});
                        }}

                        // Strip OpenAI chrome & metadata
                        if (window.{platform_var} === 'openai') {{
                            const iDoc = iframe.contentDocument;
                            // Remove sr-only labels
                            iDoc.querySelectorAll('.sr-only')
                                .forEach(el => el.remove());
                            // Remove model request badges
                            // ("Request for GPT-5 Pro") and
                            // reasoning time badges
                            // ("Reasoned for Xm Ys")
                            iDoc.querySelectorAll('.flex.pb-2')
                                .forEach(el => {{
                                const txt = el.textContent.trim();
                                if (/Request for|Reasoned for/i
                                    .test(txt))
                                    el.remove();
                            }});
                            // Remove tool use badges
                            // ("Analysis errored", "Analyzed")
                            iDoc.querySelectorAll('button')
                                .forEach(el => {{
                                const txt = el.textContent.trim();
                                if (/^Analy/i.test(txt))
                                    el.remove();
                            }});
                        }}

                        // Strip AI Studio chrome & metadata
                        if (window.{platform_var} === 'aistudio') {{
                            const iDoc = iframe.contentDocument;
                            // Remove virtual-scroll spacer divs
                            // (empty divs with fixed pixel heights
                            // that create massive whitespace)
                            iDoc.querySelectorAll(
                                '.virtual-scroll-container > div'
                            ).forEach(el => {{
                                if (!el.className
                                    && !el.textContent.trim())
                                    el.remove();
                            }});
                            // Remove turn options menus
                            iDoc.querySelectorAll(
                                'ms-chat-turn-options')
                                .forEach(el => el.remove());
                            // Remove author labels
                            iDoc.querySelectorAll('.author-label')
                                .forEach(el => el.remove());
                            // Remove file/paste metadata chunks
                            // (filename, date, token counts)
                            iDoc.querySelectorAll('ms-file-chunk')
                                .forEach(el => el.remove());
                            // Remove thought section chrome
                            // (accordion labels, expand controls)
                            iDoc.querySelectorAll('ms-thought-chunk')
                                .forEach(el => el.remove());
                            // Remove toolbar (title, token count)
                            iDoc.querySelectorAll('ms-toolbar')
                                .forEach(el => el.remove());
                            // Remove token count badges
                            iDoc.querySelectorAll('.token-count')
                                .forEach(el => el.remove());
                        }}

                        // ChatCraft: classify speakers, then
                        // strip chrome (order matters — system
                        // prompt lives inside an accordion item)
                        if (window.{platform_var} === 'chatcraft') {{
                            const iDoc = iframe.contentDocument;
                            // 1. Classify ALL cards, set speaker
                            // name, strip card header metadata
                            // (name, date, avatar, URL)
                            iDoc.querySelectorAll('.chakra-card')
                                .forEach(card => {{
                                const spans = card.querySelectorAll(
                                    'span[title]');
                                if (spans.length === 0) return;
                                const title = spans[0]
                                    .getAttribute('title') || '';
                                let role;
                                if (title === 'System Prompt') {{
                                    role = 'system';
                                }} else if (
                                    title.indexOf(' ') === -1
                                    && title.indexOf('-') !== -1
                                ) {{
                                    role = 'assistant';
                                }} else {{
                                    role = 'user';
                                }}
                                card.setAttribute(
                                    'data-speaker', role);
                                card.setAttribute(
                                    'data-speaker-name', title);
                                // Remove entire card header —
                                // contains name, date, avatar, URL
                                card.querySelectorAll(
                                    '.chakra-card__header')
                                    .forEach(h => h.remove());
                            }});
                            // 2. Extract classified cards from
                            // accordion items before removal
                            iDoc.querySelectorAll(
                                '.chakra-accordion__item'
                                + ' [data-speaker]'
                            ).forEach(card => {{
                                const acc = card.closest(
                                    '.chakra-accordion__item');
                                if (acc && acc.parentNode) {{
                                    acc.parentNode.insertBefore(
                                        card, acc);
                                }}
                            }});
                            // 3. NOW remove chrome safely
                            ['.chakra-accordion__item',
                             'form',
                             '.chakra-menu__menuitem'
                            ].forEach(sel =>
                                iDoc.querySelectorAll(sel)
                                    .forEach(el => el.remove()));
                        }}

                        // Unwrap hyperlinks: replace <a href="url">text</a>
                        // with text [url] — links are not interactive in
                        // the annotation view and interfere with selection
                        iframe.contentDocument.querySelectorAll('a[href]')
                            .forEach(a => {{
                                const href = a.getAttribute('href') || '';
                                const text = a.textContent || '';
                                // Skip anchors that are just fragment links
                                // or have no meaningful href
                                if (!href || href.startsWith('#')) {{
                                    // Just unwrap, keep text
                                    a.replaceWith(text);
                                    return;
                                }}
                                // Show URL after link text
                                const suffix = ' [' + href + ']';
                                a.replaceWith(text + suffix);
                            }});

                        // Process all elements - preserve important inline styles
                        iframe.contentDocument.querySelectorAll('*').forEach(el => {{
                            const existingStyle = el.getAttribute('style') || '';
                            const keptStyles = [];

                            // Parse inline style for important properties
                            for (const prop of keepStyleProps) {{
                                const pat = prop + '\\\\s*:\\\\s*([^;]+)';
                                const m = existingStyle.match(
                                    new RegExp(pat, 'i'));
                                if (m) {{
                                    keptStyles.push(
                                        prop + ':' + m[1].trim());
                                }}
                            }}
                            // Expand margin/padding shorthand
                            for (const sh of shorthandProps) {{
                                const pat = '(?:^|;)\\\\s*' + sh
                                    + '\\\\s*:\\\\s*([^;]+)';
                                const m = existingStyle.match(
                                    new RegExp(pat, 'i'));
                                if (m) {{
                                    const vals = m[1].trim().split(
                                        /\\s+/);
                                    const t = vals[0] || '0';
                                    const r = vals[1] || t;
                                    const b = vals[2] || t;
                                    const l = vals[3] || r;
                                    // Only keep non-zero values
                                    if (l !== '0' && l !== '0px')
                                        keptStyles.push(
                                            sh + '-left:' + l);
                                    if (r !== '0' && r !== '0px')
                                        keptStyles.push(
                                            sh + '-right:' + r);
                                }}
                            }}

                            // Apply preserved styles or remove style attr
                            if (keptStyles.length > 0) {{
                                el.setAttribute('style', keptStyles.join(';'));
                            }} else {{
                                el.removeAttribute('style');
                            }}

                            // Remove class attributes
                            el.removeAttribute('class');

                            // Remove data-* attrs except
                            // data-speaker and data-thinking
                            const dataAttrs = [];
                            const keepData = new Set([
                                'data-speaker',
                                'data-speaker-name',
                                'data-thinking']);
                            for (const attr of el.attributes) {{
                                if (attr.name.startsWith('data-')
                                    && !keepData.has(attr.name)) {{
                                    dataAttrs.push(attr.name);
                                }}
                            }}
                            dataAttrs.forEach(
                                n => el.removeAttribute(n));
                        }});

                        // Remove empty containers that only have <br> tags
                        const removeEmpty = () => {{
                            let removed = 0;
                            iframe.contentDocument.querySelectorAll('p, div, span')
                                .forEach(el => {{
                                // Preserve speaker marker divs
                                // and thinking indicators
                                if (el.hasAttribute('data-speaker')
                                    || el.hasAttribute(
                                        'data-thinking')) return;
                                const text = el.textContent?.trim();
                                const noBr = el.innerHTML.replace(/<br\\s*\\/?>/gi, '');
                                const htmlNoBr = noBr.trim();
                                if (!text && !htmlNoBr) {{
                                    el.remove();
                                    removed++;
                                }}
                            }});
                            return removed;
                        }};
                        while (removeEmpty() > 0) {{}}

                        // Clean up empty table elements
                        const removeEmptyTable = () => {{
                            let removed = 0;
                            const doc = iframe.contentDocument;
                            doc.querySelectorAll('td, tr, table, col').forEach(el => {{
                                if (!el.textContent?.trim()) {{
                                    el.remove();
                                    removed++;
                                }}
                            }});
                            return removed;
                        }};
                        while (removeEmptyTable() > 0) {{}}

                        // Strip nav elements and empty list items
                        const doc = iframe.contentDocument;
                        doc.querySelectorAll('nav').forEach(
                            el => el.remove());
                        doc.querySelectorAll('li').forEach(el => {{
                            if (!el.textContent?.trim())
                                el.remove();
                        }});

                        // P5: Flatten <pre> blocks to preserve
                        // whitespace. OpenAI wraps code in
                        // <pre><div>...<div><code><span>...
                        // After class stripping, the intermediate
                        // divs and spans break formatting.
                        // Fix: replace <pre> content with plain
                        // text from the <code> element.
                        doc.querySelectorAll('pre').forEach(
                            pre => {{
                            const code = pre.querySelector(
                                'code');
                            if (code) {{
                                // Preserve the text content
                                // (includes literal newlines)
                                const txt = code.textContent;
                                // Replace pre content with
                                // just <code>text</code>
                                const newCode =
                                    doc.createElement('code');
                                newCode.textContent = txt;
                                pre.textContent = '';
                                pre.appendChild(newCode);
                            }} else {{
                                // No <code> child — flatten
                                // all children to text
                                const txt = pre.textContent;
                                pre.textContent = txt;
                            }}
                        }});

                        // (P4 KaTeX flatten moved above,
                        // before attribute stripping)

                        // (P2 thinking collapse moved above,
                        // before attribute stripping)

                        // P1: Deduplicate speaker labels
                        // Two rules:
                        // (a) Same-role consecutive: always remove
                        //     the earlier one (nesting artefact)
                        // (b) Different-role consecutive with no
                        //     real text between: remove earlier
                        //     (null/empty round)
                        const FOLLOWING = Node
                            .DOCUMENT_POSITION_FOLLOWING;
                        const PRECEDING = Node
                            .DOCUMENT_POSITION_PRECEDING;
                        const allSp = Array.from(
                            doc.querySelectorAll('[data-speaker]'));
                        const spSet = new Set(allSp);
                        const toRemove = [];
                        for (let i = 0; i < allSp.length - 1;
                                i++) {{
                            const cur = allSp[i];
                            const nxt = allSp[i + 1];
                            const curRole = cur.getAttribute(
                                'data-speaker');
                            const nxtRole = nxt.getAttribute(
                                'data-speaker');
                            // (a) Same role = always duplicate
                            if (curRole === nxtRole) {{
                                toRemove.push(cur);
                                continue;
                            }}
                            // (b) Different role: check for text
                            // between the two speaker divs.
                            // Use compareDocumentPosition to
                            // find text nodes between cur & nxt
                            // (speaker divs are empty, so
                            // contains() won't find children).
                            const tw = doc.createTreeWalker(
                                doc.body,
                                NodeFilter.SHOW_TEXT,
                                null);
                            let hasContent = false;
                            while (tw.nextNode()) {{
                                const n = tw.currentNode;
                                // Is n after cur?
                                const afterCur = cur
                                    .compareDocumentPosition(n)
                                    & FOLLOWING;
                                if (!afterCur) continue;
                                // Is n before nxt?
                                const beforeNxt = nxt
                                    .compareDocumentPosition(n)
                                    & PRECEDING;
                                if (!beforeNxt) break;
                                // Skip text inside other speakers
                                let inSpeaker = false;
                                for (const s of spSet) {{
                                    if (s !== cur && s !== nxt
                                        && s.contains(n)) {{
                                        inSpeaker = true;
                                        break;
                                    }}
                                }}
                                if (inSpeaker) continue;
                                const t = n.textContent.trim();
                                if (t.length > 2) {{
                                    hasContent = true;
                                    break;
                                }}
                            }}
                            if (!hasContent) toRemove.push(cur);
                        }}
                        toRemove.forEach(el => el.remove());

                        cleaned = iframe.contentDocument.body.innerHTML;
                        document.body.removeChild(iframe);
                        console.log('[PASTE] Cleaned:', cleaned.length, 'bytes');
                    }}

                    window.{paste_var} = cleaned;
                    const newSize = cleaned.length;
                    console.log('[PASTE] Stripped:', origSize, '->', newSize,
                        '(' + Math.round(100 - newSize*100/origSize) + '% reduction)');

                    // Show placeholder with size info
                    const p = document.createElement('p');
                    p.style.cssText = 'color:#666;font-style:italic;';
                    p.textContent = '\u2713 Content pasted (' +
                        Math.round(newSize/1024) + ' KB after cleanup). ' +
                        'Click "Add Document" to process.';
                    editorEl.replaceChildren(p);
                }});
            }};
            tryAttach();
        }});
    </script>
    """)

    async def handle_add_document() -> None:
        """Process input and add document to workspace."""
        # Try to get pasted content from JS storage (bypasses websocket limit)
        stored = await ui.run_javascript(f"window.{paste_var}")
        platform_hint = await ui.run_javascript(f"window.{platform_var}")
        content, from_paste = (stored, True) if stored else (content_input.value, False)

        if not content or not content.strip():
            ui.notify("Please enter or paste some content", type="warning")
            return

        # Skip dialog if HTML was captured from paste - we know it's HTML
        confirmed_type: ContentType | None = (
            "html"
            if from_paste
            else (
                await show_content_type_dialog(
                    detect_content_type(content), content[:500]
                )
            )
        )
        if confirmed_type is None:
            return  # User cancelled

        try:
            processed_html = await process_input(
                content=content,
                source_type=confirmed_type,
                platform_hint=platform_hint,
            )
            auto_number, para_map = _detect_paragraph_numbering(processed_html)
            await add_document(
                workspace_id=workspace_id,
                type="source",
                content=processed_html,
                source_type=confirmed_type,
                title=None,
                auto_number_paragraphs=auto_number,
                paragraph_map=para_map,
            )
            content_input.value = ""
            ui.notify("Document added successfully", type="positive")
            ui.navigate.to(_annotation_url(workspace_id))
        except Exception as exc:
            logger.exception("Failed to add document")
            ui.notify(f"Failed to add document: {exc}", type="negative")

    ui.button("Add Document", on_click=handle_add_document).props(
        'data-testid="add-document-btn"'
    ).classes("bg-green-500 text-white mt-2")

    async def handle_file_upload(upload_event: events.UploadEventArguments) -> None:
        """Handle file upload through HTML pipeline."""
        # Access file via .file attribute (FileUpload dataclass)
        # ty cannot resolve this type due to TYPE_CHECKING import in nicegui
        filename: str = upload_event.file.name  # pyright: ignore[reportAttributeAccessIssue]
        content_bytes = await upload_event.file.read()  # pyright: ignore[reportAttributeAccessIssue]

        # Detect type from extension, fall back to content detection
        detected_type = _detect_type_from_extension(filename)
        if detected_type is None:
            detected_type = detect_content_type(content_bytes)

        preview = _get_file_preview(content_bytes, detected_type, filename)
        confirmed_type = await show_content_type_dialog(
            detected_type=detected_type,
            preview=preview,
        )

        if confirmed_type is None:
            ui.notify("Upload cancelled", type="info")
            return

        try:
            processed_html = await process_input(
                content=content_bytes,
                source_type=confirmed_type,
                platform_hint=None,
            )
            auto_number, para_map = _detect_paragraph_numbering(processed_html)
            await add_document(
                workspace_id=workspace_id,
                type="source",
                content=processed_html,
                source_type=confirmed_type,
                title=filename,
                auto_number_paragraphs=auto_number,
                paragraph_map=para_map,
            )
            ui.notify(f"Uploaded: {filename}", type="positive")
            ui.navigate.to(_annotation_url(workspace_id))
        except NotImplementedError as not_impl_err:
            ui.notify(f"Format not yet supported: {not_impl_err}", type="warning")
        except Exception as exc:
            logger.exception("Failed to process uploaded file")
            ui.notify(f"Failed to process file: {exc}", type="negative")

    # File upload for HTML, RTF, DOCX, PDF, TXT, Markdown files
    if get_settings().features.enable_file_upload:
        ui.upload(
            label="Or upload a file",
            on_upload=handle_file_upload,
            auto_upload=True,
            max_file_size=10 * 1024 * 1024,  # 10 MB limit
        ).props('accept=".html,.htm,.rtf,.docx,.pdf,.txt,.md,.markdown"').classes(
            "w-full"
        )
