#!/usr/bin/env python3
"""Pre-process a .tex file for tex4ht compatibility.

Strips commands and packages that cause dvilualatex to hang or are
irrelevant for HTML output.  Operates in-place on the given file.
"""
import re
import sys

if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} <file.tex>", file=sys.stderr)
    sys.exit(1)

path = sys.argv[1]
text = open(path, encoding='utf-8').read()


def eat_args(text, pos):
    """Starting at pos, consume all [...] and {...} argument blocks.
    Returns the position after the last consumed block."""
    while pos < len(text):
        # Skip whitespace/newlines between arguments
        while pos < len(text) and text[pos] in ' \t\n\r':
            pos += 1
        if pos >= len(text):
            break
        if text[pos] == '[':
            depth = 1
            pos += 1
            while pos < len(text) and depth > 0:
                if text[pos] == '[':
                    depth += 1
                elif text[pos] == ']':
                    depth -= 1
                pos += 1
        elif text[pos] == '{':
            depth = 1
            pos += 1
            while pos < len(text) and depth > 0:
                if text[pos] == '{':
                    depth += 1
                elif text[pos] == '}':
                    depth -= 1
                pos += 1
        else:
            break
    # Eat trailing newline
    if pos < len(text) and text[pos] == '\n':
        pos += 1
    return pos


def strip_command(text, cmd_pattern):
    """Remove all occurrences of a command matching cmd_pattern plus its args."""
    while True:
        m = re.search(cmd_pattern, text)
        if not m:
            break
        pos = eat_args(text, m.end())
        text = text[:m.start()] + text[pos:]
    return text


# ── 0. Remove non-ASCII control characters (ESC bytes etc.) ───────────
text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

# ── 1. Commands that cause tex4ht to loop at \begin{document} ──────────
for cmd in [r'\maketitle', r'\tableofcontents', r'\listoffigures',
            r'\listoftables', r'\frontmatter', r'\mainmatter', r'\backmatter']:
    text = text.replace(cmd, '')

# \printbibliography (with optional arguments)
text = re.sub(r'(?m)^[^%]*\\printbibliography\b[^\n]*', '', text)

# ── 2. Packages irrelevant or dangerous in DVI/HTML mode ───────────────
useless_packages = [
    'luacolor', 'fontspec', 'unicode-math',
    'luatexja-fontspec', 'luatexja',
    'soul', 'pdflscape', 'xucuri',
    'scrlayer-scrpage',
    'crop', 'geometry',
    'plex-sans', 'plex-serif', 'plex-mono',
    'fbb', 'ETbb', 'FiraMono',
    'fourier', 'mathastext', 'libertinus',
    'accessibility', 'endnotes',
]
for pkg in useless_packages:
    text = re.sub(
        rf'(?m)^(?!%)[^\n]*\\usepackage\b[^\n]*\{{{pkg}\}}[^\n]*\n?',
        '', text)

# ── 3. Font setup commands — strip entire multiline block ─────────────
font_cmds = [
    'setmainfont', 'setsansfont', 'setmonofont',
    'setmathfont', 'setmainjfont', 'setsansjfont',
    'setmonojfont', 'newfontfamily', 'newfontface',
    'setkomafont', 'addtokomafont', 'setcapindent',
]
for cmd in font_cmds:
    text = strip_command(text, rf'(?m)^[^%\n]*\\{cmd}\b')

# ── 4. CJK font definitions (\newjfontfamily\cmdname[...]{...}) ──────
# \newjfontfamily takes a \csname then [...]{...} arguments
def strip_newjfontfamily(text):
    pattern = r'(?m)^[^%\n]*\\newjfontfamily\b'
    while True:
        m = re.search(pattern, text)
        if not m:
            break
        pos = m.end()
        # Skip the \csname that follows
        while pos < len(text) and text[pos] in ' \t\n\r':
            pos += 1
        if pos < len(text) and text[pos] == '\\':
            pos += 1
            while pos < len(text) and text[pos].isalpha():
                pos += 1
        pos = eat_args(text, pos)
        text = text[:m.start()] + text[pos:]
    return text

text = strip_newjfontfamily(text)
text = strip_command(text, r'(?m)^[^%\n]*\\ltjsetparameter\b')

# ── 5. Commands referencing removed font families ─────────────────────
# Replace with passthrough stubs instead of deleting (so \ko{text} still works)
text = re.sub(
    r'(?m)^[^%\n]*\\(?:new|renew|Declare\w*)command\{(\\[a-zA-Z]+)\}[^\n]*'
    r'\\(?:koreanfont|japanesefont|chinesefont)\b[^\n]*\n?',
    r'\\newcommand{\1}[1]{##1}\n', text)
# Fix double-hash (from re substitution in LaTeX)
text = text.replace('##1}', '#1}')

# ── 6. KOMA-Script page style commands (irrelevant for HTML) ──────────
# Simple single-line commands
simple_koma = [
    'pagestyle', 'clearpairofpagestyles',
    'chead', 'cfoot', 'ihead', 'ifoot', 'ohead', 'ofoot',
    'lehead', 'lohead', 'rehead', 'rohead',
    'lefoot', 'lofoot', 'refoot', 'rofoot',
    'automark', 'deffootnotemark',
]
for cmd in simple_koma:
    text = strip_command(text, rf'(?m)^[^%\n]*\\{cmd}\b')

# \renewcommand{\chaptermark}[1]{...}  etc.
for cmd in ['chaptermark', 'sectionmark']:
    text = strip_command(text, rf'(?m)^[^%\n]*\\renewcommand\{{\\{cmd}\}}')

