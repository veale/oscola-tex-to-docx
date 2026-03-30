#!/usr/bin/env python3
"""Resolve unresolved biblatex citation keys in HTML output.

When make4ht runs in draft mode (no biber), footnotes contain raw citation keys
like 'chenGenerativePretrainingPixels2020' instead of formatted references.
This script parses the .bib files and replaces those keys with basic formatted
citations (Author, 'Title' (Year)).

Usage: python resolve-citations.py input.html refs.bib [more.bib ...] -o output.html
"""
import re
import sys
import argparse
from pathlib import Path


def parse_bib_entries(bib_path):
    """Parse .bib file into a dict of key -> {fields}."""
    text = open(bib_path, encoding='utf-8', errors='replace').read()
    entries = {}

    # Match @type{key, ... }
    # Use a simple brace-depth parser
    for m in re.finditer(r'@(\w+)\s*\{([^,]+),', text):
        entry_type = m.group(1).lower()
        key = m.group(2).strip()
        if entry_type == 'comment':
            continue

        # Find the matching closing brace
        start = m.end()
        depth = 1
        pos = start
        while pos < len(text) and depth > 0:
            if text[pos] == '{':
                depth += 1
            elif text[pos] == '}':
                depth -= 1
            pos += 1
        body = text[start:pos - 1]

        # Parse fields
        fields = {}
        for fm in re.finditer(r'(\w+)\s*=\s*[\{"](.+?)[\}"](?=\s*,|\s*$)',
                              body, re.DOTALL):
            fname = fm.group(1).lower()
            fval = fm.group(2).strip()
            # Remove inner braces
            fval = re.sub(r'\{([^{}]*)\}', r'\1', fval)
            fval = fval.replace('\n', ' ').strip()
            fields[fname] = fval

        fields['_type'] = entry_type
        entries[key] = fields

    return entries


def format_citation(entry):
    """Format a bib entry as a basic citation string."""
    author = entry.get('author', entry.get('editor', ''))
    title = entry.get('title', entry.get('booktitle', ''))
    year = entry.get('year', entry.get('date', ''))
    if year and '-' in year:
        year = year.split('-')[0]  # Extract year from date like 2023-01-15

    # Clean up author: "Last, First and Last2, First2" → "Last and Last2"
    if ' and ' in author:
        authors = author.split(' and ')
        if len(authors) > 2:
            first = authors[0].split(',')[0].strip()
            author = f'{first} and others'
        else:
            names = [a.split(',')[0].strip() for a in authors]
            author = ' and '.join(names)
    elif ',' in author:
        author = author.split(',')[0].strip()

    entry_type = entry.get('_type', 'misc')

    if entry_type in ('book', 'inbook', 'collection'):
        # Book: Author, Title (Year)
        parts = []
        if author:
            parts.append(author)
        if title:
            parts.append(f'<em>{title}</em>')
        if year:
            parts.append(f'({year})')
        return ' '.join(parts) if parts else None
    elif entry_type in ('article', 'inproceedings', 'incollection'):
        # Article: Author, 'Title' (Year)
        journal = entry.get('journaltitle', entry.get('journal', ''))
        parts = []
        if author:
            parts.append(author)
        if title:
            parts.append(f'\u2018{title}\u2019')
        if journal:
            parts.append(f'<em>{journal}</em>')
        if year:
            parts.append(f'({year})')
        return ' '.join(parts) if parts else None
    elif entry_type in ('legislation', 'legal', 'jurisdiction'):
        # Legal: just the title
        return title or None
    elif entry_type == 'online':
        parts = []
        if author:
            parts.append(author)
        if title:
            parts.append(f'\u2018{title}\u2019')
        org = entry.get('organization', '')
        if org:
            parts.append(f'({org})')
        if year:
            parts.append(f'({year})')
        return ' '.join(parts) if parts else None
    else:
        # Generic
        parts = []
        if author:
            parts.append(author)
        if title:
            parts.append(f'\u2018{title}\u2019')
        if year:
            parts.append(f'({year})')
        return ' '.join(parts) if parts else None


def main():
    parser = argparse.ArgumentParser(description='Resolve citation keys in HTML')
    parser.add_argument('html', help='Input HTML file')
    parser.add_argument('bibs', nargs='+', help='.bib files')
    parser.add_argument('-o', '--output', required=True, help='Output HTML file')
    args = parser.parse_args()

    # Parse all bib files
    entries = {}
    for bib in args.bibs:
        entries.update(parse_bib_entries(bib))

    html = open(args.html, encoding='utf-8').read()

    # Replace citation keys in footnotes
    # Pattern: <span class='rm-lmbx-9'>KEY</span><span class='rm-lmr-9'>.</span>
    resolved = 0
    unresolved = []

    def replace_citation(m):
        nonlocal resolved
        key = m.group(1)
        if key in entries:
            formatted = format_citation(entries[key])
            if formatted:
                resolved += 1
                return f'{formatted}.'
        unresolved.append(key)
        return m.group(0)

    html = re.sub(
        r"<span class='rm-lmbx-9'>([a-zA-Z][a-zA-Z0-9_:-]+)</span>"
        r"<span class='rm-lmr-9'>\.</span>",
        replace_citation, html)

    # Also handle bare keys that might appear differently
    # Pattern: bold key followed by period
    html = re.sub(
        r'<span class="rm-lmbx-9">([a-zA-Z][a-zA-Z0-9_:-]+)</span>'
        r'<span class="rm-lmr-9">\.</span>',
        replace_citation, html)

    open(args.output, 'w', encoding='utf-8').write(html)

    print(f"Resolved: {resolved} citations", file=sys.stderr)
    if unresolved:
        unique = sorted(set(unresolved))
        print(f"Unresolved: {len(unique)} unique keys", file=sys.stderr)
        for k in unique[:10]:
            print(f"  - {k}", file=sys.stderr)
        if len(unique) > 10:
            print(f"  ... and {len(unique) - 10} more", file=sys.stderr)


if __name__ == '__main__':
    main()
