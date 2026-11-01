# Stage 3: Allocation of daily activities

| Directory | Quantity | Content |
|---|---|---|
| `destination_attractiveness/` | A_c | Dimensionless destination weights after the configured attractiveness exponent, by class/day type |
| `destination_population/` | D_c | Destination allocations in people per cell, saved at computation precision before GeoTIFF encoding |
| `in_transit_population/` | T | Workday/rest-day road and rail assignment, normalised to the model-domain population |
| `logs/` | Execution diagnostics | Per-city completion and error records |

Attractiveness and destination NPZ files use activity codes C2, C3, C4, C5 and C7 with `_workday` and `_restday` suffixes. The transit archive uses `T_workday` and `T_restday`; street lengths and assignment statistics are supporting fields. Attractiveness weights need not sum to one after exponentiation. Destination and normalised transit population each represent the domain population.

The [Stage 3 programs](../../../02_code/stage_3_activity_allocation/README.md) calculate these results. Final multi-band component GeoTIFFs containing N, D_c and T are packaged under `05_outputs/demo/population_components/`, and are read by the hourly writer.
