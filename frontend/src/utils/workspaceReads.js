/** Settings need company metadata, not the candidate roster and saved list. */
export function workspaceReads(pathname, search = '') {
  const settings = ['/business/profile', '/business/team', '/business/integrations', '/business/billing', '/business/onboarding'].includes(pathname)
  const integration = pathname === '/business/integrations' || (pathname === '/business/profile' && new URLSearchParams(search).get('section') === 'integrations')
  const roleList = pathname === '/business/roles' || pathname === '/business/role/new' || /^\/business\/role\/[^/]+\/edit$/.test(pathname)
  return { roles: !settings || integration, candidates: !settings && !roleList, shortlist: !settings && !roleList }
}
