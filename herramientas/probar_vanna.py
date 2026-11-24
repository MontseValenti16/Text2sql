"""
Prueba Vanna con las consultas de la muestra.

Se usa la interfaz clásica de Vanna (vanna.legacy), que recibe una pregunta y devuelve
el SQL: se "entrena" con el esquema (DDL) de cada base y luego se llama a generate_sql.
El LLM es Gemini, por su dirección compatible con OpenAI, y la búsqueda del esquema
relevante la hace ChromaDB, como en la configuración estándar de Vanna.

Uso (desde la carpeta del proyecto, con el entorno activado):
  pip install "vanna[chromadb]" openai pandas python-dotenv
  python herramientas/probar_vanna.py --grupos G1
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

from vanna.legacy.chromadb import ChromaDB_VectorStore  # noqa: E402
from vanna.legacy.openai import OpenAI_Chat  # noqa: E402


class Vanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, cliente, config):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, client=cliente, config=config)

    def log(self, message, title="Info"):  # silenciar los registros de Vanna
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--grupos", nargs="*", help="Por ejemplo: G1 G2 (por defecto, todos)")
    args = p.parse_args()
    cliente, modelo, uso = comun.cliente_gemini()
    estado = {}

    def preparar(ruta):
        # Una instancia nueva por base, con su propio almacén (carpeta temporal),
        # entrenada solo con el esquema de esa base
        vn = Vanna(cliente, {"model": modelo, "temperature": 0,
                             "path": tempfile.mkdtemp(prefix="vanna_"),
                             **estado.get("config_extra", {})})
        for ddl in comun.esquema_ddl(ruta):
            vn.train(ddl=ddl)
        vn.connect_to_sqlite(ruta)
        estado["vn"] = vn

    def generar(fila, ruta):
        return estado["vn"].generate_sql(comun.pregunta_completa(fila))

    generar.uso = uso
    comun.probar("Vanna", generar, args.grupos, preparar)


if __name__ == "__main__":
    main()
