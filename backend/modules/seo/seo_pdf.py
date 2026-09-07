import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from models.seo_result import SEOAuditResult, SEOBlogPost
from models.brand_profile import BrandProfile


# ─────────────────────────────────────────────
#  COLOR PALETTE
# ─────────────────────────────────────────────

COLOR_PRIMARY = colors.HexColor("#4F46E5")      # Indigo
COLOR_SUCCESS = colors.HexColor("#16A34A")      # Green
COLOR_WARNING = colors.HexColor("#D97706")      # Amber
COLOR_DANGER = colors.HexColor("#DC2626")       # Red
COLOR_LIGHT_GRAY = colors.HexColor("#F3F4F6")
COLOR_DARK = colors.HexColor("#111827")
COLOR_MID = colors.HexColor("#6B7280")


# ─────────────────────────────────────────────
#  SEVERITY COLOR MAPPING
# ─────────────────────────────────────────────

def _severity_color(severity: str):
    if severity == "Good":
        return COLOR_SUCCESS
    elif severity == "Warning":
        return COLOR_WARNING
    return COLOR_DANGER


# ─────────────────────────────────────────────
#  STYLES
# ─────────────────────────────────────────────

def _get_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="BrandTitle",
        fontSize=24,
        fontName="Helvetica-Bold",
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SubTitle",
        fontSize=12,
        fontName="Helvetica",
        textColor=COLOR_MID,
        alignment=TA_CENTER,
        spaceAfter=20,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeader",
        fontSize=14,
        fontName="Helvetica-Bold",
        textColor=COLOR_PRIMARY,
        spaceBefore=16,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="FactorHeader",
        fontSize=12,
        fontName="Helvetica-Bold",
        textColor=COLOR_DARK,
        spaceBefore=12,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BodyText2",
        fontSize=9,
        fontName="Helvetica",
        textColor=COLOR_DARK,
        spaceAfter=4,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name="SmallText",
        fontSize=8,
        fontName="Helvetica",
        textColor=COLOR_MID,
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="BlogTitle",
        fontSize=20,
        fontName="Helvetica-Bold",
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="BlogH2",
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=COLOR_DARK,
        spaceBefore=12,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BlogH3",
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=COLOR_MID,
        spaceBefore=8,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="BlogBody",
        fontSize=10,
        fontName="Helvetica",
        textColor=COLOR_DARK,
        spaceAfter=6,
        leading=16,
    ))

    return styles


# ─────────────────────────────────────────────
#  SEO AUDIT REPORT PDF
# ─────────────────────────────────────────────

