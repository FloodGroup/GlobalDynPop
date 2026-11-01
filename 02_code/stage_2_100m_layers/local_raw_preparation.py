"""Prepare city-grid layers from the original-source subsets shipped with the example."""
from pathlib import Path
import argparse
import importlib
import json
import time

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyogrio
import rasterio
from rasterio.features import rasterize
from affine import Affine
from pyproj import Transformer
import shapely

import stage_1_data_inputs.configuration as configuration
from stage_2_100m_layers import buildings, cities, grid, places
from stage_2_100m_layers.building_sources import overture_reader, open_building_map_reader
from stage_3_activity_allocation import network


class LocalOverture(overture_reader.Reader):
    """Use the original source reader's filters on local, unclassified features."""

    def __init__(self, folder):
        self.s3 = None
        self.threads = 1
        names = {
            'building': 'buildings/overture_buildings.parquet',
            'place': 'places/overture_points_of_interest.parquet',
            'segment': 'road_and_rail/overture_transport_segments.parquet',
            'land_use': 'supporting_land_features/overture_land_use_polygons.parquet',
            'water': 'supporting_land_features/overture_water_polygons.parquet',
            'infrastructure': 'supporting_land_features/overture_infrastructure_features.parquet',
        }
        self.files = {key: folder / name for key, name in names.items()}

    def row_groups(self, layer, bbox):
        path = self.files[layer]
        count = pq.ParquetFile(path).num_row_groups
        return pd.DataFrame({'path': [str(path)] * count, 'rg': range(count)})


class LocalBuildings(open_building_map_reader.Reader):
    """Match local OpenBuildingMap occupancy and height records to footprints."""

    def __init__(self, path):
        self.s3 = None
        self.threads = 1
        self.path = path

    def row_groups(self, bbox):
        source = pq.ParquetFile(self.path)
        return pd.DataFrame({
            'path': [str(self.path)] * source.num_row_groups,
            'rg': range(source.num_row_groups),
            'rows': [source.metadata.row_group(k).num_rows for k in range(source.num_row_groups)],
        })


class LocalPlaces:
    def __init__(self, path):
        self.path = path

    def read_bbox(self, west, south, east, north, threads=1):
        table = pq.read_table(self.path)
        x = pc.struct_field(table['bbox'], 'xmin')
        y = pc.struct_field(table['bbox'], 'ymin')
        mask = pc.and_(pc.and_(pc.greater_equal(x, west), pc.less_equal(x, east)),
                       pc.and_(pc.greater_equal(y, south), pc.less_equal(y, north)))
        table = table.filter(mask)
        hierarchy = pc.struct_field(table['taxonomy'], 'hierarchy').to_pandas()
        return pd.DataFrame({
            'lon': pc.struct_field(table['bbox'], 'xmin').to_numpy(),
            'lat': pc.struct_field(table['bbox'], 'ymin').to_numpy(),
            'confidence': table['confidence'].to_numpy(),
            'status': table['operating_status'].to_pandas(),
            'basic': table['basic_category'].to_pandas(),
            'top': hierarchy.map(lambda values: values[0] if values is not None and len(values) else None),
        })


def city_table(folders):
    rows = []
    for folder in folders:
        source = pyogrio.read_dataframe(folder / 'urban_centres/urban_centre_boundary.gpkg',
                                       layer=configuration.UCDB_LAYER)
        if len(source) != 1:
            raise ValueError(f'{folder.name}: expected one urban-centre feature')
        row = source.iloc[0]
        geometry = row.geometry
        centre = shapely.centroid(geometry)
        lon, lat = Transformer.from_crs(source.crs, 4326, always_xy=True).transform(centre.x, centre.y)
        crs = grid.laea_crs(lon, lat)
        transform = Transformer.from_crs(source.crs, crs, always_xy=True)
        polygon = shapely.transform(shapely.segmentize(geometry, 200.),
                                    lambda xy: np.column_stack(transform.transform(xy[:, 0], xy[:, 1])))
        x0, y0, x1, y1 = polygon.bounds
        cell = configuration.CELL
        margin = configuration.BUFFER_M
        x0 = np.floor((x0 - margin) / cell) * cell
        y0 = np.floor((y0 - margin) / cell) * cell
        x1 = np.ceil((x1 + margin) / cell) * cell
        y1 = np.ceil((y1 + margin) / cell) * cell
        nx, ny = int(round((x1 - x0) / cell)), int(round((y1 - y0) / cell))
        rows.append(dict(uc_id=int(row.ID_UC_G0), stem=folder.name,
                         name=cities.fix_text(row.GC_UCN_MAI_2025),
                         country=cities.fix_text(row.GC_CNT_UNN_2025), iso3=folder.name.split('_')[1],
                         pop2025=float(row.GC_POP_TOT_2025), uc_area_km2=float(row.GC_UCA_KM2_2025),
                         lon0=round(lon, 6), lat0=round(lat, 6), x0=x0, y1=y1, nx=nx, ny=ny,
                         cell=cell, domain_km2=nx * ny * cell ** 2 / 1e6,
                         uc_wkt_laea=shapely.to_wkt(polygon, rounding_precision=1)))
    return pd.DataFrame(rows).sort_values('pop2025', ascending=False).reset_index(drop=True)


