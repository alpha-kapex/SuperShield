import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api, streamRunEvents } from './api'
import type {
  ApprovalCheckpoint,
  CheckpointStatus,
  CaseRecord,
  Citation,
  Contradiction,
  DecisionPacket,
  DemoCase,
  EvidenceSubmission,
  FinancialScenario,
  InvestigationTask,
  RiskFinding,
  RunEvent,
  RunRecord,
  RunStatus,
  Severity,
  SourceDocument,
} from './types'

type View = 'workspace' | 'packet'
type StreamState = 'idle' | 'connecting' | 'live' | 'polling' | 'closed'

const TERMINAL_STATUSES = new Set<RunStatus>(['COMPLETED', 'FAILED'])

const iconPaths = {
  chevron: 'm9 18 6-6-6-6',
  play: 'm8 5 11 7-11 7Z',
  pause: 'M8 5v14M16 5v14',
  check: 'm5 12 4 4L19 6',
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 0v6h6M8 13h8M8 17h5',
  trace: 'M4 6h5v5H4zM15 13h5v5h-5zM9 8.5h3a3 3 0 0 1 3 3V13M7 11v7h8',
  refresh: 'M20 6v5h-5M4 18v-5h5M18.4 9A7 7 0 0 0 6.2 6.2L4 11m16 2-2.2 4.8A7 7 0 0 1 5.6 15',
  alert: 'M12 9v4M12 17h.01M10.3 3.8 2.5 17.2A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.8L13.7 3.8a2 2 0 0 0-3.4 0Z',
  eye: 'M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  close: 'm6 6 12 12M18 6 6 18',
  upload: 'M12 16V4m0 0L7 9m5-5 5 5M5 20h14',
  arrow: 'M5 12h14m-5-5 5 5-5 5',
  lock: 'M6 10V8a6 6 0 0 1 12 0v2M5 10h14v11H5z',
  link: 'M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7-7.1l-1.1 1M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1-1',
  shield: 'M12 2 20 5v6c0 5-3.4 9.2-8 11-4.6-1.8-8-6-8-11V5Z',
} as const

function Icon({ name, size = 18 }: { name: keyof typeof iconPaths; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={iconPaths[name]} />
    </svg>
  )
}

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}

function titleCase(value: string | undefined) {
  if (!value) return 'Unknown'
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function formatCurrency(value: number | null | undefined, compact = true) {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 0,
  }).format(value)
}

function numeric(record: Record<string, unknown> | undefined, keys: string[]) {
  for (const key of keys) {
    const value = record?.[key]
    if (typeof value === 'number') return value
    if (typeof value === 'string' && value.trim() && !Number.isNaN(Number(value))) return Number(value)
  }
  return undefined
}

function textValue(record: Record<string, unknown> | undefined, keys: string[]) {
  for (const key of keys) {
    const value = record?.[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return undefined
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something unexpected happened. Please try again.'
}

function useSessionId() {
  const [sessionId] = useState(() => {
    const existing = window.sessionStorage.getItem('supershield-session')
    if (existing && existing.length >= 8) return existing
    const created = `ss-${crypto.randomUUID()}`
    window.sessionStorage.setItem('supershield-session', created)
    return created
  })
  return sessionId
}

function StatusDot({ status }: { status: string }) {
  return <span className={cx('status-dot', `status-${status.toLowerCase()}`)} aria-hidden="true" />
}

function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: keyof typeof iconPaths
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon"><Icon name={icon} size={20} /></span>
      <div>
        <h3>{title}</h3>
        <p>{body}</p>
      </div>
      {action}
    </div>
  )
}

function SectionHeading({ eyebrow, title, aside }: { eyebrow?: string; title: string; aside?: ReactNode }) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
      </div>
      {aside}
    </div>
  )
}

function LoadingSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-stack" aria-label="Loading" role="status">
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} className="skeleton" style={{ width: `${96 - index * 11}%` }} />
      ))}
    </div>
  )
}

