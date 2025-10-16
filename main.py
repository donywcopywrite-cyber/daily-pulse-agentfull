from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os, requests
from openai import OpenAI

# --- Initialize FastAPI app and OpenAI client
app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Health check (useful for quick testing)
@app.get("/")
def health():
    return {"ok": True, "service": "daily-pulse-agent"}

# --- Example helper: fetch market metrics
def metrics_get(region: str):
    base = os.getenv("METRICS_BASE_URL")
    api_key = os.getenv("METRICS_API_KEY")
    if not base or not api_key:
        # Return sample data if env not configured
        return {
            "warning": "metrics config missing; using placeholder data",
            "region": region,
            "sample": {"interest_rate": 5.25, "trend": "stable", "inventory": "Donnée non disponible"}
        }
    r = requests.get(
        f"{base}/v1/market/metrics",
        params={"region": region},
        headers={"Authorization": f"Bearer {api_key}"}
    )
    r.raise_for_status()
    return r.json()

# --- Example helper: publish to Bubble
def bubble_publish(payload: dict):
    url = os.getenv("BUBBLE_WORKFLOW_URL")
    token = os.getenv("BUBBLE_API_TOKEN")
    if not url or not token:
        return {"warning": "bubble config missing; skipping publish", "payload_preview": payload}
    r = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    r.raise_for_status()
    return r.json()

# --- Main endpoint to run the AI agent
@app.post("/agent/run")
async def run_agent(req: Request):
    body = await req.json()
    region = body.get("region", "QC")
    convo_id = body.get("conversation_id", "pulse-demo")
    auto_publish = bool(body.get("auto_publish", False))
    user_text = body.get("input_as_text", "run_market_pulse_for_QC")

    # 1️⃣ Fetch market metrics
    metrics = metrics_get(region)

    # 2️⃣ Ask OpenAI to generate a bilingual summary
    prompt = f"""
Tu es un assistant immobilier québécois.
Résume ces données du marché ({region}) en deux courts paragraphes (FR puis EN, 80–100 mots chacun).
Ajoute ensuite trois bullet points "comment le dire aux clients aujourd'hui".
Si des données manquent, dis "Donnée non disponible / Data not available".
Données : {metrics}
Texte utilisateur : {user_text}
"""

    chat = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "You are a concise, bilingual real estate assistant for Québec."},
            {"role": "user", "content": prompt}
        ]
    )

    text = chat.choices[0].message.content

    # 3️⃣ Optionally publish to Bubble
    bubble_result = None
    if auto_publish:
        bubble_result = bubble_publish({
            "as_of": body.get("as_of", "today"),
            "fr_text": text,
            "en_text": text,
            "bullets": ["Point #1", "Point #2", "Point #3"],
            "metrics_json": str(metrics),
            "sources": ["Statistique Canada", "Banque du Canada"],
            "auto_publish": True
        })

    return JSONResponse({
        "conversation_id": convo_id,
        "region": region,
        "output": text,
        "bubble_result": bubble_result
    })
