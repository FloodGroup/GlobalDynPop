"""Read road, rail and station source features for routing-graph preparation."""
import pyarrow as pa
import pyarrow.compute as pc
import stage_3_activity_allocation.network as network

def read_layer(reader, layer, bbox, cols):
    rg = reader.row_groups(layer, bbox)
    jobs = [(p, g.rg.to_numpy()) for p, g in rg.groupby("path")]
    if not jobs:
        return None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(min(8, len(jobs))) as ex:
        parts = list(ex.map(lambda j: reader._read(j[0], j[1], cols, bbox, None), jobs))
    parts = [p for p in parts if p.num_rows]
    return pa.concat_tables(parts, promote_options="permissive") if parts else None

def fetch(reader, grid):
    bb = grid.lonlat_bounds(0.0)
    seg = read_layer(reader, "segment", bb, ["id", "class", "subtype", "connectors"])
    if seg is not None:
        seg = seg.filter(pc.is_in(seg.column("subtype"), pa.array(["road", "rail"])))
    inf = read_layer(reader, "infrastructure", bb, ["id", "class", "subtype"])
    sta = None
    if inf is not None:
        sta = inf.filter(pc.and_(pc.equal(inf.column("subtype"), "transit"),
                                 pc.is_in(inf.column("class"), pa.array(list(network.STATION_CLASSES)))))
    return seg, sta
