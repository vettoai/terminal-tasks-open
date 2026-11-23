export interface RelayEvent {
  sequence: number
  at: number
  event: 'received' | 'delivered'
  direction: 'up' | 'down'
  bytes: number
  held?: boolean
  documentUpdate: boolean
}

export class Relay {
  constructor(upstream: string, port?: number, websocketOptions?: { maxPayload?: number })
  events: RelayEvent[]
  sockets: Set<WebSocket>
  ready(): Promise<string>
  hold(direction: 'up' | 'down'): void
  holdDocumentUpdates(direction: 'up' | 'down'): void
  release(direction: 'up' | 'down'): void
  releaseAll(): void
  releaseOne(direction: 'up' | 'down', index?: number): boolean
  pending(direction?: 'up' | 'down'): number
  idle(milliseconds?: number): boolean
  close(): Promise<void>
}
import type { WebSocket } from 'ws'
