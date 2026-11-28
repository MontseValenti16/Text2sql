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
src/ampliar_muestra.py          Amplía la muestra a 10 consultas por grupo (80)
src/analisis_ari.py             Por qué k-means no reproduce los niveles (análisis del ARI)
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
python src/ampliar_muestra.py   # muestra ampliada: 10 consultas por grupo

# Análisis del ARI (qué agrupa k-means y por qué no coincide con los niveles)
python src/analisis_ari.py resultados/bird/consultas_con_caracteristicas.csv resultados/bird
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
| Funciones (prom.) | 0.00 | 0.00 | 0.00 | 0.00 |
| Con aritmética | 0% | 0% | 0% | 0% |
| Longitud del SQL (prom., palabras) | 8 | 14 | 18 | 29 |

- Las consultas fáciles casi no tienen JOIN; en extra difícil, el 87% lo tiene.
- Medio y difícil tienen casi el mismo porcentaje de JOIN: lo que separa a difícil son
  las subconsultas y las operaciones de conjunto.
- Spider no tiene CASE/IIF, aritmética ni funciones en ninguna consulta:
  los cálculos, que en BIRD son lo que más distingue los niveles, aquí no existen.
- Spider no pasa de 4 JOINs ni de un nivel de subconsulta, así que no permite encontrar
  el límite de los modelos.
- Bosque aleatorio: **94.3%** de exactitud (árbol de profundidad 4: 75.6%), frente a
  42.7% de predecir siempre la clase más común.
- k-means: ARI = 0.19; los grupos naturales se parecen poco a los niveles.

En Spider el nivel viene de una regla automática (`eval_hardness` en `evaluation.py`),
así que era de esperar que el modelo la aprendiera: el resultado valida el método. La
prueba real es BIRD, donde el nivel lo asignan expertos.

(Con la corrección del conteo de funciones de noviembre de 2026, ver «Corrección» más
abajo, el bosque queda en 94.3%. La diferencia no es significativa.)

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
| Funciones (prom.) | 0.20 | 0.44 | 1.60 |
| Con aritmética | 10% | 24% | 58% |
| Longitud del SQL (prom., palabras) | 20 | 30 | 44 |

- Bosque aleatorio con el SQL: **68.8%** (árbol: 70.2%), frente a 50% de la clase más
  común. Mucho menos que en Spider: los expertos no siguen una regla fija.
- Lo que más pesa es la longitud del SQL (0.37), luego las condiciones en WHERE, la
  aritmética, el número de tablas y las funciones. Los JOINs pesan poco porque casi todas
  las consultas de BIRD tienen alguno.
- En BIRD la dificultad viene más de los **cálculos** (CASE/IIF, funciones, porcentajes)
  que de los JOINs. BIRD sí llega a 5 JOINs y a 3 niveles de subconsulta.
- k-means: ARI = −0.01. El ARI vale 0 cuando los grupos coinciden con los niveles igual
  que si fueran al azar y 1 cuando coinciden por completo, así que −0.01 es prácticamente
  aleatorio: sin conocer los niveles, las consultas no se agrupan como los expertos las
  clasificaron. Ver el análisis siguiente.

### ¿Por qué el ARI es tan bajo? (`src/analisis_ari.py`)

k-means sí encuentra grupos claros, pero agrupa por **tipo de consulta**, no por
dificultad (`kmeans_grupos_vs_niveles.csv`):

| Grupo que forma k-means | Simple | Moderado | Desafiante | Total |
|---|---|---|---|---|
| Con ORDER BY y LIMIT (máximos y mínimos) | 21 | 68 | 14 | 103 |
| Con cálculos (CASE/IIF, aritmética) | 0 | 0 | 7 | 7 |
| Filtros y JOINs, sin agrupar, ordenar ni calcular | 127 | 182 | 81 | 390 |

- k-means separa 7 consultas muy largas, llenas de cálculos (todas desafiantes), y parte
  el resto según tengan ORDER BY y LIMIT o no. Esos dos grupos grandes mezclan los tres
  niveles.
- No es un error del código: el ARI se queda entre −0.02 y 0.07 con 2 a 8 grupos, con
  logaritmo de las características y usando solo las 7 más importantes.
- El ARI es una medida muy estricta: las predicciones del bosque aleatorio, que acierta
  el 69%, tienen un ARI de solo 0.26, y cortar las consultas en tres por su longitud da
  0.21. Con niveles que se traslapan tanto, un ARI alto no es posible; un ARI cercano a 0
  indica que
  la estructura que encuentra k-means es otra.
- Conclusión: en BIRD el nivel no corresponde a un tipo de consulta, sino a una mezcla de
  longitud, cálculos y enunciado. k-means agrupa por estructura (cálculos, ORDER BY), no
  por nivel, lo que apoya elegir las consultas de prueba por estructura.
