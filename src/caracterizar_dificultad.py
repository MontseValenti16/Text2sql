
import json, os, sys
import numpy as np
import pandas as pd
import sqlglot
from sqlglot import exp
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, cross_val_predict, StratifiedKFold
from sklearn.metrics import confusion_matrix, adjusted_rand_score
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


def profundidad_anidamiento(node):
    """Niveles de SELECT anidados (0 = sin subconsultas; 1 = una subconsulta; 2 = una dentro de otra)."""
    def prof(n):
        hijos = [c for c in n.find_all(exp.Select) if c is not n and c.find_ancestor(exp.Select) is n]
        return 0 if not hijos else 1 + max(prof(c) for c in hijos)
    raiz = node if isinstance(node, exp.Select) else None
    if raiz is None:  # UNION / INTERSECT / EXCEPT: la profundidad mayor de sus partes
        partes = [c for c in node.find_all(exp.Select) if c.find_ancestor(exp.Select) is None]
        return max((prof(c) for c in partes), default=0)
    return prof(raiz)


def caracteristicas(sql):
    t = sqlglot.parse_one(sql, read="sqlite")
    selects = list(t.find_all(exp.Select))
    principal = t if isinstance(t, exp.Select) else (selects[0] if selects else t)
    where = principal.args.get("where")
    group = principal.args.get("group")
    n_cond_where = 0
    if where is not None:
        n_cond_where = len(list(where.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
                                               exp.Like, exp.In, exp.Between, exp.Is)))
    return {
        "tablas": len({tb.name.lower() for tb in t.find_all(exp.Table)}),
        "joins": len(list(t.find_all(exp.Join))),
        "subconsultas": max(len(selects) - 1 - len(list(t.find_all(exp.Union, exp.Intersect, exp.Except))), 0),
        "profundidad_anidamiento": profundidad_anidamiento(t),
        "operaciones_conjunto": len(list(t.find_all(exp.Union, exp.Intersect, exp.Except))),
        "agregaciones": len(list(t.find_all(*AGGS))),
        "tipos_agregacion": len({type(a).__name__ for a in t.find_all(*AGGS)}),
        "group_by": int(group is not None),
        "columnas_group_by": len(group.expressions) if group is not None else 0,
        "having": int(principal.args.get("having") is not None),
        "condiciones_where": n_cond_where,
        "or": len(list(t.find_all(exp.Or))),
        "like": len(list(t.find_all(exp.Like))),
        "order_by": int(principal.args.get("order") is not None),
        "limit": int(principal.args.get("limit") is not None),
        "distinct": len(list(t.find_all(exp.Distinct))),
        "columnas_select": len(principal.expressions),
        "case_when": len(list(t.find_all(exp.Case))),
        "funciones_fecha_texto": len(list(t.find_all(exp.Cast, exp.Substring, exp.StrToTime, exp.TimeToStr,
                                                       exp.Anonymous))),
        "aritmetica": len(list(t.find_all(exp.Add, exp.Sub, exp.Mul, exp.Div))),
        "longitud_tokens": len(sql.split()),
    }


def cargar(tipo, ruta):
    datos = json.load(open(ruta))
    if tipo == "spider":
        return [(d["query"], d["hardness"]) for d in datos], ["easy", "medium", "hard", "extra"]
    return [(d["SQL"], d["difficulty"]) for d in datos], ["simple", "moderate", "challenging"]


