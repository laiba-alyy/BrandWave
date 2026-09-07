/* ============================================================================
 * Landing page content
 * ----------------------------------------------------------------------------
 * Design brandwave.html se port hua hai — structure aur interactions waise hi
 * hain. Lekin us prototype ke saare numbers ek FARZI example store ("Noorah
 * Studio") ke thay. Wo figures yahan se hata diye gaye hain taake landing page
 * par koi banaya hua data live na jaye.
 *
 * ── Isay live karne ke liye ───────────────────────────────────────────────────
 *  1. `SHOW_SAMPLE_DATA` ko `true` karein  → prototype ke sample numbers wapas
 *     dikhne lagenge (design kaisa lagta hai ye dekhne ke liye).
 *  2. Ya behtar: neeche `sampleX` objects mein apne ASLI numbers daal dein aur
 *     phir flag `true` karein.
 *
 * Jab tak flag `false` hai, har figure "—" render hota hai aur har list apna
 * empty state dikhati hai. Copy (headings, prose, FAQ) hamesha render hoti hai
 * — sirf numbers gate hue hain.
 *
 * TODO(brandwave): asli data wire karne ke baad SHOW_SAMPLE_DATA hata dein.
 * ========================================================================== */

export const SHOW_SAMPLE_DATA = false

const PLACEHOLDER = '—'

/** Ek figure — flag off ho to dash. */
export function figure(value: string): string {
  return SHOW_SAMPLE_DATA ? value : PLACEHOLDER
}

/** Ek list — flag off ho to khali, taake component empty state dikhaye. */
export function rows<T>(value: T[]): T[] {
  return SHOW_SAMPLE_DATA ? value : []
}

/** Bar/meter widths — flag off ho to 0, yani track khali dikhta hai. */
export function pct(value: number): number {
  return SHOW_SAMPLE_DATA ? value : 0
}

// ─────────────────────────────────────────────────────────────────────────────
// Nav + footer
// ─────────────────────────────────────────────────────────────────────────────

export const navLinks = [
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how' },
  { label: 'Pricing', href: '#pricing' },
  { label: 'FAQ', href: '#faq' },
]

export const footerLinks = [
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how' },
  { label: 'Pricing', href: '#pricing' },
  { label: 'FAQ', href: '#faq' },
  // Google OAuth consent screen ke liye privacy policy ka public link laazmi
  // hai, aur wo site se discoverable bhi hona chahiye — sirf mojood hona
  // kaafi nahi.
  { label: 'Privacy', href: '/privacy' },
  { label: 'Terms', href: '/terms' },
]

// ─────────────────────────────────────────────────────────────────────────────
// Hero — example connected store panel
// ─────────────────────────────────────────────────────────────────────────────

export const heroMeta = [
  'Works with any Shopify store',
  'No code, no theme edits',
  'English & Roman Urdu',
]

export const demoStore = {
  name: SHOW_SAMPLE_DATA ? 'Noorah Studio' : 'Your store',
  url: SHOW_SAMPLE_DATA ? 'noorahstudio.pk' : 'yourstore.com',
  initial: SHOW_SAMPLE_DATA ? 'N' : 'B',
  status: SHOW_SAMPLE_DATA ? 'Synced' : 'Not connected',
  synced: SHOW_SAMPLE_DATA,
  stats: [
    { value: figure('7,157'), label: 'products scraped' },
    { value: figure('214'), label: 'collections mapped' },
    { value: figure('3,482'), label: 'reviews read' },
    { value: figure('PKR'), label: 'currency auto-detected' },
  ],
  sentiment: {
    positivePct: pct(78),
    neutralPct: pct(13),
    negativePct: pct(9),
    positiveLabel: figure('78%'),
    neutralLabel: figure('13%'),
    negativeLabel: figure('9%'),
    caption: 'positive sentiment, last 90 days',
  },
  ticker: SHOW_SAMPLE_DATA
    ? 'Newest insight — delivery delays now drive 31% of negative reviews on your best-selling lawn SKU.'
    : 'Connect a store to see your newest insight here.',
}

// ─────────────────────────────────────────────────────────────────────────────
// Band — core product features
// ─────────────────────────────────────────────────────────────────────────────