- En Spider pasa lo mismo, pero menos: k-means separa GROUP BY, subconsultas y
  operaciones de conjunto, y como la regla de Spider se basa en esas mismas partes, el
  ARI sube a 0.19.

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
| Solo el SQL | 94.3% | 68.8% |
| Solo el enunciado, en palabras | 49.3% | 61.2% |
| Solo el enunciado, en frases | 42.7% | 56.8% |
| Solo el enunciado, en palabras por frase | 46.7% | 51.0% |
| Solo el enunciado, las tres medidas | 49.3% | 63.0% |
| SQL y enunciado | 94.1% | 76.6% |
| Clase más común (referencia) | 42.7% | 50.0% |

- Contar palabras es la mejor medida. Las frases dicen poco de la pregunta, que casi
  siempre es una sola frase; en la evidencia sí crecen (de 1.7 a 2.8), porque las
  preguntas difíciles necesitan más datos de contexto.
- En Spider el enunciado casi no aporta (49% frente a 43% de la referencia) y sumarlo al
  SQL no cambia nada. En BIRD aporta: con el SQL solo se llega a 69% y con el SQL y el
  enunciado a 76.6%. Los expertos de BIRD tuvieron en cuenta qué tan difícil es entender
  la pregunta y el conocimiento externo, no solo el SQL.
- La longitud es una medida indirecta: dice cuánto hay que leer, no qué tan ambiguo es
  el texto.

## Grupos de dificultad y muestra estratificada

Cada consulta se asigna al primer grupo que cumple, en este orden (G8 primero):

| Grupo | Qué la hace difícil | Spider | BIRD | % Spider difícil/extra | % BIRD desafiante |
|---|---|---|---|---|---|
| G1 | Una tabla, nada más (control) | 286 | 41 | 8.0 | 4.9 |
| G2 | 1 o 2 JOINs | 169 | 220 | 42.0 | 10.5 |
| G3 | 3 JOINs | 3 | 10 | 100 | 20.0 |
| G4 | Cálculos (aritmética, CASE/IIF, funciones como CAST, SUBSTR o STRFTIME) | 0 | 165 | — | 30.3 |
| G5 | Subconsulta sin JOIN | 28 | 16 | 100 | 12.5 |
| G6 | Subconsulta y JOIN | 15 | 39 | 93.3 | 48.7 |
| G7 | UNION / INTERSECT / EXCEPT | 41 | 1 | 97.6 | 0 |
| G8 | Extremos: 4+ JOINs o 2+ niveles de subconsulta | 4 | 8 | 100 | 50.0 |

**Corrección (noviembre de 2026).** El analizador (sqlglot) trata AND y OR como
funciones, así que cualquier consulta con dos condiciones en el WHERE contaba como si
tuviera una función y caía en G4 (Cálculos). Ahora AND/OR/XOR no se cuentan. Cambios: G4
bajó de 340 a 165 consultas y se quedó sin consultas de Spider (en Spider no hay
cálculos); 175 consultas pasaron a G1, G2 y G3, y G3 subió de 6 a 13. De las 24 consultas
de la primera muestra solo cambió de grupo spider-171 (de G4 a G3). Los modelos casi no
cambian (BIRD: 68.0% → 68.8%; Spider: 94.5% → 94.3%).

**Primera muestra** (`resultados/muestra/muestra_representantes.csv`, semilla 2026): **24
consultas, 3 por grupo** (8 × 3). Hay dos clasificaciones distintas: el **grupo** (G1 a
G8) es el nuestro, por estructura; el **nivel** es el que asigna cada benchmark (BIRD:
simple, moderado, desafiante; Spider: fácil, medio, difícil, extra). En cada grupo:

1. Se toman **2 consultas de BIRD y 1 de Spider**.
2. Las 2 de BIRD son siempre **de niveles distintos**: una al azar del nivel más alto que
   tenga el grupo y otra al azar del nivel siguiente hacia abajo.
3. La de Spider sale al azar del nivel más alto que tenga el grupo.
4. En G1, el grupo de control, se hace al revés: se empieza por el nivel más bajo, para
   tener consultas fáciles que comprueben que cada herramienta funciona.
5. Si un benchmark no tiene suficientes consultas en el grupo, se completa con el otro
   (G7 tiene una sola consulta de BIRD, así que lleva 1 de BIRD y 2 de Spider).

**Muestra ampliada** (`resultados/muestra/muestra_ampliada.csv`, `src/ampliar_muestra.py`):
**80 consultas, 10 por grupo**. Conserva las 24 anteriores (ya probadas) y agrega 7 por
grupo con la misma regla: dentro de cada grupo y benchmark las consultas se barajan con la
misma semilla y se toman por turnos de cada nivel, del más alto al más bajo (en G1, al
revés). Cuota: 5 de BIRD y 5 de Spider por grupo; si un benchmark no alcanza, se completa
con el otro.

| | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 |
|---|---|---|---|---|---|---|---|---|
| BIRD | 5 | 5 | 7 | 10 | 5 | 5 | 1 | 6 |
| Spider | 5 | 5 | 3 | 0 | 5 | 5 | 9 | 4 |

Con la corrección, todos los grupos tienen al menos 10 consultas, así que no hizo falta
inventar ninguna. Si un grupo no alcanzara, `ampliar_muestra.py` completa con las de
`resultados/muestra/consultas_inventadas.csv` (comprueba que se ejecutan y que caen en ese
grupo). Huecos que siguen: G3 y G8 apenas llegan a 10, G7 casi no existe en BIRD, G4 no
existe en Spider, y ningún benchmark pasa de 5 JOINs ni de 3 niveles de subconsulta.

## Herramientas candidatas

Indicadores de popularidad y madurez (noviembre de 2026). Commits, fechas y versiones
salen del historial de git de cada repositorio; estrellas y forks, de la página de GitHub
(los marcados con * vienen de ecosyste.ms o sourcepulse y pueden estar desactualizados).
"Papers" es en cuántos de los 16 artículos leídos aparece la herramienta.

| Herramienta | Tipo | Estrellas | Forks | Commits | Versiones | Primer / último commit | Licencia | Papers | LLM que usa |
|---|---|---|---|---|---|---|---|---|---|
| Vanna | Biblioteca de Python | 23.8k | 2.5k | 972 | 78 (última v2.0.2, feb 2026) | may 2023 / feb 2026 | MIT | 0 | Cualquiera (API u Ollama local) |
| WrenAI | Capa semántica para agentes (CLI de Python) | 18.0k | 2.1k | 2,780 | 507 etiquetas (varios componentes) | may 2022 / nov 2026 | Apache-2.0 | 0 | El del agente que la usa (Claude Code, LangChain, etc.) |
| XiYan-SQL | Método + modelos propios | 1.0k | 53 | 163 | 0 | nov 2024 / may 2026 | Apache-2.0 | 2 | Sus modelos (Hugging Face) |
| DAIL-SQL | Método de investigación (prompts) | ~640* | ~66* | 24 | 0 | ago 2023 / mar 2025 | Apache-2.0 | 6 | API de OpenAI |
| OmniSQL | Modelo abierto (7B, 14B, 32B) | ~455* | – | 17 | 0 | feb 2025 / sep 2025 | – | 6 | Local (necesita GPU) |
| MAC-SQL | Método de investigación (agentes) | 347 | 54 | 35 | 0 | dic 2023 / feb 2025 | – | 5 | API de GPT-4 o su modelo |
| DIN-SQL | Método de investigación (prompts) | ~297* | ~58* | 29 | 0 | mar 2023 / oct 2023 | MIT | 11 | API de OpenAI |
| CHESS | Método de investigación (agentes) | ~115* | ~28* | 9 | 0 | jun 2024 / nov 2024 | Apache-2.0 | 7 | API de LLM (configurable) |

- Hay dos familias. **Productos** (Vanna, WrenAI): muy populares, con muchas versiones y
  activos, pero ningún paper los usa. **Métodos de investigación** (DIN-SQL, DAIL-SQL,
  CHESS, MAC-SQL, OmniSQL): son las referencias con las que se comparan los papers
  (DIN-SQL aparece en 11 de 16), pero no publican versiones y casi no se actualizan.
- **Selección acordada:** Vanna y WrenAI (los dos productos más populares y maduros), una
  herramienta de prompts (DAIL-SQL o DIN-SQL) y una de agentes (MAC-SQL o CHESS). Dentro
  de cada pareja se elegirá la que se instale y funcione mejor. OmniSQL queda fuera
  porque necesita GPU.
- La versión actual de WrenAI ya no es una plataforma con interfaz propia: es una capa
  semántica que usan agentes como Claude Code o LangChain para escribir el SQL.

### Prueba de instalación (noviembre de 2026)

Cada herramienta se instaló en un entorno aparte, con la versión de Python que pide su
README y sus dependencias tal cual (`herramientas/prueba_instalacion.sh`, en Linux).
Todavía no se ejecutaron consultas: eso requiere una clave de API.

