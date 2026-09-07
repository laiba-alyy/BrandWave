"""
Account deletion — ek user ka SAARA data teeno jagah se hatata hai:
Neon (Postgres), Pinecone (vectors), aur Supabase (users row + auth record).

── Ye module kyun bana ──────────────────────────────────────────────────────
Pehle "Delete Account" sirf frontend server action tha jo:
  1. Supabase ki `users` row delete karta tha,
  2. `auth.admin.deleteUser()` call karta tha ANON key ke saath — jo kabhi
     chal hi nahi sakta (admin API ko service_role chahiye), aur us error ko
     sirf warning samajh kar `success: true` return kar deta tha,
  3. Neon aur Pinecone ko chhoota tak nahi tha.

Nateeja: user ko "deleted" dikhta tha, magar auth record zinda rehta tha aur
uska poora business data (brands, SEO, ads, chatbot vectors) DB mein pada
rehta tha.

── Design ka usool ──────────────────────────────────────────────────────────
Delete order FOREIGN-KEY-safe hai: pehle bachche (messages), phir walidain
(conversations, bots), aakhir mein brand profiles. Har step ki count return
hoti hai taake caller (endpoint ya cleanup script) exactly bata sake kya gaya.

`dry_run=True` par kuch delete NAHI hota — sirf wahi counts aati hain jo
delete hotin. Cleanup script isi par chalti hai jab tak user confirm na kare.
"""

import os

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ye tables user_id par seedha scope hoti hain. Tarteeb ahem hai — dekho
# delete_user_data() ka docstring.
#
# ── TODO: sentiment tables cascade mein NAHI hain ────────────────────────────
# Sentiment module ki teen tables abhi is cascade se BAHAR hain:
#
#     brands              9 rows   (brand_id uuid, brand_name, website_url, ...)
#     sentiment_analyses 84 rows   (analysis_id uuid, brand_id -> brands)
#     review_posts        0 rows   (post_id uuid, analysis_id -> sentiment_analyses)
#
# Wajah: in mein `user_id` column hai hi nahi. `brands` website_url par keyed
# ek GLOBAL registry hai — do users agar ek hi store (maslan alkaramstudio.com)
# analyse karein to dono ko WAHI ek brand row milti hai. Us row ko ek user ke
# delete par hatane se doosre user ka sentiment data toot jata.
#
# Ise theek karne ke liye ownership chahiye. Do rastay hain:
#   (a) `brands` mein `user_id` add karo aur per-user rows rakho — sab se saaf,
#       magar mojooda 9 rows ko backfill karna parega (kis user ke hain, ye
#       website_url ko brand_profiles se match kar ke hi pata chalega).
#   (b) ek `brand_subscribers` join table (brand_id, user_id) banao aur brand
#       row tab delete karo jab uska AAKHRI subscriber ja chuke — shared
#       registry ka model bacha rehta hai.
#
# Jab tak in mein se ek na ho, sentiment data user delete par jaan boojh kar
# chhora jata hai. Ise chup-chaap delete karna data loss hai, orphan cleanup nahi.
_USER_SCOPED_TABLES = [
    "seo_blog_posts",
    "seo_keyword_suggestions",
    "seo_audit_results",
    "generated_ads",
    "assistant_chat_messages",
    "assistant_chat_sessions",
    "brand_profiles",
]


def _count(db: Session, sql: str, params: dict) -> int:
    return db.execute(text(sql), params).scalar() or 0


def _delete_pinecone_namespace(bot_id: str) -> str:
    """
    Ek bot ki poori Pinecone namespace hatata hai.

    Pinecone us namespace par 404 deta hai jo mojood hi nahi (jaise wo bot
    jis par kabhi document upload hi nahi hua). Wo error nahi hai — is liye
    use "absent" gin kar aage barhte hain, warna ek aisa bot poori deletion
    rok deta.
    """
    try:
        from modules.chatbot_automation.pinecone_service import delete_bot_data

        delete_bot_data(bot_id)
        return "deleted"
    except Exception as e:
        message = str(e).lower()
        if "404" in message or "not found" in message or "namespace" in message:
            return "absent"
        # Asli failure — caller ko pata chalna chahiye, magar baaki cleanup
        # rukni nahi chahiye warna data aur adhoora reh jayega.
        print(f"[account_deletion] Pinecone namespace {bot_id} failed: {e}")
        return f"error: {e}"


