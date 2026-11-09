# Testes das alternativas

Os scripts usam um PostgreSQL isolado e simulam o juiz e o orquestrador. Eles não acessam o banco configurado pela aplicação nem chamam serviços externos. Requerem Docker e `psycopg2` instalado a partir de `requirements.txt`.

```powershell
docker compose -p decisao-testes -f test/docker-compose.yml up -d --wait
python test/execucao_adiada.py
python test/transacao_compartilhada.py
python test/validacao_previa.py
python test/compensacao.py
python test/flag_validacao.py
docker compose -p decisao-testes -f test/docker-compose.yml down
```

Cada script cria e remove sua própria tabela e gera `test/relatorios/<nome_do_teste>.md`. Para outro banco de teste, configure `TEST_DATABASE_URL`. Não use banco de produção. Os scripts não executam as tools ou o grafo real; os resultados são simulações, não medições de produção. A taxa de erro inclui falhas injetadas. Tokens e custo reais não são medidos.
