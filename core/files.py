"""Text extraction for chat attachments. Stdlib only — no parser dependencies.

Covers the formats people actually drop into a chat: plain text/markdown/CSV/JSON/
code, PDF (text layer), and DOCX. Anything else is refused with a clear reason.
"""
import io
import re
import zipfile

MAX_BYTES = 2 * 1024 * 1024   # 2 MB — larger files are a document store problem
MAX_CHARS = 8000              # what actually fits in a prompt without crowding it

TEXT_EXT = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".log", ".ini", ".cfg", ".toml", ".xml", ".html", ".css", ".js", ".ts",
    ".py", ".sql", ".sh",
}


class UnsupportedFile(Exception):
    pass


def extract(filename: str, data: bytes) -> tuple[str, int]:
    """Return (text truncated to MAX_CHARS, total chars before truncation).

    Raises UnsupportedFile. The total matters: a 40-page report summarised from
    its first 8,000 characters reads as complete unless the caller says otherwise.
    """
    if len(data) > MAX_BYTES:
        raise UnsupportedFile("file is larger than 2 MB")

    name = (filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""

    if ext in TEXT_EXT:
        text = data.decode("utf-8-sig", errors="replace")  # -sig drops a leading BOM
    elif ext == ".pdf":
        text = _pdf(data)
    elif ext == ".docx":
        text = _docx(data)
    else:
        raise UnsupportedFile(f"cannot read {ext or 'that file type'} — try txt, md, csv, json, pdf or docx")

    text = text.strip()
    if not text:
        raise UnsupportedFile("no readable text in that file")
    return text[:MAX_CHARS], len(text)


def _pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise UnsupportedFile("PDF reading needs the pypdf package")
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _docx(data: bytes) -> str:
    """A .docx is a zip; the body lives in word/document.xml. Paragraphs are <w:p>."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError):
        raise UnsupportedFile("that .docx is unreadable")
    xml = xml.replace("</w:p>", "\n")
    return re.sub(r"<[^>]+>", "", xml)
