-- domfilters/make4ht-footnotes.lua
--
-- make4ht DOM filter that restructures tex4ht footnotes into the
-- format Pandoc expects for proper docx footnote generation.
--
-- ACTUAL tex4ht output structure (verified from test compilation):
--
-- Body refs:
--   <span class="footnote-mark"><a href="#fn1x0" id="fn1x0-bk">
--     <sup class="textsuperscript">1</sup></a></span>
--
-- Footnotes container:
--   <div class="footnotes">
--     <aside class="footnotetext" role="doc-footnote">
--       <p class="noindent">
--         <a id="x1-1002x1"></a>
--         <span class="footnote-mark"><a href="#fn1x0-bk" id="fn1x0">
--           <sup class="textsuperscript">1</sup></a></span>
--         <a id="x1-1003"></a>
--         <span class="ec-lmr-10">content...</span>
--       </p>
--     </aside>
--     ...
--   </div>
--
-- Target (Pandoc-compatible):
--   <sup><a class="footnote-ref" href="#fn1" id="fnref1"
--           role="doc-noteref">1</a></sup>
--
--   <section class="footnotes" role="doc-endnotes">
--     <hr />
--     <ol>
--       <li id="fn1" role="doc-endnote">
--         <p>content...
--         <a href="#fnref1" class="footnote-back"
--            role="doc-backlink">↩︎</a></p>
--       </li>
--     </ol>
--   </section>

local log = logging.new("footnotes")

local function restructure_footnotes(dom)

  -- Step 1: Find ALL footnotes containers (one per chapter in book classes)
  local fn_divs = dom:query_selector(".footnotes")
  if #fn_divs == 0 then
    log:warning("No .footnotes div found — document may have no footnotes")
    return dom
  end

  -- Step 2: Extract footnote content from all containers with globally unique IDs.
  -- tex4ht resets footnote numbering per chapter, so we assign a global counter.
  local footnotes = {}
  local global_fn = 0

  -- Build a map from tex4ht's per-chapter footnote-mark anchors to global IDs,
  -- so we can remap body references later.
  -- The body refs look like: <a href="#fn1x0" id="fn1x0-bk">
  -- The footnote-side anchors look like: <a href="#fn1x0-bk" id="fn1x0">
  -- We map the href targets (e.g. "fn1x0") to our global fn number.
  local anchor_to_global = {}

  for _, fn_div in ipairs(fn_divs) do
    local asides = fn_div:query_selector(".footnotetext")

    -- Fallback: if no asides found, try <p> elements directly (older tex4ht)
    if #asides == 0 then
      asides = fn_div:query_selector("p")
    end

    for _, aside in ipairs(asides) do
      -- Find the paragraph inside the aside (or use aside itself if it's a <p>)
      local p
      local ps = aside:query_selector("p")
      if #ps > 0 then
        p = ps[1]
      elseif aside:get_element_name() == "p" then
        p = aside
      else
        goto continue
      end

      -- Find and extract footnote number from the footnote-mark
      local marks = p:query_selector(".footnote-mark")
      local mark = marks[1]
      if not mark then goto continue end

      local fn_num = mark:get_text():match("(%d+)")
      if not fn_num then goto continue end

      -- Map the tex4ht anchor ID to our global number
      local mark_anchors = mark:query_selector("a")
      if #mark_anchors > 0 then
        local mark_id = mark_anchors[1]:get_attribute("id")
        if mark_id then
          global_fn = global_fn + 1
          anchor_to_global[mark_id] = global_fn
        end
      end

      -- Remove the footnote mark span
      mark:remove_node()

      -- Remove anchor elements that tex4ht inserts for cross-referencing
      -- (these have ids like "x1-1002x1" and no useful content)
      local anchors = p:query_selector("a")
      for _, a in ipairs(anchors) do
        local href = a:get_attribute("href")
        local id = a:get_attribute("id")
        -- Remove empty anchors (id-only, no href, no text content)
        if id and (not href or href == "") and a:get_text():match("^%s*$") then
          a:remove_node()
        end
      end

      -- Serialize the remaining paragraph content
      local content_html = ""
      for _, child in ipairs(p:get_children()) do
        content_html = content_html .. child:serialize()
      end

      -- Trim leading/trailing whitespace
      content_html = content_html:gsub("^%s+", ""):gsub("%s+$", "")

      if content_html ~= "" then
        table.insert(footnotes, {
          num = tostring(global_fn),
          content = content_html
        })
      end

      ::continue::
    end

    -- Remove this footnotes div
    fn_div:remove_node()
  end

  if #footnotes == 0 then
    log:warning("Found .footnotes div(s) but no extractable footnotes")
    return dom
  end

  log:info("Extracted " .. #footnotes .. " footnotes from " .. #fn_divs .. " container(s)")

  -- Step 3: Replace footnote references in the body text
  -- tex4ht: <span class="footnote-mark"><a href="#fn1x0" id="fn1x0-bk"><sup>1</sup></a></span>
  -- Pandoc: <sup><a class="footnote-ref" href="#fn1" id="fnref1" role="doc-noteref">1</a></sup>
  local marks = dom:query_selector(".footnote-mark")
  for _, mark in ipairs(marks) do
    -- Find the tex4ht anchor to determine which global footnote this maps to
    local mark_anchors = mark:query_selector("a")
    local global_num = nil
    if #mark_anchors > 0 then
      local href = mark_anchors[1]:get_attribute("href")
      if href then
        -- href is like "#fn1x0", the footnote-side id is "fn1x0"
        local target = href:gsub("^#", "")
        global_num = anchor_to_global[target]
      end
    end

    if global_num then
      local num_str = tostring(global_num)
      local new_sup = mark:create_element("sup")
      local new_a = new_sup:create_element("a", {
        class = "footnote-ref",
        href = "#fn" .. num_str,
        id = "fnref" .. num_str,
        role = "doc-noteref"
      })
      local text_node = new_a:create_text_node(num_str)
      new_a:add_child_node(text_node)
      new_sup:add_child_node(new_a)

      mark:replace_node(new_sup)
    end
  end

  -- Step 4: Build the Pandoc-style footnotes section
  local domobject = require("luaxml-domobject")

  local parts = {
    '<section class="footnotes" role="doc-endnotes">',
    '<hr />',
    '<ol>'
  }
  for _, fn in ipairs(footnotes) do
    parts[#parts + 1] = '<li id="fn' .. fn.num .. '" role="doc-endnote">'
    parts[#parts + 1] = '<p>' .. fn.content
      .. ' <a href="#fnref' .. fn.num
      .. '" class="footnote-back" role="doc-backlink">↩︎</a>'
    parts[#parts + 1] = '</p></li>'
  end
  parts[#parts + 1] = '</ol></section>'

  local section_html = table.concat(parts, "\n")

  -- Parse the HTML fragment and append to body
  local section_dom = domobject.html_parse(section_html)
  local bodies = dom:query_selector("body")
  if #bodies > 0 then
    local body = bodies[1]
    local root = section_dom:root_node()
    for _, child in ipairs(root:get_children()) do
      if child:is_element() then
        body:add_child_node(child)
      end
    end
  end

  return dom
end

return restructure_footnotes