/*
 * Har feature ke saath uski apni clip hai (public/Features/).
 *
 * Do tabdeeliyan is list me:
 *   1. "Dashboard overview" hata diya gaya -- har SaaS platform ka dashboard
 *      hota hai, wo koi farq nahi batata. Uski koi clip bhi nahi thi.
 *   2. "Image + video ads" do alag cards ban gaye, kyunke dono ki apni clip
 *      hai aur dono alag module hain.
 *
 * NOTE: file paths CASE-SENSITIVE hain. Folder "Features" bara F se hai aur
 * video_Ad.mp4 me bara A -- Windows par farq nahi parta magar Linux (AWS) par
 * ghalat case 404 deta hai.
 */
export interface BandFeature {
  title: string
  description: string
  icon: string
}

export const bandFeatures: BandFeature[] = [
  { title: 'Paste URL, start scraping', description: 'Connect your store by pasting only its URL.', icon: 'link' },
  { title: 'SEO intelligence', description: 'Find the keywords and page improvements that drive discovery.', icon: 'search' },
  { title: 'Sentiment analysis', description: 'See what customers love, question, and want fixed.', icon: 'pulse' },
  { title: 'Chatbot automation', description: 'Answer store questions with a chatbot trained on your data.', icon: 'chat' },
  { title: 'Image ads', description: 'Put your real product into a new scene, without redrawing it.', icon: 'spark' },
  { title: 'Video ads', description: 'Turn one product photo into a short, on-brand video ad.', icon: 'play' },
]

// ─────────────────────────────────────────────────────────────────────────────
// Module explorer — rail entries (real modules) + per-panel sample figures
// ─────────────────────────────────────────────────────────────────────────────

export interface ModuleEntry {
  n: string
  title: string
  desc: string
  crumb: string
}

export const modules: ModuleEntry[] = [
  { n: '01', title: 'Brand Setup', desc: 'Scrape catalogue, pricing and brand voice', crumb: 'setup' },
  { n: '02', title: 'Sentiment Analysis', desc: 'What customers feel, and why', crumb: 'sentiment' },
  { n: '03', title: 'SEO Intelligence', desc: 'Keywords, audit, rewritten titles', crumb: 'seo' },
  { n: '04', title: 'Brand Insights', desc: 'Problems and openings, with evidence', crumb: 'insights' },
  { n: '05', title: 'Image Ads', desc: 'Your real product, a new scene', crumb: 'image-ads' },
  { n: '06', title: 'Video Ads', desc: 'Eight seconds from one photo', crumb: 'video-ads' },
  { n: '07', title: 'Support Chatbot', desc: 'Trained on your store, live on your site', crumb: 'chatbot' },
  { n: '08', title: 'AI Assistant', desc: 'Knows your numbers, sits in every screen', crumb: 'assistant' },
  { n: '09', title: 'Dashboard', desc: 'Every module, one screen, every morning', crumb: 'dashboard' },
]

/** 01 — Brand Setup */
export const sampleSetup = {
  chip: SHOW_SAMPLE_DATA ? 'Sync complete · 4m 12s' : 'Awaiting first sync',
  catalogue: SHOW_SAMPLE_DATA
    ? '7,157 products across 214 collections, with variants, stock state and price history.'
    : 'Products across collections, with variants, stock state and price history.',
  market: SHOW_SAMPLE_DATA
    ? 'PKR pricing and a .pk domain → Pakistan. Every prompt downstream is written for that market.'
    : 'Your currency and domain decide the market. Every prompt downstream is written for it.',
  voice: 'Tone, recurring phrases and category vocabulary lifted from your own product copy.',
  priceBands: rows([
    { label: 'Unstitched lawn', value: 'PKR 3,450–7,900' },
    { label: 'Stitched kurta', value: 'PKR 4,200–11,500' },
    { label: 'Formals', value: 'PKR 18,000–64,000' },
    { label: 'Accessories', value: 'PKR 900–3,200' },
  ]),
}

