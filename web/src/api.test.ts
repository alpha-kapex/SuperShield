import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('unwraps an optional demoCases envelope', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      demoCases: [{ id: 'one', title: 'One', summary: 'Summary', tags: [], documentCount: 1 }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(api.listDemoCases()).resolves.toHaveLength(1)
  })

  it('sends the session when starting a run', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      runId: 'run-1', caseId: 'case-1', sessionId: 'session-123', status: 'RUNNING', mode: 'local', revision: 1, affectedTasks: [],
    }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await api.createRun('case-1', 'session-123')

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/cases/case-1/runs'), expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ sessionId: 'session-123' }),
    }))
  })
})
