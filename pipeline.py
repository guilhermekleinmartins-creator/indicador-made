#!/usr/bin/env python3
"""
Indicador Made — pipeline de atualizacao mensal.

Reproduz a metodologia de KLEIN, G.; PAULINO, L. "Uma Regra de Sahm para o Brasil:
desemprego e alerta rapido de recessoes". Made/USP, NPE n. 87, jul/2026.

Serie de desemprego:
  1980-01 a 2012-02 : PME (metodologia antiga ate 2002-02, nova a partir de 2002-03),
                      encadeada retrospectivamente a partir do nivel da PNAD Continua.
                      Congelada em data/nsa_frozen.csv (nao muda).
  2012-03 em diante : PNAD Continua, taxa de desocupacao, trimestre movel
                      (SIDRA tabela 6381, variavel 4099). data/pnadc.csv.

Dessazonalizacao: X-13ARIMA-SEATS (X-11, multiplicativo, automdl + outliers),
reestimada sobre a serie inteira a cada atualizacao.

Indicador: media movel de 3 meses da taxa dessazonalizada menos o menor valor
dessa media movel nos 12 meses anteriores. Gatilho: 0,3 p.p.

Uso:
    python3 pipeline.py            # le data/, escreve data.json
    python3 pipeline.py --check    # imprime diagnostico
"""
import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
THRESHOLD = 0.3

# Datacao de ciclos do CODACE-FGV (trimestres convertidos para meses),
# como usada na nota. Fim inclusivo.
CODACE = [
    ("1981-01", "1983-03"),
    ("1987-07", "1988-12"),
    ("1989-07", "1992-03"),
    ("1995-04", "1995-09"),
    ("1998-01", "1999-03"),
    ("2001-04", "2001-12"),
    ("2003-01", "2003-06"),
    ("2008-10", "2009-03"),
    ("2014-04", "2016-12"),
    ("2020-01", "2020-06"),
]


# --------------------------------------------------------------------------- #
# X-13ARIMA-SEATS
# --------------------------------------------------------------------------- #
def x13_seasonal_adjust(series):
    """series: pd.Series com PeriodIndex mensal. Retorna (sa, seasonal_factors)."""
    from x13binary import find_x13_bin

    vals = [float(v) for v in series.values]
    start = series.index[0]
    with tempfile.TemporaryDirectory() as td:
        dat = os.path.join(td, "s.dat")
        with open(dat, "w") as f:
            f.write("\n".join(f"{v:.10f}" for v in vals))
        base = os.path.join(td, "run")
        spc = (
            f'series{{ file="{dat}" period=12 start={start.year}.{start.month} }}\n'
            "transform{ function=log }\n"
            "automdl{}\n"
            "outlier{}\n"
            "x11{ mode=mult save=(d11 d10) }\n"
        )
        with open(base + ".spc", "w") as f:
            f.write(spc)
        proc = subprocess.run(
            [find_x13_bin(), "-i", base, "-o", base], capture_output=True, text=True
        )
        if not os.path.exists(base + ".d11"):
            raise RuntimeError("X-13 falhou:\n" + (proc.stdout or "")[-2000:])
        sa = _read_x13_table(base + ".d11")
        sf = _read_x13_table(base + ".d10") if os.path.exists(base + ".d10") else []
    idx = series.index
    out_sa = pd.Series(sa, index=idx, name="sa")
    out_sf = pd.Series(sf, index=idx, name="sf") if len(sf) == len(idx) else None
    return out_sa, out_sf


def _read_x13_table(path):
    vals = []
    for line in open(path):
        p = line.split()
        if len(p) == 2 and p[0].isdigit() and len(p[0]) == 6:
            vals.append(float(p[1]))
    return vals


# --------------------------------------------------------------------------- #
# Serie e indicador
# --------------------------------------------------------------------------- #
def build_nsa():
    froz = pd.read_csv(os.path.join(HERE, "data", "nsa_frozen.csv"))
    pnad = pd.read_csv(os.path.join(HERE, "data", "pnadc.csv"))
    for d in (froz, pnad):
        d["date"] = pd.PeriodIndex(d["date"], freq="M")
    s = pd.concat(
        [froz.set_index("date")["unemp_nsa"], pnad.set_index("date")["unemp_nsa"]]
    ).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    full = pd.period_range(s.index[0], s.index[-1], freq="M")
    if len(full) != len(s):
        missing = [str(p) for p in full.difference(s.index)]
        raise ValueError(f"lacunas na serie mensal: {missing}")
    return s.astype(float)


