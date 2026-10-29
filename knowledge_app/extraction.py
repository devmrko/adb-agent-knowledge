import http.client
import io
import ipaddress
import posixpath
import socket
import ssl
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from urllib.parse import urlsplit

from pypdf import PdfReader

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
NOTES_MARKER = "\n[발표자 노트]\n"
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def extract_pptx(data: bytes, max_chars: int) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = archive.infolist()
            if len(files) > 10000 or sum(f.file_size for f in files) > 100_000_000:
                raise ExtractionError("PPTX_TOO_LARGE")

            def xml(path: str) -> ET.Element:
                if archive.getinfo(path).file_size > 10_000_000:
                    raise ExtractionError("PPTX_XML_TOO_LARGE")
                raw = archive.read(path)
                if (
                    b"<!DOCTYPE" in raw.replace(b"\x00", b"").upper()
                    or b"<!ENTITY" in raw.replace(b"\x00", b"").upper()
                ):
                    raise ExtractionError("PPTX_UNSUPPORTED_XML")
                return ET.fromstring(raw)

            def relationships(path: str) -> dict[str, tuple[str, str]]:
                relpath = posixpath.join(posixpath.dirname(path), "_rels", posixpath.basename(path) + ".rels")
                if relpath not in archive.namelist():
                    return {}
                result = {}
                for rel in xml(relpath):
                    if rel.get("TargetMode") == "External":
                        continue
                    target = rel.get("Target", "")
                    target = (
                        posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                        if not target.startswith("/")
                        else target.lstrip("/")
                    )
                    if target.startswith("../"):
                        raise ExtractionError("PPTX_INVALID_RELATIONSHIP")
                    result[rel.get("Id", "")] = (target, rel.get("Type", ""))
                return result

            def texts(tree: ET.Element, *, notes: bool = False) -> str:
                parts = []
                if notes:
                    shapes = tree.findall(".//p:sp", NS)
                    for shape in shapes:
                        placeholder = shape.find(".//p:ph", NS)
                        if placeholder is not None and placeholder.get("type") in {
                            "sldImg",
                            "sldNum",
                            "hdr",
                            "ftr",
                            "dt",
                        }:
                            continue
                        for paragraph in shape.findall(".//a:p", NS):
                            parts.append("".join(t.text or "" for t in paragraph.findall(".//a:t", NS)))
                else:
                    for paragraph in tree.findall(".//a:p", NS):
                        parts.append("".join(t.text or "" for t in paragraph.findall(".//a:t", NS)))
                return "\n".join(parts).strip()

            slides = xml("ppt/presentation.xml").findall("p:sldIdLst/p:sldId", NS)
            if len(slides) > 500:
                raise ExtractionError("PPTX_TOO_MANY_SLIDES")
            rels = relationships("ppt/presentation.xml")
            pages = []
            size = 0
            for slide in slides:
                path, kind = rels[slide.attrib["{" + NS["r"] + "}id"]]
                if not kind.endswith("/slide"):
                    raise ExtractionError("PPTX_INVALID_RELATIONSHIP")
                value = texts(xml(path))
                for target, reltype in relationships(path).values():
                    if reltype.endswith("/notesSlide"):
                        notes = texts(xml(target), notes=True)
                        if notes:
                            value += NOTES_MARKER + notes
                size += len(value) + 1
                if size > max_chars:
                    raise ExtractionError("TEXT_TOO_LARGE")
                pages.append(value)
            return "\f".join(pages)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError, ValueError) as error:
        raise ExtractionError("PPTX_INVALID") from error


class ExtractionError(Exception):
    pass


class TextHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "h1", "h2", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def extract(data: bytes, mime: str, max_chars: int) -> str:
    if mime == PPTX_MIME:
        result = extract_pptx(data, max_chars)
    elif mime == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 500:
            raise ExtractionError("PDF_UNSUPPORTED")
        pages: list[str] = []
        size = 0
        for page in reader.pages:
            value = page.extract_text() or ""
            size += len(value)
            if size > max_chars:
                raise ExtractionError("TEXT_TOO_LARGE")
            pages.append(value)
        result = "\f".join(pages)
    elif mime in {"text/plain", "text/markdown", "text/html"}:
        result = data.decode("utf-8-sig")
        if mime == "text/html":
            parser = TextHTML()
            parser.feed(result)
            result = "".join(parser.parts)
    else:
        raise ExtractionError("UNSUPPORTED_MEDIA")
    if not result.strip():
        raise ExtractionError("NO_TEXT_OCR_REQUIRED")
    if len(result) > max_chars:
        raise ExtractionError("TEXT_TOO_LARGE")
    return result


def fetch_url(url: str, allowed_hosts: set[str], maximum: int) -> tuple[bytes, str]:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or host.lower() not in allowed_hosts
    ):
        raise ExtractionError("URL_NOT_ALLOWED")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ips = [str(entry[4][0]) for entry in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ExtractionError("URL_NOT_PUBLIC")
    # Pin validated IP; TLS still verifies original hostname. No proxy/redirect/DNS re-resolution.
    connection = http.client.HTTPSConnection(host, timeout=15)
    try:
        raw = socket.create_connection((ips[0], 443), timeout=15)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        except BaseException:
            raw.close()
            raise
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection.request("GET", path, headers={"Host": host, "User-Agent": "VectorKnowledge/0.1"})
        response = connection.getresponse()
        if response.status != 200:
            raise ExtractionError("URL_FETCH_FAILED")
        data = response.read(maximum + 1)
        if len(data) > maximum:
            raise ExtractionError("SOURCE_TOO_LARGE")
        return data, response.getheader("Content-Type", "").split(";")[0].strip().lower()
    finally:
        connection.close()
