function Span(el)
  local hl = el.attr.attributes["hl"]
  if not hl then return el end
  local color = el.attr.attributes["data-color"] or "yellow"
  local open = pandoc.RawInline("latex", "\\highLight[" .. color .. "]{")
  local close = pandoc.RawInline("latex", "}")
  local result = pandoc.List({open})
  result:extend(el.content)
  result:extend({close})
  return result
end
