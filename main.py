import json
from functools import partial

import pandas as pd
import geopandas as gp
import networkx as nx
import osmnx as ox
import numpy as np
from osmnx.utils import log
from pyogrio import read_dataframe, write_dataframe

from shapely.geometry import shape, Point, LineString
from shapely.ops import nearest_points
from shapely import set_precision

ox.settings.max_query_area_size = 5000000000

ox.settings.use_cache = True
ox.settings.log_console = True

COLUMNS = ["railway", "service"]

OUTPATH = "output/aquitaine-rail.gpkg"

CRS = "EPSG:2154" # France national grid
RGF93 = "EPSG:2154"
WGS84 = "EPSG:4326"

pd.set_option("display.max_columns", None)
set_precision_one = partial(set_precision, grid_size=1.0)

def get_node_group(graph, key):
    """
    In our case, I can simply retrieve all the values in the first two columns,
    which is equivalent to recovering all the node ids.
    """

    edge = ox.graph_to_gdfs(graph, nodes=False)
    edgeFilled = edge[key].fillna("").groupby(COLUMNS) # GroupBy object

    group = dict(list(edgeFilled))

    res = {}

    for k, v in group.items():
        node_id = v.reset_index().values[:, 0:2].reshape(-1) # 'values[:, 0:2]' means that we want every rows from the first 2 columns (= node ids)
        res[k] = np.unique(node_id)

    return res

def get_simplified_nx(graph, node_id, key):
    empty = gp.GeoDataFrame()

    r = graph.subgraph(node_id)
    r = ox.simplify_graph(r)

    if nx.is_empty(r):
        return empty, empty
    
    node, edge = ox.graph_to_gdfs(r)

    return node, edge

def get_network(POLYGON):
    log("Downloading railway")

    ox.settings.useful_tags_way += ['railway', 'service']

    include = 'yard'

    cf = f'["service"~"{include}"]'

    log("Creating network")

    railway = ox.graph_from_polygon(
        POLYGON, 
        simplify=False, 
        retain_all=True, 
        custom_filter=cf
    )

    return railway

def simplify_network(railway):
    log(f"Simplify network {COLUMNS}")

    rail_group = get_node_group(railway, COLUMNS)
    node, edge = gp.GeoDataFrame(), gp.GeoDataFrame()

    for k, v in rail_group.items():
        # print(f'k = {k} et v = {v}')

        log(f'For values (key) {k}: ')
        i, j = get_simplified_nx(railway, v, k) # i = nodes, j = edges

        # display(j)

        if i.empty or j.empty:
            continue

        i, j = i.reset_index().fillna(""), j.reset_index().fillna("")
        
        """j[COLUMNS] = k

        print(f'j[COLUMNS] = {j[COLUMNS]}, et k = {k}')"""

        node = pd.concat([i, node])
        edge = pd.concat([j, edge])

    return node, edge

def main():
    log("Starting...")

    polygon = read_dataframe("data/aquitaine.geojson")
    log(f'First affectation to "polygon" -> type: {type(polygon)}')
    log(f'Initial CRS of polygon: {polygon.crs}')

    polygon = polygon.explode(index_parts=False).reset_index(drop=True)
    log(f'Second affectation to "polygon" -> type: {type(polygon)}')

    polygon = polygon.loc[polygon.area.sort_values(ascending=False).index]
    log(f'Third affectation to "polygon" -> type: {type(polygon)}')
    log(f'CRS after explosion and sorting: {polygon.crs}')

    polygon = polygon.to_crs(RGF93).geometry.iloc[0]
    log(f'Last affectation to "polygon" -> type: {type(polygon)}')

    railway = get_network(polygon)
    node, edge = simplify_network(railway)

    r = node.reset_index().fillna("").to_crs(CRS)
    r["geometry"] = r["geometry"].map(set_precision_one)

    log("Output GeoPKG nodes")
    write_dataframe(r, OUTPATH, layer="node")

    # node["geometry"] = node["geometry"].map(set_precision_one) ?

    r = edge.reset_index().fillna("").to_crs(CRS)
    r["geometry"] = r["geometry"].map(set_precision_one)

    log("Output GeoPKG lines") # (= edges)
    write_dataframe(r, OUTPATH, layer="line")

    output = r.to_json(na="drop", drop_id=True)
    
    with open("output/aquitaine-rail.geojson", "w", encoding="utf8") as fout:
        fout.write(output)

    log("Finished")

if __name__ == "__main__":
    main()