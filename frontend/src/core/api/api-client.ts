"use client";

import { Client as LangGraphClient } from "@langchain/langgraph-sdk/client";

import { injectCsrfHeader } from "./fetcher";
import { sanitizeRunStreamOptions } from "./stream-mode";

function getAbsoluteApiUrl(): string {
  const configured = process.env.NEXT_PUBLIC_LANGGRAPH_API_URL;
  if (configured) return configured;

  // In the browser, use absolute URL — LangGraph SDK streaming transport
  // uses `new URL(path, apiUrl)` which requires an absolute base.
  if (typeof window !== "undefined") {
    return `${window.location.origin}/api`;
  }

  return "/api";
}

function createClient(): LangGraphClient {
  const apiUrl = getAbsoluteApiUrl();

  const client = new LangGraphClient({
    apiUrl,
    onRequest: injectCsrfHeader,
  });

  // Patch runs.stream to sanitize stream modes
  const originalRunStream = client.runs.stream.bind(client.runs);
  client.runs.stream = ((
    threadId: string | null,
    assistantId: string,
    payload?: Record<string, unknown>,
  ) =>
    originalRunStream(
      threadId as never,
      assistantId,
      sanitizeRunStreamOptions(payload),
    )) as typeof client.runs.stream;

  return client;
}

const _clients = new Map<string, LangGraphClient>();

export function getAPIClient(): LangGraphClient {
  const cacheKey = "default";
  let client = _clients.get(cacheKey);
  if (!client) {
    client = createClient();
    _clients.set(cacheKey, client);
  }
  return client;
}
