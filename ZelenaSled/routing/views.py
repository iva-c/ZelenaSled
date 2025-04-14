import json
from itertools import islice
import os
from itertools import combinations
import traceback

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
    return render(request, 'index.html') 


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

def add_noise_to_edges(G_digraph, noise_data):
    """
    Adds noise data to the edges of a directed graph.
    
    Args:
        G_digraph (nx.DiGraph): The directed graph to which noise data will be added.
        noise_data (gpd.GeoDataFrame): GeoDataFrame containing noise data with 'geometry' and 'noise_level'.
    """

    edges_gdf = ox.graph_to_gdfs(G_digraph, nodes=False, edges=True)
    edges_with_noise = gpd.sjoin(edges_gdf, noise_data[['laeq', 'geometry']], how='left', predicate='intersects')
    noise_per_edge = edges_with_noise.groupby(['u', 'v', 'key'])['laeq'].mean().reset_index()

    # Attach averaged noise back to the graph
    for _, row in noise_per_edge.iterrows():
        u, v, key = row['u'], row['v'], row['key']
        G_digraph[u][v][key]['noise'] = row['laeq']

    return G_digraph
#46.060936 14.528119
#46.052540 14.532967
def convert_to_digraph_by_combined_weight(G_multi, alpha=0.5, beta=0.5):
    G_simple = nx.DiGraph()
    G_simple.graph["crs"] = "EPSG:4326"

    # Copy all nodes with their attributes
    for node, attrs in G_multi.nodes(data=True):
        G_simple.add_node(node, **attrs)

    # Process edges, keeping only the best one (lowest combined weight)
    for u, v, data in G_multi.edges(data=True):
        length = data.get("length", 0)
        noise = data.get("noise", 0)
        combined = alpha * length + beta * noise

        edge_attrs = data.copy()
        edge_attrs["combined"] = combined

        if G_simple.has_edge(u, v):
            if combined < G_simple[u][v]["combined"]:
                G_simple[u][v].update(edge_attrs)
        else:
            G_simple.add_edge(u, v, **edge_attrs)

    return G_simple

def assign_average_noise(G):
    # Collect all valid noise values that exist in the graph (excluding 'nan' values)
    noise_values = [d['noise'] for u, v, d in G.edges(data=True) if 'noise' in d]

    # Remove 'nan' values from the list (if there are any)
    valid_noise_values = [noise for noise in noise_values if not np.isnan(noise)]

    # Check if we have any valid noise values
    if valid_noise_values:
        average_noise = np.mean(valid_noise_values)
    else:
        average_noise = 80  # Set default noise value if no valid data found

    for u, v, d in G.edges(data=True):
        if 'noise' not in d or np.isnan(d['noise']):
            d['noise'] = average_noise

    return G


# # Load the graph once when the server starts
# G_multi_walk = convert_to_digraph(ox.load_graphml(os.path.join(settings.BASE_DIR, 'routing', 'data','ljubljana_walk.graphml')))
# G_multi_bike= convert_to_digraph(ox.load_graphml(os.path.join(settings.BASE_DIR, 'routing', 'data','ljubljana_bike.graphml')))

G_multi_walk = ox.load_graphml(os.path.join(settings.BASE_DIR, 'routing', 'data','ljubljana_walk.graphml'))
G_multi_bike= ox.load_graphml(os.path.join(settings.BASE_DIR, 'routing', 'data','ljubljana_bike.graphml'))

#add noise data
noise_data = gpd.read_file(os.path.join(settings.BASE_DIR, 'routing', 'data','Slovenia_Osrednjeslovenska_Ljubljana.areas.geojson'))

G_multi_walk = add_noise_to_edges(G_multi_walk, noise_data)
G_multi_bike = add_noise_to_edges(G_multi_bike, noise_data)

G_multi_walk = assign_average_noise(G_multi_walk)
G_multi_bike = assign_average_noise(G_multi_bike)

