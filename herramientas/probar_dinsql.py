"""
Prueba DIN-SQL (prompts en 4 etapas: enlace de esquema, clasificación, generación y
autocorrección) con las consultas de la muestra.

Se usa el código original de DIN-SQL (versión fija, commit 0474801): sus prompts, sus
ejemplos y las funciones que los arman. Solo se cambia, desde este script:
- La llamada al LLM (GPT4_generation y GPT4_debug), para usar el mismo LLM que las demás
  herramientas. Se conservan su temperatura 0 y sus "stop" (aplicados a la respuesta, no en
  la API, porque en los modelos que razonan la API también corta el razonamiento); se
  quita el límite de tokens de salida, porque los modelos que razonan lo gastan antes.
- El ciclo principal, que en el original lee un archivo dev.json: aquí se repiten los mismos
  pasos para cada consulta de la muestra, pero sin reintentar para siempre.
- Si el modelo repite el "SELECT" con el que termina el prompt de autocorrección, no se
  duplica.
- La descripción de esquemas: se juntan las de Spider y BIRD (los ejemplos de DIN-SQL usan
  la base college_2 de Spider) y las llaves primarias compuestas de BIRD se separan en
  llaves simples, porque el código de DIN-SQL solo admite estas.

En BIRD la pregunta incluye la evidencia (DIN-SQL fue diseñado para Spider, que no la tiene).

Uso (desde la carpeta del proyecto, con el entorno activado):
  python herramientas/descargar_bases.py --grupos G1    # si falta tables.json
  python herramientas/probar_dinsql.py --grupos G1
  python herramientas/probar_dinsql.py --max 20   # sigue donde se quedó; 20 consultas nuevas
"""
import argparse
import json
import os
import subprocess
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = "https://github.com/MohammadrezaPourreza/Few-shot-NL2SQL-with-prompting"
COMMIT = "0474801616130413b024fd008b016a190684649e"
CARPETA = os.path.join(comun.RAIZ, "herramientas", "externas", "DIN-SQL")
INTENTOS = 3  # el original reintenta para siempre


def cargar_din_sql():
    """Ejecuta la parte de DIN-SQL con prompts y funciones (sin su ciclo principal)."""
    archivo = os.path.join(CARPETA, "DIN-SQL.py")
    if not os.path.exists(archivo):
        print("Descargando el código de DIN-SQL...")
        subprocess.run(["git", "clone", "-q", REPO, CARPETA], check=True)
        subprocess.run(["git", "-C", CARPETA, "checkout", "-q", COMMIT], check=True)
    codigo = open(archivo, encoding="utf-8").read()
    inicio_args = codigo.index('if sys.argv[1] == "--dataset"')
    fin_clave = codigo.index("openai.api_key = os.getenv(\"OPENAI_API_KEY\")")
    fin_clave = codigo.index("\n", fin_clave)
    codigo = codigo[:inicio_args] + codigo[fin_clave:]  # sin lectura de argumentos ni clave
    codigo = codigo[:codigo.index("if __name__ == '__main__':")]
    ns = {"__name__": "din_sql"}
    exec(compile(codigo, archivo, "exec"), ns)
    return ns


def tables_json_unido():
    """Une las descripciones de Spider y BIRD; separa llaves primarias compuestas."""
    items = []
    for benchmark in ["spider", "bird"]:
        ruta = os.path.join(comun.BASES, benchmark, "tables.json")
        if not os.path.exists(ruta):
            sys.exit(f"Falta {ruta}. Corre: python herramientas/descargar_bases.py")
        for item in json.load(open(ruta, encoding="utf-8")):
            pks = []
            for pk in item["primary_keys"]:
                pks.extend(pk if isinstance(pk, list) else [pk])
            item["primary_keys"] = pks
            items.append(item)
    destino = os.path.join(CARPETA, "tables_unido.json")
    json.dump(items, open(destino, "w", encoding="utf-8"))
    return destino


