"""Read city model-grid descriptors and construct grid objects."""
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
import stage_1_data_inputs.configuration as configuration
from stage_2_100m_layers.grid import Grid

def grid_of(row) -> Grid:
    return Grid(float(row["lon0"]), float(row["lat0"]), float(row["x0"]), float(row["y1"]), int(row["nx"]), int(row["ny"]),
                float(row.get("cell", 100.0)))


def uc_mask(row) -> np.ndarray:
    """Boolean mask of the 100 m cells whose centre lies inside the urban-centre polygon."""
    g = grid_of(row)
    poly = shapely.from_wkt(row["uc_wkt_laea"])
    xs, ys = g.centres()
    X, Y = np.meshgrid(xs, ys)
    m = shapely.contains_xy(poly, X.ravel(), Y.ravel())
    return m.reshape(g.shape)


def load_cities(path=None) -> pd.DataFrame:
    path = Path(path or configuration.CITY_TABLE)
    return pd.read_csv(path, encoding="utf-8-sig")