def main(tipo, ruta, salida):
    os.makedirs(salida, exist_ok=True)
    pares, orden = cargar(tipo, ruta)
    # Quitar consultas repetidas (en Spider varias preguntas comparten la misma SQL);
    # si no, la misma consulta cae en entrenamiento y prueba y la exactitud se infla.
    vistos, unicos = set(), []
    for sql, nivel in pares:
        clave = " ".join(sql.lower().split())
        if clave not in vistos:
            vistos.add(clave); unicos.append((sql, nivel))
    pares = unicos
    filas, fallos = [], 0
    for sql, nivel in pares:
        try:
            f = caracteristicas(sql)
            f["nivel"] = nivel
            filas.append(f)
        except Exception:
            fallos += 1
    df = pd.DataFrame(filas)
    df["nivel"] = pd.Categorical(df["nivel"], categories=orden, ordered=True)
    df.to_csv(os.path.join(salida, "caracteristicas.csv"), index=False)
    X = df.drop(columns="nivel")
    y = df["nivel"].astype(str)

    # 2. Resumen por nivel
    resumen = df.groupby("nivel", observed=True).agg(
        consultas=("joins", "size"),
        prom_joins=("joins", "mean"), max_joins=("joins", "max"),
        pct_con_join=("joins", lambda s: 100 * (s > 0).mean()),
        pct_subconsulta=("subconsultas", lambda s: 100 * (s > 0).mean()),
        max_anidamiento=("profundidad_anidamiento", "max"),
        pct_operacion_conjunto=("operaciones_conjunto", lambda s: 100 * (s > 0).mean()),
        pct_group_by=("group_by", lambda s: 100 * s.mean()),
        prom_agregaciones=("agregaciones", "mean"),
        prom_condiciones_where=("condiciones_where", "mean"),
        prom_longitud=("longitud_tokens", "mean"),
    ).round(2)
    resumen.to_csv(os.path.join(salida, "resumen_por_nivel.csv"))

    # 3. Supervisado
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    arbol = DecisionTreeClassifier(max_depth=4, random_state=0)
    bosque = RandomForestClassifier(n_estimators=300, random_state=0)
    acc_arbol = cross_val_score(arbol, X, y, cv=cv).mean()
    acc_bosque = cross_val_score(bosque, X, y, cv=cv).mean()
    pred = cross_val_predict(bosque, X, y, cv=cv)
    cm = pd.DataFrame(confusion_matrix(y, pred, labels=orden), index=orden, columns=orden)
    cm.to_csv(os.path.join(salida, "matriz_confusion.csv"))
    bosque.fit(X, y)
    imp = pd.Series(bosque.feature_importances_, index=X.columns).sort_values(ascending=False)
    imp.round(4).to_csv(os.path.join(salida, "importancia_caracteristicas.csv"), header=["importancia"])
    arbol.fit(X, y)
    reglas = export_text(arbol, feature_names=list(X.columns))
    open(os.path.join(salida, "reglas_arbol.txt"), "w").write(reglas)
    base = y.value_counts(normalize=True).max()

    # 4. No supervisado
    Z = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=len(orden), n_init=20, random_state=0).fit(Z)
    ari = adjusted_rand_score(y, km.labels_)
    P = PCA(n_components=2, random_state=0).fit_transform(Z)

    # Gráficas
    colores = ["#A8D5BA", "#2E9E6B", "#D9A21B", "#B5452E"][: len(orden)]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    imp.head(10)[::-1].plot.barh(ax=ax, color="#2E9E6B")
    ax.set_xlabel("Importancia en el bosque aleatorio")
    ax.set_title("Características que más explican el nivel")
    fig.tight_layout(); fig.savefig(os.path.join(salida, "importancia.png"), dpi=150); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharex=True, sharey=True)
    rng = np.random.default_rng(0)
    J = P + rng.normal(0, 0.04, P.shape)
    for nivel, c in zip(orden, colores):
        m = (y == nivel).values
        axes[0].scatter(J[m, 0], J[m, 1], s=10, color=c, label=nivel, alpha=0.7)
    axes[0].set_title("Coloreado por nivel real"); axes[0].legend()
    axes[1].scatter(J[:, 0], J[:, 1], s=10, c=km.labels_, cmap="viridis", alpha=0.7)
    axes[1].set_title(f"Grupos de k-means (ARI = {ari:.2f})")
    for a in axes: a.set_xlabel("Componente 1"); a.set_ylabel("Componente 2")
    fig.tight_layout(); fig.savefig(os.path.join(salida, "clustering.png"), dpi=150); plt.close(fig)

    res = {"consultas": len(df), "no_analizadas": fallos, "exactitud_arbol": round(acc_arbol, 3),
           "exactitud_bosque": round(acc_bosque, 3), "exactitud_base_clase_mayoritaria": round(base, 3),
           "ari_kmeans": round(ari, 3)}
    json.dump(res, open(os.path.join(salida, "resultados.json"), "w"), indent=2)
    print(json.dumps(res, indent=2)); print(resumen.to_string()); print(cm.to_string()); print(imp.round(3).head(10).to_string()); print(reglas)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
