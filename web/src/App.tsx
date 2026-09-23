import { useEffect, useMemo, useRef, useState } from 'react';

import { MapView } from './MapView';
import {
  formatEventTime,
  motionAt,
  type EventFixture,
  type EventList,
  type EventMetadata,
  type EventSummary,
  type TrackResponse,
} from './race';

const EVENTS_URL = '/api/v1/events';
const PLAYBACK_TICK_MS = 100;
const URL_UPDATE_INTERVAL_MS = 1_000;
const LIVE_REFRESH_INTERVAL_MS = 5_000;

const TAIL_OPTIONS = [
  { value: 30_000, label: '30 Sekunden' },
  { value: 60_000, label: '1 Minute' },
  { value: 120_000, label: '2 Minuten' },
  { value: 300_000, label: '5 Minuten' },
  { value: 900_000, label: '15 Minuten' },
];

function eventIsActive(event: EventSummary, nowMs = Date.now()) {
  return Date.parse(event.startTime) <= nowMs && nowMs <= Date.parse(event.endTime);
}

function toFixture(metadata: EventMetadata, trackResponse: TrackResponse): EventFixture {
  const entry = metadata.entries[0];
  if (!entry) {
    throw new Error('Der Veranstaltung ist kein Boot zugeordnet');
  }
  const track = trackResponse.tracks.find((candidate) => candidate.entryId === entry.id);
  return {
    event: metadata.event,
    boat: { ...entry.boat, color: entry.color },
    positions: track?.segments.flatMap((segment) => segment.positions) ?? [],
    positionSegments: track?.segments.map((segment) => segment.positions) ?? [],
    motion: track?.motion ?? [],
  };
}

