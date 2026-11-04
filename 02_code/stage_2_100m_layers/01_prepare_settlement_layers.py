"""Stage 2, step 1: Resample raw GHSL city subsets onto the local model grids."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    from stage_2_100m_layers.local_raw_preparation import run_step
    return run_step(1,argv)

if __name__=='__main__':main()
