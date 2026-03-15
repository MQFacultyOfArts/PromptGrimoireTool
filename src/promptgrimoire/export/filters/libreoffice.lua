-- Pandoc Lua filter for LibreOffice HTML to LaTeX conversion.
-- Handles CSS properties that Pandoc doesn't translate:
--   - Table column widths from HTML width attributes → X\textwidth
--   - LineBreak in table cells → \newline
--   - margin-left → adjustwidth environment
--   - Speaker turns → mdframed environments with left border

-- Global state for speaker turn tracking
local current_speaker = nil  -- 'user' or 'assistant' or 'system' or nil

-- Lookup table for speaker role → environment, label, colour
local speaker_roles = {
  user      = { env = 'userturn',      label = 'User:',      color = 'usercolor' },
  assistant = { env = 'assistantturn', label = 'Assistant:', color = 'assistantcolor' },
  system    = { env = 'systemturn',    label = 'System:',    color = 'systemcolor' },
}

-- Parse CSS margin value for a given property, return value and unit or nil
-- Supports: in, cm, em, rem, px
-- rem converts to em (1:1), px converts to pt (x0.75)
local function parse_margin(style, property)
  if not style then return nil, nil end

  -- Build pattern: property:%s*value+unit
  -- Try inches
  local pattern = property .. ':%s*([%d%.]+)in'
  local value = style:match(pattern)
  if value then
    return tonumber(value), 'in'
  end

  -- Try centimeters
  pattern = property .. ':%s*([%d%.]+)cm'
  value = style:match(pattern)
  if value then
    return tonumber(value), 'cm'
  end

  -- Try em (LaTeX native)
  pattern = property .. ':%s*([%d%.]+)em'
  value = style:match(pattern)
  if value then
    return tonumber(value), 'em'
  end

  -- Try rem (convert to em, 1:1 ratio)
  pattern = property .. ':%s*([%d%.]+)rem'
  value = style:match(pattern)
  if value then
    return tonumber(value), 'em'  -- rem -> em
  end

  -- Try px (convert to pt, x0.75)
  pattern = property .. ':%s*([%d%.]+)px'
  value = style:match(pattern)
  if value then
    local pt_value = tonumber(value) * 0.75
    -- Clean up decimal: use integer if whole number
    if pt_value == math.floor(pt_value) then
      return math.floor(pt_value), 'pt'
    else
      return pt_value, 'pt'
    end
  end

  return nil, nil
end

-- Backward-compatible wrapper for margin-left
local function parse_margin_left(style)
  return parse_margin(style, 'margin%-left')
end

-- Convert Pandoc inlines to LaTeX string
local function inlines_to_latex(inlines)
  -- Use pandoc's writer to convert inlines to latex
  local doc = pandoc.Pandoc({pandoc.Para(inlines)})
  local latex = pandoc.write(doc, 'latex')
  -- Remove the surrounding paragraph
  latex = latex:gsub('^%s*', ''):gsub('%s*$', '')
  return latex
end

-- Convert Pandoc blocks to LaTeX string
local function blocks_to_latex(blocks)
  local doc = pandoc.Pandoc(blocks)
  local latex = pandoc.write(doc, 'latex')
  return latex:gsub('^%s*', ''):gsub('%s*$', '')
end

