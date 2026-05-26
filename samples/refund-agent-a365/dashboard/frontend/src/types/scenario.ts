/** Chat message */
export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
}

/** Route stop for package path visualization */
export interface RouteStop {
  location: string
  type: 'origin' | 'hub' | 'destination'
  status: 'completed' | 'current' | 'stuck' | 'upcoming'
}

/** All WebSocket message types from server */
export type ServerMessage =
  | { type: 'chat_message'; role: 'user' | 'assistant'; text: string }
  | { type: 'thinking' }
  | { type: 'tool_calling' }
  | { type: 'tool_result'; tool: string; result: Record<string, unknown> }
  | { type: 'shipment_data'; payload: { tables: Array<Array<Record<string, string>>>; entities: Array<{ id: string; type: string; label: string; color: string; shape: string }>; entity_counts: Record<string, number>; focus_query?: string; refund_recommended?: boolean; package_route?: RouteStop[]; stuck_at?: string; package_id?: string } }
  | { type: 'error'; error: string }
