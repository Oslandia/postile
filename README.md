# Postile 

Fast Mapbox Vector Tile Server

## Features

- serve Mapbox Vector Tiles from a PostGIS backend (PostGIS >= 2.4.0)
- can read TM2Source files with postgis sources
- Connection pooling and asynchronous requests thanks to [asyncpg](https://github.com/MagicStack/asyncpg)
- tested against [openmaptiles vector tile schema](https://github.com/openmaptiles/openmaptiles)

## Installation 

**Python 3.6** is required to run Postile

    pip install cython
    pip install -r requirements.txt

## Usage 

    postile --help

