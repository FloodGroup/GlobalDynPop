"""Download native WorldCover and GSW raster windows for the bundled model domains."""
import sys,os,importlib.util,json,math,hashlib,time
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window,from_bounds
from rasterio.warp import transform_bounds
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'02_code'))
from stage_2_100m_layers.cities import load_cities,grid_of
spec=importlib.util.spec_from_file_location('water',R/'02_code/stage_2_100m_layers/05_prepare_permanent_water.py')
water=importlib.util.module_from_spec(spec);spec.loader.exec_module(water)

def crop(url,target,bounds):
    if target.exists() and target.with_suffix('.source.json').exists():
        return json.loads(target.with_suffix('.source.json').read_text())
    target.parent.mkdir(parents=True,exist_ok=True)
    for attempt in range(4):
        try:
            with rasterio.Env(**water.ENV),rasterio.open(url) as src:
                b=transform_bounds('EPSG:4326',src.crs,*bounds,densify_pts=101)
                w=from_bounds(*b,src.transform)
                left=max(0,math.floor(w.col_off)-3);top=max(0,math.floor(w.row_off)-3)
                right=min(src.width,math.ceil(w.col_off+w.width)+3);bottom=min(src.height,math.ceil(w.row_off+w.height)+3)
                if right<=left or bottom<=top:raise ValueError('Empty intersection')
                window=Window(left,top,right-left,bottom-top)
                array=src.read(window=window)
                profile=src.profile.copy();profile.update(width=array.shape[2],height=array.shape[1],transform=src.window_transform(window),compress='deflate',tiled=True,blockxsize=256,blockysize=256)
                with rasterio.open(target,'w',**profile) as dst:
                    dst.write(array);dst.update_tags(**src.tags())
                    for band in range(1,src.count+1):
                        dst.update_tags(band,**src.tags(band))
                        try:dst.write_colormap(band,src.colormap(band))
                        except ValueError:pass
                with rasterio.open(target) as check:
                    assert np.array_equal(check.read(),array)
                    assert check.crs==src.crs and check.transform==src.window_transform(window)
                rec=dict(path=target.relative_to(R).as_posix(),source=url.replace('/vsicurl/',''),operation='Native integer pixel-window subset; original CRS, pixel spacing, alignment and values retained. No resampling.',bounds_wgs84=bounds,source_window=[left,top,right-left,bottom-top],source_shape=[src.height,src.width],source_transform=list(src.transform),crs=str(src.crs),nodata=src.nodata,dtype=src.dtypes[0],shape=list(array.shape),bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),native_values_verified=True)
            target.with_suffix('.source.json').write_text(json.dumps(rec,indent=2),encoding='utf-8')
            print(json.dumps({'file':target.name,'shape':rec['shape'],'bytes':rec['bytes']}),flush=True)
            return rec
        except Exception as e:
            if attempt==3:raise
            print('retry',target.name,str(e)[:180],flush=True);time.sleep(3)


def main():
    records=[]
    for row in load_cities().to_dict('records'):
        bounds=grid_of(row).lonlat_bounds(.02)
        folder=R/'01_inputs/demo/raw'/row['stem']/'land_cover'
        jobs=[water.WC_URL.format(t) for t in water.wc_tiles(*bounds)]+[water.GSW_URL.format(a+b) for a,b in water.gsw_tiles(*bounds)]
        for url in jobs:
            rec=crop(url,folder/(( 'JRC_' if url.rsplit('/',1)[-1].startswith('transitions_') else '') + url.rsplit('/',1)[-1]),bounds);rec['city']=row['stem'];records.append(rec)
    print('COMPLETE',len(records),flush=True)

if __name__ == "__main__":
    main()
