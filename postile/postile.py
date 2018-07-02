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

from postile.sql import single_layer

# https://github.com/openstreetmap/mapnik-stylesheets/blob/master/zoom-to-scale.txt
# map width in meters for web mercator 3857
MAP_WIDTH_IN_METRES = 40075016.68557849
TILE_WIDTH_IN_PIXELS = 256.0
STANDARDIZED_PIXEL_SIZE = 0.00028

# prepare regexp to extract the query from a tm2 table subquery
LAYERQUERY = re.compile(r'\s*\((?P<query>.*)\)\s+as\s+\w+\s*', re.IGNORECASE | re.DOTALL)

# the de facto standard projection for web mapping applications
# official EPSG code
OUTPUT_SRID = 3857

app = Sanic()


class Config:
    # postgresql DSN
    dsn = 'postgres://{pguser}:{pgpassword}@{pghost}:{pgport}/{pgdatabase}'
    # tm2source prepared query
    tm2query = None
    # style configuration file
    style = None
    # database connection pool
    db = None


@app.listener('before_server_start')
async def setup_db(app, loop):
    """
    initiate postgresql connection
    """
    Config.db = await asyncpg.create_pool(Config.dsn, loop=loop)


@app.listener('after_server_stop')
async def cleanup_db(app, loop):
    await Config.db.close()


def zoom_to_scale_denom(zoom):
    map_width_in_pixels = TILE_WIDTH_IN_PIXELS * (2 ** zoom)
    return MAP_WIDTH_IN_METRES / (map_width_in_pixels * STANDARDIZED_PIXEL_SIZE)


def resolution(zoom):
    """
    Takes a web mercator zoom level and returns the pixel resolution for that
    scale according to the global TILE_WIDTH_IN_PIXELS size
    """
    return MAP_WIDTH_IN_METRES / (TILE_WIDTH_IN_PIXELS * (2 ** zoom))


def prepared_query(filename):
    with io.open(filename, 'r') as stream:
        layers = yaml.load(stream)

    queries = []
    for layer in layers['Layer']:
        # Remove whitespaces, subquery parenthesis and final alias
        query = LAYERQUERY.match(layer['Datasource']['table']).group('query')

        query = query.replace(
            layer['Datasource']['geometry_field'],
            "st_asmvtgeom({}, {{bbox}}) as mvtgeom"
            .format(layer['Datasource']['geometry_field'])
        )
        query = query.replace('!bbox!', '{bbox}')
        query = query.replace('!scale_denominator!', "{scale_denominator}")
        query = query.replace('!pixel_width!', '{pixel_width}')
        query = query.replace('!pixel_height!', '{pixel_height}')

        query = """
            select st_asmvt(tile, '{}', 4096, 'mvtgeom')
            from ({} where st_asmvtgeom({}, {{bbox}}) is not null) as tile
        """.format(layer['id'], query, layer['Datasource']['geometry_field'])

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


async def get_tile_tm2(request, x, y, z):
    """
    """
    scale_denominator = zoom_to_scale_denom(z)

    # compute mercator bounds
    bounds = mercantile.xy_bounds(x, y, z)
    bbox = f"st_makebox2d(st_point({bounds.left}, {bounds.bottom}), st_point({bounds.right},{bounds.top}))"

    sql = Config.tm2query.format(
        bbox=bbox,
        scale_denominator=scale_denominator,
        pixel_width=256,
        pixel_height=256,
    )
    logger.debug(sql)

    async with Config.db.acquire() as conn:
        # join tiles into one bytes string except null tiles
        rows = await conn.fetch(sql)
        pbf = b''.join([row[0] for row in rows if row[0]])

    return response.raw(
        pbf,
        headers={"Content-Type": "application/x-protobuf"}
    )

async def get_tile_postgis(request, x, y, z, layer):
    """
    Direct access to a postgis layer
    """
    if ' ' in layer:
        return response.text('bad layer name: {}'.format(layer), status=404)

    # get fields given in parameters
    fields = ',' + request.raw_args['fields'] if 'fields' in request.raw_args else ''
    # get geometry column name from query args else geom is used
    geom = request.raw_args.get('geom', 'geom')
    # compute mercator bounds
    bounds = mercantile.xy_bounds(x, y, z)

    # make bbox for filtering
    bbox = f"st_setsrid(st_makebox2d(st_point({bounds.left}, {bounds.bottom}), st_point({bounds.right},{bounds.top})), {OUTPUT_SRID})"

    # compute pixel resolution
    scale = resolution(z)

    sql = single_layer.format(**locals(), OUTPUT_SRID=OUTPUT_SRID)

    logger.debug(sql)

    async with Config.db.acquire() as conn:
        rows = await conn.fetch(sql)
        pbf = b''.join([row[0] for row in rows if row[0]])

    return response.raw(
        pbf,
        headers={"Content-Type": "application/x-protobuf"}
    )


def main():
    parser = argparse.ArgumentParser(description='Fast VectorTile server with PostGIS backend')
    parser.add_argument('--tm2', type=str, help='TM2 source file (yaml)')
    parser.add_argument('--style', type=str, help='GL Style to serve at /style.json')
    parser.add_argument('--pgdatabase', type=str, help='database name', default='osm')
    parser.add_argument('--pghost', type=str, help='postgres hostname', default='')
    parser.add_argument('--pgport', type=int, help='postgres port', default=5432)
    parser.add_argument('--pguser', type=str, help='postgres user', default='')
    parser.add_argument('--pgpassword', type=str, help='postgres password', default='')
    parser.add_argument('--listen', type=str, help='listen address', default='127.0.0.1')
    parser.add_argument('--listen-port', type=str, help='listen port', default=8080)
    parser.add_argument('--cors', action='store_true', help='make cross-origin AJAX possible')
    parser.add_argument('--debug', action='store_true', help='activate sanic debug mode')
    args = parser.parse_args()

    if args.tm2:
        if not os.path.exists(args.tm2):
            print(f'file does not exists: {args.tm2}')
            sys.exit(1)
        # build the SQL query for all layers found in TM2 file
        Config.tm2query = prepared_query(args.tm2)
        # add route dedicated to tm2 queries
        app.add_route(get_tile_tm2, r'/<z:int>/<x:int>/<y:int>.pbf', methods=['GET'])

    else:
        # no tm2 file given, switching to direct connection to postgis layers
        app.add_route(get_tile_postgis, r'/<layer>/<z:int>/<x:int>/<y:int>.pbf', methods=['GET'])

    Config.style = args.style

    # interpolate values for postgres connection
    Config.dsn = Config.dsn.format(**args.__dict__)

    if args.cors:
        CORS(app)

    app.run(
        host=args.listen,
        port=args.listen_port,
        debug=args.debug)


if __name__ == '__main__':
    main()
