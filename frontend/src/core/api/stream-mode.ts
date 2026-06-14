const SUPPORTED_RUN_STREAM_MODES = new Set([
  "values",
  "messages",
  "messages-tuple",
  "updates",
  "events",
  "debug",
  "tasks",
  "checkpoints",
  "custom",
] as const);

export function sanitizeRunStreamOptions<T>(options: T): T {
  if (typeof options !== "object" || options === null) {
    return options;
  }

  let next = options;

  if ("streamMode" in options) {
    const streamMode = options.streamMode;
    if (streamMode != null) {
      const requestedModes = Array.isArray(streamMode) ? streamMode : [streamMode];
      const sanitizedModes = requestedModes.filter((mode) =>
        SUPPORTED_RUN_STREAM_MODES.has(mode),
      );

      if (sanitizedModes.length !== requestedModes.length) {
        next = {
          ...next,
          streamMode: Array.isArray(streamMode)
            ? sanitizedModes
            : sanitizedModes[0],
        };
      }
    }
  }

  if ("onDisconnect" in next && next.onDisconnect === "continue") {
    next = {
      ...next,
      onDisconnect: "keep_alive",
    };
  }

  return next;
}
