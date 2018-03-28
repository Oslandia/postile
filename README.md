# Postile 

[![Docker Automated build](https://img.shields.io/docker/automated/oslandia/postile.svg)]()
[![Docker Pulls](https://img.shields.io/docker/pulls/oslandia/postile.svg)]()

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

## Example of serving one table from postgis

    postile --pguser **** --pgpassword **** --pgdatabase mydb --pghost localhost --listen-port 8080 --cors

Then all postgis layers in database `mydb` can be served with: 

    http://localhost:8080/z/x/y.pbf?layer=boundaries&fields=id,name


---
*For a concrete example using OpenMapTiles schema see [this tutorial](https://github.com/ldgeo/postile-openmaptiles)*
