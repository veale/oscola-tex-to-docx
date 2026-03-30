#!/usr/bin/env bash
# Install dependencies for oscola2docx

set -euo pipefail

echo "Checking and installing dependencies for oscola2docx..."
echo ""

# Detect OS and package manager
if [[ "$OSTYPE" == "darwin"* ]]; then
    PKG_MGR="brew"
elif command -v apt-get &>/dev/null; then
    PKG_MGR="apt"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
else
    echo "Unsupported package manager. Please install manually:"
    echo "  - TeX Live (with make4ht, biber, biblatex)"
    echo "  - biblatex-oscola (tlmgr install biblatex-oscola)"
    echo "  - Python 3 with beautifulsoup4"
    echo "  - Pandoc"
    exit 1
fi

echo "Detected package manager: $PKG_MGR"
echo ""

# --- TeX Live ---
if command -v make4ht &>/dev/null && command -v biber &>/dev/null; then
    echo "[OK] TeX Live (make4ht, biber) already installed"
else
    echo "Installing TeX Live..."
    case "$PKG_MGR" in
        brew)
            echo "  Install MacTeX from https://tug.org/mactex/ or run:"
            echo "  brew install --cask mactex"
            echo ""
            echo "  For a smaller install: brew install --cask basictex"
            echo "  Then: sudo tlmgr install make4ht tex4ht biber biblatex"
            ;;
        apt)
            echo "  sudo apt-get install texlive-full"
            echo "  (or for a smaller install: sudo apt-get install texlive-latex-extra texlive-bibtex-extra biber texlive-luatex)"
            ;;
        dnf)
            echo "  sudo dnf install texlive-scheme-full"
            ;;
    esac
    echo ""
fi

# --- biblatex-oscola ---
if kpsewhich oscola.bbx &>/dev/null; then
    echo "[OK] biblatex-oscola already installed"
else
    echo "Installing biblatex-oscola..."
    echo "  sudo tlmgr install biblatex-oscola"
    if command -v tlmgr &>/dev/null; then
        sudo tlmgr install biblatex-oscola || echo "  (tlmgr install failed — try manually)"
    fi
fi

# --- Pandoc ---
if command -v pandoc &>/dev/null; then
    echo "[OK] Pandoc already installed ($(pandoc --version | head -1))"
else
    echo "Installing Pandoc..."
    case "$PKG_MGR" in
        brew) brew install pandoc ;;
        apt) sudo apt-get install -y pandoc ;;
        dnf) sudo dnf install -y pandoc ;;
    esac
fi

# --- Python 3 ---
if command -v python3 &>/dev/null; then
    echo "[OK] Python 3 already installed ($(python3 --version))"
else
    echo "Installing Python 3..."
    case "$PKG_MGR" in
        brew) brew install python ;;
        apt) sudo apt-get install -y python3 python3-pip ;;
        dnf) sudo dnf install -y python3 python3-pip ;;
    esac
fi

# --- beautifulsoup4 (optional, for --no-domfilter fallback) ---
if python3 -c "import bs4" 2>/dev/null; then
    echo "[OK] beautifulsoup4 already installed"
else
    echo "Installing beautifulsoup4 (optional, for --no-domfilter fallback)..."
    pip3 install beautifulsoup4 || python3 -m pip install beautifulsoup4 || \
        echo "  Could not install beautifulsoup4 — only needed for --no-domfilter mode"
fi

echo ""
echo "Dependency check complete."
