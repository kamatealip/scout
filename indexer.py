from collections import Counter
from html.parser import HTMLParser
import json
import os
import re
import sqlite3

DATABASE_FILE = "scout.db"
LEGACY_INDEX_FILE = "index.json"
LEGACY_WORD_COUNT_FILE = "word_counts.json"
LEGACY_CLICK_COUNT_FILE = "click_counts.json"
DEFAULT_DOCS_DIR = "docs"
WORD_REGEX = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
INDEX_CACHE: dict[str, dict[str, int]] | None = None
CLICK_COUNT_CACHE: dict[str, int] | None = None
DOC_TEXT_CACHE: dict[str, str] = {}


class MyHTMLParser(HTMLParser):
    TOKEN_REGEX = re.compile(
        r"(?P<WORD>[A-Za-z]+(?:'[A-Za-z]+)?)|"
        r"(?P<NUMBER>\d+(?:\.\d+)?)|"
        r"(?P<PUNCT>[.,!?;:()\"-])"
    )
    CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
    WHITESPACE = re.compile(r"\s+")

    def __init__(self):
        super().__init__()
        self.word_counts = Counter()

    def clean_data(self, data: str) -> str:
        cleaned = self.CONTROL_CHARS.sub(" ", data)
        cleaned = self.WHITESPACE.sub(" ", cleaned).strip()
        return cleaned

    def lex(self, text: str) -> list[tuple[str, str]]:
        return [
            (match.lastgroup, match.group())
            for match in self.TOKEN_REGEX.finditer(text)
        ]

    def handle_data(self, data):
        cleaned = self.clean_data(data)
        if cleaned:
            tokens = self.lex(cleaned)
            for token_type, token_value in tokens:
                if token_type == "WORD":
                    self.word_counts[token_value.lower()] += 1


class PlainTextHTMLParser(HTMLParser):
    CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
    WHITESPACE = re.compile(r"\s+")

    def __init__(self):
        super().__init__()
        self.parts = []
        self.main_parts = []
        self._skip_depth = 0
        self._main_depth = 0

    @staticmethod
    def _attrs_to_dict(attrs):
        return {key: value for key, value in attrs if key}

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return

        attr_map = self._attrs_to_dict(attrs)
        class_names = set((attr_map.get("class") or "").split())
        is_main_container = attr_map.get("role") == "main" or "body" in class_names
        if is_main_container:
            self._main_depth += 1
        elif self._main_depth > 0:
            self._main_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if self._main_depth > 0:
            self._main_depth -= 1

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        cleaned = self.CONTROL_CHARS.sub(" ", data)
        cleaned = self.WHITESPACE.sub(" ", cleaned).strip()
        if cleaned:
            self.parts.append(cleaned)
            if self._main_depth > 0:
                self.main_parts.append(cleaned)

    def text(self) -> str:
        if self.main_parts:
            return " ".join(self.main_parts)
        return " ".join(self.parts)


def tokenize_words(text: str) -> list[str]:
    return [match.group().lower() for match in WORD_REGEX.finditer(text)]


def process_html_file(file_path: str) -> dict[str, int]:
    parser = MyHTMLParser()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
        parser.feed(source_file.read())
    parser.close()
    return dict(parser.word_counts)


