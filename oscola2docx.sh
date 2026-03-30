#!/usr/bin/env bash
set -euo pipefail

# oscola2docx - Convert OSCOLA-style LaTeX to Word docx
#
# Usage: oscola2docx input.tex [-o output.docx] [--draft] [--keep-html] [--no-domfilter]
#
# Prerequisites:
#   - TeX Live (with make4ht, biber, biblatex, biblatex-oscola)
#   - Pandoc
#   - Python 3 with beautifulsoup4 (only if --no-domfilter)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Argument parsing ---
INPUT=""
OUTPUT=""
DRAFT=false
KEEP_HTML=false
USE_DOMFILTER=true
REFERENCE_DOC=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--output)
            OUTPUT="$2"
            shift 2
            ;;
        --draft)
            DRAFT=true
            shift
            ;;
        --keep-html)
            KEEP_HTML=true
            shift
            ;;
        --no-domfilter)
            USE_DOMFILTER=false
            shift
            ;;
        --reference-doc)
            REFERENCE_DOC="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: oscola2docx input.tex [-o output.docx] [--draft] [--keep-html] [--no-domfilter] [--reference-doc FILE]"
            echo ""
            echo "Options:"
            echo "  -o, --output FILE        Output docx path (default: input with .docx extension)"
            echo "  --draft                  Single-pass compilation (faster, citations unresolved)"
            echo "  --keep-html              Keep intermediate HTML files for debugging"
            echo "  --no-domfilter           Use Python fallback instead of Lua DOM filter"
            echo "  --reference-doc FILE     Custom reference docx for styling (default: bundled reference.docx)"
            echo "  -h, --help               Show this help"
            exit 0
            ;;
        -*)
            echo "Error: Unknown option $1" >&2
            exit 1
            ;;
        *)
            if [[ -z "$INPUT" ]]; then
                INPUT="$1"
            else
                echo "Error: Unexpected argument $1" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$INPUT" ]]; then
    echo "Error: No input file specified" >&2
    echo "Usage: oscola2docx input.tex [-o output.docx]" >&2
    exit 1
fi

if [[ ! -f "$INPUT" ]]; then
    echo "Error: Input file not found: $INPUT" >&2
    exit 1
fi

# Resolve absolute path
INPUT="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
INPUT_DIR="$(dirname "$INPUT")"
INPUT_BASE="$(basename "$INPUT" .tex)"

if [[ -z "$OUTPUT" ]]; then
    OUTPUT="${INPUT_DIR}/${INPUT_BASE}.docx"
fi
OUTPUT="$(cd "$(dirname "$OUTPUT")" 2>/dev/null && pwd)/$(basename "$OUTPUT")" || OUTPUT="$(pwd)/$(basename "$OUTPUT")"

# --- Check prerequisites ---
MISSING=()
for cmd in make4ht biber pandoc; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING+=("$cmd")
    fi
done

if [[ "$USE_DOMFILTER" == false ]]; then
    if ! command -v python3 &>/dev/null; then
        MISSING+=("python3")
    elif ! python3 -c "import bs4" 2>/dev/null; then
        MISSING+=("beautifulsoup4 (pip install beautifulsoup4)")
    fi
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "Error: Missing dependencies:" >&2
    for m in "${MISSING[@]}"; do
        echo "  - $m" >&2
    done
    exit 1
fi

# --- Create temporary working directory ---
WORK_DIR="$(mktemp -d)"
trap 'if [[ "$KEEP_HTML" == false ]]; then rm -rf "$WORK_DIR"; fi' EXIT

echo "Working directory: $WORK_DIR"

# Copy input files (tex, bib, images, fonts, styles from source directory)
for ext in tex bib sty bst cls png jpg jpeg pdf eps svg otf ttf woff woff2; do
    for f in "$INPUT_DIR"/*."$ext"; do
        [[ -f "$f" ]] && cp "$f" "$WORK_DIR/" 2>/dev/null || true
    done
done

# Copy subdirectories that TeX may reference (chapters, fonts, images, etc.)
# Skips hidden dirs and common non-TeX directories to avoid copying large files.
for d in "$INPUT_DIR"/*/; do
    if [[ ! -d "$d" ]]; then continue; fi
    dirname="$(basename "$d")"
    case "$dirname" in
        .*|__pycache__|node_modules) continue ;;
    esac
    cp -r "${d%/}" "$WORK_DIR/" 2>/dev/null || true
done

# Copy pipeline files
if [[ "$USE_DOMFILTER" == true ]]; then
    cp "$SCRIPT_DIR/myfile.mk4" "$WORK_DIR/"
    mkdir -p "$WORK_DIR/domfilters"
    cp "$SCRIPT_DIR/domfilters/make4ht-footnotes.lua" "$WORK_DIR/domfilters/"
else
    cp "$SCRIPT_DIR/myfile-nodomfilter.mk4" "$WORK_DIR/myfile.mk4"
    cp "$SCRIPT_DIR/fix-footnotes.py" "$WORK_DIR/"
fi
cp "$SCRIPT_DIR/oscola2docx.cfg" "$WORK_DIR/"
cp "$SCRIPT_DIR/tex4ht-fontspec-hooks.4ht" "$WORK_DIR/fontspec-hooks.4ht"
cp "$SCRIPT_DIR/tex4ht-fonts.4ht" "$WORK_DIR/fontspec.4ht"
cp "$SCRIPT_DIR/disable-luaotfload.lua" "$WORK_DIR/"

