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

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail ?? `请求失败（${resp.status}）`)
  }
  return resp.json()
}

export async function auditImage(
  file: File,
  data: { title: string; category: string; color: string; selling_points: string },
): Promise<AuditReport> {
  const fd = new FormData()
  fd.append('image', file)
  fd.append('title', data.title)
  fd.append('category', data.category)
  fd.append('color', data.color)
  fd.append('selling_points', data.selling_points)
  return handle(await fetch('/api/audit', { method: 'POST', body: fd }))
}

export async function checkCopy(title: string, points: string): Promise<ComplianceReport> {
  const fd = new FormData()
  fd.append('title', title)
  fd.append('selling_points', points)
  return handle(await fetch('/api/compliance', { method: 'POST', body: fd }))
}
