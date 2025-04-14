## 📊 Data Overview

The following datasets are used in the **Zelena Sled** project to analyze and visualize the environment of Ljubljana, including vegetation, noise, temperature, and routing paths.

### 1. **ljubljana_bounding_box.csv**  
**Bounding box of Ljubljana** as defined by **OpenStreetMap**. This file outlines the geographic boundaries of Ljubljana for use in the application.

### 2. **Screenshot_example.png**  
A screenshot showing how routing looks in **Zelena Sled**. It provides a preview of the user interface and interactive map that visualizes greener and quieter paths.

### 3. **Slovenia_Osrednjeslovenska_Ljubljana.areas.geojson**  
**Noise data** downloaded from [Noise-Planet Data](https://data.noise-planet.org/noisecapture/). This geojson file contains aggregated community noise measurements in hexagonal areas across Ljubljana.

### 4. **avg_ndvi_h3_13.zip**  
**Average Normalized Difference Vegetation Index (NDVI)** computed within **H3 hexagons at resolution 13** in Ljubljana. This dataset is used to determine the level of vegetation along different paths.

### 5. **heat_h3.zip**  
**Average Land Surface Temperature (LST)** data calculated within **H3 hexagons at resolution 13** in Ljubljana. This dataset helps visualize the temperature distribution across the city, enabling users to find cooler paths.

### 6. **ljubljana_bike.graphml**  
**Graph of bike paths** in Ljubljana sourced from **OpenStreetMap**. This file provides the network of bike-friendly paths available throughout the city.

### 7. **ljubljana_walk.graphml**  
**Graph of walking paths** in Ljubljana sourced from **OpenStreetMap**. This dataset represents the network of pedestrian paths across the city for route planning.