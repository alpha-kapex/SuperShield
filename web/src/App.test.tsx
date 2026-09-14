import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App, { formatCurrency } from './App'
import { createSessionId } from './session'

const demoCase = {
  id: 'priya-franchise',
  title: 'Priya · Franchise acquisition',
  summary: 'Evaluate a fictional franchise before committing family savings.',
  tags: ['franchise', 'synthetic'],
  documentCount: 3,
}

const caseRecord = {
  caseId: 'case-12345678',
  demoCaseId: demoCase.id,
  title: demoCase.title,
  summary: demoCase.summary,
  input: {
    buyerName: 'Priya Sharma',
    maximumInvestment: 3000000,
    emergencyReserve: 900000,
    requiredMonthlyHouseholdIncome: 125000,
    preferredLocation: 'Maple Junction',
    riskTolerance: 'low',
    currency: 'USD',
  },
  documents: [
    { documentId: 'doc-1', title: 'Franchise disclosure', kind: 'disclosure', source: 'fixture:test' },
  ],
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

describe('SuperShield workspace', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/demo-cases')) return json([demoCase])
      if (url.endsWith('/cases') && init?.method === 'POST') return json(caseRecord, 201)
      return json({ detail: `Unhandled request: ${url}` }, 404)
    }))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('formats the synthetic USD values for the decision owner', () => {
    expect(formatCurrency(3000000)).toBe('$3M')
  })

  it('creates a UUID session when randomUUID is unavailable on an HTTP origin', () => {
    const cryptoSource = {
      getRandomValues: (array: Uint8Array) => {
        array.set(Array.from({ length: 16 }, (_, index) => index))
        return array
      },
    }

    expect(createSessionId(cryptoSource)).toBe('ss-00010203-0405-4607-8809-0a0b0c0d0e0f')
  })

  it('loads a demo case and opens the decision workspace', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByRole('option', { name: demoCase.title })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open case' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: demoCase.title })).toBeInTheDocument())
    expect(screen.getByText('Priya Sharma’s guardrails')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Start investigation/i })).toBeEnabled()
  })
})
