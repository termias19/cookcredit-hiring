/**
 * RoleRoute — renders different components based on user's active role.
 *
 * Usage:
 *   <RoleRoute eater={<EaterBookingsScreen />} cook={<CookBookingsScreen />} />
 */
import { useAuth } from '../context/AuthContext'

export default function RoleRoute({ eater, cook, fallback = null }) {
  const { profile } = useAuth()
  const roles = profile?.roles || []
  const active = profile?.activeRole || profile?.active_role || 'eater'
  // Acting as a cook requires actually HOLDING the cook role (granted only on
  // approval) — activeRole alone is just a display toggle and must not authorize.
  const isCook = active === 'cook' && roles.includes('cook')

  if (isCook && cook) return cook
  if (!isCook && eater) return eater
  return fallback || eater || cook || null
}
