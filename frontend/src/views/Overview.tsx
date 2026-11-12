import { useEffect, useState } from 'react'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

const fallbackCards = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
const fallbackModules = [{"name": "贴源层接入", "created": 0, "pending": 0, "abnormal": 0}, {"name": "明细层清洗", "created": 0, "pending": 0, "abnormal": 0}, {"name": "汇总层聚合", "created": 0, "pending": 0, "abnormal": 0}, {"name": "应用层输出", "created": 0, "pending": 0, "abnormal": 0}, {"name": "维度定义管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "事实表管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "分区策略", "created": 0, "pending": 0, "abnormal": 0}, {"name": "质量探针", "created": 0, "pending": 0, "abnormal": 0}, {"name": "血缘图谱", "created": 0, "pending": 0, "abnormal": 0}, {"name": "历史重跑", "created": 0, "pending": 0, "abnormal": 0}, {"name": "元数据目录", "created": 0, "pending": 0, "abnormal": 0}, {"name": "ETL任务调度", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据湖存储", "created": 0, "pending": 0, "abnormal": 0}, {"name": "表结构演进", "created": 0, "pending": 0, "abnormal": 0}, {"name": "运行监控面板", "created": 0, "pending": 0, "abnormal": 0}, {"name": "快照管理", "created": 0, "pending": 0, "abnormal": 0}]

export default function Overview() {
  const [cards, setCards] = useState<Overview['cards']>(fallbackCards)
  const [moduleRows, setModuleRows] = useState<Overview['modules']>(fallbackModules)

  useEffect(() => {
    fetchJson<Overview>('/api/overview')
      .then((payload) => {
        setCards(payload.cards)
        setModuleRows(payload.modules)
      })
      .catch(() => undefined)
  }, [])

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h2>运营概览</h2>
          <p className="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
        </div>
      </header>
      <div className="stat-row">
        {cards.map((card) => (
          <article key={card.label} className="stat-card">
            <span className="stat-label">{card.label}</span>
            <strong className="stat-value">{card.value}</strong>
          </article>
        ))}
      </div>
      <table className="data-table">
        <thead>
          <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
        </thead>
        <tbody>
          {moduleRows.map((row) => (
            <tr key={row.name}>
              <td>{row.name}</td>
              <td>{row.created}</td>
              <td>{row.pending}</td>
              <td>{row.abnormal}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
