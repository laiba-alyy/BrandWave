/*
 * Hero ke foran baad ek patli stats strip.
 *
 * Maqsad: page ko wazan dena. Hero se seedha feature grid par chale jana
 * page ko halka mehsoos karata hai; ek numbers ki qatar beech mein aa kar
 * "ye cheez waqai kuch karti hai" ka ehsas deti hai.
 *
 * YAHAN KOI GHARA HUA ADAD NAHI. Landing pages aksar "500+ brands trust us"
 * likh dete hain — hamare paas aise customers hain hi nahi, aur jhoota adad
 * likhna FYP demo mein pakra bhi ja sakta hai. Har number neeche wale code se
 * aata hai:
 *
 *   9 modules      -> app/business ke nau routes
 *   7,173 products -> Asim Jofa ka asal scrape (brand_profiles id=10)
 *   2 languages    -> chatbot/insights English + Roman Urdu
 *   10s            -> sab se chhoti video length (schemas.SUPPORTED_DURATIONS)
 */
const STATS = [
  { value: '9', label: 'modules, one brand profile' },
  { value: '7,173', label: 'products read in one scrape' },
  { value: '2', label: 'languages — English + Roman Urdu' },
  { value: '10s', label: 'video ad from one product photo' },
]

export default function Stats() {
  return (
    <section className="stats" aria-label="BrandWave at a glance">
      <div className="shell stats__in">
        {STATS.map((s) => (
          <div className="stats__cell" key={s.label}>
            <strong className="stats__v">{s.value}</strong>
            <span className="stats__l">{s.label}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
