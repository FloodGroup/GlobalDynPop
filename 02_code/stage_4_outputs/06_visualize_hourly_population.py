"""Draw a one-page comparison of population at 03, 08 and 13 local time.

Each city uses its own continuous colour scale, fixed over hours and day types. The numerical
rasters are displayed at their native grid spacing without spatial smoothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import ListedColormap, LinearSegmentedColormap, LogNorm
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator
import numpy as np
import pandas as pd
import rasterio

HOURS=(3,8,13)
DAYTYPES=(("workday","Workday"),("rest_day","Rest day"))
UPPER_PERCENTILE=99.5
COLOR_STOPS=((0.0,"#F1EFF6"),(.2,"#C0B5DE"),(.4,"#9481C5"),(.6,"#7654AA"),(.8,"#B14B8A"),(.93,"#D94E57"),(1.0,"#F47C45"))
WIDTH,HEIGHT=420,297
MM=1/25.4


def style():
    folder=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"
    for filename in ("times.ttf","timesbd.ttf","timesi.ttf","timesbi.ttf"):
        if (folder/filename).exists():fm.fontManager.addfont(str(folder/filename))
    plt.rcParams.update({"font.family":"serif","font.serif":["Times New Roman","Liberation Serif","DejaVu Serif"],
        "font.size":16,"axes.titlesize":17,"text.color":"#20252B","axes.labelcolor":"#20252B",
        "xtick.color":"#50575E","ytick.color":"#50575E","axes.edgecolor":"#AEB6BF",
        "pdf.fonttype":42,"axes.linewidth":.6,"savefig.dpi":360})


def axes(fig,x,y,width,height):
    return fig.add_axes([x/WIDTH,1-(y+height)/HEIGHT,width/WIDTH,height/HEIGHT])


def scalebar(ax,extent):
    x0,x1,y0,y1=extent
    length=max(v for v in (.5,1,2,5,10,20) if v*1000 <= (x1-x0)*.24)*1000
    x=x0+.055*(x1-x0);y=y0+.065*(y1-y0)
    ax.plot([x,x+length],[y,y],color="#20252B",lw=1.1,zorder=4)
    ax.text(x+length/2,y+.03*(y1-y0),f"{length/1000:g} km",ha="center",va="bottom",fontsize=16,
        bbox=dict(facecolor="white",edgecolor="none",pad=.7,alpha=.85),zorder=5)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(os.environ.get("DYNAMIC_POPULATION_ROOT",Path(__file__).resolve().parents[2])))
    parser.add_argument("--hourly",type=Path)
    parser.add_argument("--stage2",type=Path)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--stems",nargs="*")
    args=parser.parse_args(argv)
    root=args.root
    hourly=args.hourly or Path(os.environ.get("DYNAMIC_POPULATION_HOURLY",str(root/"05_outputs/demo/hourly_population")))
    stage2=args.stage2 or Path(os.environ.get("DYNAMIC_POPULATION_STAGE2",str(root/"04_intermediate/demo/stage_2")))
    out=args.out or Path(os.environ.get("DYNAMIC_POPULATION_FIGURES",str(root/"06_docs/figures")))
    cities=pd.read_csv(stage2/"local_grids/city_grid_definitions.csv").set_index("stem")
    stems=args.stems or sorted(cities.index)
    if not 1<=len(stems)<=3:raise ValueError("Select one to three cities for the one-page layout")
    out.mkdir(parents=True,exist_ok=True)
    style()
    figure=plt.figure(figsize=(WIDTH*MM,HEIGHT*MM))
    figure.text(14/WIDTH,1-12/HEIGHT,"GlobalDynPop-100m | Hourly population",fontsize=26,weight="bold")
    figure.text(406/WIDTH,1-12/HEIGHT,"100 m grids | Local time",fontsize=16,ha="right",color="#50575E")
    figure.text(14/WIDTH,1-21/HEIGHT,"People per 100 m cell | City-specific logarithmic scales",fontsize=16)
    for day_index,(_,label) in enumerate(DAYTYPES):
        x0=36+day_index*188
        figure.text((x0+91)/WIDTH,1-31/HEIGHT,label,ha="center",fontsize=17,weight="bold")
        figure.add_artist(plt.Line2D([x0/WIDTH,(x0+184)/WIDTH],[1-34/HEIGHT]*2,transform=figure.transFigure,color="#AEB6BF",lw=.6))
    cmap=LinearSegmentedColormap.from_list("population_continuous",COLOR_STOPS,N=1024)
    cmap.set_under((1,1,1,0));cmap.set_bad((1,1,1,0))
    metadata={"hours":list(HOURS),"daytypes":[x[0] for x in DAYTYPES],"time_basis":"local time",
        "population_scale":{"type":"continuous logarithmic","upper_percentile":UPPER_PERCENTILE,"upper_rounding":"up to next 10 people",
                            "color_stops":list(COLOR_STOPS),"below_3":"transparent","fixed_within_each_city":True,"shared_across_cities":False},
        "city_scales":{},
        "spatial_smoothing":"none","inputs":[],"font":fm.findfont("Times New Roman"),"output_format":"png","dpi":360}
    for row_number,stem in enumerate(stems):
        city=cities.loc[stem]
        name={"05685_JPN_Takasaki_Maebashi":"Takasaki-\nMaebashi"}.get(stem,city['name'])
        y=42+row_number*73
        figure.text(18.5/WIDTH,1-(y+28)/HEIGHT,f"{name}\n{city['country']}",ha="center",va="center",fontsize=18,weight="bold")
        city_values=[]
        for day,_ in DAYTYPES:
            for hour in HOURS:
                path=hourly/stem/day/f"{stem}_{day}_hour_{hour:02d}.tif"
                with rasterio.open(path) as source:values=source.read(1)
                city_values.append(values[values>=3])
        pooled=np.concatenate(city_values)
        upper_percentile=float(np.percentile(pooled,UPPER_PERCENTILE))
        vmax=max(10.0,float(np.ceil(upper_percentile/10.0)*10.0))
        norm=LogNorm(vmin=3,vmax=vmax,clip=False)
        red_threshold=float(norm.inverse(.93))
        metadata['city_scales'][stem]={'minimum':3.0,'maximum':vmax,'percentile_99_5':upper_percentile,
                                     'red_threshold':red_threshold,'fraction_at_or_above_red_threshold':float(np.mean(pooled>=red_threshold)),
                                     'fraction_above_upper_limit':float(np.mean(pooled>vmax)),
                                     'pooled_maps':6,'visible_cells':int(pooled.size)}
        reference=None;water=None
        waterpath=stage2/f"water_coverage_percent/{stem}.npz"
        if waterpath.exists():
            with np.load(waterpath) as z:water=z['water']
        for day_index,(day,_) in enumerate(DAYTYPES):
            for column,hour in enumerate(HOURS):
                path=hourly/stem/day/f"{stem}_{day}_hour_{hour:02d}.tif"
                with rasterio.open(path) as source:
                    if source.count!=1 or source.descriptions!=(f"hour_{hour:02d}",):raise ValueError(f"Unexpected layout: {path}")
                    signature=(source.width,source.height,source.crs,source.transform)
                    if reference is None:reference=signature
                    elif reference!=signature:raise ValueError(f"Grid mismatch: {path}")
                    values=source.read(1)
                    extent=(source.bounds.left,source.bounds.right,source.bounds.bottom,source.bounds.top)
                if not np.isfinite(values).all() or (values<0).any():raise ValueError(f"Invalid values: {path}")
                ax=axes(figure,36+day_index*188+column*62,y,60,51)
                if water is not None:
                    if water.shape!=values.shape:raise ValueError(f"Water grid mismatch: {stem}")
                    ax.imshow(np.ma.masked_where(water<50,water),extent=extent,interpolation="nearest",
                        cmap=ListedColormap(["#E6EDF0"]),vmin=50,vmax=100)
                ax.imshow(values,extent=extent,cmap=cmap,norm=norm,interpolation="nearest")
                ax.set_title(f"{hour:02d}:00-{hour+1:02d}:00",pad=4)
                ax.set_xticks([]);ax.set_yticks([])
                for spine in ax.spines.values():spine.set_color("#AEB6BF");spine.set_linewidth(.6)
                if day_index==0 and column==0:scalebar(ax,extent)
                metadata["inputs"].append({"file":f"hourly_population/{stem}/{day}/{path.name}","sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
        # One continuous scale per city, shared by its six panels.
        legend=axes(figure,85,y+54,285,3)
        colorbar=figure.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=legend,orientation="horizontal",extend="max")
        ticks=[v for v in (3,5,10,20,50,100,200,500,1000) if v<=vmax]
        if ticks[-1]!=vmax:
            if vmax/ticks[-1] < 1.35:ticks.pop()
            ticks.append(vmax)
        colorbar.ax.xaxis.set_major_locator(FixedLocator(ticks))
        colorbar.ax.xaxis.set_major_formatter(FixedFormatter([f"{v:g}" for v in ticks]))
        colorbar.ax.xaxis.set_minor_locator(NullLocator())
        colorbar.ax.tick_params(labelsize=16,length=2,width=.4,pad=3)
        colorbar.outline.set_linewidth(.4)
    figure.text(14/WIDTH,1-272/HEIGHT,"Note: Each city uses a separate logarithmic scale; cells below three people are hidden, and pale blue-grey indicates water.",
                 ha="left",va="top",fontsize=16)
    figure.canvas.draw()
    renderer=figure.canvas.get_renderer()
    for text_item in figure.findobj(matplotlib.text.Text):
        if not text_item.get_visible() or not text_item.get_text():
            continue
        box=text_item.get_window_extent(renderer)
        if box.x0 < -1 or box.y0 < -1 or box.x1 > figure.bbox.width+1 or box.y1 > figure.bbox.height+1:
            raise ValueError("Text outside figure: "+text_item.get_text())
    figure.savefig(out/"demo_population_distributions.png",dpi=360)
    plt.close(figure)
    (out/"population_visualization_metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps({"png":str(out/"demo_population_distributions.png"),"panels":len(metadata['inputs'])}),flush=True)


if __name__=="__main__":main()
