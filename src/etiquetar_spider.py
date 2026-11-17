"""
Calcula el nivel de dificultad oficial de cada consulta de desarrollo de Spider.

Descarga del repositorio oficial de Spider (https://github.com/taoyds/spider) el
programa de evaluación (evaluation.py y process_sql.py), las consultas correctas
de desarrollo y el esquema de las bases de datos, y aplica la regla de Spider
(eval_hardness) a cada consulta.

Uso (desde la carpeta del proyecto):
  python src/etiquetar_spider.py data/spider_dev_con_niveles.json
"""
import collections, json, os, sys, urllib.request

BASE = "https://raw.githubusercontent.com/taoyds"
ARCHIVOS = {
    "evaluation.py": f"{BASE}/spider/master/evaluation.py",
    "process_sql.py": f"{BASE}/spider/master/process_sql.py",
    "gold_dev.txt": f"{BASE}/spider/master/evaluation_examples/gold_example.txt",
    "tables.json": f"{BASE}/test-suite-sql-eval/master/tables.json",
    "dev.json": f"{BASE}/spider/master/evaluation_examples/examples/dev.json",
}
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "spider_oficial")


def descargar():
    os.makedirs(CACHE, exist_ok=True)
    for nombre, url in ARCHIVOS.items():
        destino = os.path.join(CACHE, nombre)
        if not os.path.exists(destino):
            print("Descargando", nombre)
            urllib.request.urlretrieve(url, destino)


def main(salida):
    descargar()
    import nltk
    for recurso in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{recurso}")
        except LookupError:
            nltk.download(recurso, quiet=True)
    sys.path.insert(0, CACHE)
    from process_sql import Schema, get_sql
    import evaluation

    tablas = {t["db_id"]: t for t in json.load(open(os.path.join(CACHE, "tables.json")))}
    evaluador = evaluation.Evaluator()
    preguntas = [d["question"] for d in json.load(open(os.path.join(CACHE, "dev.json"), encoding="utf-8"))]
    salida_datos, fallos = [], 0
    for i, linea in enumerate(open(os.path.join(CACHE, "gold_dev.txt"), encoding="utf-8")):
        consulta, db = linea.rstrip("\n").split("\t")
        t = tablas[db]
        esquema = {nombre.lower(): [c[1].lower() for c in t["column_names_original"] if c[0] == i]
                   for i, nombre in enumerate(t["table_names_original"])}
        try:
            nivel = evaluador.eval_hardness(get_sql(Schema(esquema), consulta))
        except Exception:
            nivel, fallos = None, fallos + 1
        salida_datos.append({"db_id": db, "question": preguntas[i], "query": consulta, "hardness": nivel})
    json.dump(salida_datos, open(salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("Consultas:", len(salida_datos), "sin analizar:", fallos)
    print(collections.Counter(d["hardness"] for d in salida_datos))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/spider_dev_con_niveles.json")
