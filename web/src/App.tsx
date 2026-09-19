import { useEffect, useMemo, useRef, useState } from 'react';

import { MapView } from './MapView';
import {
  formatRaceTime,
  motionAt,
  type RaceFixture,
  type RaceList,
  type RaceMetadata,
  type RaceSummary,
  type TrackResponse,
} from './race';

const RACES_URL = '/api/v1/races';
const PLAYBACK_TICK_MS = 100;
const URL_UPDATE_INTERVAL_MS = 1_000;

const TAIL_OPTIONS = [
  { value: 30_000, label: '30 Sekunden' },
  { value: 60_000, label: '1 Minute' },
  { value: 120_000, label: '2 Minuten' },
  { value: 300_000, label: '5 Minuten' },
  { value: 900_000, label: '15 Minuten' },
];

export default function App() {
  const [fixture, setFixture] = useState<RaceFixture>();
  const [races, setRaces] = useState<RaceSummary[]>([]);
  const [error, setError] = useState<string>();
  const [elapsedMs, setElapsedMs] = useState(0);
  const [tailMs, setTailMs] = useState(120_000);
  const [showHistory, setShowHistory] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(10);
  const lastUrlUpdateRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    async function loadRace() {
      const listResponse = await fetch(RACES_URL);
      if (!listResponse.ok) {
        throw new Error(`HTTP ${listResponse.status}`);
      }
      const raceList = await listResponse.json() as RaceList;
      if (raceList.races.length === 0) {
        throw new Error('Keine Regatta verfügbar');
      }

      const pathMatch = window.location.pathname.match(/^\/races\/([^/]+)\/?$/);
      const slug = pathMatch ? decodeURIComponent(pathMatch[1]) : raceList.races[0].slug;
      if (!pathMatch) {
        const url = new URL(window.location.href);
        url.pathname = `/races/${encodeURIComponent(slug)}`;
        window.history.replaceState(null, '', url);
      }

      const metadataResponse = await fetch(`/api/v1/races/${encodeURIComponent(slug)}`);
      if (!metadataResponse.ok) {
        throw new Error(`HTTP ${metadataResponse.status}`);
      }
      const metadata = await metadataResponse.json() as RaceMetadata;
      const parameters = new URLSearchParams({
        from: metadata.race.startTime,
        to: metadata.race.endTime,
      });
      const trackResponse = await fetch(
        `/api/v1/races/${encodeURIComponent(metadata.race.slug)}/tracks?${parameters}`,
      );
      if (!trackResponse.ok) {
        throw new Error(`HTTP ${trackResponse.status}`);
      }
      const trackResponseData = await trackResponse.json() as TrackResponse;
      const entry = metadata.entries[0];
      if (!entry) {
        throw new Error('Der Regatta ist kein Boot zugeordnet');
      }
      const track = trackResponseData.tracks.find((candidate) => candidate.entryId === entry.id);
      return {
        races: raceList.races,
        fixture: {
          race: metadata.race,
          boat: { ...entry.boat, color: entry.color },
          positions: track?.positions ?? [],
          motion: track?.motion ?? [],
        },
      };
    }

    loadRace()
      .then((data: { races: RaceSummary[]; fixture: RaceFixture }) => {
        if (cancelled) {
          return;
        }
        const startEpochMs = Date.parse(data.fixture.race.startTime);
        const durationMs = Date.parse(data.fixture.race.endTime) - startEpochMs;
        const requestedTime = Date.parse(new URLSearchParams(window.location.search).get('at') ?? '');
        const initialElapsedMs = Number.isFinite(requestedTime)
          ? Math.max(0, Math.min(durationMs, requestedTime - startEpochMs))
          : (data.fixture.positions[0]?.[0] ?? 0);
        setRaces(data.races);
        setFixture(data.fixture);
        setElapsedMs(initialElapsedMs);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : 'Unbekannter Fehler');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const durationMs = fixture
    ? Date.parse(fixture.race.endTime) - Date.parse(fixture.race.startTime)
    : 0;

  useEffect(() => {
    if (!playing || !fixture) {
      return;
    }
    const timer = window.setInterval(() => {
      setElapsedMs((current) => {
        const next = current + PLAYBACK_TICK_MS * playbackRate;
        if (next >= durationMs) {
          setPlaying(false);
          return durationMs;
        }
        return next;
      });
    }, PLAYBACK_TICK_MS);
    return () => window.clearInterval(timer);
  }, [durationMs, fixture, playbackRate, playing]);

  const startEpochMs = fixture ? Date.parse(fixture.race.startTime) : 0;
  const selectedEpochMs = startEpochMs + elapsedMs;
  const motion = useMemo(
    () => (fixture ? motionAt(fixture.motion, elapsedMs) : undefined),
    [elapsedMs, fixture],
  );
  const atEnd = durationMs > 0 && durationMs - elapsedMs < 1_000;

  useEffect(() => {
    if (!fixture) {
      return;
    }
    const now = performance.now();
    if (playing && now - lastUrlUpdateRef.current < URL_UPDATE_INTERVAL_MS) {
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set('at', new Date(selectedEpochMs).toISOString());
    window.history.replaceState(null, '', url);
    lastUrlUpdateRef.current = now;
  }, [fixture, playing, selectedEpochMs]);

  if (error) {
    return (
      <main className="center-message">
        <h1>Open Sail Tracker</h1>
        <p>Die Regattadaten konnten nicht geladen werden.</p>
        <code>{error}</code>
      </main>
    );
  }

  if (!fixture) {
    return <main className="center-message">Regattakarte wird geladen …</main>;
  }

  function togglePlayback() {
    if (atEnd) {
      setElapsedMs(fixture?.positions[0]?.[0] ?? 0);
    }
    setPlaying((current) => !current);
  }

  return (
    <main className="app-shell">
      <MapView
        fixture={fixture}
        elapsedMs={elapsedMs}
        tailMs={tailMs}
        showHistory={showHistory}
      />

      <header className="top-bar panel">
        <div>
          <p className="eyebrow">Open Sail Tracker · Aufzeichnung</p>
          <h1>{fixture.race.name}</h1>
        </div>
        {races.length > 1 && (
          <label>
            Regatta
            <select
              value={fixture.race.slug}
              onChange={(event) => {
                const url = new URL(window.location.href);
                url.pathname = `/races/${encodeURIComponent(event.target.value)}`;
                url.searchParams.delete('at');
                window.location.assign(url);
              }}
            >
              {races.map((race) => <option key={race.slug} value={race.slug}>{race.name}</option>)}
            </select>
          </label>
        )}
        <div className={`mode-badge ${atEnd ? 'mode-badge--live' : ''}`}>
          {atEnd ? 'Am Ende' : 'Wiedergabe'}
        </div>
      </header>

      <aside className="boat-panel panel">
        <div className="boat-heading">
          <span className="boat-swatch" style={{ backgroundColor: fixture.boat.color }} />
          <div>
            <strong>{fixture.boat.sailNumber}</strong>
            <span>{fixture.boat.name}</span>
          </div>
        </div>
        <dl className="boat-values">
          <div>
            <dt>Geschwindigkeit</dt>
            <dd>{motion ? `${motion[1].toFixed(1)} kn` : '–'}</dd>
          </div>
          <div>
            <dt>Kurs über Grund</dt>
            <dd>{motion && motion[1] >= 0.58 ? `${Math.round(motion[2])}°` : '–'}</dd>
          </div>
        </dl>
        <div className="legend" aria-label="Legende">
          <span><i className="legend__line legend__line--recent" />letzter Weg</span>
          <span><i className="legend__line legend__line--past" />älterer Weg</span>
          <span><i className="legend__line legend__line--future" />späterer Weg</span>
        </div>
      </aside>

      <section className="timeline panel" aria-label="Zeitsteuerung">
        <div className="timeline__controls">
          <button type="button" className="control-button control-button--primary" onClick={togglePlayback}>
            {playing ? 'Pause' : 'Abspielen'}
          </button>
          <button
            type="button"
            className="control-button"
            onClick={() => {
              setPlaying(false);
              setElapsedMs(durationMs);
            }}
            disabled={atEnd}
          >
            Zum Ende
          </button>
          <label>
            Tempo
            <select value={playbackRate} onChange={(event) => setPlaybackRate(Number(event.target.value))}>
              {[1, 2, 5, 10, 30].map((rate) => <option key={rate} value={rate}>{rate}×</option>)}
            </select>
          </label>
          <label>
            Farbiger Tail
            <select value={tailMs} onChange={(event) => setTailMs(Number(event.target.value))}>
              {TAIL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showHistory}
              onChange={(event) => setShowHistory(event.target.checked)}
            />
            Älteren Weg zeigen
          </label>
        </div>

        <div className="timeline__scrubber">
          <time>{formatRaceTime(startEpochMs)}</time>
          <input
            aria-label="Zeitpunkt"
            type="range"
            min={0}
            max={durationMs}
            step={1_000}
            value={elapsedMs}
            onChange={(event) => {
              setPlaying(false);
              setElapsedMs(Number(event.target.value));
            }}
          />
          <time>{formatRaceTime(startEpochMs + durationMs)}</time>
        </div>
        <output className="timeline__time">{formatRaceTime(selectedEpochMs)}</output>
      </section>
    </main>
  );
}
