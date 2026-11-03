"""Run the numbered model steps for the three example cities."""
from pathlib import Path
import argparse,csv,hashlib,json,os,subprocess,sys,time
ROOT=Path(os.environ.get('DYNAMIC_POPULATION_ROOT',Path(__file__).resolve().parents[1]))
CODE=Path(os.environ.get('DYNAMIC_POPULATION_CODE',ROOT/'02_code'))
STAGE2=Path(os.environ.get('DYNAMIC_POPULATION_STAGE2',ROOT/'04_intermediate/demo/stage_2'))
WORK=Path(os.environ.get('DYNAMIC_POPULATION_WORK',ROOT/'04_intermediate/demo'))
OUTPUTS=Path(os.environ.get('DYNAMIC_POPULATION_OUTPUTS',ROOT/'05_outputs/demo'))
DEMO_CONFIGURATION=ROOT/'03_run/demo_configuration'
STEMS=(DEMO_CONFIGURATION/'city_demo_stems.txt').read_text().split()

def input_checksum(path):
    """Hash CSV/JSON with LF line endings; hash binary inputs byte for byte."""
    content=path.read_bytes()
    if path.suffix.lower() in {'.csv','.json'}:
        content=content.replace(b'\r\n',b'\n')
    return hashlib.sha256(content).hexdigest()

