from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from chembl_webresource_client.new_client import new_client
import pandas as pd
import io
import os

app = FastAPI()

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "public")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return FileResponse(os.path.join(PUBLIC_DIR, "index.html"))

ACTIVITY_FIELDS = [
    "molecule_chembl_id", "canonical_smiles", "standard_type",
    "standard_value", "standard_units", "assay_type", "pchembl_value"
]

@app.get("/api/search")
def search_target(q: str = Query(..., min_length=2)):
    target = new_client.target
    results = list(target.search(q))
    return [
        {
            "id": t["target_chembl_id"],
            "name": t.get("pref_name", ""),
            "type": t.get("target_type", ""),
            "organism": t.get("organism", "")
        }
        for t in results[:15]
    ]

@app.get("/api/preview")
def preview(
    target_id: str = Query(...),
    activity_type: str = Query("IC50"),
    limit: int = Query(100, le=500)
):
    activity = new_client.activity
    acts = list(
        activity.filter(
            target_chembl_id=target_id,
            standard_type=activity_type
        ).only(ACTIVITY_FIELDS)[:limit]
    )
    total = len(acts)
    return {"total_shown": total, "data": acts}

@app.get("/api/download")
def download(
    target_id: str = Query(...),
    activity_type: str = Query("IC50"),
    limit: int = Query(5000, le=10000)
):
    activity = new_client.activity
    acts = list(
        activity.filter(
            target_chembl_id=target_id,
            standard_type=activity_type
        ).only(ACTIVITY_FIELDS)[:limit]
    )
    if not acts:
        raise HTTPException(status_code=404, detail="Nenhum dado encontrado.")

    df = pd.DataFrame(acts)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    filename = f"{target_id}_{activity_type}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
