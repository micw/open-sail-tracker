import { useEffect, useRef, useState } from 'react';
import type { FeatureCollection, LineString } from 'geojson';
import * as maplibregl from 'maplibre-gl';
import type {
  GeoJSONSource,
  LngLatBoundsLike,
  Map as MapLibreMap,
  Marker,
  StyleSpecification,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

import { motionAt, positionAt, type EventFixture } from './race';

maplibregl.setWorkerUrl(maplibreWorkerUrl);

const EMPTY_LINE: FeatureCollection<LineString> = {
  type: 'FeatureCollection',
  features: [],
};

const RASTER_STYLE: StyleSpecification = {
  version: 8,
  name: 'OpenStreetMap raster',
  sources: {
    'raster-tiles': {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      minzoom: 0,
      maxzoom: 19,
      attribution: '© OpenStreetMap-Mitwirkende',
    },
  },
  layers: [
    {
      id: 'base-map',
      type: 'raster',
      source: 'raster-tiles',
    },
  ],
};

interface MapViewProps {
  fixture: EventFixture;
  elapsedMs: number;
  tailMs: number;
  showHistory: boolean;
}

function lineFeatures(segments: [number, number][][]): FeatureCollection<LineString> {
  const visibleSegments = segments.filter((coordinates) => coordinates.length >= 2);
  if (visibleSegments.length === 0) {
    return EMPTY_LINE;
  }
  return {
    type: 'FeatureCollection',
    features: visibleSegments.map((coordinates) => ({
      type: 'Feature',
      properties: {},
      geometry: { type: 'LineString', coordinates },
    })),
  };
}

function setLines(map: MapLibreMap, sourceId: string, segments: [number, number][][]) {
  (map.getSource(sourceId) as GeoJSONSource | undefined)?.setData(lineFeatures(segments));
}

function splitTrack(
  fixture: EventFixture,
  elapsedMs: number,
  tailMs: number,
  showHistory: boolean,
) {
  const cutoff = Math.max(0, elapsedMs - tailMs);
  const history: [number, number][][] = [];
  const recent: [number, number][][] = [];

  for (const segment of fixture.positionSegments) {
    const historySegment: [number, number][] = [];
    const recentSegment: [number, number][] = [];
    let previousCoordinate: [number, number] | undefined;
    for (const [sampleTime, longitude, latitude] of segment) {
      const coordinate: [number, number] = [longitude, latitude];
      if (sampleTime < cutoff) {
        if (showHistory) {
          historySegment.push(coordinate);
        }
      } else if (sampleTime <= elapsedMs) {
        if (recentSegment.length === 0 && previousCoordinate) {
          recentSegment.push(previousCoordinate);
        }
        recentSegment.push(coordinate);
      }
      previousCoordinate = coordinate;
    }
    if (historySegment.length > 0) history.push(historySegment);
    if (recentSegment.length > 0) recent.push(recentSegment);
  }

  return { history, recent };
}

function createBoatMarker(color: string, sailNumber: string): { marker: HTMLElement; hull: HTMLElement } {
  const marker = document.createElement('div');
  marker.className = 'boat-marker';

  const label = document.createElement('span');
  label.className = 'boat-marker__label';
  label.textContent = sailNumber;

  const hull = document.createElement('span');
  hull.className = 'boat-marker__hull';
  hull.style.backgroundColor = color;

  marker.append(label, hull);
  return { marker, hull };
}

export function MapView({ fixture, elapsedMs, tailMs, showHistory }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const hullRef = useRef<HTMLElement | null>(null);
  const [styleRevision, setStyleRevision] = useState(0);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const bounds = fixture.event.initialBounds as LngLatBoundsLike;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: RASTER_STYLE,
      bounds,
      fitBoundsOptions: { padding: 48 },
      minZoom: 11,
      maxPitch: 0,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      cooperativeGestures: false,
      attributionControl: { compact: true },
    });

    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();
    map.scrollZoom.setWheelZoomRate(1 / 600);
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 120 }), 'bottom-right');

    map.once('load', () => {
      const initialTrack = splitTrack(fixture, elapsedMs, tailMs, showHistory);
      const completeTrack = fixture.positionSegments.map(
        (segment) => segment.map(
          ([, longitude, latitude]): [number, number] => [longitude, latitude],
        ),
      );
      map.addSource('track-complete', { type: 'geojson', data: lineFeatures(completeTrack) });
      map.addSource('track-history', { type: 'geojson', data: lineFeatures(initialTrack.history) });
      map.addSource('track-recent', { type: 'geojson', data: lineFeatures(initialTrack.recent) });

      map.addLayer({
        id: 'track-future',
        type: 'line',
        source: 'track-complete',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#6d7881',
          'line-opacity': 0.5,
          'line-width': 1,
          'line-dasharray': [2, 2],
        },
      });
      map.addLayer({
        id: 'track-history',
        type: 'line',
        source: 'track-history',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#58636b',
          'line-opacity': 1,
          'line-width': 1,
        },
      });
      map.addLayer({
        id: 'track-recent',
        type: 'line',
        source: 'track-recent',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': fixture.boat.color,
          'line-opacity': 1,
          'line-width': 3,
        },
      });

      const boatElement = createBoatMarker(fixture.boat.color, fixture.boat.sailNumber);
      hullRef.current = boatElement.hull;
      markerRef.current = new maplibregl.Marker({ element: boatElement.marker, anchor: 'center' });
      setStyleRevision((revision) => revision + 1);
    });

    mapRef.current = map;
    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      hullRef.current = null;
      mapRef.current = null;
      map.remove();
    };
  }, [fixture]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || styleRevision === 0) {
      return;
    }

    const track = splitTrack(fixture, elapsedMs, tailMs, showHistory);
    setLines(map, 'track-history', track.history);
    setLines(map, 'track-recent', track.recent);

    const position = positionAt(fixture.positions, elapsedMs);
    if (!position) {
      markerRef.current?.remove();
      return;
    }

    markerRef.current?.setLngLat([position[1], position[2]]).addTo(map);
    const motion = motionAt(fixture.motion, elapsedMs);
    const hasUsefulCourse = motion && motion[1] >= 0.58;
    if (hullRef.current) {
      const rotation = hasUsefulCourse ? motion[2] - 90 : 0;
      hullRef.current.style.transform = `rotate(${rotation}deg)`;
      hullRef.current.classList.toggle('boat-marker__hull--stationary', !hasUsefulCourse);
    }
  }, [elapsedMs, fixture, showHistory, styleRevision, tailMs]);

  return <div ref={containerRef} className="map" aria-label="Veranstaltungskarte" />;
}
