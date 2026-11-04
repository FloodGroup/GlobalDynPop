"""Plot nighttime population and signed temporal contrasts from hourly rasters.

All differences are calculated at native resolution, without spatial smoothing.
Absolute population and signed change have separate scales, each shared across cities.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LinearSegmentedColormap, LogNorm, SymLogNorm
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator
import numpy as np
import pandas as pd
import rasterio

INPUTS = [('workday', 3), ('workday', 8), ('workday', 13), ('rest_day', 3), ('rest_day', 13)]
CONTRASTS = [
    ('Workday morning', ('workday', 8), ('workday', 3)),
    ('Workday midday', ('workday', 13), ('workday', 3)),
    ('Rest-day midday', ('rest_day', 13), ('rest_day', 3)),
    ('Midday day-type difference', ('workday', 13), ('rest_day', 13)),
]


def style():
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 12,
        'text.color': '#203744', 'axes.labelcolor': '#334956',
        'xtick.color': '#627581', 'ytick.color': '#627581',
        'axes.edgecolor': '#CBD5DB', 'axes.linewidth': .6, 'pdf.fonttype': 42,
        'savefig.dpi': 360})


def scalebar(ax, extent):
    x0, x1, y0, y1 = extent
    length = max(v for v in (.5, 1, 2, 5, 10, 20) if v*1000 <= (x1-x0)*.26)*1000
    x = x0+.055*(x1-x0)
    y = y0+.065*(y1-y0)
    ax.plot([x, x+length], [y, y], color='#203744', lw=1.1)
    ax.text(x+length/2, y+.03*(y1-y0), f'{length/1000:g} km', ha='center',
            va='bottom', fontsize=9.5, bbox=dict(facecolor='white', edgecolor='none', pad=.7, alpha=.9))


def read_city(hourly, stem):
    fields = {}
    reference = None
    for day, hour in INPUTS:
        path = hourly/stem/day/f'{stem}_{day}_hour_{hour:02d}.tif'
        with rasterio.open(path) as src:
            if src.count != 1 or src.descriptions not in {(f'hour_{hour:02d}',), (f'{hour:02d}:00 local time',)}:
                raise ValueError(f'Unexpected raster layout: {path}')
            if 'hour' in src.tags() and int(src.tags()['hour']) != hour:
                raise ValueError(f'Unexpected hour tag: {path}')
            signature = (src.width, src.height, src.crs, src.transform)
            if reference is None:
                reference = signature
            elif signature != reference:
                raise ValueError(f'Grid mismatch: {path}')
            values = src.read(1).astype(np.float64)
            extent = (src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f'Invalid population values: {path}')
        fields[day, hour] = values
    return fields, extent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('DYNAMIC_POPULATION_ROOT', Path(__file__).resolve().parents[2])))
    parser.add_argument('--hourly', type=Path)
    parser.add_argument('--stage1', type=Path)
    parser.add_argument('--stage2', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--stems', nargs='*')
    args = parser.parse_args(argv)
    root = args.root
    hourly = args.hourly or Path(os.environ.get('DYNAMIC_POPULATION_HOURLY', str(root/'05_outputs/demo/hourly_population')))
    stage2 = args.stage2 or Path(os.environ.get('DYNAMIC_POPULATION_STAGE2', str(root/'04_intermediate/demo/stage_2')))
    out = args.out or Path(os.environ.get('DYNAMIC_POPULATION_FIGURES', str(root/'06_docs/figures')))
    stage1 = args.stage1 or Path(os.environ.get('DYNAMIC_POPULATION_STAGE1', str(root/'04_intermediate/demo/stage_1')))
    cities = pd.read_csv(stage1/'local_grids/city_grid_definitions.csv').set_index('stem')
    stems = args.stems or sorted(cities.index)
    if not 1 <= len(stems) <= 3:
        raise ValueError('Select one to three cities for the one-page layout')
    out.mkdir(parents=True, exist_ok=True)
    style()
    fig = plt.figure(figsize=(11, 7.6), facecolor='white')
    fig.text(.025, .99, 'Hourly population changes', fontsize=24, weight='bold', va='top')
    fig.text(.025, .94, 'Nighttime reference and changes across hours and day types', fontsize=12.5, color='#627581', va='top')
    xs = [.15, .318, .486, .654, .822]
    width = .155
    titles = [('Nighttime', 'Workday 03:00'), ('Workday change', '08:00 − 03:00'),
              ('Workday change', '13:00 − 03:00'), ('Rest-day change', '13:00 − 03:00'),
              ('Workday − rest day', '13:00')]
    for x, (title, subtitle) in zip(xs, titles):
        fig.text(x+width/2, .878, title, ha='center', fontsize=10.5, weight='bold')
        fig.text(x+width/2, .848, subtitle, ha='center', fontsize=11)
    population_cmap = LinearSegmentedColormap.from_list('population', ['#F1EFF6', '#9481C5', '#7654AA', '#B14B8A', '#F47C45'], N=1024)
    population_cmap.set_bad((1, 1, 1, 0))
    population_norm = LogNorm(3, 200)
    change_cmap = LinearSegmentedColormap.from_list('change', ['#00649C', '#56B4E9', '#FFFFFF', '#F5AD66', '#C54B00'], N=1025)
    change_cmap.set_bad((1, 1, 1, 0))
    change_norm = SymLogNorm(linthresh=2, linscale=1, vmin=-100, vmax=100, base=10)
    for i, stem in enumerate(stems):
        fields, extent = read_city(hourly, stem)
        city = cities.loc[stem]
        name = 'Takasaki-\nMaebashi' if stem == '05685_JPN_Takasaki_Maebashi' else city['name']
        bottom = .608-i*.222
        height = .205
        center = bottom+height/2
        fig.text(.074, center+.012, name, ha='center', va='center', fontsize=12, weight='bold')
        fig.text(.074, center-(.046 if '\n' in name else .028), city['country'], ha='center', va='top', fontsize=10.5, color='#627581')
        baseline = fields['workday', 3]
        differences = [fields[a]-fields[b] for _, a, b in CONTRASTS]
        water = None
        waterpath = stage2/f'water_coverage_percent/{stem}.npz'
        if waterpath.exists():
            with np.load(waterpath) as z:
                water = z['water']
            if water.shape != baseline.shape:
                raise ValueError(f'Water grid mismatch: {stem}')
        for j, (x, values) in enumerate(zip(xs, [baseline]+differences)):
            ax = fig.add_axes([x, bottom, width, height])
            if water is not None:
                ax.imshow(np.ma.masked_where(water<50, water), extent=extent, interpolation='nearest',
                          cmap=ListedColormap(['#E6EDF0']), vmin=50, vmax=100)
            # No magnitude threshold for contrasts: retain all nonzero differences.
            plot_values = np.ma.masked_where(values<3 if j == 0 else values == 0, values)
            ax.imshow(plot_values, extent=extent, interpolation='nearest',
                      cmap=population_cmap if j == 0 else change_cmap,
                      norm=population_norm if j == 0 else change_norm)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color('#AEB6BF')
            if j == 0:
                scalebar(ax, extent)
    # Shared scales make the sign and magnitude comparable across every city.
    for position, norm, cmap, ticks, label, extension in [
        ([.15, .108, .155, .013], population_norm, population_cmap, [3, 20, 200], 'Nighttime population', 'max'),
        ([.37, .108, .585, .013], change_norm, change_cmap, [-100, -10, -2, 0, 2, 10, 100], 'Population change: blue = fewer; orange = more', 'both')]:
        cax = fig.add_axes(position)
        cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation='horizontal', extend=extension)
        cb.ax.xaxis.set_major_locator(FixedLocator(ticks))
        cb.ax.xaxis.set_major_formatter(FixedFormatter([f'{v:+g}' if v>0 and extension=='both' else f'{v:g}' for v in ticks]))
        cb.ax.xaxis.set_minor_locator(NullLocator())
        cb.ax.tick_params(labelsize=11, length=0, pad=3)
        fig.text(position[0]+position[2]/2, .137, label, ha='center', fontsize=10.5)
    fig.text(.025, .044, 'People per 100 m cell. Shared scales: logarithmic population; symmetric-log change (linear within ±2).', fontsize=9.5, color='#627581')
    fig.text(.025, .019, 'Local hourly intervals; e.g., 13:00 = 13:00–14:00. No spatial smoothing. Pale blue-grey indicates water.', fontsize=9.5, color='#627581')
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for item in fig.findobj(matplotlib.text.Text):
        if item.get_visible() and item.get_text():
            box = item.get_window_extent(renderer)
            if box.x0 < -1 or box.y0 < -1 or box.x1 > fig.bbox.width+1 or box.y1 > fig.bbox.height+1:
                raise ValueError('Text outside figure: '+item.get_text())
    fig.savefig(out/'demo_population_distributions.png', dpi=360)
    public = out.resolve() == (root/'06_docs/figures').resolve()
    pdf_dir = root/'05_outputs/figure_exports' if public else out.parent/'figure_exports'
    pdf_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(pdf_dir/'demo_population_distributions.pdf', dpi=360)
    plt.close(fig)
    print(json.dumps({'png': str(out/'demo_population_distributions.png'), 'panels': 5*len(stems)}), flush=True)


if __name__ == '__main__':
    main()
