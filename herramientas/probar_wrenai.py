"""
Prueba WrenAI con las consultas de la muestra.

La versión actual de WrenAI (wrenai 0.18) no genera SQL por sí misma: es una capa semántica
(MDL) que un agente usa para conocer el esquema y ejecutar el SQL. Aquí se usa su integración
oficial con LangChain (wren-langchain): un agente de LangChain con las herramientas y el
system prompt de WrenToolkit (wren_list_models, wren_dry_plan, wren_query), y el mismo LLM
que las demás herramientas.

Preparación por base de datos (automática, en data/wren/<benchmark>/<db_id>/, que no se
sube a GitHub):
1. La base SQLite se copia a un archivo DuckDB, porque WrenAI no se conecta a SQLite.
2. Se genera el MDL con las tablas, columnas, llaves primarias y llaves foráneas
   (relaciones). Sin descripciones ni reglas de negocio: el agente recibe la misma
   información que las demás herramientas.
No se usa la memoria de Wren (búsqueda semántica del esquema), que pide descargar un modelo
de embeddings: con esquemas de este tamaño, wren_list_models ya le da al agente todo el
esquema.

Calificación: el SQL final del agente (su última consulta con wren_query sin error) se ejecuta
con WrenAI y sus filas se comparan con las del SQL correcto ejecutado en SQLite.

Uso (desde la carpeta del proyecto, con el entorno activado):
  python -m pip install wrenai wren-langchain langchain langchain-openai duckdb
  python herramientas/probar_wrenai.py --grupos G1
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import warnings
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

warnings.filterwarnings("ignore", message="Arrow output")
CARPETA_WREN = os.path.join(comun.RAIZ, "data", "wren")
LIMITE_PASOS = 25  # pasos máximos del agente (llamadas al LLM + herramientas)


# ---------- Preparación de cada base ----------

def tablas_de(con):
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def a_duckdb(ruta_sqlite, ruta_duckdb):
    """Copia todas las tablas de la base SQLite a un archivo DuckDB."""
    import duckdb
    import pandas as pd
    if os.path.exists(ruta_duckdb):
        return
    print(f"  Copiando {os.path.basename(ruta_sqlite)} a DuckDB para WrenAI (solo la primera vez)...")
    os.makedirs(os.path.dirname(ruta_duckdb), exist_ok=True)
    temporal = ruta_duckdb + ".tmp"
    if os.path.exists(temporal):
        os.remove(temporal)
    origen = sqlite3.connect(f"file:{ruta_sqlite}?mode=ro", uri=True)
    origen.text_factory = lambda b: b.decode("utf-8", errors="replace")
    destino = duckdb.connect(temporal)
    for tabla in tablas_de(origen):
        df = pd.read_sql_query(f'SELECT * FROM "{tabla}"', origen)
        destino.register("df_temporal", df)
        destino.execute(f'CREATE TABLE "{tabla}" AS SELECT * FROM df_temporal')
        destino.unregister("df_temporal")
    destino.close()
    origen.close()
    os.replace(temporal, ruta_duckdb)


def construir_mdl(ruta_sqlite, ruta_duckdb, db_id):
    """MDL de Wren a partir del esquema: modelos, columnas, llaves y relaciones."""
    import duckdb
    origen = sqlite3.connect(f"file:{ruta_sqlite}?mode=ro", uri=True)
    destino = duckdb.connect(ruta_duckdb, read_only=True)
    tablas = tablas_de(origen)
    modelos, relaciones, nombres = [], [], set()
    for tabla in tablas:
        tipos = {r[0]: r[1] for r in destino.execute(f'DESCRIBE "{tabla}"').fetchall()}
        info = origen.execute(f'PRAGMA table_info("{tabla}")').fetchall()
        pks = [r[1] for r in info if r[5]]
        modelo = {"name": tabla,
                  "tableReference": {"catalog": db_id, "schema": "main", "table": tabla},
                  "columns": [{"name": r[1], "type": tipos.get(r[1], "VARCHAR"),
                               "isCalculated": False, "notNull": False, "properties": {}}
                              for r in info],
                  "properties": {}}
        if len(pks) == 1:
            modelo["primaryKey"] = pks[0]
        modelos.append(modelo)
        for fk in origen.execute(f'PRAGMA foreign_key_list("{tabla}")').fetchall():
            otra, col, col_otra = fk[2], fk[3], fk[4]
            otra = next((t for t in tablas if t.lower() == otra.lower()), None)
            if not otra or not col_otra or otra == tabla:
                continue
            nombre = re.sub(r"\W", "_", f"{tabla}_{col}_{otra}")
            while nombre in nombres:
                nombre += "_"
            nombres.add(nombre)
            relaciones.append({"name": nombre, "models": [tabla, otra], "joinType": "MANY_TO_ONE",
                               "condition": f'"{tabla}"."{col}" = "{otra}"."{col_otra}"'})
    origen.close()
    destino.close()
    return {"catalog": "wren", "schema": "public", "dataSource": "duckdb",
            "models": modelos, "relationships": relaciones, "views": []}


class Conexion:
    """Conexión de Wren a la carpeta con el archivo DuckDB (en lugar de un perfil global)."""

    def __init__(self, carpeta):
        self.carpeta = carpeta

    def datasource(self):
        return "duckdb"

    def connection_info(self):
        return {"url": self.carpeta, "format": "duckdb"}


def preparar_toolkit(ruta_sqlite):
    from wren_langchain import WrenToolkit
    from wren_langchain._providers.mdl_source import ProjectMDLSource
    from wren_langchain._providers.memory import NoopMemoryProvider
    db_id = os.path.splitext(os.path.basename(ruta_sqlite))[0]
    benchmark = os.path.basename(os.path.dirname(os.path.dirname(ruta_sqlite)))
    carpeta = Path(CARPETA_WREN, benchmark, db_id).resolve()
    ruta_duckdb = carpeta / "datos" / f"{db_id}.duckdb"
    a_duckdb(ruta_sqlite, str(ruta_duckdb))
    (carpeta / "target").mkdir(parents=True, exist_ok=True)
    (carpeta / "target" / "mdl.json").write_text(
        json.dumps(construir_mdl(ruta_sqlite, str(ruta_duckdb), db_id), indent=1), encoding="utf-8")
    (carpeta / "wren_project.yml").write_text(
        f"schema_version: 3\nname: {db_id}\ncatalog: wren\nschema: public\ndata_source: duckdb\n",
        encoding="utf-8")
    return WrenToolkit(project_path=carpeta, mdl_source=ProjectMDLSource(project_path=carpeta),
                       connection_provider=Conexion(str(carpeta / "datos")),
                       memory_provider=NoopMemoryProvider())


# ---------- Agente ----------

class _Crudo:
    """Imita client.with_raw_response.create(...).parse() que usa langchain-openai."""

    def __init__(self, create):
        self._create = create

    def create(self, **kwargs):
        respuesta = self._create(**kwargs)
        return type("Crudo", (), {"parse": lambda _self: respuesta, "headers": {}})()


class ClienteContado:
    """Pasa las llamadas de LangChain por el cliente de comun.py: mismo conteo de tokens,
    misma pausa entre llamadas y mismos reintentos que en las demás herramientas."""

    def __init__(self, completions):
        self.create = completions.create
        self.with_raw_response = _Crudo(completions.create)


def crear_modelo():
    from langchain_openai import ChatOpenAI
    cliente, modelo, uso = comun.cliente_gemini()
    clave, _, url = comun.configuracion()
    llm = ChatOpenAI(model=modelo, api_key=clave, base_url=url, temperature=0, max_retries=0)
    llm.client = ClienteContado(cliente.chat.completions)
    return llm, uso


def sql_final(mensajes):
    """Última consulta de wren_query que se ejecutó sin error."""
    respuestas = {m.tool_call_id: m for m in mensajes if type(m).__name__ == "ToolMessage"}
    final = ""
    for m in mensajes:
        for llamada in getattr(m, "tool_calls", None) or []:
            if llamada["name"] != "wren_query":
                continue
            respuesta = respuestas.get(llamada["id"])
            if respuesta is None or getattr(respuesta, "status", "") == "error":
                continue
            texto = str(respuesta.content)
            if re.search(r"""["']ok["']\s*:\s*(true|True)""", texto):
                final = llamada["args"].get("sql", "")
    return final


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--grupos", nargs="*", help="Por ejemplo: G1 G2 (por defecto, todos)")
    args = p.parse_args()
    from langchain.agents import create_agent

    llm, uso = crear_modelo()
    estado = {}

    def preparar(ruta):
        toolkit = preparar_toolkit(ruta)
        herramientas = toolkit.get_tools(include_memory_write=False)
        # Se guarda por base: varias consultas de grupos distintos usan la misma base.
        estado[ruta] = toolkit, create_agent(model=llm, tools=herramientas,
                                        system_prompt=toolkit.system_prompt(tools=herramientas))

    def generar(fila, ruta):
        respuesta = estado[ruta][1].invoke(
            {"messages": [{"role": "user", "content": comun.pregunta_completa(fila)}]},
            {"recursion_limit": LIMITE_PASOS})
        return sql_final(respuesta["messages"])

    def ejecutar_con_wren(ruta, sql):
        tabla = estado[ruta][0].query(sql)
        return list(zip(*[columna.to_pylist() for columna in tabla.columns]))

    generar.uso = uso
    comun.probar("WrenAI", generar, args.grupos, preparar, ejecutor=ejecutar_con_wren)


if __name__ == "__main__":
    main()
