import { Fragment, useEffect, useRef, useState } from 'react'
import type { RouteStop } from '../types/scenario'

export interface ShipmentEntity {
  id: string
  type: string
  label: string
  color: string
  shape: string
}

export interface ShipmentData {
  tables: Array<Array<Record<string, string>>>
  entities: ShipmentEntity[]
  entity_counts: Record<string, number>
  focus_query?: string
  narrative?: string
  refund_recommended?: boolean
  package_route?: RouteStop[]
  stuck_at?: string
  package_id?: string
}

interface ShipmentDashboardProps {
  shipmentData: ShipmentData | null
  isLookingUp: boolean
  focusQuery?: string | null
}

const ENTITY_ICONS: Record<string, string> = {
  package: '\u{1F4E6}',
  hub: '\u{1F3ED}',
  driver: '\u{1F69A}',
  customer: '\u{1F464}',
  handoff: '\u{1F91D}',
}

const ENTITY_LABELS: Record<string, string> = {
  package: 'Packages',
  hub: 'Hubs',
  driver: 'Drivers',
  customer: 'Customers',
  handoff: 'Handoffs',
}

function getStatusColor(value: string): { bg: string; text: string } | null {
  const lower = value.toLowerCase()
  if (lower.includes('delivered') || lower.includes('on time') || lower.includes('completed'))
    return { bg: '#dcfce7', text: '#16a34a' }
  if (lower.includes('in transit') || lower.includes('active') || lower.includes('processing'))
    return { bg: '#dbeafe', text: '#2563eb' }
  if (lower.includes('late') || lower.includes('delayed') || lower.includes('overdue'))
    return { bg: '#fee2e2', text: '#dc2626' }
  if (lower.includes('pending') || lower.includes('scheduled'))
    return { bg: '#fef3c7', text: '#d97706' }
  return null
}

