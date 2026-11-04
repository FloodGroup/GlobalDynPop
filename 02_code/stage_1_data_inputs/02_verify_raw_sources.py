"""Check original city subsets using their existing per-file source records."""
from pathlib import Path
import hashlib,json,os,sqlite3

def check():
    root=Path(os.environ.get("DYNAMIC_POPULATION_ROOT",Path(__file__).resolve().parents[2]))
    raw=Path(os.environ.get("DYNAMIC_POPULATION_RAW_INPUTS",root/"01_inputs/demo/raw"))
    stems=(root/"03_run/demo_configuration/city_demo_stems.txt").read_text().split()
    checked=set()
    for stem in stems:
        folder=raw/stem
        if not folder.is_dir():raise FileNotFoundError(folder)
        records=sorted(folder.rglob("*.source.json"))
        if not records:raise RuntimeError("No source records: "+str(folder))
        for metadata in records:
            row=json.loads(metadata.read_text(encoding="utf-8"))
            if "path" in row:
                relative=Path(row["path"]).relative_to("01_inputs/demo/raw")
                p=raw/relative
            else:
                p=metadata.with_name(metadata.name.removesuffix(".source.json")+".parquet")
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row["sha256"]:
                raise RuntimeError("Raw source mismatch: "+str(p))
            checked.add(p)
        boundary=folder/"urban_centres/urban_centre_boundary.gpkg"
        if not boundary.is_file():raise FileNotFoundError(boundary)
        with sqlite3.connect(boundary.resolve().as_uri()+"?mode=ro",uri=True) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                raise RuntimeError("Invalid urban-centre database: "+str(boundary))
            if not db.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'").fetchall():
                raise RuntimeError("No boundary features: "+str(boundary))
        checked.add(boundary)
    print(json.dumps({"raw_source_files_verified":len(checked)}))
if __name__=="__main__":check()
