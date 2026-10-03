"""Text normalization helpers, ported from textacy.preprocessing (textacy doesn't build on modern python)."""
import sys
import unicodedata

import regex as re

RE_HYPHENATED_WORD = re.compile(r"(\w{2,}(?<!\d))\-\s+((?!\d)\w{2,})", flags=re.UNICODE | re.IGNORECASE)
RE_LINEBREAK = re.compile(r"(\r\n|[\n\v])+")
RE_NONBREAKING_SPACE = re.compile(r"[^\S\n\v]+")
RE_BRACKETS_CURLY = re.compile(r"\{[^{}]*?\}")
RE_BRACKETS_ROUND = re.compile(r"\([^()]*?\)")
RE_BRACKETS_SQUARE = re.compile(r"\[[^\[\]]*?\]")

QUOTE_TRANSLATION_TABLE = str.maketrans({
    ord(c): "'" for c in "‘’‚‛‹›❛❜`´"
} | {
    ord(c): '"' for c in "“”„‟«»❝❞〝〞〟＂"
})

PUNCT_TRANSLATION_TABLE = dict.fromkeys(
    (i for i in range(sys.maxunicode) if unicodedata.category(chr(i)).startswith("P")),
    " ",
)


def hyphenated_words(text: str) -> str:
    return RE_HYPHENATED_WORD.sub(r"\1\2", text)


def quotation_marks(text: str) -> str:
    return text.translate(QUOTE_TRANSLATION_TABLE)


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def whitespace(text: str) -> str:
    return RE_NONBREAKING_SPACE.sub(" ", RE_LINEBREAK.sub(r"\n", text)).strip()


def accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def brackets(text: str) -> str:
    for pattern in (RE_BRACKETS_CURLY, RE_BRACKETS_SQUARE, RE_BRACKETS_ROUND):
        text = pattern.sub("", text)
    return text


def punctuation(text: str) -> str:
    return text.translate(PUNCT_TRANSLATION_TABLE)
