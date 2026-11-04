# Stage 1: City grid definitions

`local_grids/city_grid_definitions.csv` defines the shared spatial domain before data extraction and processing. Each row records the city identifier, geographic projection centre (`lon0`, `lat0`), projected grid origin (`x0`, `y1`, metres), dimensions (`nx`, `ny`), cell size (`cell`, metres), domain area and urban-centre geometry in the local equal-area projection.

The grid uses 100 m cells and a 10 km margin around the urban-centre bounding box. The projection is reconstructed as Lambert azimuthal equal-area from its centre. Coordinates and dimensions are used by Stages 2–4 without redefining the grid.

Generate the table with [00_create_city_grids.py](../../../02_code/stage_1_data_inputs/00_create_city_grids.py) from the original urban-centre database or the bundled boundary subsets. The [method guide](../../../06_docs/methods/stage_1_data_inputs.md) explains domain construction.
