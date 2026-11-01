"""Verify the supplied original-source city subsets against their provenance manifests."""
from pathlib import Path
import hashlib,json,os
def check():
    root=Path(os.environ.get("DYNAMIC_POPULATION_ROOT",Path(__file__).resolve().parents[2]))
    raw=Path(os.environ.get("DYNAMIC_POPULATION_RAW_INPUTS",root/"01_inputs/demo/raw"))
    records=[]
    for name in ("source_manifest.json","raster_manifest.json","open_building_map_manifest.json"):
        records+=json.loads((raw/name).read_text())
    for row in records:
        p=root/row["path"]
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row["sha256"]:raise RuntimeError("Raw source mismatch: "+row["path"])
    print(json.dumps({"raw_source_files_verified":len(records)}))
if __name__=="__main__":check()
