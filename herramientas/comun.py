"""
Piezas comunes para probar las herramientas Text2SQL con las mismas reglas:

- Mismo LLM para todas, por su dirección compatible con OpenAI: Gemini (GEMINI_MODEL) o
  Groq (GROQ_MODEL), según LLM_PROVEEDOR en el archivo .env.
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


PROVEEDORES = {  # direcciones compatibles con OpenAI
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ"),
}


def configuracion():
    """Devuelve (clave, modelo, url) del proveedor elegido en .env con LLM_PROVEEDOR.

    Por defecto, Gemini (GEMINI_API_KEY, GEMINI_MODEL). Con LLM_PROVEEDOR=groq se usan
    GROQ_API_KEY y GROQ_MODEL."""
    load_dotenv(os.path.join(RAIZ, ".env"))
    proveedor = os.getenv("LLM_PROVEEDOR", "gemini").lower()
    if proveedor not in PROVEEDORES:
        sys.exit(f"LLM_PROVEEDOR debe ser uno de: {', '.join(PROVEEDORES)}")
    url, prefijo = PROVEEDORES[proveedor]
    clave, modelo = os.getenv(f"{prefijo}_API_KEY"), os.getenv(f"{prefijo}_MODEL")
    if not clave or not modelo:
        sys.exit(f"Faltan {prefijo}_API_KEY o {prefijo}_MODEL en el archivo .env.")
    return clave, modelo, url


ESPERAS = [60, 120]  # segundos entre reintentos si Gemini está saturado (cada reintento gasta cuota)


ESPERADO = {"segundos": 0.0}  # tiempo de espera por reintentos (no cuenta como tiempo de la herramienta)


class ServicioNoDisponible(Exception):
    """El LLM no respondió tras varios intentos: no es un fallo de la herramienta."""


CUOTA = {"agotada": False}  # si se agota la cuota diaria, no tiene caso seguir llamando


def detalle_error(e):
    cuerpo = getattr(e, "body", None)
    if isinstance(cuerpo, list) and cuerpo:
        cuerpo = cuerpo[0]
    if isinstance(cuerpo, dict):
        cuerpo = cuerpo.get("error", cuerpo)
        if isinstance(cuerpo, dict):
            return str(cuerpo.get("message", cuerpo))
    return str(cuerpo or e)


def llamar_con_reintentos(funcion, *args, **kwargs):
    from openai import APIConnectionError, APIStatusError, APITimeoutError
    if CUOTA["agotada"]:
        raise ServicioNoDisponible("cuota diaria del LLM agotada")
    for i, espera in enumerate(ESPERAS + [None]):
        try:
            return funcion(*args, **kwargs)
        except (APIStatusError, APIConnectionError, APITimeoutError) as e:
            codigo = getattr(e, "status_code", None)
            if codigo is not None and codigo not in (429, 500, 502, 503, 504):
                raise  # error de la petición, no de saturación
            detalle = detalle_error(e)
            if codigo == 429 and re.search(r"per ?day|PerDay|daily|\(TPD\)|\(RPD\)", detalle, re.I):
                CUOTA["agotada"] = True
                print(f"    Se agotó la cuota DIARIA gratuita del LLM: {detalle[:200]}",
                      file=sys.stderr)
                raise ServicioNoDisponible("cuota diaria del LLM agotada")
            if espera is None:
                raise ServicioNoDisponible(f"El LLM no respondió tras {len(ESPERAS) + 1} "
                                           f"intentos (último error {codigo}: {detalle[:150]})")
            # A stderr, para que se vea aunque la herramienta oculte sus mensajes
            print(f"    LLM no disponible ({codigo or type(e).__name__}: {detalle[:120]}); "
                  f"reintento en {espera} s...", file=sys.stderr)
            time.sleep(espera)
            ESPERADO["segundos"] += espera


class ContadorUso:
    """Cuenta llamadas y tokens de un cliente OpenAI sin cambiar la herramienta."""

    def __init__(self, cliente):
        self.llamadas = self.entrada = self.salida = 0
        original = cliente.chat.completions.create

        rpm = float(os.getenv("LLM_RPM", os.getenv("GEMINI_RPM", "5")))  # solicitudes por minuto
        intervalo = 60.0 / rpm + 1 if rpm > 0 else 0
        ultima = {"t": 0.0}

        def create(*args, **kwargs):
            # Espaciar las llamadas para no pasar el límite por minuto del nivel gratuito
            falta = ultima["t"] + intervalo - time.time()
            if falta > 0:
                time.sleep(falta)
                ESPERADO["segundos"] += falta
            ultima["t"] = time.time()
            # Gemini rechaza parámetros enviados como null (por ejemplo, stop=None que
            # manda Vanna); se quitan sin cambiar nada más de la petición.
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            r = llamar_con_reintentos(original, *args, **kwargs)
            self.llamadas += 1
            if getattr(r, "usage", None):
                self.entrada += r.usage.prompt_tokens or 0
                self.salida += r.usage.completion_tokens or 0
            return r

        cliente.chat.completions.create = create

    def reiniciar(self):
        self.llamadas = self.entrada = self.salida = 0


def cliente_gemini(timeout=180):
    """Cliente del LLM elegido (Gemini o Groq), con contador de uso y límite por minuto."""
    from openai import OpenAI
    clave, modelo, url = configuracion()
    cliente = OpenAI(api_key=clave, base_url=url, timeout=timeout, max_retries=0)
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
    if m:
        texto = m.group(1)
    else:  # bloque sin cerrar (por ejemplo, cortado en ";")
        texto = re.sub(r"^\s*```(?:sql)?\s*", "", texto, flags=re.I)
    return texto.strip().rstrip(";").strip()


def ejecutar(ruta, sql):
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    limite = time.time() + LIMITE_SEGUNDOS_SQL
    con.set_progress_handler(lambda: int(time.time() > limite), 10000)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def normalizar(filas):
    """Filas comparables entre motores distintos (por ejemplo, SQLite y DuckDB): números
    como float redondeado, fechas y otros valores como texto."""
    import decimal
    salida = set()
    for fila in filas:
        valores = []
        for v in fila:
            if isinstance(v, bool):
                v = int(v)
            if isinstance(v, (int, float, decimal.Decimal)):
                v = round(float(v), 4)
            elif v is not None and not isinstance(v, str):
                v = str(v)
            valores.append(v)
        salida.add(tuple(valores))
    return salida


def calificar(ruta, sql_generado, sql_correcto, ejecutor=None):
    """Devuelve (acierto, error). Acierto = mismas filas que el SQL correcto.

    `ejecutor(ruta, sql) -> filas` (opcional) ejecuta el SQL generado en otro motor (WrenAI
    ejecuta en DuckDB); en ese caso los valores de ambos lados se normalizan."""
    try:
        esperado = set(ejecutar(ruta, sql_correcto))
    except Exception as e:
        return False, f"el SQL correcto no se ejecuta: {e}"
    if not sql_generado:
        return False, "no generó SQL"
    try:
        obtenido = set((ejecutor or ejecutar)(ruta, sql_generado))
    except Exception as e:
        return False, f"error al ejecutar: {str(e)[:300]}"
    if ejecutor:
        return normalizar(obtenido) == normalizar(esperado), ""
    return obtenido == esperado, ""


def probar(herramienta, generar, grupos=None, preparar=None, ejecutor=None):
    """Corre `generar(fila, ruta) -> sql` en cada consulta y guarda los resultados.

    `preparar(ruta)` (opcional) se llama una vez por base de datos, antes de sus consultas.
    `ejecutor(ruta, sql)` (opcional): ver calificar."""
    muestra = cargar_muestra(grupos)
    _, modelo, _ = configuracion()
    filas, preparadas = [], set()
    for _, f in muestra.iterrows():
        ruta = ruta_base(f)
        if preparar and ruta not in preparadas:
            preparar(ruta)
            preparadas.add(ruta)
        uso = generar.uso
        uso.reiniciar()
        ESPERADO["segundos"] = 0.0
        inicio, error, sin_servicio = time.time(), "", False
        try:
            sql = limpiar_sql(generar(f, ruta))
        except ServicioNoDisponible as e:
            sql, error, sin_servicio = "", f"sin respuesta del LLM: {e}", True
        except Exception as e:
            detalle = getattr(e, "body", None) or str(e)
            sql, error = "", f"la herramienta falló: {type(e).__name__}: {str(detalle)[:300]}"
        segundos = round(time.time() - inicio - ESPERADO["segundos"], 1)
        acierto, error_cal = calificar(ruta, sql, f["sql"], ejecutor) if not error else (False, error)
        filas.append({"herramienta": herramienta, "modelo": modelo, "grupo": f["grupo"],
                      "benchmark": f["benchmark"], "id": f["id"], "db_id": f["db_id"],
                      "nivel": f["nivel"], "pregunta": f["pregunta"], "sql_correcto": f["sql"],
                      "sql_generado": sql, "acierto": acierto, "error": error or error_cal,
                      "sin_respuesta_llm": sin_servicio,
                      "llamadas_llm": uso.llamadas, "tokens_entrada": uso.entrada,
                      "tokens_salida": uso.salida, "segundos": segundos})
        marca = "ACIERTO" if acierto else ("PENDIENTE" if sin_servicio else "FALLO")
        print(f"{f['grupo']} {f['benchmark']:6} {f['nivel']:10} {marca:7} {segundos:6.1f} s "
              f"{uso.entrada + uso.salida:6} tokens  {(error or error_cal)[:160]}")
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
    validas = total[~total.sin_respuesta_llm]
    print(f"\n{herramienta}: {int(validas.acierto.sum())} de {len(validas)} aciertos. "
          f"Resultados en {os.path.relpath(ruta_csv, RAIZ)}")
    pendientes = total[total.sin_respuesta_llm]
    if len(pendientes):
        print(f"{len(pendientes)} consulta(s) PENDIENTE(S): El LLM no respondió, así que no "
              f"cuentan como fallo. Vuelve a correr el comando más tarde para completarlas.")
