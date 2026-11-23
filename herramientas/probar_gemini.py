"""
Prueba que la clave de Gemini funciona antes de conectar las herramientas Text2SQL.

1. Lee la clave del archivo .env (GEMINI_API_KEY) en la carpeta del proyecto.
2. Lista los modelos disponibles y elige uno "flash" (los del nivel gratuito),
   salvo que GEMINI_MODEL indique otro.
3. Le pide una consulta SQL sencilla y muestra la respuesta, los tokens y el tiempo.

Usa la dirección de Gemini compatible con OpenAI, que es la misma que usarán
DIN-SQL, MAC-SQL y las demás herramientas.

Uso (desde la carpeta del proyecto, con el entorno activado):
  pip install openai python-dotenv
  python herramientas/probar_gemini.py
"""
import os
import re
import sys
import time

from dotenv import load_dotenv
from openai import APIError, APIStatusError, OpenAI

URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"

ESQUEMA = """CREATE TABLE singer (
  singer_id INTEGER PRIMARY KEY,
  name TEXT,
  country TEXT,
  age INTEGER
);"""
PREGUNTA = "How many singers are from France?"


def candidatos(cliente):
    """Modelos flash ordenados de más a menos recomendable.

    Primero el alias estable gemini-flash-latest, luego los numerados más nuevos.
    Se evitan los preview y los omni, que suelen no tener cuota gratuita."""
    elegido = os.getenv("GEMINI_MODEL")
    if elegido:
        return [elegido]
    nombres = [m.id.removeprefix("models/") for m in cliente.models.list()]
    flash = [n for n in nombres if "flash" in n and "lite" not in n
             and not any(x in n for x in ("image", "tts", "audio", "live", "embedding"))]
    print("Modelos flash disponibles:", ", ".join(sorted(flash)) or "ninguno")
    estables = sorted((n for n in flash if re.fullmatch(r"gemini-[\d.]+-flash", n)),
                      key=lambda n: [int(x) for x in re.findall(r"\d+", n)], reverse=True)
    orden = [n for n in ["gemini-flash-latest"] if n in flash] + estables
    if not orden:
        sys.exit("No encontré un modelo flash estable. Escribe uno en GEMINI_MODEL dentro de .env.")
    return orden


def main():
    load_dotenv()
    clave = os.getenv("GEMINI_API_KEY")
    if not clave:
        sys.exit("Falta GEMINI_API_KEY. Crea el archivo .env en la carpeta del proyecto "
                 "(copia .env.ejemplo) y pega ahí tu clave.")
    # Máximo 120 s por intento (GEMINI_TIMEOUT) y un solo reintento, para no quedarse esperando
    cliente = OpenAI(api_key=clave, base_url=URL_GEMINI, timeout=int(os.getenv("GEMINI_TIMEOUT", "120")), max_retries=1)
    mensaje = [{"role": "user", "content":
                f"Schema:\n{ESQUEMA}\n\nWrite only the SQLite query, without explanation, "
                f"for this question: {PREGUNTA}"}]
    for modelo in candidatos(cliente):
        print("Probando modelo:", modelo)
        inicio = time.time()
        try:
            r = cliente.chat.completions.create(model=modelo, messages=mensaje)
            break
        except APIStatusError as e:
            motivo = {429: "sin cuota disponible para este modelo",
                      503: "el servidor de Google está saturado en este momento"}.get(
                          e.status_code, "error del servidor")
            detalle = str(getattr(e, "message", "") or e)[:200]
            print(f"  Error {e.status_code}: {motivo}. Detalle: {detalle}")
            print("  Pruebo el siguiente modelo.")
        except APIError as e:  # p. ej., tiempo de espera agotado
            print(f"  No respondió ({type(e).__name__}). Pruebo el siguiente modelo.")
    else:
        sys.exit("Ningún modelo respondió. Espera unos minutos y vuelve a intentarlo.")
    print("Modelo usado:", modelo)
    segundos = time.time() - inicio
    print("\nPregunta:", PREGUNTA)
    print("SQL generado:\n", r.choices[0].message.content.strip())
    if r.usage:
        print(f"\nTokens: {r.usage.prompt_tokens} de entrada, {r.usage.completion_tokens} de salida")
    print(f"Tiempo: {segundos:.1f} s")
    print("\nLa clave funciona.")


if __name__ == "__main__":
    main()
