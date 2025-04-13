import json
from itertools import islice
import os

import geopandas as gpd
import h3
import networkx as nx
import numpy as np
import osmnx as ox
from shapely.geometry import LineString

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from django.shortcuts import render

def home(request):
    return render(request, 'index.html')  # or whatever your main file is



def convert_to_digraph(G_multi):
    '''Convert MultiGraph to DiGraph as the server is inizialized'''

    G_walk = nx.DiGraph()
    G_walk.graph["crs"] = "EPSG:4326"
    for u, v, data in G_multi.edges(data=True):
        w = data.get('length', 1)
        if G_walk.has_edge(u, v):
            if G_walk[u][v]['length'] > w:
                # Update the existing edge with the new edge data
                G_walk[u][v].update(data)
        else:
            # Add the edge with the new data
            G_walk.add_edge(u, v, **data)

    # Also copy node data from the MultiDiGraph to the DiGraph
    for node, data in G_multi.nodes(data=True):
        G_walk.add_node(node, **data)
    
    return G_walk

# Load the graph once when the server starts
G_multi_walk = convert_to_digraph(ox.load_graphml(os.path.join(settings.BASE_DIR, 'routing', 'data','ljubljana_walk.graphml')))
G_multi_bike= convert_to_digraph(ox.load_graphml(os.path.join(settings.BASE_DIR, 'routing', 'data','ljubljana_bike.graphml')))

def is_within_bbox(coords):
    """Check if the coordinates are within the bounding box where our models work."""

    lat, lon = coords
    min_lon, min_lat, max_lon, max_lat = (14.408617, 45.974064, 14.755332, 46.145997) # Ljubljana as defined by OpenStreetMaps
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


@csrf_exempt
def get_paths(request):
    if request.method == 'POST':
        try:
            # Parse input JSON data from frontend
            data = json.loads(request.body)
            origin_coords = data.get('origin_coords')
            destination_coords = data.get('destination_coords')
            commute_mode = data.get('commute_mode')
            routing_mode = data.get('routing_mode')

            if not origin_coords or not destination_coords:
                return JsonResponse({"error": "Origin and destination coordinates are required"}, status=400)
            
            if not is_within_bbox(destination_coords):
                return JsonResponse({"error": "Destination coordinates are outside the allowed area (Ljubljana)"}, status=400)

            if not is_within_bbox(origin_coords):
                return JsonResponse({"error": "Starting coordinates are outside the allowed area (Ljubljana)"}, status=400)


            # Ensure the coordinates are in the correct format
            origin_coords = tuple(origin_coords)
            destination_coords = tuple(destination_coords)

            # Prepare graph and compute the paths
            if commute_mode == "walk":
                G_graph = G_multi_walk
            elif commute_mode == "bike":
                G_graph = G_multi_bike
            else:
                return JsonResponse({"error": "Commute mode is required (walk or bike)"}, status=400)

            # Get nearest nodes
            orig_node = ox.distance.nearest_nodes(G_graph, X=origin_coords[1], Y=origin_coords[0])
            dest_node = ox.distance.nearest_nodes(G_graph, X=destination_coords[1], Y=destination_coords[0])

            # Get 25 shortests paths (takes about 1s)
            paths = list(islice(nx.shortest_simple_paths(G_graph, orig_node, dest_node, weight='length'), 25))

            # Convert to GeoDataFrame
            path_data = []
            for i, path in enumerate(paths):
                coords = [(G_graph.nodes[n]['x'], G_graph.nodes[n]['y']) for n in path]
                length = nx.path_weight(G_graph, path, weight='length')
                path_data.append({
                    'path_num': i + 1,
                    'origin_coords': origin_coords,
                    'destination_coords': destination_coords,
                    'geometry': LineString(coords),
                    'length_m': length,
                    'coordinates': coords
                })

            # get top 3 paths based on routing mode

            if routing_mode == "vegetation":
                with open(os.path.join(settings.BASE_DIR, 'routing', 'data','avg_ndvi_h3_13.json'), 'r') as f:
                    ndvi_h3 = json.load(f)

                path_data = get_top_3_ndvi(path_data, ndvi_h3)

            elif routing_mode == "noise":
                noise_data = gpd.read_file(os.path.join(settings.BASE_DIR, 'routing', 'data','Slovenia_Osrednjeslovenska_Ljubljana.tracks.geojson'))

                path_data = get_top_3_quietest_paths(path_data, noise_data)

                if not path_data:
                    return JsonResponse({"error": "Not enough noise data between chosen locations to estimate the best path"}, status=400)

            elif routing_mode is None:

                # Get the indexes of the 3 shortest paths based on length
                sorted_indexes = sorted(range(len(path_data)), key=lambda i: path_data[i]['length_m'])

                # Select the top 3 shortest paths by using the sorted indexes
                path_data = [path_data[i] for i in sorted_indexes[:3]]

            gdf_paths = gpd.GeoDataFrame(path_data, crs="EPSG:4326")

            # Convert GeoDataFrame to GeoJSON
            geojson = gdf_paths.to_json()

            return JsonResponse(geojson, safe=False)
        
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