function ConstraintPanel({ currentCase }: { currentCase: CaseRecord | null }) {
  const input = currentCase?.input
  const person = input?.buyerName ?? 'Priya'

  return (
    <section className="side-section constraint-panel" aria-labelledby="constraints-title">
      <div className="side-section-title">
        <div>
          <span className="avatar" aria-hidden="true">{person.slice(0, 2).toUpperCase()}</span>
          <div>
            <p className="eyebrow">Decision owner</p>
            <h2 id="constraints-title">{person}’s guardrails</h2>
          </div>
        </div>
        <span className="locked-pill"><Icon name="lock" size={12} /> Locked</span>
      </div>
      {input ? (
        <dl className="constraint-list">
          {input.cashAvailable != null && <div><dt>Cash available</dt><dd>{formatCurrency(input.cashAvailable)}</dd></div>}
          <div><dt>Investment ceiling</dt><dd>{formatCurrency(input.maximumInvestment)}</dd></div>
          <div><dt>Protected reserve</dt><dd>{formatCurrency(input.emergencyReserve)}</dd></div>
          <div><dt>Income floor</dt><dd>{formatCurrency(input.requiredMonthlyHouseholdIncome)} / mo</dd></div>
          <div><dt>Preferred location</dt><dd>{input.preferredLocation}</dd></div>
          <div><dt>Risk posture</dt><dd>{titleCase(input.riskTolerance)}</dd></div>
        </dl>
      ) : <p className="muted side-copy">Choose a case to reveal the buyer constraints that govern every conclusion.</p>}
    </section>
  )
}