/** 02 — Sentiment Analysis */
export const sampleSentiment = {
  chip: SHOW_SAMPLE_DATA ? '3,482 reviews · 90 days' : 'No reviews read yet',
  headlinePct: figure('78%'),
  headlineNote: SHOW_SAMPLE_DATA ? 'positive · up 6 pts since May' : 'positive',
  positivePct: pct(78),
  neutralPct: pct(13),
  negativePct: pct(9),
  legend: [
    { n: figure('2,716'), l: 'positive' },
    { n: figure('453'), l: 'neutral' },
    { n: figure('313'), l: 'negative' },
  ],
  emotions: rows([
    { label: 'Delight', value: '41%' },
    { label: 'Trust', value: '22%' },
    { label: 'Frustration', value: '15%' },
    { label: 'Regret', value: '7%' },
  ]),
  painPoints: rows([
    { num: '31%', text: 'Dispatch later than the promised window', who: 'Trustpilot' },
    { num: '18%', text: 'Colour on delivery differs from the listing photo', who: 'YouTube' },
    { num: '12%', text: "Size chart doesn't match stitched pieces", who: 'Reddit' },
    { num: '9%', text: 'Exchange takes more than two weeks', who: 'Trustpilot' },
  ]),
  loved: rows([
    { label: 'Fabric weight', value: '+612 mentions' },
    { label: 'Chikankari detailing', value: '+430' },
    { label: 'Packaging', value: '+287' },
    { label: 'Colour range', value: '+241' },
    { label: 'Price for quality', value: '+198' },
  ]),
}

/** 03 — SEO Intelligence */
export const sampleSeo = {
  chip: SHOW_SAMPLE_DATA ? 'Audit score 61 / 100' : 'No audit run yet',
  keywords: rows([
    { kw: 'unstitched lawn suit online pakistan', intent: 'Transactional', difficulty: 38, volume: '14,800' },
    { kw: 'chikankari kurta for eid', intent: 'Seasonal', difficulty: 26, volume: '9,300' },
    { kw: '3 piece lawn suit price in pakistan', intent: 'Comparison', difficulty: 54, volume: '6,100' },
    { kw: 'summer collection 2026 pakistani brands', intent: 'Discovery', difficulty: 71, volume: '4,450' },
  ]),
  rewrite: SHOW_SAMPLE_DATA
    ? {
        oldLabel: 'Current title · 22 characters',
        oldTitle: 'Lawn Suit — SKU 4471',
        newLabel: 'Rewritten · 68 characters · keyword covered',
        newTitle: 'Chikankari Unstitched Lawn 3-Piece — Summer 2026 | Noorah Studio',
      }
    : null,
}

/** 04 — Brand Insights */
export const sampleInsights = {
  chip: SHOW_SAMPLE_DATA ? '6 findings · every one sourced' : 'No findings yet',
  fixFirst: SHOW_SAMPLE_DATA
    ? {
        body: 'Your best-selling SKU carries 4× the review volume of anything else — and 31% of those reviews mention late dispatch. Paid traffic to this product is amplifying a delivery problem.',
        tags: ['412 reviews', 'Trustpilot + YouTube', 'Last 90 days'],
      }
    : null,
  opening: SHOW_SAMPLE_DATA
    ? {
        body: '"Chikankari" appears in 430 positive reviews but in only 11 of your 7,157 product titles. The word your customers use to praise you is missing from the pages they\'d find you on.',
        tags: ['430 mentions', '11 / 7,157 titles', '9,300 searches/mo'],
      }
    : null,
  alsoFlagged: rows([
    { num: 'P2', text: 'Size chart conflicts between stitched and unstitched pages', who: '12% of negatives' },
    { num: 'P2', text: 'Formals priced above PKR 40,000 have no lifestyle photography', who: '64 products' },
    { num: 'P3', text: 'No collection page for Eid despite a seasonal search spike', who: '9,300 searches/mo' },
  ]),
}

/** 05 — Image Ads */
export const sampleImageAds = {
  headline: SHOW_SAMPLE_DATA ? ['Hand-worked.', 'Not mass-made.'] : ['Your headline,', 'from your reviews.'],
  sub: SHOW_SAMPLE_DATA ? 'Chikankari · Eid 2026' : 'Product · Season',
  brief:
    'Scene, light and copy are drawn from what reviewers actually praise — not from a generic ad template.',
  formats: ['4:5 feed', '9:16 story', '1:1 catalogue'],
}

/** 06 — Video Ads */
export const sampleVideoAds = {
  chip: '8s · 1080×1350 · ready in ~90s',
  frames: [
    { t: '00:00 · hold', inset: '24% 28%' },
    { t: '00:02 · push in', inset: '20% 24%' },
    { t: '00:05 · fabric', inset: '28% 32%' },
    { t: '00:07 · logo', inset: '22% 20%' },
  ],
  notes: [
    { k: 'Aspect', v: 'Reels, TikTok and feed exported together.' },
    { k: 'Caption', v: "Written in your market's language, English or Roman Urdu." },
    { k: 'Cost control', v: 'Preview frames first, render only the cut you keep.' },
  ],
}

