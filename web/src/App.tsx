import { useState } from 'react'
import type { FormEvent } from 'react'
import { auditImage, checkCopy, qcImage } from './api'
import type { AuditReport, ComplianceReport, QcIssue, QcReport } from './api'

const MAX_BATCH = 20
const CONCURRENCY = 3

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

const VERDICT_META: Record<string, { label: string; className: string }> = {
  usable: { label: '可直接用', className: 'verdict-chip usable' },
  retouch: { label: '需修图', className: 'verdict-chip retouch' },
  regenerate: { label: '建议重生成', className: 'verdict-chip regenerate' },
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

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{props.label}</span>
      {props.children}
    </label>
  )
}

/* ---------- 单张质检结果 ---------- */

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

/* ---------- 批量出图质检 ---------- */

type ItemStatus = 'pending' | 'running' | 'done' | 'error'

interface BatchItem {
  id: number
  file: File
  previewUrl: string
  status: ItemStatus
  report?: QcReport
  error?: string
}

function BatchQc() {
  const [items, setItems] = useState<BatchItem[]>([])
  const [form, setForm] = useState({ title: '', category: '', color: '', selling_points: '' })
  const [running, setRunning] = useState(false)
  const [notice, setNotice] = useState('')
  const [hideUsable, setHideUsable] = useState(false)
  const [formError, setFormError] = useState('')

  const selectFiles = (fileList: FileList | null) => {
    setFormError('')
    if (!fileList || fileList.length === 0) return
    if (fileList.length > MAX_BATCH) {
      setFormError(`一次最多 ${MAX_BATCH} 张，已选择 ${fileList.length} 张，请分批`)
      return
    }
    const bad = Array.from(fileList).filter((f) => f.size > 10 * 1024 * 1024)
    if (bad.length > 0) {
      setFormError(`以下图片超过 10MB：${bad.map((f) => f.name).join('、')}`)
      return
    }
    setItems(
      Array.from(fileList).map((file, i) => ({
        id: Date.now() + i,
        file,
        previewUrl: URL.createObjectURL(file),
        status: 'pending' as ItemStatus,
      })),
    )
  }

  const patch = (id: number, update: Partial<BatchItem>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...update } : it)))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const pending = items.filter((it) => it.status !== 'done')
    if (pending.length === 0 || running) return
    setRunning(true)
    setNotice('')

    let nextIdx = 0
    const worker = async () => {
      while (nextIdx < pending.length) {
        const item = pending[nextIdx++]
        patch(item.id, { status: 'running', error: undefined })
        try {
          const report = await qcImage(item.file, form)
          patch(item.id, { status: 'done', report })
        } catch (err) {
          patch(item.id, { status: 'error', error: err instanceof Error ? err.message : String(err) })
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, pending.length) }, worker))
    setRunning(false)
    setNotice('本批次质检完成')
  }

  const doneItems = items.filter((it) => it.status === 'done' && it.report)
  const stats = { usable: 0, retouch: 0, regenerate: 0 }
  for (const it of doneItems) stats[it.report!.verdict] += 1
  const failed = items.filter((it) => it.status === 'error')
  const finished = items.every((it) => it.status === 'done' || it.status === 'error') && items.length > 0
  const visible = hideUsable
    ? items.filter((it) => it.status === 'error' || (it.report && it.report.verdict !== 'usable'))
    : items

  return (
    <div>
      <form onSubmit={submit} className="card">
        <div
          className={`dropzone ${items.length > 0 ? 'has-file' : ''}`}
          onClick={() => document.getElementById('qc-file')?.click()}
        >
          {items.length > 0 ? (
            <>已选择 <strong>{items.length}</strong> 张（点击可重新选择，单次最多 {MAX_BATCH} 张）</>
          ) : (
            <>拖拽或点击上传 AIGC 生成图，支持一次多选<em>最多 {MAX_BATCH} 张 · JPG / PNG / WebP · 单张 ≤ 10MB · 同一商品的候选图共用下方商品信息</em></>
          )}
        </div>
        <input id="qc-file" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
          onChange={(e) => { selectFiles(e.target.files); e.target.value = '' }} />
        {formError && <div className="error">{formError}</div>}
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
        <button type="submit" className="btn-primary" disabled={running || items.length === 0}>
          {running
            ? `质检中…（已完成 ${doneItems.length + failed.length}/${items.length}）`
            : items.length > 0
              ? `批量质检 ${items.length} 张`
              : '批量质检'}
        </button>
        {running && <span className="hint-inline">3 路并发，每张约 15-40 秒，请勿关闭页面</span>}
      </form>
      {notice && finished && <div className="notice">{notice}</div>}

      {items.length > 0 && (
        <div className="card result">
          {finished && doneItems.length > 0 && (
            <div className="batch-stats">
              <span className="stat usable-stat">可直接用 {stats.usable}</span>
              <span className="stat retouch-stat">需修图 {stats.retouch}</span>
              <span className="stat regenerate-stat">建议重生成 {stats.regenerate}</span>
              {failed.length > 0 && <span className="stat error-stat">失败 {failed.length}</span>}
              <label className="toggle">
                <input type="checkbox" checked={hideUsable} onChange={(e) => setHideUsable(e.target.checked)} />
                只看有问题
              </label>
            </div>
          )}
          <div className="batch-list">
            {visible.map((it) => (
              <div key={it.id} className="batch-item">
                <img src={it.previewUrl} alt={it.file.name} className="thumb" />
                <div className="batch-item-body">
                  <div className="batch-item-head">
                    <span className="file-name" title={it.file.name}>{it.file.name}</span>
                    {it.status === 'pending' && <span className="badge unknown">排队中</span>}
                    {it.status === 'running' && <span className="badge running">质检中…</span>}
                    {it.status === 'error' && <span className="badge mismatch">失败</span>}
                    {it.report && <span className={VERDICT_META[it.report.verdict].className}>
                      {VERDICT_META[it.report.verdict].label}
                    </span>}
                  </div>
                  {it.error && <p className="issue-finding">{it.error}</p>}
                  {it.report && (
                    <>
                      <p className="summary">{it.report.summary}</p>
                      {it.report.issues.length > 0 && (
                        <div className="issue-list">
                          {it.report.issues.map((issue, i) => (
                            <IssueCard key={i} issue={issue} />
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
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
  { id: 'qc', label: '出图质检', hint: 'AIGC 候选图批量初筛' },
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
          <p className="subtitle">设计师的自动初筛 · 批量 {MAX_BATCH} 张 · 可直接用 / 需修图 / 建议重生成</p>
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
      {tab === 'qc' && <BatchQc />}
      {tab === 'audit' && <TabAudit />}
      {tab === 'compliance' && <TabCompliance />}
      <footer className="footer">listing-audit · 自用工具 · 检查清单来自一线质检经验</footer>
    </div>
  )
}
