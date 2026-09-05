import { useState } from 'react'
import type { FormEvent } from 'react'
import { auditImage, checkCopy, qcImage } from './api'
import type { AuditReport, ComplianceReport, QcIssue, QcReport } from './api'

/* ---------- 标签映射 ---------- */

const DIMENSION_LABELS: Record<string, string> = {
  color: '颜色',
  style: '款式',
  detail: '细节',
  copy: '文案',
  category: '类目',
}

const QC_CATEGORY_LABELS: Record<string, string> = {
  body: '人体结构',
  garment: '服装保真',
  lighting: '光影构图',
  artifact: 'AI 伪影',
  text: '文字',
  scene: '场景',
}

const SEVERITY_META: Record<string, { label: string; className: string }> = {
  blocker: { label: '硬伤', className: 'chip blocker' },
  major: { label: '需修', className: 'chip major' },
  minor: { label: '轻微', className: 'chip minor' },
}

const VERDICT_META: Record<string, { label: string; hint: string; className: string }> = {
  usable: { label: '可直接用', hint: '未发现需要处理的问题', className: 'verdict usable' },
  retouch: { label: '需修图', hint: '存在问题但可以修图解决', className: 'verdict retouch' },
  regenerate: { label: '建议重生成', hint: '存在一眼可见的硬伤', className: 'verdict regenerate' },
}

const STATUS_LABELS: Record<string, { text: string; className: string }> = {
  pass: { text: '相符', className: 'badge pass' },
  mismatch: { text: '不符', className: 'badge mismatch' },
  not_verifiable: { text: '无法判断', className: 'badge unknown' },
}

const RISK_LABELS: Record<string, { text: string; className: string }> = {
  low: { text: '低风险', className: 'risk-badge low' },
  medium: { text: '中风险', className: 'risk-badge medium' },
  high: { text: '高风险', className: 'risk-badge high' },
}

/* ---------- 通用表单字段 ---------- */

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{props.label}</span>
      {props.children}
    </label>
  )
}

/* ---------- 出图质检 ---------- */

function IssueCard({ issue }: { issue: QcIssue }) {
  const meta = SEVERITY_META[issue.severity] ?? SEVERITY_META.minor
  return (
    <div className={`issue-card sev-${issue.severity}`}>
      <div className="issue-head">
        <span className={meta.className}>{meta.label}</span>
        <span className="issue-cat">{QC_CATEGORY_LABELS[issue.category] ?? issue.category}</span>
        <span className="issue-loc">◎ {issue.location}</span>
        <span className="confidence">{Math.round(issue.confidence * 100)}%</span>
      </div>
      <p className="issue-finding">{issue.finding}</p>
      {issue.suggestion && <p className="issue-suggestion">→ {issue.suggestion}</p>}
    </div>
  )
}

function QcResult({ report }: { report: QcReport }) {
  const meta = VERDICT_META[report.verdict]
  return (
    <div className="card result">
      <div className={meta.className}>
        <div className="verdict-label">{meta.label}</div>
        <div className="verdict-hint">{meta.hint}</div>
      </div>
      <p className="summary">{report.summary}</p>
      {report.issues.length > 0 && (
        <div className="issue-list">
          {report.issues.map((issue, i) => (
            <IssueCard key={i} issue={issue} />
          ))}
        </div>
      )}
    </div>
  )
}

function TabQc() {
  const [file, setFile] = useState<File | null>(null)
  const [form, setForm] = useState({ title: '', category: '', color: '', selling_points: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [report, setReport] = useState<QcReport | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) return
    setLoading(true)
    setError('')
    setReport(null)
    try {
      setReport(await qcImage(file, form))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="card">
        <div
          className={`dropzone ${file ? 'has-file' : ''}`}
          onClick={() => document.getElementById('qc-file')?.click()}
        >
          {file ? (
            <>已选择：<strong>{file.name}</strong>（点击可更换）</>
          ) : (
            <>拖拽或点击上传 AIGC 生成图<em>支持 JPG / PNG / WebP，≤ 10MB</em></>
          )}
        </div>
        <input id="qc-file" type="file" accept="image/jpeg,image/png,image/webp" hidden
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div className="grid2">
          <Field label="商品标题（用于服装保真核对）">
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="如：法式方领泡泡袖系带连衣裙" />
          </Field>
          <Field label="类目">
            <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
              placeholder="连衣裙" />
          </Field>
          <Field label="颜色">
            <input value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })}
              placeholder="浅粉色" />
          </Field>
          <Field label="卖点关键词">
            <input value={form.selling_points}
              onChange={(e) => setForm({ ...form, selling_points: e.target.value })}
              placeholder="系带蝴蝶结;蕾丝裙摆;泡泡袖" />
          </Field>
        </div>
        <button type="submit" className="btn-primary" disabled={loading || !file}>
          {loading ? '质检中…' : '开始质检'}
        </button>
      </form>
      {error && <div className="error">{error}</div>}
      {report && <QcResult report={report} />}
    </div>
  )
}

/* ---------- 图文核对 ---------- */