-- Handle Table elements: generate raw LaTeX with proper column widths
function Table(tbl)
  if FORMAT ~= 'latex' then return tbl end

  -- Collect cell widths from first row
  local col_widths = {}
  local total_width = 0
  local num_cols = #tbl.colspecs

  for _, body in ipairs(tbl.bodies) do
    if body.body and #body.body > 0 then
      local first_row = body.body[1]
      for i, cell in ipairs(first_row.cells) do
        local width_str = cell.attr.attributes['width']
        if width_str then
          local width = tonumber(width_str)
          if width then
            col_widths[i] = width
            total_width = total_width + width
          end
        end
      end
      break
    end
  end

  -- If no widths found, measure content and generate wrapping p{} columns
  if total_width == 0 then
    -- Measure content length per column
    local max_lengths = {}
    for i = 1, num_cols do
      max_lengths[i] = 1  -- minimum 1 to avoid division by zero
    end

    -- Measure head rows
    if tbl.head and tbl.head.rows then
      for _, row in ipairs(tbl.head.rows) do
        for i, cell in ipairs(row.cells) do
          local len = #pandoc.utils.stringify(cell.contents)
          if len > max_lengths[i] then
            max_lengths[i] = len
          end
        end
      end
    end

    -- Measure body rows
    for _, body in ipairs(tbl.bodies) do
      if body.body then
        for _, row in ipairs(body.body) do
          for i, cell in ipairs(row.cells) do
            local len = #pandoc.utils.stringify(cell.contents)
            if len > max_lengths[i] then
              max_lengths[i] = len
            end
          end
        end
      end
    end

    -- Calculate proportional widths with minimum floor
    local total_length = 0
    for i = 1, num_cols do
      total_length = total_length + max_lengths[i]
    end

    local min_proportion = 0.10  -- minimum 10% per column
    -- First pass: compute raw proportions with floor
    local proportions = {}
    for i = 1, num_cols do
      local raw = (max_lengths[i] / total_length) * 0.97
      proportions[i] = raw < min_proportion and min_proportion or raw
    end
    -- Re-normalise so proportions sum to 0.97 after floor clamping
    local clamped_sum = 0
    for i = 1, num_cols do clamped_sum = clamped_sum + proportions[i] end
    local scale = 0.97 / clamped_sum
    local col_spec_parts = {}
    for i = 1, num_cols do
      table.insert(col_spec_parts, string.format('p{%.2f\\textwidth}', proportions[i] * scale))
    end
    local content_col_spec = table.concat(col_spec_parts, '')

    -- Build header rows
    local header_latex = {}
    if tbl.head and tbl.head.rows then
      for _, row in ipairs(tbl.head.rows) do
        local cells_latex = {}
        for _, cell in ipairs(row.cells) do
          local cell_latex = blocks_to_latex(cell.contents)
          cell_latex = cell_latex:gsub('\\hfill\\break', '\\newline{}')
          cell_latex = cell_latex:gsub('\\\\\n', '\\newline{}')
          cell_latex = cell_latex:gsub('\n\n', '\\newline{}')
          table.insert(cells_latex, cell_latex)
        end
        table.insert(header_latex, table.concat(cells_latex, ' & ') .. ' \\\\')
      end
    end

    -- Build body rows
    local content_rows_latex = {}
    for _, body in ipairs(tbl.bodies) do
      if body.body then
        for _, row in ipairs(body.body) do
          local cells_latex = {}
          for _, cell in ipairs(row.cells) do
            local cell_latex = blocks_to_latex(cell.contents)
            cell_latex = cell_latex:gsub('\\hfill\\break', '\\newline{}')
            cell_latex = cell_latex:gsub('\\\\\n', '\\newline{}')
            cell_latex = cell_latex:gsub('\n\n', '\\newline{}')
            table.insert(cells_latex, cell_latex)
          end
          table.insert(content_rows_latex, table.concat(cells_latex, ' & ') .. ' \\\\')
        end
      end
    end

    -- Assemble longtable with \small wrapping
    local parts = {'\\begingroup\\small'}
    table.insert(parts, string.format('\\begin{longtable}{@{}%s@{}}', content_col_spec))

    if #header_latex > 0 then
      table.insert(parts, '\\toprule')
      for _, hrow in ipairs(header_latex) do
        table.insert(parts, hrow)
      end
      table.insert(parts, '\\midrule')
      table.insert(parts, '\\endhead')
    end

    for _, brow in ipairs(content_rows_latex) do
      table.insert(parts, brow)
    end

    table.insert(parts, '\\bottomrule')
    table.insert(parts, '\\end{longtable}')
    table.insert(parts, '\\endgroup')

    return pandoc.RawBlock('latex', table.concat(parts, '\n'))
  end

  -- Build column spec with \textwidth proportions
  -- Leave small gap for column separation
  local col_spec = ''
  local width_sum = 0
  for i = 1, num_cols do
    local width = col_widths[i] or (total_width / num_cols)
    local proportion = (width / total_width) * 0.97  -- 97% to leave room for separation
    width_sum = width_sum + proportion
    col_spec = col_spec .. string.format('p{%.2f\\textwidth}', proportion)
  end

  -- Build table rows
  local rows_latex = {}

  for _, body in ipairs(tbl.bodies) do
    if body.body then
      for _, row in ipairs(body.body) do
        local cells_latex = {}
        for _, cell in ipairs(row.cells) do
          -- Convert cell content to LaTeX
          local cell_latex = blocks_to_latex(cell.contents)
          -- Replace line breaks with \newline (handles both LibreOffice and web HTML)
          -- \hfill\break comes from LibreOffice, \\ + newline comes from <br/> tags
          -- \n\n (paragraph break) comes from multiple block elements (e.g., <div>s)
          cell_latex = cell_latex:gsub('\\hfill\\break', '\\newline{}')
          cell_latex = cell_latex:gsub('\\\\\n', '\\newline{}')
          cell_latex = cell_latex:gsub('\n\n', '\\newline{}')
          table.insert(cells_latex, cell_latex)
        end
        table.insert(rows_latex, table.concat(cells_latex, ' & ') .. ' \\\\')
      end
    end
  end

  -- Generate longtable
  local latex = string.format([[
\begin{longtable}{@{}%s@{}}
%s
\end{longtable}
]], col_spec, table.concat(rows_latex, '\n'))

  return pandoc.RawBlock('latex', latex)
