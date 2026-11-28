"""
Amplía la muestra de 3 a 10 consultas por grupo (8 grupos x 10 = 80).

- Conserva las 24 consultas de muestra_representantes.csv, que ya se probaron con las
  herramientas, y agrega 7 por grupo.
- Usa la misma regla que muestreo_estratificado.py: dentro de cada grupo y benchmark, las
  consultas se barajan con la misma semilla y se toman por turnos de cada nivel, del más alto
  al más bajo (en G1, el grupo de control, del más bajo al más alto).
- Cuota por grupo: 5 de BIRD y 5 de Spider. Si un benchmark no tiene suficientes consultas
  en el grupo, se completa con el otro.
- Si el grupo no tiene 10 consultas entre los dos benchmarks (G3 solo tiene 6), se completa
  con consultas inventadas (resultados/muestra/consultas_inventadas.csv), sobre bases de
  Spider o BIRD. Para cada una se comprueba que el SQL se ejecuta y que, con las mismas
  reglas, cae en ese grupo.

Uso (desde la carpeta del proyecto):
  python src/ampliar_muestra.py
Genera resultados/muestra/muestra_ampliada.csv y .json.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caracterizar_dificultad import caracteristicas  # noqa: E402
from muestreo_estratificado import GRUPOS, ORDEN_NIVEL, SEMILLA, asignar  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "resultados", "muestra")
POR_GRUPO = 10
CUOTA = {"bird": 5, "spider": 5}
COLUMNAS = ["grupo", "nombre_grupo", "benchmark", "origen", "id", "db_id", "nivel", "pregunta",
            "evidencia", "sql", "joins", "profundidad_anidamiento", "operaciones_conjunto",
            "agregaciones", "group_by", "case_when", "funciones", "aritmetica", "longitud_tokens"]


def orden_candidatos(sub, gid):
    """Consultas del grupo en el orden en que las tomaría el muestreo estratificado."""
    cand = sub.sample(frac=1, random_state=SEMILLA)
    signo = 1 if gid == "G1" else -1
    por_nivel = [list(g.id) for _, g in sorted(cand.groupby("nivel_relativo"), key=lambda x: signo * x[0])]
    orden = []
    while any(por_nivel):
        for lista in por_nivel:
            if lista:
                orden.append(lista.pop(0))
    return orden


def inventadas():
    ruta = os.path.join(CARPETA, "consultas_inventadas.csv")
    if not os.path.exists(ruta):
        return pd.DataFrame()
    inv = pd.read_csv(ruta).fillna("")
    filas = []
    for _, r in inv.iterrows():
        fila = {**r.to_dict(), **caracteristicas(r.sql)}
        grupo = asignar(pd.Series(fila))
        if grupo != r.grupo:
            sys.exit(f"La consulta inventada {r.id} cae en {grupo}, no en {r.grupo}")
        filas.append(fila)
    return pd.DataFrame(filas)


def main():
    todas = pd.read_csv(os.path.join(CARPETA, "consultas_con_grupo.csv")).fillna("")
    actual = pd.read_csv(os.path.join(CARPETA, "muestra_representantes.csv")).fillna("")
    inv = inventadas()
    nombres = {g: n for g, n, _, _ in GRUPOS}
    elegidas = []
    for gid in sorted(nombres):
        sub = todas[todas.grupo == gid]
        ordenes = {b: orden_candidatos(sub[sub.benchmark == b], gid) for b in CUOTA}
        ids = list(actual[actual.grupo == gid].id)  # las que ya se probaron van primero
        for bench, k in CUOTA.items():
            for i in ordenes[bench]:
                if sum(1 for x in ids if x.startswith(bench)) >= k:
                    break
                if i not in ids:
                    ids.append(i)
        for bench in CUOTA:  # completar con el otro benchmark
            for i in ordenes[bench]:
                if len(ids) >= POR_GRUPO:
                    break
                if i not in ids:
                    ids.append(i)
        filas = [todas[todas.id == i].iloc[0].to_dict() for i in ids]
        for f in filas:
            f["origen"] = "benchmark"
        faltan = POR_GRUPO - len(filas)
        if faltan > 0:
            propias = inv[inv.grupo == gid] if len(inv) else inv
            if len(propias) < faltan:
                sys.exit(f"{gid}: faltan {faltan} consultas y solo hay {len(propias)} inventadas")
            for _, r in propias.head(faltan).iterrows():
                filas.append({**r.to_dict(), "origen": "inventada", "nivel": "inventada"})
        for f in filas:
            f["grupo"], f["nombre_grupo"] = gid, nombres[gid]
        elegidas += filas
    m = pd.DataFrame(elegidas)[COLUMNAS].fillna("")
    m.to_csv(os.path.join(CARPETA, "muestra_ampliada.csv"), index=False)
    m.to_json(os.path.join(CARPETA, "muestra_ampliada.json"), orient="records",
              force_ascii=False, indent=1)
    print(pd.crosstab(m.grupo, [m.benchmark, m.origen]))
    print(f"\n{len(m)} consultas en resultados/muestra/muestra_ampliada.csv")


if __name__ == "__main__":
    main()
