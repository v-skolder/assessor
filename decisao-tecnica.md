# Decisão técnica: autorização de escritas

## 1. A decisão tomada e por quê

A decisão foi **adiar a escrita até a aprovação da saída pelo juiz**. No grafo, o juiz é a última etapa de avaliação: ele preserva o julgamento de fidelidade e depois confirma ou descarta as operações pendentes. Sua aprovação exige veredito `apoiada` e pontuação `noul` de pelo menos 0,70. O juiz avalia a resposta e as evidências, e não substitui a validação de autorização ou de todos os argumentos.

**Antes:** a tool gravava; depois o orquestrador, o guardrail e o juiz avaliavam a resposta. Uma rejeição podia ocorrer após a gravação.

**Depois:** a tool prepara a operação; o orquestrador e o guardrail processam a resposta; o juiz avalia e, se aprovar, efetiva as pendências. Se rejeitar ou falhar, elas são descartadas.

No código atual, `add_transaction`, `update_transaction` e `add_event` enfileiram operações em memória quando recebem o `turno_id`. Após a aprovação, as escritas Postgres do turno são executadas em uma transação. Essa proteção depende de a chamada passar pelo turno configurado: sem `turno_id`, a escrita é imediata. O resultado inicial da tool é provisório.

A simulação da execução adiada registrou **zero inserções e zero registros na recusa**, e um registro por execução nos 20 turnos aprovados. A conexão ficou aberta por 10,62 ms em média, contra 161,42 ms na alternativa com transação aberta antes do juiz. Esses testes usam operações simuladas: ainda não comprovam o comportamento das três tools reais integradas ao grafo.

## 2. As decisões que o grupo não tomou

| Alternativa | Como funcionaria e vantagem | Custo e motivo para não adotá-la |
|---|---|---|
| Transação compartilhada | As tools executariam SQL sem commit; o juiz autorizaria commit ou rollback. Permite detectar parte dos erros SQL antes do veredito. | A conexão e a transação ficam abertas durante a espera. Na simulação, a conexão permaneceu aberta por 161,42 ms em média; na execução adiada, por 10,62 ms. |
| Validação prévia | Um juiz avaliaria cada chamada antes da escrita, e a resposta final ainda seria avaliada. Pode barrar uma operação antes de executá-la. | Acrescenta uma avaliação por escrita. Na simulação houve duas chamadas por aprovação; quando a saída final foi rejeitada depois, o registro já permanecia no banco. |
| Executar e compensar | A tool gravaria imediatamente e uma operação posterior tentaria reverter a escrita rejeitada. O agente teria acesso ao resultado real antes do julgamento. | A reversão é outro efeito e pode falhar. No teste de recusa, outra conexão observou o registro antes da remoção, mesmo com zero registros ao final. |
| Validar e guardar uma flag | Uma aprovação anterior seria registrada para evitar outra avaliação. A simulação usa uma única chamada ao juiz por aprovação. | A saída pode mudar após a avaliação: no cenário testado, a saída alterada ficou sem nova avaliação e o registro permaneceu. |

## 3. Efeito nas métricas do SRE

O monitor da Etapa 6 usa SLO de p95 de **8 s** e taxa de erro de **5%**. A taxa divide turnos `erro` pelo total de turnos; `bloqueado` não entra no numerador. Exceções não tratadas contam como erro. Uma recusa tratada com frase segura pode terminar `ok`, pois não necessariamente gera exceção.

Os testes executaram 20 turnos aprovados sequenciais por alternativa, com Postgres em container, juiz simulado de 100 ms por chamada e orquestrador simulado de 50 ms:

| Alternativa | Latência média | p95 | Conexão aberta média | Chamadas ao juiz por aprovação |
|---|---:|---:|---:|---:|
| Execução adiada | 191,11 ms | 209,24 ms | 10,62 ms | 1 |
| Transação compartilhada | 189,56 ms | 205,74 ms | 161,42 ms | 1 |
| Validação prévia | 291,14 ms | 309,76 ms | 160,79 ms | 2 |
| Compensação | 219,39 ms | 252,03 ms | 191,52 ms | 1 |
| Flag de validação | 194,23 ms | 213,64 ms | 61,38 ms | 1 |

Na execução adiada, o turno espera o juiz e depois a gravação; na transação compartilhada, a conexão permanece aberta enquanto aguarda o veredito. A validação prévia adiciona uma chamada simulada, e a compensação adiciona uma operação de remoção na recusa. O tempo de conexão é medido após conectar até fechar; ele não é necessariamente a duração da transação. Os p95 simulados ficaram abaixo de 8 s, mas não medem o SLO do sistema real.

Os cenários controlados resultaram em 21 `ok`, 2 `erro` e 1 `bloqueado` para execução adiada, transação e compensação: 2/24, ou 8,3%. Validação prévia e flag tiveram um cenário adicional: 22 `ok`, 2 `erro`, 1 `bloqueado`, ou 2/25 (8,0%). As duas falhas foram injetadas; essas proporções não estimam a taxa real nem comprovam o SLO de 5%.

## 4. As outras decisões

- **`add_google_event`:** a criação no Google Calendar também foi adiada para depois da aprovação e, quando há escritas Postgres, depois do commit. O serviço externo não integra a transação do banco. Se falhar, o resultado pode ser parcial ou desconhecido; a mensagem atual pressupõe evento local salvo mesmo quando só existe operação externa pendente. Os testes comparativos não chamaram o Google Calendar real.
- **`salvar_mensagem`:** permanece fora da autorização das escritas de negócio. O fluxo tenta salvar a entrada anonimizada e a resposta entregue após o grafo; uma falha da memória não desfaz um commit anterior.

**Evidência com marcador único:** a simulação de execução adiada verificou recusa com zero registros e 20 aprovações com um registro por execução. Ela não usou as três tools reais. Portanto, ainda falta comprovar esses dois resultados para cada uma de `add_transaction`, `update_transaction` e `add_event` integradas ao juiz; para atualização, é necessário comparar também os valores antes e depois.

## 5. Arquivos criados e arquivos modificados

**Criados:**

- `app/escritas.py`

**Testes e relatórios**
- `test/docker-compose.yml`
- `test/comum.py`
- `test/execucao_adiada.py`
- `test/transacao_compartilhada.py`
- `test/validacao_previa.py`
- `test/compensacao.py`
- `test/flag_validacao.py`
- `test/relatorios/execucao_adiada.md`
- `test/relatorios/transacao_compartilhada.md`
- `test/relatorios/validacao_previa.md`
- `test/relatorios/compensacao.md`
- `test/relatorios/flag_validacao.md`

**Modificados:**

- `app/graph.py` — encaminha o identificador do turno, registra as aprovações, encerra no juiz e limpa as pendências.
- `app/juiz.py` — mantém a avaliação e confirma ou descarta as escritas, ajustando a resposta quando necessário.
- `app/tools/financeiro.py` — prepara escritas financeiras para execução adiada.
- `app/tools/agenda.py` — prepara escritas de eventos locais para execução adiada.
- `app/tools/calendario_google.py` — adia a criação externa durante o turno.
