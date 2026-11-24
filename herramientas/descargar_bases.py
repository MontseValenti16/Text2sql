"""
Descarga las bases de datos SQLite que usan las consultas de la muestra y comprueba
que el SQL correcto de cada consulta se ejecuta en ellas.

- BIRD Mini-Dev: minidev.zip, enlace oficial del repositorio bird-bench/mini_dev.
- Spider: el zip oficial de Spider en Google Drive (el mismo que usa el cargador de
  Hugging Face); se descarga con gdown.

Solo se extraen las bases de la muestra, en data/bases/<benchmark>/<db_id>/<db_id>.sqlite.
Los zips quedan en data/descargas/ por si hacen falta más bases. Ninguna de las dos
carpetas se sube a GitHub.

Uso (desde la carpeta del proyecto, con el entorno activado):
  pip install gdown pandas
  python herramientas/descargar_bases.py
  python herramientas/descargar_bases.py --grupos G1      # solo las bases de G1

Si una descarga automática falla, baja el zip a mano y guárdalo en data/descargas/ con el
nombre indicado (minidev.zip o spider.zip); el script lo usará sin volver a descargarlo.
"""
import argparse
import os
import sqlite3
import sys
import urllib.request
import zipfile

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUESTRA = os.path.join(RAIZ, "resultados", "muestra", "muestra_representantes.csv")
DESCARGAS = os.path.join(RAIZ, "data", "descargas")
BASES = os.path.join(RAIZ, "data", "bases")

URL_BIRD = "https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip"
ID_DRIVE_SPIDER = "1_AckYkinAnhqmRQtGsQgUKAnTHxxX5J0"
# Respaldo si Google Drive no deja descargar: copia de las bases de Spider en Hugging Face
URL_SPIDER_HF = "https://huggingface.co/datasets/HAL-9001/spider-databases/resolve/main/spider_data.zip"
PAGINAS = {"bird": "https://github.com/bird-bench/mini_dev",
           "spider": "https://yale-lily.github.io/spider"}


def descargar(benchmark):
    nombre = "minidev.zip" if benchmark == "bird" else "spider.zip"
    destino = os.path.join(DESCARGAS, nombre)
    if os.path.exists(destino) and zipfile.is_zipfile(destino):
        print(f"[{benchmark}] Ya está descargado: {destino}")
        return destino
    os.makedirs(DESCARGAS, exist_ok=True)
    print(f"[{benchmark}] Descargando {nombre} (puede tardar varios minutos)...")
    def avance(bloques, tam, total):
        if total > 0 and bloques % 200 == 0:
            print(f"\r  {min(100, bloques * tam * 100 // total)}%", end="", flush=True)

    try:
        if benchmark == "bird":
            urllib.request.urlretrieve(URL_BIRD, destino, avance)
            print()
        else:
            try:
                import gdown
                gdown.download(id=ID_DRIVE_SPIDER, output=destino, quiet=False)
                if not zipfile.is_zipfile(destino):
                    raise RuntimeError("Google Drive no entregó el zip")
            except Exception as e:
                print(f"[spider] Google Drive no dejó descargar ({str(e).splitlines()[0]}).")
                print("[spider] Pruebo la copia de Hugging Face...")
                urllib.request.urlretrieve(URL_SPIDER_HF, destino, avance)
                print()
    except Exception as e:
        sys.exit(f"[{benchmark}] No se pudo descargar ({e}).\n"
                 f"Bájalo a mano desde {PAGINAS[benchmark]} y guárdalo como {destino}")
    if not zipfile.is_zipfile(destino):
        sys.exit(f"[{benchmark}] El archivo descargado no es un zip válido. Bájalo a mano desde "
                 f"{PAGINAS[benchmark]} y guárdalo como {destino}")
    return destino


def buscar_en_zip(z, db_id):
    """Ruta de <db_id>/<db_id>.sqlite dentro del zip (evitando test_database de Spider)."""
    sufijo = f"/{db_id}/{db_id}.sqlite"
    rutas = [n for n in z.namelist() if ("/" + n).endswith(sufijo)]
    rutas.sort(key=lambda n: ("test_database" in n, len(n)))
    return rutas[0] if rutas else None


def extraer(zip_path, benchmark, db_ids):
    faltan = []
    with zipfile.ZipFile(zip_path) as z:
        internos = [n for n in z.namelist() if n.endswith(".zip")]  # minidev trae zips dentro
        for db in db_ids:
            destino = os.path.join(BASES, benchmark, db, f"{db}.sqlite")
            if os.path.exists(destino):
                continue
            ruta = buscar_en_zip(z, db)
            fuente = z
            if not ruta:
                for interno in internos:
                    zi = zipfile.ZipFile(z.open(interno))
                    ruta = buscar_en_zip(zi, db)
                    if ruta:
                        fuente = zi
                        break
            if not ruta:
                faltan.append(db)
                continue
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with fuente.open(ruta) as src, open(destino, "wb") as dst:
                while bloque := src.read(1 << 20):
                    dst.write(bloque)
            print(f"[{benchmark}] Extraída: {db}")
    if faltan:
        print(f"[{benchmark}] No encontré en el zip: {', '.join(faltan)}")


def verificar(muestra):
    print("\nComprobando que el SQL correcto se ejecuta en cada base:")
    ok = 0
    for _, r in muestra.iterrows():
        ruta = os.path.join(BASES, r.benchmark, r.db_id, f"{r.db_id}.sqlite")
        if not os.path.exists(ruta):
            print(f"  {r.grupo} {r.benchmark:6} {r.db_id:22} FALTA LA BASE")
            continue
        try:
            con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
            filas = con.execute(r.sql).fetchall()
            con.close()
            print(f"  {r.grupo} {r.benchmark:6} {r.db_id:22} OK ({len(filas)} filas)")
            ok += 1
        except Exception as e:
            print(f"  {r.grupo} {r.benchmark:6} {r.db_id:22} ERROR: {e}")
    print(f"\n{ok} de {len(muestra)} consultas se ejecutan correctamente.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--grupos", nargs="*", help="Solo estos grupos (por ejemplo: G1 G2)")
    args = p.parse_args()
    muestra = pd.read_csv(MUESTRA)
    if args.grupos:
        muestra = muestra[muestra.grupo.isin(args.grupos)]
    for benchmark in ["bird", "spider"]:
        dbs = sorted(muestra[muestra.benchmark == benchmark].db_id.unique())
        if not dbs:
            continue
        print(f"\n[{benchmark}] Bases necesarias: {', '.join(dbs)}")
        extraer(descargar(benchmark), benchmark, dbs)
    verificar(muestra)


if __name__ == "__main__":
    main()
