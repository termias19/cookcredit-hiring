// Keep provider details out of the UI; distinguish access from retryable outages.
export function profileFailure(error) {
  if (error?.code === 'staging_access_denied') return {
    title: 'This account needs a testing invitation',
    message: 'CookCredit testing access has not been enabled for this email address. Use your invited account or contact connectwithus@cookcredit.com.',
    retry: false,
  }
  if (error?.status === 401) return {
    title: 'Please sign in again',
    message: 'Your session could not be verified. Sign out, then sign in to continue.',
    retry: false,
  }
  if (error?.status === 403) return {
    title: 'Your account cannot open this page yet',
    message: 'Check that you are using the correct account. Contact connectwithus@cookcredit.com if you need help with access.',
    retry: false,
  }
  return {
    title: 'We couldn’t load your account',
    message: 'The account service is unavailable or your connection was interrupted. Please try again. Your saved information has not been changed.',
    retry: true,
  }
}