/** 07 — Support Chatbot */
export const sampleChatbot = {
  chip: SHOW_SAMPLE_DATA ? 'Live on noorahstudio.pk' : 'Not deployed yet',
  thread: rows([
    { from: 'them' as const, text: 'Do you have the chikankari kurta in size M, and when would it reach Lahore?' },
    {
      from: 'us' as const,
      text: 'Yes — the Chikankari Unstitched Lawn 3-Piece is in stock in M at PKR 6,450. Lahore orders placed before 4pm ship the same day and usually arrive in 2–3 working days.',
    },
    { from: 'them' as const, text: 'I paid two days ago and nothing has shipped.' },
    { from: 'sys' as const, text: 'Escalated to a human · order issue' },
  ]),
  why: "Every reply is retrieved from your indexed store data. When there's no grounded answer — an order dispute, a refund, anything about a specific customer's money — it stops and passes the thread to your team instead of improvising.",
  tags: ['One script tag to install', 'Reindexes on catalogue change', 'Full transcript log'],
}

/** 08 — AI Assistant */
export const sampleAssistant = {
  thread: rows([
    { from: 'us' as const, text: 'Which products should I not run ads on this month?' },
    {
      from: 'them' as const,
      text: 'Three. SKU 4471 and 4488 both sit above 25% delivery complaints, and the PKR 52,000 formal has no lifestyle imagery, so cost per click has run 3× your catalogue average. Want the list exported?',
    },
    { from: 'us' as const, text: 'Roman Urdu mein samjhao' },
  ]),
  canAlsoDo: [
    'Rewrite a product title against a chosen keyword',
    "Compare this month's sentiment to last quarter",
    'Switch you to another connected brand mid-question',
    'Queue an ad set for the products you just filtered',
  ],
}

/** 09 — Dashboard */
export const sampleDashboard = {
  tiles: rows([
    {
      k: 'Sentiment',
      v: '78%',
      d: '▲ 6 pts vs May',
      tone: 'up' as const,
      spark: { color: '#3ED9A4', fill: 'rgba(62,217,164,.14)', d: 'M0 20 L20 18 L40 19 L60 13 L80 12 L100 8 L120 6', cy: 6 },
    },
    {
      k: 'SEO score',
      v: '61',
      d: '▲ 9 after 240 rewrites',
      tone: 'up' as const,
      spark: { color: '#F0A63C', fill: 'rgba(240,166,60,.14)', d: 'M0 22 L24 21 L48 19 L72 16 L96 12 L120 10', cy: 10 },
    },
    {
      k: 'Delivery complaints',
      v: '31%',
      d: '▲ 11 pts — needs you',
      tone: 'down' as const,
      spark: { color: '#F0728A', fill: 'rgba(240,114,138,.13)', d: 'M0 18 L24 19 L48 15 L72 13 L96 9 L120 5', cy: 5 },
    },
    { k: 'Products indexed', v: '7,157', d: 'Last sync 4h ago', tone: 'muted' as const, spark: null },
    { k: 'Ads generated', v: '46', d: '38 images · 8 videos', tone: 'muted' as const, spark: null },
    { k: 'Chats handled', v: '1,204', d: '92% without a handover', tone: 'up' as const, spark: null },
  ]),
}

// ─────────────────────────────────────────────────────────────────────────────
// How it works
// ─────────────────────────────────────────────────────────────────────────────

export const steps = [
  {
    n: '01 CONNECT',
    title: 'Paste your store URL',
    body: 'Paste your store URL and BrandWave scans your catalogue, pricing, and brand voice automatically.',
  },
  {
    n: '02 UNDERSTAND',
    title: 'Everything runs at once',
    body: 'Your reviews, keywords, and product pages are analyzed together to reveal what matters most.',
  },
  {
    n: '03 ACT',
    title: 'Ship the same afternoon',
    body: 'Turn your insights into SEO updates, chatbot answers, and ready-to-publish ads.',
  },
]

// ─────────────────────────────────────────────────────────────────────────────
// Insight language toggle — illustrative finding
// ─────────────────────────────────────────────────────────────────────────────

