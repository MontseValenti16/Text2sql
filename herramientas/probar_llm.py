"""
Comprueba que el LLM configurado en .env (Gemini o Groq) responde, con el mismo cliente
que usan las pruebas de las herramientas.

Uso:  python herramientas/probar_llm.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

cliente, modelo, uso = comun.cliente_gemini()
print("Proveedor:", os.getenv("LLM_PROVEEDOR", "gemini"), "| Modelo:", modelo)
inicio = time.time()
r = cliente.chat.completions.create(model=modelo, messages=[{"role": "user", "content":
    "Schema: CREATE TABLE singer (singer_id INTEGER, name TEXT, country TEXT);\n"
    "Write only the SQLite query, without explanation: How many singers are from France?"}])
print("SQL generado:", comun.limpiar_sql(r.choices[0].message.content))
print(f"Tokens: {uso.entrada} de entrada, {uso.salida} de salida | {time.time() - inicio:.1f} s")
print("El LLM funciona.")
