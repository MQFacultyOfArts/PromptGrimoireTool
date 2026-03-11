"""Client-side paste interception JavaScript for the annotation page.

Generates the ``<script>`` block that intercepts browser paste events
on the Quasar QEditor, strips CSS bloat, injects speaker label markers
for known AI platforms, and stores cleaned HTML in window-scoped
variables for server-side retrieval.

Platform detection covers: Claude, OpenAI, Gemini, AI Studio,
ScienceOS, OpenRouter, ChatCraft, and Wikimedia.

Note: This file exceeds the 400-line target because its body is a single
indivisible JavaScript string literal (~780 lines of JS). Python complexity
is 0. The line target applies to Python logic, not embedded JS templates.

Future cleanup: The JS only interpolates 3 Python variables (paste_var,
platform_var, editor_id). It could be moved to a static .js file with
runtime injection, eliminating the f-string and the line-count exception.
"""

from __future__ import annotations


def _build_paste_intercept_script(
    paste_var: str,
    platform_var: str,
    editor_id: str,
) -> str:
    """Build the client-side paste interception JavaScript.

    Args:
        paste_var: Window variable name for storing cleaned HTML.
        platform_var: Window variable name for storing detected platform.
        editor_id: NiceGUI element ID for the QEditor component.

    Returns:
        Complete ``<script>`` block ready for ``ui.add_body_html()``.
    """
    return f"""
    <script>
        window.{paste_var} = null;
        window.{platform_var} = null;
        document.addEventListener('DOMContentLoaded', function() {{
            const sel = '[id="c{editor_id}"] .q-editor__content';
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
                                const headerLabel = card.querySelector(
                                    '.chakra-card__header h2')
                                    ?.textContent?.trim() || '';
                                const title = card.querySelector(
                                    '.chakra-card__header span[title]')
                                    ?.getAttribute('title') || '';
                                const label = headerLabel || title;
                                if (!label) return;
                                let role;
                                if (label === 'System Prompt') {{
                                    role = 'system';
                                }} else if (
                                    label.indexOf(' ') === -1
                                    && label.indexOf('-') !== -1
                                ) {{
                                    role = 'assistant';
                                }} else {{
                                    role = 'user';
                                }}
                                card.setAttribute(
                                    'data-speaker', role);
                                card.setAttribute(
                                    'data-speaker-name', label);
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
                            const topLevelBodyChild = node => {{
                                let cur = node;
                                while (cur
                                    && cur.parentElement !== iDoc.body) {{
                                    cur = cur.parentElement;
                                }}
                                return cur;
                            }};
                            const firstTurn = iDoc.querySelector(
                                '.chakra-card[data-speaker]');
                            if (firstTurn) {{
                                let child = iDoc.body.firstElementChild;
                                const firstTurnContainer = topLevelBodyChild(
                                    firstTurn);
                                while (child
                                    && child !== firstTurnContainer) {{
                                    const nextChild =
                                        child.nextElementSibling;
                                    child.remove();
                                    child = nextChild;
                                }}
                            }}
                            // Remove remaining page-summary cards that
                            // are not actual conversation turns.
                            iDoc.querySelectorAll(
                                '.chakra-card:not([data-speaker])'
                            ).forEach(card => card.remove());
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
                                // Preserve whitespace-only spans and
                                // wrappers inside code blocks; ChatCraft
                                // syntax highlighting uses them for
                                // meaningful spacing between tokens.
                                if (el.closest('pre, code')) return;
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
                            const codeNodes = Array.from(
                                pre.querySelectorAll('code'));
                            const code = codeNodes.reduce(
                                (best, node) => {{
                                if (!best) return node;
                                const bestLen = (
                                    best.textContent || '').length;
                                const nodeLen = (
                                    node.textContent || '').length;
                                return nodeLen > bestLen
                                    ? node
                                    : best;
                            }}, null);
                            if (code) {{
                                // Preserve the richest text source.
                                // ChatCraft code blocks include a
                                // header <code> for the language
                                // label ("python") plus a separate
                                // body <code> for the real snippet.
                                // Falling back to the whole <pre>
                                // text avoids collapsing the block to
                                // just the language label.
                                const codeTxt =
                                    code.textContent || '';
                                const preTxt =
                                    pre.textContent || '';
                                const txt = preTxt.length > codeTxt.length
                                    ? preTxt
                                    : codeTxt;
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
                        const isLabelOnlySpeaker = (node) =>
                            !(node.textContent || '').trim();
                        const toRemove = [];
                        for (let i = 0; i < allSp.length - 1;
                                i++) {{
                            const cur = allSp[i];
                            const nxt = allSp[i + 1];
                            const curRole = cur.getAttribute(
                                'data-speaker');
                            const nxtRole = nxt.getAttribute(
                                'data-speaker');
                            // Deduping only makes sense for the
                            // empty speaker-marker divs injected for
                            // other platforms. ChatCraft stores the
                            // role on the card itself; removing a
                            // contentful node would drop the whole
                            // turn.
                            if (!isLabelOnlySpeaker(cur)
                                || !isLabelOnlySpeaker(nxt)) {{
                                continue;
                            }}
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
    """
