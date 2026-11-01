"""Save destination-attractiveness arrays for each activity and day type."""
import json
import numpy as np
from scipy.ndimage import gaussian_filter
import stage_1_data_inputs.configuration as configuration
import stage_3_activity_allocation.model as model
import stage_3_activity_allocation.network as network
from stage_2_100m_layers.cities import load_cities, grid_of
CLASSES = ('C2', 'C3', 'C4', 'C5', 'C7')

def save_destination_attractiveness(stems=None):
    stage = 3
    params = model.params_from(json.loads(configuration.MODEL_PARAMS.read_text()))
    cities = load_cities()
    if stems:
        cities = cities[cities.stem.isin(stems)]
    for row in cities.to_dict('records'):
        stem = row['stem']
        N, V, P = model.load_layers(stem)
        layers = {}
        kernels = {}
        for dt in ('workday', 'restday'):
            q = params.for_country(row['iso3']).for_daytype(dt)
            kernels[dt] = {}
            for c in CLASSES:
                ac = q.c7_like if c == 'C7' else c
                spec = q.attractor[c]
                layers[c + '_' + dt] = model.attractor(spec, ac, V, P)
                kernels[dt][c] = {'kind': q.k(c), 'kappa_m': float(q.d0[c]), 'beta': float(q.beta.get(c, 1.0)), 'distance_offset_m': 250.0, 'radius_m': min(q.radius_factor * q.d0[c], q.max_radius_m) if q.k(c) == 'pow' else q.radius_factor * q.d0[c]}
        folder = configuration.STAGE3 / 'destination_attractiveness'
        folder.mkdir(parents=True, exist_ok=True)
        assert all((a.shape == N.shape and np.isfinite(a).all() and (a >= 0).all() for a in layers.values()))
        dest = folder / (stem + '.npz')
        tmp = dest.with_suffix('.tmp.npz')
        np.savez_compressed(tmp, **layers)
        tmp.replace(dest)
        print(json.dumps({'stage': stage, 'stem': stem, 'layers_written': len(layers)}), flush=True)
