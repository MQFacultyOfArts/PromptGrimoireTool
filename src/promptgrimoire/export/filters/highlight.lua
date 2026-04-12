-- Pandoc Lua filter for highlight rendering.
-- Reads data-hl, data-colors, and data-annots span attributes and emits
-- nested \highLight / \underLine / \annot LaTeX commands.
--
-- Stacking model ("one, two, many"):
--   1 highlight:  single 1pt underline in tag's dark colour
--   2 highlights: stacked 2pt outer + 1pt inner underlines
--   3+ highlights: single 4pt underline in many-dark colour
--
-- Pandoc strips the "data-" prefix from HTML attributes, so data-hl
-- becomes just "hl", data-colors becomes "colors", etc.

--- Split a comma-separated string into a table.
--- @param str string  comma-separated values
--- @return table  list of trimmed non-empty values
local function split_csv(str)
  local result = {}
  for val in string.gmatch(str, "[^,]+") do
    table.insert(result, val)
  end
  return result
end

--- Replace "-light" suffix with "-dark".
--- @param name string  colour name ending in "-light"
--- @return string  colour name ending in "-dark"
local function light_to_dark(name)
  return (string.gsub(name, "%-light$", "-dark"))
end

--- Build underline open/close RawInline pairs based on highlight count.
--- Returns two lists: opens (outermost first) and closes (innermost first).
--- @param colors_list table  list of light colour names
--- @return table, table  open RawInlines, close RawInlines
local function build_underlines(colors_list)
  local count = #colors_list
  local opens = {}
  local closes = {}

  if count == 0 then
    return opens, closes
  elseif count == 1 then
    local dark = light_to_dark(colors_list[1])
    table.insert(opens, pandoc.RawInline("latex",
      "\\underLine[color=" .. dark .. ", height=1pt, bottom=-3pt]{"))
    table.insert(closes, pandoc.RawInline("latex", "}"))
  elseif count == 2 then
    -- Outer underline (index 1 = lower highlight index): thicker, lower
    local dark_outer = light_to_dark(colors_list[1])
    table.insert(opens, pandoc.RawInline("latex",
      "\\underLine[color=" .. dark_outer .. ", height=2pt, bottom=-5pt]{"))
    -- Inner underline (index 2 = higher highlight index): thinner, higher
    local dark_inner = light_to_dark(colors_list[2])
    table.insert(opens, pandoc.RawInline("latex",
      "\\underLine[color=" .. dark_inner .. ", height=1pt, bottom=-3pt]{"))
    -- Closes in reverse order (inner first)
    table.insert(closes, pandoc.RawInline("latex", "}"))
    table.insert(closes, pandoc.RawInline("latex", "}"))
  else
    -- 3+ highlights: single thick underline in many-dark
    table.insert(opens, pandoc.RawInline("latex",
      "\\underLine[color=many-dark, height=4pt, bottom=-5pt]{"))
    table.insert(closes, pandoc.RawInline("latex", "}"))
  end

  return opens, closes
end

--- Build highlight open/close RawInline pairs.
--- Outer highlight (lowest index) wraps innermost (highest index).
--- Opens are emitted outer-to-inner; closes are inner-to-outer.
--- @param colors_list table  list of light colour names
--- @return table, table  open RawInlines, close RawInlines
local function build_highlights(colors_list)
  local opens = {}
  local closes = {}

  -- Iterate in order (outer to inner for opens)
  for _, colour in ipairs(colors_list) do
    table.insert(opens, pandoc.RawInline("latex",
      "\\highLight[" .. colour .. "]{"))
    -- Prepend to closes so inner closes come first
    table.insert(closes, 1, pandoc.RawInline("latex", "}"))
  end

  return opens, closes
end

--- Underline callback: override Pandoc's default <u> → \ul{} (soul) emission.
--- soul's \ul is fragile and crashes with nested lua-ul \underLine or \highLight
--- commands inside it. We emit lua-ul's robust \underLine{} instead (#372).
function Underline(el)
  if FORMAT ~= "latex" then return el end
  local result = pandoc.List({pandoc.RawInline("latex", "\\underLine{")})
  result:extend(el.content)
  result:insert(pandoc.RawInline("latex", "}"))
  return result
end

