export type RunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'WAITING_FOR_EVIDENCE'
  | 'AWAITING_APPROVAL'
  | 'COMPLETED'
  | 'FAILED'

export type EventStatus = 'STARTED' | 'COMPLETED' | 'SKIPPED' | 'BLOCKED' | 'FAILED' | 'INFO'
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'
export type ApprovalAction = 'EXPORT_REPORT' | 'SEND_TEST_EVIDENCE_REQUEST'
export type CheckpointStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'CONSUMED'

export interface DemoCase {
  id: string
  title: string
  summary: string
  tags: string[]
  documentCount: number
}

export interface SourceDocument {
  documentId: string
  title: string
  kind: string
  content?: string
  source: string
  receivedAt?: string
  metadata?: Record<string, unknown>
  pages?: number
}

export interface PersonConstraints {
  buyerName: string
  cashAvailable?: number
  maximumInvestment: number
  emergencyReserve: number
  requiredMonthlyHouseholdIncome: number
  preferredLocation: string
  riskTolerance: string
  currency: string
}

export interface CaseRecord {
  caseId: string
  demoCaseId?: string
  title: string
  summary: string
  input: PersonConstraints
  documents: SourceDocument[]
  locationData?: Record<string, unknown>
  createdAt: string
  updatedAt: string
  expiresAt?: string
  version: number
}

export interface Citation {
  referenceId: string
  documentId: string
  documentTitle: string
  documentKind: string
  page: number
  excerpt: string
  contentHash: string
  locator?: string
}

export interface InvestigationTask {
  taskId: string
  tool: string
  purpose: string
  dependsOn: string[]
  required: boolean
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
}

export interface InvestigationPlan {
  planId: string
  caseId: string
  constraintsSummary: string
  tasks: InvestigationTask[]
  createdAt: string
}

export interface RunEvent {
  eventId: string
  runId: string
  sequence: number
  timestamp: string
  tool: string
  status: EventStatus
  message: string
  durationMs?: number
  citations: Citation[]
  details: Record<string, unknown>
}

export interface ClaimAssessment {
  claimId: string
  claimText: string
  topic: string
  status: 'SUPPORTED' | 'CONTRADICTED' | 'UNRESOLVED'
  rationale: string
  material: boolean
  evidence: Citation[]
  conflictingEvidence: Citation[]
}

export interface FinancialImpact {
  amount: number
  period: 'one_time' | 'monthly' | 'annual' | 'total_term'
  description: string
  formula: string
}

export interface RiskFinding {
  findingId: string
  category: string
  title: string
  description: string
  severity: Severity
  material: boolean
  unresolved: boolean
  evidence: Citation[]
  financialImpact?: FinancialImpact
  requestedEvidence?: string
}

export interface Contradiction {
  contradictionId: string
  title: string
  claimA: string
  claimB: string
  explanation: string
  severity: Severity
  citations: Citation[]
}

export interface FinancialScenario {
  scenarioId: string
  name: string
  revenueFactor: number
  monthlyRevenue: number
  investmentRequired: number
  cashAfterInvestment: number
  monthlyPercentageFees: number
  monthlyFixedAndRecurringCosts: number
  monthlyOperatingProfit: number
  monthlyHouseholdIncomeGap: number
  breakEvenMonthlyRevenue?: number
  runwayMonths?: number
  guaranteeExposure: number
  formulae: Record<string, string>
  evidence: Citation[]
}

export interface ApprovalCheckpoint {
  checkpointId: string
  action: ApprovalAction
  description: string
  payloadHash: string
  sessionId: string
  expiresAt: string
  status: CheckpointStatus
  token?: string
  approvedAt?: string
  details?: Record<string, unknown>
}

export interface DecisionPacket {
  packetId: string
  caseId: string
  runId: string
  revision: number
  decisionState: 'READY_FOR_EXPERT_REVIEW' | 'MORE_EVIDENCE_REQUIRED' | 'MATERIAL_RISK_IDENTIFIED'
  plainLanguageSummary: string
  scopeNotice: string
  investigationPlan: InvestigationPlan
  claimAssessments: ClaimAssessment[]
  riskFindings: RiskFinding[]
  financialScenarios: FinancialScenario[]
  locationAssessment?: Record<string, unknown>
  missingEvidence: string[]
  evidenceIndex: Citation[]
  whyThisChanged: string[]
  validation: { valid: boolean; issues: Array<Record<string, unknown>>; checkedReferences: number; checkedCalculations: number }
  checkpoints: ApprovalCheckpoint[]
  provenance: Array<Record<string, unknown>>
  generatedAt: string
}

export interface RunRecord {
  runId: string
  caseId: string
  sessionId: string
  status: RunStatus
  mode: 'local' | 'strands'
  plan?: InvestigationPlan
  packet?: DecisionPacket
  revision: number
  createdAt: string
  updatedAt: string
  startedAt?: string
  completedAt?: string
  error?: string
  affectedTasks: string[]
}

export interface ApprovalResult {
  checkpointId: string
  status: CheckpointStatus
  action: ApprovalAction
  approvedAt?: string
}

export interface EvidenceSubmission {
  documentId: string
  title: string
  kind: string
  content: string
  source?: string
}
