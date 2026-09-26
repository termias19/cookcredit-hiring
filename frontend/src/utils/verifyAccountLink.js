export function sameAccountEmail(account, email) {
  return Boolean(account?.email && email && account.email.toLowerCase() === email.toLowerCase())
}

// Applying an email code verifies its own account; it never signs another
// account in. Do not refresh or route an unrelated existing employer session.
export async function verifyAccountLink({ auth, code, checkCode, applyCode, complete }) {
  const info = await checkCode(auth, code)
  if (info.operation !== 'VERIFY_EMAIL' || !info.data?.email) throw new Error('Invalid verification link')
  await applyCode(auth, code)
  const email = info.data.email
  if (!sameAccountEmail(auth.currentUser, email)) return { email, profile: null }
  // Verification has already succeeded. A profile/API outage must not label
  // the now-consumed code invalid or require a second account.
  const profile = await complete().catch(() => null)
  if (!sameAccountEmail(auth.currentUser, email) || profile?.id !== auth.currentUser?.uid) return { email, profile: null }
  return { email, profile }
}
