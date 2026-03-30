-- pandoc-footnotes.lua
-- Converts Pandoc-style HTML footnote structure to real Pandoc Notes
-- which become proper Word footnotes in docx output.
--
-- Four-pass filter:
-- Pass 1: Collect footnote content from the <section class="footnotes">
-- Pass 2: Replace footnote-ref links with pandoc.Note elements
-- Pass 3: Convert "(n X)" cross-reference links to Word NOTEREF fields
-- Pass 4: Insert bookmarks at the start of each footnote for NOTEREF targets

local footnote_contents = {}
local bookmark_id_counter = 100
local note_counter = 0

-- Helper: extract inlines from blocks, skipping back-reference links
local function extract_inlines(blocks)
  local inlines = {}
  for _, block in ipairs(blocks) do
    if block.t == "Para" or block.t == "Plain" then
      for _, inline in ipairs(block.content) do
        if not (inline.t == "Link"
                and inline.classes
                and inline.classes:includes("footnote-back")) then
          table.insert(inlines, inline)
        end
      end
    elseif block.t == "Div" then
      local nested = extract_inlines(block.content)
      for _, inline in ipairs(nested) do
        table.insert(inlines, inline)
      end
    end
  end
  return inlines
end

-- Helper: trim leading and trailing Space elements
local function trim_spaces(inlines)
  while #inlines > 0 and inlines[1].t == "Space" do
    table.remove(inlines, 1)
  end
  while #inlines > 0 and inlines[#inlines].t == "Space" do
    table.remove(inlines)
  end
  return inlines
end

-- Helper: extract the plain-text number from a Link's content
local function get_link_text(link)
  local texts = {}
  local function collect(inlines)
    for _, il in ipairs(inlines) do
      if il.t == "Str" then
        table.insert(texts, il.text)
      elseif il.t == "Span" then
        collect(il.content)
      end
    end
  end
  collect(link.content)
  return table.concat(texts)
end

-- Helper: check if a link is a tex4ht cross-reference to a footnote
local function is_footnote_crossref(link)
  if link.target:match("^#x1%-") then
    local text = get_link_text(link)
    if text:match("^%d+$") then
      return true, text
    end
  end
  return false, nil
end

-- Helper: create a Word bookmark start/end pair as raw XML
local function make_bookmark(name)
  local id = tostring(bookmark_id_counter)
  bookmark_id_counter = bookmark_id_counter + 1
  local start_xml = string.format(
    '<w:bookmarkStart w:id="%s" w:name="%s"/>', id, name)
  local end_xml = string.format(
    '<w:bookmarkEnd w:id="%s"/>', id)
  return pandoc.RawInline("openxml", start_xml),
         pandoc.RawInline("openxml", end_xml)
end

-- Helper: create a NOTEREF field that references a bookmark
local function make_noteref(bookmark_name, display_num)
  local xml = string.format(
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    .. '<w:r><w:instrText xml:space="preserve"> NOTEREF %s \\h </w:instrText></w:r>'
    .. '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    .. '<w:r><w:t>%s</w:t></w:r>'
    .. '<w:r><w:fldChar w:fldCharType="end"/></w:r>',
    bookmark_name, display_num)
  return pandoc.RawInline("openxml", xml)
end

-- Pass 1: Collect footnote content from the footnotes section
local function collect_footnotes(el)
  if el.classes:includes("footnotes") then
    for _, block in ipairs(el.content) do
      if block.t == "OrderedList" then
        for i, item in ipairs(block.content) do
          local fn_num = tostring(i)

          if #item > 0 and item[1].t == "Div" and item[1].identifier then
            local id_num = item[1].identifier:match("^fn(%d+)$")
            if id_num then fn_num = id_num end
          end

          local inlines = trim_spaces(extract_inlines(item))

          if #inlines > 0 then
            footnote_contents[fn_num] = {pandoc.Para(inlines)}
          end
        end
      end
    end
    return {}
  end
  return el
end

-- Pass 2: Replace footnote references with Note elements
local function replace_ref_link(el)
  if el.classes:includes("footnote-ref") then
    local target = el.target:gsub("^#fn", "")
    if footnote_contents[target] then
      return pandoc.Note(footnote_contents[target])
    end
  end
  return el
end

local function replace_ref_sup(el)
  for _, inline in ipairs(el.content) do
    if inline.t == "Link" and inline.classes:includes("footnote-ref") then
      local target = inline.target:gsub("^#fn", "")
      if footnote_contents[target] then
        return pandoc.Note(footnote_contents[target])
      end
    end
  end
  return el
end

-- Pass 3: Convert "(n X)" cross-reference links to NOTEREF fields
local function convert_crossrefs(el)
  local is_xref, fn_num = is_footnote_crossref(el)
  if is_xref then
    return make_noteref("oscola_fn" .. fn_num, fn_num)
  end
  return el
end

-- Pass 4: Insert bookmarks at the start of each footnote
-- We walk every Note element and prepend a bookmark.
-- The note_counter tracks the sequential footnote number.
local function insert_bookmarks(el)
  note_counter = note_counter + 1
  local fn_num = tostring(note_counter)
  local bk_start, bk_end = make_bookmark("oscola_fn" .. fn_num)

  -- Find the first Para/Plain block and prepend the bookmark
  for _, block in ipairs(el.content) do
    if block.t == "Para" or block.t == "Plain" then
      table.insert(block.content, 1, bk_end)
      table.insert(block.content, 1, bk_start)
      return el
    end
  end

  -- Fallback: wrap in a new Para
  local new_para = pandoc.Para({bk_start, bk_end})
  table.insert(el.content, 1, new_para)
  return el
end

return {
  {Div = collect_footnotes},
  {Superscript = replace_ref_sup, Link = replace_ref_link},
  {Link = convert_crossrefs},
  {Note = insert_bookmarks}
}
