# Open Sail Tracker web application

This directory contains the first map and replay proof of concept for Open Sail Tracker.

## Current scope

- React and TypeScript application built with Vite;
- MapLibre GL JS map using the OpenStreetMap raster source from the MapLibre example;
- race metadata and bounded track data loaded through relative `/api/v1` resources;
- race selection through stable slugs in `/races/{slug}` URLs;
- local dummy API with the anonymized training fixture;
- colored recent tail, optional gray history, and dashed gray future track;
- timeline scrubbing and accelerated playback;
- boat marker rotation only while the speed over ground is at least 0.58 knots.

The direct `tile.openstreetmap.org` source is suitable for this small proof of concept. Before public or production use, select a tile provider or self-hosted source that matches the expected traffic and comply with its usage policy and attribution requirements.

## Development

```bash
npm install
npm run dev
```

Open the URL printed by Vite. The Vite development server provides the dummy API under the same relative paths used by the deployed application. Its fixture lives in `dev-data/` and is not copied into the production web bundle.

## Production build

```bash
npm run build
npm run preview
```

The development fixture contains no device identifier, SIM data, credentials, or provisioning information. `npm run preview` only previews static assets and therefore requires a separate API or reverse proxy.

## Container

Build and run the non-root nginx image locally:

```bash
docker build -t open-sail-tracker-web:local .
docker run --rm -p 8080:8080 open-sail-tracker-web:local
```

The application is then available at `http://localhost:8080/`. The GitHub Actions workflow publishes branch, Git tag, and commit SHA images to `ghcr.io/micw/open-sail-tracker-web`.