def check_inputs(adopted_only=False):
    with (DEMO_CONFIGURATION/'city_demo_files.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    rows=[r for r in rows if r['path'].startswith('04_intermediate/demo/stage_2/')]
    if adopted_only:
        prefixes=('04_intermediate/demo/stage_2/hourly_location_shares/',
                  '04_intermediate/demo/stage_2/allocation_parameters/')
        rows=[r for r in rows if r['path'].startswith(prefixes)]
    for row in rows:
        p=STAGE2/Path(row['path']).relative_to('04_intermediate/demo/stage_2')
        if not p.is_file() or input_checksum(p)!=row['sha256']:
            raise RuntimeError(f"Missing or modified prepared input: {row['path']}")
    return len(rows)

def verify():
    import numpy as np
    import rasterio
    expected=json.loads((DEMO_CONFIGURATION/'city_demo_array_checksums.json').read_text())
    failures=[]
    for name,bands in expected.items():
        if name.startswith('05_outputs/demo/'):
            p=OUTPUTS/Path(name).relative_to('05_outputs/demo')
        elif name.startswith('04_intermediate/demo/'):
            p=WORK/Path(name).relative_to('04_intermediate/demo')
        else:
            p=ROOT/name
        if not p.exists():failures.append(name+': missing');continue
        if p.suffix=='.npz':
            with np.load(p) as z:arrays={k:z[k] for k in bands}
        else:
            with rasterio.open(p) as src:arrays={k:src.read(int(k)) for k in bands}
        for key,value in arrays.items():
            if not np.isfinite(value).all() or hashlib.sha256(np.asarray(value,dtype='<f8').tobytes()).hexdigest()!=bands[key]:
                failures.append(name+': '+key)
    if failures:raise RuntimeError('Numerical reproduction failed: '+ '; '.join(failures))
    print(json.dumps({'status':'passed','products_checked':len(expected),'comparison':'exact numeric-array fingerprints; file metadata excluded'}))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['check','run'])
    ap.add_argument('--stage',choices=['all','1','2','3','4'],default='all',help='run all four stages or one selected stage')
    a=ap.parse_args()
    if a.command=='check' or a.stage!='1':
        n=check_inputs(adopted_only=a.command=='run')
        print(json.dumps({'prepared_inputs_checked':n}),flush=True)
    if a.command=='check':verify();return
    work=WORK
    outputs=OUTPUTS
    out=outputs/'hourly_population' 
    env=os.environ.copy()
    env.update(DYNAMIC_POPULATION_ROOT=str(ROOT),DYNAMIC_POPULATION_STAGE2=str(STAGE2),DYNAMIC_POPULATION_WORK=str(work),DYNAMIC_POPULATION_OUTPUTS=str(outputs),DYNAMIC_POPULATION_NETWORK=str(work/'stage_3/in_transit_population'),DYNAMIC_POPULATION_COMPONENTS=str(outputs/'population_components'))
    common=['--stems',*STEMS,'--overwrite'];params=['--params',str(STAGE2/'allocation_parameters/population_allocation_parameters.json')]
    jobs=[
        ('stage_1_data_inputs/02_verify_raw_sources.py',[],[]),
        ('stage_2_100m_layers/01_create_city_grids.py',['--stems',*STEMS],[STAGE2/'local_grids/city_grid_definitions.csv']),
        ('stage_2_100m_layers/02_prepare_settlement_layers.py',['--stems',*STEMS],[STAGE2/folder/f'{s}.npy' for s in STEMS for folder in ['resident_population','buildings/total_building_volume','buildings/non_residential_building_volume','buildings/building_height']]),
        ('stage_2_100m_layers/03_prepare_destination_counts.py',['--stems',*STEMS],[STAGE2/'point_of_interest_counts/overture'/f'{s}.npz' for s in STEMS]),
        ('stage_2_100m_layers/04_prepare_building_floor_area.py',common,[STAGE2/'buildings/floor_area_by_use'/f'{s}.npz' for s in STEMS]),
        ('stage_2_100m_layers/05_prepare_transport_graphs.py',['--stems',*STEMS],[STAGE2/folder/f'{s}.npz' for s in STEMS for folder in ['road_and_rail_graphs','water_coverage_percent']]),
        ('stage_2_100m_layers/06_save_model_layers.py',['--stems',*STEMS],[STAGE2/'smoothed_places'/f'{s}.npz' for s in STEMS]),
        ('stage_3_activity_allocation/01_calculate_destination_attractiveness.py',['--stems',*STEMS],[work/'stage_3/destination_attractiveness'/f'{s}.npz' for s in STEMS])]

    jobs.append(('stage_3_activity_allocation/02_calculate_in_transit_population.py',common+params+['--out',str(work/'stage_3/in_transit_population')],[work/'stage_3/in_transit_population'/f'{s}.npz' for s in STEMS]))
    jobs.append(('stage_3_activity_allocation/03_calculate_population_components.py',common+params+['--out',str(outputs/'population_components')],[outputs/'population_components'/f'{s}.tif' for s in STEMS]+[work/'stage_3/destination_population'/f'{s}.npz' for s in STEMS]))
    jobs.append(('stage_4_outputs/01_generate_hourly_population.py',common+['--comp',str(outputs/'population_components'),'--out',str(out)],[out/s/dt/f'{s}_{dt}_hour_{hour:02d}.tif' for s in STEMS for dt in ['workday','rest_day'] for hour in range(24)]))
    jobs.append(('stage_4_outputs/02_classify_functional_land_use.py',common+['--out',str(outputs/'functional_land_use')],[outputs/'functional_land_use'/s/f'{s}_{suffix}.tif' for s in STEMS for suffix in ['functional_land_use','functional_land_use_attributes']]))
    visualization=Path(os.environ.get('DYNAMIC_POPULATION_FIGURES',ROOT/'06_docs/figures'))
    jobs.append(('stage_4_outputs/06_visualize_hourly_population.py',
                 ['--root',str(ROOT),'--stage2',str(STAGE2),'--hourly',str(out),'--out',str(visualization),'--stems',*STEMS],
                 [visualization/'demo_population_distributions.png']))
    jobs.append(('stage_4_outputs/07_visualize_time_use.py',
                 ['--root',str(ROOT),'--stage2',str(STAGE2),'--out',str(visualization)],
                 [visualization/'time_use_weights.png']))
    if a.stage!='all':jobs=[job for job in jobs if job[0].startswith('stage_'+a.stage+'_')]
    for program,args,products in jobs:
        started=time.time()
        print(json.dumps({'program':program,'arguments':args}),flush=True)
        subprocess.run([sys.executable,'-B',str(CODE/program),*args],env=env,cwd=ROOT,check=True)
        if not all(p.is_file() and p.stat().st_mtime>=started-2 for p in products):
            raise RuntimeError(program+' did not regenerate all required products; inspect stage errors')
    if a.stage in ['all','4']:verify()
    else:print(json.dumps({'stage':a.stage,'status':'completed','programs_executed':len(jobs)}))
if __name__=='__main__':main()
