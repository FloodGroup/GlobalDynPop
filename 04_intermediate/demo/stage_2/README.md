# Stage 2: 100 m layers

| Directory | Model quantity | Units and format |
|---|---|---|
| `local_grids/` | Local grid | City CSV: CRS, grid origin, extent, cell size and urban-centre geometry |
| `resident_population/` | Residents N | NPY: people per 100 m cell |
| `buildings/floor_area_by_use/` | Floor area F_c | NPZ `fa`, shape `(9, ny, nx)`, m2 |
| `point_of_interest_counts/` | Classified place counts before smoothing | NPZ counts per cell by source/activity code |
| `smoothed_places/` | Places Pi_c | NPZ: Gaussian-smoothed counts per cell, proportional to density on the fixed grid |
| `distance_decay_kernels/` | Kernels f_c | Per-city JSON: effective kernel form, kappa, beta, offset, radius and routing-zone size |
| `road_and_rail_graphs/` | Network graph | NPZ: topology, travel times, stations and grid sampling |
| `hourly_location_shares/` | Shares s_c | CSV: seven location shares per local hour, by country/day type |
| `allocation_parameters/` | Adopted kernel and attractiveness settings | JSON and parameter guide |
| `buildings/` supporting layers | Building height and volume | Metres for height; m3 for total/non-residential volumes |
| `water_coverage_percent/` | Water coverage for functional land use | NPZ key `water`, uint8 percent from 0 to 100 |

The derivation of the hourly location shares is documented in [time_use.md](../../time_use.md).

Activity-specific place layers use keys such as `C2_workday` and `C2_restday`; their source selection and smoothing follow the effective settings for that city/day type. The kernel JSON represents the function used in allocation rather than a saved two-dimensional convolution matrix.

Floor-area indices 0-6 are C1-C7, index 7 is unknown use, and index 8 is industrial floor area already included in C2. Do not add the industrial subset again when calculating total floor area. Routing coordinates and lengths are metres; `p_time` is hours. City-table population refers to the urban centre, whereas N covers the larger model domain.

The spatial layers are regenerated from `01_inputs/demo/raw/` by Stage 2 programs 01 through 05; step 06 saves smoothed places and kernel settings. Hourly location shares and calibrated allocation settings are supplied study products. Survey harmonisation and calibration are separate upstream tasks. See [Stage 2 programs](../../../02_code/stage_2_100m_layers/README.md).
