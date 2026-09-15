#!/usr/bin/env python3
"""
Baixa a taxa de desocupacao da PNAD Continua (trimestre movel, Brasil) do SIDRA
e atualiza data/pnadc.csv.

SIDRA tabela 6381, variavel 4099. O codigo de periodo e AAAAMM, com MM = mes
final do trimestre movel (ex.: 202607 = mai-jun-jul/2026).

Saida: imprime quantos periodos foram acrescentados e quantos foram revisados.
Codigo de saida 0 sempre que a consulta funcionou, mesmo sem novidade.
"""
import csv
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "pnadc.csv")
URL = "https://apisidra.ibge.gov.br/values/t/6381/n1/all/v/4099/p/last%2024"
TIMEOUT = 90


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "indicador-made/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        import json

        raw = json.loads(r.read().decode("utf-8"))
    out = {}
    for row in raw:
        code, val = row.get("D3C"), row.get("V")
        if not code or not str(code).isdigit() or len(str(code)) != 6:
            continue  # linha de cabecalho
        try:
            out[f"{code[:4]}-{code[4:]}"] = float(val)
        except (TypeError, ValueError):
            continue  # "..." ou "-" quando o dado nao existe
    if not out:
        raise RuntimeError("SIDRA nao devolveu nenhuma observacao utilizavel")
    return out


def main():
    novos = fetch()

    atual = {}
    ordem = []
    with open(CSV_PATH) as f:
        for row in csv.DictReader(f):
            atual[row["date"]] = float(row["unemp_nsa"])
            ordem.append(row["date"])

    acrescentados, revisados = [], []
    for k, v in sorted(novos.items()):
        if k not in atual:
            acrescentados.append(k)
            atual[k] = v
        elif abs(atual[k] - v) > 1e-9:
            revisados.append((k, atual[k], v))
            atual[k] = v

    if not acrescentados and not revisados:
        print("sem novidade: ultimo periodo continua", ordem[-1])
        return

    with open(CSV_PATH, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "unemp_nsa"])
        for k in sorted(atual):
            w.writerow([k, f"{atual[k]:.1f}"])

    if acrescentados:
        print("acrescentados:", ", ".join(acrescentados))
    for k, a, b in revisados:
        print(f"revisado: {k} {a:.1f} -> {b:.1f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # falha de rede ou do SIDRA nao deve quebrar o site
        print(f"ERRO ao consultar o SIDRA: {exc}", file=sys.stderr)
        sys.exit(1)
