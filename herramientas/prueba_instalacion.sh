#!/bin/bash
# Prueba de instalación: python indicado por cada README, requirements tal cual
cd "$(dirname "$0")"
try() { name=$1; py=$2; shift 2; rm -rf venvs/$name; uv venv -q -p $py venvs/$name; start=$(date +%s)
  if "$@" > logs/$name.log 2>&1; then st=OK; else st=FALLA; fi
  echo "$name|python $py|$st|$(( $(date +%s)-start ))s" | tee -a resumen.txt; }
mkdir -p logs venvs; : > resumen.txt
export UV_HTTP_TIMEOUT=300
try vanna 3.12 uv pip install -p venvs/vanna "vanna" 
try wrenai 3.12 uv pip install -p venvs/wrenai "wrenai"
try macsql 3.9 uv pip install -p venvs/macsql -r repos/MAC-SQL/requirements.txt
try dinsql 3.10 uv pip install -p venvs/dinsql -r repos/Few-shot-NL2SQL-with-prompting/requirements.txt
try dailsql 3.8 uv pip install -p venvs/dailsql -r repos/DAIL-SQL/requirements.txt
try chess 3.10 uv pip install -p venvs/chess -r repos/CHESS/requirements.txt
echo FIN >> resumen.txt
