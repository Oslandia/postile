# PosTile 

[![Docker image](https://images.microbadger.com/badges/image/oslandia/postile.svg)](https://hub.docker.com/r/oslandia/postile/)

Fast Mapbox Vector Tile Server

## Features

- serve Mapbox Vector Tiles from a PostGIS backend 
- can read TM2 file data sources with postgis 
- can serve PostGIS layers individually 
- handle on-the-fly reprojection to web mercator projection (only for single layers, not tm2 sources)
- Connection pooling and asynchronous requests thanks to [asyncpg](https://github.com/MagicStack/asyncpg)
- tested with [openmaptiles vector tile schema](https://github.com/openmaptiles/openmaptiles)

## Requires 

- features stored with PostGIS >= 2.4.0

## Installation 

**Python 3.6** is required to run Postile

    pip install cython
    pip install -e .
    postile --help

## Using a Docker container

Start Postile with:

    docker run --network host oslandia/postile postile --help

## Example of serving postgis layers individually

    postile --pguser **** --pgpassword **** --pgdatabase mydb --pghost localhost --listen-port 8080 --cors

Then layer `boundaries` can be served with: 

    http://localhost:8080/boundaries/z/x/y.pbf?fields=id,name

`fields` is optional, and when absent only geometries are encoded in the vector tile.

---
*For a concrete example using OpenMapTiles schema see [this tutorial](https://github.com/ldgeo/postile-openmaptiles)*
