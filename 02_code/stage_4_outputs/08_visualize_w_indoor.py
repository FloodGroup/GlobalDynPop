"""Render three consistent maps from bundled figure data. No model fitting or parameter edits.
Requires numpy, pandas, matplotlib, cartopy and shapely.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize, ListedColormap
from matplotlib.patches import Patch
from matplotlib.ticker import NullLocator, FuncFormatter
import cartopy.crs as ccrs
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[2]
FIG=ROOT/'06_docs/figures'
DATA=ROOT/'04_intermediate/figure_data/w_indoor'
PDF=ROOT/'05_outputs/figure_exports'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.labelcolor':'#334956',
 'text.color':'#203744','pdf.fonttype':42,'ps.fonttype':42,'savefig.dpi':300})
features=json.loads((DATA/'world_countries.geojson').read_text(encoding='utf-8'))['features']
countries=[(f['properties']['iso3'],shape(f['geometry'])) for f in features if f['geometry']]
land=unary_union([g for _,g in countries])
blue=LinearSegmentedColormap.from_list('shared_blues',['#e6f1f6','#56B4E9','#0072B2','#003b60'])
proj=ccrs.EqualEarth()
geo=ccrs.PlateCarree()

def canvas(title,subtitle):
    fig=plt.figure(figsize=(11,6.6),facecolor='white')
    ax=fig.add_axes([.02,.145,.96,.755],projection=proj)
    ax.set_global()
    ax.set_facecolor('#f6f8fa')
    ax.spines['geo'].set_edgecolor('#cbd5db');ax.spines['geo'].set_linewidth(.6)
    ax.gridlines(crs=geo,xlocs=np.arange(-120,180,60),ylocs=np.arange(-60,90,30),
                 color='#bdcbd3',linewidth=.35,alpha=.55,zorder=0)
    fig.text(.025,.99,title,fontsize=24,fontweight='bold',va='top')
    fig.text(.025,.934,subtitle,fontsize=12.5,color='#627581',va='top')
    return fig,ax

def finish(fig,name,foot):
    fig.text(.025,.009,foot,fontsize=9.5,color='#627581')
    fig.savefig(FIG/f'{name}.png',dpi=300,facecolor='white')
    PDF.mkdir(parents=True,exist_ok=True)
    fig.savefig(PDF/f'{name}.pdf',facecolor='white')
    plt.close(fig)

def bar(fig,norm,label,ticks,formatter):
    ca=fig.add_axes([.28,.108,.44,.017])
    cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=blue),cax=ca,orientation='horizontal',ticks=ticks)
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0,pad=3,labelsize=12)
    cb.ax.xaxis.set_minor_locator(NullLocator())
    cb.ax.xaxis.set_major_formatter(FuncFormatter(formatter))
    cb.set_label(label,labelpad=4,fontsize=12)

def indoor():
    d=pd.read_csv(DATA/'city_map_data.csv').sort_values('stem')
    fig,ax=canvas('Time spent indoors','Adopted parameters at 1,904 urban centres')
    ax.add_geometries([land],geo,facecolor='#e4e9ed',edgecolor='#bac7cf',linewidth=.35,zorder=1)
    norm=Normalize(.75,.95)
    ax.scatter(d.lon0,d.lat0,c=d.w_indoor,s=10,cmap=blue,norm=norm,transform=geo,
               edgecolors='#ffffff',linewidths=.17,alpha=1,zorder=3)
    bar(fig,norm,'Share of the 24-hour day spent indoors',[.75,.80,.85,.90,.95],lambda x,p:f'{x:.0%}')
    finish(fig,'w_indoor_global','Source: GlobalDynPop city parameters; Global Human Settlement Layer urban centres.  •  Equal Earth projection')

def income():
    d=pd.read_csv(DATA/'income_map_data.csv')
    lookup=d.set_index('iso3').gni_atlas_usd.to_dict()
    valid=d.gni_atlas_usd.dropna()
    norm=LogNorm(200,150000)
    fig,ax=canvas('Income context','Gross national income (GNI) per capita, Atlas method  |  Latest available observations')
    matched=0
    for iso,g in countries:
        value=lookup.get(iso,np.nan)
        ok=np.isfinite(value) and value>0
        matched+=int(ok)
        ax.add_geometries([g],geo,facecolor=blue(norm(value)) if ok else '#d9dee3',edgecolor='white',linewidth=.25,zorder=1)
    bar(fig,norm,'GNI per capita (current United States dollars; logarithmic scale)',[200,1000,5000,20000,150000],lambda x,p:f'{x:,.0f}')
    ax.legend(handles=[Patch(facecolor='#d9dee3',label='No data / unmatched')],loc='lower left',bbox_to_anchor=(0,-.035),frameon=False,fontsize=11,handlelength=1.2,handletextpad=.5,borderaxespad=0)
    finish(fig,'gni_global','Source: World Bank, indicator NY.GNP.PCAP.CD; data updated 8 October 2026.  •  Observation years vary by economy')
    return {'income_features_with_observation':matched,'income_observed_range':[float(valid.min()),float(valid.max())]}

def climate():
    d=np.load(DATA/'climate_display_grid.npz')
    a=np.ma.masked_equal(d['classes'],0)
    colours=['#009E73','#E69F00','#56B4E9','#0072B2','#CC79A7']
    labels=['Tropical (A)','Arid (B)','Temperate (C)','Cold (D)','Polar (E)']
    fig,ax=canvas('Climate context','Köppen–Geiger climate classification  |  Five main climate classes')
    ax.imshow(a,origin='upper',extent=d['extent'],transform=geo,
              cmap=ListedColormap(colours),vmin=.5,vmax=5.5,interpolation='nearest',regrid_shape=1000,zorder=1)
    ax.add_geometries([land],geo,facecolor='none',edgecolor='#7f919d',linewidth=.3,zorder=2)
    fig.legend(handles=[Patch(facecolor=c,label=l) for c,l in zip(colours,labels)],
               loc='center',bbox_to_anchor=(.5,.103),ncol=5,frameon=False,fontsize=12.5,handlelength=1.2,handletextpad=.45,columnspacing=1.2)
    finish(fig,'climate_global','Source: Beck et al. (2023), global climate classification.  •  Generalized grid for map display')

if __name__=='__main__':
    indoor()
    checks=income()
    climate()
    checks.update({'figures':3,'city_points':len(pd.read_csv(DATA/'city_map_data.csv')),'projection':'Equal Earth','png_dpi':300})
    (DATA/'figure_checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks))
