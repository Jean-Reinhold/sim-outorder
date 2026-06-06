#!/usr/bin/env python3
"""Generate Jean Reinhold's technical LI_3/VORTEX_2 report from measured data."""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ["LI_3", "VORTEX_2"]
TASK4_FINAL = {
    "LI_3": ["task4_li3_economico", "task4_li3_equilibrado", "task4_li3_robusto"],
    "VORTEX_2": ["task4_vortex2_economico", "task4_vortex2_memoria", "task4_vortex2_robusto"],
}
TASK4_LABELS = {
    "task4_li3_economico": "Econômico",
    "task4_li3_equilibrado": "Equilibrado",
    "task4_li3_robusto": "Robusto",
    "task4_vortex2_economico": "Econômico",
    "task4_vortex2_memoria": "Memória",
    "task4_vortex2_robusto": "Robusto",
}

# Heuristic only. It is used to reason about tradeoffs, not as a physical area model.
COST_WEIGHTS = {
    "fetch:ifqsize": 0.5,
    "decode:width": 2.0,
    "issue:width": 3.0,
    "commit:width": 2.0,
    "ruu:size": 0.4,
    "lsq:size": 0.7,
    "res:ialu": 3.0,
    "res:imult": 6.0,
    "res:fpalu": 3.0,
    "res:fpmult": 6.0,
    "res:memport": 10.0,
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return h(value)


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


def metric(run: dict[str, Any] | None, name: str) -> int | float | None:
    if not run:
        return None
    value = run.get("stats", {}).get(name)
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def cpi(run: dict[str, Any] | None) -> float | None:
    value = metric(run, "sim_CPI")
    return float(value) if value is not None else None


def cycles(run: dict[str, Any] | None) -> int | float | None:
    return metric(run, "sim_cycle")


def cost_index(options: dict[str, Any]) -> float:
    total = 0.0
    for name, weight in COST_WEIGHTS.items():
        value = options.get(name)
        if isinstance(value, (int, float)):
            total += float(value) * weight
    return total


def run_cost(run: dict[str, Any] | None) -> float | None:
    if not run:
        return None
    return cost_index(run.get("options", {}))


def load_store_ratio(bench: dict[str, Any]) -> float | None:
    total = bench.get("total_instructions")
    load_store = bench.get("load_store_instructions")
    if not isinstance(total, (int, float)) or not isinstance(load_store, (int, float)) or total <= 0:
        return None
    return load_store / total * 100


def rel_drop(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before == 0:
        return None
    return (before - after) / before * 100


def rel_increase(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before == 0:
        return None
    return (after - before) / before * 100


def runs_for(data: dict[str, Any], benchmark: str, task: str | None = None) -> list[dict[str, Any]]:
    runs = [run for run in data.get("runs", []) if run.get("benchmark") == benchmark and run.get("status") == "completed"]
    if task:
        runs = [run for run in runs if run.get("task") == task]
    return runs


def find_run(data: dict[str, Any], benchmark: str, experiment: str) -> dict[str, Any] | None:
    for run in data.get("runs", []):
        if run.get("benchmark") == benchmark and run.get("experiment") == experiment:
            return run
    return None


def predictor(run: dict[str, Any]) -> str:
    return str(run.get("options", {}).get("bpred", "bimod"))


def first_metric(run: dict[str, Any] | None, suffix: str, prefix: str | None = None) -> int | float | None:
    if not run:
        return None
    for key in sorted(run.get("stats", {})):
        if prefix and not key.startswith(prefix):
            continue
        if key.endswith(suffix):
            value = run["stats"][key]
            if isinstance(value, (int, float)) and math.isfinite(value):
                return value
    return None


def width_run(data: dict[str, Any], benchmark: str, width: int, inorder: bool) -> dict[str, Any] | None:
    return next(
        (
            run
            for run in runs_for(data, benchmark, "Tarefa 1")
            if run.get("options", {}).get("issue:width") == width
            and run.get("options", {}).get("issue:inorder") is inorder
        ),
        None,
    )


def window_run(data: dict[str, Any], benchmark: str, ruu: int) -> dict[str, Any] | None:
    return next((run for run in runs_for(data, benchmark, "Tarefa 2") if run.get("options", {}).get("ruu:size") == ruu), None)


def pred_run(data: dict[str, Any], benchmark: str, name: str) -> dict[str, Any] | None:
    return next((run for run in runs_for(data, benchmark, "Tarefa 3") if predictor(run) == name), None)


def task4_search_note(search: dict[str, Any] | None) -> str:
    if not search:
        return "A busca exploratória da Tarefa 4 não está disponível neste build."
    completed = len([run for run in search.get("runs", []) if run.get("status") == "completed"])
    total = len(search.get("runs", []))
    return f"A busca exploratória da Tarefa 4 teve {completed}/{total} simulações completas."


def qa(question: str, body: str) -> str:
    return f"""
    <article class="qa">
      <p class="question-label">Pergunta do enunciado</p>
      <h4>{h(question)}</h4>
      {body}
    </article>
    """


def benchmark_profile_table(data: dict[str, Any]) -> str:
    rows = []
    for benchmark in BENCHMARKS:
        bench = data.get("benchmarks", {}).get(benchmark, {})
        rows.append(
            "<tr>"
            f"<td><strong>{h(benchmark)}</strong></td>"
            f"<td>{h(bench.get('family', '-'))}</td>"
            f"<td>{h(bench.get('input'))}</td>"
            f"<td>{fmt(bench.get('total_instructions'))}</td>"
            f"<td>{fmt(bench.get('load_store_instructions'))}</td>"
            f"<td>{pct(load_store_ratio(bench))}</td>"
            f"<td>{h(bench.get('description', ''))}</td>"
            "</tr>"
        )
    return f"""
    <table>
      <thead><tr><th>benchmark</th><th>família</th><th>entrada</th><th>instruções</th><th>load/store</th><th>fração</th><th>descrição</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


def task1_table(data: dict[str, Any], benchmark: str) -> str:
    rows = []
    for width in [1, 2, 4, 8]:
        in_run = width_run(data, benchmark, width, True)
        ooo_run = width_run(data, benchmark, width, False)
        in_cpi = cpi(in_run)
        ooo_cpi = cpi(ooo_run)
        rows.append(
            f"<tr><td>{width}</td><td>{fmt(in_cpi)}</td><td>{fmt(ooo_cpi)}</td>"
            f"<td>{pct(rel_drop(in_cpi, ooo_cpi))}</td><td>{fmt(cycles(in_run))}</td><td>{fmt(cycles(ooo_run))}</td></tr>"
        )
    return f"""
    <table><thead><tr><th>largura</th><th>CPI em ordem</th><th>CPI fora de ordem</th><th>redução OOO</th><th>ciclos em ordem</th><th>ciclos fora de ordem</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def task2_table(data: dict[str, Any], benchmark: str) -> str:
    runs = sorted(runs_for(data, benchmark, "Tarefa 2"), key=lambda run: run.get("options", {}).get("ruu:size", 0))
    baseline = cpi(runs[0]) if runs else None
    rows = []
    for run in runs:
        value = cpi(run)
        rows.append(
            f"<tr><td>{fmt(run.get('options', {}).get('ruu:size'))}</td>"
            f"<td>{fmt(run.get('options', {}).get('lsq:size'))}</td>"
            f"<td>{fmt(value)}</td><td>{fmt(cycles(run))}</td><td>{pct(rel_drop(baseline, value))}</td></tr>"
        )
    return f"""
    <table><thead><tr><th>RUU</th><th>LSQ</th><th>CPI</th><th>ciclos</th><th>ganho vs RUU 4</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def task3_table(data: dict[str, Any], benchmark: str) -> str:
    perfect = pred_run(data, benchmark, "perfect")
    perfect_cpi = cpi(perfect)
    rows = []
    for name in ["perfect", "bimod", "taken", "nottaken"]:
        run = pred_run(data, benchmark, name)
        value = cpi(run)
        rows.append(
            f"<tr><td>{h(name)}</td><td>{fmt(value)}</td><td>{fmt(cycles(run))}</td>"
            f"<td>{fmt(first_metric(run, 'bpred_dir_rate', 'bpred_'))}</td>"
            f"<td>{fmt(first_metric(run, 'misses', 'bpred_'))}</td><td>{pct(rel_increase(perfect_cpi, value))}</td></tr>"
        )
    return f"""
    <table><thead><tr><th>previsor</th><th>CPI</th><th>ciclos</th><th>taxa direção</th><th>misses</th><th>vs perfect</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def task4_table(data: dict[str, Any], benchmark: str) -> str:
    rows = []
    for experiment in TASK4_FINAL[benchmark]:
        run = find_run(data, benchmark, experiment)
        options = run.get("options", {}) if run else {}
        rows.append(
            f"<tr><td><strong>{h(TASK4_LABELS.get(experiment, experiment))}</strong><br><code>{h(experiment)}</code></td>"
            f"<td>{fmt(cpi(run))}</td><td>{fmt(cycles(run))}</td><td>{fmt(cost_index(options), 1)}</td>"
            f"<td>{fmt(options.get('issue:width'))}</td><td>{fmt(options.get('ruu:size'))}</td><td>{fmt(options.get('lsq:size'))}</td>"
            f"<td>{fmt(options.get('res:memport'))}</td><td>{fmt(options.get('res:ialu'))}</td><td>{fmt(options.get('res:imult'))}</td>"
            f"<td>{fmt(options.get('res:fpalu'))}/{fmt(options.get('res:fpmult'))}</td></tr>"
        )
    return f"""
    <table><thead><tr><th>configuração</th><th>CPI</th><th>ciclos</th><th>custo</th><th>width</th><th>RUU</th><th>LSQ</th><th>mem</th><th>IALU</th><th>IMult</th><th>FP</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def coverage_table() -> str:
    rows = [
        ("Tarefa 1", "Impacto da largura", "Seção 2, Pergunta 1"),
        ("Tarefa 1", "Impacto da execução fora de ordem", "Seção 2, Pergunta 2"),
        ("Tarefa 1", "Pipeline largo em ordem ou fora de ordem", "Seção 2, Pergunta 3"),
        ("Tarefa 2", "Impacto de janelas maiores", "Seção 3, Pergunta 1"),
        ("Tarefa 2", "Saturação da melhoria", "Seção 3, Pergunta 2"),
        ("Tarefa 3", "Estatísticas do previsor", "Seção 4, Pergunta 1"),
        ("Tarefa 3", "Impacto em relação ao perfect", "Seção 4, Pergunta 2"),
        ("Tarefa 3", "Ganho relativo do bimodal", "Seção 4, Pergunta 3"),
        ("Tarefa 4", "Menor CPI por benchmark", "Seção 5, Pergunta 1"),
        ("Tarefa 4", "Justificativa do custo", "Seção 5, Pergunta 2"),
        ("Tarefa 4", "Custos além de CPI", "Seção 5, Pergunta 3"),
    ]
    body = "".join(f"<tr><td>{h(task)}</td><td>{h(question)}</td><td>{h(where)}</td></tr>" for task, question, where in rows)
    return f"""
    <table><thead><tr><th>tarefa</th><th>pergunta coberta</th><th>onde está respondida</th></tr></thead><tbody>{body}</tbody></table>
    """


def task1_answers(data: dict[str, Any]) -> str:
    li_w1_in = cpi(width_run(data, "LI_3", 1, True))
    li_w8_in = cpi(width_run(data, "LI_3", 8, True))
    li_w1_ooo = cpi(width_run(data, "LI_3", 1, False))
    li_w8_ooo = cpi(width_run(data, "LI_3", 8, False))
    vo_w1_in = cpi(width_run(data, "VORTEX_2", 1, True))
    vo_w8_in = cpi(width_run(data, "VORTEX_2", 8, True))
    vo_w1_ooo = cpi(width_run(data, "VORTEX_2", 1, False))
    vo_w8_ooo = cpi(width_run(data, "VORTEX_2", 8, False))

    return "".join(
        [
            qa(
                "Qual é o impacto em CPI de permitir mais instruções por ciclo?",
                f"""
                <p>O impacto é positivo nos dois benchmarks: aumentar a largura reduz o CPI. No LI_3, considerando execução em ordem, a largura 1 mede CPI {fmt(li_w1_in)} e a largura 8 mede CPI {fmt(li_w8_in)}, uma redução de {pct(rel_drop(li_w1_in, li_w8_in))}. Com execução fora de ordem, a redução é maior: CPI {fmt(li_w1_ooo)} em largura 1 contra CPI {fmt(li_w8_ooo)} em largura 8, queda de {pct(rel_drop(li_w1_ooo, li_w8_ooo))}.</p>
                <p>No VORTEX_2, a largura 1 em ordem mede CPI {fmt(vo_w1_in)} e a largura 8 em ordem mede {fmt(vo_w8_in)}, queda de {pct(rel_drop(vo_w1_in, vo_w8_in))}. Fora de ordem, o CPI cai de {fmt(vo_w1_ooo)} para {fmt(vo_w8_ooo)}, redução de {pct(rel_drop(vo_w1_ooo, vo_w8_ooo))}. Portanto, a largura aumenta a capacidade de emissão, mas o ganho pleno depende da existência e exploração de paralelismo entre instruções.</p>
                """,
            ),
            qa(
                "Qual é o impacto em CPI do uso de execução fora de ordem?",
                f"""
                <p>A execução fora de ordem tem pouco efeito quando a largura é 1, mas passa a ser decisiva quando a largura cresce. Em largura 1, o LI_3 melhora apenas {pct(rel_drop(li_w1_in, li_w1_ooo))} e o VORTEX_2 melhora {pct(rel_drop(vo_w1_in, vo_w1_ooo))}. Isso é coerente com a limitação estrutural de uma máquina escalar: mesmo que haja reordenação, há pouca capacidade de emitir várias instruções úteis por ciclo.</p>
                <p>Em largura 8, a diferença é grande. No LI_3, o CPI cai de {fmt(li_w8_in)} em ordem para {fmt(li_w8_ooo)} fora de ordem, redução de {pct(rel_drop(li_w8_in, li_w8_ooo))}. No VORTEX_2, o CPI cai de {fmt(vo_w8_in)} para {fmt(vo_w8_ooo)}, redução de {pct(rel_drop(vo_w8_in, vo_w8_ooo))}. A interpretação é que fora de ordem transforma largura disponível em trabalho executado, escondendo parte das bolhas causadas por dependências e memória.</p>
                """,
            ),
            qa(
                "Um pipeline mais largo é mais efetivo em ordem ou fora de ordem?",
                f"""
                <p>Os dados mostram que um pipeline largo é mais efetivo fora de ordem. Em largura 8, o LI_3 fica em CPI {fmt(li_w8_in)} quando em ordem e em CPI {fmt(li_w8_ooo)} quando fora de ordem. O VORTEX_2 fica em CPI {fmt(vo_w8_in)} em ordem e {fmt(vo_w8_ooo)} fora de ordem.</p>
                <p>Assim, a largura por si só não resolve a questão. Um pipeline largo em ordem ainda precisa respeitar bloqueios na sequência de emissão. A execução fora de ordem permite que instruções independentes avancem enquanto outras aguardam, e por isso aproveita melhor a largura.</p>
                """,
            ),
        ]
    )


def task2_answers(data: dict[str, Any]) -> str:
    li_4 = cpi(window_run(data, "LI_3", 4))
    li_8 = cpi(window_run(data, "LI_3", 8))
    li_32 = cpi(window_run(data, "LI_3", 32))
    li_64 = cpi(window_run(data, "LI_3", 64))
    vo_4 = cpi(window_run(data, "VORTEX_2", 4))
    vo_8 = cpi(window_run(data, "VORTEX_2", 8))
    vo_32 = cpi(window_run(data, "VORTEX_2", 32))
    vo_64 = cpi(window_run(data, "VORTEX_2", 64))

    return "".join(
        [
            qa(
                "Qual é o impacto em CPI ao utilizar janelas maiores?",
                f"""
                <p>Janelas maiores reduzem CPI nos dois benchmarks. No LI_3, a configuração RUU 4 / LSQ 2 mede CPI {fmt(li_4)}, enquanto RUU 64 / LSQ 32 mede CPI {fmt(li_64)}; a redução acumulada é de {pct(rel_drop(li_4, li_64))}. No VORTEX_2, o CPI cai de {fmt(vo_4)} para {fmt(vo_64)}, redução de {pct(rel_drop(vo_4, vo_64))}.</p>
                <p>A primeira ampliação já mostra efeito relevante. De RUU 4 para 8, o LI_3 melhora {pct(rel_drop(li_4, li_8))}, e o VORTEX_2 melhora {pct(rel_drop(vo_4, vo_8))}. Isso indica que uma janela pequena restringe a capacidade da execução fora de ordem encontrar instruções prontas.</p>
                """,
            ),
            qa(
                "A melhoria satura em algum tamanho de janela?",
                f"""
                <p>Não há saturação completa até RUU 64, mas há redução do ganho marginal. No LI_3, passar de RUU 32 para 64 reduz o CPI de {fmt(li_32)} para {fmt(li_64)}, ganho adicional de {pct(rel_drop(li_32, li_64))}. No VORTEX_2, o mesmo trecho reduz de {fmt(vo_32)} para {fmt(vo_64)}, ganho adicional de {pct(rel_drop(vo_32, vo_64))}.</p>
                <p>Minha conclusão é que RUU 32 e RUU 64 entram numa região de compromisso: ainda há melhoria, mas ela já não é tão expressiva quanto nos primeiros aumentos. Para a Tarefa 4, isso justifica testar janela grande, mas obriga a discutir custo de RUU, LSQ e lógica de seleção.</p>
                """,
            ),
        ]
    )


def task3_answers(data: dict[str, Any]) -> str:
    li_perfect = pred_run(data, "LI_3", "perfect")
    li_bimod = pred_run(data, "LI_3", "bimod")
    li_taken = pred_run(data, "LI_3", "taken")
    li_nottaken = pred_run(data, "LI_3", "nottaken")
    vo_perfect = pred_run(data, "VORTEX_2", "perfect")
    vo_bimod = pred_run(data, "VORTEX_2", "bimod")
    vo_taken = pred_run(data, "VORTEX_2", "taken")
    vo_nottaken = pred_run(data, "VORTEX_2", "nottaken")
    li_perfect_cpi = cpi(li_perfect)
    vo_perfect_cpi = cpi(vo_perfect)

    return "".join(
        [
            qa(
                "Quais estatísticas de uso do previsor aparecem para cada benchmark?",
                f"""
                <p>As estatísticas mais importantes são a taxa de acerto de direção e o número de erros. No LI_3, o bimodal apresenta taxa de direção {fmt(first_metric(li_bimod, 'bpred_dir_rate', 'bpred_'))} e {fmt(first_metric(li_bimod, 'misses', 'bpred_'))} misses. No VORTEX_2, o bimodal apresenta taxa {fmt(first_metric(vo_bimod, 'bpred_dir_rate', 'bpred_'))} e {fmt(first_metric(vo_bimod, 'misses', 'bpred_'))} misses.</p>
                <p>Os preditores estáticos aparecem com taxa de direção bem menor: no LI_3, taken/nottaken ficam em torno de {fmt(first_metric(li_taken, 'bpred_dir_rate', 'bpred_'))}; no VORTEX_2, ficam em torno de {fmt(first_metric(vo_taken, 'bpred_dir_rate', 'bpred_'))}. Isso confirma que uma regra fixa não representa bem os padrões de desvio desses programas.</p>
                """,
            ),
            qa(
                "Quanto a previsão de desvios afeta o CPI em relação ao previsor perfeito?",
                f"""
                <p>No LI_3, o perfect mede CPI {fmt(li_perfect_cpi)}. O bimodal mede {fmt(cpi(li_bimod))}, ou {pct(rel_increase(li_perfect_cpi, cpi(li_bimod)))} acima do perfect. Os estáticos são bem piores: taken mede CPI {fmt(cpi(li_taken))}, e nottaken mede {fmt(cpi(li_nottaken))}. Portanto, para o LI_3, erro de desvio é uma fonte importante de perda.</p>
                <p>No VORTEX_2, o perfect mede CPI {fmt(vo_perfect_cpi)}. O bimodal medido ficou em CPI {fmt(cpi(vo_bimod))}, ligeiramente abaixo do perfect. Não interpretei isso como superioridade real do bimodal; a leitura conservadora é que há uma interação específica do simulador/configuração, e que o bimodal já remove quase todo o custo relevante dos desvios nesse caso. Os estáticos continuam piores, com CPI {fmt(cpi(vo_taken))} em taken e {fmt(cpi(vo_nottaken))} em nottaken.</p>
                """,
            ),
            qa(
                "Qual é o ganho relativo de um previsor bimodal?",
                f"""
                <p>No LI_3, o bimodal reduz o CPI em {pct(rel_drop(cpi(li_nottaken), cpi(li_bimod)))} contra nottaken e {pct(rel_drop(cpi(li_taken), cpi(li_bimod)))} contra taken. O ganho é grande porque os preditores estáticos erram muitos desvios.</p>
                <p>No VORTEX_2, o bimodal reduz o CPI em {pct(rel_drop(cpi(vo_nottaken), cpi(vo_bimod)))} contra nottaken e {pct(rel_drop(cpi(vo_taken), cpi(vo_bimod)))} contra taken. Como a taxa de direção do bimodal fica em {fmt(first_metric(vo_bimod, 'bpred_dir_rate', 'bpred_'))}, a maior parte do comportamento de branch foi capturada por uma estrutura simples de contadores saturantes.</p>
                """,
            ),
        ]
    )


def task4_answers(data: dict[str, Any]) -> str:
    li_econ = find_run(data, "LI_3", "task4_li3_economico")
    li_bal = find_run(data, "LI_3", "task4_li3_equilibrado")
    li_rob = find_run(data, "LI_3", "task4_li3_robusto")
    vo_econ = find_run(data, "VORTEX_2", "task4_vortex2_economico")
    vo_mem = find_run(data, "VORTEX_2", "task4_vortex2_memoria")
    vo_rob = find_run(data, "VORTEX_2", "task4_vortex2_robusto")
    vortex_ratio = load_store_ratio(data.get("benchmarks", {}).get("VORTEX_2", {}))

    return "".join(
        [
            qa(
                "Qual configuração teve o menor CPI para cada benchmark?",
                f"""
                <p>No LI_3, o menor CPI entre as três configurações finais foi o robusto: CPI {fmt(cpi(li_rob))}, ciclos {fmt(cycles(li_rob))}, largura 8, RUU 128, LSQ 64 e quatro portas de memória. A configuração equilibrada ficou em CPI {fmt(cpi(li_bal))}, e a econômica em CPI {fmt(cpi(li_econ))}.</p>
                <p>No VORTEX_2, o menor CPI também foi o robusto: CPI {fmt(cpi(vo_rob))}, ciclos {fmt(cycles(vo_rob))}, largura 8, RUU 128, LSQ 128 e quatro portas de memória. A configuração memória ficou em CPI {fmt(cpi(vo_mem))}, e a econômica em CPI {fmt(cpi(vo_econ))}.</p>
                """,
            ),
            qa(
                "A configuração vencedora justifica seu custo arquitetural?",
                f"""
                <p>Para o LI_3, a robusta reduz o CPI em {pct(rel_drop(cpi(li_bal), cpi(li_rob)))} em relação à equilibrada, mas aumenta o índice de custo de {fmt(run_cost(li_bal), 1)} para {fmt(run_cost(li_rob), 1)}, crescimento de {pct(rel_increase(run_cost(li_bal), run_cost(li_rob)))}. Se o critério for exclusivamente CPI, a robusta vence. Se o critério for custo-benefício, a equilibrada é mais defensável: ela mantém CPI {fmt(cpi(li_bal))} com custo muito menor.</p>
                <p>Para o VORTEX_2, a robusta reduz o CPI em {pct(rel_drop(cpi(vo_mem), cpi(vo_rob)))} frente à configuração memória, mas o custo sobe de {fmt(run_cost(vo_mem), 1)} para {fmt(run_cost(vo_rob), 1)}, crescimento de {pct(rel_increase(run_cost(vo_mem), run_cost(vo_rob)))}. Como o VORTEX_2 tem {pct(vortex_ratio)} de instruções load/store, faz sentido priorizar LSQ e portas de memória. Mesmo assim, LSQ 128 é um salto caro para o ganho medido. Assim, a robusta é vencedora em CPI; a configuração memória é a alternativa que eu escolheria se custo arquitetural tivesse peso maior.</p>
                """,
            ),
            qa(
                "Além de CPI, quais parâmetros de custo devem ser avaliados?",
                """
                <p>Além de CPI, eu avaliaria área, energia dinâmica, energia estática, frequência máxima de clock, complexidade da lógica de wakeup/select da RUU, quantidade de comparadores da LSQ, número de portas da cache L1, rede de bypass, pressão no rename/commit e esforço de verificação. Essas variáveis são justamente as que aumentam quando se amplia largura, janela, filas e portas de memória.</p>
                <p>Também é necessário distinguir recurso útil de recurso apenas caro. Para estes benchmarks, janela, LSQ e memória aparecem como recursos com justificativa experimental. Já ampliar unidades de ponto flutuante não se justifica pelos dados medidos, pois as cargas analisadas são predominantemente inteiras.</p>
                """,
            ),
        ]
    )


def css() -> str:
    return """
:root { --paper:#fffaf0; --ink:#1f252b; --muted:#626b73; --rule:#c7bbab; --soft:#f2eadc; --accent:#563722; --accent2:#164f63; }
* { box-sizing: border-box; }
body { margin:0; background:#d8d0c2; color:var(--ink); font:17px/1.65 Georgia, "Times New Roman", serif; }
a { color:var(--accent2); }
.page { width:min(100% - 28px, 1040px); margin:28px auto; background:var(--paper); border:1px solid #b9ad9d; box-shadow:0 18px 50px rgba(40,30,20,.2); }
header.cover { padding:46px 56px 30px; border-bottom:3px double var(--rule); }
.kicker { margin:0 0 18px; color:var(--accent); font:700 12px/1.3 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing:.12em; text-transform:uppercase; }
h1 { margin:0; max-width:820px; font-size:clamp(2.1rem,5vw,4.1rem); line-height:1.02; letter-spacing:-.04em; }
.subtitle { max-width:780px; margin:18px 0 0; color:#37424a; font-size:1.08rem; }
.meta { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px 28px; margin:28px 0 0; padding-top:18px; border-top:1px solid var(--rule); }
.meta div { display:grid; grid-template-columns:130px 1fr; gap:12px; }
.meta dt { color:var(--muted); font-style:italic; }
.meta dd { margin:0; font-weight:700; }
nav { display:flex; flex-wrap:wrap; gap:4px 18px; padding:14px 56px; border-bottom:1px solid var(--rule); background:#f7efe1; font:13px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
nav a { text-decoration:none; }
main { padding:34px 56px 56px; }
section { margin:0 0 42px; }
section + section { padding-top:34px; border-top:1px solid var(--rule); }
h2 { margin:0 0 10px; color:var(--accent); font-size:1.8rem; line-height:1.18; }
h3 { margin:26px 0 8px; font-size:1.18rem; color:#26323a; }
h4 { margin:3px 0 10px; font-size:1.05rem; line-height:1.35; }
p { margin:0 0 13px; }
.section-note { color:#3d4850; max-width:850px; }
.method, .conclusion { padding:16px 18px; border:1px solid var(--rule); background:var(--soft); }
.qa { margin:16px 0; padding:16px 18px 10px; border-left:4px solid var(--accent2); background:#fffdf7; }
.question-label { margin:0; color:var(--muted); font:700 11px/1.3 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing:.08em; text-transform:uppercase; }
.table-wrap { overflow-x:auto; margin:10px 0 18px; border:1px solid var(--rule); background:#fffdf8; }
table { width:100%; border-collapse:collapse; font-size:.88rem; }
th, td { padding:7px 9px; border-bottom:1px solid #ded4c4; text-align:right; vertical-align:top; }
th:first-child, td:first-child { text-align:left; }
td:last-child { white-space:normal; }
th { color:#4f5b64; background:#efe6d6; font:700 11px/1.3 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing:.04em; text-transform:uppercase; }
code { color:#0d4b60; font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:.92em; }
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:22px; }
.muted { color:var(--muted); }
footer { padding:22px 56px 34px; color:var(--muted); border-top:1px solid var(--rule); font-size:.92rem; }
@media (max-width:820px) { .page { width:100%; margin:0; border-left:0; border-right:0; } header.cover, main, nav, footer { padding-left:22px; padding-right:22px; } .meta, .two-col { grid-template-columns:1fr; } .meta div { grid-template-columns:110px 1fr; } }
@media print { body { background:#fff; } .page { width:100%; margin:0; border:0; box-shadow:none; } nav { display:none; } a { color:inherit; text-decoration:none; } }
    """


def build_html(final: dict[str, Any], search: dict[str, Any] | None) -> str:
    search_note = task4_search_note(search)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Relatório técnico · Jean Reinhold · LI_3 e VORTEX_2</title>
  <style>{css()}</style>
</head>
<body>
  <div class="page">
    <header class="cover">
      <p class="kicker">UFPel · Arquitetura Avançada · SimpleScalar sim-outorder</p>
      <h1>Jean Reinhold: LI_3 e VORTEX_2</h1>
      <p class="subtitle">Relatório técnico dos experimentos com processadores superescalares. O texto responde, uma a uma, às perguntas do enunciado e usa os resultados medidos para sustentar as interpretações.</p>
      <dl class="meta">
        <div><dt>Autor</dt><dd>Jean Reinhold</dd></div>
        <div><dt>Benchmarks</dt><dd>LI_3 e VORTEX_2</dd></div>
        <div><dt>Simulador</dt><dd>SimpleScalar sim-outorder</dd></div>
        <div><dt>Dados</dt><dd><a href="data/jean-final-results.json">resultados oficiais em JSON</a></dd></div>
      </dl>
    </header>
    <nav aria-label="Sumário"><a href="index.html">relatório geral</a><a href="#perfil">perfil</a><a href="#cobertura">cobertura</a><a href="#t1">tarefa 1</a><a href="#t2">tarefa 2</a><a href="#t3">tarefa 3</a><a href="#t4">tarefa 4</a><a href="#dados">dados</a></nav>
    <main>
      <section id="perfil">
        <h2>1. Perfil dos benchmarks e método</h2>
        <p class="section-note">A análise foi limitada aos benchmarks atribuídos a Jean Reinhold. O LI_3 executa um interpretador Lisp com a entrada <code>train.lsp</code>. O VORTEX_2 executa uma carga de banco de dados orientado a objetos com entrada <code>tiny.in</code>. A diferença mais importante para a interpretação é a fração de instruções load/store: ela é maior no VORTEX_2, o que ajuda a explicar a importância de LSQ e portas de memória na customização.</p>
        <div class="table-wrap">{benchmark_profile_table(final)}</div>
        <div class="method"><p><strong>Método.</strong> As tarefas 1 a 3 seguem diretamente as configurações pedidas no enunciado. Na Tarefa 4, primeiro foi feita uma busca exploratória mais ampla e depois foram selecionadas somente três configurações finais por benchmark, mantendo a restrição do trabalho. {h(search_note)}</p></div>
      </section>
      <section id="cobertura">
        <h2>2. Cobertura explícita das perguntas</h2>
        <p class="section-note">A tabela abaixo funciona como checklist do enunciado: cada pergunta pedida no PDF aparece respondida por extenso nas seções seguintes.</p>
        <div class="table-wrap">{coverage_table()}</div>
      </section>
      <section id="t1">
        <h2>3. Tarefa 1 - execução em ordem e fora de ordem</h2>
        <p class="section-note">Objetivo: medir ciclos e CPI para larguras 1, 2, 4 e 8, comparando emissão em ordem com emissão fora de ordem.</p>
        <div class="two-col"><div><h3>LI_3</h3><div class="table-wrap">{task1_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task1_table(final, 'VORTEX_2')}</div></div></div>
        <h3>Perguntas do enunciado</h3>
        {task1_answers(final)}
      </section>
      <section id="t2">
        <h2>4. Tarefa 2 - tamanho da janela de instruções</h2>
        <p class="section-note">Objetivo: medir o efeito do tamanho da RUU em execução fora de ordem. Como a LSQ cresce junto com a RUU nestas configurações, a interpretação considera o conjunto janela de instruções mais fila de load/store.</p>
        <div class="two-col"><div><h3>LI_3</h3><div class="table-wrap">{task2_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task2_table(final, 'VORTEX_2')}</div></div></div>
        <h3>Perguntas do enunciado</h3>
        {task2_answers(final)}
      </section>
      <section id="t3">
        <h2>5. Tarefa 3 - previsão de desvios</h2>
        <p class="section-note">Objetivo: comparar <code>nottaken</code>, <code>taken</code> e <code>bimod</code>, usando <code>perfect</code> como referência. O bimodal usa uma tabela de contadores saturantes de 2 bits, indexada pelo endereço do desvio.</p>
        <div class="two-col"><div><h3>LI_3</h3><div class="table-wrap">{task3_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task3_table(final, 'VORTEX_2')}</div></div></div>
        <h3>Perguntas do enunciado</h3>
        {task3_answers(final)}
      </section>
      <section id="t4">
        <h2>6. Tarefa 4 - customização do processador</h2>
        <p class="section-note">Objetivo: testar até três configurações especializadas por benchmark e discutir desempenho contra custo. O índice de custo abaixo é heurístico; ele foi usado para organizar a comparação, não como estimativa física de área.</p>
        <div class="two-col"><div><h3>LI_3</h3><div class="table-wrap">{task4_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task4_table(final, 'VORTEX_2')}</div></div></div>
        <h3>Perguntas do enunciado</h3>
        {task4_answers(final)}
      </section>
      <section id="dados">
        <h2>7. Dados e limitações</h2>
        <p>Os números usados neste relatório vêm de <a href="data/jean-final-results.json"><code>site/data/jean-final-results.json</code></a>. A busca exploratória da Tarefa 4 fica em <a href="data/jean-task4-search-results.json"><code>site/data/jean-task4-search-results.json</code></a> quando publicada junto ao site.</p>
        <div class="conclusion">
          <p><strong>Conclusão geral.</strong> Os dois benchmarks melhoram com execução fora de ordem, janelas maiores e previsão dinâmica de desvios. O LI_3 se beneficia bastante da combinação largura alta mais fora de ordem, mas ainda paga custo relevante por desvios. O VORTEX_2 tem maior fração de load/store e, por isso, a customização mais convincente prioriza janela, LSQ e memória antes de aumentar recursos que não aparecem como gargalo medido.</p>
          <p><strong>Limitação.</strong> O índice de custo é uma aproximação para discussão acadêmica. Um projeto real exigiria modelagem de área, potência, frequência, pressão de verificação e impacto físico das estruturas ampliadas.</p>
        </div>
      </section>
    </main>
    <footer>Relatório gerado por <code>scripts/generate_jean_page.py</code> a partir dos resultados medidos. O texto foi escrito especificamente para LI_3 e VORTEX_2.</footer>
  </div>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="results/jean-final", help="Official final results directory or results.json")
    parser.add_argument("--search-results", default="results/jean-task4-search", help="Task 4 search results directory")
    parser.add_argument("--output", default="site/jean-li3-vortex2.html", help="Output HTML path")
    return parser


def resolve_results(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path / "results.json" if path.is_dir() else path


def main() -> int:
    args = build_parser().parse_args()
    final_path = resolve_results(args.results)
    if not final_path.exists():
        raise SystemExit(f"Missing results file: {final_path}")
    final = read_json(final_path)

    search_path = resolve_results(args.search_results)
    search = read_json(search_path) if search_path.exists() else None

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(final, search), encoding="utf-8")

    data_dir = output.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_path, data_dir / "jean-final-results.json")
    final_csv_path = final_path.with_name("results.csv")
    if final_csv_path.exists():
        shutil.copy2(final_csv_path, data_dir / "jean-final-results.csv")

    if search_path.exists():
        shutil.copy2(search_path, data_dir / "jean-task4-search-results.json")
        csv_path = search_path.with_name("results.csv")
        if csv_path.exists():
            shutil.copy2(csv_path, data_dir / "jean-task4-search-results.csv")
        search_html = search_path.with_name("task4-search.html")
        if search_html.exists():
            shutil.copy2(search_html, output.parent / "jean-task4-search.html")

    print(f"Generated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
