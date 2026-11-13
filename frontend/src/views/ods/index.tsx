import { useCallback, useEffect, useMemo, useState } from 'react'

import { downloadFile, request } from '@/api/client'

const ENDPOINT = '/api/ods'
const columns = [
  "流水编号",
  "来源系统",
  "源表名称",
  "落地表名",
  "接入周期",
  "分区粒度",
  "保留天数",
  "最近接入时间",
  "接入状态",
  "分区水位",
  "可准入",
  "准入结论"
]
const statuses = [
  "草稿",
  "运行中",
  "已暂停",
  "已完成"
]
// 与后端状态机 NEXT_ACTIONS 保持一致：页面只暴露合法动作，非法跳级在前端即收起
const nextActions: Record<string, string[]> = {
  "草稿": ["启动接入"],
  "运行中": ["暂停接入", "完成接入"],
  "已暂停": ["启动接入", "归档流水"],
  "已完成": ["归档流水"]
}
const stats = [
  {
    "label": "接入流水总数",
    "value": 0
  },
  {
    "label": "运行中流水",
    "value": 0
  },
  {
    "label": "已暂停流水",
    "value": 0
  }
]

type Row = Record<string, string | number | boolean | null>

export default function OdsView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [filters, setFilters] = useState<{ keyword: string; status: string }>({ keyword: '', status: '' })

  const reload = useCallback(async () => {
    setErrorMessage('')
    const params = new URLSearchParams()
    if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
    if (filters.status) params.set('status', filters.status)
    try {
      const response = await request(`${ENDPOINT}?${params.toString()}`)
      if (!response.ok) {
        throw new Error('接入流水列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '贴源层接入列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(action: string, row: Row) {
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action, expected_version: row.version }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        // 409 版本冲突或业务非法流转都把后端说明展示给值班同事
        throw new Error(payload.detail ?? payload.message ?? '贴源层接入动作未生效')
      }
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '贴源层接入操作失败')
    }
  }

  const handleExport = useCallback(async () => {
    setErrorMessage('')
    const params = new URLSearchParams()
    if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
    if (filters.status) params.set('status', filters.status)
    try {
      await downloadFile(`${ENDPOINT}/export?${params.toString()}`, 'ods_access_entries.csv')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '贴源层接入清单导出失败')
    }
  }, [filters])

  const filterFields = useMemo(() => ["流水编号"], [])

  return (
    <section className="page" data-module="ods">
      <header className="page-head">
        <div>
          <h2>贴源层接入管理</h2>
          <p className="page-desc">维护贴源层接入流水的配置、执行状态与落地记录，状态按草稿→运行中→已暂停→已完成单向推进，为明细清洗提供统一准入结论。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('接入流水登记入口尚未接入审批流')}>
            登记接入流水
          </button>
          <button className="btn" type="button" onClick={() => void handleExport()}>
            导出贴源层接入清单
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
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters.keyword}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, keyword: event.target.value }))}
            />
          </label>
        ))}
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
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({ keyword: '', status: '' })}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const archived = row.归档标记 === '是'
            const legalActions = archived ? [] : (nextActions[String(row.status)] ?? [])
            return (
              <tr key={String(row.id)} className={archived ? 'row-archived' : ''}>
                {columns.map((column) => (
                  <td key={column}>
                    {column === '接入状态' ? (
                      <span className={`status-badge status-${String(row.status)}`}>{String(row.status ?? '—')}</span>
                    ) : column === '可准入' ? (
                      <span className={`admission-badge admission-${row[column] === '是' ? 'yes' : 'no'}`}>
                        {String(row[column] ?? '—')}
                      </span>
                    ) : (
                      String(row[column] ?? '—')
                    )}
                  </td>
                ))}
                <td className="row-actions">
                  {legalActions.length === 0 && <span className="muted-text">—</span>}
                  {legalActions.map((action) => (
                    <button key={action} className="link" type="button" onClick={() => void runAction(action, row)}>
                      {action}
                    </button>
                  ))}
                </td>
              </tr>
            )
          })}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无贴源层接入数据，可先登记接入流水</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条贴源层接入记录</span>
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