def delete_user_data(user_id: str, db: Session, dry_run: bool = False) -> dict:
    """
    User ka saara Neon + Pinecone data hatata hai.

    Order (foreign keys ke hisaab se — bachche pehle):
      1. chatbot_messages          (user ke bots ki conversations ke)
      2. chatbot_conversations     (user ke bots ki)
      3. Pinecone namespaces       (har bot_id ki)
      4. chatbot_uploaded_documents(user ke bots ke)
      5. chatbot_instances
      6. seo_blog_posts
      7. seo_keyword_suggestions
      8. seo_audit_results
      9. generated_ads
     10. assistant_chat_messages / assistant_chat_sessions
     11. brand_profiles            (sabse aakhir — baaki sab isi ko refer karta hai)

    Supabase (users row + auth record) YAHAN nahi hota — wo delete_supabase_user()
    mein alag hai, taake DB cleanup fail ho to auth record zinda rahe aur user
    dobara koshish kar sake (warna wo apne data tak pahunch hi na sake).

    Returns: har step ki counts ka dict.
    """
    report: dict = {"user_id": user_id, "dry_run": dry_run}

    # Pehle user ke saare bot_ids — inhi par chatbot ki har cheez hangs karti hai
    bot_ids = [
        r[0]
        for r in db.execute(
            text("SELECT bot_id FROM chatbot_instances WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchall()
    ]
    report["bot_ids"] = bot_ids

    # ── 1. chatbot_messages ──────────────────────────────────────────────
    # Messages conversation_id par hang karte hain, aur conversations bot_id par.
    # Is liye user ke bots se ho kar jana parta hai — messages mein user_id nahi hota.
    msg_sql_where = """
        conversation_id IN (
            SELECT id FROM chatbot_conversations
            WHERE bot_id IN (SELECT bot_id FROM chatbot_instances WHERE user_id = :uid)
        )
    """
    report["chatbot_messages"] = _count(
        db, f"SELECT count(*) FROM chatbot_messages WHERE {msg_sql_where}", {"uid": user_id}
    )
    if not dry_run and report["chatbot_messages"]:
        db.execute(text(f"DELETE FROM chatbot_messages WHERE {msg_sql_where}"), {"uid": user_id})

    # ── 2. chatbot_conversations ─────────────────────────────────────────
    conv_where = "bot_id IN (SELECT bot_id FROM chatbot_instances WHERE user_id = :uid)"
    report["chatbot_conversations"] = _count(
        db, f"SELECT count(*) FROM chatbot_conversations WHERE {conv_where}", {"uid": user_id}
    )
    if not dry_run and report["chatbot_conversations"]:
        db.execute(text(f"DELETE FROM chatbot_conversations WHERE {conv_where}"), {"uid": user_id})

    # ── 3. Pinecone namespaces ───────────────────────────────────────────
    # DB rows se PEHLE, warna bot_ids kho jayenge aur namespaces hamesha ke
    # liye orphan ho jayengi (Pinecone ko koi FK nahi pata).
    namespaces: dict = {}
    for bot_id in bot_ids:
        namespaces[bot_id] = "would delete" if dry_run else _delete_pinecone_namespace(bot_id)
    report["pinecone_namespaces"] = namespaces

    # ── 4. chatbot_uploaded_documents ────────────────────────────────────
    doc_where = "bot_id IN (SELECT bot_id FROM chatbot_instances WHERE user_id = :uid)"
    report["chatbot_uploaded_documents"] = _count(
        db, f"SELECT count(*) FROM chatbot_uploaded_documents WHERE {doc_where}", {"uid": user_id}
    )
    if not dry_run and report["chatbot_uploaded_documents"]:
        db.execute(
            text(f"DELETE FROM chatbot_uploaded_documents WHERE {doc_where}"), {"uid": user_id}
        )

    # ── 5. chatbot_instances ─────────────────────────────────────────────
    report["chatbot_instances"] = _count(
        db, "SELECT count(*) FROM chatbot_instances WHERE user_id = :uid", {"uid": user_id}
    )
    if not dry_run and report["chatbot_instances"]:
        db.execute(text("DELETE FROM chatbot_instances WHERE user_id = :uid"), {"uid": user_id})

    # ── 6-11. baaki har user-scoped table ────────────────────────────────
    for table in _USER_SCOPED_TABLES:
        report[table] = _count(
            db, f'SELECT count(*) FROM "{table}" WHERE user_id = :uid', {"uid": user_id}
        )
        if not dry_run and report[table]:
            db.execute(text(f'DELETE FROM "{table}" WHERE user_id = :uid'), {"uid": user_id})

    if dry_run:
        db.rollback()
    else:
        db.commit()

    report["total_rows"] = sum(
        v for k, v in report.items() if isinstance(v, int) and k != "total_rows"
    )
    return report


# ─────────────────────────────────────────────
#  SUPABASE  (shared helpers moved to modules.auth)
# ─────────────────────────────────────────────

# Re-export so existing imports keep working:
#   from modules.account_deletion import verify_access_token
from modules.auth import _supabase_config, verify_access_token  # noqa: F401


def delete_supabase_user(user_id: str, dry_run: bool = False) -> dict:
    """
    Supabase ki `users` row + auth record dono hatata hai.

    auth record aakhir mein jata hai: agar us se pehle kuch fail ho jaye to
    user login kar ke dobara koshish kar sakta hai. Ulta karte to wo apne hi
    baqi data tak pahunchne ka rasta kho deta.
    """
    if dry_run:
        return {"users_row": "would delete", "auth_user": "would delete"}

    url, key = _supabase_config()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    result = {}

    row = httpx.delete(
        f"{url}/rest/v1/users", headers=headers, params={"id": f"eq.{user_id}"}, timeout=20
    )
    result["users_row"] = "deleted" if row.status_code in (200, 204) else f"http {row.status_code}"

    auth = httpx.delete(f"{url}/auth/v1/admin/users/{user_id}", headers=headers, timeout=20)
    if auth.status_code in (200, 204):
        result["auth_user"] = "deleted"
    elif auth.status_code == 404:
        result["auth_user"] = "absent"
    else:
        # Ise chup-chaap nigalna hi purana bug tha — ab error saaf upar jati hai.
        raise RuntimeError(
            f"Supabase auth delete failed ({auth.status_code}): {auth.text}"
        )
    return result
