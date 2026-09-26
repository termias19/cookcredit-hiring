// Use stable, safe copy for known API failures; never display raw server diagnostics.
export function rolePublicationError(error) {
  if (error?.status === 409 && error.message === 'The trial includes one open role') {
    return 'This workspace already has its one open trial role. Open your existing role from Roles, or contact CookCredit about additional role access.'
  }
  if (error?.status === 409 && error.message === 'Free early access includes five open roles') {
    return 'This workspace already has five open roles, the free early-access allowance. Open your existing roles from Roles, or contact CookCredit about additional role access.'
  }
  if (error?.status === 401) return 'Your session has expired. Sign in again before publishing this role.'
  if (error?.status === 403) return 'Your account does not have permission to publish roles in this workspace.'
  if (error?.status === 429) return 'Too many requests. Wait a moment before trying to publish again.'
  const validation = new Set(['Title required', 'Work location required for an open role', 'Pay minimum cannot exceed pay maximum', 'One or more application questions are invalid', 'Activate a workspace first'])
  if (error?.status === 400 && validation.has(error.message)) return error.message
  return 'Could not publish the role. Your entries are still here. Check your connection and try again.'
}
