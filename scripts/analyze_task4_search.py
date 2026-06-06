#!/usr/bin/env python3
"""Summarize Task 4 search runs and suggest final candidates."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

# This is not a physical area model. It is a sorting aid for the Task 4 tradeoff:
# CPI versus approximate architectural cost and slack.
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


def results_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_dir():
        return path / "results.json"
    return path


def metric(run: dict[str, Any], name: str) -> int | float | None:
    value = run.get("stats", {}).get(name)
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def option(run: dict[str, Any], name: str) -> int | float | str | bool | None:
    return run.get("options", {}).get(name)


def cost_index(run: dict[str, Any]) -> float:
    options = run.get("options", {})
    total = 0.0
    for name, weight in COST_WEIGHTS.items():
        value = options.get(name)
        if isinstance(value, (int, float)):
            total += float(value) * weight
    return total


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}%"


def value_range(values: list[float], pad: float = 0.08) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        spread = abs(high) * 0.1 or 1.0
        return low - spread, high + spread
    spread = high - low
    return low - spread * pad, high + spread * pad


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct)
    return ordered[index]


def completed_explore_runs(data: dict[str, Any], benchmark: str, prefix: str) -> list[dict[str, Any]]:
    runs = []
    for run in data.get("runs", []):
        if run.get("benchmark") != benchmark:
            continue
        if run.get("status") != "completed":
            continue
        if run.get("task") != "Tarefa 4":
            continue
        if not str(run.get("experiment", "")).startswith(prefix):
            continue
        if metric(run, "sim_CPI") is None:
            continue
        run = dict(run)
        run["_cost_index"] = cost_index(run)
        runs.append(run)
    return runs


def pareto_frontier(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frontier = []
    for run in runs:
        run_cpi = metric(run, "sim_CPI")
        run_cost = run["_cost_index"]
        dominated = False
        for other in runs:
            if other is run:
                continue
            other_cpi = metric(other, "sim_CPI")
            other_cost = other["_cost_index"]
            if other_cpi is None or run_cpi is None:
                continue
            if other_cpi <= run_cpi and other_cost <= run_cost and (other_cpi < run_cpi or other_cost < run_cost):
                dominated = True
                break
        if not dominated:
            frontier.append(run)
    return sorted(frontier, key=lambda item: (item["_cost_index"], metric(item, "sim_CPI") or math.inf))


def normalized(value: float, values: list[float]) -> float:
    low = min(values)
    high = max(values)
    if high == low:
        return 0.0
    return (value - low) / (high - low)


def suggested_candidates(runs: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    costs = [run["_cost_index"] for run in runs]
    cpis = [metric(run, "sim_CPI") for run in runs if metric(run, "sim_CPI") is not None]
    if not costs or not cpis:
        return []

    low_cost_limit = percentile(costs, 0.35)
    high_cost_limit = percentile(costs, 0.70)
    low_cost_runs = [run for run in runs if run["_cost_index"] <= low_cost_limit]
    high_cost_runs = [run for run in runs if run["_cost_index"] >= high_cost_limit]
    frontier = pareto_frontier(runs) or runs

    economical = min(low_cost_runs or runs, key=lambda run: (metric(run, "sim_CPI") or math.inf, run["_cost_index"]))
    balanced = min(
        frontier,
        key=lambda run: normalized(metric(run, "sim_CPI") or math.inf, cpis) + normalized(run["_cost_index"], costs),
    )
    robust = min(high_cost_runs or runs, key=lambda run: (metric(run, "sim_CPI") or math.inf, run["_cost_index"]))

    selected: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for label, run in [("economico", economical), ("enxuto", balanced), ("robusto", robust)]:
        experiment = str(run.get("experiment"))
        if experiment in seen:
            continue
        selected.append((label, run))
        seen.add(experiment)
    return selected


def load_store_ratio(data: dict[str, Any], benchmark: str) -> float | None:
    bench = data.get("benchmarks", {}).get(benchmark, {})
    total = bench.get("total_instructions")
    load_store = bench.get("load_store_instructions")
    if not isinstance(total, (int, float)) or not isinstance(load_store, (int, float)) or total <= 0:
        return None
    return load_store / total * 100


def spark_summary(runs: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None]:
    values = [metric(run, "sim_CPI") for run in runs if metric(run, "sim_CPI") is not None]
    if not values:
        return None, None, None
    return min(values), sum(values) / len(values), max(values)


def table_row(run: dict[str, Any], label: str | None = None) -> str:
    experiment = str(run.get("experiment"))
    name = f"{label}: `{experiment}`" if label else f"`{experiment}`"
    fp = f"{option(run, 'res:fpalu')}/{option(run, 'res:fpmult')}"
    return "| " + " | ".join(
        [
            name,
            fmt(metric(run, "sim_CPI")),
            fmt(metric(run, "sim_cycle")),
            fmt(run["_cost_index"], 1),
            fmt(option(run, "issue:width")),
            fmt(option(run, "ruu:size")),
            fmt(option(run, "lsq:size")),
            fmt(option(run, "res:memport")),
            fmt(option(run, "res:ialu")),
            fmt(option(run, "res:imult")),
            fp,
        ]
    ) + " |"


def print_table(title: str, runs: list[dict[str, Any]], labels: dict[str, str] | None = None) -> None:
    print(f"### {title}")
    print("| Experimento | CPI | Ciclos | Custo | Width | RUU | LSQ | Mem | IALU | IMult | FP/FPMult |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for run in runs:
        experiment = str(run.get("experiment"))
        print(table_row(run, labels.get(experiment) if labels else None))
    print()


def scatter_svg(benchmark: str, runs: list[dict[str, Any]], candidates: list[tuple[str, dict[str, Any]]]) -> str:
    if len(runs) < 2:
        return '<div class="empty">Sem pontos suficientes para desenhar a busca.</div>'
    costs = [run["_cost_index"] for run in runs]
    cpis = [metric(run, "sim_CPI") for run in runs if metric(run, "sim_CPI") is not None]
    x_min, x_max = value_range(costs, 0.12)
    y_min, y_max = value_range(cpis, 0.12)
    width = 960
    height = 520
    left = 82
    top = 42
    plot_w = 800
    plot_h = 345
    candidate_ids = {str(run.get("experiment")): label for label, run in candidates}
    frontier_ids = {str(run.get("experiment")) for run in pareto_frontier(runs)}

    def x_pos(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def y_pos(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    grid = []
    for idx in range(5):
        x = left + plot_w * idx / 4
        x_value = x_min + (x_max - x_min) * idx / 4
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="grid"/>')
        grid.append(f'<text x="{x:.1f}" y="{top + plot_h + 30}" class="axis" text-anchor="middle">{h(fmt(x_value, 0))}</text>')
    for idx in range(5):
        y = top + plot_h * idx / 4
        y_value = y_max - (y_max - y_min) * idx / 4
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        grid.append(f'<text x="{left - 12}" y="{y + 4:.1f}" class="axis" text-anchor="end">{h(fmt(y_value, 2))}</text>')

    points = []
    for run in sorted(runs, key=lambda item: (item["_cost_index"], metric(item, "sim_CPI") or math.inf)):
        value = metric(run, "sim_CPI")
        if value is None:
            continue
        experiment = str(run.get("experiment"))
        x = x_pos(run["_cost_index"])
        y = y_pos(value)
        profile = str(run.get("experiment", "")).split("_")[2] if "_" in str(run.get("experiment", "")) else "search"
        selected = experiment in candidate_ids
        frontier = experiment in frontier_ids
        css_class = "point selected" if selected else "point frontier" if frontier else "point"
        radius = 11 if selected else 7 if frontier else 4
        points.append(
            f'<circle class="{css_class}" cx="{x:.1f}" cy="{y:.1f}" r="{radius}" data-profile="{h(profile)}">'
            f'<title>{h(experiment)} | CPI {h(fmt(value))} | custo {h(fmt(run["_cost_index"], 1))}</title></circle>'
        )

    labels = []
    for label, run in candidates:
        value = metric(run, "sim_CPI")
        if value is None:
            continue
        x = x_pos(run["_cost_index"])
        y = y_pos(value)
        labels.append(
            f'<text x="{x + 14:.1f}" y="{y - 12:.1f}" class="label">{h(label)}</text>'
            f'<text x="{x + 14:.1f}" y="{y + 4:.1f}" class="muted">{h(fmt(value))} CPI</text>'
        )

    return f"""
    <svg class="search-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Busca CPI contra custo para {h(benchmark)}">
      <title>Busca CPI contra custo para {h(benchmark)}</title>
      <rect x="0" y="0" width="{width}" height="{height}" rx="26" class="canvas"/>
      <text x="24" y="28" class="chart-title">{h(benchmark)}: nuvem da busca</text>
      <text x="24" y="52" class="axis">cada ponto e uma configuracao; pontos grandes sao candidatos sugeridos</text>
      {''.join(grid)}
      {''.join(points)}
      {''.join(labels)}
      <text x="{left + plot_w / 2}" y="{height - 28}" class="axis" text-anchor="middle">indice de custo arquitetural heuristico</text>
      <text x="22" y="{top + 14}" class="axis">CPI</text>
    </svg>
    """


def pyramid_svg(benchmark: str, candidates: list[tuple[str, dict[str, Any]]]) -> str:
    width = 760
    height = 520
    top = (380, 58)
    left = (100, 410)
    right = (660, 410)
    positions = {
        "economico": (205, 346),
        "enxuto": (360, 238),
        "robusto": (525, 346),
    }
    labels = {label: run for label, run in candidates}
    points = []
    for label, (x, y) in positions.items():
        run = labels.get(label)
        if run:
            detail = f"{run.get('experiment')} | CPI {fmt(metric(run, 'sim_CPI'))} | custo {fmt(run['_cost_index'], 1)}"
            klass = "pyramid-point active"
        else:
            detail = "sem candidato"
            klass = "pyramid-point"
        points.append(
            f'<circle cx="{x}" cy="{y}" r="18" class="{klass}"><title>{h(detail)}</title></circle>'
            f'<text x="{x}" y="{y + 42}" class="pyramid-label" text-anchor="middle">{h(label)}</text>'
        )
    return f"""
    <svg class="pyramid-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Piramide de escolha para {h(benchmark)}">
      <title>Piramide de escolha para {h(benchmark)}</title>
      <rect x="0" y="0" width="{width}" height="{height}" rx="26" class="canvas"/>
      <polygon points="{top[0]},{top[1]} {left[0]},{left[1]} {right[0]},{right[1]}" class="pyramid-fill"/>
      <line x1="{top[0]}" y1="{top[1]}" x2="{left[0]}" y2="{left[1]}" class="pyramid-edge"/>
      <line x1="{top[0]}" y1="{top[1]}" x2="{right[0]}" y2="{right[1]}" class="pyramid-edge"/>
      <line x1="{left[0]}" y1="{left[1]}" x2="{right[0]}" y2="{right[1]}" class="pyramid-edge"/>
      <text x="{top[0]}" y="38" class="vertex" text-anchor="middle">desempenho</text>
      <text x="{left[0] - 12}" y="454" class="vertex" text-anchor="middle">baixo custo</text>
      <text x="{right[0] + 12}" y="454" class="vertex" text-anchor="middle">folga arquitetural</text>
      <text x="{width / 2}" y="492" class="axis" text-anchor="middle">a leitura e escolher dois objetivos e aceitar o custo do terceiro</text>
      {''.join(points)}
    </svg>
    """


def html_table(runs: list[dict[str, Any]], labels: dict[str, str] | None = None) -> str:
    rows = []
    for run in runs:
        experiment = str(run.get("experiment"))
        label = labels.get(experiment) if labels else None
        name = f"<strong>{h(label)}</strong><br><code>{h(experiment)}</code>" if label else f"<code>{h(experiment)}</code>"
        rows.append(
            "<tr>"
            f"<td>{name}</td>"
            f"<td>{h(fmt(metric(run, 'sim_CPI')))}</td>"
            f"<td>{h(fmt(metric(run, 'sim_cycle')))}</td>"
            f"<td>{h(fmt(run['_cost_index'], 1))}</td>"
            f"<td>{h(fmt(option(run, 'issue:width')))}</td>"
            f"<td>{h(fmt(option(run, 'ruu:size')))}</td>"
            f"<td>{h(fmt(option(run, 'lsq:size')))}</td>"
            f"<td>{h(fmt(option(run, 'res:memport')))}</td>"
            f"<td>{h(fmt(option(run, 'res:ialu')))}</td>"
            f"<td>{h(fmt(option(run, 'res:imult')))}</td>"
            f"<td>{h(option(run, 'res:fpalu'))}/{h(option(run, 'res:fpmult'))}</td>"
            "</tr>"
        )
    return """
    <table>
      <thead><tr><th>Experimento</th><th>CPI</th><th>Ciclos</th><th>Custo</th><th>Width</th><th>RUU</th><th>LSQ</th><th>Mem</th><th>IALU</th><th>IMult</th><th>FP/FPMult</th></tr></thead>
      <tbody>""" + "".join(rows) + "</tbody></table>"


def build_html(data: dict[str, Any], benchmark_runs: dict[str, list[dict[str, Any]]], prefix: str, top: int) -> str:
    sections = []
    for benchmark, runs in benchmark_runs.items():
        candidates = suggested_candidates(runs)
        labels = {str(run.get("experiment")): label for label, run in candidates}
        best, avg, worst = spark_summary(runs)
        ratio = load_store_ratio(data, benchmark)
        frontier = pareto_frontier(runs)
        by_cpi = sorted(runs, key=lambda run: (metric(run, "sim_CPI") or math.inf, run["_cost_index"]))[:top]
        sections.append(
            f"""
            <section class="bench-section">
              <div class="bench-head">
                <div><span>benchmark</span><h2>{h(benchmark)}</h2></div>
                <p>{len(runs)} configuracoes completas · load/store {h(pct(ratio))}</p>
              </div>
              <div class="kpis">
                <article><span>melhor CPI</span><strong>{h(fmt(best))}</strong></article>
                <article><span>CPI medio</span><strong>{h(fmt(avg))}</strong></article>
                <article><span>pior CPI</span><strong>{h(fmt(worst))}</strong></article>
                <article><span>Pareto</span><strong>{len(frontier)}</strong></article>
              </div>
              <div class="plot-grid">
                {scatter_svg(benchmark, runs, candidates)}
                {pyramid_svg(benchmark, candidates)}
              </div>
              <h3>Candidatos sugeridos</h3>
              {html_table([run for _, run in candidates], labels)}
              <h3>Fronteira de Pareto CPI/custo</h3>
              {html_table(frontier, labels)}
              <h3>Top {min(top, len(by_cpi))} por CPI</h3>
              {html_table(by_cpi, labels)}
            </section>
            """
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Busca Tarefa 4</title>
  <style>
    :root {{ color-scheme: dark; --bg:#07111f; --panel:#0d1b2f; --line:rgba(255,255,255,.13); --text:#edf6ff; --muted:#a9bbcf; --cyan:#1bd7ff; --green:#00d084; --gold:#f6c343; --pink:#ff5a8a; }}
    body {{ margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at 20% 0%, rgba(27,215,255,.18), transparent 32%), linear-gradient(135deg,#06101d,#102846 55%,#06101d); color:var(--text); }}
    header {{ padding:48px min(7vw,80px) 28px; }}
    header span, .bench-head span, article span {{ color:var(--gold); text-transform:uppercase; letter-spacing:.12em; font-size:.74rem; }}
    h1 {{ margin:.2rem 0; font-size:clamp(2rem,5vw,4.5rem); line-height:.95; }}
    h2 {{ margin:.1rem 0; font-size:clamp(1.6rem,3vw,2.8rem); }}
    h3 {{ margin:30px 0 12px; }}
    main {{ width:min(100% - 32px,1500px); margin:0 auto 48px; }}
    .bench-section {{ background:rgba(13,27,47,.82); border:1px solid var(--line); border-radius:30px; padding:28px; margin:24px 0; box-shadow:0 28px 80px rgba(0,0,0,.32); }}
    .bench-head {{ display:flex; justify-content:space-between; gap:18px; align-items:end; }}
    .bench-head p {{ color:var(--muted); margin:0; }}
    .kpis {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    article {{ background:rgba(255,255,255,.06); border:1px solid var(--line); border-radius:18px; padding:16px; }}
    article strong {{ display:block; margin-top:6px; font-size:1.45rem; }}
    .plot-grid {{ display:grid; grid-template-columns:minmax(0,1.25fr) minmax(340px,.75fr); gap:18px; align-items:stretch; }}
    svg {{ width:100%; height:auto; display:block; }}
    .canvas {{ fill:rgba(0,0,0,.20); }}
    .grid {{ stroke:rgba(255,255,255,.11); }}
    .axis,.muted {{ fill:var(--muted); font-size:13px; }}
    .chart-title {{ fill:var(--text); font-size:20px; font-weight:800; }}
    .label {{ fill:var(--text); font-size:14px; font-weight:800; }}
    .point {{ fill:rgba(27,215,255,.55); stroke:rgba(255,255,255,.45); }}
    .point.frontier {{ fill:var(--green); }}
    .point.selected {{ fill:var(--gold); stroke:#fff; stroke-width:2.5; filter:drop-shadow(0 0 10px rgba(246,195,67,.6)); }}
    .pyramid-fill {{ fill:rgba(27,215,255,.06); }}
    .pyramid-edge {{ stroke:rgba(255,255,255,.32); stroke-width:3; }}
    .pyramid-point {{ fill:rgba(255,255,255,.16); stroke:rgba(255,255,255,.4); stroke-width:2; }}
    .pyramid-point.active {{ fill:var(--pink); stroke:#fff; filter:drop-shadow(0 0 12px rgba(255,90,138,.55)); }}
    .pyramid-label,.vertex {{ fill:var(--text); font-size:16px; font-weight:800; }}
    table {{ width:100%; border-collapse:collapse; margin:0 0 12px; overflow:hidden; border-radius:14px; }}
    th,td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:right; }}
    th:first-child,td:first-child {{ text-align:left; }}
    th {{ color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; }}
    code {{ color:#bceeff; }}
    @media (max-width: 980px) {{ .plot-grid,.kpis {{ grid-template-columns:1fr; }} .bench-head {{ display:block; }} }}
  </style>
</head>
<body>
  <header>
    <span>sim-outorder · Tarefa 4</span>
    <h1>Busca data-driven das configuracoes customizadas</h1>
    <p>Resultados filtrados por prefixo <code>{h(prefix)}</code>. A entrega final continua limitada a tres configuracoes por benchmark; esta pagina mostra a busca usada para escolher.</p>
  </header>
  <main>{''.join(sections)}</main>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="results/jean-task4-search", help="Results directory or results.json path")
    parser.add_argument("--benchmarks", default="LI_3,VORTEX_2", help="Comma-separated benchmark IDs")
    parser.add_argument("--prefix", default="task4_search_", help="Experiment ID prefix to include")
    parser.add_argument("--top", type=int, default=10, help="Rows to show in CPI ranking")
    parser.add_argument("--html-output", help="Optional HTML output with SVG plots")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = results_path(args.results)
    if not path.exists():
        raise SystemExit(f"Missing results file: {path}")
    data = read_json(path)
    benchmarks = [item.strip() for item in args.benchmarks.split(",") if item.strip()]

    print("# Analise exploratoria da Tarefa 4")
    print()
    print("O indice de custo e apenas uma heuristica de ordenacao; a escolha final ainda deve ser justificada pelos dados medidos.")
    print()

    benchmark_runs: dict[str, list[dict[str, Any]]] = {}
    for benchmark in benchmarks:
        runs = completed_explore_runs(data, benchmark, args.prefix)
        benchmark_runs[benchmark] = runs
        print(f"## {benchmark}")
        print()
        if not runs:
            print("Nenhuma rodada exploratoria completa encontrada.")
            print()
            continue

        candidates = suggested_candidates(runs)
        labels = {str(run.get("experiment")): label for label, run in candidates}
        print_table("Candidatos sugeridos para a piramide", [run for _, run in candidates], labels)
        print_table("Fronteira de Pareto CPI/custo", pareto_frontier(runs), labels)
        by_cpi = sorted(runs, key=lambda run: (metric(run, "sim_CPI") or math.inf, run["_cost_index"]))[: args.top]
        print_table(f"Top {min(args.top, len(by_cpi))} por CPI", by_cpi, labels)

    if args.html_output:
        output = Path(args.html_output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(build_html(data, benchmark_runs, args.prefix, args.top), encoding="utf-8")
        print(f"Relatorio visual escrito em {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
