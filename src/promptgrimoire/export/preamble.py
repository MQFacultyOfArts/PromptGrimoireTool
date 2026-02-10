"""LaTeX preamble assembly and escape utilities (P5 functions).

Generates the LuaLaTeX preamble for annotated PDF export, including:
- Tag colour definitions (full, light, dark variants)
- Speaker turn environments
- Annotation counter and margin note macro
- LaTeX special character escaping
- Timestamp formatting

Extracted from latex.py during the module split (Issue #134, Phase 1).
"""

from __future__ import annotations

import re
from datetime import datetime

from promptgrimoire.export.unicode_latex import UNICODE_PREAMBLE

# Base LaTeX preamble for LuaLaTeX with marginalia+lua-ul annotation approach
# Note: The \annot command takes 2 parameters: colour name and margin content.
# It places a superscript number at the insertion point with a coloured margin note.
# Highlighting uses lua-ul's \highLight for robust cross-line-break backgrounds.
# marginalia package auto-stacks overlapping margin notes (requires 2+ lualatex runs).
ANNOTATION_PREAMBLE_BASE = r"""
% fontspec and \setmainfont are in UNICODE_PREAMBLE (with fallback chain)
\usepackage{amsmath}           % Math extensions (\text{} in math mode)
\usepackage{microtype}         % Better typography (kerning, protrusion)
\usepackage{marginalia}        % Auto-stacking margin notes for LuaLaTeX
\usepackage{longtable}
\usepackage{booktabs}
\usepackage{array}
\usepackage{calc}
\usepackage[hidelinks]{hyperref}
\usepackage{changepage}
\usepackage{luacolor}  % Required by lua-ul for coloured highlights
\usepackage{lua-ul}    % LuaLaTeX highlighting (robust across line breaks)
\usepackage{luabidi}   % Bidirectional text support for LuaLaTeX
\usepackage{fancyvrb}  % Verbatim/code blocks from Pandoc syntax highlighting
\usepackage[a4paper,left=2.5cm,right=6cm,top=2.5cm,bottom=2.5cm]{geometry}
\usepackage[framemethod=tikz]{mdframed}  % For speaker turn borders

% Stub for \includegraphics - Pandoc converts <img> tags to this.
% hyperref loads graphicx which defines \includegraphics, so we must
% \renewcommand AFTER all \usepackage calls to survive.
\renewcommand{\includegraphics}[2][]{[image]}

% No-op otherlanguage environment - Pandoc generates \begin{otherlanguage}{X}
% for non-English content but we handle multilingual via luatexja + font fallbacks.
% babel (loaded by hyperref/luabidi chain) may define it, so override safely.
\makeatletter
\@ifundefined{otherlanguage}%
  {\newenvironment{otherlanguage}[1]{}{}}%
  {\renewenvironment{otherlanguage}[1]{}{}}
\makeatother

% Paragraph formatting for chatbot exports (no indent, paragraph spacing)
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.5\baselineskip}

% Speaker turn environments with left border
\newmdenv[
  topline=false,
  bottomline=false,
  rightline=false,
  linewidth=3pt,
  linecolor=usercolor,
  innerleftmargin=1em,
  innerrightmargin=0pt,
  innertopmargin=0pt,
  innerbottommargin=0pt,
  skipabove=0pt,
  skipbelow=0pt
]{userturn}
\newmdenv[
  topline=false,
  bottomline=false,
  rightline=false,
  linewidth=3pt,
  linecolor=assistantcolor,
  innerleftmargin=1em,
  innerrightmargin=0pt,
  innertopmargin=0pt,
  innerbottommargin=0pt,
  skipabove=0pt,
  skipbelow=0pt
]{assistantturn}

% Pandoc compatibility
\providecommand{\tightlist}{%
  \setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\setlength{\emergencystretch}{3em}  % prevent overfull lines
\setcounter{secnumdepth}{-\maxdimen}  % no section numbering

% Annotation counter and macro
% Usage: \annot{colour-name}{margin content}
% Uses footnotesize for compact margin notes
% marginalia auto-stacks overlapping notes with ysep spacing
\newcounter{annotnum}
\newcommand{\annot}[2]{%
  \stepcounter{annotnum}%
  \textsuperscript{\textcolor{#1}{\textbf{\theannotnum}}}%
  \marginalia[ysep=3pt]{%
    \fcolorbox{#1}{#1!20}{%
      \parbox{4.3cm}{\footnotesize\textbf{\theannotnum.} #2}%
    }%
  }%
}
"""


def generate_tag_colour_definitions(tag_colours: dict[str, str]) -> str:
    """Generate LaTeX \\definecolor commands from tag->colour mapping.

    Generates full-strength, light (30%), and dark (70% black mix) versions
    of each colour. The light versions are used for text highlighting backgrounds,
    and dark versions are used for underlines.

    Args:
        tag_colours: Dict of tag_name -> hex colour (e.g., {"jurisdiction": "#1f77b4"})

    Returns:
        LaTeX \\definecolor commands for each tag (full, light, and dark variants),
        plus the many-dark colour for 3+ overlapping highlights.
    """
    definitions: list[str] = []
    for tag, colour in tag_colours.items():
        hex_code = colour.lstrip("#")
        safe_name = tag.replace("_", "-")  # LaTeX-safe name
        # Full colour for borders and text
        definitions.append(f"\\definecolor{{tag-{safe_name}}}{{HTML}}{{{hex_code}}}")
        # Light colour (30% strength) for highlight backgrounds
        # Using xcolor's mixing: 30% of tag colour + 70% white
        definitions.append(f"\\colorlet{{tag-{safe_name}-light}}{{tag-{safe_name}!30}}")
        # Dark variant for underlines (70% base, 30% black)
        definitions.append(
            f"\\colorlet{{tag-{safe_name}-dark}}{{tag-{safe_name}!70!black}}"
        )

    # many-dark colour for 3+ overlapping highlights
    definitions.append(r"\definecolor{many-dark}{HTML}{333333}")

    return "\n".join(definitions)


def build_annotation_preamble(tag_colours: dict[str, str]) -> str:
    """Build complete annotation preamble with tag colour definitions.

    Args:
        tag_colours: Dict of tag_name -> hex colour.

    Returns:
        Complete LaTeX preamble string.
    """
    colour_defs = generate_tag_colour_definitions(tag_colours)
    # Speaker colours for chatbot turn distinction
    speaker_colours = r"""
% Speaker colours for chatbot turn markers
\definecolor{usercolor}{HTML}{4A90D9}
\definecolor{assistantcolor}{HTML}{7B68EE}
"""
    return (
        f"\\usepackage{{xcolor}}\n{colour_defs}\n"
        f"{speaker_colours}\n{UNICODE_PREAMBLE}\n{ANNOTATION_PREAMBLE_BASE}"
    )


def _format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp to human-readable format (e.g., '26 Jan 2026 14:30')."""
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y %H:%M")
    except ValueError, AttributeError:
        return ""


def _strip_test_uuid(name: str) -> str:
    """Strip test UUID suffix from display names.

    E.g., 'Alice Jones 1664E02D' -> 'Alice Jones'.
    """
    # Match trailing hex UUID (8+ hex chars at end after space)
    return re.sub(r"\s+[A-Fa-f0-9]{6,}$", "", name)
