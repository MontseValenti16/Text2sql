"""
Grupos de dificultad y muestreo estratificado de consultas representantes.

1. Junta las consultas de Spider y BIRD con sus características (salida de
   caracterizar_dificultad.py: consultas_con_caracteristicas.csv).
2. Asigna cada consulta a un grupo según lo que la vuelve difícil (JOINs,
   subconsultas, operaciones de conjunto, cálculos), más fino que los niveles.
3. Resume cada grupo: cuántas consultas tiene en cada benchmark y en qué niveles caen.
4. Elige representantes con un muestreo estratificado: 3 consultas por grupo
   (8 grupos x 3 = 24). En cada grupo, 2 de BIRD y 1 de Spider:
   - BIRD: una al azar del nivel más alto que tenga el grupo y otra del siguiente nivel
     hacia abajo, así las dos son de niveles distintos.
   - Spider: una al azar del nivel más alto que tenga el grupo.
   - G1 (control) se recorre al revés: se empieza por el nivel más bajo.
   - Si un benchmark no tiene suficientes consultas en el grupo, se completa con el otro.
   «Nivel» es el que asigna el benchmark; «grupo» es el nuestro (G1 a G8).

Uso (desde la carpeta del proyecto):
  python src/muestreo_estratificado.py resultados/spider/consultas_con_caracteristicas.csv \
      resultados/bird/consultas_con_caracteristicas.csv resultados/muestra
"""
import json, os, sys
import pandas as pd

SEMILLA = 2026

# Orden de prioridad: una consulta va al primer grupo cuya condición cumple.
GRUPOS = [
    ("G8", "Extremos: 4 o más JOINs, o 2 o más niveles de subconsulta",
     lambda r: r.joins >= 4 or r.profundidad_anidamiento >= 2, 3),
    ("G7", "Operaciones de conjunto (UNION, INTERSECT, EXCEPT)",
     lambda r: r.operaciones_conjunto > 0, 3),
    ("G6", "Subconsulta y JOIN",
     lambda r: r.profundidad_anidamiento >= 1 and r.joins > 0, 3),
    ("G5", "Subconsulta sin JOIN",
     lambda r: r.profundidad_anidamiento >= 1 and r.joins == 0, 3),
    ("G4", "Cálculos (aritmética, CASE/IIF o funciones) sin subconsulta",
     lambda r: r.aritmetica > 0 or r["case_when"] > 0 or r.funciones > 0, 3),
    ("G3", "3 JOINs, sin subconsulta ni cálculos",
     lambda r: r.joins == 3, 3),
    ("G2", "1 o 2 JOINs, sin subconsulta ni cálculos",
     lambda r: r.joins in (1, 2), 3),
    ("G1", "Una tabla, sin subconsulta ni cálculos (control)",
     lambda r: True, 3),
]
ORDEN_NIVEL = {"easy": 1, "medium": 2, "hard": 3, "extra": 4, "simple": 1, "moderate": 2, "challenging": 3}
NOMBRE_NIVEL = {"easy": "Spider fácil", "medium": "Spider medio", "hard": "Spider difícil", "extra": "Spider extra",
                "simple": "BIRD simple", "moderate": "BIRD moderado", "challenging": "BIRD desafiante"}


def asignar(r):
    for gid, nombre, cond, _ in GRUPOS:
        if cond(r):
            return gid
    return "G1"


def main(rutas, salida):
    os.makedirs(salida, exist_ok=True)
    df = pd.concat([pd.read_csv(r) for r in rutas], ignore_index=True)
    df["grupo"] = df.apply(asignar, axis=1)
    nombres = {g: n for g, n, _, _ in GRUPOS}
    df["nombre_grupo"] = df["grupo"].map(nombres)
    df["nivel_relativo"] = df["nivel"].map(ORDEN_NIVEL)
    df.to_csv(os.path.join(salida, "consultas_con_grupo.csv"), index=False)

    # Resumen de grupos: tamaño por benchmark y distribución de niveles
    filas = []
    for gid, nombre, _, _ in sorted(GRUPOS, key=lambda g: g[0]):
        sub = df[df.grupo == gid]
        fila = {"grupo": gid, "descripcion": nombre, "spider": int((sub.benchmark == "spider").sum()),
                "bird": int((sub.benchmark == "bird").sum())}
        for niv in ["easy", "medium", "hard", "extra", "simple", "moderate", "challenging"]:
            fila[NOMBRE_NIVEL[niv]] = int((sub.nivel == niv).sum())
        sp = sub[sub.benchmark == "spider"]; bi = sub[sub.benchmark == "bird"]
        fila["% Spider difícil o extra"] = round(100 * sp.nivel.isin(["hard", "extra"]).mean(), 1) if len(sp) else None
        fila["% BIRD desafiante"] = round(100 * (bi.nivel == "challenging").mean(), 1) if len(bi) else None
        filas.append(fila)
    resumen = pd.DataFrame(filas)
    resumen.to_csv(os.path.join(salida, "resumen_grupos.csv"), index=False)

    # Muestreo estratificado: n por grupo; se reparte entre benchmarks y, dentro de cada
    # benchmark, se toman niveles distintos cuando los hay.
    muestra = []
    for gid, nombre, _, n in sorted(GRUPOS, key=lambda g: g[0]):
        sub = df[df.grupo == gid]
        elegidas = []
        cuotas = {"bird": 2, "spider": 1}  # 3 por grupo: 2 de BIRD (de niveles distintos) y 1 de Spider
        for bench, k in cuotas.items():
            cand = sub[sub.benchmark == bench].sample(frac=1, random_state=SEMILLA)
            # una por nivel, de mayor a menor dificultad (en G1, el grupo de control, de menor
            # a mayor: ahí interesan consultas fáciles para comprobar que la herramienta funciona)
            signo = 1 if gid == "G1" else -1
            por_nivel = [g for _, g in sorted(cand.groupby("nivel_relativo"), key=lambda x: signo * x[0])]
            i = 0
            while len([e for e in elegidas if e["benchmark"] == bench]) < k and any(len(g) > 0 for g in por_nivel):
                g = por_nivel[i % len(por_nivel)]
                if len(g):
                    elegidas.append(g.iloc[0].to_dict()); por_nivel[i % len(por_nivel)] = g.iloc[1:]
                i += 1
        faltan = n - len(elegidas)
        if faltan > 0:  # completar con lo que haya en el grupo
            resto = sub[~sub.id.isin([e["id"] for e in elegidas])].sample(frac=1, random_state=SEMILLA).head(faltan)
            elegidas += [r.to_dict() for _, r in resto.iterrows()]
        for e in elegidas:
            muestra.append(e)
    cols = ["grupo", "nombre_grupo", "benchmark", "id", "db_id", "nivel", "pregunta", "evidencia", "sql",
            "joins", "profundidad_anidamiento", "operaciones_conjunto", "agregaciones", "group_by",
            "case_when", "funciones", "aritmetica", "longitud_tokens"]
    m = pd.DataFrame(muestra)[cols].fillna("")
    m.to_csv(os.path.join(salida, "muestra_representantes.csv"), index=False)
    m.to_json(os.path.join(salida, "muestra_representantes.json"), orient="records", force_ascii=False, indent=1)
    print(resumen.to_string(index=False))
    print(m[["grupo", "benchmark", "nivel", "joins", "profundidad_anidamiento", "pregunta"]].to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:-1], sys.argv[-1])
