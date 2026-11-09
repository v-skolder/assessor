# validacao_previa

## Método

20 turnos aprovados sequenciais, mais cenários controlados; PostgreSQL em container isolado. Juiz simulado: 100 ms por chamada; orquestrador simulado: 50 ms. Os modelos, Google Calendar e o grafo real não são executados.

## Indicadores

| Indicador | Resultado |
|---|---:|
| Latência média dos aprovados | 291.14 ms |
| Latência p95 dos aprovados (limite 8 s) | 309.76 ms |
| Conexão aberta média dos aprovados | 160.79 ms |
| Chamadas simuladas ao juiz por aprovação | 2.0 |
| Taxa de erro nos cenários controlados (limite 5%) | 8.0% (2/25) |
| Status ok / erro / bloqueado | 22 / 2 / 1 |
| Tokens reais / custo real | Não medidos |

A taxa inclui falhas injetadas deliberadamente e não estima a taxa de erro em produção. A latência inclui a espera simulada, gravação e commit; o tempo de conexão começa após conectar. Bloqueios entram no denominador, mas não no numerador de erros.

## Cenários

| Cenário | Status | Registros finais | SQL executado | Visível antes do veredito | Chamadas ao juiz | Saída final rejeitada ou não reavaliada |
|---|---|---:|---:|---:|---:|---|
| recusa | ok | 0 | 0 | 0 | 1 | não |
| falha_sql | erro | 0 | 1 | 0 | 1 | não |
| bloqueio | bloqueado | 0 | 0 | 0 | 0 | não |
| excecao | erro | 0 | 0 | 0 | 0 | não |
| saida_alterada | ok | 1 | 1 | 0 | 2 | sim |

Cada cenário usa marcador único. `SQL executado` conta inserções executadas, inclusive as revertidas; a visibilidade é consultada por outra conexão somente na compensação. Uma aprovação escreve uma linha; isso não demonstra idempotência em uma repetição. A falha SQL é uma violação de chave dentro da transação.

A simulação não mede concorrência, falha do commit, timeout real, queda do processo ou custo de modelos. Ela não comprova a execução das tools reais nem a qualidade do julgamento.