| Herramienta | Python | ¿Se instala? | Tiempo | Tamaño | Observaciones |
|---|---|---|---|---|---|
| Vanna 2.0.2 | 3.12 | Sí | 4 s | 0.2 GB | Paquete de pip. |
| WrenAI 0.18.0 | 3.12 | Sí | 11 s | 0.5 GB | Su CLI ejecuta y controla el SQL, pero no lo genera: necesita un agente (LangChain, Claude Code) que escriba la consulta. |
| MAC-SQL | 3.9 | Sí | 6 s | 0.2 GB | El código carga bien y permite cambiar la dirección de la API, así que es fácil usarlo con Gemini. |
| DIN-SQL | 3.10 | Sí | 71 s | 3.7 GB | Dependencias antiguas (torch 1.13, openai 0.27). El script trae un error de sintaxis (`API_KEY = #key`) que hay que corregir, y el modelo está fijo en `gpt-4`. |
| DAIL-SQL | 3.8 | Sí | 15 min | 5.2 GB | Python 3.8 ya no tiene soporte. Además necesita Java, el servidor Stanford CoreNLP y descargar datos de NLTK. |
| CHESS | 3.10 | Sí | 33 s | 6.4 GB | Los *embeddings* de OpenAI están escritos en el código: para usar solo Gemini hay que modificarlo. |

- Las seis se instalan, pero con esfuerzo muy distinto: Vanna, WrenAI y MAC-SQL son
  ligeras; DIN-SQL, DAIL-SQL y CHESS bajan PyTorch y ocupan varios GB.
- Entre las de prompts, DIN-SQL es más sencilla de poner en marcha que DAIL-SQL (no
  necesita Java ni CoreNLP). Entre las de agentes, MAC-SQL es más sencilla que CHESS.

### Clave de Gemini

Las herramientas usan Gemini a través de su dirección compatible con OpenAI. La clave va en
un archivo `.env` en la carpeta del proyecto, que **no se sube a GitHub** (está en
`.gitignore`):

1. Copia `.env.ejemplo` como `.env` y pega tu clave en `GEMINI_API_KEY`.
2. Comprueba que funciona: `python herramientas/probar_gemini.py`

### Probar las herramientas

Todas se prueban con las mismas reglas (`herramientas/comun.py`): el mismo LLM
(el que indica `LLM_PROVEEDOR` en `.env`; en las pruebas, openai/gpt-oss-120b en Groq), la pregunta más la evidencia en BIRD, y exactitud por ejecución (el SQL
generado debe devolver las mismas filas que el correcto). Para cada consulta se guardan el
SQL generado, el acierto, los tokens, las llamadas al LLM y el tiempo, en
`resultados/herramientas/<herramienta>.csv`.

```bash
pip install gdown pandas "vanna[chromadb]" openai python-dotenv
python herramientas/descargar_bases.py              # bases SQLite de la muestra (80 consultas)
python herramientas/probar_vanna.py

pip install func_timeout sqlparse tiktoken nltk tqdm
python herramientas/probar_macsql.py --max 30
python herramientas/probar_dinsql.py --max 20

python -m pip install wrenai wren-langchain langchain langchain-openai duckdb
python herramientas/probar_wrenai.py --max 20
```

Los tokens de **entrada** (el prompt: pregunta, esquema, ejemplos) y de **salida** (lo que
responde el modelo, incluido su razonamiento) se guardan por separado, porque su precio es
muy distinto: en Groq, gpt-oss-120b cuesta 0.15 USD por millón de tokens de entrada y 0.60
de salida (noviembre de 2026). Al final de cada corrida se muestra el costo estimado
(`PRECIO_ENTRADA` y `PRECIO_SALIDA` se pueden cambiar en `.env`).

Cada script **sigue donde se quedó**: salta las consultas que ya tienen resultado en su
CSV (las PENDIENTES sí se vuelven a correr) y guarda el CSV después de cada consulta.
`--max N` limita cuántas consultas nuevas se corren esa vez (con el plan gratuito de Groq,
unos 200,000 tokens al día: Vanna puede correr las 80 en un día; MAC-SQL, unas 30;
WrenAI y DIN-SQL, unas 20). `--grupos` corre solo esos grupos y `--repetir` vuelve a
correr las que ya tienen resultado. Si se agota la cuota diaria, el script se detiene y al
día siguiente basta con repetir el mismo comando.

WrenAI (versión 0.18) no genera SQL por sí misma: es una capa semántica que usa un agente.
Se prueba con su integración oficial con LangChain, con el mismo LLM. El script copia cada
base a DuckDB (WrenAI no se conecta a SQLite) y arma su modelo semántico (MDL) solo con
tablas, columnas y llaves, sin descripciones, para que reciba la misma información que las
demás herramientas. El SQL final del agente se ejecuta con WrenAI.

Las consultas en las que el LLM no responde (saturación o cuota agotada) quedan como PENDIENTE y no
cuentan como fallo; el tiempo de espera de los reintentos no se suma al de la herramienta.

## Datos y créditos

- Spider: Yu et al. (2018), https://yale-lily.github.io/spider ·
  regla de niveles en https://github.com/taoyds/spider (licencia CC BY-SA 4.0).
- BIRD: Li et al. (2023), https://bird-bench.github.io/