function SourceList({ documents }: { documents: SourceDocument[] }) {
  return (
    <section className="side-section sources" aria-labelledby="sources-title">
      <div className="side-section-title compact">
        <div>
          <p className="eyebrow">Evidence room</p>
          <h2 id="sources-title">Source documents</h2>
        </div>
        <span className="count-badge">{documents.length}</span>
      </div>
      {documents.length ? (
        <ul className="document-list">
          {documents.map((document) => (
            <li key={document.documentId}>
              <span className="document-icon"><Icon name="file" size={15} /></span>
              <span>
                <strong>{document.title}</strong>
                <small>{titleCase(document.kind)}{document.pages ? ` · ${document.pages} pages` : ''}</small>
              </span>
              <span className="verified-mark" title="Available for analysis"><Icon name="check" size={13} /></span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted side-copy">No documents loaded yet.</p>
      )}
    </section>
  )
}

function InvestigationPlanView({ tasks, runStatus }: { tasks: InvestigationTask[]; runStatus?: RunStatus }) {
  return (
    <section className="panel plan-panel" aria-labelledby="plan-title">
      <SectionHeading eyebrow="Orchestration" title="Investigation plan" aside={<span className="tiny-meta">{tasks.filter((task) => task.status === 'completed').length}/{tasks.length || 0} complete</span>} />
      {tasks.length ? (
        <ol className="plan-rail">{tasks.map((task, index) => {
          const status = task.status ?? 'pending'
          return <li key={task.taskId} className={cx('plan-step', `plan-${status}`)}><span className="step-marker">{status === 'completed' ? <Icon name="check" size={13} /> : index + 1}</span><div><span className="step-owner">{titleCase(task.tool)}</span><strong>{titleCase(task.taskId)}</strong><small>{task.purpose}</small></div></li>
        })}</ol>
      ) : <EmptyState icon="trace" title={runStatus ? 'Plan is being assembled' : 'Ready to investigate'} body={runStatus ? 'The supervisor will publish each bounded task here.' : 'Start an investigation to see the agent’s work plan before conclusions appear.'} />}
    </section>
  )
}

function EventTimeline({ events, streamState }: { events: RunEvent[]; streamState: StreamState }) {
  const visible = events.slice(-8).reverse()
  return (
    <section className="panel timeline-panel" aria-labelledby="timeline-title">
      <SectionHeading
        eyebrow="Live worklog"
        title="Investigation activity"
        aside={
          <span className={cx('connection-pill', streamState)}>
            <span className="pulse-dot" />
            {streamState === 'polling' ? 'Polling fallback' : streamState === 'live' ? 'Live stream' : titleCase(streamState)}
          </span>
        }
      />
      {visible.length ? (
        <ol className="event-list" aria-live="polite">
          {visible.map((event) => (
            <li key={event.eventId}>
              <span className={cx('event-node', `event-${event.status.toLowerCase()}`)}>
                {event.status === 'COMPLETED' ? <Icon name="check" size={12} /> : null}
              </span>
              <div className="event-copy">
                <div>
                  <strong>{event.tool ? titleCase(event.tool) : 'Supervisor'}</strong>
                  <time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>
                </div>
                <p>{event.message}</p>
                <span className="event-meta">
                  {event.durationMs != null && `${(event.durationMs / 1000).toFixed(1)}s`}
                  {event.citations?.length ? `${event.durationMs != null ? ' · ' : ''}${event.citations.length} cited source${event.citations.length === 1 ? '' : 's'}` : ''}
                </span>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <EmptyState icon="play" title="No activity yet" body="The live evidence trail will appear here when the run starts." />
      )}
    </section>
  )
}

function CitationChips({ citations = [] }: { citations?: Citation[] }) {
  if (!citations.length) return null
  return <div className="citation-row">{citations.slice(0, 3).map((citation) => <span className="citation-chip" key={citation.referenceId} title={citation.excerpt}><Icon name="link" size={11} />{citation.documentTitle}{citation.page ? ` · p.${citation.page}` : ''}</span>)}</div>
}

function SeverityPill({ severity }: { severity: Severity | string | undefined }) {
  const safeSeverity = severity || 'INFO'
  return <span className={cx('severity-pill', `severity-${safeSeverity.toLowerCase()}`)}>{titleCase(safeSeverity)}</span>
}

function RiskCards({ findings }: { findings: RiskFinding[] }) {
  return <section className="panel analysis-panel" aria-labelledby="risks-title"><SectionHeading eyebrow="Adversarial review" title="Material risks" aside={<span className="count-badge warm">{findings.length}</span>} />{findings.length ? <div className="finding-list">{findings.slice(0, 5).map((finding, index) => <article className="finding-card" key={finding.findingId}><div className="finding-topline"><span className="finding-index">{String(index + 1).padStart(2, '0')}</span><SeverityPill severity={finding.severity} /></div><h3>{finding.title}</h3><p>{finding.description}</p>{finding.financialImpact && <div className="impact-line"><strong>Decision impact</strong>{formatCurrency(finding.financialImpact.amount)} · {finding.financialImpact.description}</div>}<CitationChips citations={finding.evidence} /></article>)}</div> : <EmptyState icon="alert" title="No material risks published" body="Validated findings will appear only when they are backed by evidence." />}</section>
}

function ContradictionCards({ contradictions }: { contradictions: Contradiction[] }) {
  return (
    <section className="panel analysis-panel contradiction-panel" aria-labelledby="contradictions-title">
      <SectionHeading
        eyebrow="Cross-source check"
        title="Contradictions"
        aside={<span className="count-badge red">{contradictions.length}</span>}
      />
      {contradictions.length ? (
        <div className="contradiction-list">
          {contradictions.slice(0, 4).map((item, index) => (
            <article key={item.contradictionId ?? index} className="contradiction-card">
              <div className="contradiction-title"><span>≠</span><h3>{item.title}</h3></div>
              {(item.claimA || item.claimB) && (
                <div className="claim-compare">
                  <blockquote>{item.claimA ?? 'First source claim'}</blockquote>
                  <blockquote>{item.claimB ?? 'Conflicting source claim'}</blockquote>
                </div>
              )}
              {item.explanation && <p>{item.explanation}</p>}
              <CitationChips citations={item.citations} />
            </article>
          ))}
        </div>
      ) : (
        <EmptyState icon="check" title="No contradictions published" body="Cross-document conflicts will be isolated here with both supporting citations." />
      )}
    </section>
  )
}

function scenarioName(scenario: FinancialScenario) { return titleCase(scenario.name) }

function FinancialComparison({ scenarios, reserveFloor }: { scenarios: FinancialScenario[]; reserveFloor?: number }) {
  const maxCash = Math.max(...scenarios.map((item) => item.investmentRequired), 1)
  return <section className="panel financial-panel" aria-labelledby="finance-title"><SectionHeading eyebrow="Deterministic calculation" title="Financial scenarios" aside={<span className="math-pill">Python-calculated</span>} />{scenarios.length ? <div className="scenario-table" role="table" aria-label="Financial scenario comparison"><div className="scenario-header" role="row"><span role="columnheader">Scenario</span><span role="columnheader">Monthly profit</span><span role="columnheader">Cash required</span><span role="columnheader">Cash after entry</span><span role="columnheader">Break-even revenue</span><span role="columnheader">Guardrail</span></div>{scenarios.map((scenario, index) => {
    const viable = reserveFloor == null ? undefined : scenario.cashAfterInvestment >= reserveFloor
    return <div className={cx('scenario-row', index === 0 && 'featured')} role="row" key={scenario.scenarioId}><span role="cell"><strong>{scenarioName(scenario)}</strong><small>{Math.round(scenario.revenueFactor * 100)}% of cited revenue</small></span><span role="cell" className={scenario.monthlyOperatingProfit < 0 ? 'negative' : 'positive'}>{formatCurrency(scenario.monthlyOperatingProfit)}</span><span role="cell">{formatCurrency(scenario.investmentRequired)}<i className="cash-bar"><i style={{ width: `${Math.min(100, (scenario.investmentRequired / maxCash) * 100)}%` }} /></i></span><span role="cell">{formatCurrency(scenario.cashAfterInvestment)}</span><span role="cell">{scenario.breakEvenMonthlyRevenue == null ? 'Not calculable' : formatCurrency(scenario.breakEvenMonthlyRevenue)}</span><span role="cell"><span className={cx('guardrail-pill', viable === false ? 'fail' : viable === true ? 'pass' : 'unknown')}>{viable === false ? 'Breached' : viable === true ? 'Within' : 'Review'}</span></span></div>
  })}</div> : <EmptyState icon="refresh" title="Scenarios not calculated" body="Base and downside outcomes will be compared using deterministic arithmetic." />}</section>
}

function WhyChanged({ revision, affectedTasks }: { revision?: number; affectedTasks: string[] }) {
  if (!revision || revision <= 1) return null
  return (
    <section className="change-panel" aria-labelledby="change-title">
      <div className="change-icon"><Icon name="refresh" size={18} /></div>
      <div>
        <p className="eyebrow">Revision {revision}</p>
        <h2 id="change-title">Why this decision changed</h2>
        <p>New evidence was accepted and only the analyses whose inputs changed were recalculated.</p>
      </div>
      <div className="affected-list">
        {affectedTasks.length ? affectedTasks.map((task) => <span key={task}>{titleCase(task)}</span>) : <span>Decision packet refreshed</span>}
      </div>
    </section>
  )
}

function EvidenceForm({
  run,
  sessionId,
  onSubmitted,
}: {
  run: RunRecord
  sessionId: string
  onSubmitted: (run: RunRecord) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [title, setTitle] = useState('Clarification from franchisor')
  const [kind, setKind] = useState('correspondence')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!title.trim() || !content.trim()) return
    setSubmitting(true)
    setError(null)
    const document: EvidenceSubmission = {
      documentId: `user-${Date.now()}`,
      title: title.trim(),
      kind,
      content: content.trim(),
      source: 'Submitted by decision owner',
    }
    try {
      const updated = await api.submitEvidence(run.runId, sessionId, [document])
      onSubmitted(updated)
      setContent('')
      setExpanded(false)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="panel evidence-submit" aria-labelledby="evidence-submit-title">
      <div className="evidence-callout">
        <span><Icon name="upload" size={20} /></span>
        <div>
          <p className="eyebrow">Evidence loop</p>
          <h2 id="evidence-submit-title">Have a new clarification?</h2>
          <p>Add the response, then SuperShield reruns only the affected tasks and explains what changed.</p>
        </div>
        <button type="button" className="secondary-button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Close' : 'Add evidence'}
        </button>
      </div>
      {expanded && (
        <form className="evidence-form" onSubmit={submit}>
          <label>
            Document title
            <input value={title} onChange={(event) => setTitle(event.target.value)} required />
          </label>
          <label>
            Evidence type
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="correspondence">Clarification / email</option>
              <option value="financial">Financial document</option>
              <option value="lease">Lease / contract amendment</option>
              <option value="other">Other evidence</option>
            </select>
          </label>
          <label className="wide-field">
            Content
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={5}
              required
              placeholder="Paste the new evidence exactly as received…"
            />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="form-actions wide-field">
            <span><Icon name="lock" size={13} /> Evidence is added to the audit trail.</span>
            <button className="primary-button" disabled={submitting || !content.trim()}>
              {submitting ? 'Submitting…' : 'Submit & resume'} <Icon name="arrow" size={15} />
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

function ApprovalPanel({ checkpoint, run, sessionId, onResolved }: { checkpoint: ApprovalCheckpoint; run: RunRecord; sessionId: string; onResolved: (status: CheckpointStatus, message: string) => void }) {
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const decide = async (approve: boolean) => {
    if (!run.packet) return
    setBusy(approve ? 'approve' : 'reject'); setError(null)
    const common = { caseId: run.caseId, runId: run.runId, packetRevision: run.packet.revision }
    const payload = checkpoint.action === 'EXPORT_REPORT' ? { ...common, format: 'json' } : { ...common, requests: run.packet.missingEvidence }
    try { const result = await api.submitApproval(run.runId, checkpoint, sessionId, approve, payload); onResolved(result.status, approve ? 'Approval recorded. The exact payload is now authorized.' : 'Declined. No action was taken.') } catch (caught) { setError(errorMessage(caught)) } finally { setBusy(null) }
  }
  return <section className="approval-panel" aria-labelledby={`approval-${checkpoint.checkpointId}`}><div className="approval-lock"><Icon name="lock" size={22} /></div><div className="approval-copy"><p className="eyebrow">Human checkpoint · consequential action paused</p><h2 id={`approval-${checkpoint.checkpointId}`}>{titleCase(checkpoint.action)}</h2><p>{checkpoint.description}</p>{error && <p className="form-error" role="alert">{error}</p>}</div><div className="approval-actions"><button className="ghost-button danger" onClick={() => decide(false)} disabled={busy != null}>{busy === 'reject' ? 'Declining…' : 'Decline'}</button><button className="primary-button" onClick={() => decide(true)} disabled={busy != null}>{busy === 'approve' ? 'Approving…' : 'Approve exact action'} <Icon name="arrow" size={15} /></button></div></section>
}

function DecisionHeader({ packet, loading }: { packet: DecisionPacket | null; loading: boolean }) {
  const posture = packet?.decisionState
  const tone = posture === 'MATERIAL_RISK_IDENTIFIED' ? 'negative' : posture === 'MORE_EVIDENCE_REQUIRED' ? 'caution' : posture ? 'positive' : 'neutral'
  const validated = packet?.validation.valid
  return <section className={cx('decision-hero', `decision-${tone}`)}><div><p className="eyebrow">Current decision posture</p>{loading ? <span className="skeleton hero-skeleton" /> : <h1>{posture ? titleCase(posture) : 'Investigation not started'}</h1>}<p className="hero-summary">{packet?.plainLanguageSummary ?? 'SuperShield will produce a bounded, auditable decision packet—not make the decision for you.'}</p></div><div className="confidence-orbit" aria-label={validated == null ? 'Validation pending' : validated ? 'Packet validated' : 'Validation requires review'}><svg viewBox="0 0 84 84" aria-hidden="true"><circle cx="42" cy="42" r="36" /><circle cx="42" cy="42" r="36" style={{ strokeDasharray: `${validated ? 226.2 : 0} 226.2` }} /></svg><strong>{validated == null ? '—' : validated ? '✓' : '!'}</strong><span>{validated ? 'validated' : 'validation'}</span></div></section>
}

function DecisionPacketView({ packet, caseTitle }: { packet: DecisionPacket | null; caseTitle?: string }) {
  return <div className="packet-view"><div className="packet-cover"><div className="packet-monogram"><Icon name="shield" size={26} /></div><div><p className="eyebrow">Versioned decision packet</p><h1>{caseTitle ?? 'SuperShield analysis'}</h1><p>{packet?.generatedAt ? `Generated ${new Date(packet.generatedAt).toLocaleString()}` : 'Generated when the investigation completes'}</p></div><div className="packet-version">v{packet?.revision ?? 1}</div></div>{!packet ? <EmptyState icon="file" title="Decision Packet is not ready" body="Complete the investigation to assemble the auditable record." /> : <><section className="packet-summary"><div><p className="eyebrow">Decision posture</p><h2>{titleCase(packet.decisionState)}</h2></div><p>{packet.plainLanguageSummary}</p></section><div className="packet-grid"><section><h2>Material findings</h2><ol>{packet.riskFindings.map((risk) => <li key={risk.findingId}><SeverityPill severity={risk.severity} /><div><strong>{risk.title}</strong><p>{risk.description}</p></div></li>)}</ol></section><section><h2>Evidence still required</h2><ol className="question-list">{packet.missingEvidence.map((question, index) => <li key={question}><span>{index + 1}</span>{question}</li>)}</ol></section></div><section className="packet-scenarios"><h2>Scenario conclusion</h2><div>{packet.financialScenarios.map((scenario) => <article key={scenario.scenarioId}><p>{scenarioName(scenario)}</p><strong>{formatCurrency(scenario.monthlyOperatingProfit)} / mo</strong><span>{formatCurrency(scenario.investmentRequired)} required</span></article>)}</div></section><section className="packet-next"><h2>Why this changed</h2><ul>{(packet.whyThisChanged.length ? packet.whyThisChanged : ['Initial evidence-bound analysis completed.']).map((step) => <li key={step}><Icon name="arrow" size={14} />{step}</li>)}</ul></section><footer className="packet-footer"><Icon name="lock" size={13} /> {packet.scopeNotice}</footer></>}</div>
}

function TraceDrawer({ events, run, open, onClose }: { events: RunEvent[]; run: RunRecord | null; open: boolean; onClose: () => void }) {
  const [selected, setSelected] = useState<RunEvent | null>(null)
  useEffect(() => {
    if (!open) setSelected(null)
  }, [open])
  return (
    <>
      <button aria-label="Close trace drawer" className={cx('drawer-scrim', open && 'open')} onClick={onClose} />
      <aside className={cx('trace-drawer', open && 'open')} aria-hidden={!open} aria-labelledby="trace-title">
        <header>
          <div><p className="eyebrow">Full provenance</p><h2 id="trace-title">Execution trace</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="Close trace"><Icon name="close" /></button>
        </header>
        <div className="trace-meta">
          <span><small>Run</small>{run?.runId?.slice(0, 14) ?? 'Not started'}</span>
          <span><small>Mode</small>{titleCase(run?.mode ?? '—')}</span>
          <span><small>Revision</small>{run?.revision ?? '—'}</span>
        </div>
        {selected ? (
          <div className="trace-detail">
            <button className="back-button" onClick={() => setSelected(null)}>← All events</button>
            <p className="eyebrow">Sequence {selected.sequence}</p>
            <h3>{selected.message}</h3>
            <dl>
              <div><dt>Tool</dt><dd>{selected.tool}</dd></div>
              <div><dt>Status</dt><dd>{selected.status}</dd></div>
              <div><dt>Timestamp</dt><dd>{new Date(selected.timestamp).toLocaleString()}</dd></div>
              <div><dt>Duration</dt><dd>{selected.durationMs == null ? '—' : `${selected.durationMs} ms`}</dd></div>
            </dl>
            <h4>Structured details</h4>
            <pre>{JSON.stringify(selected.details ?? {}, null, 2)}</pre>
            <h4>Citations</h4>
            <CitationChips citations={selected.citations} />
          </div>
        ) : events.length ? (
          <ol className="trace-list">
            {[...events].reverse().map((event) => (
              <li key={event.eventId}>
                <button onClick={() => setSelected(event)}>
                  <span className="trace-sequence">{String(event.sequence).padStart(2, '0')}</span>
                  <span><strong>{titleCase(event.tool)}</strong><small>{event.message}</small></span>
                  <Icon name="chevron" size={14} />
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState icon="trace" title="No trace yet" body="Tool calls, durations, citations, and structured outputs will accumulate here." />
        )}
      </aside>
    </>
  )
}

function App() {
  const sessionId = useSessionId()
  const [demoCases, setDemoCases] = useState<DemoCase[]>([])
  const [selectedDemoId, setSelectedDemoId] = useState('')
  const [currentCase, setCurrentCase] = useState<CaseRecord | null>(null)
  const [run, setRun] = useState<RunRecord | null>(null)
  const [packet, setPacket] = useState<DecisionPacket | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [view, setView] = useState<View>('workspace')
  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [traceOpen, setTraceOpen] = useState(false)
  const [loadingCases, setLoadingCases] = useState(true)
  const [openingCase, setOpeningCase] = useState(false)
  const [startingRun, setStartingRun] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const lastSequence = useRef(0)

  const loadDemoCases = useCallback(async () => {
    setLoadingCases(true)
    setError(null)
    try {
      const items = await api.listDemoCases()
      setDemoCases(Array.isArray(items) ? items : [])
      setSelectedDemoId((current) => current || items[0]?.id || '')
    } catch (caught) {
      setError(`Could not load demo cases. ${errorMessage(caught)}`)
    } finally {
      setLoadingCases(false)
    }
  }, [])

  useEffect(() => { void loadDemoCases() }, [loadDemoCases])

  const openCase = async () => {
    if (!selectedDemoId) return
    setOpeningCase(true)
    setError(null)
    setNotice(null)
    try {
      const created = await api.createCase(selectedDemoId)
      setCurrentCase(created)
      setRun(null)
      setPacket(null)
      setEvents([])
      lastSequence.current = 0
      setView('workspace')
    } catch (caught) {
      setError(`Could not open the case. ${errorMessage(caught)}`)
    } finally {
      setOpeningCase(false)
    }
  }

  const updateRun = useCallback((next: RunRecord) => {
    setRun(next)
    if (next.packet) setPacket(next.packet)
  }, [])

  const fetchPacket = useCallback(async (caseId: string) => {
    try {
      const next = await api.getDecisionPacket(caseId)
      setPacket(next)
    } catch (caught) {
      if (!(caught instanceof ApiError) || caught.status !== 404) {
        setError(`Decision Packet could not be refreshed. ${errorMessage(caught)}`)
      }
    }
  }, [])

  const startRun = async () => {
    if (!currentCase) return
    setStartingRun(true)
    setError(null)
    setNotice(null)
    setEvents([])
    lastSequence.current = 0
    try {
      const created = await api.createRun(currentCase.caseId, sessionId)
      updateRun(created)
      setStreamState('connecting')
    } catch (caught) {
      setError(`The investigation could not start. ${errorMessage(caught)}`)
    } finally {
      setStartingRun(false)
    }
  }

  useEffect(() => {
    if (!run?.runId || !run.caseId) return
    let disposed = false
    setStreamState('connecting')
    const connection = streamRunEvents(run.runId, {
      onOpen: () => !disposed && setStreamState('live'),
      onEvent: (event) => { if (!disposed && event.sequence > lastSequence.current) { lastSequence.current = event.sequence; setEvents((current) => [...current, event].sort((a, b) => a.sequence - b.sequence)) } },
      onDone: () => { if (!disposed) { setStreamState('closed'); void fetchPacket(run.caseId) } },
      onDisconnect: () => { if (!disposed) { setStreamState('closed'); void fetchPacket(run.caseId) } },
    })
    return () => { disposed = true; connection.close() }
  }, [run?.runId, run?.revision, run?.caseId, fetchPacket])

  const tasks = useMemo(() => (run?.plan?.tasks ?? []).map((task) => {
    const last = events.filter((event) => event.tool === task.tool).at(-1)
    const status: InvestigationTask['status'] = last?.status === 'COMPLETED' ? 'completed' : last?.status === 'FAILED' ? 'failed' : last?.status === 'SKIPPED' ? 'skipped' : last?.status === 'STARTED' ? 'running' : 'pending'
    return { ...task, status }
  }), [run?.plan, events])
  const findings = packet?.riskFindings ?? []
  const contradictions: Contradiction[] = (packet?.claimAssessments ?? []).filter((assessment) => assessment.status === 'CONTRADICTED').map((assessment) => ({ contradictionId: assessment.claimId, title: `Conflicting ${titleCase(assessment.topic)}`, claimA: assessment.claimText, claimB: assessment.conflictingEvidence[0]?.excerpt ?? 'Conflicting evidence is cited in the packet.', explanation: assessment.rationale, severity: assessment.material ? 'HIGH' : 'MEDIUM', citations: [...assessment.evidence, ...assessment.conflictingEvidence] }))
  const scenarios = packet?.financialScenarios ?? []
  const checkpoint = packet?.checkpoints.find((item) => item.status === 'PENDING')
  const reserveFloor = currentCase?.input.emergencyReserve
  const canStart = Boolean(currentCase && !startingRun && (!run || TERMINAL_STATUSES.has(run.status)))
  const runActive = Boolean(run && ['PENDING', 'RUNNING'].includes(run.status))

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="SuperShield home">
          <span className="brand-mark"><Icon name="shield" size={21} /><i /></span>
          <span><strong>SuperShield</strong><small>Decision intelligence</small></span>
        </a>
        <nav className="view-tabs" aria-label="Workspace views">
          <button className={view === 'workspace' ? 'active' : ''} onClick={() => setView('workspace')}>Workspace</button>
          <button className={view === 'packet' ? 'active' : ''} onClick={() => setView('packet')}>Decision Packet</button>
        </nav>
        <div className="top-actions">
          <span className="safety-state"><span /> Human-controlled</span>
          <button className="trace-button" onClick={() => setTraceOpen(true)}><Icon name="trace" size={16} /> Trace</button>
        </div>
      </header>

      <div className="workspace-layout" id="top">
        <aside className="sidebar">
          <section className="case-picker" aria-labelledby="case-picker-title">
            <p className="eyebrow">Active case</p>
            <h1 id="case-picker-title">Choose an investigation</h1>
            {loadingCases ? <LoadingSkeleton rows={2} /> : demoCases.length ? (
              <>
                <label className="select-wrap">
                  <span className="sr-only">Demo case</span>
                  <select value={selectedDemoId} onChange={(event) => setSelectedDemoId(event.target.value)}>
                    {demoCases.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}
                  </select>
                  <Icon name="chevron" size={15} />
                </label>
                <button className="case-open-button" onClick={openCase} disabled={openingCase || !selectedDemoId}>
                  {openingCase ? 'Preparing case…' : currentCase ? 'Switch case' : 'Open case'}
                  {!openingCase && <Icon name="arrow" size={15} />}
                </button>
                {selectedDemoId && <p className="case-summary">{demoCases.find((item) => item.id === selectedDemoId)?.summary}</p>}
              </>
            ) : (
              <EmptyState icon="file" title="No demo cases" body="The API is online but did not return a case." action={<button className="text-button" onClick={loadDemoCases}>Retry</button>} />
            )}
          </section>
          <ConstraintPanel currentCase={currentCase} />
          <SourceList documents={currentCase?.documents ?? []} />
          <div className="sidebar-footnote"><Icon name="shield" size={14} /><p><strong>Evidence before advice.</strong> SuperShield abstains when the record cannot support a conclusion.</p></div>
        </aside>

        <main className="main-content">
          {error && (
            <div className="global-alert error" role="alert"><Icon name="alert" size={18} /><span>{error}</span><button onClick={() => setError(null)} aria-label="Dismiss"><Icon name="close" size={15} /></button></div>
          )}
          {notice && <div className="global-alert success" role="status"><Icon name="check" size={18} /><span>{notice}</span><button onClick={() => setNotice(null)} aria-label="Dismiss"><Icon name="close" size={15} /></button></div>}

          {!currentCase ? (
            <section className="welcome-state">
              <div className="welcome-shield"><Icon name="shield" size={42} /><span /></div>
              <p className="eyebrow">A decision workspace—not a chatbot</p>
              <h1>See what the documents imply<br />before your money is committed.</h1>
              <p>Choose Priya’s fictional case to watch SuperShield collect evidence, challenge claims, calculate downside, and stop for human judgment.</p>
              <div className="welcome-proof">
                <span><strong>01</strong>Cited evidence</span>
                <span><strong>02</strong>Deterministic math</span>
                <span><strong>03</strong>Human approval</span>
              </div>
              {error && <button className="secondary-button" onClick={loadDemoCases}>Retry connection</button>}
            </section>
          ) : view === 'packet' ? (
            <DecisionPacketView packet={packet} caseTitle={currentCase.title} />
          ) : (
            <>
              <div className="case-header">
                <div>
                  <div className="case-kicker"><span>CASE {currentCase.caseId.slice(0, 8).toUpperCase()}</span><span>•</span><span>{currentCase.documents.length} sources</span></div>
                  <h1>{currentCase.title}</h1>
                  <p>{currentCase.summary}</p>
                </div>
                <div className="run-controls">
                  {run && <span className={cx('run-status', `run-${run.status.toLowerCase()}`)}><StatusDot status={run.status} />{titleCase(run.status)}</span>}
                  <button className="primary-button run-button" onClick={startRun} disabled={!canStart}>
                    <Icon name={runActive ? 'pause' : 'play'} size={16} />
                    {startingRun ? 'Starting…' : runActive ? 'Investigation running' : run ? 'Run again' : 'Start investigation'}
                  </button>
                </div>
              </div>

              <DecisionHeader packet={packet} loading={Boolean(runActive && !packet)} />
              <WhyChanged revision={run?.revision} affectedTasks={run?.affectedTasks ?? []} />
              <InvestigationPlanView tasks={tasks} runStatus={run?.status} />

              <div className="analysis-grid">
                <RiskCards findings={findings} />
                <ContradictionCards contradictions={contradictions} />
              </div>

              <FinancialComparison scenarios={scenarios} reserveFloor={reserveFloor} />

              {checkpoint && run && checkpoint.status === 'PENDING' && (
                <ApprovalPanel
                  checkpoint={checkpoint}
                  run={run}
                  sessionId={sessionId}
                  onResolved={(status, message) => {
                    setPacket((current) => current ? {
                      ...current,
                      checkpoints: current.checkpoints.map((item) => item.checkpointId === checkpoint.checkpointId ? { ...item, status, token: undefined } : item),
                    } : current)
                    setNotice(message)
                  }}

                />
              )}

              <div className="lower-grid">
                <EventTimeline events={events} streamState={streamState} />
                {run ? <EvidenceForm run={run} sessionId={sessionId} onSubmitted={(updated) => { updateRun(updated); setNotice('Evidence accepted. Affected tasks are resuming.') }} /> : (
                  <section className="panel evidence-placeholder"><EmptyState icon="upload" title="Evidence loop" body="Once a run starts, you can add a clarification and selectively resume the analysis." /></section>
                )}
              </div>

              {packet && (
                <section className="packet-cta">
                  <div><p className="eyebrow">Auditable output</p><h2>Your Decision Packet is ready</h2><p>Review the final position, open questions, scenario math, and human-owned next steps.</p></div>
                  <button className="light-button" onClick={() => setView('packet')}>Open Decision Packet <Icon name="arrow" size={15} /></button>
                </section>
              )}
            </>
          )}
        </main>
      </div>
      <TraceDrawer events={events} run={run} open={traceOpen} onClose={() => setTraceOpen(false)} />
    </div>
  )
}

export default App
