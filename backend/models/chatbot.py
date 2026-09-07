import uuid
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, JSON, text, inspect
from sqlalchemy.sql import func
from database.connection import Base


class ChatbotInstance(Base):
    __tablename__ = "chatbot_instances"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    bot_name = Column(String, default="Assistant")
    description = Column(Text, nullable=True)
    category = Column(String, default="custom")  # ecommerce / support / sales / custom
    personality = Column(String, default="helpful and friendly")
    tone = Column(String, default="professional")  # professional / friendly / casual / empathetic
    personality_traits = Column(JSON, default=list)  # ["helpful", "concise", ...]
    custom_prompt = Column(Text, nullable=True)
    welcome_message = Column(Text, default="Hello! How can I help you today?")
    primary_color = Column(String, default="#4F46E5")
    owner_email = Column(String, nullable=True)  # escalation alerts destination
    # Kaunse brand ka bot hai — multi-brand accounts mein bots ko organise karne
    # ke liye. Nullable hai: chatbot ka koi logic isse depend nahi karta, ye
    # sirf grouping/labelling ke liye hai.
    brand_profile_id = Column(Integer, nullable=True, index=True)
    status = Column(String, default="active")  # active / paused / draft
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())


class Conversation(Base):
    __tablename__ = "chatbot_conversations"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, index=True)
    customer_session_id = Column(String, index=True)
    started_at = Column(DateTime, default=func.now())
    is_escalated = Column(Boolean, default=False)
    escalated_at = Column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "chatbot_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, index=True)
    sender = Column(String)  # "customer" or "bot"
    content = Column(Text)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=func.now())


class UploadedDocument(Base):
    __tablename__ = "chatbot_uploaded_documents"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String, index=True)
    filename = Column(String)
    file_type = Column(String, nullable=True)     # pdf / docx / txt / text / faq
    file_size = Column(Integer, default=0)        # bytes
    chunks_stored = Column(Integer, default=0)
    source_type = Column(String, default="document")  # document / text / faq
    # Pinecone vector ids for THIS document only — lets a single document be
    # removed without wiping the bot's whole namespace.
    vector_ids = Column(JSON, default=list)
    uploaded_at = Column(DateTime, default=func.now())


# ── Additive Schema Migration ─────────────────
# Base.metadata.create_all() sirf missing TABLES banata hai — existing table mein
# naye columns add nahi karta. Ye helper un columns ko idempotently add karta hai
# taake purani deployments bina manual migration ke upgrade ho jayein.
_ADDED_COLUMNS = {
    "chatbot_instances": [
        ("brand_profile_id", "INTEGER"),
        ("description", "TEXT"),
        ("category", "VARCHAR"),
        ("tone", "VARCHAR"),
        ("personality_traits", "JSON"),
        ("custom_prompt", "TEXT"),
        ("welcome_message", "TEXT"),
        ("status", "VARCHAR"),
    ],
    "chatbot_uploaded_documents": [
        ("file_type", "VARCHAR"),
        ("file_size", "INTEGER"),
        ("source_type", "VARCHAR"),
        ("vector_ids", "JSON"),
    ],
}


def ensure_chatbot_schema(engine) -> None:
    """Naye chatbot columns add karta hai aur defaults backfill karta hai."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                # Table abhi bana hi nahi — create_all() ise poore schema ke saath banayega.
                continue

            # Sirf missing columns add karo. `ADD COLUMN IF NOT EXISTS` sirf Postgres
            # par chalta hai, isliye pehle inspect karke dialect-agnostic rehte hain.
            present = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in present:
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")

        if "chatbot_instances" in existing_tables:
            # Purane bots ka status is_active se derive karo (sirf jahan NULL hai).
            conn.execute(text(
                "UPDATE chatbot_instances "
                "SET status = CASE WHEN is_active THEN 'active' ELSE 'paused' END "
                "WHERE status IS NULL"
            ))
            conn.execute(text(
                "UPDATE chatbot_instances SET category = 'custom' WHERE category IS NULL"
            ))
            conn.execute(text(
                "UPDATE chatbot_instances SET tone = 'professional' WHERE tone IS NULL"
            ))
            conn.execute(text(
                "UPDATE chatbot_instances "
                "SET welcome_message = 'Hello! How can I help you today?' "
                "WHERE welcome_message IS NULL"
            ))

        if "chatbot_uploaded_documents" in existing_tables:
            conn.execute(text(
                "UPDATE chatbot_uploaded_documents "
                "SET source_type = 'document' WHERE source_type IS NULL"
            ))
