# Caracterización de la dificultad en benchmarks Text-to-SQL

Proyecto 4 · Estudio comparativo de herramientas Text2SQL
Alicia Montserrat Valenti Ruiz · Ingeniería en Software, Universidad Politécnica de Chiapas

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
src/muestreo_estratificado.py   Grupos de dificultad y muestra de consultas representantes
data/spider_dev_con_niveles.json  Consultas de desarrollo de Spider con su nivel
resultados/spider/               Resultados del análisis de Spider
resultados/bird/                 Resultados del análisis de BIRD (Mini-Dev)
resultados/muestra/              Grupos y consultas representantes (Spider + BIRD)
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

# BIRD Mini-Dev (500 preguntas oficiales): descargar mini_dev_prompt.jsonl de
# https://github.com/bird-bench/mini_dev y guardarlo en data/bird/
python src/caracterizar_dificultad.py bird data/bird/mini_dev_prompt.jsonl resultados/bird

# Grupos y muestra estratificada (usa la salida de los dos análisis anteriores)
python src/muestreo_estratificado.py resultados/spider/consultas_con_caracteristicas.csv \
    resultados/bird/consultas_con_caracteristicas.csv resultados/muestra
```

Cada ejecución genera en la carpeta de resultados: `caracteristicas.csv`,
`resumen_por_nivel.csv`, `matriz_confusion.csv`, `importancia_caracteristicas.csv`,
`reglas_arbol.txt`, `resultados.json`, `importancia.png`, `clustering.png` y
`consultas_con_caracteristicas.csv` (pregunta, SQL y características de cada consulta).

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
- Bosque aleatorio: **94.5%** de exactitud (árbol de profundidad 4: 75.6%), frente a
  42.7% de predecir siempre la clase más común.
- k-means: ARI = 0.19; los grupos naturales se parecen poco a los niveles.

En Spider el nivel viene de una regla automática (`eval_hardness` en `evaluation.py`),
así que era de esperar que el modelo la aprendiera: el resultado valida el método. La
prueba real es BIRD, donde el nivel lo asignan expertos.

(Antes se reportó 94.3%; al añadir CASE/IIF, funciones y aritmética como características
pasó a 94.5%. La diferencia no es significativa.)

## Resultados con BIRD (Mini-Dev, 500 consultas únicas)

| | Simple | Moderado | Desafiante |
|---|---|---|---|
| Consultas | 148 | 250 | 102 |
| Con JOIN | 60% | 88% | 95% |
| JOINs (máx.) | 3 | 3 | 5 |
| Con subconsulta | 8% | 10% | 25% |
| Con CASE/IIF | 7% | 14% | 41% |
| Funciones (prom.) | 0.58 | 1.21 | 2.54 |
| Con aritmética | 10% | 24% | 58% |
| Longitud del SQL (prom., palabras) | 20 | 30 | 44 |

- Bosque aleatorio con el SQL: **68.0%** (árbol: 70.2%), frente a 50% de la clase más
  común. Mucho menos que en Spider: los expertos no siguen una regla fija.
- Con el SQL **y** la pregunta y la evidencia: **77.6%**. Solo con la pregunta: 61.2%.
  En Spider la pregunta sola da 49.4%. En BIRD la dificultad también está en entender la
  pregunta y el conocimiento externo, no solo en el SQL.
- Lo que más pesa es la longitud del SQL (0.35), luego funciones, condiciones en WHERE y
  aritmética. Los JOINs pesan poco porque casi todas las consultas de BIRD tienen alguno.
- En BIRD la dificultad viene más de los **cálculos** (CASE/IIF, funciones, porcentajes)
  que de los JOINs. BIRD sí llega a 5 JOINs y a 3 niveles de subconsulta.
- k-means: ARI = 0.07.

## Grupos de dificultad y muestra estratificada

Cada consulta se asigna al primer grupo que cumple, en este orden (G8 primero):

| Grupo | Qué la hace difícil | Spider | BIRD | % Spider difícil/extra | % BIRD desafiante |
|---|---|---|---|---|---|
| G1 | Una tabla, nada más (control) | 265 | 26 | 7.5 | 7.7 |
| G2 | 1 o 2 JOINs | 154 | 103 | 39.6 | 7.8 |
| G3 | 3 JOINs | 1 | 5 | 100 | 20.0 |
| G4 | Cálculos (aritmética, CASE/IIF, funciones) | 38 | 302 | 39.5 | 21.9 |
| G5 | Subconsulta sin JOIN | 28 | 16 | 100 | 12.5 |
| G6 | Subconsulta y JOIN | 15 | 39 | 93.3 | 48.7 |
| G7 | UNION / INTERSECT / EXCEPT | 41 | 1 | 97.6 | 0 |
| G8 | Extremos: 4+ JOINs o 2+ niveles de subconsulta | 4 | 8 | 100 | 50.0 |

La muestra (`resultados/muestra/muestra_representantes.csv`, semilla 2026) toma 3
consultas por grupo (2 en G1): dos de BIRD y una de Spider, empezando por el nivel más
difícil y cambiando de nivel cuando se puede. En G1 se toman las más fáciles, para
comprobar que cada herramienta funciona. Total: 23 consultas.

Huecos: G3 y G8 tienen muy pocas consultas, G7 casi no existe en BIRD, y ningún
benchmark pasa de 5 JOINs ni de 3 niveles de subconsulta. Para encontrar el límite de
las herramientas habrá que **inventar consultas** con más JOINs y más anidamiento.

## Datos y créditos

- Spider: Yu et al. (2018), https://yale-lily.github.io/spider ·
  regla de niveles en https://github.com/taoyds/spider (licencia CC BY-SA 4.0).
- BIRD: Li et al. (2023), https://bird-bench.github.io/
