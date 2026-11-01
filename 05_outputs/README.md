# Output dictionary

[Population maps](../06_docs/figures/demo_population_distributions.png) compare the three cities at 03:00-04:00, 08:00-09:00 and 13:00-14:00 on one page, using a separate population legend for each city, fixed across that city's workday and rest-day maps. The 360 dpi PNG is stored in `06_docs/figures/`.

## Hourly population

`demo/hourly_population/<stem>/<daytype>/<stem>_<daytype>_hour_<HH>.tif` contains one float32 band for one local hour, with `<HH>` from `00` to `23`. Each city has 24 files under `workday/` and 24 under `rest_day/`. Values are people per 100 m cell. The `restday` model identifier maps to the `rest_day` directory and filename. `demo/hourly_population_index.csv` records one row per city, day type and hour, with the file path, interval, units and domain population. Each city uses its own Lambert azimuthal equal-area CRS stored in the raster. Inspect CRS, affine transform, extent, NoData and masks before comparing outputs.

Hourly population files use lossless DEFLATE compression of the calculated float32 values, without additional decimal rounding. The component rasters use LERC-ZSTD with an absolute error setting of 0.001 people per cell, or a DEFLATE fallback rounded to 0.001. Domain totals are conserved by the model; stored component values and floating-point arithmetic can introduce small numerical differences.

Land-use classification is a single uint8 band with 13 categories; its detail raster has 16 bands: nine floor-area categories (m²), three groups of road length (m), other street length (m), rail length (m), water percentage and station count. Check the actual band descriptions. The original classification rules are in 02_code/stage_4_outputs/02_classify_functional_land_use.py; these are proxy land-use classes, not ground-truth land cover.

## Land-use files

The three cities' land-use classification and 16-band detail rasters are under `demo/functional_land_use/<city>/`. `demo/functional_land_use/functional_land_use_index.csv` summarises their areas and source availability. See [Stage 4](../02_code/stage_4_outputs/README.md) for all 13 classes, band units, source layers and classification thresholds. These are model-derived functional classes; the original source polygons are under `01_inputs/demo/raw/<city>/supporting_land_features/overture_land_use_polygons.parquet`.
