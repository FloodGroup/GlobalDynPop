"""Define city domains and write the shared Stage 1 grid table."""
from pathlib import Path
import re
import numpy as np
import pandas as pd
import pyogrio
import shapely
from pyproj import CRS, Transformer
from stage_1_data_inputs import configuration

def fix_text(value):
    if not isinstance(value, str):
        return ''
    try:
        return value.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def city_record(source, stem):
    """Define the Stage 1 extraction domain and 100 m model-grid descriptor."""
    if len(source) != 1:
        raise ValueError(f'{stem}: expected one urban-centre feature')
    row = source.iloc[0]
    geometry = row.geometry
    centre = shapely.centroid(geometry)
    lon, lat = Transformer.from_crs(source.crs, 4326, always_xy=True).transform(centre.x, centre.y)
    crs = CRS.from_proj4(f'+proj=laea +lat_0={lat:.6f} +lon_0={lon:.6f} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs')
    transform = Transformer.from_crs(source.crs, crs, always_xy=True)
    polygon = shapely.transform(shapely.segmentize(geometry, 200.),
                                lambda xy: np.column_stack(transform.transform(xy[:, 0], xy[:, 1])))
    x0, y0, x1, y1 = polygon.bounds
    cell, margin = configuration.CELL, configuration.BUFFER_M
    x0 = np.floor((x0 - margin) / cell) * cell
    y0 = np.floor((y0 - margin) / cell) * cell
    x1 = np.ceil((x1 + margin) / cell) * cell
    y1 = np.ceil((y1 + margin) / cell) * cell
    nx, ny = int(round((x1 - x0) / cell)), int(round((y1 - y0) / cell))
    return dict(uc_id=int(row.ID_UC_G0), stem=stem,
                name=fix_text(row.GC_UCN_MAI_2025), country=fix_text(row.GC_CNT_UNN_2025),
                iso3=stem.split('_')[1], pop2025=float(row.GC_POP_TOT_2025),
                uc_area_km2=float(row.GC_UCA_KM2_2025), lon0=round(lon, 6), lat0=round(lat, 6),
                x0=x0, y1=y1, nx=nx, ny=ny, cell=cell, domain_km2=nx * ny * cell ** 2 / 1e6,
                uc_wkt_laea=shapely.to_wkt(polygon, rounding_precision=1))


def select_urban_centres(path, city_ids):
    source = pyogrio.read_dataframe(path, layer=configuration.UCDB_LAYER)
    source = source[source.ID_UC_G0.astype(int).isin(city_ids)]
    missing = set(city_ids) - set(source.ID_UC_G0.astype(int))
    if missing:
        raise ValueError(f'Urban-centre IDs not found: {sorted(missing)}')
    if source.GC_POP_TOT_2025.astype(float).lt(configuration.POP_MIN).any():
        raise ValueError('Selected urban centres must have at least 300,000 residents in 2025')
    return source


def source_city_table(source):
    from unidecode import unidecode
    import country_converter
    rows = []
    for index, feature in source.iterrows():
        country = fix_text(feature.GC_CNT_UNN_2025)
        iso = 'TWN' if country == 'China, Taiwan Province of China' else country_converter.convert(country, to='ISO3')
        if not isinstance(iso, str) or len(iso) != 3:
            raise ValueError(f'Cannot resolve ISO3 for {country}')
        name = re.sub(r'[^A-Za-z0-9]+', '_', unidecode(fix_text(feature.GC_UCN_MAI_2025))).strip('_')[:40] or 'UC'
        stem = f'{int(feature.ID_UC_G0):05d}_{iso}_{name}'
        rows.append(city_record(source.loc[[index]], stem))
    return pd.DataFrame(rows).sort_values('pop2025', ascending=False).reset_index(drop=True)


def raw_city_table(raw, stems=None):
    raw = Path(raw)
    folders = sorted(p for p in raw.iterdir() if p.is_dir()
                     and (p/'urban_centres/urban_centre_boundary.gpkg').is_file()
                     and (not stems or p.name in stems))
    missing = set(stems or []) - {p.name for p in folders}
    if missing or not folders:
        raise FileNotFoundError(f'Urban-centre boundary subsets not found: {sorted(missing) or raw}')
    rows = [city_record(pyogrio.read_dataframe(p/'urban_centres/urban_centre_boundary.gpkg',
                        layer=configuration.UCDB_LAYER), p.name) for p in folders]
    return pd.DataFrame(rows).sort_values('pop2025', ascending=False).reset_index(drop=True)


def write_city_table(table, output=None, merge=False):
    output = Path(output or configuration.CITY_TABLE)
    if output.exists():
        existing = pd.read_csv(output)
        # Preserve descriptive fields that do not enter the grid calculation.
        for column in existing.columns.difference(table.columns):
            table[column] = table.stem.map(existing.set_index('stem')[column])
        if merge:
            table = pd.concat([existing[~existing.stem.isin(table.stem)], table], ignore_index=True)
            table = table.sort_values('pop2025', ascending=False).reset_index(drop=True)
        table = table.reindex(columns=list(existing.columns)+[c for c in table if c not in existing])
    if table.stem.duplicated().any():
        raise ValueError('Duplicate city identifiers in grid table')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.csv.tmp')
    table.to_csv(temporary, index=False)
    temporary.replace(output)
    return output
