"""Extract unclassified city subsets while preserving source records and native pixels."""
from pathlib import Path
import hashlib
import json
import re

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyogrio
from pyproj import CRS, Transformer
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform_bounds
import shapely

from stage_1_data_inputs import configuration
from stage_1_data_inputs.city_definitions import city_record, fix_text, select_urban_centres, source_city_table, write_city_table
from stage_1_data_inputs.ghsl_sources import fetch_tile, tiles_for_bounds, tile_url, file_window

VECTOR_FILES = {
    'building': 'buildings/overture_buildings.parquet',
    'place': 'places/overture_points_of_interest.parquet',
    'segment': 'road_and_rail/overture_transport_segments.parquet',
    'infrastructure': 'supporting_land_features/overture_infrastructure_features.parquet',
    'land_use': 'supporting_land_features/overture_land_use_polygons.parquet',
    'water': 'supporting_land_features/overture_water_polygons.parquet',
}
RASTER_NAMES = {'pop': 'resident_population_2025', 'vol': 'total_building_volume_2025',
                'vol_nres': 'non_residential_building_volume_2025', 'height': 'building_height_2018'}
BUILDING_MARGIN_DEGREES = 0.003


def source_bounds(row, margin=0.):
    """WGS84 bounds of a densified domain boundary, including the reading margin."""
    x0, y1, cell = row['x0'], row['y1'], row['cell']
    x1, y0 = x0 + row['nx'] * cell, y1 - row['ny'] * cell
    t = np.linspace(0, 1, 200)
    xs = np.r_[x0 + (x1-x0)*t, np.full(200,x1), x1-(x1-x0)*t, np.full(200,x0)]
    ys = np.r_[np.full(200,y1), y1-(y1-y0)*t, np.full(200,y0), y0+(y1-y0)*t]
    crs = CRS.from_proj4(f"+proj=laea +lat_0={row['lat0']:.6f} +lon_0={row['lon0']:.6f} +datum=WGS84 +units=m +no_defs")
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xs, ys)
    return [float(lon.min()-margin), float(lat.min()-margin), float(lon.max()+margin), float(lat.max()+margin)]


def _parquet(path):
    if Path(path).is_file():
        return pq.ParquetFile(path)
    if path.startswith('s3://') or not re.match(r'^[A-Za-z]:', path) and '://' not in path:
        import pyarrow.fs as fs
        return pq.ParquetFile(path.removeprefix('s3://'), filesystem=fs.S3FileSystem(anonymous=True, region='us-west-2'))
    return pq.ParquetFile(path)


def build_source_index(kind, destination, files=None):
    """Index source Parquet bounding-box statistics without classifying records."""
    from concurrent.futures import ThreadPoolExecutor
    if files is None:
        import pyarrow.fs as fs
        filesystem = fs.S3FileSystem(anonymous=True, region='us-west-2')
        if kind == 'buildings':
            prefixes = [('building','us-west-2.opendata.source.coop/tge-labs/openbuildingmap')]
        else:
            definitions = [('place','places','place')] if kind == 'places' else [
                ('building','buildings','building'), ('segment','transportation','segment'),
                ('infrastructure','base','infrastructure'), ('land_use','base','land_use'), ('water','base','water')]
            prefixes = [(layer,f'{configuration.OVERTURE_BUCKET}/{configuration.OVERTURE_RELEASE}/theme={theme}/type={typ}')
                        for layer,theme,typ in definitions]
        files = []
        for layer,prefix in prefixes:
            for info in filesystem.get_file_info(fs.FileSelector(prefix,recursive=False)):
                if info.type == fs.FileType.File and info.path.endswith('.parquet'):
                    files.append((layer,'s3://'+info.path))
    if not files:
        raise FileNotFoundError(f'No source Parquet files for {kind}')
    def one(item):
        layer,path = item
        metadata = _parquet(str(path)).metadata
        names = [metadata.schema.column(i).path for i in range(metadata.num_columns)]
        columns = {field:names.index('bbox.'+field) for field in ('xmin','xmax','ymin','ymax')}
        rows = []
        for number in range(metadata.num_row_groups):
            group = metadata.row_group(number)
            stats = {field:group.column(column).statistics for field,column in columns.items()}
            if any(value is None or not value.has_min_max for value in stats.values()):
                west,east,south,north = -180.,180.,-90.,90.
            else:
                west,east,south,north = stats['xmin'].min,stats['xmax'].max,stats['ymin'].min,stats['ymax'].max
            rows.append(dict(layer=layer,path=str(path),rg=number,xmin=west,xmax=east,ymin=south,ymax=north,rows=group.num_rows))
        return rows
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = [row for group in pool.map(one,sorted(files)) for row in group]
    table = pd.DataFrame(records)
    destination = Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    table.to_parquet(destination,index=False)
    return table


