# Caracterización de la dificultad en benchmarks Text-to-SQL

Proyecto 4 · Estudio comparativo de herramientas Text2SQL
Alicia Montserrat Valenti Ruiz · 

## Objetivo

Averiguar qué características de una consulta SQL la vuelven difícil (número de JOINs,
subconsultas, niveles de anidamiento, agregaciones, GROUP BY, etc.) a partir de los
niveles de dificultad que asignan los benchmarks.

## Método

1. **Características:** de cada consulta se extraen, con un analizador de SQL
   ([sqlglot](https://github.com/tobymao/sqlglot)), el número de tablas, JOINs,
   subconsultas, profundidad de anidamiento, UNION/INTERSECT/EXCEPT, agregaciones,
   GROUP BY, HAVING, condiciones en WHERE, OR, LIKE, ORDER BY, LIMIT, DISTINCT,
   columnas en SELECT, CASE, funciones, aritmética y longitud.
2. **Resumen por nivel:** promedio y porcentaje de cada característica en cada nivel.
3. **Supervisado:** un árbol de decisión y un bosque aleatorio predicen el nivel a partir
   de las características (validación cruzada de 5 particiones). Si predicen bien, la
   importancia de cada característica indica qué hace difícil una consulta.
4. **No supervisado:** k-means agrupa las consultas y se compara con los niveles reales
   (índice de Rand ajustado, ARI, y gráfica con colores).

Las consultas repetidas se eliminan antes de entrenar para que la misma consulta no
aparezca en entrenamiento y prueba.

## Estructura

```
src/etiquetar_spider.py         Calcula el nivel oficial de cada consulta de Spider
src/caracterizar_dificultad.py  Características, modelos y gráficas
data/spider_dev_con_niveles.json  Consultas de desarrollo de Spider con su nivel
resultados/spider/               Resultados del análisis de Spider
docs/                            Tabla de benchmarks contra dificultades y notas de lectura
```

## Cómo ejecutarlo

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Spider (los niveles ya están en data/; este paso es opcional)
python src/etiquetar_spider.py data/spider_dev_con_niveles.json
python src/caracterizar_dificultad.py spider data/spider_dev_con_niveles.json resultados/spider

# BIRD: descargar dev.json desde https://bird-bench.github.io/ y guardarlo en data/bird/
python src/caracterizar_dificultad.py bird data/bird/dev.json resultados/bird
```

Cada ejecución genera en la carpeta de resultados: `caracteristicas.csv`,
`resumen_por_nivel.csv`, `matriz_confusion.csv`, `importancia_caracteristicas.csv`,
`reglas_arbol.txt`, `resultados.json`, `importancia.png` y `clustering.png`.

## Resultados con Spider (546 consultas únicas de desarrollo)

| Nivel | Consultas | Con JOIN | JOINs (máx.) | Con subconsulta | Con UNION/INTERSECT/EXCEPT | Con GROUP BY |
|---|---|---|---|---|---|---|
| Fácil | 130 | 3% | 2 | 2% | 1% | 8% |
| Medio | 233 | 41% | 2 | 0% | 0% | 29% |
| Difícil | 90 | 39% | 2 | 22% | 26% | 22% |
| Extra | 93 | 87% | 4 | 26% | 22% | 45% |

- Las consultas fáciles casi no tienen JOIN; en extra difícil, el 87% lo tiene.
- Medio y difícil tienen casi el mismo porcentaje de JOIN: lo que separa a difícil son
  las subconsultas y las operaciones de conjunto.
- Spider no pasa de 4 JOINs ni de un nivel de subconsulta, así que no permite encontrar
  el límite de los modelos.
- Bosque aleatorio: **94.3%** de exactitud (árbol de profundidad 4: 75.6%), frente a
  42.7% de predecir siempre la clase más común.
- k-means: ARI = 0.19; los grupos naturales se parecen poco a los niveles.

En Spider el nivel viene de una regla automática (`eval_hardness` en `evaluation.py`),
así que era de esperar que el modelo la aprendiera: el resultado valida el método. 

## Datos y créditos

- Spider: Yu et al. (2018), https://yale-lily.github.io/spider ·
  regla de niveles en https://github.com/taoyds/spider (licencia CC BY-SA 4.0).
- BIRD: Li et al. (2023), https://bird-bench.github.io/
