import { z } from 'zod'

export const loginSchema = z.object({
  email: z
    .string()
    .email('Invalid email address')
    .min(1, 'Email is required'),
  password: z
    .string()
    .min(1, 'Password is required')
    .min(6, 'Password must be at least 6 characters'),
})

export type LoginInput = z.infer<typeof loginSchema>

/*
 * Signup + password recovery ke schemas.
 *
 * Password rules teen jagah chahiye: signup, reset-password aur (UI mein) live
 * checklist. Is liye rules yahan ek jagah likhe hain aur `passwordChecks()`
 * wohi teen shartein return karta hai jo `strongPassword` enforce karta hai —
 * warna checklist green dikha kar submit par error dena mumkin ho jata.
 */
export const strongPassword = z
  .string()
  .min(8, 'Use at least 8 characters')
  .regex(/[A-Z]/, 'Add at least one uppercase letter')
  .regex(/[^A-Za-z0-9]/, 'Add at least one special character')

export function passwordChecks(password: string) {
  return {
    minLength: password.length >= 8,
    hasUppercase: /[A-Z]/.test(password),
    hasSpecial: /[^A-Za-z0-9]/.test(password),
  }
}

export const signupSchema = z
  .object({
    businessName: z.string().trim().min(2, 'Business name is required'),
    email: z.string().email('Invalid email address'),
    password: strongPassword,
    confirmPassword: z.string().min(1, 'Confirm your password'),
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

export type SignupInput = z.infer<typeof signupSchema>

export const forgotPasswordSchema = z.object({
  email: z.string().email('Invalid email address'),
})

export type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>

export const resetPasswordSchema = z
  .object({
    password: strongPassword,
    confirmPassword: z.string().min(1, 'Confirm your password'),
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

export type ResetPasswordInput = z.infer<typeof resetPasswordSchema>
