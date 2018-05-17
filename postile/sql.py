"""
Module containing SQL raw requests
"""


single_layer = """
select st_asmvt(tile, '{layer}', 4096)
from (
    with tmp as (
        select st_srid({geom}) as srid
        from {layer}
        limit 1
    ) select * from tmp
    , lateral (
        select
            st_asmvtgeom(
                st_simplify(
                    st_transform({geom}, {OUTPUT_SRID})
                    , {scale}, true
                )
            , {bbox}) as mvtgeom
            {fields}
        from {layer}
        where st_transform({bbox}, tmp.srid) && {geom}
    ) _ where mvtgeom is not null
) as tile
"""