def get_top_3_ndvi(path_data, ndvi_h3):
    """
    Returns the top 3 paths with the highest average NDVI.
    
    Args:
        path_data (dict): GeoJSON-like dict with 25 paths.
        ndvi_h3 (dict): Dict with H3 indexes as keys and NDVI values as floats.
    
    Returns:
        list: List of path numbers with the highest average NDVI.
    """
    
    def get_h3_index(lat, lon):
        return h3.latlng_to_cell(lat, lon, res=13)

    def calculate_average_ndvi(path):
        # Extract coordinates of the path
        coords = path['coordinates']
        
        # Convert coordinates to H3 indexes
        h3_indexes = [
            get_h3_index(coord[1], coord[0])  # (lat, lon)
            for coord in coords
        ]
        
        # Get the NDVI values for the H3 indexes
        ndvi_values = [
            ndvi_h3[h3_index]
            for h3_index in h3_indexes if h3_index in ndvi_h3
        ]
        
        # Return the average NDVI, or None if no valid NDVI values
        return np.mean(ndvi_values) if ndvi_values else None

    # Calculate NDVI for each path
    for path in path_data:
        avg_ndvi = calculate_average_ndvi(path)
        path['average_ndvi'] = avg_ndvi   # Add average NDVI to path data

    # Sort the paths by average NDVI in descending order
    sorted_paths = sorted(path_data, key=lambda x: x.get('average_ndvi', float('-inf')), reverse=True)

    # Get the top 3 paths
    top_3_paths = sorted_paths[:3]

    return top_3_paths

def get_top_3_quietest_paths(path_data, noise_data):
    """
    Returns the top 3 paths with the lowest average noise levels.

    Args:
        path_data (dict): Dictionary containing paths with geometry and other metadata.
        noise_data (list): List of dictionaries with 'geometry' (Polygon) and 'noise_level'.

    Returns:
        list: List of path numbers with the lowest average noise levels.
    """

    def check_noise_data_for_path(path_data, noise_data, path_length):
        total_noise = 0
        count = 0

        for index, row in noise_data.iterrows():
            noise_polygon = row['geometry']
            if path_data.intersects(noise_polygon):
                total_noise += row['noise_level']
                count += 1

        if count > 0 and path_length / count < 500:
            return total_noise / count
        else:
            return None

    def calculate_average_noise(path):
        path_geom = path['geometry']
        path_length = path['length_m']
        return check_noise_data_for_path(path_geom, noise_data, path_length)

    # Process each path
    valid_paths = []
    for path in path_data:
        avg_noise = calculate_average_noise(path)
        if avg_noise is not None:
            path['average_noise'] = avg_noise
            valid_paths.append(path)

    # Sort paths by average noise (ascending order)
    sorted_paths = sorted(valid_paths, key=lambda x: x.get('average_noise', float('inf')))

    # Check if top 3 paths exist
    if sorted_paths:
        top_3_paths = sorted_paths[:3]
        return top_3_paths
    else:
        return None
   
    return sorted_paths
