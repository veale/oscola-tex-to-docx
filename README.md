# oscola2docx

Convert LaTeX documents using `biblatex-oscola` (the OSCOLA legal citation style) to `.docx` files with correct Word footnotes.

This tool exists because biblatex-oscola's citation formatting — ibid tracking (at least for editions below the 5th), "(n X)" back-references, case/legislation formatting, conditional short titles — is too complex for any external converter to replicate. Instead, we let TeX do the formatting via `make4ht`, capture the HTML output with fully resolved citations, then convert to docx via Pandoc.

## Prerequisites

- **TeX Live** with `make4ht`, `biber`, `biblatex`, and `biblatex-oscola`
- **Pandoc**
- **Python 3** (optional, only for `--no-domfilter` fallback mode)

Install dependencies:
```bash
./install-deps.sh
```

## Usage

```bash
# Basic usage
./oscola2docx.sh input.tex -o output.docx

# Or with Python
python3 oscola2docx.py input.tex -o output.docx

# Draft mode (single pass, faster but citations unresolved)
./oscola2docx.sh input.tex --draft

# Keep intermediate HTML for debugging
./oscola2docx.sh input.tex --keep-html

# Use Python fallback instead of Lua DOM filter
./oscola2docx.sh input.tex --no-domfilter

# Use a custom reference docx for styling
./oscola2docx.sh input.tex --reference-doc my-styles.docx
```

## How it works

1. **make4ht** compiles the LaTeX document with `lualatex` and `biber`, producing HTML with fully resolved OSCOLA citations including "(n X)" back-references.
2. **DOM filter** (or Python fallback) restructures tex4ht's footnote HTML into the format Pandoc expects.
3. **Pandoc** with a Lua filter converts the HTML footnote structure into real `pandoc.Note` AST elements, producing proper Word footnotes in the docx output.

## Validation

```bash
python3 validate.py test/test-article.tex output.docx
```

This counts footnotes at each pipeline stage and reports mismatches.

## Styling

The output is styled using a bundled `reference.docx` template. Pandoc reads style definitions from this file and applies them to the output — the placeholder text in the reference doc is ignored.

By default, the template uses **ETBookOT** as the body font. I just felt like it. If you don't have ETBookOT installed, Word should (but who knows) fall back to Times New Roman via the `altName` entry in the font table. This is fine and requires no action. To get the intended look, install ETBookOT from [its GitHub repository](https://github.com/edwardtufte/et-book).

To use your own styling, pass `--reference-doc my-styles.docx`. You can create a starting point with:
```bash
pandoc -o my-styles.docx --print-default-data-file reference.docx
```
Then open it in Word, modify the styles (Normal, Heading 1, Footnote Text, etc.), and save.

## Files

| File | Purpose |
|------|---------|
| `oscola2docx.sh` | Main entry point (Bash) |
| `oscola2docx.py` | Alternative entry point (Python) |
| `myfile.mk4` | make4ht build sequence + DOM filter registration |
| `oscola2docx.cfg` | tex4ht HTML configuration |
| `domfilters/make4ht-footnotes.lua` | Footnote restructuring (primary) |
| `fix-footnotes.py` | Footnote restructuring (fallback) |
| `pandoc-footnotes.lua` | Pandoc AST filter for footnotes |
| `validate.py` | Pipeline validation |
| `reference.docx` | Bundled style template for docx output |

## License

Mozilla Public License 2.0