export const sampleInsight = {
  priority: 'Priority 1',
  ref: SHOW_SAMPLE_DATA ? 'insight #0412 · generated 06:10 PKT' : 'a finding from your own store',
  en: SHOW_SAMPLE_DATA
    ? {
        title: 'You are paying to send traffic to a delivery problem.',
        body: 'Your Chikankari Unstitched Lawn 3-Piece collects four times more reviews than any other product — and 31% of them mention dispatch running past the promised window. Fix the dispatch window on this SKU before you spend another rupee advertising it, because right now every new buyer is a new complaint.',
      }
    : {
        title: 'Your finding, written in plain English.',
      body: 'Connect your store and BrandWave turns the data into one clear problem, backed by evidence and ready for action.',
      },
  ur: SHOW_SAMPLE_DATA
    ? {
        title: 'Aap paisay laga kar traffic aik delivery problem par bhej rahe hain.',
        body: 'Aapki Chikankari Unstitched Lawn 3-Piece par baaki har product se chaar guna zyada reviews aate hain — lekin in mein se 31% kehte hain ke dispatch waqt par nahi hota. Is SKU par aur ads chalane se pehle dispatch window theek karein, warna har naya customer aik nayi shikayat ban raha hai.',
      }
    : {
        title: 'Wohi finding, Roman Urdu mein.',
      body: 'Store connect karein aur BrandWave data ko aik saaf maslay mein badal deta hai, evidence ke saath aur foran action ke liye tayyar.',
      },
  evidence: rows(['412 reviews', 'Trustpilot + YouTube', 'Last 90 days', 'SKU 4471', 'Confidence high']),
}

// ─────────────────────────────────────────────────────────────────────────────
// Pricing
// ─────────────────────────────────────────────────────────────────────────────

export interface Plan {
  name: string
  hero?: boolean
  badge?: string
  price: { pkr: string; usd: string }
  for: string
  features: string[]
  cta: { label: string; href: string; variant: 'primary' | 'ghost' }
}

export const plans: Plan[] = [
  {
    name: 'Starter',
    price: { pkr: 'PKR 4,900', usd: '$19' },
    for: 'One store, first look at your own data.',
    features: [
      '1 connected store, up to 1,000 products',
      'Sentiment analysis and SEO audit',
      '10 ad images per month',
      'Weekly insight digest',
    ],
    cta: { label: 'Start with one store', href: '/signup', variant: 'ghost' },
  },
  {
    name: 'Growth',
    hero: true,
    badge: 'Most brands',
    price: { pkr: 'PKR 12,900', usd: '$49' },
    for: 'All nine modules, no catalogue limit.',
    features: [
      '3 connected stores, unlimited products',
      'Brand insights in English and Roman Urdu',
      '60 ad images and 10 video ads per month',
      'Support chatbot on your site',
      'AI assistant across every screen',
    ],
    cta: { label: 'Connect your store', href: '/signup', variant: 'primary' },
  },
  {
    name: 'Studio',
    price: { pkr: 'PKR 29,900', usd: '$115' },
    for: 'Several brands under one roof.',
    features: [
      '10 connected stores with a brand switcher',
      'Team seats and shared insight boards',
      'Unlimited chatbot pages',
      'Priority generation queue',
    ],
    cta: { label: 'Talk to us', href: '/signup', variant: 'ghost' },
  },
]

export const pricingNote =
  'USD prices are converted for reference. Billing happens in the currency your store sells in.'

// ─────────────────────────────────────────────────────────────────────────────
// FAQ
// ─────────────────────────────────────────────────────────────────────────────

export const faqs = [
  {
    q: 'Do I have to change anything on my Shopify theme?',
    a: 'No. The scrape reads your public store, and the support chatbot installs with a single script tag. Nothing else touches your theme files.',
  },
  {
    q: 'How big a catalogue can it handle?',
    a: 'There is no page cap — BrandWave paginates until your catalogue runs out. Large stores sync in a few minutes.',
  },
  {
    q: 'Where do the reviews come from?',
    a: "Trustpilot, YouTube comments and Reddit threads about your brand, deduplicated so one customer complaining in three places doesn't count as three problems.",
  },
  {
    q: 'Will the generated ad still show my real product?',
    a: 'Yes. The product from your catalogue photo is preserved; only the scene, lighting and copy around it are generated. Nothing about the garment itself is invented.',
  },
  {
    q: "What happens when the chatbot doesn't know something?",
    a: 'It stops and hands the conversation to your team. Anything touching a specific order, refund or payment escalates by default rather than being answered from a guess.',
  },
  {
    q: 'Does it work for stores outside Pakistan?',
    a: 'Yes. Currency and domain decide the market, and every prompt downstream is written for it — Pakistan is just where the sharpest examples come from.',
  },
]
