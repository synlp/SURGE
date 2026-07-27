(function () {
  "use strict";

  const defaults = {
    mode: "static",
    apiBaseUrl: "",
    snapshotUrl: "data/events-v9-1.json",
    catalogUrl: "data/event-catalog-v1.json",
    eventDetailBaseUrl: "data/event-details-v1",
    requestTimeoutMs: 10000,
    endpoints: {
      events: "/api/v1/events",
      catalog: "/api/v1/events",
      event: "/api/v1/events/{eventId}",
      analysis: "/api/v1/events/{eventId}/analysis",
      stream: "/api/v1/events/{eventId}/stream"
    }
  };
  const supplied = window.SURGE_RUNTIME_CONFIG || {};
  const config = {
    ...defaults,
    ...supplied,
    endpoints: { ...defaults.endpoints, ...(supplied.endpoints || {}) }
  };
  let snapshotPromise = null;
  const eventPromises = new Map();

  const endpoint = (name, eventId) => {
    const template = config.endpoints[name];
    const path = template.replace("{eventId}", encodeURIComponent(eventId || ""));
    return `${String(config.apiBaseUrl || "").replace(/\/$/, "")}${path}`;
  };

  async function requestJson(url) {
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      Number(config.requestTimeoutMs) || 10000
    );
    try {
      const response = await fetch(url, {
        cache: "no-cache",
        headers: { Accept: "application/json" },
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`request failed: ${response.status}`);
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function getSnapshot() {
    if (!snapshotPromise) {
      snapshotPromise = (async () => {
        if (config.mode === "api") return requestJson(endpoint("events"));
        if (window.SURGE_LIVE_DATA) return window.SURGE_LIVE_DATA;
        return requestJson(config.snapshotUrl);
      })();
    }
    return snapshotPromise;
  }

  async function listEvents() {
    const payload = await getSnapshot();
    if (!payload || !Array.isArray(payload.events)) {
      throw new Error("event response does not contain an events array");
    }
    return payload;
  }

  function snapshotCatalog(payload) {
    return {
      schemaVersion: "surge-live-event-catalog-v1",
      generatedAt: payload.generatedAt,
      source: "published_snapshot_fallback",
      partial: true,
      events: (payload.events || []).map(event => ({
        id: event.id,
        sourceEventId: event.sourceEventId,
        title: event.title,
        category: event.category,
        summary: event.summary,
        status: "analysis_ready",
        postCount: Number(event.sourcePostCount || 0),
        updatedAt: payload.generatedAt,
        analysisHref: `event.html?id=${encodeURIComponent(event.id)}`
      }))
    };
  }

  async function getCatalog(options = {}) {
    let payload;
    if (config.mode === "api") {
      const url = new URL(endpoint("catalog"), window.location.href);
      Object.entries(options).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          url.searchParams.set(key, value);
        }
      });
      payload = await requestJson(url.toString());
    } else {
      if (window.SURGE_EVENT_CATALOG) {
        payload = window.SURGE_EVENT_CATALOG;
      } else {
        try {
          payload = await requestJson(config.catalogUrl);
        } catch (error) {
          payload = snapshotCatalog(await getSnapshot());
        }
      }
    }
    if (!payload || !Array.isArray(payload.events)) {
      throw new Error("catalog response does not contain an events array");
    }
    return payload;
  }

  async function getEvent(eventId) {
    if (!eventId) throw new Error("eventId is required");
    if (config.mode === "api") return requestJson(endpoint("event", eventId));
    if (!eventPromises.has(eventId)) {
      eventPromises.set(eventId, (async () => {
        try {
          const base = String(config.eventDetailBaseUrl || "").replace(/\/$/, "");
          const payload = await requestJson(`${base}/${encodeURIComponent(eventId)}.json`);
          if (!payload || !payload.event) {
            throw new Error("event detail response does not contain an event");
          }
          return payload;
        } catch (detailError) {
          const payload = await getSnapshot();
          const event = (payload.events || []).find(item =>
            item.id === eventId || item.sourceEventId === eventId
          );
          if (!event) throw detailError;
          return { ...payload, event };
        }
      })());
    }
    return eventPromises.get(eventId);
  }

  async function getEventAnalysis(eventId) {
    if (!eventId) throw new Error("eventId is required");
    if (config.mode === "api") {
      return requestJson(endpoint("analysis", eventId));
    }
    return getEvent(eventId);
  }

  function subscribeToEvent(eventId, handlers = {}) {
    if (config.mode !== "api" || typeof window.EventSource !== "function") {
      return { close() {} };
    }
    const source = new EventSource(endpoint("stream", eventId));
    if (handlers.update) {
      source.addEventListener("update", event => {
        try {
          handlers.update(JSON.parse(event.data));
        } catch (error) {
          if (handlers.error) handlers.error(error);
        }
      });
    }
    if (handlers.error) source.addEventListener("error", handlers.error);
    return source;
  }

  window.SurgeData = Object.freeze({
    config: Object.freeze({ ...config }),
    getSnapshot,
    listEvents,
    getCatalog,
    getEvent,
    getEventAnalysis,
    subscribeToEvent
  });
})();
