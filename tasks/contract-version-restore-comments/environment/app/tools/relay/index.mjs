import { WebSocketServer, WebSocket } from 'ws'
import * as decoding from 'lib0/decoding'

let transportSequence = 0

function isDocumentUpdate(data, binary) {
  if (!binary) return false
  try {
    const decoder = decoding.createDecoder(new Uint8Array(data))
    decoding.readVarString(decoder)
    const type = decoding.readVarUint(decoder)
    if (type !== 0 && type !== 4) return false
    const subtype = decoding.readVarUint(decoder)
    return subtype === 1 || subtype === 2
  } catch {
    return false
  }
}

export class Relay {
  constructor(upstream, port = 0, websocketOptions = {}) {
    this.upstream = upstream
    this.websocketOptions = websocketOptions
    this.held = { up: false, down: false }
    this.documentHeld = { up: false, down: false }
    this.queues = { up: [], down: [] }
    this.sockets = new Set()
    this.events = []
    this.lastTraffic = performance.now()
    this.server = new WebSocketServer({ port, host: '127.0.0.1', ...websocketOptions })
    this.server.on('connection', client => {
      const remote = new WebSocket(this.upstream, this.websocketOptions)
      this.sockets.add(client); this.sockets.add(remote)
      const forward = (direction, target, data, binary) => {
        this.lastTraffic = performance.now()
        const documentUpdate = isDocumentUpdate(data, binary)
        const held = this.held[direction] || (this.documentHeld[direction] && documentUpdate)
        this.events.push({ sequence: ++transportSequence, at: performance.now(), event: 'received', direction, bytes: data.length, held, documentUpdate })
        if (this.events.length > 4096) this.events.shift()
        if (direction === 'up') this.onFrame?.(direction, data)
        const deliver = () => {
          if (target.readyState === WebSocket.OPEN) {
            this.events.push({ sequence: ++transportSequence, at: performance.now(), event: 'delivered', direction, bytes: data.length, documentUpdate })
            if (this.events.length > 4096) this.events.shift()
            if (direction === 'down') this.onFrame?.(direction, data)
            target.send(data, { binary })
          }
        }
        if (held) this.queues[direction].push(deliver)
        else if (target.readyState === WebSocket.CONNECTING) target.once('open', deliver)
        else deliver()
      }
      client.on('message', (data, binary) => forward('up', remote, data, binary))
      remote.on('message', (data, binary) => forward('down', client, data, binary))
      client.on('close', () => { remote.close(); this.sockets.delete(client) })
      remote.on('close', () => { client.close(); this.sockets.delete(remote) })
      client.on('error', () => remote.close())
      remote.on('error', () => client.close())
    })
  }
  async ready() {
    if (!this.server.address()) await new Promise(resolve => this.server.once('listening', resolve))
    return `ws://127.0.0.1:${this.server.address().port}`
  }
  hold(direction) { this.held[direction] = true }
  holdDocumentUpdates(direction) { this.documentHeld[direction] = true }
  release(direction) {
    this.held[direction] = false
    this.documentHeld[direction] = false
    const queue = this.queues[direction].splice(0)
    for (const deliver of queue) deliver()
    this.lastTraffic = performance.now()
  }
  releaseAll() { this.release('up'); this.release('down') }
  releaseOne(direction, index = 0) {
    const deliver = this.queues[direction].splice(index, 1)[0]
    if (!deliver) return false
    deliver(); this.lastTraffic = performance.now(); return true
  }
  pending(direction) { return direction ? this.queues[direction].length : this.queues.up.length + this.queues.down.length }
  idle(milliseconds = 500) { return this.pending() === 0 && performance.now() - this.lastTraffic >= milliseconds }
  async close() {
    this.releaseAll()
    for (const socket of this.sockets) socket.terminate()
    await new Promise(resolve => this.server.close(resolve))
  }
}
