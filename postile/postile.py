"""
Fast VectorTile server for PostGIS backend

inspired by https://github.com/openmaptiles/postserve
"""
import io
import os
import sys
import re
import argparse
import time

from sanic import Sanic
from sanic.log import logger
from sanic import response
from sanic_cors import CORS

import mercantile
import yaml

from mercantile import Bbox

import asyncio
import asyncpg

from postile.sql import single_layer

# map_bbox = Bbox(
#     -20037508.342789244,
#     -20037508.342789244,
#     20037508.342789244,
#     20037508.342789244,
# )
# # the de facto standard projection for web mapping applications
# # official EPSG code
# output_srid = 3857

output_srid = "3949"
map_bbox = Bbox(
    1643204.5199999844,
    8171564.31999849, # square 8179445.318998469,
    1661111.5199999844,
    8189471.31999849,
)

# https://github.com/openstreetmap/mapnik-stylesheets/blob/master/zoom-to-scale.txt
# map width in meters for web mercator 3857
MAP_WIDTH_IN_METRES = map_bbox.right - map_bbox.left
TILE_WIDTH_IN_PIXELS = 256.0
STANDARDIZED_PIXEL_SIZE = 0.00028

# prepare regexp to extract the query from a tm2 table subquery
LAYERQUERY = re.compile(
    r"\s*\((?P<query>.*)\)\s+as\s+\w+\s*", re.IGNORECASE | re.DOTALL
)

app = Sanic()


class Config:
    # postgresql DSN
    dsn = "postgres://{pguser}:{pgpassword}@{pghost}:{pgport}/{pgdatabase}"
    # tm2source prepared query
    tm2query = None
    auto_tm2_ts = None
    # style configuration file
    style = None
    # database connection pool
    db = None


@app.listener("before_server_start")
async def setup_db(app, loop):
    """
    initiate postgresql connection
    """
    Config.db = await asyncpg.create_pool(Config.dsn, loop=loop)


@app.listener("after_server_stop")
async def cleanup_db(app, loop):
    await Config.db.close()


def zoom_to_scale_denom(zoom):
    map_width_in_pixels = TILE_WIDTH_IN_PIXELS * (2 ** zoom)
    return MAP_WIDTH_IN_METRES / (map_width_in_pixels * STANDARDIZED_PIXEL_SIZE)


def resolution(map_width_in_metres, zoom):
    """
    Takes a web mercator zoom level and returns the pixel resolution for that
    scale according to the global TILE_WIDTH_IN_PIXELS size
    """
    return map_width_in_metres / (TILE_WIDTH_IN_PIXELS * (2 ** zoom))


def prepared_query(filename):
    if type(filename) == 'str':
        with io.open(filename, "r") as stream:
            layers = yaml.load(stream)
    else:
        layers = filename

    queries = []
    for layer in layers["Layer"]:
        # Remove whitespaces, subquery parenthesis and final alias
        query = LAYERQUERY.match(layer["Datasource"]["table"]).group("query")

        query = query.replace(
            layer["Datasource"]["geometry_field"],
            "st_asmvtgeom(st_intersection({}, {{bbox}}), {{bbox}}) as mvtgeom".format(
                layer["Datasource"]["geometry_field"]
            ),
        )
        query = query.replace("!bbox!", "{bbox}")
        query = query.replace("!scale_denominator!", "{scale_denominator}")
        query = query.replace("!pixel_width!", "{pixel_width}")
        query = query.replace("!pixel_height!", "{pixel_height}")
        query = query.replace("!min_length!", "{min_length}")

        query = """
            select st_asmvt(tile, '{}', 4096, 'mvtgeom')
            from ({} where st_asmvtgeom(st_intersection({}, {{bbox}}), {{bbox}}) is not null) as tile
        """.format(
            layer["id"], query, layer["Datasource"]["geometry_field"]
        )

        queries.append(query)

    return " union all ".join(queries)


@app.route("/style.json")
async def get_jsonstyle(request):
    if not Config.style:
        return response.text("no style available")

    return await response.file(
        Config.style, headers={"Content-Type": "application/json"}
    )

def sql_bbox(x, y, z, output_srid = None):
    if output_srid is None:
        bounds = mercantile.xy_bounds(x, y, z)
        return ("st_makebox2d(st_point({bounds.left}, {bounds.bottom}), st_point({bounds.right},{bounds.top}))".format(**locals()), 0)

    # compute mercator bounds
    tile_count = pow(2, z)
    tile_width_in_metres = (map_bbox.right - map_bbox.left) / tile_count
    tile_height_in_metres = (map_bbox.top - map_bbox.bottom) / tile_count

    left = map_bbox.left + x * tile_width_in_metres
    right = map_bbox.left + (x + 1) * tile_width_in_metres
    top = map_bbox.top - y * tile_height_in_metres
    bottom = map_bbox.top - (y + 1) * tile_height_in_metres
    # bounds = mercantile.xy_bounds(x, y, z)
    bounds = Bbox(left, bottom, right, top)

    return ("st_setsrid(st_makebox2d(st_point({bounds.left}, {bounds.bottom}), st_point({bounds.right},{bounds.top})), {output_srid})".format(**locals()), tile_width_in_metres / 50.0)


