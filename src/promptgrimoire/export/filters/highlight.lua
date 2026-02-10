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

--- Span callback: transform highlighted spans into LaTeX commands.
function Span(el)
  if FORMAT ~= "latex" then return el end

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
  -- No special heading handling needed: Pandoc auto-wraps the entire
  -- Span content (including RawInline outputs) in \texorpdfstring{}
  -- when the span is inside a heading (validated in E2b experiment).
  local annots = el.attributes["annots"]
  if annots ~= nil and annots ~= "" then
    result:insert(pandoc.RawInline("latex", annots))
  end

  return result
end
