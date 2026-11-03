"""Extract city source records and native raster windows before model preprocessing."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main(argv=None):
    from stage_1_data_inputs import configuration
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urban-centres',type=Path,required=True,help='Original GHS-UCDB GeoPackage')
    parser.add_argument('--city-ids',type=int,nargs='+',required=True,help='GHS-UCDB ID_UC_G0 values')
    parser.add_argument('--overture-index',type=Path,required=True,help='Row-group index for Overture spatial layers')
    parser.add_argument('--places-index',type=Path,required=True,help='Row-group index for Overture Places')
    parser.add_argument('--building-index',type=Path,required=True,help='OpenBuildingMap row-group index')
    parser.add_argument('--raster-cache',type=Path,required=True,help='Native GHSL tile cache; missing tiles are downloaded')
    parser.add_argument('--build-missing-indexes',action='store_true',help='Build absent indexes from public source Parquet footers; requires source-release access')
    parser.add_argument('--output',type=Path,default=configuration.RAW_INPUTS,help='Raw-data directory inside the repository root')
    parser.add_argument('--offline',action='store_true',help='Require every GHSL tile to be cached; use local Parquet paths in the indexes for a fully offline extraction')
    parser.add_argument('--overwrite',action='store_true',help='Replace an existing raw-data directory')
    args=parser.parse_args(argv)
    from stage_1_data_inputs.source_preparation import prepare
    print({'raw_source_files_written':prepare(args)})

if __name__=='__main__':main()
