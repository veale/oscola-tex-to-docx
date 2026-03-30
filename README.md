# oscola2docx

Convert LaTeX documents using `biblatex-oscola` (the OSCOLA legal citation style) to `.docx` files with correct Word footnotes.

This tool exists because biblatex-oscola's citation formatting — ibid tracking, "(n X)" back-references, case/legislation formatting, conditional short titles — is too complex for any external converter to replicate. Instead, we let TeX do the formatting via `make4ht`, capture the HTML output, resolve citations from `.bib` files, then convert to docx via Pandoc.

## Prerequisites

- **TeX Live** with `make4ht`, `biber`, `biblatex`, and `biblatex-oscola`
- **Pandoc**
- **Python 3**

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

# Keep intermediate HTML for debugging
./oscola2docx.sh input.tex --keep-html

# Use Python fallback instead of Lua DOM filter
./oscola2docx.sh input.tex --no-domfilter

# Use a custom reference docx for styling
./oscola2docx.sh input.tex --reference-doc my-styles.docx

# Draft mode (single pass, no biber — citations unresolved)
./oscola2docx.sh input.tex --draft
```

### Full vs draft mode

**Full mode** (default) runs `htlatex → biber → htlatex → htlatex` (4 passes) for TeX-native OSCOLA citation formatting with ibid tracking, "(n X)" back-references, and proper author/title/year formatting. The preprocessor patches biblatex-oscola's `\footcite` macros to avoid a known tex4ht stack overflow (see Technical Notes below).

**Draft mode** (`--draft`) runs a single `htlatex` pass and resolves citations post-hoc by parsing your `.bib` files. This is faster but produces simplified citations without OSCOLA formatting.

## How it works

1. **Preprocessing** strips packages and commands that cause `dvilualatex` to hang or are irrelevant for HTML output: `fontspec`, `unicode-math`, `luatexja-fontspec`, `soul`, `pdflscape`, KOMA-Script page styles, font setup commands, `\ghostprompt`, `\maketitle`, `\tableofcontents`, `\printbibliography`, etc.
2. **make4ht** compiles the LaTeX document with `dvilualatex`, producing HTML with footnotes. TikZ and PGF diagrams are rendered to SVG via `dvisvgm`.
3. **Citation resolution** (`resolve-citations.py`) parses `.bib` files and replaces raw citation keys in footnotes with formatted author/title/year text.
4. **DOM filter** (or Python fallback) restructures tex4ht's footnote HTML into the format Pandoc expects.
5. **Pandoc** with a Lua filter converts the HTML footnote structure into real `pandoc.Note` AST elements, producing proper Word footnotes in the docx output. Generated images (SVGs from TikZ, etc.) are embedded into the docx via `--extract-media`.

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
| `preprocess-tex.py` | Strips problematic packages/commands for DVI mode |
| `resolve-citations.py` | Resolves citation keys from .bib files in HTML |
| `myfile.mk4` | make4ht build sequence + DOM filter registration |
| `oscola2docx.cfg` | tex4ht HTML configuration |
| `tex4ht-fontspec-hooks.4ht` | Blocks fontspec loading in DVI mode |
| `tex4ht-fonts.4ht` | Font command stubs for DVI mode |
| `disable-luaotfload.lua` | Removes luaotfload callbacks in DVI mode |
| `domfilters/make4ht-footnotes.lua` | Footnote restructuring (primary) |
| `fix-footnotes.py` | Footnote restructuring (fallback) |
| `pandoc-footnotes.lua` | Pandoc AST filter for footnotes |
| `validate.py` | Pipeline validation |
| `reference.docx` | Bundled style template for docx output |

## Figures, tables, and diagrams

The pipeline handles non-text content as follows:

- **TikZ / PGF diagrams** are rendered to SVG by `dvisvgm` (via the `svg` tex4ht option) and embedded in the docx. In draft mode, diagrams may not render fully since only one htlatex pass runs.
- **Figures** (`\begin{figure}`) are wrapped in `<figure>` / `<figcaption>` HTML elements so Pandoc produces proper image blocks with captions.
- **Tables** (`\begin{table}`) are wrapped in a container div to preserve caption association. Standard `tabular`, `booktabs`, and `tabularx` tables convert well; complex cell spans or coloured cells may need manual touch-up in Word.
- **`\includegraphics`** images (PNG, JPG, PDF, SVG, EPS) are copied into the working directory and embedded in the docx via Pandoc's `--extract-media`.
- **Landscape pages** (`pdflscape`) are silently ignored since there is no HTML/DOCX equivalent.

## Technical notes

### biblatex-oscola + tex4ht stack overflow fix

biblatex-oscola (via `verbose-inote.cbx`) uses `\label{cbx@N}` inside `footcite:save` and `\ref{cbx@...}` inside `footcite:note:old` for "(n X)" back-references. tex4ht redefines `\label` and `\ref` with heavy expansion (`\Protect\l::bel`, `\cur:th`, `\a:newlabel`) that recurses when called inside footnote citation contexts, causing `TeX capacity exceeded [input stack size=10000]`.

The preprocessor fixes this by injecting code after `\begin{document}` that replaces these macros with the originals tex4ht saved as `\:label` (`\csname :label\endcsname` with `\catcode\`\:=11`) and `\o:ref`. This means "(n X)" back-references won't be hyperlinked in HTML, but they resolve correctly via the standard `.aux` mechanism.

## Known limitations

- **fontspec / luaotfload**: These packages cause infinite loops in DVI mode. They are automatically stripped by the preprocessor and blocked by tex4ht hooks.
- **CJK text**: `luatexja-fontspec` is stripped. CJK characters will appear in the output if the system has appropriate fonts, but without specific font selection.
- **`\sout` / `\ul` (soul package)**: Replaced with passthrough stubs since `soul` is stripped.
- **Per-chapter footnote numbering**: tex4ht resets footnote numbers per chapter in book classes. The DOM filter renumbers them globally for the docx output.

## License

Mozilla Public License 2.0
