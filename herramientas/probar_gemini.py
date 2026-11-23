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
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"

ESQUEMA = """CREATE TABLE singer (
  singer_id INTEGER PRIMARY KEY,
  name TEXT,
  country TEXT,
  age INTEGER
);"""
PREGUNTA = "How many singers are from France?"


def elegir_modelo(cliente):
    elegido = os.getenv("GEMINI_MODEL")
    if elegido:
        return elegido
    nombres = sorted(m.id.removeprefix("models/") for m in cliente.models.list())
    flash = [n for n in nombres if "flash" in n and "lite" not in n
             and not any(x in n for x in ("image", "tts", "audio", "live", "embedding"))]
    print("Modelos flash disponibles:", ", ".join(flash) or "ninguno")
    if not flash:
        sys.exit("No encontré un modelo flash. Escribe uno en GEMINI_MODEL dentro de .env.")
    return flash[-1]


def main():
    load_dotenv()
    clave = os.getenv("GEMINI_API_KEY")
    if not clave:
        sys.exit("Falta GEMINI_API_KEY. Crea el archivo .env en la carpeta del proyecto "
                 "(copia .env.ejemplo) y pega ahí tu clave.")
    cliente = OpenAI(api_key=clave, base_url=URL_GEMINI)
    modelo = elegir_modelo(cliente)
    print("Modelo usado:", modelo)

    inicio = time.time()
    r = cliente.chat.completions.create(
        model=modelo,
        messages=[{"role": "user", "content":
                   f"Schema:\n{ESQUEMA}\n\nWrite only the SQLite query, without explanation, "
                   f"for this question: {PREGUNTA}"}],
    )
    segundos = time.time() - inicio
    print("\nPregunta:", PREGUNTA)
    print("SQL generado:\n", r.choices[0].message.content.strip())
    if r.usage:
        print(f"\nTokens: {r.usage.prompt_tokens} de entrada, {r.usage.completion_tokens} de salida")
    print(f"Tiempo: {segundos:.1f} s")
    print("\nLa clave funciona.")


if __name__ == "__main__":
    main()
