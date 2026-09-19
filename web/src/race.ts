export type Bounds = [[number, number], [number, number]];
export type PositionSample = [elapsedMs: number, longitude: number, latitude: number];
export type MotionSample = [elapsedMs: number, speedKnots: number, courseDegrees: number];

export interface EventSummary {
  slug: string;
  name: string;
  startTime: string;
  endTime: string;
}

export interface EventList {
  events: EventSummary[];
}

export interface EventMetadata {
  event: EventSummary & {
    initialBounds: Bounds;
    publicationBounds: Bounds;
    course: {
      type: 'FeatureCollection';
      features: unknown[];
    };
  };
  entries: EventEntry[];
}

export interface EventEntry {
  id: string;
  trackerNumbers: string[];
  color: string;
  boat: {
    id: string;
    sailNumber: string;
    name: string;
  };
}

export interface PositionSegment {
  positions: PositionSample[];
}

export interface EventTrack {
  entryId: string;
  segments: PositionSegment[];
  motion: MotionSample[];
}

export interface TrackResponse {
  eventSlug: string;
  tracks: EventTrack[];
}

export interface EventFixture {
  event: EventMetadata['event'];
  boat: EventEntry['boat'] & { color: string };
  positions: PositionSample[];
  positionSegments: PositionSample[][];
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
  const sample = sampleAtOrBefore(samples, elapsedMs);
  return sample && elapsedMs - sample[0] <= 5_000 ? sample : undefined;
}

export function motionAt(samples: MotionSample[], elapsedMs: number): MotionSample | undefined {
  return sampleAtOrBefore(samples, elapsedMs);
}

export function formatEventTime(epochMs: number): string {
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: 'Europe/Berlin',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(epochMs);
}
