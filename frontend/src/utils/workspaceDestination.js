export function workspaceDestination(pathname, search = '') {
  const params = new URLSearchParams(search)
  const section = { '/business/team': 'team', '/business/integrations': 'integrations', '/business/billing': 'billing' }[pathname]
  if (section) { params.set('section', section); return `/business/profile?${params}` }
  if (pathname === '/business/shortlists') { params.set('view', 'saved'); return `/business/candidates?${params}` }
  return `${pathname}${search}`
}
