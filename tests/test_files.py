"""Spec X — attachment text extraction: PDF pages, truncation reporting, upload wiring."""
import io

import pytest

from core.files import MAX_CHARS, UnsupportedFile, extract


def _pdf(*page_texts: str) -> bytes:
    """Smallest real PDF with a text layer, one page per argument, correct xref."""
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[" + b" ".join(
            f"{3 + i} 0 R".encode() for i in range(len(page_texts))
        ) + f"]/Count {len(page_texts)}>>".encode(),
    ]
    first_content = 3 + len(page_texts)
    font_num = first_content + len(page_texts)
    for i in range(len(page_texts)):
        objs.append(f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]"
                    f"/Resources<</Font<</F1 {font_num} 0 R>>>>"
                    f"/Contents {first_content + i} 0 R>>".encode())
    for text in page_texts:
        stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
        objs.append(b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream")
    objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def test_pdf_extracts_every_page():
    text, total = extract("report.pdf", _pdf("ALPHA ON PAGE ONE", "OMEGA ON PAGE TWO"))
    assert "ALPHA ON PAGE ONE" in text
    assert "OMEGA ON PAGE TWO" in text      # proves multi-page joining
    assert total == len(text)


def test_pdf_dependency_is_installed():
    """pypdf missing in production made every PDF upload look like a user error."""
    import pypdf  # noqa: F401


def test_short_file_is_not_truncated():
    text, total = extract("notes.txt", b"x" * 800)
    assert len(text) == 800 and total == 800


def test_long_file_truncates_and_reports_the_real_size():
    text, total = extract("report.txt", b"y" * 20000)
    assert len(text) == MAX_CHARS and total == 20000


def test_boundary_is_not_reported_as_truncated():
    text, total = extract("exact.txt", b"z" * MAX_CHARS)
    assert total == len(text) == MAX_CHARS


def test_unsupported_type_is_refused():
    with pytest.raises(UnsupportedFile):
        extract("photo.png", b"\x89PNG")


def test_upload_endpoint_reports_truncation(client):
    res = client.post("/api/friday/upload", content_type="multipart/form-data",
                      data={"file": (io.BytesIO(b"y" * 20000), "report.txt")})
    body = res.get_json()
    assert body["truncated"] is True
    assert body["chars"] == MAX_CHARS and body["total_chars"] == 20000

    res = client.post("/api/friday/upload", content_type="multipart/form-data",
                      data={"file": (io.BytesIO(b"short"), "notes.txt")})
    assert res.get_json()["truncated"] is False
