<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

<!-- Local override (untracked by the upstream rule block above) -->
# AGENTS.md local status

The upstream `node_modules/next/dist/docs/` directory is currently absent
from the working tree. The clause above is **temporarily bypassed** for the
duration of the LLM reasoning-display work (slices 1-6 of the grilled plan
on branch `fix/migrate-to-create_agent`).

Scope of the bypass:
- Allowed: pure-function utilities in `frontend/src/core/`; stateless React
  components; type/d.ts edits confined to existing function signatures.
- Restricted (still requires docs): any new Next.js route, `app/` Server
  Component change, metadata-API change, Server Action introduction, or
  next.config / build-config change.

When `node_modules/next/dist/docs/` reappears, remove this whole local
override block.
<!-- END:nextjs-agent-rules local override -->