def extract_vectors(index, layer, bounds, destination):
    """Keep whole source features and every source field; perform no use classification."""
    west, south, east, north = bounds
    selected = index[index.layer == layer] if 'layer' in index else index
    if selected.empty:
        raise ValueError(f'Source index has no {layer} layer')
    hits = selected[(selected.xmin <= east) & (selected.xmax >= west) &
                    (selected.ymin <= north) & (selected.ymax >= south)]
    parts, sources, schema = [], [], None
    for path, groups in hits.groupby('path', sort=True):
        path = str(path)
        table = _parquet(path).read_row_groups(groups.rg.astype(int).tolist())
        schema = table.schema
        box = table['bbox']
        mask = pc.and_(pc.and_(pc.less_equal(pc.struct_field(box,'xmin'),east), pc.greater_equal(pc.struct_field(box,'xmax'),west)),
                       pc.and_(pc.less_equal(pc.struct_field(box,'ymin'),north), pc.greater_equal(pc.struct_field(box,'ymax'),south)))
        subset = table.filter(mask)
        if subset.num_rows:
            parts.append(subset)
        sources.append({'path': path, 'row_groups': groups.rg.astype(int).tolist()})
    if not parts:
        schema = _parquet(str(selected.iloc[0]['path'])).schema_arrow
    table = pa.concat_tables(parts, promote_options='permissive') if parts else pa.Table.from_batches([], schema=schema)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, destination, compression='zstd')
    return {'records': table.num_rows, 'bounds_wgs84': bounds, 'sources': sources,
            'operation': 'Select whole source features by intersecting bounding boxes; preserve source attributes, geometry and CRS.'}


def crop_raster(source, destination, bounds):
    """Copy an integer pixel window; the source raster supplies its actual transform."""
    with rasterio.open(source) as src:
        projected_bounds = transform_bounds('EPSG:4326', src.crs, *bounds, densify_pts=30)
        col, line, right, bottom = file_window(src, *projected_bounds)
        if right <= col or bottom <= line:
            return None
        window = Window(col,line,right-col,bottom-line)
        profile = src.profile.copy()
        profile.update(width=int(window.width),height=int(window.height),transform=src.window_transform(window),compress='deflate')
        destination = Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with rasterio.open(destination,'w',**profile) as dst:
            dst.write(src.read(window=window))
            dst.update_tags(**src.tags())
    return {'source_window':[col,line,int(window.width),int(window.height)],
            'operation':'Native pixel-window crop only; preserve source CRS, resolution, alignment and pixel values.'}


def record_file(path, root, **metadata):
    path, root = Path(path), Path(root)
    record = dict(path=path.relative_to(root).as_posix(), **metadata,
                  bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    path.with_suffix('.source.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    return record


def prepare(args):
    """Write only original-source subsets and provenance under the raw-data directory."""
    root, out = configuration.ROOT, args.output.resolve()
    # Source record paths are relative to the repository.
    out.relative_to(root.resolve())
    if out.exists() and any(out.iterdir()) and not args.overwrite:
        raise FileExistsError(f'{out}: use --overwrite to replace source subsets')
    if out.exists():
        old_ids = {int(folder.name.split('_')[0]) for folder in out.iterdir()
                   if folder.is_dir() and folder.name.split('_')[0].isdigit()}
        if old_ids - set(args.city_ids):
            raise ValueError('Output contains other cities; choose an empty output directory')
    source = select_urban_centres(args.urban_centres, args.city_ids)
    table = source_city_table(source)
    write_city_table(table, merge=True)
    indexes = {}
    for kind,path in [('overture',args.overture_index),('places',args.places_index),('buildings',args.building_index)]:
        if not path.is_file() and args.build_missing_indexes:
            if args.offline:
                raise ValueError('Build remote source indexes before using --offline')
            build_source_index(kind,path)
        indexes[kind] = pd.read_parquet(path)
    regular, rasters = [], []
    for _, feature in source.iterrows():
        selected = source.loc[[feature.name]]
        row = table.loc[table.uc_id == int(feature.ID_UC_G0)].iloc[0].to_dict()
        stem = row['stem']
        dest = out/stem/'urban_centres/urban_centre_boundary.gpkg'
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            dest.unlink()
        pyogrio.write_dataframe(selected,dest,layer=configuration.UCDB_LAYER,driver='GPKG')
        regular.append(record_file(dest,root,city=stem,layer='urban_centre',records=1,
                                   source=str(args.urban_centres),operation='Select original urban-centre feature by ID; preserve geometry, attributes and CRS.'))
        for layer, relative in VECTOR_FILES.items():
            margin = BUILDING_MARGIN_DEGREES if layer in ('building','land_use') else 0.
            dest = out/stem/relative
            metadata = extract_vectors(indexes['places' if layer=='place' else 'overture'],layer,source_bounds(row,margin),dest)
            regular.append(record_file(dest,root,city=stem,layer=layer,source_release=configuration.OVERTURE_RELEASE,
                                       processing_margin_degrees=margin,**metadata))
        dest = out/stem/'buildings/open_building_map_buildings.parquet'
        metadata = extract_vectors(indexes['buildings'],'building',source_bounds(row,BUILDING_MARGIN_DEGREES),dest)
        regular.append(record_file(dest,root,city=stem,layer='building',source_release='OpenBuildingMap 2025',
                                     processing_margin_degrees=BUILDING_MARGIN_DEGREES,**metadata))
        bounds = source_bounds(row)
        mollweide = transform_bounds(4326,configuration.MOLLWEIDE,*bounds,densify_pts=30)
        for product, label in RASTER_NAMES.items():
            count = 0
            for tile_row,tile_col in tiles_for_bounds(*mollweide):
                tile = fetch_tile(product,tile_row,tile_col,args.raster_cache,offline=args.offline)
                if tile is None:
                    continue
                dest = out/stem/'population'/f'ghsl_{label}_R{tile_row}_C{tile_col}.tif'
                metadata = crop_raster(tile,dest,bounds)
                if metadata is not None:
                    count += 1
                    rasters.append(record_file(dest,root,city=stem,source=tile_url(product,tile_row,tile_col),**metadata))
            if count == 0:
                raise FileNotFoundError(f'{stem}: no {product} source pixels')
        print(json.dumps({'city':stem,'stage':1,'status':'extracted'}),flush=True)
    return len(regular)+len(rasters)
