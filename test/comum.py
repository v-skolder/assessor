
"""Simulação comparável das alternativas usando PostgreSQL isolado."""

import math
import os
import statistics
import time
import uuid
from pathlib import Path

import psycopg2


__all__ = ["executar"]


DSN = os.getenv("TEST_DATABASE_URL", "host=127.0.0.1 port=55439 dbname=decisao_testes user=testes password=testes connect_timeout=3")
ATRASO_JUIZ = 0.10
ATRASO_ORQUESTRADOR = 0.05
AMOSTRAS = 20
PASTA = Path(__file__).resolve().parent / "relatorios"


def executar(nome, modo):
    """Executa cenários e grava um relatório da alternativa."""
    tabela = "teste_" + uuid.uuid4().hex
    with psycopg2.connect(DSN) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(f"CREATE TABLE {tabela} (marcador TEXT PRIMARY KEY, valor INTEGER NOT NULL)")

    def contar(marcador):
        with psycopg2.connect(DSN) as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {tabela} WHERE marcador = %s", (marcador,))
                return cursor.fetchone()[0]

    def turno(cenario):
        inicio = time.perf_counter()
        marcador = uuid.uuid4().hex
        conexao = None
        inicio_conexao = None
        tempo_conexao = 0.0
        chamadas = 0
        efeitos = 0
        exposicao = 0
        status = "ok"
        conteudo_invalido = False

        def abrir():
            nonlocal conexao, inicio_conexao
            conexao = psycopg2.connect(DSN)
            inicio_conexao = time.perf_counter()

        def gravar():
            nonlocal efeitos
            with conexao.cursor() as cursor:
                cursor.execute(f"INSERT INTO {tabela} (marcador, valor) VALUES (%s, %s)", (marcador, 1))
                efeitos += 1
                if cenario == "falha_sql":
                    cursor.execute(f"INSERT INTO {tabela} (marcador, valor) VALUES (%s, %s)", (marcador, 2))

        def julgar():
            nonlocal chamadas
            chamadas += 1
            time.sleep(ATRASO_JUIZ)
            return cenario != "recusa" and not (cenario == "saida_alterada" and chamadas > 1)

        try:
            if cenario == "bloqueio":
                status = "bloqueado"
            elif cenario == "excecao":
                raise RuntimeError("falha simulada")
            elif modo == "adiada":
                time.sleep(ATRASO_ORQUESTRADOR)
                if julgar():
                    abrir()
                    gravar()
                    conexao.commit()
            elif modo == "transacao":
                abrir()
                gravar()
                time.sleep(ATRASO_ORQUESTRADOR)
                if julgar():
                    conexao.commit()
                else:
                    conexao.rollback()
            elif modo == "pre_validacao":
                if julgar():
                    abrir()
                    gravar()
                    conexao.commit()
                    time.sleep(ATRASO_ORQUESTRADOR)
                    if not julgar():
                        conteudo_invalido = True
            elif modo == "compensacao":
                abrir()
                gravar()
                conexao.commit()
                exposicao = contar(marcador)
                time.sleep(ATRASO_ORQUESTRADOR)
                if not julgar():
                    with conexao.cursor() as cursor:
                        cursor.execute(f"DELETE FROM {tabela} WHERE marcador = %s", (marcador,))
                    conexao.commit()
            elif modo == "flag":
                if julgar():
                    abrir()
                    gravar()
                    conexao.commit()
                    time.sleep(ATRASO_ORQUESTRADOR)
                    conteudo_invalido = cenario == "saida_alterada"
            else:
                raise ValueError(modo)
        except Exception:
            status = "erro"
            if conexao:
                conexao.rollback()
        finally:
            if conexao:
                tempo_conexao = (time.perf_counter() - inicio_conexao) * 1000
                conexao.close()
        return {
            "status": status, "latencia_ms": (time.perf_counter() - inicio) * 1000,
            "conexao_ms": tempo_conexao, "chamadas_juiz": chamadas,
            "efeitos_sql": efeitos, "exposicao_antes_veredito": exposicao,
            "restantes": contar(marcador), "saida_invalida": conteudo_invalido,
        }

    try:
        amostras = [turno("aprovacao") for _ in range(AMOSTRAS)]
        casos = {nome_caso: turno(nome_caso) for nome_caso in ("recusa", "falha_sql", "bloqueio", "excecao")}
        if modo in ("flag", "pre_validacao"):
            casos["saida_alterada"] = turno("saida_alterada")
            assert casos["saida_alterada"]["restantes"] == 1
            assert casos["saida_alterada"]["saida_invalida"]
        assert all(item["restantes"] == 1 and item["status"] == "ok" for item in amostras)
        assert casos["recusa"]["restantes"] == 0
        assert casos["falha_sql"]["status"] == "erro" and casos["falha_sql"]["restantes"] == 0
        assert casos["bloqueio"]["status"] == "bloqueado" and casos["bloqueio"]["restantes"] == 0
        assert casos["excecao"]["status"] == "erro" and casos["excecao"]["restantes"] == 0
        valores = sorted(item["latencia_ms"] for item in amostras)
        p95 = valores[math.ceil(len(valores) * 0.95) - 1]
        conexoes = [item["conexao_ms"] for item in amostras]
        todos = amostras + list(casos.values())
        erros = sum(item["status"] == "erro" for item in todos)
        chamadas = sum(item["chamadas_juiz"] for item in amostras) / len(amostras)
        linhas = [
            f"# {nome}", "", "## Método", "",
            f"{AMOSTRAS} turnos aprovados sequenciais, mais cenários controlados; PostgreSQL em container isolado. "
            f"Juiz simulado: {ATRASO_JUIZ * 1000:.0f} ms por chamada; orquestrador simulado: {ATRASO_ORQUESTRADOR * 1000:.0f} ms. "
            "Os modelos, Google Calendar e o grafo real não são executados.", "",
            "## Indicadores", "", "| Indicador | Resultado |", "|---|---:|",
            f"| Latência média dos aprovados | {statistics.mean(valores):.2f} ms |",
            f"| Latência p95 dos aprovados (limite 8 s) | {p95:.2f} ms |",
            f"| Conexão aberta média dos aprovados | {statistics.mean(conexoes):.2f} ms |",
            f"| Chamadas simuladas ao juiz por aprovação | {chamadas:.1f} |",
            f"| Taxa de erro nos cenários controlados (limite 5%) | {erros / len(todos):.1%} ({erros}/{len(todos)}) |",
            f"| Status ok / erro / bloqueado | {sum(x['status'] == 'ok' for x in todos)} / {erros} / {sum(x['status'] == 'bloqueado' for x in todos)} |",
            "| Tokens reais / custo real | Não medidos |", "",
            "A taxa inclui falhas injetadas deliberadamente e não estima a taxa de erro em produção. "
            "A latência inclui a espera simulada, gravação e commit; o tempo de conexão começa após conectar. "
            "Bloqueios entram no denominador, mas não no numerador de erros.", "",
            "## Cenários", "", "| Cenário | Status | Registros finais | SQL executado | Visível antes do veredito | Chamadas ao juiz | Saída final rejeitada ou não reavaliada |", "|---|---|---:|---:|---:|---:|---|",
        ]
        for caso, item in casos.items():
            linhas.append(f"| {caso} | {item['status']} | {item['restantes']} | {item['efeitos_sql']} | {item['exposicao_antes_veredito']} | {item['chamadas_juiz']} | {'sim' if item['saida_invalida'] else 'não'} |")
        linhas += ["", "Cada cenário usa marcador único. `SQL executado` conta inserções executadas, inclusive as revertidas; "
                   "a visibilidade é consultada por outra conexão somente na compensação. Uma aprovação escreve uma linha; "
                   "isso não demonstra idempotência em uma repetição. A falha SQL é uma violação de chave dentro da transação.",
                   "", "A simulação não mede concorrência, falha do commit, timeout real, queda do processo ou custo de modelos. "
                   "Ela não comprova a execução das tools reais nem a qualidade do julgamento."]
        PASTA.mkdir(parents=True, exist_ok=True)
        arquivo = PASTA / f"{nome}.md"
        arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        print(f"Cenários verificados; relatório: {arquivo}")
    finally:
        with psycopg2.connect(DSN) as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"DROP TABLE {tabela}")