def main():
    p = argparse.ArgumentParser()
    comun.agregar_opciones(p)
    args = p.parse_args()
    cliente, modelo, uso = comun.cliente_gemini()
    din = cargar_din_sql()
    din["spider_schema"], din["spider_primary"], din["spider_foreign"] = \
        din["creatiing_schema"](tables_json_unido())

    carpeta_log = os.path.join(comun.RAIZ, "resultados", "herramientas", "logs_dinsql")
    os.makedirs(carpeta_log, exist_ok=True)
    actual = {"id": ""}

    def llamar(prompt, stop):
        # Los "stop" se aplican aquí, sobre la respuesta final, y no se envían a la API: en
        # los modelos que razonan, la API también corta el razonamiento (por ejemplo, en la
        # primera línea en blanco) y la respuesta llega vacía.
        r = cliente.chat.completions.create(
            model=modelo, messages=[{"role": "user", "content": prompt}], temperature=0.0)
        completo = (r.choices[0].message.content or "").strip()
        texto = completo
        for corte in stop:
            texto = texto.split(corte)[0]
        # Registro de cada etapa para poder revisar qué respondió el modelo
        with open(os.path.join(carpeta_log, f"{actual['id']}.txt"), "a", encoding="utf-8") as f:
            f.write(f"===== stop={stop} | finish_reason={r.choices[0].finish_reason}\n")
            f.write(f"--- respuesta completa:\n{completo!r}\n--- tras los stop:\n{texto!r}\n\n")
        return texto

    def con_intentos(funcion, *a):
        for i in range(INTENTOS):
            try:
                return funcion(*a)
            except comun.ServicioNoDisponible:
                raise
            except Exception:
                if i == INTENTOS - 1:
                    raise

    generacion = lambda prompt: llamar(prompt, ["Q:"])  # noqa: E731  (GPT4_generation)
    depuracion = lambda prompt: llamar(prompt, ["#", ";", "\n\n"])  # noqa: E731  (GPT4_debug)

    def generar(fila, ruta):
        # Mismos pasos que el ciclo principal de DIN-SQL.py
        actual["id"] = fila["id"]
        log = os.path.join(carpeta_log, f"{fila['id']}.txt")
        if os.path.exists(log):
            os.remove(log)
        pregunta, db = comun.pregunta_completa(fila), fila["db_id"]
        schema_links = con_intentos(generacion, din["schema_linking_prompt_maker"](pregunta, db))
        try:
            schema_links = schema_links.split("Schema_links: ")[1]
        except IndexError:
            schema_links = "[]"
        clasificacion = con_intentos(
            generacion, din["classification_prompt_maker"](pregunta, db, schema_links[1:]))
        try:
            clase = clasificacion.split("Label: ")[1]
        except IndexError:
            clase = '"NESTED"'
        if '"EASY"' in clase:
            sql = con_intentos(generacion, din["easy_prompt_maker"](pregunta, db, schema_links))
        elif '"NON-NESTED"' in clase:
            sql = con_intentos(generacion, din["medium_prompt_maker"](pregunta, db, schema_links))
            try:
                sql = sql.split("SQL: ")[1]
            except IndexError:
                sql = "SELECT"
        else:
            try:
                subpreguntas = clasificacion.split('questions = ["')[1].split('"]')[0]
            except IndexError:
                subpreguntas = ""
            sql = con_intentos(generacion, din["hard_prompt_maker"](pregunta, db, schema_links,
                                                                    subpreguntas))
            try:
                sql = sql.split("SQL: ")[1]
            except IndexError:
                sql = "SELECT"
        corregido = con_intentos(depuracion, din["debuger"](pregunta, db, sql)).replace("\n", " ")
        corregido = comun.limpiar_sql(corregido)
        # El prompt termina en "SELECT" para que el modelo lo continúe; los modelos de chat
        # a veces repiten la palabra, y no hay que duplicarla.
        if corregido.upper().startswith("SELECT"):
            return corregido
        return "SELECT " + corregido

    generar.uso = uso
    comun.probar("DIN-SQL", generar, args.grupos, maximo=args.max, repetir=args.repetir)


if __name__ == "__main__":
    main()
