import { footerLinks } from './landingContent'
import Logo from './Logo'

export default function Footer() {
  return (
    <footer className="foot">
      <div className="shell">
        <div className="foot__in">
          <a className="brand" href="#top">
            <Logo size={22} />
            BrandWave
          </a>
          <div className="foot__cols">
            {footerLinks.map((link) => (
              <a key={link.href} href={link.href}>
                {link.label}
              </a>
            ))}
          </div>
        </div>
        <p className="foot__note">
          © {new Date().getFullYear()} BrandWave. AI-powered marketing automation for
          Shopify businesses.
        </p>
      </div>
    </footer>
  )
}