function DataTable({ table, index }: { table: Array<Record<string, string>>; index: number }) {
  if (!table.length) return null
  const headers = Object.keys(table[0])

  return (
    <div className="shipment-card" data-table-index={index}>
      <div className="shipment-table-wrapper">
        <table className="shipment-table">
          <thead>
            <tr>
              {headers.map(h => (
                <th key={h}>{h.replace(/_/g, ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.map((row, ri) => (
              <tr key={ri}>
                {headers.map(h => {
                  const val = row[h] || ''
                  const statusColor = getStatusColor(val)
                  return (
                    <td key={h}>
                      {statusColor ? (
                        <span
                          className="status-badge"
                          style={{ backgroundColor: statusColor.bg, color: statusColor.text }}
                        >
                          {val}
                        </span>
                      ) : (
                        val
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function EntitySummary({ entityCounts }: { entityCounts: Record<string, number> }) {
  const types = Object.keys(entityCounts)
  if (!types.length) return null

  return (
    <div className="entity-summary">
      {types.map(type => (
        <div key={type} className="summary-stat">
          <span className="summary-icon">{ENTITY_ICONS[type] || '\u{1F4CB}'}</span>
          <span className="summary-value">{entityCounts[type]}</span>
          <span className="summary-label">{ENTITY_LABELS[type] || type}</span>
        </div>
      ))}
    </div>
  )
}

function EntityCards({ entities }: { entities: ShipmentEntity[] }) {
  if (!entities.length) return null

  const grouped: Record<string, ShipmentEntity[]> = {}
  for (const e of entities) {
    if (!grouped[e.type]) grouped[e.type] = []
    grouped[e.type].push(e)
  }

  return (
    <div className="entity-cards-section">
      {Object.entries(grouped).map(([type, items]) => (
        <div key={type} className="entity-group">
          <h3 className="section-title">
            {ENTITY_ICONS[type] || '\u{1F4CB}'} {ENTITY_LABELS[type] || type}
          </h3>
          <div className="entity-chip-grid">
            {items.map(e => (
              <div
                key={e.id}
                className="entity-chip"
                style={{ borderLeftColor: e.color }}
              >
                <span className="entity-chip-id">{e.id}</span>
                <span className="entity-chip-type">{e.type}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function PackagePathVisualization({ route, packageId }: { route: RouteStop[]; packageId?: string }) {
  return (
    <div className="package-path-card" data-testid="package-path-visualization">
      <h3 className="section-title">
        {'\u{1F4E6}'} Package Route{packageId ? ` — ${packageId}` : ''}
      </h3>
      <div className="package-path">
        {route.map((stop, i) => {
          const prevStatus = i > 0 ? route[i - 1].status : null
          let connectorClass = 'completed'
          if (stop.status === 'stuck') {
            connectorClass = 'stuck'
          } else if (stop.status === 'upcoming' || prevStatus === 'stuck') {
            connectorClass = 'upcoming'
          }

          return (
            <Fragment key={i}>
              {i > 0 && (
                <div className={`path-connector ${connectorClass}`} />
              )}
              <div className={`path-node ${stop.status}`}>
                <div className="path-node-dot">
                  {stop.status === 'completed' && '\u2713'}
                  {stop.status === 'stuck' && '!'}
                  {stop.status === 'current' && '\u25CF'}
                </div>
                <span className="path-node-label">{stop.location}</span>
                {stop.status === 'stuck' && (
                  <span className="path-node-status">Delayed</span>
                )}
              </div>
            </Fragment>
          )
        })}
      </div>
    </div>
  )
}

function GrantRefundButton() {
  const [granted, setGranted] = useState(false)

  return (
    <div className="grant-refund-container" data-testid="grant-refund-section">
      <button
        className={`grant-refund-button ${granted ? 'granted' : ''}`}
        onClick={() => setGranted(true)}
        data-testid="grant-refund-button"
      >
        {granted ? '\u2713 Refund Granted' : 'Grant Refund'}
      </button>
    </div>
  )
}

export function ShipmentDashboard({ shipmentData, isLookingUp, focusQuery }: ShipmentDashboardProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (shipmentData && scrollRef.current) {
      scrollRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [shipmentData])

  if (isLookingUp) {
    return (
      <div className="dashboard-panel">
        <div className="dashboard-loading">
          <div className="dashboard-loading-spinner"></div>
          <p>Querying delivery network...</p>
        </div>
      </div>
    )
  }

  if (!shipmentData) {
    return (
      <div className="dashboard-panel">
        <div className="dashboard-empty">
          <div className="dashboard-empty-icon">{'\u{1F4E6}'}</div>
          <h2>Shipment Dashboard</h2>
          <p>Ask about packages, deliveries, routes, or hubs and the details will appear here.</p>
          <div className="dashboard-empty-examples">
            <span>Try: &quot;How many packages are in the system?&quot; or &quot;Show me all late deliveries&quot;</span>
          </div>
        </div>
      </div>
    )
  }

  const hasTables = shipmentData.tables && shipmentData.tables.length > 0
  const hasEntities = shipmentData.entities && shipmentData.entities.length > 0
  const hasEntityCounts = shipmentData.entity_counts && Object.keys(shipmentData.entity_counts).length > 0
  const hasNarrative = shipmentData.narrative && shipmentData.narrative.trim().length > 0
  const hasRefund = shipmentData.refund_recommended && shipmentData.package_route && shipmentData.package_route.length > 0

  return (
    <div className="dashboard-scroll-container" ref={scrollRef}>
      <div className="dashboard-content">
        {focusQuery && (
          <div className="dashboard-query-bar">
            <span className="query-icon">{'\u{1F50D}'}</span>
            <span className="query-text">{focusQuery}</span>
          </div>
        )}

        {hasRefund && (
          <PackagePathVisualization
            route={shipmentData.package_route!}
            packageId={shipmentData.package_id}
          />
        )}

        {hasRefund && <GrantRefundButton />}

        {hasEntityCounts && (
          <EntitySummary entityCounts={shipmentData.entity_counts} />
        )}

        {hasTables && shipmentData.tables.map((table, i) => (
          <DataTable key={i} table={table} index={i} />
        ))}

        {hasEntities && !hasTables && (
          <EntityCards entities={shipmentData.entities} />
        )}

        {!hasTables && !hasEntities && !hasRefund && hasNarrative && (
          <div className="shipment-card" style={{ padding: '24px' }}>
            <div style={{ fontSize: 14, lineHeight: 1.7, color: '#334155', whiteSpace: 'pre-wrap' }}>
              {shipmentData.narrative}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
