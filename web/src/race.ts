export type Bounds = [[number, number], [number, number]];
export type PositionSample = [elapsedMs: number, longitude: number, latitude: number];
export type MotionSample = [elapsedMs: number, speedKnots: number, courseDegrees: number];

export interface RaceSummary {
  slug: string;
  name: string;
  startTime: string;
  endTime: string;
}

export interface RaceList {
  races: RaceSummary[];
}

export interface RaceMetadata {
  race: RaceSummary & {
    initialBounds: Bounds;
    course: {
      type: 'FeatureCollection';
      features: unknown[];
    };
  };
  entries: RaceEntry[];
}

export interface RaceEntry {
  id: string;
  trackerNumber: string;
  color: string;
  boat: {
    id: string;
    sailNumber: string;
    name: string;
  };
}

export interface RaceTrack {
  entryId: string;
  positions: PositionSample[];
  motion: MotionSample[];
}

export interface TrackResponse {
  raceSlug: string;
  tracks: RaceTrack[];
}

export interface RaceFixture {
  race: RaceMetadata['race'];
  boat: RaceEntry['boat'] & { color: string };
  positions: PositionSample[];
  motion: MotionSample[];
}

function sampleAtOrBefore<T extends [number, ...unknown[]]>(samples: T[], elapsedMs: number): T | undefined {
  let low = 0;
  let high = samples.length - 1;
  let result: T | undefined;

  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const sample = samples[middle];
    if (sample[0] <= elapsedMs) {
      result = sample;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }

  return result;
}

export function positionAt(samples: PositionSample[], elapsedMs: number): PositionSample | undefined {
  return sampleAtOrBefore(samples, elapsedMs);
}

export function motionAt(samples: MotionSample[], elapsedMs: number): MotionSample | undefined {
  return sampleAtOrBefore(samples, elapsedMs);
}

export function formatRaceTime(epochMs: number): string {
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: 'Europe/Berlin',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(epochMs);
}
