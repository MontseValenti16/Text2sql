"""
Piezas comunes para probar las herramientas Text2SQL con las mismas reglas:

- Mismo LLM para todas: Gemini por su dirección compatible con OpenAI, con el modelo de
  GEMINI_MODEL (archivo .env).
- Misma entrada: la pregunta y, en BIRD, también la evidencia (como en el benchmark).
- Misma forma de calificar: exactitud por ejecución, como BIRD. Se ejecutan el SQL
  generado y el correcto, y se comparan los conjuntos de filas (sin importar el orden).
- Mismo registro: SQL generado, acierto, tokens, llamadas al LLM y tiempo de cada consulta,
  en resultados/herramientas/<herramienta>.csv.
"""
import os
import re
import sqlite3
import sys
import threading
import time

import pandas as pd
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUESTRA = os.path.join(RAIZ, "resultados", "muestra", "muestra_representantes.csv")
BASES = os.path.join(RAIZ, "data", "bases")
SALIDA = os.path.join(RAIZ, "resultados", "herramientas")
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"
LIMITE_SEGUNDOS_SQL = 60  # una consulta que tarde más se corta y cuenta como fallo


def configuracion():
    load_dotenv(os.path.join(RAIZ, ".env"))
    clave, modelo = os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL")
    if not clave or not modelo:
        sys.exit("Faltan GEMINI_API_KEY o GEMINI_MODEL en el archivo .env.")
    return clave, modelo


class ContadorUso:
    """Cuenta llamadas y tokens de un cliente OpenAI sin cambiar la herramienta."""

    def __init__(self, cliente):
        self.llamadas = self.entrada = self.salida = 0
        original = cliente.chat.completions.create

        def create(*args, **kwargs):
            r = original(*args, **kwargs)
            self.llamadas += 1
            if getattr(r, "usage", None):
                self.entrada += r.usage.prompt_tokens or 0
                self.salida += r.usage.completion_tokens or 0
            return r

        cliente.chat.completions.create = create

    def reiniciar(self):
        self.llamadas = self.entrada = self.salida = 0


def cliente_gemini(timeout=180):
    from openai import OpenAI
    clave, modelo = configuracion()
    cliente = OpenAI(api_key=clave, base_url=URL_GEMINI, timeout=timeout, max_retries=2)
    return cliente, modelo, ContadorUso(cliente)


def cargar_muestra(grupos=None):
    m = pd.read_csv(MUESTRA).fillna("")
    if grupos:
        m = m[m.grupo.isin(grupos)]
    return m


def ruta_base(fila):
    ruta = os.path.join(BASES, fila["benchmark"], fila["db_id"], f"{fila['db_id']}.sqlite")
    if not os.path.exists(ruta):
        sys.exit(f"Falta la base {ruta}. Corre antes: python herramientas/descargar_bases.py")
    return ruta


def pregunta_completa(fila):
    """Pregunta tal como la recibe cada herramienta (en BIRD, con su evidencia)."""
    if fila["evidencia"]:
        return f"{fila['pregunta']} (Evidence: {fila['evidencia']})"
    return fila["pregunta"]


def esquema_ddl(ruta):
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    ddl = [r[0] for r in con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")]
    con.close()
    return ddl


def limpiar_sql(texto):
    """Quita bloques ```sql``` y texto de más alrededor de la consulta."""
    if not texto:
        return ""
    m = re.search(r"```(?:sql)?\s*(.*?)```", texto, re.S | re.I)
    return (m.group(1) if m else texto).strip().rstrip(";").strip()


def ejecutar(ruta, sql):
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    limite = time.time() + LIMITE_SEGUNDOS_SQL
    con.set_progress_handler(lambda: int(time.time() > limite), 10000)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def calificar(ruta, sql_generado, sql_correcto):
    """Devuelve (acierto, error). Acierto = mismas filas que el SQL correcto."""
    try:
        esperado = set(ejecutar(ruta, sql_correcto))
    except Exception as e:
        return False, f"el SQL correcto no se ejecuta: {e}"
    if not sql_generado:
        return False, "no generó SQL"
    try:
        obtenido = set(ejecutar(ruta, sql_generado))
    except Exception as e:
        return False, f"error al ejecutar: {e}"
    return obtenido == esperado, ""


def probar(herramienta, generar, grupos=None, preparar=None):
    """Corre `generar(fila, ruta) -> sql` en cada consulta y guarda los resultados.

    `preparar(ruta)` (opcional) se llama una vez por base de datos, antes de sus consultas."""
    muestra = cargar_muestra(grupos)
    _, modelo = configuracion()
    filas, preparadas = [], set()
    for _, f in muestra.iterrows():
        ruta = ruta_base(f)
        if preparar and ruta not in preparadas:
            preparar(ruta)
            preparadas.add(ruta)
        uso = generar.uso
        uso.reiniciar()
        inicio, error = time.time(), ""
        try:
            sql = limpiar_sql(generar(f, ruta))
        except Exception as e:
            sql, error = "", f"la herramienta falló: {type(e).__name__}: {str(e)[:300]}"
        segundos = round(time.time() - inicio, 1)
        acierto, error_cal = calificar(ruta, sql, f["sql"]) if not error else (False, error)
        filas.append({"herramienta": herramienta, "modelo": modelo, "grupo": f["grupo"],
                      "benchmark": f["benchmark"], "id": f["id"], "db_id": f["db_id"],
                      "nivel": f["nivel"], "pregunta": f["pregunta"], "sql_correcto": f["sql"],
                      "sql_generado": sql, "acierto": acierto, "error": error or error_cal,
                      "llamadas_llm": uso.llamadas, "tokens_entrada": uso.entrada,
                      "tokens_salida": uso.salida, "segundos": segundos})
        marca = "ACIERTO" if acierto else "FALLO"
        print(f"{f['grupo']} {f['benchmark']:6} {f['nivel']:10} {marca:7} {segundos:6.1f} s "
              f"{uso.entrada + uso.salida:6} tokens  {(error or error_cal)[:80]}")
    os.makedirs(SALIDA, exist_ok=True)
    nombre = herramienta.lower().replace(" ", "_")
    ruta_csv = os.path.join(SALIDA, f"{nombre}.csv")
    nuevo = pd.DataFrame(filas)
    if os.path.exists(ruta_csv):  # conservar resultados de otros grupos
        viejo = pd.read_csv(ruta_csv)
        viejo = viejo[~viejo.id.astype(str).isin(nuevo.id.astype(str))]
        nuevo = pd.concat([viejo, nuevo], ignore_index=True)
    nuevo.sort_values(["grupo", "benchmark"]).to_csv(ruta_csv, index=False)
    total = pd.DataFrame(filas)
    print(f"\n{herramienta}: {int(total.acierto.sum())} de {len(total)} aciertos. "
          f"Resultados en {os.path.relpath(ruta_csv, RAIZ)}")
