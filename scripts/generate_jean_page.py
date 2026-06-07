#!/usr/bin/env python3
"""Generate Jean Reinhold's technical LI_3/VORTEX_2 report from measured data.

The analytical prose on this page is written by hand (Jean's voice). The tables
and charts stay data-driven from results.json, so the numbers remain correct and
reproducible while the narrative reads like a person wrote it. Trade-off: if the
underlying data changes substantially, the hand-cited anchor numbers in the prose
must be updated by hand as well.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
# Reuse the homepage chart/utility helpers instead of reinventing them. Running this
# script puts scripts/ on sys.path[0]; we also insert it explicitly so the import keeps
# working when the module is imported (e.g. from a test) rather than executed directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_report import chart_empty, multi_line_chart, value_range  # noqa: E402

BENCHMARKS = ["LI_3", "VORTEX_2"]
UFPEL_BLUE = "#003d73"
UFPEL_GOLD = "#f6c343"
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


# --------------------------------------------------------------------------------------
# Data-driven tables (kept correct/reproducible; only the analytical prose is authored).
# --------------------------------------------------------------------------------------


def benchmark_profile_table(data: dict[str, Any]) -> str:
    rows = []
    for benchmark in BENCHMARKS:
        bench = data.get("benchmarks", {}).get(benchmark, {})
        rows.append(
            "<tr>"
            f"<td><strong>{h(benchmark)}</strong></td>"
            f"<td>{h(bench.get('family', '-'))}</td>"
            f"<td>{h(bench.get('input'))}</td>"
            f"<td class=\"num\">{fmt(bench.get('total_instructions'))}</td>"
            f"<td class=\"num\">{fmt(bench.get('load_store_instructions'))}</td>"
            f"<td class=\"num\">{pct(load_store_ratio(bench))}</td>"
            f"<td>{h(bench.get('description', ''))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>benchmark</th><th>família</th><th>entrada</th>"
        "<th class=\"num\">instruções</th><th class=\"num\">load/store</th><th class=\"num\">fração</th>"
        f"<th>descrição</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def task1_table(data: dict[str, Any], benchmark: str) -> str:
    rows = []
    for width in [1, 2, 4, 8]:
        in_run = width_run(data, benchmark, width, True)
        ooo_run = width_run(data, benchmark, width, False)
        in_cpi = cpi(in_run)
        ooo_cpi = cpi(ooo_run)
        rows.append(
            f"<tr><td class=\"num\">{width}</td><td class=\"num\">{fmt(in_cpi)}</td><td class=\"num\">{fmt(ooo_cpi)}</td>"
            f"<td class=\"num\">{pct(rel_drop(in_cpi, ooo_cpi))}</td>"
            f"<td class=\"num\">{fmt(cycles(in_run))}</td><td class=\"num\">{fmt(cycles(ooo_run))}</td></tr>"
        )
    return (
        "<table><thead><tr><th class=\"num\">largura</th><th class=\"num\">CPI em ordem</th>"
        "<th class=\"num\">CPI fora de ordem</th><th class=\"num\">redução OOO</th>"
        "<th class=\"num\">ciclos em ordem</th><th class=\"num\">ciclos fora de ordem</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def task2_table(data: dict[str, Any], benchmark: str) -> str:
    runs = sorted(runs_for(data, benchmark, "Tarefa 2"), key=lambda run: run.get("options", {}).get("ruu:size", 0))
    baseline = cpi(runs[0]) if runs else None
    rows = []
    for run in runs:
        value = cpi(run)
        rows.append(
            f"<tr><td class=\"num\">{fmt(run.get('options', {}).get('ruu:size'))}</td>"
            f"<td class=\"num\">{fmt(run.get('options', {}).get('lsq:size'))}</td>"
            f"<td class=\"num\">{fmt(value)}</td><td class=\"num\">{fmt(cycles(run))}</td>"
            f"<td class=\"num\">{pct(rel_drop(baseline, value))}</td></tr>"
        )
    return (
        "<table><thead><tr><th class=\"num\">RUU</th><th class=\"num\">LSQ</th><th class=\"num\">CPI</th>"
        "<th class=\"num\">ciclos</th><th class=\"num\">ganho vs RUU 4</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def task3_table(data: dict[str, Any], benchmark: str) -> str:
    perfect = pred_run(data, benchmark, "perfect")
    perfect_cpi = cpi(perfect)
    rows = []
    for name in ["perfect", "bimod", "taken", "nottaken"]:
        run = pred_run(data, benchmark, name)
        value = cpi(run)
        rows.append(
            f"<tr><td>{h(name)}</td><td class=\"num\">{fmt(value)}</td><td class=\"num\">{fmt(cycles(run))}</td>"
            f"<td class=\"num\">{fmt(first_metric(run, 'bpred_dir_rate', 'bpred_'))}</td>"
            f"<td class=\"num\">{fmt(first_metric(run, 'misses', 'bpred_'))}</td>"
            f"<td class=\"num\">{pct(rel_increase(perfect_cpi, value))}</td></tr>"
        )
    return (
        "<table><thead><tr><th>previsor</th><th class=\"num\">CPI</th><th class=\"num\">ciclos</th>"
        "<th class=\"num\">taxa direção</th><th class=\"num\">misses</th><th class=\"num\">vs perfect</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def task4_table(data: dict[str, Any], benchmark: str) -> str:
    rows = []
    for experiment in TASK4_FINAL[benchmark]:
        run = find_run(data, benchmark, experiment)
        options = run.get("options", {}) if run else {}
        rows.append(
            f"<tr><td><strong>{h(TASK4_LABELS.get(experiment, experiment))}</strong><br><code>{h(experiment)}</code></td>"
            f"<td class=\"num\">{fmt(cpi(run))}</td><td class=\"num\">{fmt(cycles(run))}</td>"
            f"<td class=\"num\">{fmt(cost_index(options), 1)}</td>"
            f"<td class=\"num\">{fmt(options.get('issue:width'))}</td><td class=\"num\">{fmt(options.get('ruu:size'))}</td>"
            f"<td class=\"num\">{fmt(options.get('lsq:size'))}</td><td class=\"num\">{fmt(options.get('res:memport'))}</td>"
            f"<td class=\"num\">{fmt(options.get('res:ialu'))}</td><td class=\"num\">{fmt(options.get('res:imult'))}</td>"
            f"<td class=\"num\">{fmt(options.get('res:fpalu'))}/{fmt(options.get('res:fpmult'))}</td></tr>"
        )
    return (
        "<table><thead><tr><th>configuração</th><th class=\"num\">CPI</th><th class=\"num\">ciclos</th>"
        "<th class=\"num\">custo</th><th class=\"num\">width</th><th class=\"num\">RUU</th><th class=\"num\">LSQ</th>"
        "<th class=\"num\">mem</th><th class=\"num\">IALU</th><th class=\"num\">IMult</th><th class=\"num\">FP</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def coverage_table() -> str:
    rows = [
        ("Tarefa 1", "Impacto da largura em CPI", "Reduz o CPI nos dois (LI_3 ~17%, VORTEX_2 ~24% em ordem), com retornos decrescentes.", "Seção 3"),
        ("Tarefa 1", "Impacto da execução fora de ordem", "Pequeno na largura 1 (~1.5%) e grande na largura 8 (LI_3 26%, VORTEX_2 20%).", "Seção 3"),
        ("Tarefa 1", "Pipeline largo: em ordem ou fora de ordem?", "Fora de ordem; o menor CPI de cada benchmark está na largura 8 OOO.", "Seção 3"),
        ("Tarefa 2", "Impacto de janelas maiores", "Reduzem o CPI (LI_3 26%, VORTEX_2 29% de RUU 4 a 64).", "Seção 4"),
        ("Tarefa 2", "A melhoria satura?", "Não até RUU 64, mas o ganho do último passo cai para 3% a 5%.", "Seção 4"),
        ("Tarefa 3", "Estatísticas de uso do previsor", "Taxa de direção e de endereço, consultas e misses (bimod acerta 0.9247 e 0.9718 a direção).", "Seção 5"),
        ("Tarefa 3", "Impacto no CPI vs. perfect", "Bimod ~5.75% acima no LI_3; junto do perfect no VORTEX_2; estáticos bem piores.", "Seção 5"),
        ("Tarefa 3", "Ganho relativo do bimodal", "~24% sobre os estáticos no LI_3, ~11% no VORTEX_2.", "Seção 5"),
        ("Tarefa 4", "Menor CPI por benchmark", "Robusto nos dois (LI_3 1.8929, VORTEX_2 3.7361).", "Seção 6"),
        ("Tarefa 4", "A vencedora justifica o custo?", "Em CPI sim; em custo-benefício a equilibrada/memória compensa mais.", "Seção 6"),
        ("Tarefa 4", "Custos além do CPI", "Área, energia, frequência, complexidade de RUU/LSQ e verificação.", "Seção 6"),
    ]
    body = "".join(
        f"<tr><td>{h(task)}</td><td>{h(question)}</td><td>{h(answer)}</td><td>{h(where)}</td></tr>"
        for task, question, answer, where in rows
    )
    return (
        "<table><thead><tr><th>tarefa</th><th>pergunta do enunciado</th><th>resposta curta</th><th>seção</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


COST_WEIGHT_LABELS = {
    "res:memport": "porta de memória",
    "res:imult": "multiplicador inteiro",
    "res:fpmult": "multiplicador de ponto flutuante",
    "issue:width": "largura de emissão",
    "res:ialu": "ALU inteira",
    "res:fpalu": "ALU de ponto flutuante",
    "decode:width": "largura de decode",
    "commit:width": "largura de commit",
    "lsq:size": "entrada de LSQ",
    "fetch:ifqsize": "entrada da fila de fetch",
    "ruu:size": "entrada de RUU",
}


def cost_weights_table() -> str:
    rows = []
    for key, weight in sorted(COST_WEIGHTS.items(), key=lambda item: item[1], reverse=True):
        rows.append(
            f"<tr><td>{h(COST_WEIGHT_LABELS.get(key, key))}</td>"
            f"<td><code>{h(key)}</code></td>"
            f"<td class=\"num\">{fmt(weight, 1)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>recurso</th><th>parâmetro</th><th class=\"num\">peso por unidade</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


# --------------------------------------------------------------------------------------
# Charts. Tasks 1-2 reuse the homepage line chart (light-themed by this page's CSS).
# Tasks 3-4 use small bespoke builders because the requirement is per-benchmark
# (the homepage versions average across benchmarks). All draw dark ink on light paper.
# --------------------------------------------------------------------------------------


def figure(svg: str, caption: str) -> str:
    return f'<figure class="fig">{svg}<figcaption>{h(caption)}</figcaption></figure>'


def light_line_chart(title: str, x_values: list[int], series: list[tuple[str, dict[int, float], str]], x_label: str) -> str:
    # multi_line_chart hardcodes a "CPI medio" y-axis label; here every curve is a single
    # benchmark (not an average), so relabel it to plain "CPI".
    return multi_line_chart(title, x_values, series, x_label).replace("CPI medio", "CPI")


def task1_line_chart(data: dict[str, Any], benchmark: str) -> str:
    widths = [1, 2, 4, 8]
    in_order = {w: value for w in widths if (value := cpi(width_run(data, benchmark, w, True))) is not None}
    out_order = {w: value for w in widths if (value := cpi(width_run(data, benchmark, w, False))) is not None}
    series = [
        ("em ordem", in_order, UFPEL_GOLD),
        ("fora de ordem", out_order, UFPEL_BLUE),
    ]
    return light_line_chart(f"CPI por largura no {benchmark}", widths, series, "largura de issue / decode / commit")


def task2_line_chart(data: dict[str, Any]) -> str:
    ruus = [4, 8, 16, 32, 64]
    li = {r: value for r in ruus if (value := cpi(window_run(data, "LI_3", r))) is not None}
    vo = {r: value for r in ruus if (value := cpi(window_run(data, "VORTEX_2", r))) is not None}
    series = [
        ("LI_3", li, UFPEL_BLUE),
        ("VORTEX_2", vo, UFPEL_GOLD),
    ]
    return light_line_chart("CPI por tamanho da janela", ruus, series, "tamanho da RUU (a LSQ cresce junto)")


def task3_bar_chart(data: dict[str, Any]) -> str:
    predictors = ["perfect", "bimod", "taken", "nottaken"]
    series = [("LI_3", UFPEL_BLUE), ("VORTEX_2", UFPEL_GOLD)]
    values: dict[tuple[str, str], float] = {}
    observed: list[float] = []
    for name in predictors:
        for bench, _color in series:
            value = cpi(pred_run(data, bench, name))
            if value is not None:
                values[(name, bench)] = value
                observed.append(value)
    if not observed:
        return chart_empty("Sem resultados completos de previsores para o gráfico.")

    width, height = 980, 360
    left, top, plot_w, plot_h = 64, 30, 856, 250
    y_max = max(observed) * 1.08
    grid = []
    for i in range(5):
        y_value = y_max * i / 4
        y = top + (1 - i / 4) * plot_h
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="plot-grid"/>')
        grid.append(f'<text x="{left - 10}" y="{y + 4:.1f}" class="plot-axis" text-anchor="end">{fmt(y_value, 1)}</text>')

    group_w = plot_w / len(predictors)
    bar_w = group_w * 0.30
    gap = group_w * 0.06
    bars = []
    labels = []
    for gi, name in enumerate(predictors):
        center = left + group_w * gi + group_w / 2
        positions = [center - gap / 2 - bar_w, center + gap / 2]
        for (bench, color), x0 in zip(series, positions):
            value = values.get((name, bench))
            if value is None:
                continue
            y = top + (1 - value / y_max) * plot_h
            bar_h = top + plot_h - y
            bars.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="3" fill="{color}"/>')
            bars.append(f'<text x="{x0 + bar_w / 2:.1f}" y="{y - 6:.1f}" class="plot-value" text-anchor="middle">{fmt(value, 2)}</text>')
        labels.append(f'<text x="{center:.1f}" y="{top + plot_h + 26:.1f}" class="plot-label" text-anchor="middle">{h(name)}</text>')

    legend = []
    for i, (bench, color) in enumerate(series):
        x = left + i * 150
        legend.append(f'<rect x="{x}" y="{height - 22}" width="14" height="14" rx="3" fill="{color}"/>')
        legend.append(f'<text x="{x + 20}" y="{height - 11}" class="plot-axis">{h(bench)}</text>')

    return (
        f'<svg class="plot-svg" viewBox="0 0 {width} {height}" role="img" aria-label="CPI por previsor e benchmark">'
        f'<title>CPI por previsor e benchmark</title>'
        f'<text x="18" y="20" class="plot-axis">CPI por previsor (menor é melhor)</text>'
        f"{''.join(grid)}{''.join(bars)}{''.join(labels)}{''.join(legend)}</svg>"
    )


def task4_pyramid(data: dict[str, Any]) -> str:
    tiers = [
        ("Robusto", "task4_li3_robusto", "task4_vortex2_robusto", "#003d73"),
        ("Equilibrado · Memória", "task4_li3_equilibrado", "task4_vortex2_memoria", "#2f6092"),
        ("Econômico", "task4_li3_economico", "task4_vortex2_economico", "#6d92b8"),
    ]
    geometry = [(24, 112, 150, 220), (116, 204, 220, 290), (208, 296, 290, 360)]
    center = 490
    blocks = []
    for (name, li_exp, vo_exp, color), (top_y, bottom_y, top_hw, bottom_hw) in zip(tiers, geometry):
        li = find_run(data, "LI_3", li_exp)
        vo = find_run(data, "VORTEX_2", vo_exp)
        li_cost = cost_index(li.get("options", {})) if li else None
        vo_cost = cost_index(vo.get("options", {})) if vo else None
        pts = (
            f"{center - top_hw},{top_y} {center + top_hw},{top_y} "
            f"{center + bottom_hw},{bottom_y} {center - bottom_hw},{bottom_y}"
        )
        mid = (top_y + bottom_y) / 2
        blocks.append(
            f'<polygon points="{pts}" fill="{color}"/>'
            f'<text x="{center}" y="{mid - 13:.0f}" text-anchor="middle" fill="#ffffff" font-size="17" font-weight="700">{h(name)}</text>'
            f'<text x="{center}" y="{mid + 7:.0f}" text-anchor="middle" fill="#eaf2fb" font-size="12.5">LI_3 · CPI {fmt(cpi(li), 2)} · custo {fmt(li_cost, 0)}</text>'
            f'<text x="{center}" y="{mid + 25:.0f}" text-anchor="middle" fill="#eaf2fb" font-size="12.5">VORTEX_2 · CPI {fmt(cpi(vo), 2)} · custo {fmt(vo_cost, 0)}</text>'
        )
    return (
        '<svg class="plot-svg" viewBox="0 0 980 320" role="img" aria-label="As três frentes de configuração da Tarefa 4">'
        '<title>As três frentes de configuração da Tarefa 4</title>'
        '<text x="18" y="16" class="plot-axis">do menor custo (base) ao máximo desempenho (topo)</text>'
        f'{"".join(blocks)}</svg>'
    )


def task4_scatter_chart(final: dict[str, Any], search: dict[str, Any] | None = None) -> str:
    groups = [("LI_3", UFPEL_BLUE), ("VORTEX_2", UFPEL_GOLD)]
    color_of = dict(groups)
    final_points: list[tuple[str, str, float, float]] = []
    for bench, color in groups:
        for experiment in TASK4_FINAL[bench]:
            run = find_run(final, bench, experiment)
            if not run:
                continue
            value = cpi(run)
            if value is None:
                continue
            final_points.append((TASK4_LABELS.get(experiment, experiment), color, cost_index(run.get("options", {})), value))
    if len(final_points) < 2:
        return chart_empty("São necessárias ao menos duas configurações completas para o gráfico de custo.")

    search_points: list[tuple[str, float, float]] = []
    if search:
        for run in search.get("runs", []):
            bench = run.get("benchmark")
            if run.get("status") != "completed" or bench not in color_of:
                continue
            value = cpi(run)
            if value is None:
                continue
            search_points.append((color_of[bench], cost_index(run.get("options", {})), value))

    costs = [point[2] for point in final_points] + [point[1] for point in search_points]
    cpis = [point[3] for point in final_points] + [point[2] for point in search_points]
    x_min, x_max = value_range(costs, 0.08)
    y_min, y_max = value_range(cpis, 0.08)
    width, height = 980, 410
    left, top, plot_w, plot_h = 64, 28, 856, 286

    def place(cost: float, value: float) -> tuple[float, float]:
        x = left + (cost - x_min) / (x_max - x_min) * plot_w
        y = top + (y_max - value) / (y_max - y_min) * plot_h
        return x, y

    grid = []
    for i in range(4):
        x = left + plot_w * i / 3
        x_value = x_min + (x_max - x_min) * i / 3
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="plot-grid"/>')
        grid.append(f'<text x="{x:.1f}" y="{top + plot_h + 26:.1f}" class="plot-axis" text-anchor="middle">{fmt(x_value, 0)}</text>')
    for i in range(4):
        y = top + plot_h * i / 3
        y_value = y_max - (y_max - y_min) * i / 3
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="plot-grid"/>')
        grid.append(f'<text x="{left - 10}" y="{y + 4:.1f}" class="plot-axis" text-anchor="end">{fmt(y_value, 2)}</text>')

    cloud = []
    for color, cost, value in search_points:
        x, y = place(cost, value)
        cloud.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}" opacity="0.3"/>')

    marks = []
    for label, color, cost, value in final_points:
        x, y = place(cost, value)
        marks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7.5" fill="{color}" stroke="#ffffff" stroke-width="2"/>'
            f'<text x="{x + 12:.1f}" y="{y - 6:.1f}" class="plot-label tiny">{h(label)}</text>'
            f'<text x="{x + 12:.1f}" y="{y + 9:.1f}" class="plot-muted tiny">{fmt(value, 2)} CPI</text>'
        )

    legend = []
    for i, (bench, color) in enumerate(groups):
        x = left + i * 150
        legend.append(f'<circle cx="{x + 6}" cy="{height - 13}" r="6" fill="{color}"/>')
        legend.append(f'<text x="{x + 18}" y="{height - 9}" class="plot-axis">{h(bench)}</text>')
    if search_points:
        legend.append(f'<circle cx="{left + 320}" cy="{height - 13}" r="3" fill="#9bb6cf"/>')
        legend.append(f'<text x="{left + 330}" y="{height - 9}" class="plot-axis">configurações da busca</text>')

    return (
        f'<svg class="plot-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Custo arquitetural contra CPI">'
        f'<title>Custo arquitetural contra CPI</title>{"".join(grid)}'
        f'<text x="18" y="18" class="plot-axis">CPI medido (menor é melhor)</text>'
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 30:.1f}" class="plot-axis" text-anchor="middle">índice de custo arquitetural (heurístico)</text>'
        f'{"".join(cloud)}{"".join(marks)}{"".join(legend)}</svg>'
    )


# --------------------------------------------------------------------------------------
# Hand-written analysis. Numbers below are the measured anchors from results/jean-final
# (46/46 runs). They are cited as literal prose so the page reads like a person wrote it.
# --------------------------------------------------------------------------------------


def task1_prose() -> str:
    return """
    <p>O aumento de largura reduz o CPI nos dois benchmarks, com retornos decrescentes. No LI_3 em ordem, o CPI cai de 3.2732 na largura 1 para 2.7228 na largura 8, cerca de 17%, e boa parte desse ganho já se realiza até a largura 4 (2.8358). O VORTEX_2 repete o padrão num patamar mais alto, de 6.3690 para 4.8375. A diferença de patamar entre eles vem da memória: o VORTEX_2 erra 9.71% dos acessos na cache de instruções e 7.63% na de dados, contra 2.78% e 4.90% do LI_3, e essas faltas seguram o CPI seja qual for a largura.</p>
    <p>A execução fora de ordem só rende quando há largura para aproveitar. Na largura 1 ela quase não muda nada, melhorando 1.20% no LI_3 e 1.50% no VORTEX_2, o que faz sentido: com um único slot de emissão por ciclo, não há como reordenar para ganhar trabalho. Na largura 8 a diferença aparece. O LI_3 passa de 2.7228 em ordem para 2.0048 fora de ordem (IPC de 0.50), 26% a menos, e o VORTEX_2 vai de 4.8375 para 3.8685, perto de 20%.</p>
    <p>Sobre qual configuração aproveita melhor um pipeline largo, os dados não deixam dúvida: o menor CPI de cada benchmark, 2.0048 no LI_3 e 3.8685 no VORTEX_2, está sempre na largura 8 fora de ordem. Em ordem, um pipeline largo continua preso à sequência do programa, porque uma instrução bloqueada trava as seguintes. É a reordenação que transforma a largura em instruções de fato executadas.</p>
    """


def task2_prose() -> str:
    return """
    <p>Janelas maiores reduzem o CPI de forma consistente. O LI_3 cai de 2.7480 (RUU 4) para 2.0242 (RUU 64), cerca de 26%, e o VORTEX_2 de 5.4423 para 3.8872, cerca de 29%. O passo mais forte é o primeiro, de RUU 4 para 8, que sozinho entrega perto de 15% nos dois casos (LI_3 de 2.7480 para 2.3422, VORTEX_2 de 5.4423 para 4.6325).</p>
    <p>As estatísticas de ocupação explicam esse comportamento melhor do que o CPI isolado. Com RUU 4, a fila de reordenação do LI_3 ficava cheia em 31.75% dos ciclos, ou seja, em quase um terço do tempo havia instrução pronta esperando vaga. Com RUU 64 esse número cai para 8.05% e a ocupação média sobe de 1.99 para 13.63 entradas. No VORTEX_2 o gargalo não é a RUU e sim a LSQ: com a janela pequena, a fila de load/store ficava cheia em 39.30% dos ciclos, coerente com o peso de memória do benchmark. Ampliar a janela alivia exatamente essa pressão.</p>
    <p>A melhoria não satura por completo até RUU 64, mas perde força. O último degrau, de RUU 32 para 64, rende só 3.50% no LI_3 (2.0976 para 2.0242) e 4.82% no VORTEX_2 (4.0842 para 3.8872). Como nesse ponto a fila fica cheia em menos de 9% dos ciclos, resta pouco a recuperar aumentando a janela, e o custo de RUU e LSQ passa a pesar mais que o ganho. Foi com base nisso que defini as janelas da Tarefa 4.</p>
    """


def task3_prose() -> str:
    return """
    <p>O bimodal acerta a direção do desvio em 0.9247 dos casos no LI_3 e em 0.9718 no VORTEX_2, e o acerto do endereço alvo acompanha de perto (0.8931 e 0.9677). O volume também difere: o LI_3 faz 53.1 milhões de consultas ao previsor e erra 3.1 milhões delas, enquanto o VORTEX_2 faz 10.5 milhões de consultas e erra apenas 287 mil. Os previsores estáticos ficam em torno de 0.35 de acerto de direção nos dois benchmarks, o que confirma que uma regra fixa não acompanha o padrão de desvios desses programas.</p>
    <p>O custo no CPI varia bastante. No LI_3 o perfect mede 2.0755 e o bimodal 2.1949, cerca de 5.75% acima, enquanto taken e nottaken passam de 2.9, sinal de que o erro de desvio pesa de verdade aqui.</p>
    <p>No VORTEX_2 chama atenção o bimodal (4.2781) aparecer abaixo do perfect (4.3900) na tabela. Fui investigar, e não é o previsor superando um oráculo. As duas execuções concluem exatamente as mesmas 65.133.533 instruções, então a diferença está só nos ciclos: o perfect gasta 285,9 milhões e o bimodal 278,6 milhões. A causa é a cache de instruções. Com previsão perfeita, o front-end nunca é descartado e busca de forma contínua e agressiva, acumulando 82,2 milhões de acessos à cache de instruções contra 74,0 milhões do bimodal; num benchmark cuja taxa de falta de instruções já é alta (perto de 9%), esse excesso de busca vira mais faltas em valor absoluto, 7,53 milhões contra 7,26 milhões. Essas cerca de 270 mil faltas a mais respondem por quase toda a diferença de 7,3 milhões de ciclos. Um previsor real, ao errar de vez em quando, acaba freando o front-end e segurando essa pressão sobre a cache. A ordem só se inverte aqui porque o VORTEX_2 é fortemente limitado pela cache de instruções; no LI_3, com taxa de falta perto de 3%, o perfect é mais rápido como esperado (380,5 contra 402,4 milhões de ciclos).</p>
    <p>O ganho do bimodal sobre os estáticos é o resultado mais consistente. No LI_3 ele reduz o CPI em torno de 24% tanto contra taken quanto contra nottaken; no VORTEX_2, onde havia menos a recuperar, a redução fica perto de 11%. Para o custo de uma tabela de contadores de 2 bits, é um retorno alto, que cobre boa parte da distância até o previsor perfeito.</p>
    """


def task4_prose() -> str:
    return """
    <p>Em CPI, a configuração robusta vence nos dois benchmarks. No LI_3 ela chega a 1.8929 (IPC 0.53), com largura 8, RUU 128, LSQ 64 e quatro portas de memória, à frente dos 2.0242 da equilibrada e dos 2.1369 da econômica. No VORTEX_2 a robusta também lidera, com 3.7361 (IPC 0.27), usando LSQ 128 no lugar de 64, contra 3.8872 da configuração de memória e 4.1063 da econômica.</p>
    <p>A questão é se esse CPI menor compensa o custo. No LI_3, a robusta melhora 6.49% sobre a equilibrada e para isso leva o índice de custo de 125.0 para 241.0, um aumento de 93%. Se o critério for só CPI, fico com a robusta; havendo orçamento de área e energia, a equilibrada se defende melhor, porque entrega 2.0242 por bem menos. No VORTEX_2 o desequilíbrio é maior: a robusta ganha apenas 3.89% sobre a configuração de memória e ainda assim leva o custo de 125.0 para 285.8. Como esse benchmark move 18.6 milhões de loads e 16.4 milhões de stores, ou 53.7% das instruções, investir em LSQ e memória se justifica, mas a LSQ de 128 entradas já passa do ponto de equilíbrio.</p>
    <p>Convém olhar além do CPI também porque ele não conta tudo. A taxa de faltas na cache de dados quase não se mexe entre as três configurações, ficando perto de 5% no LI_3 e 7.2% no VORTEX_2, o que indica que ampliar janela e portas resolve a vazão, não a localidade dos acessos. Num projeto real eu pesaria área, energia, frequência de clock, a complexidade do wakeup/select da RUU, o número de comparadores da LSQ e o esforço de verificação, que são os custos que crescem ao ampliar essas estruturas. E manteria a distinção entre recurso útil e recurso caro: janela, LSQ e memória têm justificativa nos dados; ampliar ponto flutuante não tem, porque as duas cargas são majoritariamente inteiras.</p>
    """


def css() -> str:
    return """
