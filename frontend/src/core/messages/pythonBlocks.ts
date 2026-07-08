import type { Message } from '@langchain/langgraph-sdk'

import { extractContentFromMessage } from './utils'

const PYTHON_FENCE = /```(?:python|py)\s*\n([\s\S]*?)```/gi

/** Extract the latest ```python fenced block from plain text. */
export function extractLatestPythonBlockFromText(text: string): string | null {
  if (!text.trim()) return null

  const matches = [...text.matchAll(PYTHON_FENCE)]
  if (matches.length === 0) return null

  const last = matches[matches.length - 1]
  const code = last?.[1]?.trim()
  return code || null
}

/** Extract the latest assistant ```python block across all messages. */
export function extractLatestPythonBlock(messages: Message[]): string | null {
  let latest: string | null = null

  for (const message of messages) {
    if (message.type !== 'ai') continue
    const content = extractContentFromMessage(message)
    const block = extractLatestPythonBlockFromText(content)
    if (block) latest = block
  }

  return latest
}

/** Decide whether Monaco should sync from a newly detected assistant block. */
export function shouldSyncEditorCode(
  assistantBlock: string | null,
  lastSyncedBlock: string | null,
): boolean {
  if (!assistantBlock) return false
  return assistantBlock !== lastSyncedBlock
}
