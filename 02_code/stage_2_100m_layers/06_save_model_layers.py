"""Save smoothed place layers and kernel settings for the selected cities."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stage_2_100m_layers.model_layer_exports import save_model_layers
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stems",nargs="*")
    args=parser.parse_args()
    save_model_layers(args.stems)
