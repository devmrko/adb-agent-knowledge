"""Live PDF and HTTPS source checks; creates two labelled development documents."""

import io
import time

import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from knowledge_app.settings import Settings

writer = PdfWriter()
page = writer.add_blank_page(width=300, height=300)
font = DictionaryObject(
    {
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }
)
page[NameObject("/Resources")] = DictionaryObject(
    {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
)
stream = DecodedStreamObject()
stream.set_data(b"BT /F1 12 Tf 20 250 Td (Oracle Wallet connection guide) Tj ET")
page[NameObject("/Contents")] = writer._add_object(stream)
output = io.BytesIO()
writer.write(output)
settings = Settings()
assert settings.dev_api_token
with httpx.Client(
    base_url="http://127.0.0.1:8000",
    timeout=120,
    headers={"Authorization": "Bearer " + settings.dev_api_token.get_secret_value()},
) as client:
    schema = client.get("/openapi.json").json()
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    response = client.post(
        "/api/v1/knowledge/files",
        data={"title": "[개발 검증] PDF 원문"},
        files={"file": ("guide.pdf", output.getvalue(), "application/pdf")},
    )
    response.raise_for_status()
    pdf = response.json()
    response = client.post(
        "/api/v1/knowledge", json={"title": "[개발 검증] 공개 URL", "url": "https://example.com"}
    )
    response.raise_for_status()
    url = response.json()
    for ids, expected in [(pdf, "Oracle Wallet"), (url, "Example Domain")]:
        for _ in range(90):
            response = client.get("/api/v1/jobs/" + ids["job_id"])
            response.raise_for_status()
            job = response.json()
            if job["status"] in {"READY", "FAILED"}:
                break
            time.sleep(2)
        assert job["status"] == "READY", job
        response = client.get(
            "/api/v1/knowledge/" + ids["knowledge_id"] + "/revisions/" + ids["revision_id"] + "/content"
        )
        response.raise_for_status()
        assert expected in response.json()["text"]
        print("PASS source:", expected, "knowledge_id:", ids["knowledge_id"], flush=True)
    response = client.post("/api/v1/knowledge/search", json={"query": "Oracle Wallet connection guide"})
    response.raise_for_status()
    assert any(item["knowledge_id"] == pdf["knowledge_id"] for item in response.json()["items"])
    print("PASS PDF search and Swagger Bearer schema", flush=True)
