"""Stage 2, step 5: Build routing graphs and water coverage from raw transport and water records."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    from stage_2_100m_layers.local_raw_preparation import run_step
    return run_step(5,argv)

if __name__=='__main__':main()
