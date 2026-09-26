export function errorReference(data, response) {
  const id = data?.requestId || response.headers?.get?.('X-Request-ID')
  return response.status >= 500 && /^[a-f0-9]{32}$/.test(id || '') ? id : null
}
