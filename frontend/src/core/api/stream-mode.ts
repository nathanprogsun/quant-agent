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
  if (
    typeof options !== "object" ||
    options === null ||
    !("streamMode" in options)
  ) {
    return options;
  }

  const streamMode = options.streamMode;
  if (streamMode == null) return options;

  const requestedModes = Array.isArray(streamMode) ? streamMode : [streamMode];
  const sanitizedModes = requestedModes.filter((mode) =>
    SUPPORTED_RUN_STREAM_MODES.has(mode),
  );

  if (sanitizedModes.length === requestedModes.length) return options;

  return {
    ...options,
    streamMode: Array.isArray(streamMode)
      ? sanitizedModes
      : sanitizedModes[0],
  };
}
