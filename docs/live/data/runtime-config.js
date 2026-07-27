window.SURGE_RUNTIME_CONFIG = Object.freeze({
  mode: "static",
  apiBaseUrl: "",
  snapshotUrl: "data/events-v9-1.json",
  catalogUrl: "data/event-catalog-v1.json",
  eventDetailBaseUrl: "data/event-details-v1",
  requestTimeoutMs: 10000,
  endpoints: Object.freeze({
    events: "/api/v1/events",
    catalog: "/api/v1/events",
    event: "/api/v1/events/{eventId}",
    analysis: "/api/v1/events/{eventId}/analysis",
    stream: "/api/v1/events/{eventId}/stream"
  })
});