def get_db_connection(database_file: str | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(database_file or DATABASE_FILE)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
            file_key TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS word_counts (
            file_key TEXT NOT NULL,
            term TEXT NOT NULL,
            count INTEGER NOT NULL CHECK (count > 0),
            PRIMARY KEY (file_key, term),
            FOREIGN KEY (file_key) REFERENCES documents(file_key) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS click_counts (
            doc_path TEXT PRIMARY KEY,
            count INTEGER NOT NULL CHECK (count >= 0)
        );

        CREATE INDEX IF NOT EXISTS idx_word_counts_term
        ON word_counts (term);
        """
    )


def normalize_term_counts(term_counts: dict[str, int]) -> dict[str, int]:
    normalized_counts: dict[str, int] = {}
    for term, count in term_counts.items():
        normalized_count = max(0, int(count))
        if normalized_count > 0:
            normalized_term = str(term).lower()
            normalized_counts[normalized_term] = (
                normalized_counts.get(normalized_term, 0) + normalized_count
            )
    return normalized_counts


def normalize_index_data(
    counts_by_file: dict[str, dict[str, int]]
) -> dict[str, dict[str, int]]:
    normalized_counts_by_file: dict[str, dict[str, int]] = {}
    for file_key, term_counts in counts_by_file.items():
        normalized_counts_by_file[str(file_key)] = normalize_term_counts(term_counts)
    return normalized_counts_by_file


def save_index_data(
    counts_by_file: dict[str, dict[str, int]],
    database_file: str | None = None,
) -> dict[str, dict[str, int]]:
    global INDEX_CACHE, DOC_TEXT_CACHE
    normalized_counts_by_file = normalize_index_data(counts_by_file)

    with get_db_connection(database_file) as connection:
        ensure_database(connection)
        connection.execute("DELETE FROM word_counts")
        connection.execute("DELETE FROM documents")
        connection.executemany(
            "INSERT INTO documents (file_key) VALUES (?)",
            [(file_key,) for file_key in normalized_counts_by_file],
        )
        word_count_rows = [
            (file_key, term, count)
            for file_key, term_counts in normalized_counts_by_file.items()
            for term, count in term_counts.items()
        ]
        if word_count_rows:
            connection.executemany(
                """
                INSERT INTO word_counts (file_key, term, count)
                VALUES (?, ?, ?)
                """,
                word_count_rows,
            )

    INDEX_CACHE = normalized_counts_by_file
    DOC_TEXT_CACHE = {}
    return INDEX_CACHE


def index_file(
    file_path: str, output_file: str = DATABASE_FILE
) -> dict[str, dict[str, int]]:
    counts_by_file: dict[str, dict[str, int]] = {}
    for dirpath, _, filenames in os.walk(file_path):
        for filename in filenames:
            if not filename.endswith((".html", ".xhtl", ".xhtml")):
                continue
            absolute_file_path = os.path.join(dirpath, filename)
            file_key = f"{dirpath}/{filename}"
            print("Working with {}".format(absolute_file_path))
            counts_by_file[file_key] = process_html_file(absolute_file_path)

    save_index_data(counts_by_file, database_file=output_file)
    print("Saved word counts to {}".format(output_file))
    return counts_by_file


def load_index_data_from_database(
    database_file: str | None = None,
) -> dict[str, dict[str, int]] | None:
    target_database_file = database_file or DATABASE_FILE
    if not os.path.exists(target_database_file):
        return None

    with get_db_connection(target_database_file) as connection:
        ensure_database(connection)
        document_rows = connection.execute(
            "SELECT file_key FROM documents ORDER BY file_key"
        ).fetchall()
        if not document_rows:
            return None

        counts_by_file = {file_key: {} for (file_key,) in document_rows}
        for file_key, term, count in connection.execute(
            """
            SELECT file_key, term, count
            FROM word_counts
            ORDER BY file_key, term
            """
        ):
            counts_by_file[file_key][term] = count

    return counts_by_file


def load_legacy_index_data() -> dict[str, dict[str, int]] | None:
    for candidate in (LEGACY_WORD_COUNT_FILE, LEGACY_INDEX_FILE):
        if not os.path.exists(candidate):
            continue
        with open(candidate, "r", encoding="utf-8") as source_file:
            legacy_counts_by_file = json.load(source_file)
        return save_index_data(legacy_counts_by_file)

    return None


def load_index_data() -> dict[str, dict[str, int]]:
    global INDEX_CACHE
    if INDEX_CACHE is not None:
        return INDEX_CACHE

    database_counts_by_file = load_index_data_from_database()
    if database_counts_by_file is not None:
        INDEX_CACHE = database_counts_by_file
        return INDEX_CACHE

    legacy_counts_by_file = load_legacy_index_data()
    if legacy_counts_by_file is not None:
        INDEX_CACHE = legacy_counts_by_file
        return INDEX_CACHE

    if os.path.isdir(DEFAULT_DOCS_DIR):
        INDEX_CACHE = index_file(DEFAULT_DOCS_DIR, output_file=DATABASE_FILE)
        return INDEX_CACHE

    raise FileNotFoundError(
        "No search index found. Run: python main.py INDEX <folder path>."
    )


def load_click_counts_from_database(
    database_file: str | None = None,
) -> dict[str, int] | None:
    target_database_file = database_file or DATABASE_FILE
    if not os.path.exists(target_database_file):
        return None

    with get_db_connection(target_database_file) as connection:
        ensure_database(connection)
        return {
            str(doc_path): max(0, int(count))
            for doc_path, count in connection.execute(
                "SELECT doc_path, count FROM click_counts ORDER BY doc_path"
            )
        }


def load_legacy_click_counts() -> dict[str, int] | None:
    if not os.path.exists(LEGACY_CLICK_COUNT_FILE):
        return None

    with open(LEGACY_CLICK_COUNT_FILE, "r", encoding="utf-8") as source_file:
        raw_click_counts = json.load(source_file)

    return save_click_counts(raw_click_counts)


def load_click_counts() -> dict[str, int]:
    global CLICK_COUNT_CACHE
    if CLICK_COUNT_CACHE is not None:
        return CLICK_COUNT_CACHE

    database_click_counts = load_click_counts_from_database()
    if database_click_counts:
        CLICK_COUNT_CACHE = database_click_counts
        return CLICK_COUNT_CACHE

    legacy_click_counts = load_legacy_click_counts()
    if legacy_click_counts is not None:
        CLICK_COUNT_CACHE = legacy_click_counts
        return CLICK_COUNT_CACHE

    CLICK_COUNT_CACHE = database_click_counts or {}
    return CLICK_COUNT_CACHE


def save_click_counts(click_counts: dict[str, int]) -> dict[str, int]:
    global CLICK_COUNT_CACHE
    normalized_counts: dict[str, int] = {}
    for doc_path, count in click_counts.items():
        normalized_count = max(0, int(count))
        if normalized_count > 0:
            normalized_counts[str(doc_path)] = normalized_count

    with get_db_connection() as connection:
        ensure_database(connection)
        connection.execute("DELETE FROM click_counts")
        if normalized_counts:
            connection.executemany(
                """
                INSERT INTO click_counts (doc_path, count)
                VALUES (?, ?)
                """,
                sorted(normalized_counts.items()),
            )

    CLICK_COUNT_CACHE = normalized_counts
    return CLICK_COUNT_CACHE


def get_click_count(doc_path: str) -> int:
    return load_click_counts().get(doc_path, 0)


def increment_click_count(doc_path: str) -> int:
    global CLICK_COUNT_CACHE
    normalized_doc_path = str(doc_path)

    with get_db_connection() as connection:
        ensure_database(connection)
        connection.execute(
            """
            INSERT INTO click_counts (doc_path, count)
            VALUES (?, 1)
            ON CONFLICT(doc_path) DO UPDATE SET count = count + 1
            """,
            (normalized_doc_path,),
        )
        updated_count = connection.execute(
            "SELECT count FROM click_counts WHERE doc_path = ?",
            (normalized_doc_path,),
        ).fetchone()[0]

    if CLICK_COUNT_CACHE is not None:
        CLICK_COUNT_CACHE[normalized_doc_path] = updated_count
    return updated_count


def docs_relative_path(file_key: str) -> str | None:
    normalized = file_key.replace("\\", "/")
    docs_root = os.path.abspath(DEFAULT_DOCS_DIR)
    docs_dir_name = os.path.basename(docs_root.rstrip("/")) or "docs"
    docs_prefix = f"{docs_dir_name}/"

    absolute_key = os.path.abspath(file_key)
    try:
        if os.path.commonpath([docs_root, absolute_key]) == docs_root:
            return os.path.relpath(absolute_key, docs_root).replace(os.sep, "/")
    except ValueError:
        pass

    if normalized.startswith(docs_prefix):
        return normalized[len(docs_prefix):]

    marker = f"/{docs_dir_name}/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]

    if normalized.endswith((".html", ".xhtml", ".xhtl")) and not normalized.startswith("/"):
        return normalized.lstrip("./")

    return None


def resolve_doc_path(doc_path: str) -> str:
    docs_root = os.path.abspath(DEFAULT_DOCS_DIR)
    normalized = os.path.normpath(doc_path).replace("\\", "/")
    if normalized in (".", ""):
        normalized = "index.html"

    if normalized == ".." or normalized.startswith("../"):
        raise FileNotFoundError(normalized)

    absolute_file_path = os.path.abspath(os.path.join(docs_root, normalized))
    try:
        if os.path.commonpath([docs_root, absolute_file_path]) != docs_root:
            raise FileNotFoundError(normalized)
    except ValueError as exc:
        raise FileNotFoundError(normalized) from exc

    if not os.path.isfile(absolute_file_path):
        raise FileNotFoundError(normalized)

    return normalized


def extract_plain_text_from_html(file_path: str) -> str:
    parser = PlainTextHTMLParser()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
        parser.feed(source_file.read())
    parser.close()
    return parser.text()


def get_document_text(doc_path: str) -> str:
    cached_text = DOC_TEXT_CACHE.get(doc_path)
    if cached_text is not None:
        return cached_text

    full_path = os.path.join(DEFAULT_DOCS_DIR, doc_path)
    if not os.path.isfile(full_path):
        DOC_TEXT_CACHE[doc_path] = ""
        return ""

    extracted = extract_plain_text_from_html(full_path)
    DOC_TEXT_CACHE[doc_path] = extracted
    return extracted
