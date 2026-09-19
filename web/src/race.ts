export type Bounds = [[number, number], [number, number]];
export type PositionSample = [elapsedMs: number, longitude: number, latitude: number];
export type MotionSample = [elapsedMs: number, speedKnots: number, courseDegrees: number];

export interface RaceFixture {
  race: {
    id: string;
    name: string;
    startTime: string;
    endTime: string;
    initialBounds: Bounds;
  };
  boat: {
    id: string;
    sailNumber: string;
    name: string;
    color: string;
  };
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
