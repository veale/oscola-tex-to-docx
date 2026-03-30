#!/usr/bin/env python3
"""
Validate the oscola2docx conversion pipeline.

Counts footnotes at each stage and reports mismatches.

Usage: python validate.py input.tex [intermediate.html] output.docx
"""

import re
import sys
import zipfile
from xml.etree import ElementTree
from pathlib import Path


def count_tex_footnotes(tex_path):
    """Count citation and footnote commands in the source."""
    text = Path(tex_path).read_text(encoding='utf-8')

    # Remove comments
    text = re.sub(r'(?<!\\)%.*$', '', text, flags=re.MULTILINE)

    commands = [
        r'\\footcite\b',
        r'\\footcites\b',
        r'\\footnote\b',
        r'\\autocite\b',
    ]

    total = 0
    for cmd in commands:
        matches = re.findall(cmd, text)
        count = len(matches)
        if count > 0:
            cmd_name = cmd.replace('\\\\', '\\').replace(r'\b', '')
            print(f"  {cmd_name}: {count}")
        total += count

    return total


def count_html_footnotes(html_path):
    """Count footnotes in the intermediate HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  (beautifulsoup4 not installed, skipping HTML validation)")
        return -1

    html = Path(html_path).read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'html.parser')

    # Check for Pandoc-style footnotes (post DOM filter)
    refs = soup.find_all('a', class_='footnote-ref')
    if refs:
        section = soup.find('section', class_='footnotes')
        bodies = section.find_all('li') if section else []
        print(f"  Refs (footnote-ref links): {len(refs)}")
        print(f"  Bodies (li in footnotes section): {len(bodies)}")
        if len(refs) != len(bodies):
            print(f"  WARNING: ref/body mismatch!")
        return len(refs)

    # Check for raw tex4ht footnotes (pre DOM filter)
    marks = soup.find_all('span', class_='footnote-mark')
    # Halve the count since marks appear both in body and footnote div
    fn_div = soup.find('div', class_='footnotes')
    if fn_div:
        body_marks = [m for m in marks if not m.find_parent('div', class_='footnotes')]
        print(f"  Footnote marks in body: {len(body_marks)}")
        asides = fn_div.find_all('aside', class_='footnotetext')
        print(f"  Footnote bodies (aside): {len(asides)}")
        return len(body_marks)

    print("  No footnotes found in HTML")
    return 0


def count_docx_footnotes(docx_path):
    """Count footnotes in the docx output."""
    with zipfile.ZipFile(docx_path, 'r') as z:
        if 'word/footnotes.xml' not in z.namelist():
            print("  No footnotes.xml in docx")
            return 0
        xml = z.read('word/footnotes.xml')
        tree = ElementTree.fromstring(xml)

        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        footnotes = tree.findall('.//w:footnote', ns)

        # Filter out separator/continuation footnotes (type attribute present)
        real = [fn for fn in footnotes
                if fn.get(f'{{{ns["w"]}}}type') is None]

        return len(real)


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate.py input.tex [intermediate.html] output.docx")
        sys.exit(1)

    args = sys.argv[1:]
    tex_path = None
    html_path = None
    docx_path = None

    for arg in args:
        if arg.endswith('.tex'):
            tex_path = arg
        elif arg.endswith('.html'):
            html_path = arg
        elif arg.endswith('.docx'):
            docx_path = arg

    ok = True

    if tex_path:
        print(f"\nTeX source ({tex_path}):")
        tex_count = count_tex_footnotes(tex_path)
        print(f"  Total footnote commands: {tex_count}")

    if html_path:
        print(f"\nHTML intermediate ({html_path}):")
        html_count = count_html_footnotes(html_path)

    if docx_path:
        print(f"\nDOCX output ({docx_path}):")
        docx_count = count_docx_footnotes(docx_path)
        print(f"  Real footnotes: {docx_count}")

    # Cross-check
    if tex_path and docx_path:
        print(f"\nCross-check:")
        print(f"  TeX commands: {tex_count}")
        print(f"  DOCX footnotes: {docx_count}")
        if tex_count == docx_count:
            print(f"  PASS: counts match")
        else:
            print(f"  NOTE: counts differ (footcites produces 1 footnote from multiple commands)")
            ok = False

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
