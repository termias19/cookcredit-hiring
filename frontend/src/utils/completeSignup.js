/** Once Firebase creates the account, an API/email outage must not invite the
 * customer to create that account a second time. Both operations can be retried
 * after sign-in. Keep the submitted profile intent for profile-sync recovery.
 */
export async function completeSignup({ user, profile, updateName, sync, verify, remember, clear }) {
  if (profile.name?.trim()) await updateName(user, profile.name.trim()).catch(() => {})
  remember(user.uid, profile)
  let profileSynced = false
  let verificationSent = false
  try {
    await sync(user, profile)
    clear()
    profileSynced = true
  } catch { /* The verification screen remains reachable and sync can retry. */ }
  try { await verify(user); verificationSent = true }
  catch { /* Resend is available for this same account. */ }
  return { profileSynced, verificationSent }
}
