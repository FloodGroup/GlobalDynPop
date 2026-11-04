"""Stage 1: define local 100 m grids before source extraction or spatial processing."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    from stage_1_data_inputs import configuration
    from stage_1_data_inputs.city_definitions import (raw_city_table, select_urban_centres,
                                                     source_city_table, write_city_table)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urban-centres', type=Path, help='Original GHS-UCDB GeoPackage; otherwise use local boundary subsets')
    parser.add_argument('--city-ids', type=int, nargs='+')
    parser.add_argument('--raw', type=Path, default=configuration.RAW_INPUTS)
    parser.add_argument('--stems', nargs='+')
    parser.add_argument('--stems-file', type=Path)
    parser.add_argument('--output', type=Path, default=configuration.CITY_TABLE)
    args = parser.parse_args(argv)
    stems = list(args.stems or [])
    if args.stems_file:
        stems += args.stems_file.read_text(encoding='utf-8-sig').split()
    if bool(args.urban_centres) != bool(args.city_ids):
        parser.error('--urban-centres and --city-ids must be supplied together')
    if args.urban_centres and stems:
        parser.error('Use --city-ids with the original database, or --stems with local subsets')
    table = (source_city_table(select_urban_centres(args.urban_centres, args.city_ids))
             if args.urban_centres else raw_city_table(args.raw, stems))
    output = write_city_table(table, args.output, merge=bool(stems or args.city_ids))
    print(json.dumps({'stage': 1, 'cities': len(table), 'output': str(output)}), flush=True)


if __name__ == '__main__': main()
