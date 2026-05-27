import type { Message } from "@langchain/langgraph-sdk";

export interface Thread {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ThreadCreateParams {
  title?: string;
}

export interface ThreadUpdateParams {
  title?: string;
}

/**
 * Agent thread state — aligned with backend ThreadState (§5.3).
 * All fields are optional (total=False) since they arrive incrementally via SSE.
 */
export interface AgentThreadState {
  messages: Message[];
  title?: string;
  code?: string;
  session_status?: string;
}
