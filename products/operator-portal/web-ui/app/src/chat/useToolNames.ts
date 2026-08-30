// Catalog-backed sanitized → canonical tool-name map for display rewriting
// (v0.27.4). The catalog is registry state, so one request per page session
// suffices; a failed fetch degrades to an empty map (text renders exactly as
// the model wrote it) and retries on the next mount.
import { useEffect, useState } from "react";
import { requestJson } from "../api/client";
import { canonicalToolNames } from "./toolNames";

interface CatalogEntry {
  name?: string;
}

let catalogPromise: Promise<Map<string, string>> | null = null;

function loadToolNameMap(): Promise<Map<string, string>> {
  if (!catalogPromise) {
    catalogPromise = requestJson<unknown>("/api/v1/tools")
      .then((payload) =>
        canonicalToolNames(
          Array.isArray(payload) ? (payload as CatalogEntry[]) : [],
        ),
      )
      .catch(() => {
        // Drop the failed promise so a later render retries after a
        // transient outage instead of caching the empty map forever.
        catalogPromise = null;
        return new Map<string, string>();
      });
  }
  return catalogPromise;
}

export function useToolNameMap(): Map<string, string> {
  const [map, setMap] = useState<Map<string, string>>(() => new Map());
  useEffect(() => {
    let active = true;
    loadToolNameMap().then((resolved) => {
      if (active) setMap(resolved);
    });
    return () => {
      active = false;
    };
  }, []);
  return map;
}
