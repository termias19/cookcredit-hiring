/** Recover only this identity's missing profile; never depend on browser storage. */
export async function loadAccountProfile(account, { request, suppliedProfile, readDraft, clearDraft }) {
  const token = await account.getIdToken()
  let draft
  try { draft = readDraft() } catch { /* Restricted browser storage. */ }
  const values = suppliedProfile || (draft?.uid === account.uid ? draft.profile : null)
  const sync = profile => request('/api/auth/sync', token, { method: 'POST', body: JSON.stringify(profile) })
  if (values) {
    await sync(values)
    try { clearDraft() } catch { /* Storage is not required for successful login. */ }
  }
  try {
    return await request('/api/auth/me', token)
  } catch (error) {
    // Forbidden, unavailable and network failures must never create another account.
    if (error?.status !== 404) throw error
    await sync(values || {
      name: account.displayName || (account.email || '').split('@')[0] || 'User',
      roles: ['eater'], activeRole: 'eater', createOnly: true,
    })
    return request('/api/auth/me', token)
  }
}
