-- Pandoc Lua filter for legal document LaTeX output.
-- Handles ordered list start attributes and preserves margin indents.

-- Handle <ol start="N"> by injecting \setcounter{enumi}{N-1} before the list.
-- LaTeX enumerate increments before displaying, so we set to N-1.
function OrderedList(el)
  if el.start and el.start > 1 then
    local preamble = pandoc.RawBlock('latex',
      string.format('\\setcounter{enumi}{%d}', el.start - 1))
    return {preamble, el}
  end
  return el
end

-- BlockQuote handling - pandoc's default quote environment is fine,
-- but we could customise here if needed for specific margin behaviours.
function BlockQuote(el)
  return el
end
