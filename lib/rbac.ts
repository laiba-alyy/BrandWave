/**
 * Role-Based Access Control (RBAC) Utilities
 * Functions to check user permissions and roles
 */

export type UserRole = 'admin' | 'user'

/**
 * Check if user is admin
 */
export const isAdmin = (role: string | undefined): boolean => {
  return role === 'admin'
}

/**
 * Check if user is business owner (regular user)
 */
export const isBusinessOwner = (role: string | undefined): boolean => {
  return role === 'user'
}

/**
 * Check if user is authenticated
 */
/**
 * Sirf itna chahiye jitna ye function parhta hai — poora Supabase User type
 * import karne ki zaroorat nahi, aur `any` ki bhi nahi.
 */
export interface MaybeAuthedUser {
  id?: string | null
}

export const isAuthenticated = (user: MaybeAuthedUser | null | undefined): boolean => {
  return !!user && !!user.id
}

/**
 * Check if user can access another user's profile
 * Admin can access anyone, user can only access their own
 */
export const canAccessUserProfile = (
  currentUserId: string,
  targetUserId: string,
  userRole: string | undefined
): boolean => {
  // Admin can access anyone's profile
  if (isAdmin(userRole)) return true

  // User can only access their own profile
  if (currentUserId === targetUserId) return true

  return false
}

/**
 * Check if user can delete another user
 * Only admin can delete users
 */
export const canDeleteUser = (userRole: string | undefined): boolean => {
  return isAdmin(userRole)
}

/**
 * Check if user can edit another user's data
 * Admin can edit anyone, user can only edit their own
 */
export const canEditUser = (
  currentUserId: string,
  targetUserId: string,
  userRole: string | undefined
): boolean => {
  // Admin can edit anyone
  if (isAdmin(userRole)) return true

  // User can only edit their own profile
  if (currentUserId === targetUserId) return true

  return false
}

/**
 * Check if user can change another user's role
 * Only admin can change roles
 */
export const canChangeRole = (userRole: string | undefined): boolean => {
  return isAdmin(userRole)
}

/**
 * Get user dashboard path based on role
 */
export const getDashboardPath = (role: string | undefined): string => {
  if (isAdmin(role)) return '/admin'
  if (isBusinessOwner(role)) return '/business'
  return '/login'
}