:root {
  --ufpel-blue:#003d73; --ufpel-blue-dark:#06233f; --ufpel-blue-soft:#e7f0f8;
  --ufpel-gold:#f6c343; --ink:#162033; --muted:#5d6b80; --line:#d8e1ec;
  --paper:#ffffff; --bg:#f3f7fb; --ok:#137333;
  --serif: Georgia, "Times New Roman", serif;
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; color:var(--ink); background:var(--bg); line-height:1.62;
  font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
a { color:var(--ufpel-blue); font-weight:700; text-decoration:none; }
a:hover { text-decoration:underline; }
code { font-family:"SFMono-Regular", Consolas, "Liberation Mono", monospace; color:var(--ufpel-blue-dark); font-size:.92em; }
.page { width:min(100% - 32px, 960px); margin:28px auto 56px; background:var(--paper);
  border:1px solid var(--line); border-radius:18px; box-shadow:0 18px 50px rgba(15,43,72,.08); overflow:hidden; }
header.masthead { padding:40px clamp(22px,5vw,56px) 30px; border-bottom:1px solid var(--line);
  background:linear-gradient(180deg,#f7fbff,#fff); }
.brand { display:flex; gap:14px; align-items:center; margin-bottom:26px; }
.seal { display:grid; width:54px; height:54px; place-items:center; border-radius:50%;
  background:var(--ufpel-blue); color:var(--ufpel-gold); font-family:var(--serif); font-weight:700; font-size:.95rem; letter-spacing:.01em; }
.brand strong { display:block; color:var(--ufpel-blue-dark); font-size:1.02rem; }
.brand span { display:block; color:var(--muted); font-size:.9rem; }
.eyebrow { margin:0 0 10px; color:var(--ufpel-blue); font-size:.74rem; font-weight:900; letter-spacing:.14em; text-transform:uppercase; }
h1 { margin:0; font-family:var(--serif); color:var(--ufpel-blue-dark); font-size:clamp(2rem,4.5vw,3.1rem); line-height:1.07; letter-spacing:-.01em; }
.lede { max-width:730px; margin:16px 0 0; color:#33414f; font-size:1.06rem; }
dl.meta { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px 28px; margin:26px 0 0; padding-top:20px; border-top:1px solid var(--line); }
dl.meta div { display:grid; grid-template-columns:120px 1fr; gap:12px; align-items:baseline; }
dl.meta dt { color:var(--muted); font-size:.78rem; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
dl.meta dd { margin:0; color:var(--ink); font-weight:700; }
nav { position:sticky; top:0; z-index:10; display:flex; flex-wrap:wrap; gap:8px;
  padding:11px clamp(22px,5vw,56px); border-bottom:1px solid var(--line);
  background:rgba(255,255,255,.9); backdrop-filter:blur(14px); }
nav a { white-space:nowrap; border-radius:999px; padding:7px 12px; color:var(--ufpel-blue-dark); font-size:.85rem; font-weight:700; }
nav a:hover { background:var(--ufpel-blue-soft); text-decoration:none; }
nav a.home { color:var(--ufpel-blue); }
main { padding:30px clamp(22px,5vw,56px) 46px; }
section { margin:0 0 38px; }
section + section { padding-top:32px; border-top:1px solid var(--line); }
h2 { margin:0 0 8px; font-family:var(--serif); color:var(--ufpel-blue-dark); font-size:clamp(1.5rem,3vw,2rem); line-height:1.16; }
h3 { margin:26px 0 8px; font-family:var(--serif); color:var(--ufpel-blue-dark); font-size:1.2rem; }
p { margin:0 0 14px; max-width:760px; }
.section-note { color:#3d4850; max-width:760px; }
.subhead { margin:20px 0 2px; color:var(--ufpel-blue-dark); font-weight:800; font-size:.92rem; letter-spacing:.01em; }
.table-wrap { overflow-x:auto; margin:8px 0 6px; border:1px solid var(--line); border-radius:14px; }
table { width:100%; border-collapse:collapse; background:var(--paper); font-size:.9rem; }
th, td { padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
th { color:var(--ufpel-blue-dark); background:#f7fbff; font-size:.72rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
td:last-child { white-space:normal; }
tbody tr:last-child td { border-bottom:0; }
.fig { margin:18px 0 6px; padding:16px 16px 10px; border:1px solid var(--line); border-radius:14px; background:#fcfdff; }
.fig figcaption { margin:10px 4px 0; color:var(--muted); font-size:.86rem; }
.method, .conclusion { padding:16px 18px; border:1px solid var(--line); border-left:4px solid var(--ufpel-gold); border-radius:12px; background:#fbfcfe; }
.method p:last-child, .conclusion p:last-child { margin-bottom:0; }
.coverage table { font-size:.86rem; }
.plot-svg { display:block; width:100%; height:auto; overflow:visible; background:transparent; }
.plot-grid { stroke:var(--line); stroke-width:1; stroke-dasharray:4 6; }
.plot-axis, .plot-muted { fill:var(--muted); font-size:13px; font-weight:600; }
.plot-label { fill:var(--ink); font-size:13px; font-weight:700; }
.plot-label.tiny, .plot-muted.tiny { font-size:11px; }
.plot-value { fill:var(--ufpel-blue-dark); font-size:12px; font-weight:700; }
.plot-track { fill:#eef3f9; }
.plot-zero { stroke:var(--ufpel-gold); stroke-width:2; stroke-dasharray:4 5; }
.plot-empty { display:grid; min-height:160px; place-items:center; border:1px dashed var(--line); border-radius:12px; color:var(--muted); text-align:center; }
footer { padding:22px clamp(22px,5vw,56px) 30px; color:var(--muted); border-top:1px solid var(--line); background:#f7fbff; font-size:.9rem; }
@media (max-width:760px) {
  dl.meta { grid-template-columns:1fr; }
  dl.meta div { grid-template-columns:108px 1fr; }
}
@media print {
  body { background:#fff; }
  .page { width:100%; margin:0; border:0; border-radius:0; box-shadow:none; }
  nav { display:none; }
  a { color:inherit; text-decoration:none; }
  .fig, section { break-inside:avoid; }
}
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
    <header class="masthead">
      <div class="brand">
        <div class="seal">UFPel</div>
        <div><strong>Universidade Federal de Pelotas</strong><span>Centro de Desenvolvimento Tecnológico</span></div>
      </div>
      <p class="eyebrow">Relatório técnico · SimpleScalar sim-outorder</p>
      <h1>Jean Reinhold: LI_3 e VORTEX_2</h1>
      <p class="lede">Medições no sim-outorder do efeito de largura, execução fora de ordem, tamanho de janela e previsão de desvios sobre o CPI, com uma customização final por benchmark.</p>
      <dl class="meta">
        <div><dt>Autor</dt><dd>Jean Reinhold</dd></div>
        <div><dt>Benchmarks</dt><dd>LI_3 e VORTEX_2</dd></div>
        <div><dt>Simulador</dt><dd>SimpleScalar sim-outorder</dd></div>
        <div><dt>Dados</dt><dd><a href="data/jean-final-results.json">resultados em JSON</a></dd></div>
      </dl>
    </header>
    <nav aria-label="Sumário">
      <a class="home" href="index.html">← relatório geral</a>
      <a href="#perfil">perfil</a>
      <a href="#cobertura">cobertura</a>
      <a href="#t1">tarefa 1</a>
      <a href="#t2">tarefa 2</a>
      <a href="#t3">tarefa 3</a>
      <a href="#t4">tarefa 4</a>
      <a href="#dados">dados</a>
    </nav>
    <main>
      <section id="perfil">
        <h2>1. Perfil dos benchmarks e método</h2>
        <p class="section-note">Trabalhei apenas com LI_3 e VORTEX_2. Antes dos números, vale registrar o que cada um exercita. O LI_3 é um interpretador Lisp rodando a entrada <code>train.lsp</code>, com pouco mais de 183 milhões de instruções, das quais 42.45% acessam memória. O VORTEX_2 é uma carga de banco de dados orientado a objetos com a entrada <code>tiny.in</code>, menor em volume (cerca de 65 milhões de instruções), porém mais pesada em memória: 53.72% das instruções são load ou store. Essa diferença de perfil pesa em quase toda a análise adiante, sobretudo na customização da Tarefa 4.</p>
        <div class="table-wrap">{benchmark_profile_table(final)}</div>
        <div class="method"><p><strong>Método.</strong> As Tarefas 1 a 3 seguem exatamente as configurações pedidas no enunciado. Para a Tarefa 4 eu fiz primeiro uma busca exploratória mais ampla e só depois escolhi três configurações finais por benchmark, respeitando o limite do trabalho. {h(search_note)}</p></div>
      </section>
      <section id="cobertura">
        <h2>2. Onde cada pergunta é respondida</h2>
        <p class="section-note">Para facilitar a correção, deixo um mapa rápido das perguntas do enunciado. Ele não é o foco da página; as respostas vêm por extenso no texto de cada tarefa.</p>
        <div class="table-wrap coverage">{coverage_table()}</div>
      </section>
      <section id="t1">
        <h2>3. Tarefa 1: execução em ordem e fora de ordem</h2>
        <p class="section-note">Medi ciclos e CPI para as larguras 1, 2, 4 e 8, comparando o despacho em ordem com o despacho fora de ordem.</p>
        <p class="subhead">LI_3</p>
        <div class="table-wrap">{task1_table(final, 'LI_3')}</div>
        <p class="subhead">VORTEX_2</p>
        <div class="table-wrap">{task1_table(final, 'VORTEX_2')}</div>
        {figure(task1_line_chart(final, 'LI_3'), 'CPI por largura no LI_3. As curvas em ordem e fora de ordem só se afastam a partir da largura 2.')}
        {figure(task1_line_chart(final, 'VORTEX_2'), 'CPI por largura no VORTEX_2, no mesmo padrão do LI_3 mas em um patamar mais alto.')}
        {task1_prose()}
      </section>
      <section id="t2">
        <h2>4. Tarefa 2: tamanho da janela de instruções</h2>
        <p class="section-note">Variei o tamanho da RUU de 4 a 64, sempre fora de ordem. Como nas minhas configurações a LSQ cresce junto com a RUU, leio o efeito como o da janela de instruções inteira, e não só da fila de reordenação.</p>
        <p class="subhead">LI_3</p>
        <div class="table-wrap">{task2_table(final, 'LI_3')}</div>
        <p class="subhead">VORTEX_2</p>
        <div class="table-wrap">{task2_table(final, 'VORTEX_2')}</div>
        {figure(task2_line_chart(final), 'CPI por tamanho da RUU. As duas curvas achatam à direita, sinal claro de retornos decrescentes.')}
        {task2_prose()}
      </section>
      <section id="t3">
        <h2>5. Tarefa 3: previsão de desvios</h2>
        <p class="section-note">Comparei os previsores <code>nottaken</code>, <code>taken</code> e <code>bimod</code>, usando o <code>perfect</code> como referência. O bimodal é uma tabela de contadores saturantes de 2 bits indexada pelo endereço do desvio.</p>
        <p class="subhead">LI_3</p>
        <div class="table-wrap">{task3_table(final, 'LI_3')}</div>
        <p class="subhead">VORTEX_2</p>
        <div class="table-wrap">{task3_table(final, 'VORTEX_2')}</div>
        {figure(task3_bar_chart(final), 'CPI por previsor. As barras estáticas (taken e nottaken) deixam visível o custo de não prever desvios.')}
        {task3_prose()}
      </section>
      <section id="t4">
        <h2>6. Tarefa 4: customização do processador</h2>
        <p class="section-note">Parti de uma busca exploratória com 99 configurações por benchmark e dela destaquei três frentes: uma econômica, uma intermediária e uma robusta. Comparo o desempenho de cada uma a um índice de custo heurístico, usado para organizar a discussão, não como estimativa física de área.</p>
        <h3>O índice de custo</h3>
        <p>O índice é uma soma ponderada dos recursos de cada configuração. Os pesos refletem o custo relativo aproximado de cada estrutura: uma porta de memória pesa 10, os multiplicadores pesam 6 e a largura e as ALUs ficam entre 2 e 3, enquanto cada entrada de RUU (0.4) e de LSQ (0.7) sai barata por unidade. Não é um modelo de área, mas captura a ideia de que dobrar portas de memória custa muito mais do que somar algumas entradas de janela.</p>
        <div class="table-wrap">{cost_weights_table()}</div>
        <p class="subhead">LI_3</p>
        <div class="table-wrap">{task4_table(final, 'LI_3')}</div>
        <p class="subhead">VORTEX_2</p>
        <div class="table-wrap">{task4_table(final, 'VORTEX_2')}</div>
        {figure(task4_pyramid(final), 'As três frentes de configuração, da base econômica ao topo robusto. Os valores são por benchmark.')}
        {figure(task4_scatter_chart(final, search), 'Custo contra CPI. Os pontos claros são as 99 configurações simuladas na busca por benchmark; os destacados são as três escolhidas.')}
        {task4_prose()}
      </section>
      <section id="dados">
        <h2>7. Dados e limitações</h2>
        <p>Todos os números desta página vêm de <a href="data/jean-final-results.json"><code>site/data/jean-final-results.json</code></a>. A busca exploratória da Tarefa 4, quando publicada junto ao site, fica em <a href="data/jean-task4-search-results.json"><code>site/data/jean-task4-search-results.json</code></a>. O código que gera esta página e os dados completos estão no repositório <a href="https://github.com/Jean-Reinhold/sim-outorder">github.com/Jean-Reinhold/sim-outorder</a>.</p>
        <div class="conclusion">
          <p><strong>Conclusão geral.</strong> Os dois benchmarks respondem bem a execução fora de ordem, janelas maiores e previsão dinâmica de desvios, mas cada um pede uma ênfase diferente. O LI_3 se beneficia bastante de largura alta combinada com execução fora de ordem, e ainda perde desempenho relevante por erros de desvio. O VORTEX_2, mais pesado em memória, recompensa antes de tudo janela, LSQ e portas de memória, e só depois o resto.</p>
          <p><strong>Limitação.</strong> O índice de custo é uma aproximação para discussão acadêmica. Um projeto real exigiria modelagem de área, potência, frequência e do impacto físico de cada estrutura que ampliei.</p>
        </div>
      </section>
    </main>
    <footer>Página escrita e mantida por Jean Reinhold para os benchmarks LI_3 e VORTEX_2. As tabelas e os gráficos são gerados a partir dos resultados medidos; o texto de análise é autoral. Código e dados no GitHub: <a href="https://github.com/Jean-Reinhold/sim-outorder">github.com/Jean-Reinhold/sim-outorder</a>.</footer>
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
