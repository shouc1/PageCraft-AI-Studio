# Jimeng Agent Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync the requirements document with the current Jimeng API architecture and implement backend-led workflow selection, task events, Jimeng workflow adapters, and a basic inpaint mask editor.

**Architecture:** Keep Next.js as a thin client that submits user intent, image, and optional mask. FastAPI owns workflow selection, Agent progress, task event persistence, and provider-specific Jimeng adapters. SQLite stores task state and timeline events.

**Tech Stack:** Next.js 14, React 18, TailwindCSS, FastAPI, SQLite, LangGraph, Chroma/BM25 RAG, Volcengine Jimeng API, ARK/Doubao LLM.

## Global Constraints

- Do not reintroduce ComfyUI or ControlNet into the current product path.
- Keep API keys in environment variables only.
- Preserve mock mode for local demos, but make real API failures distinguishable.
- Make the frontend call backend APIs rather than provider APIs directly.
- Verify with `npm run build` and Python compile/tests.

---

### Task 1: Documentation Sync

**Files:**
- Modify: `docs/需求分析.md`
- Modify: `frontend/app/styles/page.tsx`

**Interfaces:**
- Consumes: current backend routes `/api/uploads`, `/api/results`, `/api/tasks/{id}/confirm`
- Produces: updated source of truth for project scope and status

- [ ] Update current status to mark FastAPI, upload, task CRUD, WebSocket, RAG, LangGraph skeleton, and Jimeng wrapper as started or completed.
- [ ] Replace `/api/upload` with `/api/uploads`.
- [ ] Replace `/api/images/{filename}` with `/api/uploads/{filename}` and `/api/results/{filename}`.
- [ ] Document `awaiting_confirmation` after planning and before generation.
- [ ] Change ARK auth wording from reusing AK/SK to `ARK_API_KEY` + `DOUBAO_MODEL`.
- [ ] Replace ComfyUI copy in the styles page with Jimeng workflow copy.

### Task 2: Backend Workflow Selection

**Files:**
- Create: `backend/app/services/workflows.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/api/tasks.py`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/studio/StudioWorkspace.tsx`

**Interfaces:**
- Produces: `select_workflow(requested_workflow: str | None, input_image: str | None, mask_image: str | None) -> str`

- [ ] Add tests for text-only, image, mask, and explicit workflow selection.
- [ ] Run the tests and confirm they fail because `select_workflow` is missing.
- [ ] Implement `select_workflow`.
- [ ] Make `TaskCreate.workflow` optional and add `mask_image`.
- [ ] Make frontend submit `workflow: "auto"` and optional `mask_image`.

### Task 3: Task Events

**Files:**
- Create: `backend/app/services/events.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/services/task_runner.py`
- Modify: `backend/app/services/graph.py`
- Modify: `backend/app/api/tasks.py`
- Modify: `backend/app/api/ws.py`
- Modify: `frontend/app/tasks/[id]/page.tsx`

**Interfaces:**
- Produces: `add_task_event(task_id: str, stage: str, message: str, progress: int, metadata: dict | None = None) -> None`
- Produces: `GET /api/tasks/{task_id}/events`

- [ ] Add tests proving events can be inserted and listed.
- [ ] Run the tests and confirm they fail because `task_events` is missing.
- [ ] Add `task_events` table.
- [ ] Record every `_update_task` transition.
- [ ] Record Agent node/RAG details and Jimeng provider task id when available.
- [ ] Show task timeline on the detail page.

### Task 4: Jimeng Adapters

**Files:**
- Create: `backend/app/services/jimeng_adapters.py`
- Modify: `backend/app/services/jimeng.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Produces: `build_jimeng_request(workflow: str, prompt: str, input_image: str | None, mask: str | None, size: str | None, strength: float | None) -> JimengRequest`

- [ ] Add tests for text2image, image2image, and inpaint request construction.
- [ ] Run the tests and confirm they fail because the adapter is missing.
- [ ] Split workflow request construction into adapter functions.
- [ ] Return provider task id metadata from real generation.
- [ ] Add `mock_on_api_failure` setting.

### Task 5: Inpaint Mask Editor

**Files:**
- Create: `frontend/components/studio/InpaintMaskEditor.tsx`
- Modify: `frontend/components/studio/PreviewCanvas.tsx`
- Modify: `frontend/components/studio/StudioWorkspace.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `backend/app/api/uploads.py`

**Interfaces:**
- Produces: mask PNG upload through existing `/api/uploads`
- Produces: inpaint task creation with `input_image` and `mask_image`

- [ ] Add canvas drawing over the generated image.
- [ ] Export the mask as a PNG `File`.
- [ ] Upload the mask through `/api/uploads`.
- [ ] Submit a new task with `workflow: "inpaint"`, `input_image` set to the generated result filename where possible, and `mask_image`.
- [ ] Verify frontend build.

## Self-Review

- Spec coverage: all five requested areas map to tasks.
- Placeholder scan: no implementation step depends on an undefined follow-up.
- Type consistency: `mask_image`, `workflow: "auto"`, and `task_events` are carried through backend and frontend boundaries.
