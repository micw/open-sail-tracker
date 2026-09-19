# Open Sail Tracker web application

This directory contains the first map and replay proof of concept for Open Sail Tracker.

## Current scope

- React and TypeScript application built with Vite;
- MapLibre GL JS map using the OpenStreetMap raster source from the MapLibre example;
- static race window from 10:50 to 12:45 local time on 19 September 2026;
- anonymized position and motion fixture from the training run;
- colored recent tail, optional gray history, and dashed gray future track;
- timeline scrubbing and accelerated playback;
- boat marker rotation only while the speed over ground is at least 0.58 knots.

The direct `tile.openstreetmap.org` source is suitable for this small proof of concept. Before public or production use, select a tile provider or self-hosted source that matches the expected traffic and comply with its usage policy and attribution requirements.

## Development

```bash
npm install
npm run dev
```

Open the URL printed by Vite.

## Production build

```bash
npm run build
npm run preview
```

The fixture contains no device identifier, SIM data, credentials, or provisioning information.

## Container

Build and run the non-root nginx image locally:

```bash
docker build -t open-sail-tracker-web:local .
docker run --rm -p 8080:8080 open-sail-tracker-web:local
```

The application is then available at `http://localhost:8080/`. The GitHub Actions workflow publishes branch, Git tag, and commit SHA images to `ghcr.io/micw/open-sail-tracker-web`.
