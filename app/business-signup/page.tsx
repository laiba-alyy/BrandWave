import { redirect } from 'next/navigation'

/*
 * /business-signup ab /signup ka purana naam hai.
 *
 * Role selection (Business owner vs Administrator) hata di gayi hai, is liye
 * "business" prefix ka koi matlab nahi raha — har account brand owner hai.
 * Route sirf is liye zinda hai ke purane verification/bookmark links 404 na
 * dein.
 */
export default function BusinessSignupPage() {
  redirect('/signup')
}
