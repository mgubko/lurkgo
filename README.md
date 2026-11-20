# lurkgo

Static site for **LurkGo**, served by GitHub Pages at https://lurkgo.app (lurkgo.com redirects here).

- `index.html` – landing / community hub (EN, DE, RU; language picked from the browser, switch top right)
- `privacy.html`, `terms.html` – privacy policy and terms of use (linked from the app and Google Play – keep these paths)
- `osm/v1/` – prepared OpenStreetMap path data (0.01° tiles + `index.json`) that the app reads instead of the public Overpass servers; built monthly by `.github/workflows/osm-tiles.yml` from Geofabrik's Oberbayern extract with `tools/osm_tiles.py` (run it by hand via Actions → *OSM path tiles* → Run workflow, optionally with a bigger area). © OpenStreetMap contributors, ODbL
- `assets/` – logo, world cards (same images as the app's welcome screen), store screenshots, social preview image

No build step and no server: edit the HTML and push (the map data is the one generated part). Public contact is only yougosupport@gmail.com.
