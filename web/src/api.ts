import type {
  ApprovalCheckpoint,
  ApprovalResult,
  CaseRecord,
  DecisionPacket,
  DemoCase,
  EvidenceSubmission,
  RunEvent,
  RunRecord,
  RunStatus,
} from './types'

const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()
export const API_BASE = (configuredBase || '').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number
  readonly requestId?: string

  constructor(status: number, message: string, requestId?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
  }
}

function unwrap<T>(payload: unknown, keys: string[]): T {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    for (const key of keys) {
      if (key in record) return record[key] as T
    }
    if ('data' in record) return record.data as T
  }
  return payload as T
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    let requestId = response.headers.get('x-request-id') ?? undefined
    try {
      const body = (await response.json()) as Record<string, unknown>
      detail = String(body.detail ?? body.message ?? detail)
      requestId = String(body.requestId ?? requestId ?? '') || undefined
    } catch {
      // Preserve the HTTP status for a non-JSON response.
    }
    throw new ApiError(response.status, detail, requestId)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  health: () => request<Record<string, unknown>>('/health'),

  async listDemoCases(): Promise<DemoCase[]> {
    return unwrap<DemoCase[]>(await request<unknown>('/demo-cases'), ['demoCases', 'cases', 'items'])
  },

  async createCase(demoCaseId: string): Promise<CaseRecord> {
    return unwrap<CaseRecord>(await request<unknown>('/cases', {
      method: 'POST',
      body: JSON.stringify({ demoCaseId }),
    }), ['case'])
  },

  async createRun(caseId: string, sessionId: string): Promise<RunRecord> {
    return unwrap<RunRecord>(await request<unknown>(`/cases/${encodeURIComponent(caseId)}/runs`, {
      method: 'POST',
      body: JSON.stringify({ sessionId }),
    }), ['run'])
  },

  async submitEvidence(runId: string, sessionId: string, documents: EvidenceSubmission[]): Promise<RunRecord> {
    return unwrap<RunRecord>(await request<unknown>(`/runs/${encodeURIComponent(runId)}/evidence`, {
      method: 'POST',
      body: JSON.stringify({ sessionId, documents }),
    }), ['run'])
  },

  async submitApproval(
    runId: string,
    checkpoint: ApprovalCheckpoint,
    sessionId: string,
    approve: boolean,
    payload: Record<string, unknown>,
  ): Promise<ApprovalResult> {
    if (!checkpoint.token) throw new Error('This approval token is no longer available.')
    return unwrap<ApprovalResult>(await request<unknown>(`/runs/${encodeURIComponent(runId)}/approvals`, {
      method: 'POST',
      body: JSON.stringify({
        checkpointId: checkpoint.checkpointId,
        token: checkpoint.token,
        sessionId,
        action: checkpoint.action,
        payload,
        approve,
      }),
    }), ['approval', 'result'])
  },

  async getDecisionPacket(caseId: string): Promise<DecisionPacket> {
    return unwrap<DecisionPacket>(await request<unknown>(`/cases/${encodeURIComponent(caseId)}/decision-packet`), ['packet', 'decisionPacket'])
  },

  async deleteCase(caseId: string): Promise<void> {
    await request<void>(`/cases/${encodeURIComponent(caseId)}`, { method: 'DELETE' })
  },
}

export type EventConnection = { close: () => void }

export function streamRunEvents(
  runId: string,
  handlers: {
    onEvent: (event: RunEvent) => void
    onDone: (status?: RunStatus) => void
    onDisconnect: () => void
    onOpen?: () => void
  },
): EventConnection {
  const source = new EventSource(`${API_BASE}/runs/${encodeURIComponent(runId)}/events`)
  const receive = (message: MessageEvent<string>) => {
    try {
      const event = unwrap<RunEvent>(JSON.parse(message.data) as unknown, ['event'])
      if (event?.eventId && typeof event.sequence === 'number') handlers.onEvent(event)
    } catch {
      // Keep-alives and malformed extension events are ignored.
    }
  }
  source.onopen = () => handlers.onOpen?.()
  source.addEventListener('run_event', receive as EventListener)
  source.onmessage = receive
  source.addEventListener('done', ((message: MessageEvent<string>) => {
    let status: RunStatus | undefined
    try {
      const payload = JSON.parse(message.data) as { status?: RunStatus }
      status = payload.status
    } catch {
      // A status-less done event is still terminal for this replay stream.
    }
    source.close()
    handlers.onDone(status)
  }) as EventListener)
  source.onerror = () => {
    source.close()
    handlers.onDisconnect()
  }
  return { close: () => source.close() }
}