--- Strikeout callback: override Pandoc's default <del>/<s> → \st{} (soul) emission.
--- soul's \st tokenizes its argument and crashes with nested lua-ul commands
--- (\underLine, \highLight) inside it — same conflict class as Underline above.
--- We emit lua-ul's \underLine at strikethrough height (0.4ex above baseline)
--- instead, which is robust across nested lua-ul commands.
function Strikeout(el)
  if FORMAT ~= "latex" then return el end
  local result = pandoc.List({pandoc.RawInline("latex",
    "\\underLine[height=0.4pt, bottom=-0.4ex]{")})
  result:extend(el.content)
  result:insert(pandoc.RawInline("latex", "}"))
  return result
end

--- Span callback: transform highlighted spans into LaTeX commands.
function Span(el)
  if FORMAT ~= "latex" then return el end

  -- Paragraph number marker: emit \paranumber{N} and return.
  -- Must be checked BEFORE the hl nil-guard because paranumber spans
  -- have no hl attribute and would otherwise be returned unchanged.
  local paranumber = el.attributes["paranumber"]
  if paranumber ~= nil and paranumber ~= "" then
    return pandoc.RawInline("latex", "\\paranumber{" .. paranumber .. "}")
  end

  -- Guard: no hl attribute means pass through unchanged
  local hl = el.attributes["hl"]
  if hl == nil or hl == "" then
    return el
  end

  -- Parse colors attribute
  local colors_str = el.attributes["colors"] or ""
  local colors_list = split_csv(colors_str)
  if #colors_list == 0 then
    return el
  end

  -- Build highlight wrapping (outer to inner)
  local hl_opens, hl_closes = build_highlights(colors_list)

  -- Build underline wrapping based on count
  local ul_opens, ul_closes = build_underlines(colors_list)

  -- Assemble result list:
  -- underline opens, highlight opens, content, highlight closes, underline closes
  local result = pandoc.List({})

  -- Underline opens (outermost first)
  for _, o in ipairs(ul_opens) do
    result:insert(o)
  end

  -- Highlight opens (outer to inner)
  for _, o in ipairs(hl_opens) do
    result:insert(o)
  end

  -- Original span content
  result:extend(el.content)

  -- Highlight closes (inner to outer)
  for _, c in ipairs(hl_closes) do
    result:insert(c)
  end

  -- Underline closes (inner first for stacked)
  for _, c in ipairs(ul_closes) do
    result:insert(c)
  end

  -- Annotation emission: annots attribute contains pre-formatted LaTeX
  -- (produced by Python's format_annot_latex in highlight_spans.py).
  -- Emitted as RawInline AFTER the closing highlight/underline braces.
  -- NOTE: When this span is inside a heading, Pandoc wraps the output in
  -- \texorpdfstring{}{} which lives inside \section{} — \par is forbidden
  -- there. The Header callback below detects and moves annots outside.
  local annots = el.attributes["annots"]
  if annots ~= nil and annots ~= "" then
    result:insert(pandoc.RawInline("latex", annots))
  end

  return result
end

--- Header callback: strip fragile commands from headings (#372).
--- LaTeX section headings are "moving arguments" where fragile commands
--- (\annot with \par, \BeginAccSupp PDF literals) cause fatal errors.
---
--- Uses recursive :walk() to process the entire heading subtree,
--- catching commands nested inside Strong/Emph/Span nodes that a flat
--- loop over el.content would miss (Gemini review finding).
---
--- \annot commands are moved AFTER the heading (margin notes preserved).
--- AccSupp wrappers are unwrapped: the inner emoji is kept, the PDF
--- /ActualText wrapper is dropped (headings already have plain-text
--- bookmarks via \texorpdfstring).
function Header(el)
  if FORMAT ~= "latex" then return el end

  local extracted_annots = pandoc.List({})

  el.content = el.content:walk({
    RawInline = function(raw)
      if raw.format ~= "latex" then return nil end

      -- Extract \annot commands (move after heading)
      if string.find(raw.text, "\\annot{", 1, true) then
        extracted_annots:insert(raw)
        return {}
      end

      -- Unwrap AccSupp: rescue the inner emoji, drop the wrapper
      if string.find(raw.text, "\\BeginAccSupp", 1, true) then
        local emoji = string.match(
          raw.text,
          "\\BeginAccSupp%{ActualText={.-}%}(.-)\\EndAccSupp%{%}"
        )
        if emoji then
          return pandoc.RawInline("latex", emoji)
        end
        return {}  -- fallback removal if pattern doesn't match
      end

      return nil  -- keep other RawInlines unchanged
    end
  })

  if #extracted_annots == 0 then
    return el
  end

  return { el, pandoc.Plain(extracted_annots) }
end

--- Find the closing brace matching an opening brace at position `start`.
--- @param str string  the string to search
--- @param start number  position of the opening '{'
--- @return number|nil  position of the matching '}', or nil if not found
local function find_matching_brace(str, start)
  local depth = 0
  for i = start, #str do
    local ch = str:sub(i, i)
    if ch == '{' then
      depth = depth + 1
    elseif ch == '}' then
      depth = depth - 1
      if depth == 0 then
        return i
      end
    end
  end
  return nil
end

--- Parse \annot{colour}{content} from a RawInline text string.
--- Returns colour, content, and any prefix/suffix text around the \annot.
--- @param text string  RawInline text potentially containing \annot{...}{...}
--- @return string|nil colour
--- @return string|nil content
--- @return string prefix  text before \annot
--- @return string suffix  text after \annot
local function parse_annot(text)
  local annot_start = text:find('\\annot{', 1, true)
  if not annot_start then
    return nil, nil, text, ''
  end

  local prefix = text:sub(1, annot_start - 1)

  -- First brace group: {colour}
  local brace1_start = annot_start + #'\\annot'
  local brace1_end = find_matching_brace(text, brace1_start)
  if not brace1_end then
    return nil, nil, text, ''
  end
  local colour = text:sub(brace1_start + 1, brace1_end - 1)

  -- Second brace group: {content}
  local brace2_start = brace1_end + 1
  if brace2_start > #text or text:sub(brace2_start, brace2_start) ~= '{' then
    return nil, nil, text, ''
  end
  local brace2_end = find_matching_brace(text, brace2_start)
  if not brace2_end then
    return nil, nil, text, ''
  end
  local content = text:sub(brace2_start + 1, brace2_end - 1)

  local suffix = text:sub(brace2_end + 1)

  return colour, content, prefix, suffix
end

--- Table callback: move \annot out of table cells.
--- \annot contains \par which is illegal in longtable cells and causes
--- LuaTeX to hang when luatexja-fontspec is loaded (CJK documents).
--- Replaces each \annot{colour}{content} with \annotref{colour} inline
--- and defers \annotendnote{colour}{num}{content} to after the table.
function Table(el)
  if FORMAT ~= 'latex' then return el end

  local annot_counter = 0  -- total annots found in this table
  local deferred = {}       -- structured entries: {colour=..., content=...}

  --- Process a single RawInline, splitting \annot into \annotref + deferred endnote.
  --- Stores structured {colour, content} entries in `deferred` (NOT pre-formatted
  --- LaTeX strings). The final \annotendnote assembly happens after all cells are
  --- processed, using \numexpr to compute the correct counter value for each entry.
  --- @param raw pandoc.RawInline
  --- @return pandoc.List  replacement inlines
  local function process_rawinline(raw)
    if raw.t ~= 'RawInline' or raw.format ~= 'latex' then
      return pandoc.List({raw})
    end

    local text = raw.text
    if not text:find('\\annot{', 1, true) then
      return pandoc.List({raw})
    end

    local result = pandoc.List({})
    local remaining = text

    while true do
      local colour, content, prefix, suffix = parse_annot(remaining)
      if not colour then
        if remaining ~= '' then
          result:insert(pandoc.RawInline('latex', remaining))
        end
        break
      end

      if prefix ~= '' then
        result:insert(pandoc.RawInline('latex', prefix))
      end

      -- Emit \annotref{colour} inline (increments annotnum counter in LaTeX)
      result:insert(pandoc.RawInline('latex',
        '\\annotref{' .. colour .. '}'))

      -- Store structured entry for deferred assembly (NOT a pre-formatted string).
      -- Counter value is computed after all cells are processed.
      annot_counter = annot_counter + 1
      table.insert(deferred, {colour = colour, content = content})

      remaining = suffix
    end

    return result
  end

  --- Walk a list of blocks, replacing \annot RawInlines with \annotref.
  --- @param blocks pandoc.List  blocks to process
  --- @return pandoc.List  processed blocks
  local function process_blocks(blocks)
    local filter = {
      RawInline = process_rawinline,
    }
    local new_blocks = pandoc.List({})
    for _, block in ipairs(blocks) do
      new_blocks:insert(block:walk(filter))
    end
    return new_blocks
  end

  -- Process head rows
  if el.head and el.head.rows then
    for _, row in ipairs(el.head.rows) do
      for _, cell in ipairs(row.cells) do
        cell.contents = process_blocks(cell.contents)
      end
    end
  end

  -- Process body rows
  for _, body in ipairs(el.bodies) do
    if body.body then
      for _, row in ipairs(body.body) do
        for _, cell in ipairs(row.cells) do
          cell.contents = process_blocks(cell.contents)
        end
      end
    end
  end

  -- Process foot rows
  if el.foot and el.foot.rows then
    for _, row in ipairs(el.foot.rows) do
      for _, cell in ipairs(row.cells) do
        cell.contents = process_blocks(cell.contents)
      end
    end
  end

  -- If no annots were found, return table unchanged
  if #deferred == 0 then
    return el
  end

  -- Assemble deferred \annotendnote commands with correct counter values.
  --
  -- Counter sequencing (proleptic challenge resolved):
  -- Each \annotref{colour} inside the table calls \stepcounter{annotnum}.
  -- After all cells are processed, the LaTeX counter annotnum = base + annot_counter.
  -- Annot K (1-based) had counter value base + K.
  -- So the correct number for annot K is: \the\numexpr\value{annotnum} - N + K\relax
  -- where N = annot_counter (total annots in this table).
  local deferred_latex = {}
  for k, entry in ipairs(deferred) do
    local num_expr = string.format(
      '\\the\\numexpr\\value{annotnum}-%d+%d\\relax',
      annot_counter, k)
    deferred_latex[k] = string.format(
      '\\annotendnote{%s}{%s}{%s}',
      entry.colour, num_expr, entry.content)
  end

  -- Return table followed by deferred endnote commands
  return {el, pandoc.RawBlock('latex', table.concat(deferred_latex, '\n'))}
end

--- Check if a Unicode codepoint is an emoji that needs AccSupp wrapping.
--- Noto Color Emoji renders these as CBDT bitmaps — without /ActualText
--- the codepoint is lost in the PDF.
--- @param cp number  Unicode codepoint
--- @return boolean
local function is_emoji(cp)
  return (cp >= 0x2600 and cp <= 0x26FF)    -- Miscellaneous Symbols
      or (cp >= 0x2700 and cp <= 0x27BF)    -- Dingbats
      or (cp >= 0x1F300 and cp <= 0x1F5FF)  -- Misc Symbols and Pictographs
      or (cp >= 0x1F600 and cp <= 0x1F64F)  -- Emoticons
      or (cp >= 0x1F680 and cp <= 0x1F6FF)  -- Transport and Map Symbols
      or (cp >= 0x1F900 and cp <= 0x1F9FF)  -- Supplemental Symbols
      or (cp >= 0x1FA00 and cp <= 0x1FA6F)  -- Symbols Extended-A
      or (cp >= 0x1FA70 and cp <= 0x1FAFF)  -- Symbols Extended-B
end

--- Str callback: wrap emoji characters in AccSupp for PDF /ActualText (#274).
--- Pandoc passes document text through as Str elements.  Emoji rendered by
--- Noto Color Emoji become bitmap images in the PDF — AccSupp adds /ActualText
--- so text extractors (PyMuPDF) can recover the Unicode codepoints.
function Str(el)
  if FORMAT ~= "latex" then return el end

  local text = el.text
  local result = pandoc.List({})
  local buf = {}

  for _, cp in utf8.codes(text) do
    if is_emoji(cp) then
      -- Flush non-emoji buffer
      if #buf > 0 then
        result:insert(pandoc.Str(table.concat(buf)))
        buf = {}
      end
      local ch = utf8.char(cp)
      result:insert(pandoc.RawInline("latex",
        "\\BeginAccSupp{ActualText={" .. ch .. "}}" .. ch .. "\\EndAccSupp{}"))
    else
      table.insert(buf, utf8.char(cp))
    end
  end

  -- Flush remaining non-emoji text
  if #buf > 0 then
    result:insert(pandoc.Str(table.concat(buf)))
  end

  if #result == 1 and result[1].t == "Str" then
    return el  -- No emoji found, return unchanged
  end
  return result
end
