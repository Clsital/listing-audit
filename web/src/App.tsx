import { useState } from 'react'
import type { FormEvent } from 'react'
import { auditImage, checkCopy } from './api'
import type { AuditReport, ComplianceReport } from './api'

const DIMENSION_LABELS: Record<string, string> = {
  color: '颜色',
  style: '款式',
  detail: '细节',
  copy: '文案',
  category: '类目',
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
        <label>
          商品标题
          <input value={title} onChange={(e) => setTitle(e.target.value)} required
            placeholder="如：艾莱依可脱卸连帽羽绒服" />
        </label>
        <label>
          卖点文案（支持多行真实格式）
          <textarea rows={8} value={points} onChange={(e) => setPoints(e.target.value)}
            placeholder={'卖点文案\t可脱卸连帽 一衣两穿\n戴上时挡风保暖 轻松应对户外…'} />
        </label>
        <button type="submit" disabled={loading}>
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
        <label>
          商品图
          <input type="file" accept="image/jpeg,image/png,image/webp"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        </label>
        <div className="grid2">
          <label>
            商品标题
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </label>
          <label>
            类目
            <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required />
          </label>
          <label>
            颜色
            <input value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} required />
          </label>
          <label>
            卖点（分号分隔）
            <input value={form.selling_points}
              onChange={(e) => setForm({ ...form, selling_points: e.target.value })} />
          </label>
        </div>
        <button type="submit" disabled={loading || !file}>
          {loading ? '审核中…' : '审核图文一致性'}
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
                  <span className={STATUS_LABELS[c.status].className}>
                    {STATUS_LABELS[c.status].text}
                  </span>
                  <span className="confidence">{Math.round(c.confidence * 100)}%</span>
                </div>
                <p>{c.finding}</p>
                {c.suggestion && <p className="suggestion">建议：{c.suggestion}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState<'compliance' | 'audit'>('compliance')
  return (
    <div className="wrap">
      <h1>商品上架前检查台</h1>
      <p className="subtitle">文案合规（极限词）＋ 图文属性一致性 —— 上架前拦截违规与不符</p>
      <div className="tabs">
        <button className={tab === 'compliance' ? 'active' : ''} onClick={() => setTab('compliance')}>
          文案合规
        </button>
        <button className={tab === 'audit' ? 'active' : ''} onClick={() => setTab('audit')}>
          图文一致性
        </button>
      </div>
      {tab === 'compliance' ? <TabCompliance /> : <TabAudit />}
    </div>
  )
}