def generate_audit_pdf(
    brand_profile: BrandProfile,
    audit_result: SEOAuditResult,
) -> bytes:
    """
    SEO audit report PDF generate karo.
    Returns PDF as bytes for FastAPI response.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = _get_styles()
    story = []

    # ── Header ──────────────────────────────
    story.append(Paragraph("BrandWave", styles["BrandTitle"]))
    story.append(Paragraph("SEO Audit Report", styles["SubTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 12))

    # Store info
    story.append(Paragraph(f"<b>Store:</b> {brand_profile.business_name}", styles["BodyText2"]))
    story.append(Paragraph(f"<b>Website:</b> {brand_profile.website_url}", styles["BodyText2"]))
    story.append(Paragraph(
        f"<b>Report Generated:</b> {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
        styles["BodyText2"]
    ))
    # Audit sample par chalta hai, poore catalogue par nahi — report mein bhi
    # yehi saaf likho warna reader samajhta hai ke score poore store ka hai.
    audited = audit_result.total_products_audited or 0
    catalogue = audit_result.total_catalogue_products
    if catalogue and catalogue > audited:
        pct = round(audited / catalogue * 100)
        audited_line = (
            f"<b>Products Audited:</b> {audited:,} of {catalogue:,} ({pct}% of catalogue)"
        )
    else:
        audited_line = f"<b>Products Audited:</b> {audited:,}"

    story.append(Paragraph(audited_line, styles["BodyText2"]))
    story.append(Spacer(1, 16))

    # ── Overall Score ────────────────────────
    story.append(Paragraph("Overall SEO Score", styles["SectionHeader"]))

    score = audit_result.seo_score or 0
    score_color = COLOR_SUCCESS if score >= 70 else (COLOR_WARNING if score >= 40 else COLOR_DANGER)

    score_data = [[
        Paragraph(f"<font color='#{score_color.hexval()[2:]}' size='28'><b>{score}/100</b></font>", styles["BodyText2"]),
        Paragraph(
            f"<b>Good:</b> {audit_result.good_count or 0} &nbsp;&nbsp; "
            f"<b>Warning:</b> {audit_result.warning_count or 0} &nbsp;&nbsp; "
            f"<b>Needs Work:</b> {audit_result.needs_work_count or 0}",
            styles["BodyText2"]
        ),
    ]]

    score_table = Table(score_data, colWidths=[4 * cm, 13 * cm])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_GRAY),
        ("ROWPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 16))

    # ── Factor Scores Summary ────────────────
    story.append(Paragraph("Factor Score Breakdown", styles["SectionHeader"]))

    factors = [
        ("Product Title Quality", audit_result.title_score or 0),
        ("Meta Description Quality", audit_result.description_score or 0),
        ("Image Alt Text", audit_result.image_alt_score or 0),
        ("Keyword Usage", audit_result.keyword_score or 0),
        ("Tag Completeness", audit_result.tags_score or 0),
    ]

    factor_data = [["Factor", "Score", "Status"]]
    for factor_name, factor_score in factors:
        status = "Good" if factor_score >= 70 else ("Warning" if factor_score >= 40 else "Needs Work")
        factor_data.append([
            factor_name,
            f"{factor_score}%",
            status,
        ])

    factor_table = Table(factor_data, colWidths=[9 * cm, 3 * cm, 5 * cm])
    factor_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_GRAY]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(factor_table)
    story.append(Spacer(1, 16))

    # ── Suggested Keywords ───────────────────
    if audit_result.suggested_keywords:
        story.append(Paragraph("Target Keywords Used", styles["SectionHeader"]))
        kw_text = " • ".join(audit_result.suggested_keywords[:10])
        story.append(Paragraph(kw_text, styles["BodyText2"]))
        story.append(Spacer(1, 12))

    # ── Detailed Issues ──────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Detailed Audit Issues", styles["SectionHeader"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LIGHT_GRAY))

    issue_sections = [
        ("Product Title Issues", audit_result.title_issues),
        ("Meta Description Issues", audit_result.description_issues),
        ("Image Alt Text Issues", audit_result.image_alt_issues),
        ("Keyword Usage Issues", audit_result.keyword_issues),
        ("Tag Completeness Issues", audit_result.tags_issues),
    ]

    for section_name, issues in issue_sections:
        if not issues:
            continue

        story.append(Paragraph(section_name, styles["FactorHeader"]))

        # Show max 15 issues per section to keep PDF readable
        display_issues = [i for i in issues if i.get("severity") != "Good"][:15]

        if not display_issues:
            story.append(Paragraph("✓ All products passed this check.", styles["SmallText"]))
            continue

        issue_data = [["Product", "Issue", "Severity"]]
        for issue in display_issues:
            issue_data.append([
                Paragraph(str(issue.get("product_name", ""))[:40], styles["SmallText"]),
                Paragraph(str(issue.get("issue", ""))[:80], styles["SmallText"]),
                str(issue.get("severity", "")),
            ])

        issue_table = Table(issue_data, colWidths=[5 * cm, 9 * cm, 3 * cm])
        issue_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_GRAY]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(issue_table)
        story.append(Spacer(1, 10))

    # ── AI Recommendations ───────────────────
    if audit_result.ai_recommendations:
        story.append(PageBreak())
        story.append(Paragraph("AI-Optimized Content Recommendations", styles["SectionHeader"]))
        story.append(Paragraph(
            "Below are AI-generated optimized titles and descriptions. "
            "Copy these directly into your Shopify product editor.",
            styles["BodyText2"]
        ))
        story.append(Spacer(1, 10))

        for rec in audit_result.ai_recommendations[:20]:
            story.append(Paragraph(
                f"<b>{rec.get('original_name', '')}</b>",
                styles["FactorHeader"]
            ))

            rec_data = [
                ["", "Original", "Optimized"],
                [
                    "Title",
                    Paragraph(str(rec.get("original_title", ""))[:80], styles["SmallText"]),
                    Paragraph(str(rec.get("optimized_title", ""))[:80], styles["SmallText"]),
                ],
                [
                    "Description",
                    Paragraph(str(rec.get("original_description", ""))[:200], styles["SmallText"]),
                    Paragraph(str(rec.get("optimized_description", ""))[:200], styles["SmallText"]),
                ],
            ]

            rec_table = Table(rec_data, colWidths=[2.5 * cm, 7.5 * cm, 7 * cm])
            rec_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_LIGHT_GRAY),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#F0FDF4")),
            ]))
            story.append(rec_table)
            story.append(Spacer(1, 8))

    # ── Footer ───────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LIGHT_GRAY))
    story.append(Paragraph(
        "Generated by BrandWave — AI-Powered Marketing Platform for Shopify Businesses",
        styles["SmallText"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ─────────────────────────────────────────────
#  BLOG POST PDF
# ─────────────────────────────────────────────

def generate_blog_pdf(
    brand_profile: BrandProfile,
    blog_post: SEOBlogPost,
) -> bytes:
    """
    Blog post PDF generate karo.
    Formatted with headings, meta info, and full content.
    Returns PDF as bytes for FastAPI response.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5 * cm,
        leftMargin=2.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = _get_styles()
    story = []

    # ── Header ──────────────────────────────
    story.append(Paragraph("BrandWave", styles["BrandTitle"]))
    story.append(Paragraph("SEO Blog Article", styles["SubTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 12))

    # ── Meta Info Box ────────────────────────
    meta_data = [
        ["Store", brand_profile.business_name or ""],
        ["Generated", datetime.now().strftime("%d %B %Y")],
        ["Word Count", str(blog_post.word_count or 0)],
        ["Keywords Used", str(blog_post.keyword_count or 0)],
    ]

    meta_table = Table(meta_data, colWidths=[4 * cm, 13 * cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), COLOR_LIGHT_GRAY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    # ── SEO Meta Section ─────────────────────
    story.append(Paragraph("SEO Meta Information", styles["SectionHeader"]))

    seo_data = [
        ["Meta Title", blog_post.meta_title or ""],
        ["Meta Description", blog_post.meta_description or ""],
        ["Target Keywords", ", ".join(blog_post.keywords_used or [])],
    ]

    seo_table = Table(seo_data, colWidths=[4 * cm, 13 * cm])
    seo_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#EEF2FF")),
    ]))
    story.append(seo_table)
    story.append(Spacer(1, 16))

    # ── Blog Content ─────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LIGHT_GRAY))
    story.append(Spacer(1, 8))
    story.append(Paragraph(blog_post.title or "", styles["BlogTitle"]))
    story.append(Spacer(1, 12))

    # Parse markdown-style headings and render as styled paragraphs
    content = blog_post.content or ""
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue

        if line.startswith("### "):
            story.append(Paragraph(line[4:], styles["BlogH3"]))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], styles["BlogH2"]))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], styles["BlogH2"]))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph(f"• {line[2:]}", styles["BlogBody"]))
        else:
            # Escape any XML special characters for ReportLab
            line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(line, styles["BlogBody"]))

    # ── Footer ───────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LIGHT_GRAY))
    story.append(Paragraph(
        "Generated by BrandWave — Paste this content directly into your Shopify Blog Editor",
        styles["SmallText"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()