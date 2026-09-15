# Indicador Made

Uma regra de Sahm calibrada para o Brasil. O indicador sinaliza o início de uma recessão quando a
média móvel de três meses da taxa de desocupação dessazonalizada supera em **0,3 ponto percentual**
o menor valor dessa média nos doze meses anteriores.

Metodologia: KLEIN, G.; PAULINO, L. *Uma Regra de Sahm para o Brasil: desemprego e alerta rápido de
recessões*. São Paulo: Centro de Pesquisa em Macroeconomia das Desigualdades (Made/USP), 2026.
Nota de Política Econômica nº 87.

O site é publicado por GitHub Pages a partir da pasta `docs/` e se atualiza sozinho a cada
divulgação da PNAD Contínua.

## Como funciona

| Arquivo | Papel |
|---|---|
| `data/nsa_frozen.csv` | Série mensal de desemprego de jan/1980 a fev/2012, sem ajuste sazonal. Congelada: resulta do encadeamento retrospectivo da PME (metodologia antiga até 2002, nova de 2002 a 2012) a partir do nível da PNAD Contínua. **Não muda.** |
| `data/pnadc.csv` | Taxa de desocupação da PNAD Contínua, trimestre móvel, de mar/2012 em diante. Atualizada a cada rodada. |
| `fetch_sidra.py` | Busca os períodos novos no SIDRA (tabela 6381, variável 4099) e os acrescenta a `data/pnadc.csv`, corrigindo também valores revisados pelo IBGE. |
| `pipeline.py` | Emenda as duas séries, dessazonaliza com X-13ARIMA-SEATS, calcula o indicador e escreve `docs/data.json`, `docs/data.js` e `docs/indicador_made.csv`. |
| `docs/index.html` | O site. Carrega `data.js`; nada mais muda entre atualizações. |
| `.github/workflows/atualiza.yml` | Roda os dois scripts nos dias 2 e 9 de cada mês e faz commit se algo mudou. |

O código de período do SIDRA é `AAAAMM`, com `MM` igual ao **mês final** do trimestre móvel:
`202607` é o trimestre mai-jun-jul/2026.

## Rodar localmente

```bash
pip install -r requirements.txt
python fetch_sidra.py     # opcional: só busca dado novo
python pipeline.py --check
python -m http.server -d docs 8000
```

`pipeline.py --check` imprime a lista completa de episódios sinalizados.

## Uma observação sobre revisões

O ajuste sazonal é reestimado sobre a série inteira a cada rodada, como é praxe na produção de
indicadores conjunturais. Isso significa que meses antigos sofrem revisões marginais e que a
contagem de episódios pode diferir ligeiramente da Tabela 1 da nota original, cujo ajuste sazonal
foi estimado uma única vez. As datas dos dezesseis episódios da nota se mantêm.

## Dados

`docs/indicador_made.csv` traz a série completa (bruta, dessazonalizada, indicador e a dummy de
acionamento). `docs/data.json` traz o mesmo conteúdo em JSON, incluindo o status corrente e a lista
de episódios — serve como API simples para quem quiser consumir o indicador.

Fonte primária: IBGE (PME e PNAD Contínua). Datação de ciclos para comparação: CODACE-FGV.

## Como colocar no ar (primeira vez)

O Google Drive sincroniza arquivos continuamente e não convive bem com uma pasta `.git`.
Copie o projeto para fora do Drive antes de versioná-lo:

```bash
cp -R ~/"Library/CloudStorage/GoogleDrive-guilherme.klein.martins@gmail.com/My Drive/MADE/SAHM RULE/indicador-made" ~/indicador-made
cd ~/indicador-made
git init -b main
git add -A
git commit -m "Indicador Made: site e atualizacao automatica"
git remote add origin https://github.com/SEU-USUARIO/indicador-made.git
git push -u origin main
```

Crie o repositório vazio e **público** em github.com/new antes do `git push` (sem README, sem
.gitignore — o push traz tudo).

Depois, no repositório:

1. **Settings → Pages**: em *Source*, escolha `Deploy from a branch`; em *Branch*, `main` e a pasta
   `/docs`. O site sai em `https://SEU-USUARIO.github.io/indicador-made/` em um ou dois minutos.
2. **Settings → Actions → General**: em *Workflow permissions*, marque
   `Read and write permissions`. Sem isso o robô não consegue publicar o commit mensal.
3. **Aba Actions → "Atualiza o Indicador Made" → Run workflow**: roda na hora e confirma que o
   caminho inteiro funciona, sem esperar o dia 2.

Para transferir depois para a organização do Made: **Settings → General → Transfer ownership**.
Isso preserva histórico, Actions e issues; só o endereço do site muda para
`https://made-usp.github.io/indicador-made/`, e o link "Código e dados" no rodapé acompanha
sozinho, porque é deduzido do endereço da própria página.
