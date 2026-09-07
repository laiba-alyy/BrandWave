/**
 * BrandWave mark — do lehrein, amber upar jade neeche.
 * Nav aur footer dono isay use karte hain taake mark ek jagah se aaye.
 */
export default function Logo({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2 15c3.2 0 3.2-6 6.4-6s3.2 6 6.4 6 3.2-6 6.4-6"
        stroke="#F0A63C"
        strokeWidth="2.1"
        strokeLinecap="round"
      />
      <path
        d="M2 19.5c3.2 0 3.2-4 6.4-4s3.2 4 6.4 4 3.2-4 6.4-4"
        stroke="#3ED9A4"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity=".7"
      />
    </svg>
  )
}