# \RedeclareSectionCommand[...]{...} and \DeclareTOCStyleEntry[...]{...}
for cmd in ['RedeclareSectionCommand', 'DeclareTOCStyleEntry']:
    text = strip_command(text, rf'(?m)^[^%\n]*\\{cmd}\b')

# ── 7. \ghostprompt and its callers ────────────────────────────────────
text = re.sub(
    r'\\DeclareRobustCommand\{\\ghostprompt\}.*?(?=\\renewcommand|\\makeatother)',
    '', text, flags=re.DOTALL)
text = re.sub(
    r'\\renewcommand\{\\chapterlinesformat\}[^\n]*\n[^\n]*ghostprompt[^\n]*\n\}',
    '', text)
text = re.sub(
    r'\\renewcommand\{\\sectionlinesformat\}[^\n]*\n[^\n]*ghostprompt[^\n]*\n\}',
    '', text)

# ── 8. \ifdefined\HCode guards ────────────────────────────────────────
text = re.sub(
    r'\\ifdefined\\HCode.*?\\fi',
    '', text, flags=re.DOTALL)

# ── 9. endnotes leftovers ─────────────────────────────────────────────
text = re.sub(r'(?m)^[^%]*\\let\\footnote\\endnote[^\n]*\n?', '', text)
text = re.sub(r'(?m)^[^%]*\\theendnotes[^\n]*\n?', '', text)

# ── 10. \renewenvironment{quote} (uses font commands) ─────────────────
text = re.sub(
    r'\\renewenvironment\{quote\}\{[^}]*\}\{[^}]*\}',
    '', text)

# ── 11. Provide stubs for stripped packages ────────────────────────────
# soul package: \ul, \hl, \so, \st, \caps → passthrough
# \sout → passthrough (used by \cut command)
stubs = r"""
% Stubs for stripped packages (added by preprocess-tex.py)
\providecommand{\ul}[1]{\underline{#1}}
\providecommand{\hl}[1]{#1}
\providecommand{\so}[1]{#1}
\providecommand{\st}[1]{#1}
\providecommand{\caps}[1]{#1}
\providecommand{\sout}[1]{#1}
"""

# Fix biblatex-oscola/verbose-inote \footcite stack overflow with tex4ht.
# verbose-inote's footcite:save does \label{cbx@N} and footcite:note:old
# does \ref{cbx@...} for "(n X)" back-references. tex4ht redefines \label
# and \ref with heavy expansion that recurses inside footnote contexts.
# Fix: inject AFTER \begin{document} so both biblatex and tex4ht have
# fully loaded, then replace \label/\ref with the originals tex4ht saved
# as \:label (\csname :label\endcsname with catcode-11 colon) and \o:ref.
footcite_fix = r"""
% Fix tex4ht + oscola \footcite stack overflow (added by preprocess-tex.py)
\makeatletter
% tex4ht uses catcode-11 colon for internal names like \:label, \o:ref.
\catcode`\:=11
\ifcsname :label\endcsname
  \expandafter\let\expandafter\cbx@origlabel\csname :label\endcsname
  \renewbibmacro*{footcite:save}{%
    \csxdef{cbx@f@\thefield{entrykey}}{\the\value{instcount}}%
    \cbx@origlabel{cbx@\the\value{instcount}}}
\fi
\ifdefined\o:ref
  \let\cbx@origref\o:ref
  \let\cbx@origpageref\o:pageref
  \renewbibmacro*{footcite:note:old}{%
    \ifboolexpr{ test {\ifentrytype{misc}}
                 or test {\ifentrytype{legal}}
                 or test {\ifentrytype{jurisdiction}}}
      {\printfield[title]{labeltitle}\setunit*{\addspace}}
      {\ifnameundef{labelname}%
        {\printfield{label}}%
        {\printnames{labelname}}%
      \ifsingletitle%
        {}%
        {\setunit*{\nametitledelim}%
         \printfield[title]{labeltitle}}%
      \setunit*{\addspace}}%
    \bbx@unsetpostnotedelim%
    \printtext[parens]{%
      \midsentence
      \bibstring{seenote}\addnbspace%
      \cbx@origref{cbx@\csuse{cbx@f@\thefield{entrykey}}}%
      \iftoggle{cbx:pageref}%
        {\ifsamepage{\the\value{instcount}}%
                    {\csuse{cbx@f@\thefield{entrykey}}}%
           {}%
           {\addcomma\space\bibstring{page}\addnbspace%
            \cbx@origpageref{cbx@\csuse{cbx@f@\thefield{entrykey}}}}}
        {}}}
\fi
\catcode`\:=12
% Fix citereset=chapter: KOMA's \AddtoDoHook{heading/begingroup/chapter}
% doesn't fire under tex4ht. Patch \chapter to call \citereset directly.
\ifdefined\chapter
  \let\cbx@origchapter\chapter
  \renewcommand{\chapter}{\citereset\cbx@origchapter}
\fi
\makeatother
"""

# Insert stubs before \begin{document}, footcite fix after it
text = text.replace(r'\begin{document}',
                    stubs + r'\begin{document}' + footcite_fix)

# ── 12. Force \citereset at each \chapter ─────────────────────────────
# biblatex's citereset=chapter hooks into KOMA's \AddtoDoHook which
# tex4ht breaks by redefining the heading machinery. Patch \chapter
# to call \citereset so each chapter gets fresh full citations.
# This is injected after \begin{document} alongside the footcite fix.

# ── 13. Clean up multiple blank lines ─────────────────────────────────
text = re.sub(r'\n{3,}', '\n\n', text)

open(path, 'w', encoding='utf-8').write(text)
print(f"Preprocessed: {path}", file=sys.stderr)
