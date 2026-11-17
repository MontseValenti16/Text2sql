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
`consultas_con_caracteristicas.csv` (pregunta, SQL y características de cada consulta) y
`resumen_pregunta_por_nivel.csv` (longitud de la pregunta y la evidencia por nivel).

## Resultados con Spider (546 consultas únicas de desarrollo)

| Característica | Fácil | Medio | Difícil | Extra |
|---|---|---|---|---|
| Consultas | 130 | 233 | 90 | 93 |
| Con JOIN | 3% | 41% | 39% | 87% |
| JOINs (máx.) | 2 | 2 | 2 | 4 |
| Con subconsulta | 2% | 0% | 22% | 26% |
| Anidamiento (máx.) | 1 | 0 | 1 | 1 |
| Con UNION/INTERSECT/EXCEPT | 1% | 0% | 26% | 22% |
| Con GROUP BY | 8% | 29% | 22% | 45% |
| Con CASE/IIF | 0% | 0% | 0% | 0% |
| Funciones (prom.) | 0.00 | 0.10 | 0.12 | 0.20 |
| Con aritmética | 0% | 0% | 0% | 0% |
| Longitud del SQL (prom., palabras) | 8 | 14 | 18 | 29 |

- Las consultas fáciles casi no tienen JOIN; en extra difícil, el 87% lo tiene.
- Medio y difícil tienen casi el mismo porcentaje de JOIN: lo que separa a difícil son
  las subconsultas y las operaciones de conjunto.
- Spider no tiene CASE/IIF ni aritmética en ninguna consulta, y casi no usa funciones:
  los cálculos, que en BIRD son lo que más distingue los niveles, aquí no existen.
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

| Característica | Simple | Moderado | Desafiante |
|---|---|---|---|
| Consultas | 148 | 250 | 102 |
| Con JOIN | 60% | 88% | 95% |
| JOINs (máx.) | 3 | 3 | 5 |
| Con subconsulta | 8% | 10% | 25% |
| Anidamiento (máx.) | 2 | 3 | 2 |
| Con UNION/INTERSECT/EXCEPT | 0% | 0.4% | 1% |
| Con GROUP BY | 3% | 9% | 10% |
| Con CASE/IIF | 7% | 14% | 41% |
| Funciones (prom.) | 0.58 | 1.21 | 2.54 |
| Con aritmética | 10% | 24% | 58% |
| Longitud del SQL (prom., palabras) | 20 | 30 | 44 |

- Bosque aleatorio con el SQL: **68.0%** (árbol: 70.2%), frente a 50% de la clase más
  común. Mucho menos que en Spider: los expertos no siguen una regla fija.
- Lo que más pesa es la longitud del SQL (0.35), luego funciones, condiciones en WHERE y
  aritmética. Los JOINs pesan poco porque casi todas las consultas de BIRD tienen alguno.
- En BIRD la dificultad viene más de los **cálculos** (CASE/IIF, funciones, porcentajes)
  que de los JOINs. BIRD sí llega a 5 JOINs y a 3 niveles de subconsulta.
- k-means: ARI = 0.07. El ARI vale 0 cuando los grupos coinciden con los niveles igual
  que si fueran al azar y 1 cuando coinciden por completo, así que 0.07 es prácticamente
  aleatorio: sin conocer los niveles, las consultas no se agrupan como los expertos las
  clasificaron.

### El enunciado: pregunta y evidencia

En BIRD cada pregunta viene con una **evidencia** (*evidence*): una nota escrita por los
anotadores con el conocimiento externo necesario para responderla, por ejemplo qué
significa un valor o cómo se calcula un porcentaje. Por ejemplo, para *"Calculate the
percentage of superheroes with blue eyes"* la evidencia es
`percentage = MULTIPLY(DIVIDE(SUM(superhero_name WHERE color = 'Blue'), COUNT(superhero_name)), 100.0); blue eyes refers to color = 'Blue' and color.id = eye_colour_id = 7;`
La herramienta recibe la pregunta y la evidencia. Spider no tiene evidencia.

Para medir cuánto pesa entender el enunciado, se mide la pregunta y la evidencia en
palabras, en frases (separadas por `.`, `?`, `!` o `;`) y en palabras por frase
(`resumen_pregunta_por_nivel.csv`):

| Medida (promedio) | Simple | Moderado | Desafiante |
|---|---|---|---|
| Palabras de la pregunta | 11.8 | 17.0 | 18.8 |
| Frases de la pregunta | 1.12 | 1.18 | 1.13 |
| Palabras por frase (pregunta) | 10.9 | 15.2 | 17.2 |
| Palabras de la evidencia | 13.0 | 19.8 | 27.9 |
| Frases de la evidencia | 1.66 | 2.25 | 2.84 |
| Palabras por frase (evidencia) | 8.0 | 9.4 | 10.1 |

| Bosque aleatorio entrenado con | Spider | BIRD |
|---|---|---|
| Solo el SQL | 94.5% | 68.0% |
| Solo el enunciado, en palabras | 49.3% | 61.2% |
| Solo el enunciado, en frases | 42.7% | 56.8% |
| Solo el enunciado, en palabras por frase | 46.7% | 51.0% |
| Solo el enunciado, las tres medidas | 49.3% | 63.0% |
| SQL y enunciado | 94.7% | 77.6% |
| Clase más común (referencia) | 42.7% | 50.0% |

- Contar palabras es la mejor medida. Las frases dicen poco de la pregunta, que casi
  siempre es una sola frase; en la evidencia sí crecen (de 1.7 a 2.8), porque las
  preguntas difíciles necesitan más datos de contexto.
- En Spider el enunciado casi no aporta (49% frente a 43% de la referencia) y sumarlo al
  SQL no cambia nada. En BIRD aporta: con el SQL solo se llega a 68% y con el SQL y el
  enunciado a 77.6%. Los expertos de BIRD tuvieron en cuenta qué tan difícil es entender
  la pregunta y el conocimiento externo, no solo el SQL.
- La longitud es una medida indirecta: dice cuánto hay que leer, no qué tan ambiguo es
  el texto.

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

La muestra (`resultados/muestra/muestra_representantes.csv`, semilla 2026) tiene 23
consultas. En cada grupo:

1. Se toman 3 consultas: 2 de BIRD y 1 de Spider. En G1 se toman 2: 1 de cada benchmark.
2. Dentro de cada benchmark, las consultas del grupo se separan por el nivel que les
   da el benchmark (en BIRD: simple, moderado, desafiante).
3. La primera consulta de BIRD sale al azar del nivel más alto que haya en el grupo; la
   segunda, del siguiente nivel hacia abajo. Así las dos de BIRD son de niveles
   distintos. De Spider solo se toma una, del nivel más alto que haya en el grupo.
4. En G1, el grupo de control, se hace al revés: se empieza por el nivel más bajo, para
   tener consultas fáciles que comprueben que cada herramienta funciona.
5. Si un benchmark no tiene suficientes consultas en el grupo, se completa con
   consultas del otro (en G7 solo hay 1 de BIRD, así que se tomaron 2 de Spider).

Huecos: G3 y G8 tienen muy pocas consultas, G7 casi no existe en BIRD, y ningún
benchmark pasa de 5 JOINs ni de 3 niveles de subconsulta. Para encontrar el límite de
las herramientas habrá que **inventar consultas** con más JOINs y más anidamiento.

## Datos y créditos

- Spider: Yu et al. (2018), https://yale-lily.github.io/spider ·
  regla de niveles en https://github.com/taoyds/spider (licencia CC BY-SA 4.0).
- BIRD: Li et al. (2023), https://bird-bench.github.io/
