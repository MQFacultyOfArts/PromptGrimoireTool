-- E5 experiment: dump AST + emit \highLight for data-hl spans
-- NOTE: Pandoc strips "data-" prefix, so data-hl becomes just "hl"

local dump_count = 0

function dump_element(tag, el)
  dump_count = dump_count + 1
  local attrs_str = ""
  if el.attr then
    local id = el.attr.identifier or ""
    local classes = el.attr.classes or {}
    local kvs = el.attr.attributes or {}
    if id ~= "" then attrs_str = attrs_str .. " id=" .. id end
    if #classes > 0 then attrs_str = attrs_str .. " classes={" .. table.concat(classes, ",") .. "}" end
    for k, v in pairs(kvs) do
      attrs_str = attrs_str .. " " .. k .. "=" .. v
    end
  end
  if el.text then
    local text_preview = string.sub(el.text, 1, 40)
    io.stderr:write(string.format("[%03d] %s: text=%q%s\n", dump_count, tag, text_preview, attrs_str))
  else
    io.stderr:write(string.format("[%03d] %s:%s\n", dump_count, tag, attrs_str))
  end
end

function Span(el)
  dump_element("Span", el)
  -- Pandoc strips "data-" prefix, so data-hl="5" becomes hl="5"
  local hl = el.attr.attributes["hl"]
  if hl then
    io.stderr:write("  >> Found hl=" .. hl .. ", wrapping in \\highLight\n")
    local open = pandoc.RawInline("latex", "\\highLight[yellow]{")
    local close = pandoc.RawInline("latex", "}")
    local result = pandoc.List({open})
    result:extend(el.content)
    result:extend({close})
    return result
  end
  return el
end

function Str(el)
  dump_element("Str", el)
  return el
end

function Space(el)
  dump_count = dump_count + 1
  io.stderr:write(string.format("[%03d] Space\n", dump_count))
  return el
end

function Header(el)
  dump_element("Header", el)
  return el
end

function Para(el)
  dump_element("Para", el)
  return el
end

function Div(el)
  dump_element("Div", el)
  return el
end

function SoftBreak(el)
  dump_count = dump_count + 1
  io.stderr:write(string.format("[%03d] SoftBreak\n", dump_count))
  return el
end

function RawInline(el)
  dump_element("RawInline", el)
  return el
end

function RawBlock(el)
  dump_element("RawBlock", el)
  return el
end