export default function App() {
  const [fixture, setFixture] = useState<EventFixture>();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [liveMode, setLiveMode] = useState(false);
  const [error, setError] = useState<string>();
  const [elapsedMs, setElapsedMs] = useState(0);
  const [tailMs, setTailMs] = useState(120_000);
  const [showHistory, setShowHistory] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(10);
  const lastUrlUpdateRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    async function loadEvent() {
      const listResponse = await fetch(EVENTS_URL);
      if (!listResponse.ok) {
        throw new Error(`HTTP ${listResponse.status}`);
      }
      const eventList = await listResponse.json() as EventList;
      if (eventList.events.length === 0) {
        throw new Error('Keine Veranstaltung verfügbar');
      }

      const pathMatch = window.location.pathname.match(/^\/events\/([^/]+)\/?$/);
      const isLive = window.location.pathname === '/live';
      const activeEvent = eventList.events.find((event) => eventIsActive(event));
      const slug = pathMatch
        ? decodeURIComponent(pathMatch[1])
        : (activeEvent?.slug ?? eventList.events[0].slug);
      if (!pathMatch && !isLive) {
        const url = new URL(window.location.href);
        url.pathname = `/events/${encodeURIComponent(slug)}`;
        window.history.replaceState(null, '', url);
      }

      const metadataUrl = isLive ? '/api/v1/live' : `/api/v1/events/${encodeURIComponent(slug)}`;
      const metadataResponse = await fetch(metadataUrl);
      if (!metadataResponse.ok) {
        throw new Error(`HTTP ${metadataResponse.status}`);
      }
      const metadata = await metadataResponse.json() as EventMetadata;
      const parameters = new URLSearchParams({ from: metadata.event.startTime, to: metadata.event.endTime });
      const trackUrl = isLive
        ? '/api/v1/live/tracks'
        : `/api/v1/events/${encodeURIComponent(metadata.event.slug)}/tracks?${parameters}`;
      const trackResponse = await fetch(trackUrl);
      if (!trackResponse.ok) {
        throw new Error(`HTTP ${trackResponse.status}`);
      }
      const trackResponseData = await trackResponse.json() as TrackResponse;
      return {
        events: eventList.events,
        liveMode: isLive || eventIsActive(metadata.event),
        fixture: toFixture(metadata, trackResponseData),
      };
    }

    loadEvent()
      .then((data: { events: EventSummary[]; fixture: EventFixture; liveMode: boolean }) => {
        if (cancelled) {
          return;
        }
        const startEpochMs = Date.parse(data.fixture.event.startTime);
        const durationMs = Date.parse(data.fixture.event.endTime) - startEpochMs;
        const currentElapsedMs = Math.max(0, Math.min(durationMs, Date.now() - startEpochMs));
        const requestedTime = Date.parse(new URLSearchParams(window.location.search).get('at') ?? '');
        const initialElapsedMs = Number.isFinite(requestedTime)
          ? Math.max(0, Math.min(durationMs, requestedTime - startEpochMs))
          : (data.liveMode ? currentElapsedMs : (data.fixture.positions[0]?.[0] ?? 0));
        setEvents(data.events);
        setLiveMode(data.liveMode);
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

  useEffect(() => {
    if (!liveMode || !fixture) {
      return;
    }
    const rollingLive = fixture.event.slug === 'live';
    let cancelled = false;
    const refresh = async () => {
      const metadataUrl = rollingLive
        ? '/api/v1/live'
        : `/api/v1/events/${encodeURIComponent(fixture.event.slug)}`;
      const parameters = new URLSearchParams({
        from: fixture.event.startTime,
        to: fixture.event.endTime,
      });
      const trackUrl = rollingLive
        ? '/api/v1/live/tracks'
        : `/api/v1/events/${encodeURIComponent(fixture.event.slug)}/tracks?${parameters}`;
      const metadataResponse = await fetch(metadataUrl);
      const trackResponse = await fetch(trackUrl);
      if (!metadataResponse.ok || !trackResponse.ok || cancelled) {
        return;
      }
      const metadata = await metadataResponse.json() as EventMetadata;
      const tracks = await trackResponse.json() as TrackResponse;
      const nextFixture = toFixture(metadata, tracks);
      if (!cancelled) {
        setFixture(nextFixture);
        const startMs = Date.parse(nextFixture.event.startTime);
        const durationMs = Date.parse(nextFixture.event.endTime) - startMs;
        setElapsedMs(rollingLive ? durationMs : Math.max(0, Math.min(durationMs, Date.now() - startMs)));
      }
    };
    const timer = window.setInterval(() => void refresh(), LIVE_REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [fixture?.event.slug, liveMode]);

  useEffect(() => {
    if (!fixture || fixture.event.slug === 'live') {
      return;
    }
    const updateActiveState = () => setLiveMode(eventIsActive(fixture.event));
    updateActiveState();
    const timer = window.setInterval(updateActiveState, LIVE_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [fixture?.event.endTime, fixture?.event.slug, fixture?.event.startTime]);

  const durationMs = fixture
    ? Date.parse(fixture.event.endTime) - Date.parse(fixture.event.startTime)
    : 0;

  useEffect(() => {
    if (!playing || !fixture || liveMode) {
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
  }, [durationMs, fixture, liveMode, playbackRate, playing]);

  const startEpochMs = fixture ? Date.parse(fixture.event.startTime) : 0;
  const selectedEpochMs = startEpochMs + elapsedMs;
  const motion = useMemo(
    () => (fixture ? motionAt(fixture.motion, elapsedMs) : undefined),
    [elapsedMs, fixture],
  );
  const atEnd = durationMs > 0 && durationMs - elapsedMs < 1_000;
  const rollingLive = fixture?.event.slug === 'live';

  useEffect(() => {
    if (!fixture || liveMode) {
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
  }, [fixture, liveMode, playing, selectedEpochMs]);

  if (error) {
    return (
      <main className="center-message">
        <h1>Open Sail Tracker</h1>
        <p>Die Veranstaltungsdaten konnten nicht geladen werden.</p>
        <code>{error}</code>
      </main>
    );
  }

  if (!fixture) {
    return <main className="center-message">Veranstaltung wird geladen …</main>;
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
          <p className="eyebrow">Open Sail Tracker · {liveMode ? 'Live' : 'Aufzeichnung'}</p>
          <h1>{fixture.event.name}</h1>
        </div>
        {events.length > 0 && (
          <label>
            Veranstaltung
            <select
              value={rollingLive ? '__live__' : fixture.event.slug}
              onChange={(event) => {
                const url = new URL(window.location.href);
                url.pathname = event.target.value === '__live__'
                  ? '/live'
                  : `/events/${encodeURIComponent(event.target.value)}`;
                url.searchParams.delete('at');
                window.location.assign(url);
              }}
            >
              <option value="__live__">Live</option>
              {events.map((event) => <option key={event.slug} value={event.slug}>{event.name}</option>)}
            </select>
          </label>
        )}
        <div className={`mode-badge ${liveMode || atEnd ? 'mode-badge--live' : ''}`}>
          {liveMode ? 'Live' : (atEnd ? 'Am Ende' : 'Wiedergabe')}
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

      {!liveMode && <section className="timeline panel" aria-label="Zeitsteuerung">
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
          <time>{formatEventTime(startEpochMs)}</time>
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
          <time>{formatEventTime(startEpochMs + durationMs)}</time>
        </div>
        <output className="timeline__time">{formatEventTime(selectedEpochMs)}</output>
      </section>}
    </main>
  );
}
