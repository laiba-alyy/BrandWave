import LegalPage from '@/components/legal/LegalPage'

export const metadata = {
  title: 'Terms of Service — BrandWave',
  description: 'The terms under which BrandWave is provided.',
}

const CONTACT = 'laibslb2004@gmail.com'

export default function Terms() {
  return (
    <LegalPage
      title="Terms of Service"
      updated="5 September 2026"
      lede="These terms cover your use of BrandWave. By creating an account you agree to them."
    >
      <h2>1. The service</h2>
      <p>
        BrandWave provides AI-assisted marketing tools for online stores: catalogue scraping,
        customer sentiment analysis, SEO tooling, advertisement generation and an embeddable
        support chatbot.
      </p>

      <h2>2. Your account</h2>
      <ul>
        <li>Provide accurate information when registering</li>
        <li>Keep your password confidential — you are responsible for activity under your account</li>
        <li>One person or business per account; do not share credentials</li>
        <li>Tell us promptly if you suspect unauthorised access</li>
      </ul>

      <h2>3. Acceptable use</h2>
      <p>You agree not to:</p>
      <ul>
        <li>Scrape stores you do not own or lack permission to analyse</li>
        <li>Generate content that is unlawful, deceptive, defamatory or infringing</li>
        <li>Misrepresent AI-generated advertisements as photography of real products where that would mislead buyers</li>
        <li>Attempt to breach, overload or reverse-engineer the service</li>
        <li>Use the service to send spam or unsolicited messages</li>
        <li>Upload malware, or personal data you have no right to process</li>
      </ul>

      <h2>4. Your content</h2>
      <p>
        You keep ownership of everything you upload and of your store data. You grant us only
        the permission needed to operate the service — to store your content, and to transmit
        it to the AI providers described in our <a href="/privacy">Privacy Policy</a> so that
        generation can happen.
      </p>
      <p>
        You are responsible for having the right to use the product images, descriptions and
        documents you submit.
      </p>

      <h2>5. AI-generated output</h2>
      <p>
        Advertisements, copy, SEO recommendations and chatbot replies are produced by AI models
        and <strong>may be inaccurate, generic or unsuitable</strong>. Review everything before
        publishing it.
      </p>
      <ul>
        <li>We make no claim that generated output is original or free of third-party rights</li>
        <li>You are responsible for complying with the advertising and AI-disclosure rules that apply to you</li>
        <li>Output is also governed by the terms of the provider that generated it</li>
      </ul>

      <h2>6. Third-party services</h2>
      <p>
        BrandWave depends on external providers for authentication, hosting, database and AI
        generation. Outages, rate limits or policy changes at those providers can interrupt or
        degrade features, and that is outside our control.
      </p>

      <h2>7. Availability</h2>
      <p>
        The service is provided <strong>as is</strong>, with no guarantee of availability. We
        may change, suspend or discontinue any feature at any time, with or without notice.
      </p>

      <h2>8. Liability</h2>
      <p>
        To the maximum extent permitted by law, we are not liable for any indirect or
        consequential loss, lost profits, lost data, or losses arising from your use of
        generated content. Nothing here excludes liability that cannot lawfully be excluded.
      </p>

      <h2>9. Termination</h2>
      <p>
        You may delete your account at any time from profile settings. We may suspend accounts
        that breach these terms. On termination your data is removed as described in the{' '}
        <a href="/privacy">Privacy Policy</a>.
      </p>

      <h2>10. Changes</h2>
      <p>
        We may update these terms; the date at the top will change. Continuing to use the
        service after an update means you accept it.
      </p>

      <h2>11. Contact</h2>
      <p>
        Questions about these terms: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
      </p>
    </LegalPage>
  )
}
