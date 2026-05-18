import re
from typing import List

HYPHEN_LINEBREAK = re.compile(r"(?<=\w)-\s*\n\s*(?=\w)")  # word-\nword
MULTI_NL = re.compile(r"\n{3,}")
TRAIL_SPACE_BEFORE_NL = re.compile(r"[ \t]+\n")

# --- Heuristics to preserve structure ---

BULLET_OR_ENUM = re.compile(
    r"""^\s*(
        [\-\*\u2022\u25CF\u25E6]      # bullets: -,*,•, etc.
        |\d+[\.\)]                   # 1. or 1)
        |[A-Za-z][\.\)]              # a. or a)
        |[IVXLCDM]+[\.\)]            # Roman numerals I. II)
    )\s+""",
    re.VERBOSE
)

# Common "heading-like" patterns:
# - short lines in ALL CAPS
# - numbered headings: "1 Introduction", "1.2 Scope"
# - Title Case-ish short lines
NUMBERED_HEADING = re.compile(r"^\s*\d+(\.\d+)*\s+.+$")
ALL_CAPS_HEADING = re.compile(r"^\s*[A-Z0-9][A-Z0-9 \-–—,:;()\/]{3,}\s*$")

def is_heading_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False

    # Ends with colon usually introduces a list/subsection
    if s.endswith(":"):
        return True

    # If it's a bullet/list item, treat as structure (not prose)
    if BULLET_OR_ENUM.match(s):
        return True

    # Strong signals
    if ALL_CAPS_HEADING.match(s):
        return True

    # Numbered headings like "1.2 Scope" (but avoid long prose)
    if NUMBERED_HEADING.match(s) and len(s) <= 80:
        return True

    # Short "Title-like" lines: few words, mostly alphabetic, not ending with period
    words = s.split()
    if 1 <= len(words) <= 10 and len(s) <= 80 and not s.endswith("."):
        # if most words look capitalized (Title Case vibe)
        cap_like = sum(w[:1].isupper() for w in words if w and w[0].isalpha())
        alpha_words = sum(1 for w in words if any(ch.isalpha() for ch in w))
        if alpha_words and cap_like / alpha_words >= 0.6:
            return True

    return False

def looks_like_table_or_code(line: str) -> bool:
    s = line.rstrip("\n")
    # Pipes (markdown tables) or many consecutive spaces often signal tabular data
    if "|" in s:
        return True
    if re.search(r"\S\s{3,}\S", s):
        return True
    # code-ish: starts with indentation and has symbols
    if re.match(r"^\s{4,}\S", s):
        return True
    return False

def should_merge(prev_line: str, next_line: str) -> bool:
    """
    Decide whether to merge a newline between prev_line and next_line
    into a space (soft-wrap).
    """
    p = prev_line.strip()
    n = next_line.strip()

    if not p or not n:
        return False

    # Preserve structure markers
    if is_heading_line(p) or is_heading_line(n):
        return False

    if BULLET_OR_ENUM.match(n) or BULLET_OR_ENUM.match(p):
        return False

    if looks_like_table_or_code(p) or looks_like_table_or_code(n):
        return False

    # If previous ends with sentence-ending punctuation, keep newline (often paragraph-like)
    if re.search(r"[.!?]\s*$", p):
        return False

    # If next starts like a new section label "Note:", "Definition:", keep newline
    if re.match(r"^[A-Z][A-Za-z0-9 _-]{0,25}:\s+", n):
        return False

    # Otherwise, likely wrapped prose -> merge
    return True

def merge_soft_wraps_preserving_structure(block: str) -> str:
    """
    Merge soft-wrapped lines inside a block, but preserve headings/list lines.
    """
    lines = [ln.rstrip() for ln in block.split("\n")]
    out: List[str] = []

    i = 0
    while i < len(lines):
        cur = lines[i].strip()
        if not cur:
            i += 1
            continue

        # Always keep heading/list/table/code lines as standalone lines
        if is_heading_line(cur) or BULLET_OR_ENUM.match(cur) or looks_like_table_or_code(cur):
            out.append(re.sub(r"[ \t]+", " ", cur).strip())
            i += 1
            continue

        # Otherwise, try to merge following lines as long as they look like prose wraps
        buf = cur
        j = i + 1
        while j < len(lines):
            nxt_raw = lines[j]
            nxt = nxt_raw.strip()

            if not nxt:
                break

            if should_merge(buf, nxt):
                buf = f"{buf} {nxt}"
                j += 1
            else:
                break

        buf = re.sub(r"[ \t]+", " ", buf).strip()
        out.append(buf)
        i = j

    return "\n".join(out)

def clean_pdf_text_preserve_structure(text: str) -> str:
    """
    Clean PDF text while preserving structural boundaries like headings,
    subheadings, lists, and paragraph breaks.

    - Keeps blank lines as block separators.
    - Fixes hyphenated line breaks.
    - Merges only soft-wrapped lines in prose paragraphs.
    - Preserves headings/list items as separate lines.
    """
    if not text:
        return ""

    # Normalize Windows newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove trailing spaces before newline
    text = TRAIL_SPACE_BEFORE_NL.sub("\n", text)

    # Fix hyphenated line breaks: develop-\nment -> development
    text = HYPHEN_LINEBREAK.sub("", text)

    # Reduce 3+ newlines to exactly 2 (keep paragraph boundaries)
    text = MULTI_NL.sub("\n\n", text)

    # Split into "blocks" separated by blank lines
    raw_blocks = [b for b in text.split("\n\n") if b.strip()]
    cleaned_blocks: List[str] = []

    for b in raw_blocks:
        cleaned = merge_soft_wraps_preserving_structure(b)
        cleaned_blocks.append(cleaned.strip())

    return "\n\n".join(cleaned_blocks)