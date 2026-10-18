import { useEffect } from "react";
import { useMap } from "react-leaflet";

export const OSM_TILES = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

export const wellMarker = {
  color: "#d4652f",
  fillColor: "#f6f3ee",
  fillOpacity: 0.95,
  weight: 2,
} as const;

/** Leaflet measures the container before layout. Recalculate once it has a size. */
export function MapReady() {
  const map = useMap();
  useEffect(() => {
    const id = requestAnimationFrame(() => map.invalidateSize());
    return () => cancelAnimationFrame(id);
  }, [map]);
  return null;
}