def prepare_settlement(folder, row, products, sub):
    target = cities.grid_of(row)
    patterns = {'pop': 'ghsl_resident_population_2025_*.tif',
                'vol': 'ghsl_total_building_volume_2025_*.tif',
                'vol_nres': 'ghsl_non_residential_building_volume_2025_*.tif',
                'height': 'ghsl_building_height_2018_*.tif'}
    for key in products:
        paths = sorted((folder / 'population').glob(patterns[key]))
        if not paths:
            raise FileNotFoundError(f'{folder.name}: missing raw {key} raster')
        output = np.zeros(target.shape, np.float64)
        for path in paths:
            with rasterio.open(path) as source:
                array = source.read(1)
                if key != 'height':
                    output = grid.resample_counts(array, source.transform.c, source.transform.f,
                                                  source.res[0], source.crs, target, out=output,
                                                  sub=sub, nodata=source.nodata)
                else:
                    xs, ys = target.centres()
                    x, y = np.meshgrid(xs, ys)
                    mx, my = Transformer.from_crs(target.crs, source.crs, always_xy=True).transform(x.ravel(), y.ravel())
                    rr, cc = map(np.asarray, rasterio.transform.rowcol(source.transform, mx, my))
                    inside = (rr >= 0) & (rr < source.height) & (cc >= 0) & (cc < source.width)
                    values = array[rr[inside], cc[inside]].astype(float)
                    if source.nodata is not None:
                        values = np.where(values == source.nodata, 0., values)
                    output.ravel()[np.flatnonzero(inside)] = np.maximum(values, 0.)
        path = configuration.ghsl_file(key, row['stem'])
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, output.astype(np.float32))


def water_coverage(reader, target):
    table = reader.extract('water', target.lonlat_bounds(0))
    pixels = np.zeros((target.ny * 4, target.nx * 4), np.uint8)
    if table is not None and table.num_rows:
        geometries = shapely.from_wkb(np.array(table['geometry'].to_pylist(), dtype=object))
        transform = Transformer.from_crs(4326, target.crs, always_xy=True)
        geometries = shapely.make_valid(shapely.transform(geometries,
                       lambda xy: np.column_stack(transform.transform(xy[:, 0], xy[:, 1]))))
        geometries = [item for item in shapely.intersection(geometries, shapely.box(*target.bounds()))
                      if not item.is_empty]
        if geometries:
            pixels = rasterize(((item, 1) for item in geometries), out_shape=pixels.shape,
                               transform=Affine(target.cell / 4, 0, target.x0, 0, -target.cell / 4, target.y1),
                               fill=0, dtype='uint8')
    return np.round(pixels.reshape(target.ny, 4, target.nx, 4).mean((1, 3)) * 100).astype(np.uint8)


