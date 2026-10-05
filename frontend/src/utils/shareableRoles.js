/** Only open roles accept new applicants. Unknown states fail closed. */
export function shareableRoles(roles) {
  return (roles || []).filter(role => role.status === 'open')
}
export function selectedShareableRole(roles, preferredId) {
  const available = shareableRoles(roles)
  return available.find(role => role.id === preferredId)?.id || available[0]?.id || ''
}