G_multi_walk = convert_to_digraph_by_combined_weight(G_multi_walk, alpha=0.6, beta=0.4)
G_multi_bike = convert_to_digraph_by_combined_weight(G_multi_bike, alpha=0.6, beta=0.4)


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



            if routing_mode == "noise":
                paths_generator = nx.shortest_simple_paths(G_graph, orig_node, dest_node, weight='combined')
                candidate_paths = list(islice(paths_generator, 25))
                best_3_paths = get_different_paths(candidate_paths)
                if not best_3_paths:
                    return JsonResponse({"error": "Not enough noise data between chosen locations to estimate the best path"}, status=400)
                
                path_data = []
                for i, path in enumerate(best_3_paths):
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
                gdf_paths = gpd.GeoDataFrame(path_data, crs="EPSG:4326")
        


            else:
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

                elif routing_mode == "heat":
                    with open(os.path.join(settings.BASE_DIR, 'routing', 'data','heat_h3.json'), 'r') as f:
                        ndvi_h3 = json.load(f)

                    path_data = get_top_3_ndvi(path_data, ndvi_h3)

                # elif routing_mode == "noise":
                #     noise_data = gpd.read_file(os.path.join(settings.BASE_DIR, 'routing', 'data','Slovenia_Osrednjeslovenska_Ljubljana.areas.geojson'))

                #     path_data = get_top_3_quietest_paths(path_data, noise_data)

                #     if not path_data:
                #         return JsonResponse({"error": "Not enough noise data between chosen locations to estimate the best path"}, status=400)

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
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


def get_different_paths(path_data):

    """
    Returns shortest paths that are the most different

    Args:
        path_data (dict): List of 15 paths.

    Returns:
        list: List of path numbers that are the most different.
    """

    def dissimilarity(path1, path2):
        set1, set2 = set(path1), set(path2)
        return 1 - len(set1 & set2) / len(set1 | set2)
    
    dissimilarity_scores = []

    for combo in combinations(path_data, 3):
        # Calculate dissimilarities for the three paths
        d1 = dissimilarity(combo[0], combo[1])
        d2 = dissimilarity(combo[0], combo[2])
        d3 = dissimilarity(combo[1], combo[2])
        
        # Total dissimilarity score for the combination
        total_dissimilarity = d1 + d2 + d3
        
        # Store the combination and its dissimilarity score
        dissimilarity_scores.append((combo, total_dissimilarity))

    # Find the combination with the highest dissimilarity
    best_combo, best_score = max(dissimilarity_scores, key=lambda x: x[1])
    
    return best_combo




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
    
    def get_most_different_paths(path_data):
        
        def dissimilarity(path1, path2):
            set1, set2 = set(path1), set(path2)
            return 1 - len(set1 & set2) / len(set1 | set2)

        # Calculate dissimilarity scores for all combinations of paths
        dissimilarity_scores = []
        for combo in combinations(path_data, 3):
            d1 = dissimilarity(combo[0]['coordinates'], combo[1]['coordinates'])
            d2 = dissimilarity(combo[0]['coordinates'], combo[2]['coordinates'])
            d3 = dissimilarity(combo[1]['coordinates'], combo[2]['coordinates'])
            total_dissimilarity = d1 + d2 + d3
            dissimilarity_scores.append((combo, total_dissimilarity))

        # Find the combination with the highest dissimilarity
        best_combo, best_score = max(dissimilarity_scores, key=lambda x: x[1])
        
        return best_combo

    # Calculate NDVI for each path
    for path in path_data:
        avg_ndvi = calculate_average_ndvi(path)
        path['average_ndvi'] = avg_ndvi   # Add average NDVI to path data

    #get most different paths

    # Sort the paths by average NDVI in descending order
    sorted_paths = sorted(path_data, key=lambda x: x.get('average_ndvi', float('-inf')), reverse=True)
    
    #get most different out of top 10

    most_different_paths = get_most_different_paths(sorted_paths[:10])

    #get most different paths:
    #get the list of paths


    # Get the top 3 paths
    #top_3_paths = sorted_paths[:3]


    #return top_3_paths
    return most_different_paths

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
            path['la50'] = avg_noise
            valid_paths.append(path)

    # Sort paths by average noise (ascending order)
    sorted_paths = sorted(valid_paths, key=lambda x: x.get('la50', float('inf')))

    # Check if top 3 paths exist
    if sorted_paths:
        top_3_paths = sorted_paths[:3]
        return top_3_paths
    else:
        return None
   
    return sorted_paths