# --- Pre-process: strip commands that cause tex4ht to hang ---
cd "$WORK_DIR"
python3 "$SCRIPT_DIR/preprocess-tex.py" "$INPUT_BASE.tex" 2>&1 || echo "Warning: pre-processing failed, continuing with original"

# --- Run make4ht ---
echo "Running make4ht..."
MAKE4HT_ARGS=(-e myfile.mk4 -c oscola2docx.cfg -l -f html5+common_domfilters)
if [[ "$DRAFT" == true ]]; then
    MAKE4HT_ARGS+=(-m draft)
fi
MAKE4HT_ARGS+=("$INPUT_BASE.tex" "fn-in,svg")

make4ht "${MAKE4HT_ARGS[@]}" 2>&1 || true

HTMLFILE="${INPUT_BASE}.html"

if [[ ! -f "$HTMLFILE" ]]; then
    echo "Error: make4ht did not produce $HTMLFILE. Check the log:" >&2
    [[ -f "${INPUT_BASE}.log" ]] && tail -30 "${INPUT_BASE}.log" >&2
    exit 1
fi

# --- Python fallback (if --no-domfilter) ---
if [[ "$USE_DOMFILTER" == false ]]; then
    echo "Running Python footnote fixer..."
    FIXED="${INPUT_BASE}-fixed.html"
    if ! python3 fix-footnotes.py "$HTMLFILE" "$FIXED" 2>&1; then
        echo "Error: fix-footnotes.py failed" >&2
        exit 1
    fi
    HTMLFILE="$FIXED"
fi

# --- Resolve citations from .bib files ---
BIB_FILES=("$WORK_DIR"/*.bib)
if [[ ${#BIB_FILES[@]} -gt 0 && -f "${BIB_FILES[0]}" ]]; then
    echo "Resolving citations..."
    RESOLVED="${INPUT_BASE}-resolved.html"
    if python3 "$SCRIPT_DIR/resolve-citations.py" "$HTMLFILE" "${BIB_FILES[@]}" -o "$RESOLVED" 2>&1; then
        HTMLFILE="$RESOLVED"
    fi
fi

# --- Run Pandoc ---
echo "Running Pandoc..."
PANDOC_ARGS=(
    "$HTMLFILE"
    --lua-filter="$SCRIPT_DIR/pandoc-footnotes.lua"
    -o "$OUTPUT"
    --from html
    --to docx
    --extract-media=.
)

# Use reference doc: user-provided > bundled > none
if [[ -n "$REFERENCE_DOC" ]]; then
    if [[ ! -f "$REFERENCE_DOC" ]]; then
        echo "Error: Reference doc not found: $REFERENCE_DOC" >&2
        exit 1
    fi
    PANDOC_ARGS+=(--reference-doc="$REFERENCE_DOC")
elif [[ -f "$SCRIPT_DIR/reference.docx" ]]; then
    PANDOC_ARGS+=(--reference-doc="$SCRIPT_DIR/reference.docx")
fi

if ! pandoc "${PANDOC_ARGS[@]}" 2>&1; then
    echo "Error: Pandoc failed" >&2
    exit 1
fi

# --- Fix footnote numbering (restart per chapter for book classes) ---
RESTART_FLAG=""
if grep -qE '\\documentclass(\[.*\])?\{(scr)?book\}|\\documentclass(\[.*\])?\{(scr)?reprt\}' "$INPUT_BASE.tex" 2>/dev/null; then
    RESTART_FLAG="--restart-footnotes"
    echo "Book class detected — restarting footnote numbering per chapter..."
fi
python3 "$SCRIPT_DIR/fix-footnote-numbering.py" $RESTART_FLAG "$OUTPUT" 2>&1 || echo "Warning: footnote numbering fix failed, continuing"

# --- Keep HTML if requested ---
if [[ "$KEEP_HTML" == true ]]; then
    OUTPUT_DIR="$(dirname "$OUTPUT")"
    cp "$WORK_DIR/${INPUT_BASE}.html" "$OUTPUT_DIR/${INPUT_BASE}-intermediate.html"
    echo "Intermediate HTML saved: ${OUTPUT_DIR}/${INPUT_BASE}-intermediate.html"
    if [[ -f "$WORK_DIR/${INPUT_BASE}-fixed.html" ]]; then
        cp "$WORK_DIR/${INPUT_BASE}-fixed.html" "$OUTPUT_DIR/${INPUT_BASE}-fixed.html"
        echo "Fixed HTML saved: ${OUTPUT_DIR}/${INPUT_BASE}-fixed.html"
    fi
fi

# --- Report ---
echo "Output: $OUTPUT"

# Quick footnote count
if command -v python3 &>/dev/null; then
    python3 -c "
import zipfile
from xml.etree import ElementTree
with zipfile.ZipFile('$OUTPUT', 'r') as z:
    if 'word/footnotes.xml' in z.namelist():
        xml = z.read('word/footnotes.xml')
        tree = ElementTree.fromstring(xml)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        fns = tree.findall('.//w:footnote', ns)
        real = [f for f in fns if f.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type') is None]
        print(f'Footnotes in output: {len(real)}')
" 2>/dev/null || true
fi

echo "Done."
