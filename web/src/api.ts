export interface CheckItem {
  dimension: string
  status: 'pass' | 'mismatch' | 'not_verifiable'
  finding: string
  suggestion: string | null
  confidence: number
}

export interface AuditReport {
  consistent: boolean
  risk_level: 'low' | 'medium' | 'high'
  checks: CheckItem[]
  summary: string
}

export interface Violation {
  term: string
  category: string
  location: 'title' | 'selling_points'
  context: string
  suggestion: string
  source: 'wordlist' | 'llm'
  confidence: number
}

export interface ComplianceReport {
  clean: boolean
  violations: Violation[]
  summary: string
}

export type QcVerdict = 'usable' | 'retouch' | 'regenerate'

export interface QcIssue {
  category: string
  severity: 'blocker' | 'major' | 'minor'
  location: string
  finding: string
  suggestion: string | null
  confidence: number
}

export interface QcReport {
  verdict: QcVerdict
  issues: QcIssue[]
  summary: string
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail ?? `请求失败（${resp.status}）`)
  }
  return resp.json()
}

function form(data: Record<string, string>): FormData {
  const fd = new FormData()
  for (const [k, v] of Object.entries(data)) fd.append(k, v)
  return fd
}

export async function qcImage(
  file: File,
  data: { title: string; category: string; color: string; selling_points: string },
): Promise<QcReport> {
  const fd = form(data)
  fd.append('image', file)
  return handle(await fetch('/api/qc', { method: 'POST', body: fd }))
}

export async function auditImage(
  file: File,
  data: { title: string; category: string; color: string; selling_points: string },
): Promise<AuditReport> {
  const fd = form(data)
  fd.append('image', file)
  return handle(await fetch('/api/audit', { method: 'POST', body: fd }))
}

export async function checkCopy(title: string, points: string): Promise<ComplianceReport> {
  return handle(await fetch('/api/compliance', { method: 'POST', body: form({ title, points }) }))
}
