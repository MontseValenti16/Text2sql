"""
Prueba MAC-SQL (agentes: Selector, Decomposer y Refiner) con las consultas de la muestra.

Se usa el código original de MAC-SQL sin modificarlo. Lo único que se cambia, desde
este script, es la función que llama al LLM (core.llm.api_func), para que use Gemini
en lugar de Azure OpenAI; se mantiene la temperatura de 0.1 de MAC-SQL. La pregunta y
la evidencia de BIRD se pasan por separado, como espera MAC-SQL.

La primera vez se descarga el código de MAC-SQL en herramientas/externas/MAC-SQL
(versión fija, commit 31a9df5), que no se sube a GitHub.

Uso (desde la carpeta del proyecto, con el entorno activado):
  pip install openai pandas python-dotenv func_timeout sqlparse tiktoken nltk tqdm
  python herramientas/probar_macsql.py --grupos G1
"""
import argparse
import contextlib
import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = "https://github.com/wbbeyourself/MAC-SQL"
COMMIT = "31a9df5e0d520be4769be57a4b9022e5e34a14f4"
CARPETA = os.path.join(comun.RAIZ, "herramientas", "externas", "MAC-SQL")


def obtener_codigo():
    if not os.path.exists(os.path.join(CARPETA, "core", "agents.py")):
        print("Descargando el código de MAC-SQL...")
        subprocess.run(["git", "clone", "-q", REPO, CARPETA], check=True)
        subprocess.run(["git", "-C", CARPETA, "checkout", "-q", COMMIT], check=True)
    sys.path.insert(0, CARPETA)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--grupos", nargs="*", help="Por ejemplo: G1 G2 (por defecto, todos)")
    args = p.parse_args()
    cliente, modelo, uso = comun.cliente_gemini()
    obtener_codigo()
    os.chdir(comun.RAIZ)  # MAC-SQL trabaja con rutas relativas

    from core import llm
    from core.chat_manager import ChatManager
    from core.const import SYSTEM_NAME

    # MAC-SQL ya reintenta cada llamada 5 veces (esperando 20 s), así que aquí se
    # reintenta menos para no alargar la espera.
    comun.ESPERAS[:] = [15, 30]
    sin_servicio = {"ocurrio": False}

    def api_func(prompt):  # reemplaza la llamada a Azure OpenAI de MAC-SQL
        try:
            r = cliente.chat.completions.create(
                model=modelo, messages=[{"role": "user", "content": prompt}], temperature=0.1)
        except comun.ServicioNoDisponible:
            sin_servicio["ocurrio"] = True
            raise
        return (r.choices[0].message.content or "").strip(), \
            r.usage.prompt_tokens if r.usage else 0, r.usage.completion_tokens if r.usage else 0

    llm.api_func = api_func
    # Si se agotó la cuota diaria, que MAC-SQL no espere 20 s entre sus reintentos
    import time as _time
    import types
    llm.time = types.SimpleNamespace(
        time=_time.time,
        sleep=lambda s: None if comun.CUOTA["agotada"] else _time.sleep(s))
    llm.MODEL_NAME = modelo
    gestores = {}

    def preparar(ruta):
        benchmark = os.path.basename(os.path.dirname(os.path.dirname(ruta)))
        if benchmark not in gestores:
            datos = os.path.relpath(os.path.join(comun.BASES, benchmark))
            tablas = os.path.join(datos, "tables.json")
            if not os.path.exists(tablas):
                sys.exit(f"Falta {tablas}. Vuelve a correr: python herramientas/descargar_bases.py")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    gestores[benchmark] = ChatManager(
                        data_path=datos, tables_json_path=tablas,
                        log_path=os.path.join("resultados", "herramientas", "logs_macsql", "log.txt"),
                        model_name=modelo, dataset_name=benchmark, lazy=True)
            except Exception:  # MAC-SQL prueba la conexión al iniciar
                gestores[benchmark] = None

    def generar(fila, ruta):
        mensaje = {"idx": fila["id"], "db_id": fila["db_id"], "query": fila["pregunta"],
                   "evidence": fila["evidencia"], "extracted_schema": {},
                   "ground_truth": "", "difficulty": "", "send_to": SYSTEM_NAME}
        if gestores[fila["benchmark"]] is None:
            raise comun.ServicioNoDisponible("MAC-SQL no pudo conectarse a Gemini al iniciar")
        sin_servicio["ocurrio"] = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                gestores[fila["benchmark"]].start(mensaje)
        except Exception:
            if sin_servicio["ocurrio"]:
                raise comun.ServicioNoDisponible("Gemini no respondió durante MAC-SQL")
            raise
        sql = mensaje.get("pred") or mensaje.get("final_sql") or ""
        if not sql and sin_servicio["ocurrio"]:
            raise comun.ServicioNoDisponible("Gemini no respondió durante MAC-SQL")
        return sql

    generar.uso = uso
    comun.probar("MAC-SQL", generar, args.grupos, preparar)


if __name__ == "__main__":
    main()
