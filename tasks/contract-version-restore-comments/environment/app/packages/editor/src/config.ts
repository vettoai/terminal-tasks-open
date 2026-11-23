export function httpBase(): string {
  const configured = typeof process !== 'undefined' ? process.env.CONTRACT_HTTP_URL : undefined
  return configured || (globalThis as any).CONTRACT_HTTP_URL || 'http://127.0.0.1:1234'
}