end

-- Handle Div elements: speaker turns, margin-left style
-- Note: margin-top/margin-bottom support disabled pending investigation
-- of spacing regression in enumerated lists
function Div(elem)
  if FORMAT ~= 'latex' then return elem end

  -- Handle thinking section markers (Claude's extended thinking summary)
  -- Note: Pandoc strips 'data-' prefix, so data-thinking becomes just 'thinking'
  local thinking = elem.attr.attributes['thinking']
  if thinking then
    -- Wrap thinking content in footnotesize and gray color
    local open = pandoc.RawBlock('latex', '\\begingroup\\footnotesize\\color{gray}')
    local close = pandoc.RawBlock('latex', '\\endgroup')

    local result = {open}
    for _, block in ipairs(elem.content) do
      table.insert(result, block)
    end
    table.insert(result, close)
    return result
  end

  -- Handle speaker turn markers (inserted by platforms.preprocess_for_export)
  -- Note: Pandoc strips 'data-' prefix, so data-speaker becomes just 'speaker'
  local speaker = elem.attr.attributes['speaker']
  if speaker then
    local role_info = speaker_roles[speaker]
    if not role_info then return elem end  -- unknown role, pass through

    local result = {}

    -- Close previous speaker turn environment if open
    if current_speaker then
      local prev_info = speaker_roles[current_speaker]
      if prev_info then
        table.insert(result, pandoc.RawBlock('latex', '\\end{' .. prev_info.env .. '}'))
      end
    end

    -- Add spacing and label before the environment
    table.insert(result, pandoc.RawBlock('latex', string.format([[

\vspace{0.8\baselineskip}
\noindent{\footnotesize\textcolor{%s}{\textbf{%s}}}
\vspace{0.3\baselineskip}
]], role_info.color, role_info.label)))

    -- Open new speaker turn environment
    table.insert(result, pandoc.RawBlock('latex', '\\begin{' .. role_info.env .. '}'))

    -- Include the div's own content (ChatCraft-ingested HTML wraps
    -- turn content inside the data-speaker div rather than using
    -- empty marker divs followed by sibling content).
    for _, block in ipairs(elem.content) do
      table.insert(result, block)
    end

    -- Update state
    current_speaker = speaker

    return result
  end

  local style = elem.attr.attributes['style']
  if not style then return elem end

  local margin, unit = parse_margin_left(style)
  if margin and margin > 0 then
    -- Use adjustwidth environment for indentation (preserves original unit)
    local open = pandoc.RawBlock('latex',
      string.format('\\begin{adjustwidth}{%s%s}{}', margin, unit))
    local close = pandoc.RawBlock('latex', '\\end{adjustwidth}')

    local result = {open}
    for _, block in ipairs(elem.content) do
      table.insert(result, block)
    end
    table.insert(result, close)
    return result
  end

  return elem
end

-- Check if inlines list contains only LineBreaks and spaces
local function only_linebreaks(inlines)
  for _, el in ipairs(inlines) do
    if el.t ~= 'LineBreak' and el.t ~= 'Space' and el.t ~= 'SoftBreak' then
      return false
    end
  end
  return true
end

-- Handle Para: remove paragraphs that only contain line breaks,
-- and strip leading line breaks from content paragraphs
function Para(elem)
  if FORMAT ~= 'latex' then return elem end

  -- If paragraph only contains line breaks, convert to vertical space
  if only_linebreaks(elem.content) then
    return pandoc.RawBlock('latex', '\\vspace{\\baselineskip}')
  end

  -- Strip leading LineBreaks from content
  local content = elem.content
  while #content > 0 and (content[1].t == 'LineBreak' or content[1].t == 'SoftBreak') do
    table.remove(content, 1)
  end

  -- Replace remaining LineBreaks with \newline
  local new_content = {}
  for _, el in ipairs(content) do
    if el.t == 'LineBreak' then
      table.insert(new_content, pandoc.RawInline('latex', '\\newline{}'))
    else
      table.insert(new_content, el)
    end
  end

  return pandoc.Para(new_content)
end

-- Document-level filter to close final speaker turn environment
function Pandoc(doc)
  if FORMAT ~= 'latex' then return doc end

  -- If there's an open speaker turn, close it
  if current_speaker then
    local info = speaker_roles[current_speaker]
    if info then
      table.insert(doc.blocks, pandoc.RawBlock('latex', '\\end{' .. info.env .. '}'))
    end
    current_speaker = nil  -- Reset state
  end

  return doc
end

-- Don't convert LineBreak globally - let Para handle it
-- This avoids issues with standalone LineBreaks
