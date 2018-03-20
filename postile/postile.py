"""
Fast VectorTile server for PostGIS backend

inspired by https://github.com/openmaptiles/postserve
"""
import io
import os
import sys
import re
import argparse

from sanic import Sanic
from sanic.log import logger
from sanic import response
from sanic_cors import CORS

import mercantile
import yaml

import asyncio
import asyncpg

app = Sanic()


class Config:
    # postgresql DSN
    dsn = 'postgres://{user}:{password}@{host}:{port}/{database}'
    # tm2source prepared query
    tm2query = None
    # style configuration file
    style = None


# https://github.com/openstreetmap/mapnik-stylesheets/blob/master/zoom-to-scale.txt
# map width in meters for web mercator 3857
MAP_WIDTH_IN_METRES = 40075016.68557849
TILE_WIDTH_IN_PIXELS = 256.0
STANDARDIZED_PIXEL_SIZE = 0.00028

# prepare regexp to extract the query from a tm2 table subquery
LAYERQUERY = re.compile(r'\s*\((?P<query>.*)\)\s+as\s+\w+\s*', re.IGNORECASE | re.DOTALL)


@app.listener('before_server_start')
async def setup_db(app, loop):
    """
    initiate postgresql connection
    """
    app.db = await asyncpg.create_pool(Config.dsn, loop=loop)


@app.listener('after_server_stop')
async def cleanup_db(app, loop):
    await app.db.close()


def zoom_to_scale_denom(zoom):
    map_width_in_pixels = TILE_WIDTH_IN_PIXELS * (2 ** zoom)
    return MAP_WIDTH_IN_METRES / (map_width_in_pixels * STANDARDIZED_PIXEL_SIZE)


def prepared_query(filename):
    with io.open(filename, 'r') as stream:
        layers = yaml.load(stream)

    queries = []
    for layer in layers['Layer']:
        # Remove whitespaces, subquery parenthesis and final alias
        query = LAYERQUERY.match(layer['Datasource']['table']).group('query')

        query = query.replace("geometry", "st_asmvtgeom(geometry, {bbox}) as mvtgeom")
        query = query.replace('!bbox!', '{bbox}')
        query = query.replace('!scale_denominator!', "{scale_denominator}")
        query = query.replace('!pixel_width!', '{pixel_width}')
        query = query.replace('!pixel_height!', '{pixel_height}')

        query = """
            select st_asmvt(tile, '%s', 4096, 'mvtgeom')
            from (%s where st_asmvtgeom(geometry, {bbox}) is not null) as tile
        """ % (layer['id'], query)

        queries.append(query)

    return " union all ".join(queries)


@app.route('/style.json')
async def get_jsonstyle(request):
    if not Config.style:
        return response.text('no style available')

    return await response.file(
        Config.style,
        headers={"Content-Type": "application/json"}
    )


@app.route(r'/tiles/<z:int>/<x:int>/<y:int>.pbf')
async def get_tile(request, x, y, z):

    scale_denominator = zoom_to_scale_denom(z)

    # compute mercator bounds
    mbounds = mercantile.xy_bounds(x, y, z)
    sqlbbox = f"st_makebox2d(st_point({mbounds.left}, {mbounds.bottom}), st_point({mbounds.right},{mbounds.top}))"

    async with request.app.db.acquire() as conn:
        st = Config.tm2query.format(
            bbox=sqlbbox,
            scale_denominator=scale_denominator,
            pixel_width=256,
            pixel_height=256,
        )
        async with conn.transaction():
            # Postgres requires non-scrollable cursors to be created
            # and used in a transaction.
            # join tiles into one bytes string except null tiles
            pbf = b''.join([rec[0] async for rec in conn.cursor(st) if rec[0]])

    return response.raw(
        pbf,
        headers={"Content-Type": "application/x-protobuf"}
    )


def main():
    parser = argparse.ArgumentParser(description='Fast VectorTile server with PostGIS backend')
    parser.add_argument('--tm2', type=str, help='TM2 source file (yaml)')
    parser.add_argument('--style', type=str, help='GL Style to serve at /style.json')
    parser.add_argument('--database', type=str, help='database name', default='osm')
    parser.add_argument('--host', type=str, help='postgres hostname', default='')
    parser.add_argument('--port', type=int, help='postgres port', default=5432)
    parser.add_argument('--user', type=str, help='postgres user', default='')
    parser.add_argument('--password', type=str, help='postgres password', default='')
    parser.add_argument('--listen', type=str, help='listen address', default='127.0.0.1')
    parser.add_argument('--listen-port', type=str, help='listen port', default=8080)
    parser.add_argument('--cors', action='store_true', help='make cross-origin AJAX possible')
    args = parser.parse_args()

    if args.tm2:
        if not os.path.exists(args.tm2):
            print(f'file does not exists: {args.tm2}')
            sys.exit(1)
        # build the SQL query for all layers found in TM2 file
        Config.tm2query = prepared_query(args.tm2)

    Config.style = args.style

    # interpolate values for postgres connection
    Config.dsn = Config.dsn.format(**args.__dict__)

    if args.cors:
        CORS(app)

    app.run(host=args.listen, port=args.listen_port)


if __name__ == '__main__':
    main()
