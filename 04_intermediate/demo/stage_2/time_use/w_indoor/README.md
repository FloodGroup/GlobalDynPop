# Share of the day spent inside buildings (W_indoor)

`w_indoor_cities.csv` gives W_indoor for each of the 1,904 cities. Columns:

| Column | Meaning |
|---|---|
| stem | city identifier |
| iso3 | country code of the city table |
| w_indoor | share of the 24-hour day spent inside buildings (0-1) |
| assignment | how the value was assigned (see below) |
| reference | country or province whose value is used |
| source_id | source(s) in `w_indoor_sources.csv` |
| koppen | Koppen-Geiger class at the urban centre (Beck et al. 2023) |
| gni_usd | GNI per capita of the country (World Bank Atlas method, US$) |

The model uses W_indoor only for activities away from home (work, education, services, leisure, other).
A share W_indoor of their destinations is placed in buildings and at points of interest, using the building and POI destination layer.
The rest, 1 - W_indoor, is placed on the open space of the urban fabric near those destinations; half of it goes to
outdoor recreation land for leisure and other activities. Permanent water never receives people.

## How the values are assigned

1. China: the provincial median of daily indoor time of adults, from the Chinese Exposure Factors Handbook
   (survey 2011-2012; Duan et al. 2015), divided by 1,440 min. The province is found from the urban centre.
   Hong Kong uses its own survey. Cities in provinces without a value in the handbook table take the mean of the
   adjacent provinces; island provinces take the nearest province across the strait.
2. Other countries with an adopted source: the value of that source (`w_indoor_sources.csv`, status "adopted").
3. All other countries: the reference rule used for the time-use references.
   - References are first restricted by income: GNI per capita within a factor of 2, then 3, then 5, then any.
   - Within an income tier, a reference in the same UN sub-region is preferred, then one on the same continent.
     The 15 former Soviet republics count as one sub-region.
   - Ties are broken by the evidence grade of the source, then by the closest GNI, then by the same Koppen-Geiger
     main class.
   - The references ranked equally with the best one (same income tier, same geographic level, same evidence grade)
     are averaged, at most three of them. In the last, unbounded income tier only the best reference is used.

`w_indoor_sources.csv` lists every source reviewed: 40 adopted and 25 reviewed but not used, with the reason.
`w_indoor_china_provinces.csv` gives the provincial values of China.
`sensitivity/` holds three alternative tables:
- `w_indoor_cities_single_donor.csv`: alternative assignment using one donor with the same climate and the closest GNI.
- `w_indoor_cities_minus005.csv`: all values minus 0.05.
- `w_indoor_cities_plus005.csv`: all values plus 0.05.

Select a table with the environment variable GDP_WINDOOR.
