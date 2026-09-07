import Link from 'next/link'

export default function CTA() {
  return (
    <section className="final">
      <div className="shell final__in">
        <div className="eyebrow eyebrow--amber">Four minutes to your first finding</div>
        <h2>Connect the store. Read what it says.</h2>
        <p>
          You already have the reviews, the catalogue and the traffic. BrandWave is the
          part that reads all three at once.
        </p>
        <div className="hero__actions">
          <Link className="btn btn--primary btn--lg" href="/signup">
            Connect your store
          </Link>
          <a className="btn btn--ghost btn--lg" href="#features">
            Explore features
          </a>
        </div>
      </div>
    </section>
  )
}