def run_step(step, argv=None):
    parser = argparse.ArgumentParser(description=f'Stage 2 step {step}: prepare the supplied raw city subsets. '
                                                'Use --global-sources for the external-source interface.')
    parser.add_argument('--stems', nargs='*')
    parser.add_argument('--stems-file')
    parser.add_argument('--overwrite', action='store_true', help='accepted for compatibility; local subsets are always recomputed')
    if step == 2:
        parser.add_argument('--products', nargs='+', choices=['pop', 'vol', 'vol_nres', 'height'],
                            default=['pop', 'vol', 'vol_nres', 'height'])
        parser.add_argument('--sub', type=int, default=4)
    if step == 4:
        parser.add_argument('--strip-cells', type=int, default=500_000)
    args = parser.parse_args(argv)
    stems = list(args.stems or [])
    if args.stems_file:
        stems += Path(args.stems_file).read_text(encoding='utf-8-sig').split()
    folders = sorted(folder for folder in configuration.RAW_INPUTS.iterdir()
                     if folder.is_dir() and (not stems or folder.name in stems))
    missing = set(stems) - {folder.name for folder in folders}
    if missing or not folders:
        raise FileNotFoundError(f'Raw city folders not found: {sorted(missing) or configuration.RAW_INPUTS}')
    if step == 1:
        table = city_table(folders)
        if stems and configuration.CITY_TABLE.exists():
            existing = pd.read_csv(configuration.CITY_TABLE)
            table = pd.concat([existing[~existing.stem.isin(table.stem)], table], ignore_index=True)
            table = table.sort_values('pop2025', ascending=False).reset_index(drop=True)
        configuration.CITY_TABLE.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(configuration.CITY_TABLE, index=False)
        print(json.dumps({'step': 1, 'cities': len(folders), 'output': str(configuration.CITY_TABLE)}), flush=True)
        return
    table = cities.load_cities()
    selected = {folder.name for folder in folders}
    absent = selected - set(table.stem)
    if absent:
        raise ValueError(f'Run 01_create_city_grids.py first: {sorted(absent)}')
    records = []
    for row in table[table.stem.isin(selected)].to_dict('records'):
        started = time.time()
        stem = row['stem']
        folder = configuration.RAW_INPUTS / stem
        record = {'step': step, 'stem': stem, 'source': str(folder)}
        if step == 2:
            prepare_settlement(folder, row, args.products, args.sub)
            record['products'] = args.products
        elif step == 3:
            counts, stats = places.city_places(LocalPlaces(folder / 'places/overture_points_of_interest.parquet'), row)
            configuration.POI_OVERTURE.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(configuration.POI_OVERTURE / (stem + '.npz'), **counts)
            record['statistics'] = stats
        elif step == 4:
            entry = importlib.import_module('stage_2_100m_layers.04_prepare_building_floor_area')
            rules, mixed = buildings.load_rules()
            height = np.load(configuration.ghsl_file('height', stem))
            area, stats = entry.floor_area(row, LocalOverture(folder),
                          LocalBuildings(folder / 'buildings/open_building_map_buildings.parquet'),
                          height, rules, mixed, args.strip_cells or None)
            if not np.isfinite(area).all() or (area < 0).any():
                raise ValueError(f'{stem}: invalid floor area')
            configuration.FLOOR_AREA.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(configuration.FLOOR_AREA / (stem + '.npz'), fa=area)
            record['statistics'] = stats
            record['sources'] = ['Overture buildings', 'OpenBuildingMap occupancy and height',
                                 'GHSL building height', 'Overture land-use polygons']
        elif step == 5:
            from stage_2_100m_layers.building_sources.transportation import fetch
            target = cities.grid_of(row)
            reader = LocalOverture(folder)
            segments, stations = fetch(reader, target)
            if segments is None or not segments.num_rows:
                raise ValueError(f'{stem}: no raw road or rail features')
            graph = network.build_from_table(segments, stations, target)
            configuration.ROAD_GRAPHS.mkdir(parents=True, exist_ok=True)
            network.save_graph(configuration.ROAD_GRAPHS / (stem + '.npz'), graph,
                               {'stem': stem, 'overture_release': configuration.OVERTURE_RELEASE})
            configuration.WATER_COVERAGE_PERCENT.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(configuration.WATER_COVERAGE_PERCENT / (stem + '.npz'),
                                water=water_coverage(reader, target),
                                meta=json.dumps({'source': 'Overture water polygons', 'subcells': 4}))
        record['seconds'] = round(time.time() - started, 1)
        records.append(record)
        print(json.dumps(record), flush=True)
    metadata = configuration.INPUTS / 'preparation_metadata'
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / f'{step:02d}_source_processing.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
