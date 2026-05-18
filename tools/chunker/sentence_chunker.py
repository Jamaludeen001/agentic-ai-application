from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple, Callable
import re

from transformers import AutoTokenizer

import sys
import os

sys.path.append(os.path.abspath(".."))

# -----------------------------
# 0) Tokenizer init (BGE-small)
# -----------------------------
TOKENIZER_PATH = "/dbfs/FileStore/tables/tokenizers/bge-small-en-v1.5"
hf_tokenizer = AutoTokenizer.from_pretrained(
    TOKENIZER_PATH,
    local_files_only=True,
    trust_remote_code=True
)


# ---------------------------------------------------
# 1) Fast token utilities (optional caching enabled)
# ---------------------------------------------------
# NOTE: For very large corpora, LRU caches can grow memory.
# You can reduce maxsize or disable caches by not using these helpers.

@lru_cache(maxsize=200_000)
def tok_ids(text: str) -> Tuple[int, ...]:
    """Token IDs for raw text (no special tokens). Cached for speed."""
    return tuple(hf_tokenizer.encode(text, add_special_tokens=False))

@lru_cache(maxsize=200_000)
def tok_len(text: str) -> int:
    """Token length of raw text (no special tokens). Cached for speed."""
    return len(tok_ids(text))


def decode(ids: List[int] | Tuple[int, ...]) -> str:
    """Decode token IDs back to text."""
    return hf_tokenizer.decode(list(ids), skip_special_tokens=True).strip()


def tail_cut(text: str, overlap_tokens: int) -> str:
    """
    Token-tail cut: last `overlap_tokens` tokens from `text`.
    May start mid-sentence (used only as fallback).
    """
    if overlap_tokens <= 0:
        return ""
    ids = tok_ids(text)
    if not ids:
        return ""
    tail_ids = ids[-overlap_tokens:]
    return decode(tail_ids)


def split_by_tokens(text: str, max_tokens: int) -> List[str]:
    """
    Split a long text into multiple pieces, each <= max_tokens tokens.
    Used when a SINGLE sentence exceeds max_tokens.
    """
    if max_tokens <= 0:
        return []
    ids = tok_ids(text)
    out = []
    for i in range(0, len(ids), max_tokens):
        part = decode(ids[i:i + max_tokens])
        if part:
            out.append(part)
    return out


# ---------------------------------------------------
# 2) Sentence splitting helper (no nltk dependency)
# ---------------------------------------------------

# ---------------------------------------------------
# 3) Overlap builder (HYBRID)
#    - sentence-safe overlap first
#    - if overlap too small, tail-cut fallback from last sentence
#    - guardrails to avoid overlapping whole chunk
# ---------------------------------------------------
def build_overlap(
    cur_sents: List[str],
    cur_sent_lens: List[int],
    chunk_token_len: int,
    overlap_tokens: int,
    min_overlap_tokens: int = 20,
    hybrid_tail_fallback: bool = True,
) -> str:
    """
    Returns overlap text to seed the next chunk.
    Strategy:
      1) If chunk too small -> no overlap
      2) Try sentence-safe overlap (whole sentences from end)
      3) If overlap too small and hybrid enabled -> tail-cut fallback from last sentence
      4) If overlap equals whole chunk -> drop overlap
    """
    # Guardrail: tiny chunk -> no overlap
    if chunk_token_len < min_overlap_tokens:
        return ""

    # Sentence-safe overlap (whole sentences from end)
    ov_sents = []
    ov_t = 0
    for sent, st in zip(reversed(cur_sents), reversed(cur_sent_lens)):
        if ov_t + st > overlap_tokens:
            break
        ov_sents.append(sent)
        ov_t += st
    ov_sents.reverse()

    if ov_t >= min_overlap_tokens or not hybrid_tail_fallback:
        overlap_text = " ".join(ov_sents).strip()
        # Guardrail: don't overlap entire chunk
        if tok_len(overlap_text) >= chunk_token_len:
            return ""
        return overlap_text

    # Hybrid fallback: add token-tail from last sentence to reach minimum overlap
    # needed = how many tokens we still want to reach min_overlap_tokens
    need = max(min_overlap_tokens - ov_t, 0)
    need = min(need, overlap_tokens)  # never exceed overlap_tokens
    tail = tail_cut(cur_sents[-1], need)

    overlap_text = (" ".join(ov_sents) + " " + tail).strip()

    # Guardrail: don't overlap entire chunk
    if tok_len(overlap_text) >= chunk_token_len:
        return ""
    return overlap_text


