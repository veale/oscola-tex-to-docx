#!/usr/bin/env python3
"""
Restructure tex4ht footnotes into Pandoc-compatible format.

This is a FALLBACK tool. In normal operation, the make4ht DOM filter
(domfilters/make4ht-footnotes.lua) handles this restructuring inside
the make4ht pipeline. Use this script for debugging, or when the DOM
filter cannot handle a particular document.

Usage: python fix-footnotes.py input.html output.html
"""

import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup, NavigableString, Comment
except ImportError:
    print("Error: beautifulsoup4 is required. Install with: pip install beautifulsoup4",
          file=sys.stderr)
    sys.exit(1)


def count_footnotes(html, stage_name):
    """Count footnote refs and bodies for pipeline validation."""
    soup = BeautifulSoup(html, 'html.parser')

    refs = len(soup.find_all('a', class_='footnote-ref')) or \
           len(soup.find_all('span', class_='footnote-mark'))

    fn_section = soup.find('section', class_='footnotes') or \
                 soup.find('div', class_='footnotes')
    bodies = 0
    if fn_section:
        bodies = len(fn_section.find_all('li')) or \
                 len(fn_section.find_all('aside', class_='footnotetext')) or \
                 len(fn_section.find_all('p', recursive=False))

    print(f"[{stage_name}] Footnote refs: {refs}, bodies: {bodies}",
          file=sys.stderr)

    if refs != bodies and refs > 0 and bodies > 0:
        print(f"  WARNING: mismatch!", file=sys.stderr)

    return refs, bodies


def find_footnote_div(soup):
    """
    Locate the footnotes container. tex4ht may use different
    structures depending on configuration and version.
    """
    # Strategy 1: div with class "footnotes" (most common with fn-in)
    fn_div = soup.find('div', class_='footnotes')
    if fn_div:
        return fn_div

    # Strategy 2: look for a div at the end of body containing footnote-mark spans
    body = soup.find('body')
    if body:
        for div in reversed(body.find_all('div')):
            if div.find('span', class_='footnote-mark'):
                return div

    return None


def extract_footnote_content(container):
    """
    Extract footnotes from the container. Handles both:
    - <aside class="footnotetext"> elements (modern tex4ht)
    - <p> elements directly in the div (older tex4ht)
    """
    footnotes = {}

    # Try <aside class="footnotetext"> first (actual tex4ht output)
    asides = container.find_all('aside', class_='footnotetext')
    if not asides:
        # Fallback: <p> elements containing footnote-mark spans
        asides = [p for p in container.find_all('p', recursive=False)
                  if p.find('span', class_='footnote-mark')]

    for aside in asides:
        # Find the paragraph inside the aside
        p = aside.find('p') if aside.name == 'aside' else aside

        mark = p.find('span', class_='footnote-mark')
        if not mark:
            continue

        # Extract footnote number from displayed text
        fn_num = None
        sup = mark.find('sup')
        if sup:
            fn_num = sup.get_text(strip=True)
        if not fn_num:
            text = mark.get_text(strip=True)
            m = re.search(r'(\d+)', text)
            if m:
                fn_num = m.group(1)

        if not fn_num:
            continue

        # Remove the footnote mark
        mark.decompose()

        # Remove empty anchor elements (tex4ht cross-ref anchors)
        for a in p.find_all('a'):
            if a.get('id') and not a.get('href') and not a.get_text(strip=True):
                a.decompose()
            elif a.get('id') and a.get('href', '') == '' and not a.get_text(strip=True):
                a.decompose()

        # Remove HTML comments
        for comment in p.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()

        # Get inner HTML content
        content = ''.join(str(c) for c in p.children).strip()

        if content:
            footnotes[fn_num] = content

    return footnotes


def fix_footnotes(html):
    """Main transformation: restructure tex4ht footnotes for Pandoc."""
    soup = BeautifulSoup(html, 'html.parser')

    fn_div = find_footnote_div(soup)
    if not fn_div:
        print("WARNING: No footnotes container found", file=sys.stderr)
        return str(soup)

    # Extract footnotes
    footnotes = extract_footnote_content(fn_div)
    if not footnotes:
        print("WARNING: No footnotes extracted from container", file=sys.stderr)
        return str(soup)

    print(f"Extracted {len(footnotes)} footnotes", file=sys.stderr)

    # Remove original footnotes container
    fn_div.decompose()

    # Replace footnote references in body text
    for mark in soup.find_all('span', class_='footnote-mark'):
        fn_num = None
        sup = mark.find('sup')
        if sup:
            fn_num = sup.get_text(strip=True)
        if not fn_num:
            m = re.search(r'(\d+)', mark.get_text())
            if m:
                fn_num = m.group(1)

        if fn_num:
            new_sup = soup.new_tag('sup')
            new_a = soup.new_tag('a',
                                 attrs={'class': 'footnote-ref',
                                        'href': f'#fn{fn_num}',
                                        'id': f'fnref{fn_num}',
                                        'role': 'doc-noteref'})
            new_a.string = fn_num
            new_sup.append(new_a)
            mark.replace_with(new_sup)

    # Build Pandoc-style footnotes section
    section = soup.new_tag('section',
                           attrs={'class': 'footnotes',
                                  'role': 'doc-endnotes'})
    section.append(soup.new_tag('hr'))
    ol = soup.new_tag('ol')

    # Sort by numeric key
    for fn_num in sorted(footnotes.keys(), key=int):
        li = soup.new_tag('li', id=f'fn{fn_num}', role='doc-endnote')
        # Parse the content HTML and wrap in <p>
        content_soup = BeautifulSoup(
            f'<p>{footnotes[fn_num]} '
            f'<a href="#fnref{fn_num}" class="footnote-back" '
            f'role="doc-backlink">↩︎</a></p>',
            'html.parser')
        for child in list(content_soup.children):
            li.append(child)
        ol.append(li)

    section.append(ol)

    body = soup.find('body')
    if body:
        body.append(section)

    return str(soup)


def main():
    if len(sys.argv) < 3:
        print("Usage: python fix-footnotes.py input.html output.html",
              file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    html = input_path.read_text(encoding='utf-8')

    count_footnotes(html, "before")
    result = fix_footnotes(html)
    count_footnotes(result, "after")

    output_path.write_text(result, encoding='utf-8')
    print(f"Written to {output_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
