#!/usr/bin/env python3
"""Post-process a .docx to restart footnote numbering at each chapter.

Inserts continuous section breaks before each Heading 1 paragraph and
sets footnote numbering to restart per section. This preserves OSCOLA's
per-chapter "(n X)" back-references which use chapter-local footnote numbers.

Only runs when --restart-footnotes is passed (the caller decides based on
document class — book/scrbook/report need this, articles do not).
"""
import re
import sys
import zipfile
import shutil
from io import BytesIO

if '--restart-footnotes' not in sys.argv:
    sys.exit(0)

args = [a for a in sys.argv[1:] if a != '--restart-footnotes']
if len(args) != 1:
    print(f"Usage: {sys.argv[0]} --restart-footnotes <file.docx>", file=sys.stderr)
    sys.exit(1)

docx_path = args[0]

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

# Read the docx into memory
with open(docx_path, 'rb') as f:
    docx_bytes = f.read()

zin = zipfile.ZipFile(BytesIO(docx_bytes), 'r')

# --- Patch settings.xml: add footnote restart per section ---
settings_xml = zin.read('word/settings.xml').decode('utf-8')

# Add <w:footnotePr><w:numRestart w:val="eachSect"/></w:footnotePr>
# Insert before </w:settings>
if 'w:footnotePr' not in settings_xml:
    settings_xml = settings_xml.replace(
        '</w:settings>',
        '<w:footnotePr><w:numRestart w:val="eachSect"/></w:footnotePr>'
        '</w:settings>')
elif 'w:numRestart' not in settings_xml:
    # footnotePr exists but no numRestart — add it
    settings_xml = re.sub(
        r'(<w:footnotePr[^/]*?)(/?>)',
        r'\1><w:numRestart w:val="eachSect"/></w:footnotePr>',
        settings_xml)

# --- Patch document.xml: insert section breaks before Heading 1 ---
doc_xml = zin.read('word/document.xml').decode('utf-8')

# Find the final sectPr (document-level section properties) to use as template
final_sect_match = re.search(
    r'<w:sectPr\b[^>]*>.*?</w:sectPr>',
    doc_xml, re.DOTALL)

if final_sect_match:
    final_sect = final_sect_match.group()
    # Create a continuous section break version (no page break)
    # Replace pgSz/pgMar etc. with just the type
    # Actually, we need to keep page size/margins but change type to continuous
    if '<w:type ' in final_sect:
        cont_sect = re.sub(r'<w:type\s+w:val="[^"]*"\s*/>',
                          '<w:type w:val="continuous"/>', final_sect)
    else:
        # Insert type="continuous" as first child of sectPr
        cont_sect = re.sub(r'(<w:sectPr\b[^>]*>)',
                          r'\1<w:type w:val="continuous"/>',
                          final_sect)

    # Add footnote restart inside sectPr (Word needs it per-section too)
    fn_restart = '<w:footnotePr><w:numRestart w:val="eachSect"/></w:footnotePr>'
    if fn_restart not in cont_sect:
        cont_sect = cont_sect.replace('</w:sectPr>', fn_restart + '</w:sectPr>')

    # Find all Heading 1 paragraphs and insert sectPr in their pPr
    # Pattern: <w:p ...><w:pPr><w:pStyle w:val="Heading1"/>...
    # We need to insert a sectPr into the pPr of the PREVIOUS paragraph
    # Actually, Word section breaks work by putting sectPr in the LAST
    # paragraph of the section. So we need to find the paragraph BEFORE
    # each Heading 1 and add sectPr to its pPr.

    # Find all paragraph boundaries
    para_pattern = re.compile(r'<w:p\b[^>]*>.*?</w:p>', re.DOTALL)
    paragraphs = list(para_pattern.finditer(doc_xml))

    # Detect which heading level represents chapters.
    # In book classes, tex4ht maps \chapter to <h2> → Heading2 (h1 is for \part).
    # Try Heading1 first; if none found, fall back to Heading2.
    chapter_style = None
    for style_candidate in ['Heading1', 'Heading2']:
        pattern = re.compile(
            r'<w:pStyle\s+w:val="' + style_candidate + r'"\s*/>')
        count = sum(1 for pm in paragraphs if pattern.search(pm.group()))
        if count > 0:
            chapter_style = style_candidate
            break

    if not chapter_style:
        print("No chapter headings found — skipping", file=sys.stderr)
        zin.close()
        sys.exit(0)

    chapter_pattern = re.compile(
        r'<w:pStyle\s+w:val="' + chapter_style + r'"\s*/>')
    heading1_indices = []
    for i, pm in enumerate(paragraphs):
        if chapter_pattern.search(pm.group()):
            heading1_indices.append(i)

    print(f"Found {len(heading1_indices)} {chapter_style} paragraphs",
          file=sys.stderr)

    # For each Heading 1 (except the first one, since there's no prior section),
    # insert a section break in the previous paragraph's pPr
    # Work backwards to preserve positions
    insertions = 0
    for h1_idx in reversed(heading1_indices):
        if h1_idx == 0:
            continue  # Skip first heading, no prior paragraph

        prev_para = paragraphs[h1_idx - 1]
        prev_text = prev_para.group()

        # Check if this paragraph already has a sectPr
        if '<w:sectPr' in prev_text:
            continue

        # Insert sectPr into the paragraph's pPr
        if '<w:pPr>' in prev_text:
            # Add sectPr inside existing pPr (before closing tag)
            new_text = prev_text.replace('</w:pPr>', cont_sect + '</w:pPr>')
        elif '<w:pPr/>' in prev_text:
            new_text = prev_text.replace('<w:pPr/>', '<w:pPr>' + cont_sect + '</w:pPr>')
        else:
            # No pPr at all — add one after <w:p...>
            new_text = re.sub(
                r'(<w:p\b[^>]*>)',
                r'\1<w:pPr>' + cont_sect + '</w:pPr>',
                prev_text, count=1)

        doc_xml = doc_xml[:prev_para.start()] + new_text + doc_xml[prev_para.end():]
        insertions += 1

    print(f"Inserted {insertions} section breaks", file=sys.stderr)

    # Ensure ALL sectPr elements have footnote restart (including the final one)
    def add_fn_restart(match):
        sect = match.group()
        if fn_restart in sect:
            return sect
        return sect.replace('</w:sectPr>', fn_restart + '</w:sectPr>')
    doc_xml = re.sub(r'<w:sectPr\b[^>]*>.*?</w:sectPr>', add_fn_restart,
                     doc_xml, flags=re.DOTALL)

# --- Write patched docx ---
with zipfile.ZipFile(docx_path, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        if item.filename == 'word/settings.xml':
            zout.writestr(item, settings_xml)
        elif item.filename == 'word/document.xml':
            zout.writestr(item, doc_xml)
        else:
            zout.writestr(item, zin.read(item.filename))

zin.close()
print(f"Patched: {docx_path}", file=sys.stderr)