function TabAudit() {
  const [file, setFile] = useState<File | null>(null)
  const [form, setForm] = useState({ title: '', category: '', color: '', selling_points: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [report, setReport] = useState<AuditReport | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) return
    setLoading(true)
    setError('')
    setReport(null)
    try {
      setReport(await auditImage(file, form))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="card">
        <div className={`dropzone ${file ? 'has-file' : ''}`}
          onClick={() => document.getElementById('audit-file')?.click()}>
          {file ? <>已选择：<strong>{file.name}</strong>（点击可更换）</> : <>上传商品图<em>JPG / PNG / WebP，≤ 10MB</em></>}
        </div>
        <input id="audit-file" type="file" accept="image/jpeg,image/png,image/webp" hidden
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div className="grid2">
          <Field label="商品标题">
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </Field>
          <Field label="类目">
            <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required />
          </Field>
          <Field label="颜色">
            <input value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} required />
          </Field>
          <Field label="卖点">
            <input value={form.selling_points}
              onChange={(e) => setForm({ ...form, selling_points: e.target.value })} />
          </Field>
        </div>
        <button type="submit" className="btn-primary" disabled={loading || !file}>
          {loading ? '核对中…' : '开始核对'}
        </button>
      </form>
      {error && <div className="error">{error}</div>}
      {report && (
        <div className="card result">
          <div className={`banner ${report.consistent ? 'ok' : 'bad'}`}>
            {report.consistent ? '✓ 图文相符' : '✗ 图文不符'}
            <span className={RISK_LABELS[report.risk_level].className}>
              {RISK_LABELS[report.risk_level].text}
            </span>
          </div>
          <p className="summary">{report.summary}</p>
          <ul className="checks">
            {report.checks.map((c, i) => (
              <li key={i}>
                <div className="check-head">
                  <span>{DIMENSION_LABELS[c.dimension] ?? c.dimension}</span>
                  <span className={STATUS_LABELS[c.status].className}>{STATUS_LABELS[c.status].text}</span>
                  <span className="confidence">{Math.round(c.confidence * 100)}%</span>
                </div>
                <p>{c.finding}</p>
                {c.suggestion && <p className="issue-suggestion">→ {c.suggestion}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/* ---------- 文案合规 ---------- */

function TabCompliance() {
  const [title, setTitle] = useState('')
  const [points, setPoints] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [report, setReport] = useState<ComplianceReport | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setReport(null)
    try {
      setReport(await checkCopy(title, points))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="card">
        <Field label="商品标题">
          <input value={title} onChange={(e) => setTitle(e.target.value)} required
            placeholder="如：艾莱依可脱卸连帽羽绒服" />
        </Field>
        <Field label="卖点文案（支持多行真实格式）">
          <textarea rows={8} value={points} onChange={(e) => setPoints(e.target.value)}
            placeholder={'卖点文案\t可脱卸连帽 一衣两穿\n戴上时挡风保暖 轻松应对户外…'} />
        </Field>
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? '检测中…' : '检测文案合规'}
        </button>
      </form>
      {error && <div className="error">{error}</div>}
      {report && (
        <div className="card result">
          <div className={`banner ${report.clean ? 'ok' : 'bad'}`}>
            {report.clean ? '✓ 未发现违规风险' : `✗ 发现 ${report.violations.length} 处风险表述`}
          </div>
          <p className="summary">{report.summary}</p>
          {report.violations.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>违规词</th><th>类别</th><th>位置</th><th>原文</th><th>整改建议</th><th>来源</th>
                </tr>
              </thead>
              <tbody>
                {report.violations.map((v, i) => (
                  <tr key={i}>
                    <td className="term">{v.term}</td>
                    <td>{v.category}</td>
                    <td>{v.location === 'title' ? '标题' : '卖点'}</td>
                    <td className="context">{v.context}</td>
                    <td className="suggestion">{v.suggestion}</td>
                    <td>{v.source === 'wordlist' ? '词表' : 'LLM'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

/* ---------- 主框架 ---------- */

const TABS = [
  { id: 'qc', label: '出图质检', hint: 'AIGC 生成图初筛' },
  { id: 'audit', label: '图文核对', hint: '上架前最终核对' },
  { id: 'compliance', label: '文案合规', hint: '极限词检测' },
] as const

export default function App() {
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('qc')
  return (
    <div className="wrap">
      <header className="header">
        <div className="logo-dot" />
        <div>
          <h1>AIGC 出图质检台</h1>
          <p className="subtitle">设计师的自动初筛 · 可直接用 / 需修图 / 建议重生成</p>
        </div>
      </header>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>
            <span className="tab-label">{t.label}</span>
            <span className="tab-hint">{t.hint}</span>
          </button>
        ))}
      </div>
      {tab === 'qc' && <TabQc />}
      {tab === 'audit' && <TabAudit />}
      {tab === 'compliance' && <TabCompliance />}
      <footer className="footer">listing-audit · 自用工具 · 检查清单来自一线质检经验</footer>
    </div>
  )
}
