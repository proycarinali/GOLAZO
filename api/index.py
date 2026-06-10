import json
import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from openai import OpenAI

# Definicion principal en el nivel superior para Vercel
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROK_API_KEY = os.environ.get("GROK_API_KEY")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")

grok_client = None
if GROK_API_KEY:
    grok_client = OpenAI(
        api_key=GROK_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )


def obtener_datos_final_mundo():
    base_url = "https://v3.football.api-sports.io"
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY or "",
        "x-rapidapi-host": "v3.football.api-sports.io"
    }

    resultado = {"detalles": {"partido": "Buscando partido reciente..."}, "jugadores": []}

    try:
        res_list = requests.get(
            f"{base_url}/fixtures?league=39&season=2024&status=FT&last=1",
            headers=headers, timeout=10
        )
        if res_list.status_code == 200:
            data_list = res_list.json()
            if data_list.get("response"):
                fixture = data_list["response"][0]
                fixture_id = fixture["fixture"]["id"]
                resultado["detalles"]["partido"] = (
                    f"{fixture['teams']['home']['name']} vs {fixture['teams']['away']['name']}"
                )

                url = f"{base_url}/fixtures/players?fixture={fixture_id}"
                res = requests.get(url, headers=headers, timeout=10)

                if res.status_code == 200:
                    data = res.json()
                    if "response" in data and data["response"]:
                        for team in data["response"]:
                            for player in team.get("players", []):
                                stats = player.get("statistics", [{}])[0]
                                resultado["jugadores"].append({
                                    "nombre": player["player"]["name"],
                                    "posicion": stats.get("games", {}).get("position", "N/A"),
                                    "minutos": stats.get("games", {}).get("minutes", 0),
                                    "calificacion": stats.get("games", {}).get("rating", "N/A"),
                                    "goles": stats.get("goals", {}).get("total", 0),
                                    "asistencias": stats.get("goals", {}).get("assists", 0),
                                    "tiros_total": stats.get("shots", {}).get("total", 0),
                                    "tiros_al_arco": stats.get("shots", {}).get("on", 0),
                                    "pases_completados": stats.get("passes", {}).get("accuracy", "0%"),
                                    "faltas_cometidas": stats.get("fouls", {}).get("committed", 0),
                                    "faltas_recibidas": stats.get("fouls", {}).get("drawn", 0),
                                    "tarjetas_amarillas": stats.get("cards", {}).get("yellow", 0),
                                    "tarjetas_rojas": stats.get("cards", {}).get("red", 0),
                                    "atajadas": stats.get("goalkeeper", {}).get("saves", 0)
                                })
    except Exception as e:
        resultado["error"] = str(e)
        resultado["detalles"]["debug"] = f"Excepcion: {type(e).__name__}: {str(e)}"

    return resultado


@app.get("/", response_class=HTMLResponse)
async def root():
    # El HTML debe estar en api/index.html para que __file__ lo encuentre
    ruta_html = os.path.join(os.path.dirname(__file__), "index.html")
    with open(ruta_html, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/test")
async def probar_apis():
    datos = obtener_datos_final_mundo()
    grok_res = {"status": "No configurado"}

    if grok_client:
        try:
            response = grok_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "Hola"}]
            )
            grok_res = {"status": 200, "body": response.choices[0].message.content}
        except Exception as e:
            grok_res = {"error": str(e)}

    return {"grok": grok_res, "datos_futbol": datos}


@app.get("/api/trivias")
async def obtener_trivias():
    if not grok_client:
        return {"error": "GROK_API_KEY no configurada"}

    datos = obtener_datos_final_mundo()
    info_jugadores = datos.get("jugadores", [])[:15]

    if not info_jugadores:
        # BUG CORREGIDO: el string estaba roto con un salto de linea sin cerrar
        prompt_contenido = (
            "Eres un experto en futbol. Basandote en tus conocimientos sobre el ultimo partido "
            "del ultimo Mundial, o del Mundial en curso si lo hay, "
            "crea 50 preguntas de trivia variadas y desafiantes. "
            "Puedes incluir preguntas sobre: goleadores (Mbappe hat-trick, Di Maria, Messi penales), "
            "sustituciones clave, minutos de los goles, jugadores destacados, estadisticas del partido, "
            "arbitro, asistencias, tarjetas, penales (quien pateo, quien atajo), "
            "contexto historico (primera copa de Messi, records rotos, etc.). "
            "IMPORTANTE: todas las respuestas correctas deben ser 100% veridicas. "
            "Formato de salida SOLO JSON sin texto adicional ni backticks: "
            "{\"preguntas\": [{\"pregunta\": \"...\", \"opciones\": [\"A\",\"B\",\"C\"], \"correcta\": \"...\"}]}"
        )
    else:
        prompt_contenido = (
            f"Crea 50 preguntas de trivia basandote estrictamente en estos jugadores: "
            f"{json.dumps(info_jugadores)}. Formato: {{\"preguntas\": [{{\"pregunta\": \"...\", "
            f"\"opciones\": [\"A\",\"B\",\"C\"], \"correcta\": \"...\"}}]}}"
        )

    try:
        response = grok_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt_contenido}],
            max_tokens=4096
        )
        raw_text = response.choices[0].message.content
        texto = raw_text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto)
    except Exception as e:
        return {"error": str(e)}