async def get_tile_tm2(request, x, y, z):
    """
    """
    scale_denominator = zoom_to_scale_denom(z)

    # compute mercator bounds
    bbox, min_length = sql_bbox(x, y, z, '3949')

    if Config.tm2query == None or (time.monotonic() - Config.auto_tm2_ts) > 10:
        # build it
        async with Config.db.acquire() as conn:
            rows = await conn.fetch("select table_name from INFORMATION_SCHEMA.COLUMNS where COLUMN_NAME like 'geom'")
            table_names = [r['table_name'] for r in rows]
            sources = []
            for table in table_names:
                if '3949' not in table:
                    continue
                source = {
                    'Datasource': {
                        'geometry_field': 'geom',
                        'table': '(select geom from layer_{}(!bbox!::box2d, !min_length!::float)) AS t'.format(table)
                    },
                    'id': table
                }
                sources += [source]
            Config.tm2query = prepared_query({ 'Layer': sources })
            Config.auto_tm2_ts = time.monotonic()

    sql = Config.tm2query.format(
        bbox=bbox,
        scale_denominator=scale_denominator,
        pixel_width=256,
        pixel_height=256,
        min_length=min_length,
    )
    print(sql)
    logger.debug(sql)

    async with Config.db.acquire() as conn:
        # join tiles into one bytes string except null tiles
        rows = await conn.fetch(sql)
        pbf = b"".join([row[0] for row in rows if row[0]])

    return response.raw(pbf, headers={"Content-Type": "application/x-protobuf"})


async def get_tile_postgis(request, x, y, z, layer):
    """
    Direct access to a postgis layer
    """
    if " " in layer:
        return response.text("bad layer name: {}".format(layer), status=404)

    # get fields given in parameters
    fields = "," + request.raw_args["fields"] if "fields" in request.raw_args else ""
    # get geometry column name from query args else geom is used
    geom = request.raw_args.get("geom", "geom")
    # make bbox for filtering
    output_srid = '3949'
    bbox, min_length = sql_bbox(x, y, z, output_srid)

    # compute pixel resolution
    scale = resolution((map_bbox.right - map_bbox.left), z)

    sql = single_layer.format(**locals(), OUTPUT_SRID=output_srid)

    logger.debug(sql)
    print(sql)

    async with Config.db.acquire() as conn:
        rows = await conn.fetch(sql)
        pbf = b"".join([row[0] for row in rows if row[0]])

    return response.raw(pbf, headers={"Content-Type": "application/x-protobuf"})


def main():
    parser = argparse.ArgumentParser(
        description="Fast VectorTile server with PostGIS backend"
    )
    parser.add_argument("--tm2", type=str, help="TM2 source file (yaml)")
    parser.add_argument("--style", type=str, help="GL Style to serve at /style.json")
    parser.add_argument("--pgdatabase", type=str, help="database name", default="osm")
    parser.add_argument("--pghost", type=str, help="postgres hostname", default="")
    parser.add_argument("--pgport", type=int, help="postgres port", default=5432)
    parser.add_argument("--pguser", type=str, help="postgres user", default="")
    parser.add_argument("--pgpassword", type=str, help="postgres password", default="")
    parser.add_argument(
        "--listen", type=str, help="listen address", default="127.0.0.1"
    )
    parser.add_argument("--listen-port", type=str, help="listen port", default=8080)
    parser.add_argument(
        "--cors", action="store_true", help="make cross-origin AJAX possible"
    )
    parser.add_argument(
        "--debug", action="store_true", help="activate sanic debug mode"
    )
    args = parser.parse_args()

    if args.tm2:
        if args.tm2 != 'auto':
            if not os.path.exists(args.tm2):
                print("file does not exists: {args.tm2}".format(**locals()))
                sys.exit(1)
            else:
                # build the SQL query for all layers found in TM2 file
                Config.tm2query = prepared_query(args.tm2)
        # add route dedicated to tm2 queries
        app.add_route(get_tile_tm2, r"/<z:int>/<x:int>/<y:int>.pbf", methods=["GET"])

    else:
        # no tm2 file given, switching to direct connection to postgis layers
        app.add_route(
            get_tile_postgis, r"/<layer>/<z:int>/<x:int>/<y:int>.pbf", methods=["GET"]
        )

    Config.style = args.style

    # interpolate values for postgres connection
    Config.dsn = Config.dsn.format(**args.__dict__)

    if args.cors:
        CORS(app)

    app.run(host=args.listen, port=args.listen_port, debug=args.debug)


if __name__ == "__main__":
    main()
