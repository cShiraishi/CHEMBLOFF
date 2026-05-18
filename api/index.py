from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import httpx
import pandas as pd
import io
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data"
HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "public", "index.html")

@app.get("/")
def root():
    with open(HTML_PATH, "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/search")
async def search_target(q: str = Query(..., min_length=2)):
    async with httpx.AsyncClient(timeout=8) as client:
        res = await client.get(f"{CHEMBL_API}/target/search", params={"q": q, "format": "json"})
        res.raise_for_status()
        data = res.json()
    targets = data.get("targets", [])
    return [
        {
            "id": t["target_chembl_id"],
            "name": t.get("pref_name", ""),
            "type": t.get("target_type", ""),
            "organism": t.get("organism", "")
        }
        for t in targets[:15]
    ]

@app.get("/api/preview")
async def preview(
    target_id: str = Query(...),
    activity_type: str = Query("IC50"),
    limit: int = Query(100, le=500)
):
    async with httpx.AsyncClient(timeout=8) as client:
        res = await client.get(f"{CHEMBL_API}/activity", params={
            "target_chembl_id": target_id,
            "standard_type": activity_type,
            "format": "json",
            "limit": min(limit, 100)
        })
        res.raise_for_status()
        data = res.json()
    activities = data.get("activities", [])
    fields = ["molecule_chembl_id", "canonical_smiles", "standard_type", "standard_value", "standard_units", "assay_type", "pchembl_value"]
    rows = [{f: a.get(f) for f in fields} for a in activities]
    return {"total_shown": len(rows), "data": rows}

@app.get("/api/download")
async def download(
    target_id: str = Query(...),
    activity_type: str = Query("IC50"),
    limit: int = Query(500, le=1000)
):
    fields = ["molecule_chembl_id", "canonical_smiles", "standard_type", "standard_value", "standard_units", "assay_type", "pchembl_value"]
    all_rows = []
    offset = 0
    page_size = 100

    async with httpx.AsyncClient(timeout=8) as client:
        while len(all_rows) < limit:
            res = await client.get(f"{CHEMBL_API}/activity", params={
                "target_chembl_id": target_id,
                "standard_type": activity_type,
                "format": "json",
                "limit": page_size,
                "offset": offset
            })
            res.raise_for_status()
            data = res.json()
            activities = data.get("activities", [])
            if not activities:
                break
            all_rows.extend([{f: a.get(f) for f in fields} for a in activities])
            offset += page_size
            if len(activities) < page_size:
                break

    if not all_rows:
        raise HTTPException(status_code=404, detail="No data found.")

    df = pd.DataFrame(all_rows[:limit])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    filename = f"{target_id}_{activity_type}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

handler = Mangum(app)
