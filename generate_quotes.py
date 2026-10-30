#!/usr/bin/env python3
"""Download Portuguese Project Gutenberg books and extract short sentences."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path


API_URL = "https://gutendex.com/books/"
BOOK_LIMIT = 30
QUOTE_TARGET = 200
OUTPUT_FILE = Path(__file__).with_name("quotes.json")
SCRIPT_FILE = Path(__file__).with_name("quotes.js")
USER_AGENT = "Mozilla/5.0 (compatible; GutendexQuotesCollector/1.0)"

NONLITERARY_TITLE = re.compile(
    r"\b(dicion[aá]rio|bibliografia|emigra[cç][aã]o|coloniza[cç][aã]o|"
    r"revolu[cç][aã]o|relat[oó]rio|manual|gram[aá]tica)\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿ]+)*")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
REPEATED_LETTER_RE = re.compile(r"([A-Za-zÀ-ÖØ-öø-ÿ])\1{2,}")
SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])[\"»”’')\]]*\s+|(?<=[.!?])[\"»”’')\]]*[—–-]+(?=[A-ZÀ-ÖØ-Þ])"
)
HEADING_START_RE = re.compile(
    r"^(cap[ií]tulo|livro|parte|canto|acto|ato|cena|personagens?)\b",
    re.IGNORECASE,
)
FINITE_VERBS = {
    "acho", "anda", "andava", "acontece", "acordou", "acredito", "acabou",
    "aparece", "basta", "caiu", "chove", "começou", "conheço", "conhecia",
    "contou", "dá", "dava", "deixou", "digo", "disse", "diz", "dizia",
    "é", "era", "eram", "está", "estava", "estavam", "esteve", "estive",
    "estou", "existe", "faz", "fazia", "fez", "fica", "ficou", "fiz", "foi",
    "foram", "fui", "há", "havia", "houve", "ia", "iam", "iria", "lembro",
    "manda", "mora", "nasceu", "parece", "parecia", "passou", "pode", "pôde",
    "podia", "quer", "sabia", "sabe", "são", "sei", "será", "somos", "sou",
    "tem", "têm", "tinha", "tinham", "tive", "teve", "tiveram", "traz", "trouxe",
    "vai", "veio", "vieram", "viu", "abria", "dizia", "morria", "queria",
    "seria", "sentia", "vivia",
}
FINITE_SUFFIX_RE = re.compile(
    r"(?:ou|ava|avam|iam|aram|eram|iram|iu|aste|este|iste|asse|esse|isse|"
    r"aremos|eremos|iremos|ávamos|íamos)$",
    re.IGNORECASE,
)
PARENTHESIS_RE = re.compile(r"[()]|\[[^]]*\]")
ROMAN_MARKER_RE = re.compile(r"\b[IVXLCDM]{1,8}\b")
METADATA_RE = re.compile(
    r"\b(pag\.?|p[aá]gina|tomo|volume|vol\.?|edi[cç][aã]o|tipografia|typ\.?|"
    r"produced|copyright|impress[aã]o|livraria|classicos)\b",
    re.IGNORECASE,
)


def get_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read()


def author_name(authors: list[dict]) -> str:
    if not authors:
        return "Autor desconhecido"
    names = []
    for author in authors:
        name = author.get("name", "Autor desconhecido")
        if ", " in name:
            surname, given_names = name.split(", ", 1)
            name = f"{given_names} {surname}"
        names.append(name)
    return "; ".join(names)


def text_url(book: dict) -> str | None:
    formats = book.get("formats", {})
    plain_text = [
        (mime, url)
        for mime, url in formats.items()
        if "text/plain" in mime.lower() and url.lower().endswith((".txt", ".txt.utf-8"))
    ]
    if not plain_text:
        return None
    plain_text.sort(key=lambda item: ("utf-8" not in item[0].lower(), item[1]))
    return plain_text[0][1]


def project_text(raw_text: str) -> str:
    start = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", raw_text, re.I)
    if start:
        raw_text = raw_text[start.end():]
    end = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", raw_text, re.I)
    if end:
        raw_text = raw_text[:end.start()]
    first_chapter = re.search(
        r"^\s*(?:cap[ií]tulo|chapter|canto|livro)\s+(?:[ivxlcdm]+|\d+)\b.*$",
        raw_text,
        re.IGNORECASE | re.MULTILINE,
    )
    if first_chapter:
        raw_text = raw_text[first_chapter.start():]
    return raw_text


def clean_candidate(candidate: str) -> str:
    candidate = CONTROL_CHAR_RE.sub("", candidate)
    candidate = REPEATED_LETTER_RE.sub(r"\1", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()

    candidate = re.sub(r"^[—–-]+\s*", "", candidate)
    candidate = candidate.strip(" \t\r\n\"'“”‘’«»")

    for opening, closing in (("\"", "\""), ("“", "”"), ("‘", "’"), ("«", "»")):
        if opening == closing:
            if candidate.count(opening) % 2:
                candidate = candidate.replace(opening, "")
        else:
            while candidate.count(opening) > candidate.count(closing):
                candidate = candidate.replace(opening, "", 1)
            while candidate.count(closing) > candidate.count(opening):
                candidate = candidate[::-1].replace(closing, "", 1)[::-1]

    candidate = re.sub(r"\s+", " ", candidate).strip()
    candidate = re.sub(r"^[—–-]+\s*", "— ", candidate)
    return candidate


def extract_quotes(raw_text: str, author: str, title: str) -> list[dict[str, str]]:
    body = project_text(raw_text)
    quotes = []
    seen = set()

    for paragraph in re.split(r"\n\s*\n+", body):
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
        if not paragraph:
            continue
        for candidate in SENTENCE_SPLIT_RE.split(paragraph):
            candidate = clean_candidate(candidate)
            candidate = re.sub(r"[*_]", "", candidate)
            if not candidate or not re.search(r"[.!]$", candidate):
                continue
            if "..." in candidate or "…" in candidate or HEADING_START_RE.match(candidate):
                continue
            if re.search(r"[!?]{2,}|\.{2,}|[:\d]", candidate):
                continue
            if (
                PARENTHESIS_RE.search(candidate)
                or ROMAN_MARKER_RE.search(candidate)
                or METADATA_RE.search(candidate)
                or re.search(r"\b[A-ZÀ-ÖØ-Þ]\.\s*$", candidate)
                or re.search(r"\b[A-ZÀ-ÖØ-Þ]{2,}\b", candidate)
            ):
                continue

            words = WORD_RE.findall(candidate)
            if not 2 <= len(words) <= 5:
                continue
            first_letter = next((char for char in candidate if char.isalpha()), "")
            if not first_letter or not first_letter.isupper():
                continue
            if not any(
                word.casefold() in FINITE_VERBS or FINITE_SUFFIX_RE.search(word)
                for word in words
            ):
                continue

            key = re.sub(r"\W+", " ", candidate.casefold()).strip()
            if key in seen:
                continue
            seen.add(key)
            quotes.append({"texto": candidate, "autor": author, "obra": title})
    return quotes


def fetch_books() -> list[tuple[str, str, list[dict[str, str]]]]:
    books = []
    seen_ids = set()
    next_url = API_URL + "?" + urllib.parse.urlencode({"languages": "pt", "sort": "popular"})

    while next_url and len(books) < BOOK_LIMIT:
        page = json.loads(get_url(next_url).decode("utf-8"))
        for book in page.get("results", []):
            if len(books) >= BOOK_LIMIT:
                break
            if book["id"] in seen_ids:
                continue
            seen_ids.add(book["id"])
            title = book.get("title", "").strip()
            url = text_url(book)
            if not title or not url or not book.get("authors") or NONLITERARY_TITLE.search(title):
                continue
            try:
                raw_text = get_url(url).decode("utf-8-sig", errors="replace")
            except (urllib.error.URLError, TimeoutError) as error:
                print(f"Ignorando {title!r}: falha no download ({error}).")
                continue
            quotes = extract_quotes(raw_text, author_name(book.get("authors", [])), title)
            books.append((title, author_name(book.get("authors", [])), quotes))
            print(f"[{len(books):02d}/{BOOK_LIMIT}] {title}: {len(quotes)} candidatas")
            time.sleep(0.15)
        next_url = page.get("next")
        time.sleep(0.15)

    return books


def distribute_quotes(books: list[tuple[str, str, list[dict[str, str]]]]) -> list[dict[str, str]]:
    queues = deque(deque(quotes) for _, _, quotes in books if quotes)
    selected = []
    seen = set()

    while queues and len(selected) < QUOTE_TARGET:
        queue = queues.popleft()
        quote = queue.popleft()
        key = re.sub(r"\W+", " ", quote["texto"].casefold()).strip()
        if key not in seen:
            seen.add(key)
            selected.append(quote)
        if queue:
            queues.append(queue)

    return selected


def main() -> None:
    books = fetch_books()
    if len(books) < BOOK_LIMIT:
        print(f"Aviso: foram baixadas {len(books)} obras, em vez de {BOOK_LIMIT}.")

    quotes = distribute_quotes(books)
    if len(quotes) < 150:
        raise SystemExit(f"A coleta encontrou apenas {len(quotes)} citações; mínimo exigido: 150.")

    OUTPUT_FILE.write_text(
        json.dumps(quotes, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    SCRIPT_FILE.write_text(
        "window.CITACOES = " + OUTPUT_FILE.read_text(encoding="utf-8").rstrip() + ";\n",
        encoding="utf-8",
    )
    print(f"\nSalvas {len(quotes)} citações de {len(books)} obras em {OUTPUT_FILE} e {SCRIPT_FILE}.")


if __name__ == "__main__":
    main()