def compute_indicator(sa):
    ma3 = sa.rolling(3).mean()
    min12 = ma3.shift(1).rolling(12).min()
    ind = ma3 - min12
    return pd.DataFrame({"sa": sa, "ma3": ma3, "min12": min12, "ind": ind})


def episodes(flag_series):
    """Sequencias contiguas onde flag e True. Retorna [(inicio, fim), ...]."""
    eps, cur, prev = [], None, None
    for d, v in flag_series.items():
        if v and cur is None:
            cur = d
        elif not v and cur is not None:
            eps.append((cur, prev))
            cur = None
        prev = d
    if cur is not None:
        eps.append((cur, prev))
    return eps


def month_diff(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


# --------------------------------------------------------------------------- #
def main():
    nsa = build_nsa()
    sa, sf = x13_seasonal_adjust(nsa)
    df = compute_indicator(sa)
    df["nsa"] = nsa
    df["trig"] = df["ind"] >= THRESHOLD

    eps = episodes(df["trig"].fillna(False))
    last_ep = eps[-1] if eps else None
    last = df.index[-1]
    cur_ind = float(df["ind"].iloc[-1])
    in_recession = bool(df["trig"].iloc[-1])

    if in_recession:
        months_since = 0
        start_current = str(last_ep[0])
    else:
        months_since = month_diff(last_ep[1], last) if last_ep else None
        start_current = None

    # Intervalos (em meses) entre o fim de um episodio e o inicio do seguinte.
    gaps = [month_diff(eps[i][1], eps[i + 1][0]) for i in range(len(eps) - 1)]
    record_gap = bool(
        not in_recession and months_since is not None and gaps and months_since > max(gaps)
    )

    codace_flag = pd.Series(False, index=df.index)
    for a, b in CODACE:
        codace_flag.loc[pd.Period(a) : pd.Period(b)] = True

    out = {
        "meta": {
            "atualizado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limiar": THRESHOLD,
            "ultimo_mes": str(last),
            "fonte": "PME (IBGE) e PNAD Continua (IBGE, SIDRA tabela 6381, variavel 4099)",
            "n_obs": int(len(df)),
        },
        "status": {
            "acionado": in_recession,
            "indicador": round(cur_ind, 4),
            "desemprego_sa": round(float(df["sa"].iloc[-1]), 3),
            "desemprego_nsa": round(float(df["nsa"].iloc[-1]), 2),
            "ma3": round(float(df["ma3"].iloc[-1]), 3),
            "min12": round(float(df["min12"].iloc[-1]), 3),
            "meses_desde_ultima_recessao": months_since,
            "inicio_recessao_corrente": start_current,
            "fim_ultima_recessao": str(last_ep[1]) if last_ep else None,
            "meses_acionados": int(df["trig"].sum()),
            "intervalo_recorde": record_gap,
            "maior_intervalo_anterior": max(gaps) if gaps else None,
        },
        "series": {
            "datas": [str(p) for p in df.index],
            "nsa": [round(v, 4) for v in df["nsa"]],
            "sa": [round(v, 4) for v in df["sa"]],
            "ind": [None if pd.isna(v) else round(v, 4) for v in df["ind"]],
        },
        "episodios_made": [
            {"inicio": str(a), "fim": str(b), "meses": month_diff(a, b) + 1}
            for a, b in eps
        ],
        "recessoes_codace": [{"inicio": a, "fim": b} for a, b in CODACE],
    }

    docs = os.path.join(HERE, "docs")
    os.makedirs(docs, exist_ok=True)

    # data.json — a "API" do indicador, servida junto com o site.
    with open(os.path.join(docs, "data.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    # data.js — o arquivo que a pagina carrega (<script src="data.js">).
    with open(os.path.join(docs, "data.js"), "w") as f:
        f.write("window.MADE_DATA=")
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    # CSV completo para download.
    with open(os.path.join(docs, "indicador_made.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["data", "desemprego_nsa", "desemprego_sa", "indicador_made", "acionado"])
        for p, row in df.iterrows():
            ind = row["ind"]
            w.writerow([
                str(p),
                round(row["nsa"], 4),
                round(row["sa"], 4),
                "" if pd.isna(ind) else round(ind, 4),
                "" if pd.isna(ind) else int(ind >= THRESHOLD),
            ])

    print(f"ok: docs/  ultimo={last}  indicador={cur_ind:.3f}  acionado={in_recession}")

    if "--check" in sys.argv:
        print("\nEpisodios do Indicador Made:")
        for e in out["episodios_made"]:
            print(f"  {e['inicio']} -> {e['fim']}  ({e['meses']} meses)")
    return out


if __name__ == "__main__":
    main()
