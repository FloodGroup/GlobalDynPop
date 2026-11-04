"""Rebuild and verify the three-city example in dependency order, entirely from local raw inputs."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('DYNAMIC_POPULATION_ROOT', PACKAGE)).resolve()
STEMS = (ROOT/'03_run/demo_configuration/city_demo_stems.txt').read_text().split()
S2_PROGRAMS = [
    '01_prepare_settlement_layers.py', '02_prepare_destination_counts.py',
    '03_prepare_building_floor_area.py', '04_prepare_transport_graphs.py',
    '05_prepare_permanent_water.py', '06_prepare_outdoor_recreation.py',
    '07_prepare_land_use.py', '08_prepare_china_land_use.py',
    '09_prepare_global_building_atlas.py', '10_prepare_buildings_open_space.py',
    '11_save_model_layers.py',
]


def environment(out):
    env = os.environ.copy()
    env.update(DYNAMIC_POPULATION_ROOT=str(ROOT), DYNAMIC_POPULATION_STAGE1=str(out/'stage_1'),
               DYNAMIC_POPULATION_STAGE2=str(out/'stage_2'), DYNAMIC_POPULATION_STAGE3=str(out/'stage_3'),
               DYNAMIC_POPULATION_WORK=str(out), DYNAMIC_POPULATION_OUTPUTS=str(out/'outputs'),
               DYNAMIC_POPULATION_NETWORK=str(out/'stage_3/in_transit_population'),
               DYNAMIC_POPULATION_ROAD_GRAPHS=str(out/'stage_2/road_and_rail_graphs'),
               DYNAMIC_POPULATION_COMPONENTS=str(out/'outputs/population_components'),
               DYNAMIC_POPULATION_HOURLY=str(out/'outputs/hourly_population'),
               DYNAMIC_POPULATION_PARAMS=str(out/'stage_2/allocation_parameters/population_allocation_parameters.json'),
               DYNAMIC_POPULATION_DAYTYPE_DIR=str(out/'stage_2/hourly_location_shares'),
               PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
               DYNAMIC_POPULATION_RUN_START=str(time.time()), GDP_RUN_START=str(time.time()))
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(PACKAGE/'03_run/runtime'), env.get('PYTHONPATH')]))
    return env


def call(program, args, env, expected=()):
    before = {p: p.stat().st_mtime_ns if p.exists() else None for p in expected}
    print('Running '+program, flush=True)
    subprocess.run([sys.executable, '-B', str(PACKAGE/'02_code'/program), *map(str,args)],
                   cwd=ROOT, env=env, check=True)
    for path, stamp in before.items():
        if not path.is_file() or (stamp is not None and path.stat().st_mtime_ns == stamp):
            raise RuntimeError(f'Program did not regenerate its output: {program}: {path}')


def require(files):
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise FileNotFoundError('Missing prerequisite outputs; run the preceding stage first: '+str(missing))


def validate_stage2(out, stems):
    import numpy as np
    import pandas as pd
    s2 = out/'stage_2'
    require([out/'stage_1/local_grids/city_grid_definitions.csv',
             s2/'allocation_parameters/population_allocation_parameters.json',
             s2/'time_use/w_indoor/w_indoor_cities.csv'])
    table = pd.read_csv(out/'stage_1/local_grids/city_grid_definitions.csv').set_index('stem')
    indoor = pd.read_csv(s2/'time_use/w_indoor/w_indoor_cities.csv').set_index('stem')
    sources = pd.read_csv(s2/'hourly_location_shares/location_share_sources.csv')
    checks=[]
    for stem in stems:
        row=table.loc[stem]; shape=(int(row.ny),int(row.nx))
        for folder in ['resident_population','buildings/total_building_volume',
                       'buildings/non_residential_building_volume','buildings/building_height']:
            a=np.load(s2/folder/(stem+'.npy'))
            if a.shape!=shape or not np.isfinite(a).all() or (a<0).any():raise ValueError(f'Invalid {stem}/{folder}')
        for folder,keys in [('buildings/floor_area_legacy',['fa']),('buildings/floor_area_by_use',['fa']),
                            ('buildings/gba_cells',['foot_m2','vol_m3','floor_m2']),
                            ('basemap/landcover',['pw']),('basemap/outdoor',['outdoor']),
                            ('basemap/open_space',['street','parking','plaza','park','grass','rec','campus','cons','open']),
                            ('water_coverage_percent',['water']),('point_of_interest_counts/overture',[]),
                            ('smoothed_places',[]),('basemap/land_use',[])]:
            with np.load(s2/folder/(stem+'.npz'),allow_pickle=False) as z:
                if not set(keys)<=set(z.files):raise ValueError(f'Missing arrays: {stem}/{folder}')
                for key in z.files:
                    if key=='meta':continue
                    a=z[key]
                    if a.shape[-2:]!=shape or not np.isfinite(a).all() or (a<0).any():raise ValueError(f'Invalid {stem}/{folder}/{key}')
        require([s2/'road_and_rail_graphs'/(stem+'.npz'),s2/'distance_decay_kernels'/(stem+'.json')])
        with np.load(s2/'basemap/open_space'/(stem+'.npz')) as z:
            if (sum(z[k] for k in z.files if k!='meta')>1+1e-6).any():raise ValueError('Outdoor fractions exceed one')
        with np.load(s2/'basemap/landcover'/(stem+'.npz')) as z:
            if (z['pw']>100).any():raise ValueError('Invalid permanent-water fraction')
        if not 0<=float(indoor.loc[stem,'w_indoor'])<=1:raise ValueError('Invalid indoor fraction')
        for dt in ['workday','restday']:
            source=sources[(sources.iso3==row.iso3)&(sources.daytype==dt)]
            if len(source)!=1:raise ValueError(f'Missing/duplicate share index: {row.iso3}/{dt}')
            a=pd.read_csv(s2/'hourly_location_shares'/source.iloc[0]['file']).iloc[:,1:8].to_numpy(float)
            if a.shape!=(24,7) or not np.isfinite(a).all() or (a<0).any() or not np.allclose(a.sum(1),1,atol=1e-6):raise ValueError('Invalid hourly shares')
        checks.append(dict(stem=stem,shape=list(shape),population=float(np.load(s2/'resident_population'/(stem+'.npy')).sum(dtype=float))))
    return checks


def validate_stage3(out, stems):
    import numpy as np
    import rasterio
    rows=[]
    for stem in stems:
        n=np.load(out/'stage_2/resident_population'/(stem+'.npy')); total=float(n.sum(dtype=float))
        require([out/'outputs/population_components'/(stem+'.tif'),out/'outputs/population_components'/(stem+'.json')])
        for folder,keys in [('destination_attractiveness',[f'{c}_{dt}' for dt in ('workday','restday') for c in ('C2','C3','C4','C5','C7')]),
                            ('destination_population',[f'{c}_{dt}' for dt in ('workday','restday') for c in ('C2','C3','C4','C5','C7')]),
                            ('in_transit_population',['T_workday','T_restday'])]:
            with np.load(out/'stage_3'/folder/(stem+'.npz')) as z:
                for key in keys:
                    a=z[key]
                    if a.shape!=n.shape or not np.isfinite(a).all() or (a<0).any():raise ValueError(f'Invalid {stem}/{folder}/{key}')
                    if folder!='destination_attractiveness' and abs(a.sum(dtype=float)-total)>1e-4*max(total,1):raise ValueError(f'Population loss: {stem}/{folder}/{key}')
        with rasterio.open(out/'outputs/population_components'/(stem+'.tif')) as src:
            if not set(['C1','C2','C3','C4','C5','C6','C7'])<=set(src.descriptions):raise ValueError('Missing component bands')
            for k in range(1,src.count+1):
                a=src.read(k)
                if a.shape!=n.shape or not np.isfinite(a).all() or (a<0).any():raise ValueError('Invalid components')
                if abs(a.sum(dtype=float)-total)>1e-4*max(total,1):raise ValueError('Component population loss')
        rows.append(dict(stem=stem,components_checked=src.count))
    return rows


def validate_stage4(out, stems):
    import numpy as np
    import pandas as pd
    import rasterio
    table=pd.read_csv(out/'stage_1/local_grids/city_grid_definitions.csv').set_index('stem')
    index=pd.read_csv(out/'stage_2/hourly_location_shares/location_share_sources.csv')
    cols=['residential','commercial_industrial','education','medical_public','leisure','transportation','other']
    checks=[]
    for stem in stems:
        with rasterio.open(out/'outputs/population_components'/(stem+'.tif')) as src:
            comp=dict(zip(src.descriptions,src.read().astype(float))); signature=(src.shape,src.crs,src.transform)
        for dt,label in [('workday','workday'),('restday','rest_day')]:
            f=index[(index.iso3==table.loc[stem,'iso3'])&(index.daytype==dt)].iloc[0]['file']
            shares=pd.read_csv(out/'stage_2/hourly_location_shares'/f)[cols].to_numpy(float);shares/=shares.sum(1,keepdims=True)
            bands=np.stack([comp.get(f'C{i}_rest',comp[f'C{i}']) if dt=='restday' else comp[f'C{i}'] for i in range(1,8)])
            for h in range(24):
                path=out/'outputs/hourly_population'/stem/label/f'{stem}_{label}_hour_{h:02d}.tif'
                with rasterio.open(path) as src:
                    if (src.shape,src.crs,src.transform)!=signature or src.count!=1:raise ValueError('Hourly grid mismatch')
                    a=src.read(1).astype(float)
                    if int(src.tags().get('hour',-1))!=h:raise ValueError('Hourly metadata mismatch')
                expected=np.einsum('i,ijk->jk',shares[h],bands)
                error=float(abs(a-expected).max())
                if not np.isfinite(a).all() or (a<0).any() or error>.005:raise ValueError(f'Hourly mixture mismatch: {path}: {error}')
                checks.append(dict(stem=stem,daytype=dt,hour=h,max_abs_people=error))
        for suffix in ['land_use','land_use_detail']:
            with rasterio.open(out/'outputs/functional_land_use'/stem/f'{stem}_{suffix}.tif') as src:
                if (src.shape,src.crs,src.transform)!=signature:raise ValueError('Land-use grid mismatch')
                a=src.read()
                if not np.isfinite(a).all() or (a<0).any():raise ValueError('Invalid land-use values')
                if suffix=='land_use' and not np.isin(a,range(1,8)).all():raise ValueError('Invalid land-use classes')
    return checks


def build_stage2(out, stems, env):
    require([out/'stage_1/local_grids/city_grid_definitions.csv'])
    s2=out/'stage_2';s2.mkdir(parents=True,exist_ok=True)
    # Adopted non-spatial research inputs only; no prepared spatial or population arrays are copied.
    for folder in ['allocation_parameters','time_use','hourly_location_shares']:
        shutil.copytree(ROOT/'04_intermediate/demo/stage_2'/folder,s2/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns("*.md", "*.html"))
    products = {
        '01': [('resident_population','.npy'),('buildings/total_building_volume','.npy'),('buildings/non_residential_building_volume','.npy'),('buildings/building_height','.npy')],
        '02': [('point_of_interest_counts/overture','.npz')],
        '03': [('buildings/floor_area_legacy','.npz')],
        '04': [('road_and_rail_graphs','.npz'),('basemap/overture_water','.npz')],
        '05': [('basemap/landcover','.npz'),('water_coverage_percent','.npz')],
        '06': [('basemap/outdoor','.npz')], '07': [('basemap/land_use','.npz')],
        '08': [('basemap/land_use_aoi','.npz')], '09': [('buildings/gba','.npz')],
        '10': [('buildings/floor_area_by_use','.npz'),('buildings/gba_cells','.npz'),('basemap/open_space','.npz')],
        '11': [('smoothed_places','.npz'),('distance_decay_kernels','.json')],
    }
    for name in S2_PROGRAMS:
        args=['--stems',*stems]
        if name.startswith(('05_','06_','07_','09_')):args+=['--local-raw']
        if name.startswith(('01_','02_','03_','04_','05_','06_','07_','08_','10_')):args+=['--overwrite']
        if name.startswith('08_'):
            china=[s for s in stems if s.split('_')[1]=='CHN']
            if not china:
                print('China AOI processing: not applicable to the selected cities',flush=True);continue
            args=['--stems',*china,'--overwrite']
        expected=[s2/folder/(stem+suffix) for folder,suffix in products[name[:2]] for stem in (china if name.startswith('08_') else stems)]
        call('stage_2_100m_layers/'+name,args,env,expected)
    call('stage_4_outputs/01_verify_inputs.py',['--full','--stems',*stems],env)
    return validate_stage2(out,stems)


def write_report(out, report):
    tmp=out/'verification.tmp.json';tmp.write_text(json.dumps(report,indent=2),encoding='utf-8');tmp.replace(out/'verification.json')


def run(mode, stage, out, stems):
    out=out.resolve()
    # The numerical reference package is never an execution destination.
    for protected in [ROOT/'01_inputs',ROOT/'02_code',ROOT/'03_run',ROOT/'04_intermediate/demo/stage_1',
                      ROOT/'04_intermediate/demo/stage_2',ROOT/'04_intermediate/demo/stage_3',ROOT/'05_outputs',ROOT/'06_docs']:
        protected=protected.resolve()
        if out==protected or out.is_relative_to(protected) or protected.is_relative_to(out):raise ValueError('Choose a separate run output directory')
    out.mkdir(parents=True,exist_ok=True);env=environment(out)
    report_path=out/'verification.json'
    report=json.loads(report_path.read_text()) if report_path.exists() else {'stems':stems,'stages':{}}
    if not isinstance(report.get('stages'), dict):
        report={'stems':stems,'stages':{}}
    selected=['1','2','3','4'] if stage=='all' else [stage]
    if report.get('stems')!=stems and selected!=['1','2','3','4']:raise ValueError('Use the same cities as the preceding stages, or run all stages')
    report['stems']=stems
    try:
        for s in selected:
            if mode=='run':
                if s!='1' and report['stages'].get(str(int(s)-1),{}).get('status')!='passed':raise RuntimeError(f'Run Stage {int(s)-1} in this --out directory first')
                for later in range(int(s),5):report['stages'].pop(str(later),None)
                report['status']='running';report['active_stage']=s;write_report(out,report)
                if s=='1':
                    call('stage_1_data_inputs/02_verify_raw_sources.py',[],env)
                    call('stage_1_data_inputs/00_create_city_grids.py',['--stems',*stems,'--output',out/'stage_1/local_grids/city_grid_definitions.csv'],env)
                    result={'grid':str(out/'stage_1/local_grids/city_grid_definitions.csv')}
                elif s=='2':result=build_stage2(out,stems,env)
                elif s=='3':
                    validate_stage2(out,stems)
                    call('stage_3_activity_allocation/01_calculate_destination_attractiveness.py',['--stems',*stems],env,[out/'stage_3/destination_attractiveness'/(x+'.npz') for x in stems])
                    call('stage_3_activity_allocation/02_calculate_in_transit_population.py',['--stems',*stems,'--overwrite'],env,[out/'stage_3/in_transit_population'/(x+'.npz') for x in stems])
                    call('stage_3_activity_allocation/03_calculate_population_components.py',['--stems',*stems,'--overwrite'],env,[out/'outputs/population_components'/(x+'.tif') for x in stems])
                    result=validate_stage3(out,stems)
                else:
                    validate_stage2(out,stems);validate_stage3(out,stems)
                    call('stage_4_outputs/01_verify_inputs.py',['--full','--stems',*stems],env)
                    call('stage_4_outputs/02_generate_hourly_population.py',['--stems',*stems,'--overwrite'],env,[out/'outputs/hourly_population'/x/dt/f'{x}_{dt}_hour_{h:02d}.tif' for x in stems for dt in ['workday','rest_day'] for h in range(24)])
                    call('stage_4_outputs/03_classify_functional_land_use.py',['--stems',*stems,'--overwrite','--out',out/'outputs/functional_land_use'],env,[out/'outputs/functional_land_use'/x/f'{x}_{kind}.tif' for x in stems for kind in ['land_use','land_use_detail']])
                    result=validate_stage4(out,stems)
                    for kind in ['network','components','hourly']:
                        call('stage_4_outputs/04_verify_outputs.py',['--step',kind,'--jobs','1'],env)
                    call('stage_4_outputs/06_visualize_hourly_population.py',['--root',ROOT,'--stage1',out/'stage_1','--stage2',out/'stage_2','--hourly',out/'outputs/hourly_population','--out',out/'figures','--stems',*stems],env)
                    call('stage_4_outputs/07_visualize_time_use.py',['--root',ROOT,'--stage2',out/'stage_2','--out',out/'figures'],env)
                report['stages'][s]={'status':'passed','checks':result}
            else:
                if report['stages'].get(s,{}).get('status')!='passed':raise RuntimeError(f'Stage {s} has not completed in this output directory')
                if s=='1':
                    call('stage_1_data_inputs/02_verify_raw_sources.py',[],env)
                    require([out/'stage_1/local_grids/city_grid_definitions.csv'])
                else:{'2':validate_stage2,'3':validate_stage3,'4':validate_stage4}[s](out,stems)
        report['status']='passed';report.pop('active_stage',None);report.pop('error',None)
        write_report(out,report)
        print(json.dumps({'status':'passed','mode':mode,'stages':selected,'report':str(report_path)}),flush=True)
    except Exception as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}')
        write_report(out,report)
        raise


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['run','check'])
    ap.add_argument('--stage',choices=['all','1','2','3','4'],default='all')
    ap.add_argument('--out',type=Path,default=ROOT/'04_intermediate/demo/reproduction')
    ap.add_argument('--stems',nargs='+',choices=STEMS,default=STEMS)
    a=ap.parse_args();run(a.command,a.stage,a.out,list(dict.fromkeys(a.stems)))
