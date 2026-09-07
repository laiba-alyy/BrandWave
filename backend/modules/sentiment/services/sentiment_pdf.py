"""
Sentiment report -> PDF bytes. SAADA (plain) aur seedha.

Kyun server par, browser mein nahi:
    Pehle "Download report" ek popup kholta tha aur `window.print()` chalata
    tha. Wo DOWNLOAD nahi hai — wo print dialog hai: user ko khud "Save as
    PDF" chunna parta, popup blocker rok deta, aur natija har browser par
    alag aata. Ab backend asli PDF banata hai aur
    `Content-Disposition: attachment` ke saath bhejta hai.

Kyun itna saada:
    Pehli koshish mein rangeen tables aur 26pt ke bare numbers thay. Do
    masle hue:
      1. Bare numbers NAZAR HI NAHI AATE thay — style mein `fontSize=26`
         tha magar `leading` (line height) parent se 12 hi raha, is liye
         text 12pt ki line mein squeeze ho kar kat gaya. (Sabaq: reportlab
         mein font size barhao to leading BHI barhao.)
      2. Report parhne ke liye hai, dekhne ke liye nahi. Brand owner ko
         seedhe jumle chahiye, dashboard ki naqal nahi.

    Ab: kaala text, ek hi font, koi table nahi, koi rang nahi. Har cheez
    poore jumle ya saada list mein.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
)

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6B7280")
RULE = colors.HexColor("#D1D5DB")

_SOURCE_LABELS = {
    "trustpilot": "Trustpilot",
    "youtube": "YouTube (the brand's own channel)",
    "youtube_reviews": "YouTube reviewer videos",
}


def _styles():
    s = getSampleStyleSheet()
    # NOTE: har style par `leading` saaf likha hua hai. Pehle 26pt heading
    # 12pt leading par render ho kar ghayab ho gayi thi.
    s.add(ParagraphStyle("Title2", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=18, leading=23, textColor=INK, spaceAfter=2))
    s.add(ParagraphStyle("Meta", parent=s["Normal"], fontName="Helvetica",
                         fontSize=9.5, leading=14, textColor=MUTED, spaceAfter=14))
    s.add(ParagraphStyle("H2", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=12, leading=16, textColor=INK,
                         spaceBefore=16, spaceAfter=6))
    s.add(ParagraphStyle("Body", parent=s["Normal"], fontName="Helvetica",
                         fontSize=10.5, leading=16, textColor=INK, spaceAfter=4))
    s.add(ParagraphStyle("Item", parent=s["Normal"], fontName="Helvetica",
                         fontSize=10.5, leading=16, textColor=INK,
                         leftIndent=14, spaceAfter=3))
    s.add(ParagraphStyle("Foot", parent=s["Normal"], fontName="Helvetica",
                         fontSize=8.5, leading=12, textColor=MUTED))
    return s


def _text_of(item) -> str:
    """
    Insight items kabhi string hoti hain, kabhi {"text": ...} dict — dono
    shaklein DB mein mojood hain (Groq ke jawab ki shakl waqt ke saath badli).
    """
    if isinstance(item, dict):
        return str(item.get("text") or item.get("point") or item.get("value") or "").strip()
    return str(item or "").strip()


def _esc(text) -> str:
    """reportlab Paragraph mini-HTML parse karta hai — & < > escape zaroori."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _list_section(heading, items, st, empty_msg, limit=12):
    body = [Paragraph(heading, st["H2"])]
    written = 0
    for item in (items or []):
        text = _text_of(item)
        if not text:
            continue
        written += 1
        body.append(Paragraph(f"{written}.&nbsp;&nbsp;{_esc(text)}", st["Item"]))
        if written >= limit:
            break
    if not written:
        body.append(Paragraph(empty_msg, st["Body"]))
    return KeepTogether(body)


