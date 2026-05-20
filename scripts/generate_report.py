#!/usr/bin/env python3
"""Generate a static UFPel-themed HTML report from experiment results."""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = ROOT / "experiments"
CONCLUSIONS_PATH = ROOT / "reports" / "conclusions.md"
TASK_ORDER = ["Tarefa 1", "Tarefa 2", "Tarefa 3", "Tarefa 4"]


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def metric(run: dict[str, Any], name: str) -> int | float | None:
    value = run.get("stats", {}).get(name)
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def first_metric(run: dict[str, Any], suffix: str, prefix: str | None = None) -> int | float | None:
    for key in sorted(run.get("stats", {})):
        if prefix and not key.startswith(prefix):
            continue
        if key.endswith(suffix):
            value = run["stats"][key]
            if isinstance(value, (int, float)) and math.isfinite(value):
                return value
    return None


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return h(value)


def pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}%"


def status_class(status: str) -> str:
    return {
        "completed": "ok",
        "planned": "planned",
        "failed": "bad",
        "timed_out": "bad",
    }.get(status, "bad")


def option_table(options: dict[str, Any]) -> str:
    rows = []
    for key in sorted(options):
        rows.append(f"<tr><th>{h(key)}</th><td>{h(options[key])}</td></tr>")
    return "<table class=\"mini-table\"><tbody>" + "".join(rows) + "</tbody></table>"


def run_link(run: dict[str, Any], label: str, file_key: str) -> str:
    files = run.get("files", {})
    path = files.get(file_key)
    if not path:
        return "-"
    return f"<a href=\"data/{h(path)}\">{h(label)}</a>"


def cpi(run: dict[str, Any]) -> float | None:
    return metric(run, "sim_CPI")


def width_and_mode(run: dict[str, Any]) -> tuple[int | None, str]:
    options = run.get("options", {})
    width = options.get("issue:width")
    mode = "in-order" if options.get("issue:inorder") is True else "out-of-order"
    return width if isinstance(width, int) else None, mode


def predictor(run: dict[str, Any]) -> str:
    return str(run.get("options", {}).get("bpred", "bimod"))


