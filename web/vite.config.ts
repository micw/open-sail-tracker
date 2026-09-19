import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

interface Fixture {
  race: {
    id: string;
    name: string;
    startTime: string;
    endTime: string;
    initialBounds: [[number, number], [number, number]];
  };
  boat: { id: string; sailNumber: string; name: string; color: string };
  positions: [number, number, number][];
  motion: [number, number, number][];
}

const PUBLICATION_BOUNDS: [[number, number], [number, number]] = [
  [12.236718465054931, 51.296003387362596],
  [12.258043783104087, 51.31842232597056],
];

function dummyApi(): Plugin {
  const directory = path.dirname(fileURLToPath(import.meta.url));
  const fixture = JSON.parse(
    fs.readFileSync(path.join(directory, 'dev-data/training-2026-09-19.json'), 'utf8'),
  ) as Fixture;
  const slug = fixture.race.id;
  const summary = {
    slug,
    name: fixture.race.name,
    startTime: fixture.race.startTime,
    endTime: fixture.race.endTime,
  };
  const entry = {
    id: 'test-entry',
    trackerNumbers: ['01'],
    color: fixture.boat.color,
    boat: {
      id: fixture.boat.id,
      sailNumber: fixture.boat.sailNumber,
      name: fixture.boat.name,
    },
  };

  return {
    name: 'open-sail-tracker-dummy-api',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const url = new URL(request.url ?? '/', 'http://localhost');
        const sendJson = (status: number, value: object) => {
          response.statusCode = status;
          response.setHeader('Content-Type', 'application/json; charset=utf-8');
          response.setHeader('Cache-Control', 'no-store');
          response.end(JSON.stringify(value));
        };

        if (request.method !== 'GET' || !url.pathname.startsWith('/api/v1/events')) {
          next();
          return;
        }
        if (url.pathname === '/api/v1/events') {
          sendJson(200, { events: [summary] });
          return;
        }
        if (url.pathname === `/api/v1/events/${slug}`) {
          sendJson(200, {
            event: {
              ...summary,
              initialBounds: fixture.race.initialBounds,
              publicationBounds: PUBLICATION_BOUNDS,
              course: { type: 'FeatureCollection', features: [] },
            },
            entries: [entry],
          });
          return;
        }
        if (url.pathname !== `/api/v1/events/${slug}/tracks`) {
          sendJson(404, { error: 'not_found' });
          return;
        }

        const requestedStart = Date.parse(url.searchParams.get('from') ?? '');
        const requestedEnd = Date.parse(url.searchParams.get('to') ?? '');
        if (!Number.isFinite(requestedStart) || !Number.isFinite(requestedEnd) || requestedStart > requestedEnd) {
          sendJson(400, { error: 'invalid_query' });
          return;
        }

        const eventStart = Date.parse(fixture.race.startTime);
        const eventEnd = Date.parse(fixture.race.endTime);
        const start = Math.max(requestedStart, eventStart);
        const end = Math.min(requestedEnd, eventEnd);
        if (start > end) {
          sendJson(200, { eventSlug: slug, tracks: [] });
          return;
        }
        const inRange = (sample: [number, ...number[]]) => {
          const timestamp = eventStart + sample[0];
          return timestamp >= start && timestamp <= end;
        };
        const segments: { positions: [number, number, number][] }[] = [];
        let current: [number, number, number][] = [];
        for (const sample of fixture.positions) {
          const [, longitude, latitude] = sample;
          const [[west, south], [east, north]] = PUBLICATION_BOUNDS;
          const visible = inRange(sample)
            && longitude >= west && longitude <= east
            && latitude >= south && latitude <= north;
          if (visible) {
            current.push(sample);
          } else if (current.length > 0) {
            segments.push({ positions: current });
            current = [];
          }
        }
        if (current.length > 0) segments.push({ positions: current });

        sendJson(200, {
          eventSlug: slug,
          tracks: [{
            entryId: entry.id,
            segments,
            motion: fixture.motion.filter(inRange),
          }],
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), dummyApi()],
  server: {
    allowedHosts: true,
  },
});