# ---------------------------------------------------
# 4) Main chunker (flush-based, optimized)
# ---------------------------------------------------
def chunk_sentences(
    s: List[str],                # list of sentences [s1, s2, ...]
    target_tokens: int = 280,     # soft flush goal
    max_tokens: int = 380,        # hard cap
    overlap_tokens: int = 60,     # overlap budget (hybrid)
    min_overlap_tokens: int = 20  # skip overlap for tiny chunks
) -> List[str]:
    """
    Optimized sentence-based chunking for RAG (BGE tokenizer).
    - Packs whole sentences until max_tokens would be exceeded.
    - Flushes when reaching target_tokens (soft goal).
    - Overlap is hybrid: whole-sentence overlap first, token-tail fallback if needed.
    - If a single sentence > max_tokens, splits it by tokens.
    """

    # sanitize input
    s = [x.strip() for x in s if x and x.strip()]
    if not s:
        return []

    # Precompute sentence token lengths ONCE (major speed win)
    s_lens = [tok_len(x) for x in s]

    chunks: List[str] = []
    cur_sents: List[str] = []
    cur_lens: List[int] = []
    cur_tok: int = 0

    def flush():
        nonlocal cur_sents, cur_lens, cur_tok

        if not cur_sents:
            return

        chunk_text = " ".join(cur_sents).strip()
        chunk_len = cur_tok  # already tracked as token sum
        chunks.append(chunk_text)

        ov_text = build_overlap(
            cur_sents=cur_sents,
            cur_sent_lens=cur_lens,
            chunk_token_len=chunk_len,
            overlap_tokens=overlap_tokens,
            min_overlap_tokens=min_overlap_tokens,
            hybrid_tail_fallback=True
        )

        if ov_text:
            # Start new buffer with overlap as one "pseudo-sentence"
            cur_sents = [ov_text]
            ov_len = tok_len(ov_text)
            cur_lens = [ov_len]
            cur_tok = ov_len
        else:
            cur_sents, cur_lens, cur_tok = [], [], 0

    i = 0
    while i < len(s):
        sent = s[i]
        st = s_lens[i]

        # Case A: single sentence too long -> split by tokens
        if st > max_tokens:
            flush()
            parts = split_by_tokens(sent, max_tokens)
            chunks.extend(parts)

            # Optional: seed next buffer with overlap from last part
            if parts:
                ov = tail_cut(parts[-1], overlap_tokens)
                if ov and tok_len(ov) >= min_overlap_tokens:
                    ov_len = tok_len(ov)
                    cur_sents, cur_lens, cur_tok = [ov], [ov_len], ov_len
                else:
                    cur_sents, cur_lens, cur_tok = [], [], 0

            i += 1
            continue

        # Case B: sentence doesn't fit -> flush and retry same sentence
        if cur_tok + st > max_tokens:
            flush()
            continue

        # Case C: add sentence
        cur_sents.append(sent)
        cur_lens.append(st)
        cur_tok += st
        i += 1

        # Soft flush once target is reached
        if cur_tok >= target_tokens:
            flush()

    flush()
    return chunks


# ---------------------------------------------------
# 5) Convenience wrapper: chunk raw page text
# ---------------------------------------------------


# ---------------------------------------------------
# 6) Quick test / demo
# ---------------------------------------------------
