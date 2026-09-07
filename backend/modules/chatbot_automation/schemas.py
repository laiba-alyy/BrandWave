from pydantic import BaseModel, Field
from typing import Optional, List


class CreateChatbotRequest(BaseModel):
    user_id: str
    # Frontend active brand bhejta hai — link create par hi populate ho jata hai,
    # kisi extra UI ki zaroorat nahi.
    brand_profile_id: Optional[int] = None
    bot_name: str = "Assistant"
    description: Optional[str] = None
    category: str = "custom"
    personality: str = "helpful and friendly"
    tone: str = "professional"
    personality_traits: List[str] = Field(default_factory=list)
    custom_prompt: Optional[str] = None
    welcome_message: str = "Hello! How can I help you today?"
    primary_color: str = "#4F46E5"
    owner_email: Optional[str] = None
    status: str = "active"


class UpdateChatbotRequest(BaseModel):
    bot_name: Optional[str] = None
    brand_profile_id: Optional[int] = None
    description: Optional[str] = None
    category: Optional[str] = None
    personality: Optional[str] = None
    tone: Optional[str] = None
    personality_traits: Optional[List[str]] = None
    custom_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    primary_color: Optional[str] = None
    owner_email: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class ChatRequest(BaseModel):
    bot_id: str
    # POST /api/chatbot/chat JAAN BOOJH KAR public hai (embeddable widget usay
    # kisi bhi Shopify store se call karta hai) aur bot_id embed snippet mein
    # likha hota hai. Pehle `message` unbounded thi: 60,000 characters seedha
    # embeddings aur Groq tak chale jate the, jis se ek hi request poora shared
    # rate-limit budget kha kar 429 le aati thi.
    #
    # 2,000 characters ek asli customer sawal ke liye kaafi zyada hain — is se
    # bara input ab 422 par ruk jata hai, kisi API call se pehle.
    message: str = Field(min_length=1, max_length=2000)
    customer_session_id: Optional[str] = None


class UploadTextRequest(BaseModel):
    """Raw text ko knowledge base mein chunk karke store karne ke liye."""
    text: str
    title: Optional[str] = None


class FaqPair(BaseModel):
    question: str
    answer: str


class UploadFaqRequest(BaseModel):
    """Question/answer pairs — formatted text bana kar store hote hain."""
    faqs: List[FaqPair]
    title: Optional[str] = None