def by_task(runs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {task: [] for task in TASK_ORDER}
    for run in runs:
        grouped.setdefault(run["task"], []).append(run)
    return grouped


def summary_cards(results: dict[str, Any]) -> str:
    runs = results["runs"]
    completed = [run for run in runs if run["status"] == "completed"]
    cpis = [value for run in completed if (value := cpi(run)) is not None]
    best = min(cpis) if cpis else None
    avg = sum(cpis) / len(cpis) if cpis else None
    cards = [
        ("Benchmarks", len(results.get("selected_benchmarks", []))),
        ("Configuracoes", len(results.get("selected_experiments", []))),
        ("Rodadas completas", f"{len(completed)}/{len(runs)}"),
        ("CPI medio", fmt(avg)),
        ("Melhor CPI", fmt(best)),
        ("Limite de instrucoes", "completo" if results.get("max_instructions") == 0 else fmt(results.get("max_instructions"))),
    ]
    return "".join(
        f"<article class=\"card\"><span>{h(label)}</span><strong>{h(value)}</strong></article>"
        for label, value in cards
    )


def benchmark_section(results: dict[str, Any]) -> str:
    rows = []
    for name, bench in sorted(results.get("benchmarks", {}).items()):
        rows.append(
            "<tr>"
            f"<td><strong>{h(name)}</strong></td>"
            f"<td>{h(bench.get('family'))}</td>"
            f"<td>{h(bench.get('input'))}</td>"
            f"<td class=\"num\">{fmt(bench.get('total_instructions'))}</td>"
            f"<td class=\"num\">{fmt(bench.get('load_store_instructions'))}</td>"
            f"<td>{h(bench.get('description'))}</td>"
            "</tr>"
        )
    return f"""
    <section class="panel" id="benchmarks">
      <div class="section-heading"><span>Benchmarks</span><h2>Cargas de Trabalho</h2></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Benchmark</th><th>Familia</th><th>Entrada</th><th>Instrucoes</th><th>Load/Store</th><th>Descricao</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def experiments_section(results: dict[str, Any]) -> str:
    rows = []
    for exp_id, exp in sorted(results.get("experiments", {}).items(), key=lambda item: (item[1]["task"], item[0])):
        rows.append(
            "<tr>"
            f"<td><code>{h(exp_id)}</code></td>"
            f"<td>{h(exp.get('task'))}</td>"
            f"<td><strong>{h(exp.get('title'))}</strong><br><small>{h(exp.get('summary'))}</small></td>"
            f"<td>{option_table(exp.get('options', {}))}</td>"
            "</tr>"
        )
    return f"""
    <section class="panel" id="experiments">
      <div class="section-heading"><span>Experimentos</span><h2>Configuracoes Simuladas</h2></div>
      <p>As configuracoes abaixo sao geradas como arquivos <code>sim-outorder.cfg</code> por rodada. O arquivo base de cache/TLB vem do pacote de benchmarks.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Tarefa</th><th>Objetivo</th><th>Parametros</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def task_intro_sections(report: dict[str, Any]) -> str:
    sections = []
    for task in TASK_ORDER:
        data = report.get("tasks", {}).get(task, {})
        questions = "".join(f"<li>{h(question)}</li>" for question in data.get("questions", []))
        sections.append(
            f"<article class=\"task-card\"><span>{h(task)}</span><h3>{h(data.get('title'))}</h3>"
            f"<p>{h(data.get('goal'))}</p><ul>{questions}</ul></article>"
        )
    return f"""
    <section class="panel" id="tasks">
      <div class="section-heading"><span>Escopo</span><h2>Questoes do Trabalho</h2></div>
      <div class="task-grid">{''.join(sections)}</div>
    </section>
    """


def result_rows(runs: list[dict[str, Any]]) -> str:
    rows = []
    for run in sorted(runs, key=lambda item: (item["benchmark"], item["experiment"])):
        bpred_rate = first_metric(run, "bpred_dir_rate", "bpred_")
        bpred_misses = first_metric(run, "misses", "bpred_")
        rows.append(
            "<tr>"
            f"<td><strong>{h(run['benchmark'])}</strong><br><small>{h(run.get('benchmark_input'))}</small></td>"
            f"<td><code>{h(run['experiment'])}</code><br><small>{h(run.get('experiment_title'))}</small></td>"
            f"<td><span class=\"status {status_class(run['status'])}\">{h(run['status'])}</span></td>"
            f"<td class=\"num\">{fmt(metric(run, 'sim_cycle'))}</td>"
            f"<td class=\"num\">{fmt(cpi(run))}</td>"
            f"<td class=\"num\">{fmt(metric(run, 'sim_IPC'))}</td>"
            f"<td class=\"num\">{fmt(metric(run, 'sim_num_insn'))}</td>"
            f"<td class=\"num\">{fmt(bpred_rate)}</td>"
            f"<td class=\"num\">{fmt(bpred_misses)}</td>"
            f"<td>{run_link(run, 'config', 'config')} · {run_link(run, 'stdout', 'stdout')}</td>"
            "</tr>"
        )
    return "".join(rows)


def results_section(grouped: dict[str, list[dict[str, Any]]]) -> str:
    sections = []
    for task in TASK_ORDER:
        runs = grouped.get(task, [])
        if not runs:
            continue
        sections.append(
            f"""
            <section class="panel result-panel" id="{h(task.lower().replace(' ', '-'))}">
              <div class="section-heading"><span>{h(task)}</span><h2>Resultados</h2></div>
              <div class="table-wrap">
                <table>
                  <thead><tr><th>Benchmark</th><th>Experimento</th><th>Status</th><th>Ciclos</th><th>CPI</th><th>IPC</th><th>Instrucoes</th><th>Taxa previsor</th><th>Misses previsor</th><th>Arquivos</th></tr></thead>
                  <tbody>{result_rows(runs)}</tbody>
                </table>
              </div>
            </section>
            """
        )
    return "".join(sections)


def task1_analysis(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return ""
    lookup: dict[tuple[str, int | None, str], dict[str, Any]] = {}
    for run in runs:
        width, mode = width_and_mode(run)
        lookup[(run["benchmark"], width, mode)] = run
    rows = []
    for benchmark in sorted({run["benchmark"] for run in runs}):
        for width in sorted({width_and_mode(run)[0] for run in runs if run["benchmark"] == benchmark and width_and_mode(run)[0] is not None}):
            in_run = lookup.get((benchmark, width, "in-order"))
            ooo_run = lookup.get((benchmark, width, "out-of-order"))
            in_cpi = cpi(in_run) if in_run else None
            ooo_cpi = cpi(ooo_run) if ooo_run else None
            gain = ((in_cpi - ooo_cpi) / in_cpi * 100) if in_cpi and ooo_cpi else None
            rows.append(
                "<tr>"
                f"<td>{h(benchmark)}</td><td class=\"num\">{fmt(width)}</td>"
                f"<td class=\"num\">{fmt(in_cpi)}</td><td class=\"num\">{fmt(ooo_cpi)}</td>"
                f"<td class=\"num\">{pct(gain)}</td>"
                "</tr>"
            )
    return f"""
    <article class="analysis-block">
      <h3>Tarefa 1: impacto de largura e fora de ordem</h3>
      <p>Valores positivos indicam reducao de CPI ao trocar despacho em ordem por fora de ordem na mesma largura.</p>
      <div class="table-wrap"><table><thead><tr><th>Benchmark</th><th>Largura</th><th>CPI in-order</th><th>CPI out-of-order</th><th>Reducao CPI</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </article>
    """


def best_by_benchmark(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for run in runs:
        value = cpi(run)
        if value is None:
            continue
        current = best.get(run["benchmark"])
        if current is None or value < cpi(current):
            best[run["benchmark"]] = run
    return [best[name] for name in sorted(best)]


def task2_analysis(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return ""
    rows = []
    for run in best_by_benchmark(runs):
        rows.append(
            "<tr>"
            f"<td>{h(run['benchmark'])}</td>"
            f"<td><code>{h(run['experiment'])}</code></td>"
            f"<td class=\"num\">{fmt(run.get('options', {}).get('ruu:size'))}</td>"
            f"<td class=\"num\">{fmt(run.get('options', {}).get('lsq:size'))}</td>"
            f"<td class=\"num\">{fmt(cpi(run))}</td>"
            "</tr>"
        )
    return f"""
    <article class="analysis-block">
      <h3>Tarefa 2: melhor tamanho de janela observado</h3>
      <div class="table-wrap"><table><thead><tr><th>Benchmark</th><th>Configuracao</th><th>RUU</th><th>LSQ</th><th>CPI</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </article>
    """


def task3_analysis(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return ""
    perfect: dict[str, float] = {}
    for run in runs:
        if predictor(run) == "perfect" and cpi(run) is not None:
            perfect[run["benchmark"]] = cpi(run)
    rows = []
    for run in sorted(runs, key=lambda item: (item["benchmark"], predictor(item))):
        value = cpi(run)
        baseline = perfect.get(run["benchmark"])
        overhead = ((value / baseline - 1) * 100) if value and baseline else None
        rows.append(
            "<tr>"
            f"<td>{h(run['benchmark'])}</td>"
            f"<td>{h(predictor(run))}</td>"
            f"<td class=\"num\">{fmt(value)}</td>"
            f"<td class=\"num\">{fmt(first_metric(run, 'bpred_dir_rate', 'bpred_'))}</td>"
            f"<td class=\"num\">{fmt(first_metric(run, 'misses', 'bpred_'))}</td>"
            f"<td class=\"num\">{pct(overhead)}</td>"
            "</tr>"
        )
    return f"""
    <article class="analysis-block">
      <h3>Tarefa 3: custo relativo dos previsores</h3>
      <p>O overhead usa o previsor perfeito do mesmo benchmark como baseline. O previsor bimodal usa contadores saturantes de 2 bits indexados pelo endereco do desvio para aprender se cada desvio tende a ser tomado ou nao tomado.</p>
      <div class="table-wrap"><table><thead><tr><th>Benchmark</th><th>Previsor</th><th>CPI</th><th>Taxa direcao</th><th>Misses</th><th>Overhead vs perfect</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </article>
    """


def task4_analysis(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return ""
    rows = []
    for run in best_by_benchmark(runs):
        options = run.get("options", {})
        cost_hint = sum(
            int(options.get(name, 0) or 0)
            for name in ["ruu:size", "lsq:size", "res:ialu", "res:imult", "res:fpalu", "res:fpmult", "res:memport"]
        )
        rows.append(
            "<tr>"
            f"<td>{h(run['benchmark'])}</td>"
            f"<td><code>{h(run['experiment'])}</code><br><small>{h(run.get('experiment_title'))}</small></td>"
            f"<td class=\"num\">{fmt(cpi(run))}</td>"
            f"<td class=\"num\">{fmt(cost_hint)}</td>"
            f"<td>{option_table(options)}</td>"
            "</tr>"
        )
    return f"""
    <article class="analysis-block">
      <h3>Tarefa 4: melhor customizacao por benchmark</h3>
      <p>O indice de custo e uma soma simples dos recursos configurados; ele nao substitui area, energia, frequencia, complexidade de projeto ou custo de memoria/cache, mas ajuda a comparar configuracoes no relatorio inicial.</p>
      <div class="table-wrap"><table><thead><tr><th>Benchmark</th><th>Melhor configuracao</th><th>CPI</th><th>Indice custo</th><th>Parametros</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </article>
    """


def analysis_section(grouped: dict[str, list[dict[str, Any]]]) -> str:
    content = "".join(
        [
            task1_analysis(grouped.get("Tarefa 1", [])),
            task2_analysis(grouped.get("Tarefa 2", [])),
            task3_analysis(grouped.get("Tarefa 3", [])),
            task4_analysis(grouped.get("Tarefa 4", [])),
        ]
    )
    return f"""
    <section class="panel" id="analysis">
      <div class="section-heading"><span>Analise</span><h2>Leituras Automaticas</h2></div>
      {content if content else '<p>Nao ha resultados suficientes para gerar analises automaticas.</p>'}
    </section>
    """


def completed_cpi_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [run for run in runs if run.get("status") == "completed" and cpi(run) is not None]


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def load_store_ratio(benchmark: dict[str, Any]) -> float | None:
    total = benchmark.get("total_instructions")
    load_store = benchmark.get("load_store_instructions")
    if not isinstance(total, (int, float)) or not isinstance(load_store, (int, float)) or total <= 0:
        return None
    return load_store / total * 100


def architecture_cost(options: dict[str, Any]) -> int:
    return sum(
        int(options.get(name, 0) or 0)
        for name in ["ruu:size", "lsq:size", "res:ialu", "res:imult", "res:fpalu", "res:fpmult", "res:memport"]
    )


def palette(index: int) -> str:
    colors = ["#1bd7ff", "#00d084", "#f6c343", "#ff5a8a", "#9b7cff", "#42f5b0", "#ff8a3d", "#6ea8ff"]
    return colors[index % len(colors)]


def value_range(values: list[float], pad: float = 0.08) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        spread = abs(high) * 0.1 or 1.0
        return low - spread, high + spread
    spread = high - low
    return low - spread * pad, high + spread * pad


def chart_empty(message: str) -> str:
    return f"<div class=\"plot-empty\">{h(message)}</div>"


def chart_card(title: str, subtitle: str, body: str, note: str) -> str:
    return f"""
    <article class="plot-card">
      <div class="plot-card-head"><span>{h(subtitle)}</span><h3>{h(title)}</h3></div>
      {body}
      <p class="plot-note">{h(note)}</p>
    </article>
    """


def best_cpi_chart(results: dict[str, Any]) -> str:
    best_runs = best_by_benchmark(completed_cpi_runs(results.get("runs", [])))
    data = [(run["benchmark"], cpi(run), run["experiment"]) for run in best_runs if cpi(run) is not None]
    if not data:
        return chart_empty("Sem CPI completo suficiente para ranquear benchmarks.")

    data.sort(key=lambda item: item[1] or math.inf)
    max_value = max(value for _, value, _ in data if value is not None)
    width = 980
    row_h = 36
    top = 48
    left = 140
    plot_w = 720
    height = top + row_h * len(data) + 34
    grid = []
    for idx in range(5):
        value = max_value * idx / 4
        x = left + plot_w * idx / 4
        grid.append(f'<line x1="{x:.1f}" y1="34" x2="{x:.1f}" y2="{height - 28}" class="plot-grid"/>')
        grid.append(f'<text x="{x:.1f}" y="24" class="plot-axis" text-anchor="middle">{h(fmt(value, 2))}</text>')

    rows = []
    for index, (benchmark, value, experiment) in enumerate(data):
        if value is None:
            continue
        y = top + index * row_h
        bar_w = max(4, value / max_value * plot_w)
        rows.append(
            f'<g class="plot-row">'
            f'<text x="18" y="{y + 18}" class="plot-label">{h(benchmark)}</text>'
            f'<rect x="{left}" y="{y}" width="{plot_w}" height="18" rx="9" class="plot-track"/>'
            f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="18" rx="9" fill="url(#bestCpiGradient)"/>'
            f'<text x="{left + bar_w + 10:.1f}" y="{y + 14}" class="plot-value">{h(fmt(value))}</text>'
            f'<text x="{width - 18}" y="{y + 14}" class="plot-muted" text-anchor="end">{h(experiment)}</text>'
            f'</g>'
        )

    return f"""
    <svg class="plot-svg tall" viewBox="0 0 {width} {height}" role="img" aria-label="Ranking de melhor CPI por benchmark">
      <title>Ranking de melhor CPI por benchmark</title>
      <defs><linearGradient id="bestCpiGradient" x1="0" x2="1"><stop offset="0" stop-color="#1bd7ff"/><stop offset="1" stop-color="#f6c343"/></linearGradient></defs>
      <text x="18" y="24" class="plot-axis">CPI observado: menor barra = melhor desempenho</text>
      {''.join(grid)}
      {''.join(rows)}
    </svg>
    """


def workload_scatter_chart(results: dict[str, Any]) -> str:
    best_runs = {run["benchmark"]: run for run in best_by_benchmark(completed_cpi_runs(results.get("runs", [])))}
    points = []
    for benchmark, run in best_runs.items():
        bench = results.get("benchmarks", {}).get(benchmark, {})
        ratio = load_store_ratio(bench)
        value = cpi(run)
        if ratio is not None and value is not None:
            points.append((benchmark, bench.get("family", ""), ratio, value))
    if len(points) < 2:
        return chart_empty("Sao necessarios pelo menos dois benchmarks completos para correlacionar mix e CPI.")

    x_min, x_max = value_range([point[2] for point in points], 0.12)
    y_min, y_max = value_range([point[3] for point in points], 0.12)
    width = 980
    height = 430
    left = 72
    top = 36
    plot_w = 820
    plot_h = 310
    families = {family: palette(index) for index, family in enumerate(sorted({point[1] for point in points}))}

    grid = []
    for idx in range(5):
        x = left + plot_w * idx / 4
        x_value = x_min + (x_max - x_min) * idx / 4
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="plot-grid"/>')
        grid.append(f'<text x="{x:.1f}" y="{top + plot_h + 30}" class="plot-axis" text-anchor="middle">{x_value:.0f}%</text>')
    for idx in range(4):
        y = top + plot_h * idx / 3
        y_value = y_max - (y_max - y_min) * idx / 3
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="plot-grid"/>')
        grid.append(f'<text x="{left - 12}" y="{y + 4:.1f}" class="plot-axis" text-anchor="end">{h(fmt(y_value, 2))}</text>')

    point_markup = []
    for benchmark, family, ratio, value in points:
        x = left + (ratio - x_min) / (x_max - x_min) * plot_w
        y = top + (y_max - value) / (y_max - y_min) * plot_h
        color = families.get(family, palette(0))
        point_markup.append(
            f'<g class="scatter-point">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{color}"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="{color}" opacity="0.16"/>'
            f'<text x="{x + 13:.1f}" y="{y - 10:.1f}" class="plot-label tiny">{h(benchmark)}</text>'
            f'</g>'
        )
    legend = []
    for index, (family, color) in enumerate(families.items()):
        x = left + index * 115
        legend.append(f'<circle cx="{x}" cy="396" r="6" fill="{color}"/><text x="{x + 12}" y="400" class="plot-axis">{h(family)}</text>')

    return f"""
    <svg class="plot-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Carga de load-store contra melhor CPI">
      <title>Carga de load-store contra melhor CPI</title>
      {''.join(grid)}
      <text x="{left + plot_w / 2}" y="{height - 8}" class="plot-axis" text-anchor="middle">percentual de instrucoes load/store no benchmark</text>
      <text x="18" y="28" class="plot-axis">melhor CPI observado</text>
      {''.join(point_markup)}
      {''.join(legend)}
    </svg>
    """


def multi_line_chart(title: str, x_values: list[int], series: list[tuple[str, dict[int, float], str]], x_label: str) -> str:
    available_values = [value for _, points, _ in series for value in points.values()]
    if not available_values or not x_values:
        return chart_empty(f"Sem dados completos para {title}.")
    y_min, y_max = value_range(available_values, 0.15)
    width = 980
    height = 400
    left = 72
    top = 34
    plot_w = 820
    plot_h = 275

    def x_pos(value: int) -> float:
        if len(x_values) == 1:
            return left + plot_w / 2
        return left + x_values.index(value) / (len(x_values) - 1) * plot_w

    def y_pos(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    grid = []
    for value in x_values:
        x = x_pos(value)
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="plot-grid"/>')
        grid.append(f'<text x="{x:.1f}" y="{top + plot_h + 28}" class="plot-axis" text-anchor="middle">{value}</text>')
    for idx in range(4):
        y = top + plot_h * idx / 3
        y_value = y_max - (y_max - y_min) * idx / 3
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="plot-grid"/>')
        grid.append(f'<text x="{left - 12}" y="{y + 4:.1f}" class="plot-axis" text-anchor="end">{h(fmt(y_value, 2))}</text>')

    lines = []
    for index, (label, points, color) in enumerate(series):
        coords = [(x_pos(x), y_pos(points[x])) for x in x_values if x in points]
        if not coords:
            continue
        path = " ".join(("M" if idx == 0 else "L") + f" {x:.1f} {y:.1f}" for idx, (x, y) in enumerate(coords))
        circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>' for x, y in coords)
        legend_y = 356 + index * 20
        lines.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
            f'{circles}'
            f'<line x1="72" y1="{legend_y}" x2="104" y2="{legend_y}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
            f'<text x="114" y="{legend_y + 4}" class="plot-axis">{h(label)}</text>'
        )

    return f"""
    <svg class="plot-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{h(title)}">
      <title>{h(title)}</title>
      {''.join(grid)}
      {''.join(lines)}
      <text x="18" y="28" class="plot-axis">CPI medio</text>
      <text x="{left + plot_w / 2}" y="{height - 12}" class="plot-axis" text-anchor="middle">{h(x_label)}</text>
    </svg>
    """


def task1_width_visual(runs: list[dict[str, Any]]) -> str:
    grouped_values: dict[str, dict[int, list[float]]] = {"in-order": {}, "out-of-order": {}}
    for run in completed_cpi_runs(runs):
        width, mode = width_and_mode(run)
        value = cpi(run)
        if width is None or value is None:
            continue
        grouped_values.setdefault(mode, {}).setdefault(width, []).append(value)
    widths = sorted({width for values in grouped_values.values() for width in values})
    series = [
        ("in-order", {width: mean(values) for width, values in grouped_values.get("in-order", {}).items() if mean(values) is not None}, "#f6c343"),
        ("out-of-order", {width: mean(values) for width, values in grouped_values.get("out-of-order", {}).items() if mean(values) is not None}, "#1bd7ff"),
    ]
    return multi_line_chart("CPI medio por largura", widths, series, "largura de issue/decode/commit")


def task2_window_visual(runs: list[dict[str, Any]]) -> str:
    grouped_values: dict[int, list[float]] = {}
    for run in completed_cpi_runs(runs):
        value = cpi(run)
        ruu = run.get("options", {}).get("ruu:size")
        if isinstance(ruu, int) and value is not None:
            grouped_values.setdefault(ruu, []).append(value)
    windows = sorted(grouped_values)
    series = [("media dos benchmarks", {window: mean(values) for window, values in grouped_values.items() if mean(values) is not None}, "#00d084")]
    return multi_line_chart("CPI medio por tamanho da janela", windows, series, "tamanho da RUU")


def predictor_overhead_chart(runs: list[dict[str, Any]]) -> str:
    perfect: dict[str, float] = {}
    for run in completed_cpi_runs(runs):
        value = cpi(run)
        if predictor(run) == "perfect" and value is not None:
            perfect[run["benchmark"]] = value

    grouped_values: dict[str, list[float]] = {}
    for run in completed_cpi_runs(runs):
        value = cpi(run)
        baseline = perfect.get(run["benchmark"])
        if value is None or baseline is None or baseline <= 0:
            continue
        grouped_values.setdefault(predictor(run), []).append((value / baseline - 1) * 100)

    order = [name for name in ["perfect", "bimod", "taken", "nottaken"] if name in grouped_values]
    data = [(name, mean(grouped_values[name]) or 0.0) for name in order]
    if not data:
        return chart_empty("Sem baseline perfect completo para comparar previsores.")

    min_value = min(0.0, min(value for _, value in data))
    max_value = max(0.0, max(value for _, value in data))
    if math.isclose(min_value, max_value):
        max_value = min_value + 1.0
    width = 980
    height = 360
    left = 96
    top = 42
    plot_w = 780
    plot_h = 210
    zero_x = left + (0 - min_value) / (max_value - min_value) * plot_w
    row_h = 46
    rows = [f'<line x1="{zero_x:.1f}" y1="{top - 8}" x2="{zero_x:.1f}" y2="{top + plot_h + 8}" class="plot-zero"/>']
    for index, (name, value) in enumerate(data):
        y = top + index * row_h
        x = left + (min(value, 0) - min_value) / (max_value - min_value) * plot_w
        bar_w = abs(value) / (max_value - min_value) * plot_w
        rows.append(
            f'<text x="18" y="{y + 18}" class="plot-label">{h(name)}</text>'
            f'<rect x="{x:.1f}" y="{y}" width="{max(2, bar_w):.1f}" height="20" rx="10" fill="{palette(index)}"/>'
            f'<text x="{x + bar_w + 10:.1f}" y="{y + 15}" class="plot-value">{h(pct(value))}</text>'
        )
    return f"""
    <svg class="plot-svg compact" viewBox="0 0 {width} {height}" role="img" aria-label="Overhead medio dos previsores contra perfect">
      <title>Overhead medio dos previsores contra perfect</title>
      <text x="18" y="28" class="plot-axis">overhead medio vs perfect; menor e melhor</text>
      {''.join(rows)}
    </svg>
    """


def task4_cost_scatter_chart(runs: list[dict[str, Any]]) -> str:
    grouped_values: dict[str, list[float]] = {}
    costs: dict[str, int] = {}
    titles: dict[str, str] = {}
    for run in completed_cpi_runs(runs):
        value = cpi(run)
        if value is None:
            continue
        exp = run["experiment"]
        grouped_values.setdefault(exp, []).append(value)
        costs[exp] = architecture_cost(run.get("options", {}))
        titles[exp] = run.get("experiment_title", exp)
    points = [(exp, titles.get(exp, exp), costs[exp], mean(values) or 0.0) for exp, values in grouped_values.items()]
    if len(points) < 2:
        return chart_empty("Sao necessarias ao menos duas customizacoes completas para comparar custo e CPI.")

    x_min, x_max = value_range([float(point[2]) for point in points], 0.16)
    y_min, y_max = value_range([point[3] for point in points], 0.16)
    width = 980
    height = 410
    left = 74
    top = 34
    plot_w = 810
    plot_h = 280
    grid = []
    for idx in range(4):
        x = left + plot_w * idx / 3
        x_value = x_min + (x_max - x_min) * idx / 3
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="plot-grid"/>')
        grid.append(f'<text x="{x:.1f}" y="{top + plot_h + 28}" class="plot-axis" text-anchor="middle">{h(fmt(x_value, 0))}</text>')
    for idx in range(4):
        y = top + plot_h * idx / 3
        y_value = y_max - (y_max - y_min) * idx / 3
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="plot-grid"/>')
        grid.append(f'<text x="{left - 12}" y="{y + 4:.1f}" class="plot-axis" text-anchor="end">{h(fmt(y_value, 2))}</text>')
    point_markup = []
    for index, (exp, title, cost, value) in enumerate(sorted(points)):
        x = left + (cost - x_min) / (x_max - x_min) * plot_w
        y = top + (y_max - value) / (y_max - y_min) * plot_h
        color = palette(index)
        point_markup.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{color}"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="21" fill="{color}" opacity="0.14"/>'
            f'<text x="{x + 14:.1f}" y="{y - 12:.1f}" class="plot-label tiny">{h(exp.replace("task4_", ""))}</text>'
            f'<text x="{x + 14:.1f}" y="{y + 4:.1f}" class="plot-muted tiny">{h(fmt(value))} CPI</text>'
        )
    return f"""
    <svg class="plot-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Custo arquitetural contra CPI medio das customizacoes">
      <title>Custo arquitetural contra CPI medio das customizacoes</title>
      {''.join(grid)}
      {''.join(point_markup)}
      <text x="18" y="28" class="plot-axis">CPI medio</text>
      <text x="{left + plot_w / 2}" y="{height - 12}" class="plot-axis" text-anchor="middle">indice de custo arquitetural simples</text>
    </svg>
    """


def benchmark_story_cards(results: dict[str, Any], grouped: dict[str, list[dict[str, Any]]]) -> str:
    completed = completed_cpi_runs(results.get("runs", []))
    if not completed:
        return chart_empty("As cartas por benchmark aparecem quando ha runs completos com CPI.")

    runs_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for run in completed:
        runs_by_benchmark.setdefault(run["benchmark"], []).append(run)

    cards = []
    for benchmark in sorted(results.get("benchmarks", {})):
        bench = results["benchmarks"][benchmark]
        runs = runs_by_benchmark.get(benchmark, [])
        if not runs:
            continue
        best = min(runs, key=lambda run: cpi(run) or math.inf)
        task_values = []
        for task in TASK_ORDER:
            task_runs = [run for run in runs if run.get("task") == task]
            best_task = min(task_runs, key=lambda run: cpi(run) or math.inf) if task_runs else None
            if best_task and cpi(best_task) is not None:
                task_values.append((task.replace("Tarefa ", "T"), cpi(best_task), best_task["experiment"]))
        max_task_cpi = max((value for _, value, _ in task_values if value is not None), default=1.0)
        bars = []
        for index, (task, value, experiment) in enumerate(task_values):
            width_pct = max(5.0, (value or 0.0) / max_task_cpi * 100)
            bars.append(
                f'<div class="mini-bar-row"><span>{h(task)}</span><i style="--w:{width_pct:.1f}%;--bar:{palette(index)}"></i>'
                f'<b>{h(fmt(value))}</b><em>{h(experiment.replace("task", "t"))}</em></div>'
            )
        ratio = load_store_ratio(bench)
        cards.append(
            f"""
            <article class="bench-story">
              <div class="bench-story-top"><strong>{h(benchmark)}</strong><span>{h(bench.get('family'))}</span></div>
              <div class="bench-kpi"><span>melhor CPI</span><b>{h(fmt(cpi(best)))}</b></div>
              <p>Vencedor: <code>{h(best['experiment'])}</code></p>
              <div class="bench-meta"><span>Entrada: {h(bench.get('input'))}</span><span>Load/store: {h(pct(ratio))}</span></div>
              <div class="mini-bars">{''.join(bars)}</div>
            </article>
            """
        )
    return f'<div class="bench-story-grid">{"".join(cards)}</div>'


def visuals_section(results: dict[str, Any], grouped: dict[str, list[dict[str, Any]]]) -> str:
    cards = [
        chart_card(
            "Ranking de CPI por benchmark",
            "cross-benchmark",
            best_cpi_chart(results),
            "Cada barra usa o menor CPI observado para aquele benchmark em qualquer configuracao completa.",
        ),
        chart_card(
            "Mix de memoria vs CPI",
            "workload fingerprint",
            workload_scatter_chart(results),
            "A posicao horizontal vem do percentual load/store do PDF; a vertical usa o melhor CPI medido.",
        ),
        chart_card(
            "Largura: in-order contra out-of-order",
            "Tarefa 1",
            task1_width_visual(grouped.get("Tarefa 1", [])),
            "As curvas mostram a media entre benchmarks; pontos mais baixos indicam menor CPI.",
        ),
        chart_card(
            "Tamanho da janela RUU",
            "Tarefa 2",
            task2_window_visual(grouped.get("Tarefa 2", [])),
            "Se a curva achata, aumentar a janela deixou de comprar desempenho no conjunto medido.",
        ),
        chart_card(
            "Custo dos previsores",
            "Tarefa 3",
            predictor_overhead_chart(grouped.get("Tarefa 3", [])),
            "Overhead e calculado contra o previsor perfect do mesmo benchmark antes da media.",
        ),
        chart_card(
            "Customizacao: custo contra CPI",
            "Tarefa 4",
            task4_cost_scatter_chart(grouped.get("Tarefa 4", [])),
            "O canto inferior esquerdo representa o melhor compromisso visual: baixo custo e baixo CPI.",
        ),
    ]
    return f"""
    <section class="panel visual-panel" id="visuals">
      <div class="section-heading"><span>Visualizacoes</span><h2>Comparacoes Autoexplicativas</h2></div>
      <p class="visual-lede">Esta secao transforma os resultados brutos em graficos estaticos: comparacoes entre benchmarks, curvas internas por tarefa e cartas compactas que resumem o comportamento de cada carga. Em todos os graficos de CPI, menor e melhor.</p>
      <div class="plot-card-grid">{''.join(cards)}</div>
      <div class="section-heading mini-heading"><span>Dentro de cada benchmark</span><h2>Cartas de leitura rapida</h2></div>
      {benchmark_story_cards(results, grouped)}
    </section>
    """


def methodology_section(results: dict[str, Any]) -> str:
    command = (
        "python3 scripts/run_experiments.py "
        f"--benchmarks {results.get('benchmark_selection')} "
        f"--experiment-set {results.get('experiment_selection')} "
        f"--max-instructions {results.get('max_instructions')}"
    )
    return f"""
    <section class="panel" id="methodology">
      <div class="section-heading"><span>Reprodutibilidade</span><h2>Como Estes Dados Foram Gerados</h2></div>
      <p>O workflow constroi uma imagem Docker com o SimpleScalar do snapshot fixado de <code>khaledhassan/simplescalar-docker</code>, monta este repositorio e executa o runner de experimentos.</p>
      <pre><code>{h(command)}</code></pre>
      <p>Arquivos estruturados: <a href="data/results.json"><code>data/results.json</code></a> e <a href="data/results.csv"><code>data/results.csv</code></a>. Os logs e configs de cada rodada ficam em <code>data/runs/&lt;benchmark&gt;/&lt;experimento&gt;/</code>.</p>
    </section>
    """


def markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{h(' '.join(paragraph))}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            blocks.append("</ul>")
            in_list = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                blocks.append(f"<pre><code>{h(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            close_list()
            blocks.append(f"<h4>{h(stripped[4:])}</h4>")
        elif stripped.startswith("## "):
            flush_paragraph()
            close_list()
            blocks.append(f"<h3>{h(stripped[3:])}</h3>")
        elif stripped.startswith("# "):
            flush_paragraph()
            close_list()
            blocks.append(f"<h3>{h(stripped[2:])}</h3>")
        elif stripped.startswith("- "):
            flush_paragraph()
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{h(stripped[2:])}</li>")
        else:
            paragraph.append(stripped)
    flush_paragraph()
    close_list()
    if in_code:
        blocks.append(f"<pre><code>{h(chr(10).join(code_lines))}</code></pre>")
    return "".join(blocks)


def conclusions_section() -> str:
    if not CONCLUSIONS_PATH.exists():
        return ""
    markdown = CONCLUSIONS_PATH.read_text(encoding="utf-8")
    return f"""
    <section class="panel" id="conclusions">
      <div class="section-heading"><span>Conclusoes</span><h2>Interpretacao Agentica</h2></div>
      <div class="conclusions-body">{markdown_to_html(markdown)}</div>
    </section>
    """


def stylesheet() -> str:
    return """
:root {
  --ufpel-blue: #003d73;
  --ufpel-blue-dark: #06233f;
  --ufpel-blue-soft: #e7f0f8;
  --ufpel-gold: #f6c343;
  --ink: #162033;
  --muted: #5d6b80;
  --line: #d8e1ec;
  --paper: #ffffff;
  --bg: #f3f7fb;
  --bad: #b42318;
  --ok: #137333;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background: linear-gradient(180deg, #eef5fc 0, var(--bg) 380px, #fff 100%);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
a { color: var(--ufpel-blue); font-weight: 700; text-decoration: none; }
a:hover { text-decoration: underline; }
code, pre { font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }
pre { overflow-x: auto; border-radius: 16px; padding: 18px; background: #071b30; color: #e5f2ff; }
.hero {
  position: relative;
  overflow: hidden;
  padding: 56px clamp(20px, 5vw, 72px) 34px;
  color: #fff;
  background: radial-gradient(circle at 80% 20%, rgba(246, 195, 67, .32), transparent 28%), linear-gradient(135deg, var(--ufpel-blue-dark), var(--ufpel-blue));
}
.hero::after {
  content: "";
  position: absolute;
  inset: auto -12vw -22vw auto;
  width: 48vw;
  height: 48vw;
  border-radius: 50%;
  border: 60px solid rgba(255, 255, 255, .08);
}
.brand {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 36px;
}
.seal {
  display: grid;
  width: 58px;
  height: 58px;
  place-items: center;
  border: 2px solid rgba(255, 255, 255, .72);
  border-radius: 50%;
  color: var(--ufpel-gold);
  font-weight: 900;
  letter-spacing: .04em;
}
.brand strong { display: block; font-size: 1.08rem; }
.brand span, .subtitle, .hero-meta { color: rgba(255, 255, 255, .78); }
.hero h1 {
  max-width: 980px;
  margin: 0 0 14px;
  font-size: clamp(2.3rem, 7vw, 5.8rem);
  line-height: .95;
  letter-spacing: -.07em;
}
.subtitle { max-width: 850px; margin: 0; font-size: clamp(1rem, 2vw, 1.35rem); }
.hero-meta { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 26px; }
.hero-meta span { border: 1px solid rgba(255, 255, 255, .22); border-radius: 999px; padding: 8px 12px; background: rgba(255, 255, 255, .08); }
nav {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 12px clamp(20px, 5vw, 72px);
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, .88);
  backdrop-filter: blur(16px);
}
nav a { white-space: nowrap; border-radius: 999px; padding: 8px 12px; color: var(--ufpel-blue-dark); }
nav a:hover { background: var(--ufpel-blue-soft); text-decoration: none; }
main { width: min(1480px, calc(100% - 32px)); margin: 24px auto 64px; }
.cards { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin-bottom: 24px; }
.card, .panel, .task-card, .analysis-block {
  border: 1px solid var(--line);
  border-radius: 22px;
  background: rgba(255, 255, 255, .94);
  box-shadow: 0 18px 50px rgba(15, 43, 72, .08);
}
.card { padding: 18px; }
.card span { display: block; color: var(--muted); font-size: .85rem; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; }
.card strong { display: block; margin-top: 7px; color: var(--ufpel-blue-dark); font-size: clamp(1.35rem, 2.4vw, 2rem); }
.panel { margin-top: 22px; padding: clamp(18px, 2.4vw, 30px); }
.section-heading span {
  display: inline-flex;
  color: var(--ufpel-blue);
  font-size: .78rem;
  font-weight: 900;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.section-heading h2 { margin: 4px 0 18px; color: var(--ufpel-blue-dark); font-size: clamp(1.65rem, 3vw, 2.6rem); letter-spacing: -.04em; }
.task-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.task-card { padding: 18px; box-shadow: none; }
.task-card span { color: var(--ufpel-gold); font-weight: 900; text-transform: uppercase; }
.task-card h3 { margin: 8px 0; color: var(--ufpel-blue-dark); }
.task-card ul { padding-left: 20px; margin-bottom: 0; color: var(--muted); }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 16px; }
table { width: 100%; border-collapse: collapse; min-width: 860px; background: var(--paper); }
th, td { padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--ufpel-blue-dark); background: #f7fbff; font-size: .78rem; letter-spacing: .08em; text-transform: uppercase; }
td small { color: var(--muted); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.mini-table { min-width: 0; font-size: .86rem; }
.mini-table th, .mini-table td { padding: 5px 7px; border-bottom: 1px solid #edf2f8; }
.mini-table th { width: 44%; background: transparent; text-transform: none; letter-spacing: 0; }
.status { display: inline-flex; border-radius: 999px; padding: 4px 9px; font-size: .78rem; font-weight: 900; text-transform: uppercase; }
.status.ok { color: var(--ok); background: #e6f4ea; }
.status.bad { color: var(--bad); background: #fce8e6; }
.status.planned { color: var(--ufpel-blue); background: var(--ufpel-blue-soft); }
.analysis-block { padding: 18px; margin: 16px 0; box-shadow: none; }
.analysis-block h3 { margin-top: 0; color: var(--ufpel-blue-dark); }
.visual-panel {
  position: relative;
  overflow: hidden;
  color: #dcecff;
  border: 0;
  background:
    radial-gradient(circle at 18% 8%, rgba(27, 215, 255, .28), transparent 28%),
    radial-gradient(circle at 88% 18%, rgba(246, 195, 67, .24), transparent 24%),
    linear-gradient(135deg, #06182b 0%, #082948 54%, #061827 100%);
  box-shadow: 0 28px 90px rgba(6, 24, 43, .28);
}
.visual-panel::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px);
  background-size: 34px 34px;
  mask-image: linear-gradient(180deg, rgba(0,0,0,.9), transparent 72%);
}
.visual-panel > * { position: relative; z-index: 1; }
.visual-panel .section-heading span { color: #65dcff; }
.visual-panel .section-heading h2 { color: #fff; text-shadow: 0 0 32px rgba(27, 215, 255, .2); }
.visual-lede { max-width: 980px; margin: -6px 0 24px; color: rgba(220, 236, 255, .78); font-size: 1.05rem; }
.plot-card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.plot-card {
  overflow: hidden;
  padding: 18px;
  border: 1px solid rgba(143, 206, 255, .22);
  border-radius: 26px;
  background: linear-gradient(180deg, rgba(255,255,255,.105), rgba(255,255,255,.045));
  box-shadow: inset 0 1px 0 rgba(255,255,255,.16), 0 24px 60px rgba(0, 0, 0, .18);
  backdrop-filter: blur(18px);
}
.plot-card-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px; margin-bottom: 12px; }
.plot-card-head span { color: #65dcff; font-size: .72rem; font-weight: 900; letter-spacing: .16em; text-transform: uppercase; }
.plot-card-head h3 { max-width: 680px; margin: 0; color: #fff; font-size: clamp(1.08rem, 2vw, 1.45rem); letter-spacing: -.03em; }
.plot-note { margin: 12px 0 0; color: rgba(220, 236, 255, .72); font-size: .92rem; }
.plot-svg { display: block; width: 100%; height: auto; overflow: visible; border-radius: 18px; background: rgba(2, 12, 24, .28); }
.plot-svg.tall { min-height: 390px; }
.plot-svg.compact { min-height: 240px; }
.plot-grid { stroke: rgba(196, 226, 255, .16); stroke-width: 1; stroke-dasharray: 5 8; }
.plot-zero { stroke: rgba(246, 195, 67, .72); stroke-width: 2; stroke-dasharray: 4 5; }
.plot-axis, .plot-muted { fill: rgba(220, 236, 255, .62); font-size: 13px; font-weight: 700; }
.plot-label { fill: #f7fbff; font-size: 14px; font-weight: 900; }
.plot-label.tiny, .plot-muted.tiny { font-size: 12px; }
.plot-value { fill: #fff; font-size: 13px; font-weight: 900; }
.plot-track { fill: rgba(255, 255, 255, .08); }
.plot-empty { display: grid; min-height: 220px; place-items: center; border: 1px dashed rgba(143, 206, 255, .28); border-radius: 18px; color: rgba(220, 236, 255, .72); text-align: center; }
.mini-heading { margin-top: 28px; }
.bench-story-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.bench-story {
  padding: 16px;
  border: 1px solid rgba(143, 206, 255, .2);
  border-radius: 22px;
  background: rgba(255, 255, 255, .075);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.12);
}
.bench-story-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.bench-story-top strong { color: #fff; font-size: 1.1rem; }
.bench-story-top span { color: #65dcff; font-weight: 900; text-transform: uppercase; }
.bench-kpi { display: flex; align-items: baseline; gap: 10px; margin: 14px 0 6px; }
.bench-kpi span { color: rgba(220, 236, 255, .65); font-size: .78rem; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
.bench-kpi b { color: var(--ufpel-gold); font-size: 2rem; line-height: 1; }
.bench-story p { margin: 0 0 10px; color: rgba(220, 236, 255, .78); }
.bench-story code { color: #fff; }
.bench-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.bench-meta span { border-radius: 999px; padding: 5px 8px; color: rgba(220, 236, 255, .76); background: rgba(255,255,255,.08); font-size: .8rem; }
.mini-bars { display: grid; gap: 8px; }
.mini-bar-row { display: grid; grid-template-columns: 32px minmax(70px, 1fr) 56px; gap: 8px; align-items: center; color: rgba(220, 236, 255, .82); font-size: .82rem; }
.mini-bar-row i { position: relative; height: 9px; border-radius: 999px; background: rgba(255,255,255,.08); overflow: hidden; }
.mini-bar-row i::before { content: ""; position: absolute; inset: 0 auto 0 0; width: var(--w); border-radius: inherit; background: var(--bar); box-shadow: 0 0 18px var(--bar); }
.mini-bar-row b { color: #fff; text-align: right; font-variant-numeric: tabular-nums; }
.mini-bar-row em { grid-column: 2 / 4; color: rgba(220, 236, 255, .52); font-size: .72rem; font-style: normal; }
.conclusions-body h3, .conclusions-body h4 { color: var(--ufpel-blue-dark); }
.conclusions-body ul { padding-left: 22px; }
.conclusions-body li { margin: 6px 0; }
footer { padding: 28px clamp(20px, 5vw, 72px); color: var(--muted); border-top: 1px solid var(--line); background: #fff; }
@media (max-width: 1100px) { .cards, .task-grid, .plot-card-grid, .bench-story-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 680px) {
  .hero { padding-top: 34px; }
  .cards, .task-grid, .plot-card-grid, .bench-story-grid { grid-template-columns: 1fr; }
  main { width: min(100% - 20px, 1480px); }
  th, td { padding: 10px; }
  .plot-card { padding: 14px; border-radius: 20px; }
  .plot-card-head { display: block; }
}
    """


def build_html(results: dict[str, Any], report: dict[str, Any]) -> str:
    grouped = by_task(results["runs"])
    generated = results.get("generated_at", "")
    title = report.get("title", "Sim-OutOrder")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
  <header class="hero">
    <div class="brand">
      <div class="seal">UFPel</div>
      <div><strong>{h(report.get('institution'))}</strong><span>{h(report.get('unit'))}</span></div>
    </div>
    <h1>{h(title)}</h1>
    <p class="subtitle">Relatorio reprodutivel para investigar configuracoes de processadores superescalares com o {h(report.get('simulator'))}.</p>
    <div class="hero-meta">
      <span>{h(report.get('course'))}</span>
      <span>{h(report.get('semester'))}</span>
      <span>Gerado em {h(generated)}</span>
    </div>
  </header>
  <nav aria-label="Navegacao do relatorio">
    <a href="#overview">Resumo</a>
    <a href="#tasks">Tarefas</a>
    <a href="#benchmarks">Benchmarks</a>
    <a href="#experiments">Experimentos</a>
    <a href="#visuals">Visualizacoes</a>
    <a href="#analysis">Analise</a>
    <a href="#conclusions">Conclusoes</a>
    <a href="#methodology">Reprodutibilidade</a>
  </nav>
  <main>
    <section id="overview" class="cards">{summary_cards(results)}</section>
    {task_intro_sections(report)}
    {benchmark_section(results)}
    {experiments_section(results)}
    {visuals_section(results, grouped)}
    {analysis_section(grouped)}
    {conclusions_section()}
    {results_section(grouped)}
    {methodology_section(results)}
  </main>
  <footer>
    <strong>Nota:</strong> este site e gerado automaticamente por <code>scripts/generate_report.py</code>. Edite os dados em <code>experiments/*.json</code> e regenere o relatorio em vez de editar o HTML manualmente.
  </footer>
</body>
</html>
"""


def copy_data(results_dir: Path, output: Path) -> None:
    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename in ["results.json", "results.csv"]:
        source = results_dir / filename
        if source.exists():
            shutil.copy2(source, data_dir / filename)
    runs_source = results_dir / "runs"
    if runs_source.exists():
        shutil.copytree(runs_source, data_dir / "runs", dirs_exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="results/latest", help="Directory containing results.json")
    parser.add_argument("--output", default="site", help="Static site output directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results_dir = (ROOT / args.results).resolve() if not Path(args.results).is_absolute() else Path(args.results)
    output = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    results_path = results_dir / "results.json"
    if not results_path.exists():
        raise SystemExit(f"Missing results file: {results_path}")
    results = read_json(results_path)
    report = read_json(EXPERIMENTS_DIR / "report.json")

    if output.exists():
        shutil.rmtree(output)
    (output / "assets").mkdir(parents=True, exist_ok=True)
    copy_data(results_dir, output)
    (output / "assets" / "style.css").write_text(stylesheet(), encoding="utf-8")
    (output / "index.html").write_text(build_html(results, report), encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Generated {output / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
