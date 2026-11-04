"""Rebuild three-city spatial inputs offline and compare them with bundled model layers."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys

ROOT=Path(os.environ.get("DYNAMIC_POPULATION_ROOT", Path(__file__).resolve().parents[1]))
REFERENCE=ROOT/'04_intermediate/demo/stage_2'
GRID_REFERENCE=ROOT/'04_intermediate/demo/stage_1/local_grids/city_grid_definitions.csv'
STEMS=(ROOT/'03_run/demo_configuration/city_demo_stems.txt').read_text().split()
SPATIAL=['resident_population','buildings','point_of_interest_counts/overture','road_and_rail_graphs',
         'water_coverage_percent','basemap/landcover','basemap/outdoor','basemap/land_use','basemap/open_space','smoothed_places']

def compare(rebuilt,stems):
    import numpy as np
    import pandas as pd
    records=[]
    x=pd.read_csv(rebuilt.parent/'stage_1/local_grids/city_grid_definitions.csv').set_index('stem')
    y=pd.read_csv(GRID_REFERENCE).set_index('stem')
    for stem in stems:
        for key in ['lon0','lat0','x0','y1','nx','ny','cell']:
            records.append(dict(path='stage_1/local_grids/city_grid_definitions.csv',stem=stem,key=key,
                                exact=bool(x.loc[stem,key]==y.loc[stem,key]),max_abs=abs(float(x.loc[stem,key]-y.loc[stem,key]))))
    for folder in SPATIAL:
        for ref in sorted((REFERENCE/folder).rglob('*')):
            if ref.suffix not in ('.npy','.npz') or ref.stem not in stems:continue
            rel=ref.relative_to(REFERENCE);path=rebuilt/rel
            if not path.is_file():
                records.append(dict(path=rel.as_posix(),exact=False,status='missing_reconstruction'));continue
            a={'array':np.load(path)} if path.suffix=='.npy' else dict(np.load(path,allow_pickle=False))
            b={'array':np.load(ref)} if ref.suffix=='.npy' else dict(np.load(ref,allow_pickle=False))
            for key in sorted(set(a)|set(b)):
                if key=='meta':continue
                rec=dict(path=rel.as_posix(),key=key)
                if key not in a or key not in b:
                    records.append(dict(rec,exact=False,status='missing_key'));continue
                u,v=a[key],b[key]
                if u.dtype.kind in 'USO' or v.dtype.kind in 'USO':continue
                rec.update(shape_equal=u.shape==v.shape,exact=bool(np.array_equal(u,v)))
                if u.shape==v.shape:
                    if not np.isfinite(u).all():raise ValueError(f'Non-finite {rel}/{key}')
                    delta=u.astype(float)-v.astype(float)
                    rec.update(max_abs=float(np.abs(delta).max(initial=0)),different_values=int(np.count_nonzero(delta)),
                               values=int(u.size),sum_rebuilt=float(u.sum(dtype=float)),sum_reference=float(v.sum(dtype=float)),
                               relative_l1=float(np.abs(delta).sum()/max(np.abs(v.astype(float)).sum(),1e-30)))
                records.append(rec)
    return records

def main():
    from run_city_demo import run
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT/'04_intermediate/demo/reproduction')
    ap.add_argument('--stems', nargs='+', choices=STEMS, default=STEMS)
    ap.add_argument('--compare-only', action='store_true')
    ap.add_argument('--require-exact', action='store_true')
    a = ap.parse_args()
    if not a.compare_only:
        run('run', '1', a.out, a.stems)
        run('run', '2', a.out, a.stems)
    records = compare(a.out/'stage_2', a.stems)
    report = dict(checks=len(records), exact_checks=sum(r['exact'] for r in records), comparisons=records)
    report['all_exact'] = report['checks'] == report['exact_checks']
    (a.out/'spatial_reference_comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='comparisons'}), flush=True)
    return 1 if a.require_exact and not report['all_exact'] else 0

if __name__=='__main__':sys.exit(main())
