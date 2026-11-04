# Outdoor micro-environments of the time away from home (model)

Used by the outdoor pool of the destination layers (`02_code/stage_3_activity_allocation/model.py`, `_two_pool_destinations`; parameters
`04_intermediate/demo/stage_2/allocation_parameters/population_allocation_parameters.json`, key `outdoor_pool` of every activity class).

## Source

Glen, G. & Shadwick, D. (1998). *Final Technical Report: Analysis of Carbon Monoxide Exposure for Fourteen Cities
using HAPEM-MS3.* ManTech Environmental Technology, Inc., Research Triangle Park, NC, for the U.S. Environmental
Protection Agency, March 1998. Appendix A, "HAPEM-MS3 Microenvironmental Concentration and Duration by Calendar
Quarter and Annually for 1990" (Baltimore, city-wide, by demographic group).
Archived copy: https://webarchive.library.unt.edu/eot2008/20081105055914/http:/epa.gov/otaq/regs/toxics/hapem-co/e-mecd.pdf

HAPEM-MS3 (Hazardous Air Pollutant Exposure Model for Mobile Sources, version 3) simulates a year of activity
patterns of every demographic group and reports the hours spent in each micro-environment. Its outdoor
micro-environments are: parking lot, roadway (near a road), construction site, residential grounds, school
grounds, sports arena, park or golf course, and other outdoor locations.

## Files

`hapem_ms3_baltimore_outdoor_hours.csv`: annual hours (1990) in each outdoor micro-environment for the nine
demographic groups of the report (working and non-working men and women aged 18-44 and 45-64, children 0-17).

`outdoor_away_shares.csv`: share of the outdoor time away from home in each micro-environment. Residential grounds
(the time in the own yard) are left out, because the pools hold the people away from home only; the hours of the
groups are summed without weights:

| group used              | groups summed                              | used for                                     |
|-------------------------|--------------------------------------------|----------------------------------------------|
| working adults 18-64    | the four groups of working men and women   | work and commerce (C2)                       |
| adults 18-64            | all eight adult groups                     | services (C4), leisure (C5), other (C7); education (C3) where no school or campus grounds are mapped near the destinations |
| children 0-17           | children                                   | not used (education uses the school and campus grounds, `campus` = 1) |

## Micro-environment -> open space of the cells (three groups)

The open space of every cell is mapped by type (`01_inputs/basemap/open_space`, 10_prepare_buildings_open_space.py) and the
outdoor pool uses three groups of these types, each with the summed shares of its micro-environments:

| group (parameter key)  | open-space types of the cells | HAPEM-MS3 micro-environments | share, working adults / all adults |
|---|---|---|---|
| `street`                      | walkable street surface (road length x width: primary/secondary 20 m, tertiary/unclassified 12 m, local 8 m; motorways excluded) | roadway | 0.5755 / 0.5688 |
| `park+grass+rec+plaza`        | parks and gardens, managed grass, sports and recreation grounds, squares and pedestrian areas | park / golf course, sports arena | 0.1140 / 0.1244 |
| `parking+campus+cons+open`    | parking lots, school and hospital grounds, construction sites, other open land outside buildings, farmland and protected areas | parking lot, school grounds, construction, other | 0.3105 / 0.3068 |

Within a group the share is spread in proportion to the area of its types (Gaussian weight of the distance to the indoor
destinations, 300 m). Education uses the school and campus grounds (`campus` = 1; the adult shares where none are mapped
near the destinations). For leisure and other activities half of the outdoor pool goes to parks, sports grounds and
squares anywhere in the domain (`free`, `free_share` = 0.5).

The three groups were chosen by validation: nine separate types and the three groups give the same
agreement with the observations (Tier A medians within 0.002, same grades), and both agree better than an outdoor pool
without types (the open space outside the building footprints, untyped outdoor scheme).

## Limitations

The shares describe one U.S. metropolitan area in 1990 and are applied to every city; they set only how the outdoor
part of the time away from home (weight 1 - W_indoor of the city, 01_inputs/time_use/w_indoor) is spread over the
open space near the destinations, not how many people are outdoors.
