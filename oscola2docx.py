#!/usr/bin/env python3
"""
oscola2docx - Convert OSCOLA-style LaTeX to Word docx.

Usage: python oscola2docx.py input.tex [-o output.docx] [--draft] [--keep-html] [--no-domfilter]
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def check_dependencies(use_domfilter=True):
    """Verify all required tools are available."""
    missing = []
    for cmd in ['make4ht', 'biber', 'pandoc']:
        if shutil.which(cmd) is None:
            missing.append(cmd)

    if not use_domfilter:
        try:
            import bs4  # noqa: F401
        except ImportError:
            missing.append('beautifulsoup4 (pip install beautifulsoup4)')

    if missing:
        print("Missing dependencies:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)


def count_docx_footnotes(docx_path):
    """Count real footnotes in the docx output."""
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            if 'word/footnotes.xml' not in z.namelist():
                return 0
            xml = z.read('word/footnotes.xml')
            tree = ElementTree.fromstring(xml)
            ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
            footnotes = tree.findall(f'.//{{{ns}}}footnote')
            return len([fn for fn in footnotes if fn.get(f'{{{ns}}}type') is None])
    except Exception:
        return -1


def run(cmd, cwd=None, check=True):
    """Run a command and return the result."""
    print(f"  Running: {' '.join(str(c) for c in cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error running {cmd[0]}:", file=sys.stderr)
        if result.stdout:
            print(result.stdout[-2000:], file=sys.stderr)
        if result.stderr:
            print(result.stderr[-2000:], file=sys.stderr)
        sys.exit(1)
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Convert OSCOLA-style LaTeX to Word docx')
    parser.add_argument('input', help='Input .tex file')
    parser.add_argument('-o', '--output', help='Output .docx file')
    parser.add_argument('--draft', action='store_true',
                        help='Single-pass compilation (faster, citations unresolved)')
    parser.add_argument('--keep-html', action='store_true',
                        help='Keep intermediate HTML files for debugging')
    parser.add_argument('--no-domfilter', action='store_true',
                        help='Use Python fallback instead of Lua DOM filter')
    parser.add_argument('--reference-doc',
                        help='Custom reference docx for styling (default: bundled reference.docx)')
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    input_path = Path(args.input).resolve()

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output).resolve() if args.output else \
        input_path.with_suffix('.docx')

    check_dependencies(use_domfilter=not args.no_domfilter)

    # Create temporary working directory
    work_dir = Path(tempfile.mkdtemp(prefix='oscola2docx_'))
    print(f"Working directory: {work_dir}", file=sys.stderr)

    try:
        # Copy input files (tex, bib, images, fonts, styles)
        source_dir = input_path.parent
        extensions = ['.tex', '.bib', '.sty', '.bst', '.cls',
                      '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.svg',
                      '.otf', '.ttf', '.woff', '.woff2']
        for ext in extensions:
            for f in source_dir.glob(f'*{ext}'):
                shutil.copy2(f, work_dir)

        # Copy subdirectories that TeX may reference (chapters, fonts, images, etc.)
        # Skips hidden dirs and common non-TeX directories.
        skip_dirs = {'.', '__pycache__', 'node_modules'}
        for d in source_dir.iterdir():
            if d.is_dir() and d.name not in skip_dirs and not d.name.startswith('.'):
                shutil.copytree(d, work_dir / d.name, dirs_exist_ok=True)

        # Copy pipeline files
        if not args.no_domfilter:
            shutil.copy2(script_dir / 'myfile.mk4', work_dir)
            (work_dir / 'domfilters').mkdir(exist_ok=True)
            shutil.copy2(script_dir / 'domfilters' / 'make4ht-footnotes.lua',
                         work_dir / 'domfilters')
        else:
            shutil.copy2(script_dir / 'myfile-nodomfilter.mk4',
                         work_dir / 'myfile.mk4')
            shutil.copy2(script_dir / 'fix-footnotes.py', work_dir)

        shutil.copy2(script_dir / 'oscola2docx.cfg', work_dir)
        shutil.copy2(script_dir / 'tex4ht-fontspec-hooks.4ht',
                     work_dir / 'fontspec-hooks.4ht')
        shutil.copy2(script_dir / 'tex4ht-fonts.4ht', work_dir / 'fontspec.4ht')
        shutil.copy2(script_dir / 'disable-luaotfload.lua', work_dir)

        input_base = input_path.stem

        # Pre-process: strip commands that cause tex4ht to hang
        run(['python3', str(script_dir / 'preprocess-tex.py'),
             str(work_dir / f'{input_base}.tex')], cwd=work_dir)

        # Run make4ht
        print("Running make4ht...", file=sys.stderr)
        make4ht_cmd = [
            'make4ht', '-e', 'myfile.mk4', '-c', 'oscola2docx.cfg',
            '-l', '-f', 'html5+common_domfilters'
        ]
        if args.draft:
            make4ht_cmd.extend(['-m', 'draft'])
        make4ht_cmd.extend([f'{input_base}.tex', 'fn-in,svg'])

        run(make4ht_cmd, cwd=work_dir, check=False)

        html_file = work_dir / f'{input_base}.html'
        if not html_file.exists():
            print(f"Error: make4ht did not produce {html_file.name}. "
                  f"Check the log in {work_dir}",
                  file=sys.stderr)
            sys.exit(1)

        # Python fallback if --no-domfilter
        if args.no_domfilter:
            print("Running Python footnote fixer...", file=sys.stderr)
            fixed_file = work_dir / f'{input_base}-fixed.html'
            run(['python3', 'fix-footnotes.py', str(html_file), str(fixed_file)],
                cwd=work_dir)
            html_file = fixed_file

        # Resolve citation keys from .bib files (draft mode leaves raw keys)
        bib_files = list(work_dir.glob('*.bib'))
        if bib_files:
            print("Resolving citations from .bib files...", file=sys.stderr)
            resolved_file = work_dir / f'{input_base}-resolved.html'
            resolve_cmd = [
                'python3', str(script_dir / 'resolve-citations.py'),
                str(html_file)
            ] + [str(b) for b in bib_files] + ['-o', str(resolved_file)]
            result = run(resolve_cmd, cwd=work_dir, check=False)
            if resolved_file.exists():
                html_file = resolved_file

        # Run Pandoc
        print("Running Pandoc...", file=sys.stderr)
        pandoc_cmd = [
            'pandoc', str(html_file),
            '--lua-filter', str(script_dir / 'pandoc-footnotes.lua'),
            '-o', str(output_path),
            '--from', 'html',
            '--to', 'docx',
            '--extract-media', '.'
        ]
        # Use reference doc: user-provided > bundled > none
        if args.reference_doc:
            ref_doc = Path(args.reference_doc).resolve()
            if not ref_doc.exists():
                print(f"Error: Reference doc not found: {ref_doc}",
                      file=sys.stderr)
                sys.exit(1)
            pandoc_cmd.extend(['--reference-doc', str(ref_doc)])
        else:
            ref_doc = script_dir / 'reference.docx'
            if ref_doc.exists():
                pandoc_cmd.extend(['--reference-doc', str(ref_doc)])

        run(pandoc_cmd, cwd=work_dir)

        # Keep HTML if requested
        if args.keep_html:
            output_dir = output_path.parent
            intermediate = work_dir / f'{input_base}.html'
            if intermediate.exists():
                dest = output_dir / f'{input_base}-intermediate.html'
                shutil.copy2(intermediate, dest)
                print(f"Intermediate HTML: {dest}", file=sys.stderr)
            fixed = work_dir / f'{input_base}-fixed.html'
            if fixed.exists():
                dest = output_dir / f'{input_base}-fixed.html'
                shutil.copy2(fixed, dest)
                print(f"Fixed HTML: {dest}", file=sys.stderr)

        # Report
        fn_count = count_docx_footnotes(output_path)
        print(f"Output: {output_path}", file=sys.stderr)
        if fn_count >= 0:
            print(f"Footnotes in output: {fn_count}", file=sys.stderr)
        print("Done.", file=sys.stderr)

    finally:
        if not args.keep_html:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
