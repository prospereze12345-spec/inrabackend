import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

print("TOKEN =", GROQ_API_KEY)
print("LEN =", len(GROQ_API_KEY) if GROQ_API_KEY else 0)

URL = "https://api.groq.com/openai/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": "llama-3.1-8b-instant",
    "messages": [
        {
            "role": "user",
            "content": """
Generate marketing captions for a fashion brand for 3 platforms:

WhatsApp:
- 20–40 words
- short, direct, sales-focused

Instagram:
- 60–120 words
- engaging, aesthetic, includes hashtags (3–8)

TikTok:
- 10–25 words
- viral hook style, attention-grabbing

Rules:
- no explanations
- no numbering
- clean output only
"""
        }
    ],
    "temperature": 0.7,
    "max_tokens": 300
}

try:
    r = requests.post(URL, headers=headers, json=payload, timeout=60)
    print("STATUS:", r.status_code)
    print("RESPONSE:", r.text)
except Exception as e:
    print("ERROR:", e)