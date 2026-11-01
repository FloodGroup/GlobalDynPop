"""Compare requested v4 outputs; missing, empty or incompatible inputs fail."""
from pathlib import Path
import argparse,json
import numpy as np
def compare_arrays(a,b,tol):
    if not a or set(a)!=set(b):raise ValueError('Empty or different band/key sets')
    worst=0.;absolute=0.;count=0
    for key in a:
        x=np.asarray(a[key],dtype=np.float64);y=np.asarray(b[key],dtype=np.float64)
        if x.shape!=y.shape or not x.size:raise ValueError(f'{key}: empty or different shape')
        if not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError(f'{key}: non-finite values')
        d=float(np.abs(x-y).max());r=d/max(float(np.abs(x).max()),1e-12)
        absolute=max(absolute,d);worst=max(worst,r);count+=1
    return {'bands_compared':count,'max_absolute_difference':absolute,'largest_relative_difference':worst,'reproduced':worst<=tol}
def rasters(a,b,tol):
    for path in [a,b]:
        if not Path(path).is_file():raise FileNotFoundError(f'Missing raster: {path}')
    import rasterio
    with rasterio.open(a) as x,rasterio.open(b) as y:
        if (x.crs,x.transform,x.shape,x.count,x.descriptions)!=(y.crs,y.transform,y.shape,y.count,y.descriptions):raise ValueError('Raster grid, band count or descriptions differ')
        ma,mb=x.read_masks(),y.read_masks()
        if not np.array_equal(ma,mb):raise ValueError('Raster masks differ')
        A={};B={}
        for i in range(1,x.count+1):
            valid=ma[i-1]>0
            if not valid.any():raise ValueError('Band has no valid cells')
            A[str(i)]=x.read(i)[valid];B[str(i)]=y.read(i)[valid]
        return compare_arrays(A,B,tol)
def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    for flag in ['a','b','net-a','net-b','hourly-a','hourly-b']:ap.add_argument('--'+flag)
    ap.add_argument('--stems',nargs='+',required=True);ap.add_argument('--tol',type=float,default=1e-5)
    args=ap.parse_args(argv);results=[];errors=[];pairs=[(args.a,args.b),(args.net_a,args.net_b),(args.hourly_a,args.hourly_b)]
    if not any(a or b for a,b in pairs) or any(bool(a)!=bool(b) for a,b in pairs):errors.append('Provide at least one complete pair of input directories')
    if not np.isfinite(args.tol) or args.tol<0:errors.append('Tolerance must be finite and nonnegative')
    if not errors:
        for stem in args.stems:
            try:
                if args.a:results.append(rasters(Path(args.a)/f'{stem}.tif',Path(args.b)/f'{stem}.tif',args.tol))
                if args.net_a:
                    with np.load(Path(args.net_a)/f'{stem}.npz',allow_pickle=False) as a,np.load(Path(args.net_b)/f'{stem}.npz',allow_pickle=False) as b:
                        results.append(compare_arrays({k:a[k] for k in ['T_workday','T_restday']},{k:b[k] for k in ['T_workday','T_restday']},args.tol))
                if args.hourly_a:
                    for dt in ['workday','rest_day']:
                        name=f'{stem}_{dt}.tif';results.append(rasters(Path(args.hourly_a)/stem/name,Path(args.hourly_b)/stem/name,args.tol))
            except (OSError,ValueError,KeyError,ImportError) as e:errors.append(f'{stem}: {type(e).__name__}: {e}')
    ok=bool(results) and not errors and all(x['reproduced'] for x in results)
    print(json.dumps({'reproduced':ok,'comparisons':len(results),'tolerance':args.tol if np.isfinite(args.tol) else None,'results':results,'errors':errors},allow_nan=False));return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
