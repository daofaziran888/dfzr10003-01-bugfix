import { useCallback, useEffect, useState } from 'react'

import { downloadFile, request } from '@/api/client'

const ENDPOINT = '/api/dwd'
const columns = [
  "流水编号",
  "输入表名",
  "输出表名",
  "接入状态",
  "分区水位",
  "执行批次",
  "可准入",
  "准入结论"
]
const statuses = [
  "草稿",
  "运行中",
  "已暂停",
  "已完成"
]
const admissionOptions = ["可准入", "不可准入"]
const stats = [
  {
    "label": "清洗准入总数",
    "value": 0
  },
  {
    "label": "可准入流水",
    "value": 0
  },
  {
    "label": "不可准入流水",
    "value": 0
  }
]

type Row = Record<string, string | number | null>
type Filters = { keyword: string; status: string; admission: string }

export default function DwdView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [filters, setFilters] = useState<Filters>({ keyword: '', status: '', admission: '' })

  const reload = useCallback(async () => {
    setErrorMessage('')
    const params = new URLSearchParams()
    if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
    if (filters.status) params.set('status', filters.status)
    if (filters.admission) params.set('admission', filters.admission)
    try {
      const response = await request(`${ENDPOINT}?${params.toString()}`)
      if (!response.ok) {
        throw new Error('明细清洗准入清单读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '明细层清洗列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  const handleExport = useCallback(async () => {
    setErrorMessage('')
    const params = new URLSearchParams()
    if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
    if (filters.status) params.set('status', filters.status)
    if (filters.admission) params.set('admission', filters.admission)
    try {
      await downloadFile(`${ENDPOINT}/export?${params.toString()}`, 'dwd_admission_entries.csv')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '明细层清洗清单导出失败')
    }
  }, [filters])

  return (
    <section className="page" data-module="dwd">
      <header className="page-head">
        <div>
          <h2>明细层清洗管理</h2>
          <p className="page-desc">清洗准入清单由贴源层接入流水实时派生，两个入口共用同一条状态结论；仅运行中、已完成的接入可进入待清洗队列，已归档流水不再出现。</p>
        </div>
        <div className="page-actions">
          <button className="btn" type="button" onClick={() => void handleExport()}>
            导出明细层清洗清单
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        <label className="filter-item">
          <span>流水编号</span>
          <input
            value={filters.keyword}
            placeholder="按流水编号检索"
            onChange={(event) => setFilters((prev) => ({ ...prev, keyword: event.target.value }))}
          />
        </label>
        <label className="filter-item">
          <span>接入状态</span>
          <select
            value={filters.status}
            onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
          >
            <option value="">全部状态</option>
            {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
          </select>
        </label>
        <label className="filter-item">
          <span>准入结论</span>
          <select
            value={filters.admission}
            onChange={(event) => setFilters((prev) => ({ ...prev, admission: event.target.value }))}
          >
            <option value="">全部结论</option>
            {admissionOptions.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({ keyword: '', status: '', admission: '' })}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => (
                <td key={column}>
                  {column === '接入状态' ? (
                    <span className={`status-badge status-${String(row[column])}`}>{String(row[column] ?? '—')}</span>
                  ) : column === '可准入' ? (
                    <span className={`admission-badge admission-${row[column] === '是' ? 'yes' : 'no'}`}>
                      {String(row[column] ?? '—')}
                    </span>
                  ) : (
                    String(row[column] ?? '—')
                  )}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length}>当前没有可展示的清洗准入记录（已归档流水不会进入待清洗队列）</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条清洗准入记录</span>
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
