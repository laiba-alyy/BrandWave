'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import type { User } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase'
import { navLinks } from './landingContent'
import Logo from './Logo'

export default function Navbar() {
  const router = useRouter()
  const supabase = createClient()
    const [user, setUser] = useState<User | null>(null)
  const [stuck, setStuck] = useState(false)

  useEffect(() => {
    const checkAuth = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      setUser(session?.user || null)
    }
    checkAuth()
  }, [supabase])

  // Nav sticky hai aur top par border nahi rakhta — scroll hote hi hairline
  // border aa jata hai, taake hero ka glow nav ke neeche se saaf kat jaye.
  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleLogout = async () => {
    await supabase.auth.signOut()
    setUser(null)
    router.push('/')
  }

  return (
    <nav className={`nav${stuck ? ' is-stuck' : ''}`}>
      <div className="shell nav__in">
        <Link className="brand" href="#top">
          <Logo />
          BrandWave
        </Link>

        <div className="nav__links">
          {navLinks.map((link) => (
            <a key={link.href} href={link.href}>
              {link.label}
            </a>
          ))}
        </div>

        {user ? (
          <>
            <Link className="btn btn--ghost nav__secondary" href="/business">
              Dashboard
            </Link>
            <button className="btn btn--primary nav__cta" onClick={handleLogout}>
              Log out
            </button>
          </>
        ) : (
          <>
            <Link className="btn btn--ghost nav__secondary" href="/login">
              Log in
            </Link>
            <Link className="btn btn--primary nav__cta" href="/signup">
              <span className="nav__cta-long">Scrape your store</span>
              <span className="nav__cta-short">Get started</span>
            </Link>
          </>
        )}
      </div>
    </nav>
  )
}
