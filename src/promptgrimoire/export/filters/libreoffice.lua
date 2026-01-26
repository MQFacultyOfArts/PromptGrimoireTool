-- Pandoc Lua filter for LibreOffice HTML to LaTeX conversion.
-- Handles CSS properties that Pandoc doesn't translate:
--   - Table column widths from HTML width attributes → X\textwidth
--   - LineBreak in table cells → \newline
--   - margin-left → adjustwidth environment
--   - text-transform: uppercase → \MakeUppercase

-- Parse CSS margin-left value, return inches as number or nil
local function parse_margin_left(style)
  if not style then return nil end
  local value = style:match('margin%-left:%s*([%d%.]+)in')
  if value then
    return tonumber(value)
  end
  return nil
end

-- Escape special LaTeX characters in text
local function escape_latex(text)
  local replacements = {
    ['\\'] = '\\textbackslash{}',
    ['&'] = '\\&',
    ['%%'] = '\\%%',
    ['%$'] = '\\$',
    ['#'] = '\\#',
    ['_'] = '\\_',
    ['{'] = '\\{',
    ['}'] = '\\}',
    ['~'] = '\\textasciitilde{}',
    ['%^'] = '\\textasciicircum{}',
  }
  for char, escaped in pairs(replacements) do
    text = text:gsub(char, escaped)
  end
  return text
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

  -- If no widths found, let Pandoc handle it
  if total_width == 0 then return tbl end

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
          -- Replace \hfill\break with \newline for line breaks
          cell_latex = cell_latex:gsub('\\hfill\\break', '\\newline{}')
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

-- Handle Div elements with margin-left style
function Div(elem)
  if FORMAT ~= 'latex' then return elem end

  local style = elem.attr.attributes['style']
  if not style then return elem end

  local margin = parse_margin_left(style)
  if margin and margin > 0 then
    -- Use adjustwidth environment for indentation
    local open = pandoc.RawBlock('latex',
      string.format('\\begin{adjustwidth}{%sin}{}', margin))
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

-- Don't convert LineBreak globally - let Para handle it
-- This avoids issues with standalone LineBreaks
