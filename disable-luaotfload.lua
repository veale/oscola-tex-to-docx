-- disable-luaotfload.lua
-- Aggressively disable luaotfload for dvilualatex (tex4ht) compatibility.
-- luaotfload is baked into the lualatex format and its font processing
-- causes infinite loops when the output is DVI rather than PDF.

texio.write_nl("oscola2docx: disabling luaotfload for DVI mode")

-- Remove all known luaotfload callbacks
local callbacks_to_remove = {
  {"define_font", "luaotfload.define_font"},
  {"pre_linebreak_filter", "luaotfload.node_processor"},
  {"hpack_filter", "luaotfload.node_processor"},
  {"glyph_stream_provider", "luaotfload.glyph_stream"},
  {"pre_output_filter", "luaotfload.node_processor"},
  {"post_linebreak_filter", "luaotfload.node_processor"},
}

for _, cb in ipairs(callbacks_to_remove) do
  pcall(function()
    luatexbase.remove_from_callback(cb[1], cb[2])
    texio.write_nl("oscola2docx: removed " .. cb[1] .. "/" .. cb[2])
  end)
end

-- List all remaining callbacks so we can debug
if callback and callback.list then
  texio.write_nl("oscola2docx: remaining callbacks:")
  for name, _ in pairs(callback.list()) do
    local info = callback.list and callback.list()
    -- just list callback names that have registered functions
  end
end

-- Neuter the font loader itself
if fonts and fonts.definers then
  local original = fonts.definers.read
  fonts.definers.read = function(name, size, id)
    texio.write_nl("oscola2docx: font request blocked: " .. (name or "nil"))
    return nil -- fall back to TeX's native font handling
  end
end

-- Prevent luaotfload from re-initialising
if luaotfload then
  luaotfload.main = function() end
  if luaotfload.init then
    luaotfload.init = function() return true end
  end
end
