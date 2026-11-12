"""Downloads the 3 papers at the exact versions and stores text page by page."""
import httpx, io, json, os
from pypdf import PdfReader
P = [("1706.03762v7", "Attention Is All You Need"), ("2410.00037v1", "Moshi"), ("2507.07955v2", "Dynamic Chunking")]
os.makedirs("data", exist_ok=True); pages = []
for aid, name in P:
    r = httpx.get(f"https://arxiv.org/pdf/{aid}", follow_redirects=True, timeout=90); r.raise_for_status()
    open(f"data/{aid}.pdf", "wb").write(r.content)
    for i, pg in enumerate(PdfReader(io.BytesIO(r.content)).pages, 1):
        pages.append(dict(paper=name, arxiv=aid.split("v")[0], version=aid, page=i, text=" ".join((pg.extract_text() or "").split())))
    print("ok", aid)
json.dump(pages, open("data/pages.json", "w"))
