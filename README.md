# Postile 

[![Docker image](https://images.microbadger.com/badges/image/oslandia/postile.svg)](https://hub.docker.com/r/oslandia/postile/)

Fast Mapbox Vector Tile Server

## Features

- serve Mapbox Vector Tiles from a PostGIS backend (PostGIS >= 2.4.0)
- can read TM2Source files with postgis sources
- Connection pooling and asynchronous requests thanks to [asyncpg](https://github.com/MagicStack/asyncpg)
- tested against [openmaptiles vector tile schema](https://github.com/openmaptiles/openmaptiles)

## Installation 

**Python 3.6** is required to run Postile

    pip install cython
    pip install -e .
    postile --help

## Installation using a Docker container

Start Postile with:

    docker run --network host oslandia/postile postile --help

## Example of serving postgis layers individually

    postile --pguser **** --pgpassword **** --pgdatabase mydb --pghost localhost --listen-port 8080 --cors

Then layer `boundaries` can be served with: 

    http://localhost:8080/z/x/y.pbf?layer=boundaries&fields=id,name

`fields` is optional, and when absent only geometries are encoded in the vector tile.

---
*For a concrete example using OpenMapTiles schema see [this tutorial](https://github.com/ldgeo/postile-openmaptiles)*
