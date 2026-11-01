"""Plot the hourly location shares used by the three example cities."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd

LABELS=['C1 Home','C2 Work and commerce','C3 Education','C4 Services',
        'C5 Leisure','C6 In transit','C7 Other']
COLORS=['#D9D9D9','#2878D0','#21A899','#7651C8','#EC6544','#E6AC16','#CC79A7']


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(os.environ.get('DYNAMIC_POPULATION_ROOT',Path(__file__).resolve().parents[2])))
    parser.add_argument('--stage2',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args(argv)
    stage2=args.stage2 or Path(os.environ.get('DYNAMIC_POPULATION_STAGE2',args.root/'04_intermediate/demo/stage_2'))
    out=args.out or Path(os.environ.get('DYNAMIC_POPULATION_FIGURES',args.root/'06_docs/figures'))
    sys.path.insert(0,str(args.root/'02_code'))
    from stage_2_100m_layers.time_use import daytype_shares, CLASS_COLS

    for name in ('times.ttf','timesbd.ttf','timesi.ttf','timesbi.ttf'):
        font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
        if font.exists():fm.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','Liberation Serif','DejaVu Serif'],
        'font.size':14,'pdf.fonttype':42,'axes.linewidth':.6,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(2,2,figsize=(11.7,8.3),sharex=True,sharey=True)
    fig.subplots_adjust(left=.09,right=.97,top=.79,bottom=.30,hspace=.48,wspace=.13)
    fig.text(.09,.95,'GlobalDynPop-100m',color='#23466E',fontsize=15)
    fig.text(.09,.90,'Hourly location shares used by the example cities',fontsize=22,weight='bold')
    metadata={'source_directory':'04_intermediate/demo/stage_2/hourly_location_shares',
              'time_basis':'local hour','shape':[24,7],'normalisation':'each row divided by its sum, as in the model reader',
              'colors':dict(zip(LABELS,COLORS)),'inputs':[],'output_format':'png','dpi':360}
    for row,(iso,title) in enumerate([('FIN','Finland | Helsinki'),('JPN','Japan | Kitakyushu and Takasaki-Maebashi')]):
        for col,(day,label) in enumerate([('workday','Workday'),('restday','Rest day')]):
            base=stage2/'hourly_location_shares'
            shares,source=daytype_shares(iso,day,base=base)
            path=base/source['file']
            raw=pd.read_csv(path)
            if not np.array_equal(raw['hour'].to_numpy(),np.arange(24)):
                raise ValueError(f'Expected ordered hours 0-23: {path}')
            values=raw[CLASS_COLS].to_numpy(float)
            if values.shape!=(24,7) or not np.isfinite(values).all() or (values<0).any() or (values.sum(axis=1)<=0).any():
                raise ValueError(f'Invalid raw shares: {path}')
            if not np.isfinite(shares).all() or (shares<0).any() or not np.allclose(shares.sum(axis=1),1,atol=1e-12):
                raise ValueError(f'Invalid model shares: {path}')
            ax=axs[row,col]
            # The last sample extends hour 23 to the right-hand boundary at 24.
            plotted=np.vstack([shares,shares[-1]])
            ax.stackplot(np.arange(25),plotted.T,colors=COLORS,step='post',linewidth=0,labels=LABELS)
            ax.set_xlim(0,24);ax.set_ylim(0,1)
            ax.set_xticks([0,6,12,18,24]);ax.set_yticks([0,.25,.5,.75,1])
            ax.tick_params(length=3,width=.6)
            ax.set_title(f'{title}\n{label}',fontsize=15,pad=8)
            ax.text(-.09,1.10,chr(97+2*row+col),transform=ax.transAxes,weight='bold',fontsize=17)
            if col==0:ax.set_ylabel('Population share')
            if row==1:ax.set_xlabel('Local hour')
            metadata['inputs'].append({'country':iso,'daytype':day,'file':path.name,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source':source,
                'raw_row_sum_max_error':float(np.max(np.abs(values.sum(axis=1)-1))),
                'model_row_sum_max_error':float(np.max(np.abs(shares.sum(axis=1)-1)))})
    handles,labels=axs[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.53,.15),ncol=4,frameon=False,fontsize=13)
    fig.text(.09,.095,'Note. Hourly shares sum to one; both Japanese cities use the same national profile.',
             ha='left',va='top',fontsize=15)
    out.mkdir(parents=True,exist_ok=True)
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    for text_item in fig.findobj(matplotlib.text.Text):
        if not text_item.get_visible() or not text_item.get_text():
            continue
        box=text_item.get_window_extent(renderer)
        if box.x0 < -1 or box.y0 < -1 or box.x1 > fig.bbox.width+1 or box.y1 > fig.bbox.height+1:
            raise ValueError("Text outside figure: "+text_item.get_text())
    fig.savefig(out/'time_use_weights.png',dpi=360)
    plt.close(fig)
    (out/'time_use_weights_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps({'png':str(out/'time_use_weights.png'),'panels':4,'matrices_checked':4}))


if __name__=='__main__':main()
