Detailed country outlines for the Where map. Each country loads separately at zoom level 5 and above; the smaller 1:110m outlines in `_data/recording_countries.json` remain in use for the world view. Names, codes, and flags match that overview dataset. Coordinates are rounded to five decimal places.

Most countries use [Natural Earth 1:10m Admin 0 Countries](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/), selected by `ADM0_A3` from the [source GeoJSON](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson). Natural Earth data is [public domain](https://www.naturalearthdata.com/about/terms-of-use/).

The Slovenia road trip uses additional detail to follow the Adriatic coast:

| File | Source | License |
| --- | --- | --- |
| `HRV.geojson` | OpenStreetMap contributors / Wambacher, via [geoBoundaries Croatia ADM0](https://www.geoboundaries.org/api/current/gbOpen/HRV/ADM0/) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| `ITA.geojson` | © ISTAT, via [geoBoundaries Italy ADM0](https://www.geoboundaries.org/api/current/gbOpen/ITA/ADM0/) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |
| `SVN.geojson` | OpenStreetMap contributors / Wambacher, via [geoBoundaries Slovenia ADM2](https://www.geoboundaries.org/api/current/gbOpen/SVN/ADM2/), and OpenStreetMap coastline | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |

These files contain modified source data and retain the licenses above. Their source credits are also displayed in the map attribution when loaded. geoBoundaries source files are pinned to revision `9469f09` in the [geoBoundaries repository](https://github.com/wmgeolab/geoBoundaries/tree/9469f09/releaseData/gbOpen).

Preparation: dissolve each source's features into one country geometry, simplify with topology preserved at a tolerance of 0.0001 degrees, and round coordinates to five decimals. Italy uses a topology-preserving precision grid of 0.00001 degrees before rounding to prevent collapsed rings. For Slovenia, dissolve the municipal boundaries, remove the sea using OpenStreetMap coastline, then simplify. Municipal boundaries include maritime territory, which should not be shaded as land. The sea mask is the polygon containing `(13.4, 45.55)` after polygonizing coastline with the bounding box `(13.3, 45.35, 13.95, 45.8)`.

Coastline was downloaded from `https://overpass-api.de/api/interpreter` with this query:

```text
[out:json][timeout:20];way["natural"="coastline"](45.35,13.3,45.8,13.95);out geom;
```

Data downloaded November 6, 2026.