def generate_sentiment_pdf(analysis, brand_display_name: str) -> bytes:
    """
    Ek SentimentAnalysis row -> saada PDF bytes.

    Saara content `analysis_data` JSON se aata hai, is liye purani analyses
    bhi bilkul isi tarah export hoti hain.
    """
    data = analysis.analysis_data or {}
    summary = data.get("sentiment_summary") or {}
    platforms = data.get("platforms") or {}
    emotions = data.get("emotions") or {}
    total = summary.get("total_posts") or analysis.review_count or 0

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Sentiment Report - {brand_display_name}",
        author="BrandWave",
    )
    st = _styles()
    out = []

    # ── heading ─────────────────────────────────────────────────────────
    out.append(Paragraph("Customer Sentiment Report", st["Title2"]))
    when = analysis.analysis_date.strftime("%d %B %Y at %H:%M") if analysis.analysis_date else "unknown date"
    # Saada hyphen — &middot; kuchh PDF readers mein theek encode nahi hota.
    out.append(Paragraph(f"{_esc(brand_display_name)} &nbsp;&#8212;&nbsp; {when}", st["Meta"]))
    out.append(HRFlowable(width="100%", thickness=0.6, color=RULE,
                          spaceBefore=0, spaceAfter=14))

    # ── overall ─────────────────────────────────────────────────────────
    # Jaan boojh kar poore jumle mein — pehle ye teen bare rangeen numbers
    # thay jo layout mein kat gaye. Text kabhi nahi katta.
    out.append(Paragraph("Overall result", st["H2"]))
    out.append(Paragraph(
        f"We analysed <b>{total}</b> pieces of customer feedback for "
        f"{_esc(brand_display_name)}.",
        st["Body"],
    ))
    out.append(Paragraph(
        f"Positive: <b>{summary.get('positive_percent', 0)}%</b> "
        f"({summary.get('positive', 0)} items)",
        st["Item"],
    ))
    out.append(Paragraph(
        f"Neutral: <b>{summary.get('neutral_percent', 0)}%</b> "
        f"({summary.get('neutral', 0)} items)",
        st["Item"],
    ))
    out.append(Paragraph(
        f"Negative: <b>{summary.get('negative_percent', 0)}%</b> "
        f"({summary.get('negative', 0)} items)",
        st["Item"],
    ))

    # ── sources ─────────────────────────────────────────────────────────
    if platforms:
        out.append(Paragraph("Where this feedback came from", st["H2"]))
        for key, count in sorted(platforms.items(), key=lambda kv: -kv[1]):
            out.append(Paragraph(
                f"{_esc(_SOURCE_LABELS.get(key, key))}: <b>{count}</b>", st["Item"]
            ))
        if data.get("deep"):
            out.append(Paragraph(
                "This report includes comments from independent YouTube "
                "reviewers, not just the brand's own channel.", st["Body"]
            ))

    # ── emotions ────────────────────────────────────────────────────────
    live = {k: v for k, v in emotions.items() if v}
    if live:
        out.append(Paragraph("Emotional tone", st["H2"]))
        for name, count in sorted(live.items(), key=lambda kv: -kv[1]):
            share = f" ({round(count / total * 100)}%)" if total else ""
            out.append(Paragraph(
                f"{_esc(name.capitalize())}: <b>{count}</b>{share}", st["Item"]
            ))

    # ── qualitative ─────────────────────────────────────────────────────
    out.append(_list_section(
        "What customers complain about", data.get("pain_points"), st,
        "No clear complaints came through in this feedback."))
    out.append(_list_section(
        "What customers like", data.get("loved"), st,
        "No clear praise came through in this feedback."))
    out.append(_list_section(
        "What customers are asking for", data.get("desires"), st,
        "No specific requests came through in this feedback."))

    # ── keywords ────────────────────────────────────────────────────────
    keywords = data.get("keywords") or []
    if keywords:
        out.append(Paragraph("Most mentioned words", st["H2"]))
        words = []
        for k in keywords[:20]:
            if isinstance(k, dict):
                word, freq = k.get("keyword"), k.get("frequency")
                words.append(f"{_esc(word)} ({freq})" if freq else _esc(word))
            else:
                words.append(_esc(k))
        out.append(Paragraph(", ".join(words), st["Body"]))

    # ── footer ──────────────────────────────────────────────────────────
    out.append(Spacer(1, 18))
    out.append(HRFlowable(width="100%", thickness=0.6, color=RULE,
                          spaceBefore=0, spaceAfter=8))
    out.append(Paragraph(
        f"Generated by BrandWave on {datetime.utcnow().strftime('%d %B %Y')}. "
        f"Report ID {analysis.analysis_id}.",
        st["Foot"],
    ))

    doc.build(out)
    return buf.getvalue()
