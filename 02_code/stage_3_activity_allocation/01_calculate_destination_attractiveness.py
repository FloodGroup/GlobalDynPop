"""Save destination attractiveness for the selected cities."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stage_3_activity_allocation.destination_attractiveness import save_destination_attractiveness
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stems",nargs="*")
    args=parser.parse_args()
    save_destination_attractiveness(args.stems)
