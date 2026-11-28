"""
¿Por qué k-means no reproduce los niveles? Análisis del ARI.

Lee consultas_con_caracteristicas.csv (salida de caracterizar_dificultad.py) y revisa:
1. Qué tipo de consultas cae en cada grupo de k-means y de qué nivel son.
2. Si el ARI cambia con otro número de grupos, con logaritmo o con menos características.
3. Referencias para leer el ARI: el de cortar solo por longitud y el de las predicciones
   del bosque aleatorio (supervisado).

Uso:
  python src/analisis_ari.py resultados/bird/consultas_con_caracteristicas.csv resultados/bird
"""
import json, os, sys
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import adjusted_rand_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

NO_CARACTERISTICAS = {"benchmark", "id", "db_id", "pregunta", "evidencia", "sql", "nivel"}


def kmeans(Z, k):
    return KMeans(n_clusters=k, n_init=20, random_state=0).fit_predict(Z)


def describir(centro):
    """Nombre corto de un grupo según sus promedios."""
    if centro["aritmetica"] > 1 or centro["case_when"] > 1:
        return "Con cálculos (CASE/IIF, aritmética)"
    if centro["group_by"] > 0.5:
        return "Con GROUP BY"
    if centro["order_by"] > 0.5:
        return "Con ORDER BY y LIMIT (máximos y mínimos)"
    if centro["profundidad_anidamiento"] > 0.5:
        return "Con subconsulta"
    if centro["operaciones_conjunto"] > 0.3:
        return "Con UNION/INTERSECT/EXCEPT"
    return "Filtros y JOINs, sin agrupar, ordenar ni calcular"


def main(ruta, salida):
    df = pd.read_csv(ruta)
    feats = [c for c in df.columns if c not in NO_CARACTERISTICAS]
    X, y = df[feats].astype(float), df["nivel"]
    k = y.nunique()
    Z = StandardScaler().fit_transform(X)
    grupos = kmeans(Z, k)

    # 1. Composición de cada grupo
    medias = df.groupby(grupos)[feats].mean()
    nombres = {}
    for g in medias.index:  # nombres únicos aunque dos grupos se describan igual
        n = describir(medias.loc[g])
        nombres[g] = n if n not in nombres.values() else f"{n} ({g + 1})"
    tabla = pd.crosstab(pd.Series(grupos).map(nombres).rename("grupo_kmeans"), y)
    tabla["total"] = tabla.sum(axis=1)
    tabla.to_csv(os.path.join(salida, "kmeans_grupos_vs_niveles.csv"))
    medias.rename(index=nombres).round(2).T.to_csv(os.path.join(salida, "kmeans_promedios_por_grupo.csv"))

    # 2. Robustez del ARI
    robustez = {f"k={kk}": round(adjusted_rand_score(y, kmeans(Z, kk)), 3) for kk in range(2, 9)}
    robustez["logaritmo"] = round(adjusted_rand_score(
        y, kmeans(StandardScaler().fit_transform(np.log1p(X)), k)), 3)
    ruta_imp = os.path.join(salida, "importancia_caracteristicas.csv")  # de caracterizar_dificultad.py
    top = (list(pd.read_csv(ruta_imp, index_col=0).index[:7]) if os.path.exists(ruta_imp) else
           ["longitud_tokens", "funciones", "condiciones_where", "aritmetica", "tablas", "joins", "case_when"])
    robustez["solo_7_mas_importantes"] = round(adjusted_rand_score(
        y, kmeans(StandardScaler().fit_transform(X[top]), k)), 3)

    # 3. Referencias
    terciles = pd.qcut(X["longitud_tokens"].rank(method="first"), k, labels=False)
    pred = cross_val_predict(RandomForestClassifier(n_estimators=300, random_state=0), X, y,
                             cv=StratifiedKFold(5, shuffle=True, random_state=0))
    res = {
        "ari_kmeans": round(adjusted_rand_score(y, grupos), 3),
        "robustez": robustez,
        "ari_cortar_solo_por_longitud": round(adjusted_rand_score(y, terciles), 3),
        "ari_predicciones_bosque": round(adjusted_rand_score(y, pred), 3),
        "exactitud_bosque": round(float((pred == y).mean()), 3),
        "caracteristicas_casi_constantes": [f for f in feats if (X[f] == X[f].mode()[0]).mean() > 0.95],
    }
    json.dump(res, open(os.path.join(salida, "analisis_ari.json"), "w"), indent=2, ensure_ascii=False)
    print(tabla.to_string()); print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
