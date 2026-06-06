#!/usr/bin/env python3
"""Generate Jean Reinhold's hand-crafted LI_3/VORTEX_2 page from measured data."""

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


def load_store_ratio(bench: dict[str, Any]) -> float | None:
    total = bench.get("total_instructions")
    load_store = bench.get("load_store_instructions")
    if not isinstance(total, (int, float)) or not isinstance(load_store, (int, float)) or total <= 0:
        return None
    return load_store / total * 100


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


def first_metric(run: dict[str, Any], suffix: str, prefix: str | None = None) -> int | float | None:
    for key in sorted(run.get("stats", {})):
        if prefix and not key.startswith(prefix):
            continue
        if key.endswith(suffix):
            value = run["stats"][key]
            if isinstance(value, (int, float)) and math.isfinite(value):
                return value
    return None


def value_range(values: list[float], pad: float = 0.1) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        spread = abs(high) * 0.1 or 1.0
        return low - spread, high + spread
    spread = high - low
    return low - spread * pad, high + spread * pad


def same_options(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = set(COST_WEIGHTS) | {"issue:inorder", "bpred"}
    return all(left.get(key) == right.get(key) for key in keys)


def benchmark_cards(data: dict[str, Any]) -> str:
    cards = []
    for benchmark in BENCHMARKS:
        bench = data.get("benchmarks", {}).get(benchmark, {})
        ratio = load_store_ratio(bench)
        cards.append(
            f"""
            <article class="bench-card">
              <span>{h(bench.get('family', '-'))}</span>
              <h3>{h(benchmark)}</h3>
              <p>{h(bench.get('description', ''))}</p>
              <dl>
                <div><dt>entrada</dt><dd>{h(bench.get('input'))}</dd></div>
                <div><dt>instruções</dt><dd>{fmt(bench.get('total_instructions'))}</dd></div>
                <div><dt>load/store</dt><dd>{fmt(bench.get('load_store_instructions'))} · {pct(ratio)}</dd></div>
              </dl>
            </article>
            """
        )
    return "".join(cards)


def task1_table(data: dict[str, Any], benchmark: str) -> str:
    rows = []
    task_runs = runs_for(data, benchmark, "Tarefa 1")
    for width in [1, 2, 4, 8]:
        in_run = next((run for run in task_runs if run.get("options", {}).get("issue:width") == width and run.get("options", {}).get("issue:inorder") is True), None)
        ooo_run = next((run for run in task_runs if run.get("options", {}).get("issue:width") == width and run.get("options", {}).get("issue:inorder") is False), None)
        in_cpi = cpi(in_run)
        ooo_cpi = cpi(ooo_run)
        gain = ((in_cpi - ooo_cpi) / in_cpi * 100) if in_cpi and ooo_cpi else None
        rows.append(
            f"<tr><td>{width}</td><td>{fmt(in_cpi)}</td><td>{fmt(ooo_cpi)}</td>"
            f"<td>{pct(gain)}</td><td>{fmt(cycles(in_run))}</td><td>{fmt(cycles(ooo_run))}</td></tr>"
        )
    return f"""
    <table><thead><tr><th>Largura</th><th>CPI em ordem</th><th>CPI fora de ordem</th><th>redução</th><th>ciclos em ordem</th><th>ciclos fora de ordem</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def task2_table(data: dict[str, Any], benchmark: str) -> str:
    rows = []
    task_runs = sorted(runs_for(data, benchmark, "Tarefa 2"), key=lambda run: run.get("options", {}).get("ruu:size", 0))
    baseline = cpi(task_runs[0]) if task_runs else None
    for run in task_runs:
        value = cpi(run)
        gain = ((baseline - value) / baseline * 100) if baseline and value else None
        rows.append(
            f"<tr><td>{fmt(run.get('options', {}).get('ruu:size'))}</td>"
            f"<td>{fmt(run.get('options', {}).get('lsq:size'))}</td>"
            f"<td>{fmt(value)}</td><td>{fmt(cycles(run))}</td><td>{pct(gain)}</td></tr>"
        )
    return f"""
    <table><thead><tr><th>RUU</th><th>LSQ</th><th>CPI</th><th>ciclos</th><th>ganho vs RUU 4</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def task3_table(data: dict[str, Any], benchmark: str) -> str:
    task_runs = runs_for(data, benchmark, "Tarefa 3")
    perfect = next((run for run in task_runs if predictor(run) == "perfect"), None)
    perfect_cpi = cpi(perfect)
    rows = []
    for name in ["perfect", "bimod", "taken", "nottaken"]:
        run = next((item for item in task_runs if predictor(item) == name), None)
        value = cpi(run)
        overhead = ((value / perfect_cpi - 1) * 100) if value and perfect_cpi else None
        rows.append(
            f"<tr><td>{h(name)}</td><td>{fmt(value)}</td><td>{fmt(cycles(run))}</td>"
            f"<td>{fmt(first_metric(run, 'bpred_dir_rate', 'bpred_') if run else None)}</td>"
            f"<td>{fmt(first_metric(run, 'misses', 'bpred_') if run else None)}</td><td>{pct(overhead)}</td></tr>"
        )
    return f"""
    <table><thead><tr><th>previsor</th><th>CPI</th><th>ciclos</th><th>taxa direção</th><th>misses</th><th>vs perfect</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def task4_table(data: dict[str, Any], benchmark: str) -> str:
    rows = []
    selected = TASK4_FINAL[benchmark]
    for experiment in selected:
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
    <table><thead><tr><th>projeto</th><th>CPI</th><th>ciclos</th><th>custo</th><th>width</th><th>RUU</th><th>LSQ</th><th>mem</th><th>IALU</th><th>IMult</th><th>FP</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """


def search_runs(search: dict[str, Any] | None, benchmark: str) -> list[dict[str, Any]]:
    if not search:
        return []
    return [run for run in search.get("runs", []) if run.get("benchmark") == benchmark and run.get("status") == "completed" and cpi(run) is not None]


def search_cloud_svg(search: dict[str, Any] | None, final: dict[str, Any], benchmark: str) -> str:
    runs = search_runs(search, benchmark)
    if len(runs) < 2:
        return "<p class=\"muted\">Busca ampla indisponível para este benchmark.</p>"
    final_runs = [find_run(final, benchmark, experiment) for experiment in TASK4_FINAL[benchmark]]
    final_options = [(TASK4_LABELS.get(run["experiment"], run["experiment"]), run.get("options", {})) for run in final_runs if run]
    costs = [cost_index(run.get("options", {})) for run in runs]
    cpis = [cpi(run) for run in runs if cpi(run) is not None]
    x_min, x_max = value_range(costs, 0.1)
    y_min, y_max = value_range([float(value) for value in cpis], 0.1)
    width, height = 760, 420
    left, top, plot_w, plot_h = 70, 42, 620, 280

    def x_pos(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def y_pos(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    grid = []
    for idx in range(5):
        x = left + plot_w * idx / 4
        xv = x_min + (x_max - x_min) * idx / 4
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="grid"/>')
        grid.append(f'<text x="{x:.1f}" y="{top + plot_h + 26}" class="axis" text-anchor="middle">{fmt(xv,0)}</text>')
    for idx in range(4):
        y = top + plot_h * idx / 3
        yv = y_max - (y_max - y_min) * idx / 3
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        grid.append(f'<text x="{left - 10}" y="{y + 4:.1f}" class="axis" text-anchor="end">{fmt(yv,2)}</text>')
    points = []
    labels = []
    for run in runs:
        value = cpi(run)
        if value is None:
            continue
        options = run.get("options", {})
        match = next((label for label, final_opts in final_options if same_options(options, final_opts)), None)
        x, y = x_pos(cost_index(options)), y_pos(value)
        if match:
            points.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" class="point chosen"><title>{h(match)} · CPI {fmt(value)}</title></circle>')
            labels.append(f'<text x="{x + 13:.1f}" y="{y - 9:.1f}" class="label">{h(match)}</text>')
        else:
            points.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.8" class="point"><title>{h(run.get("experiment"))} · CPI {fmt(value)}</title></circle>')
    return f"""
    <svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Busca CPI por custo para {h(benchmark)}">
      <text x="18" y="24" class="axis">CPI menor fica mais alto; custo cresce para a direita</text>
      {''.join(grid)}
      {''.join(points)}
      {''.join(labels)}
      <text x="{left + plot_w / 2}" y="{height - 16}" class="axis" text-anchor="middle">índice de custo arquitetural</text>
      <text x="18" y="{top + 12}" class="axis">CPI</text>
    </svg>
    """


def pyramid_svg(benchmark: str) -> str:
    labels = [TASK4_LABELS[experiment] for experiment in TASK4_FINAL[benchmark]]
    if benchmark == "LI_3":
        text = "No LI_3, a configuração robusta compra desempenho; a equilibrada é o ponto defensável quando custo entra na conta."
    else:
        text = "No VORTEX_2, a folga de memória pesa mais: LSQ e janela maiores aparecem como parte do projeto, não como enfeite."
    return f"""
    <div class="pyramid-box">
      <svg viewBox="0 0 560 360" role="img" aria-label="Pirâmide de decisão para {h(benchmark)}">
        <polygon points="280,34 64,300 496,300" class="tri"/>
        <line x1="280" y1="34" x2="64" y2="300" class="edge"/><line x1="280" y1="34" x2="496" y2="300" class="edge"/><line x1="64" y1="300" x2="496" y2="300" class="edge"/>
        <text x="280" y="22" text-anchor="middle" class="vertex">desempenho</text>
        <text x="64" y="332" text-anchor="middle" class="vertex">baixo custo</text>
        <text x="496" y="332" text-anchor="middle" class="vertex">folga arquitetural</text>
        <circle cx="162" cy="246" r="15" class="dot"/><text x="162" y="276" text-anchor="middle" class="label">{h(labels[0])}</text>
        <circle cx="282" cy="190" r="15" class="dot alt"/><text x="282" y="220" text-anchor="middle" class="label">{h(labels[1])}</text>
        <circle cx="402" cy="246" r="15" class="dot hot"/><text x="402" y="276" text-anchor="middle" class="label">{h(labels[2])}</text>
      </svg>
      <p>{h(text)}</p>
    </div>
    """


def task4_search_note(search: dict[str, Any] | None) -> str:
    if not search:
        return "A busca ampla ainda não está disponível neste build."
    completed = len([run for run in search.get("runs", []) if run.get("status") == "completed"])
    total = len(search.get("runs", []))
    return f"A escolha saiu de uma varredura local com {completed}/{total} simulações completas. A tabela final mostra só três projetos por benchmark, como a especificação pede."


def css() -> str:
    return """
:root{--bg:#0b0f14;--ink:#eef4f8;--muted:#9fb0bd;--panel:#111a24;--line:#263545;--blue:#73c7ff;--gold:#f3c35b;--green:#77d68f;--red:#ff6f91}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 18% 0%,rgba(115,199,255,.20),transparent 28%),linear-gradient(135deg,#081018,#14212e 55%,#0b0f14);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--blue)}header{padding:56px min(7vw,84px) 34px;border-bottom:1px solid var(--line)}header small,.eyebrow{color:var(--gold);letter-spacing:.14em;text-transform:uppercase;font-weight:800;font-size:.76rem}h1{font-size:clamp(2.4rem,6vw,5.8rem);line-height:.9;margin:.25em 0 .18em;max-width:980px}h2{font-size:clamp(1.7rem,3vw,3rem);line-height:1;margin:0 0 14px}h3{font-size:1.25rem;margin:0 0 10px}.lead{max-width:900px;color:#d7e5ef;font-size:1.14rem}.wrap{width:min(100% - 30px,1440px);margin:0 auto}.nav{display:flex;gap:10px;flex-wrap:wrap;padding:18px 0}.nav a{border:1px solid var(--line);border-radius:999px;padding:8px 13px;text-decoration:none;background:rgba(255,255,255,.05)}section{margin:24px 0;padding:26px;border:1px solid var(--line);border-radius:28px;background:rgba(17,26,36,.86);box-shadow:0 30px 80px rgba(0,0,0,.25)}.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.bench-card,.note,.mini{border:1px solid var(--line);border-radius:22px;background:rgba(255,255,255,.045);padding:18px}.bench-card span,.note strong{color:var(--gold);text-transform:uppercase;letter-spacing:.11em;font-size:.75rem}.bench-card h3{font-size:2rem;margin:4px 0}.bench-card dl{display:grid;gap:8px;margin:14px 0 0}.bench-card div{display:flex;justify-content:space-between;gap:16px;border-top:1px solid var(--line);padding-top:8px}.bench-card dt{color:var(--muted)}.bench-card dd{margin:0;font-weight:800}.task-head{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:16px}.task-head p{max-width:720px;color:var(--muted);margin:0}.table-wrap{overflow:auto;border-radius:18px;border:1px solid var(--line)}table{width:100%;border-collapse:collapse;background:rgba(0,0,0,.18)}th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{color:#bfd0dc;text-transform:uppercase;letter-spacing:.08em;font-size:.72rem}code{color:#bde8ff}.callout{border-left:4px solid var(--gold);padding:12px 14px;background:rgba(243,195,91,.08);border-radius:14px;color:#f6e7bd}.muted{color:var(--muted)}.chart{width:100%;height:auto;background:rgba(0,0,0,.16);border:1px solid var(--line);border-radius:20px}.grid{stroke:rgba(255,255,255,.12)}.axis{fill:var(--muted);font-size:13px}.point{fill:rgba(115,199,255,.45)}.point.chosen{fill:var(--gold);stroke:white;stroke-width:2}.label{fill:white;font-size:13px;font-weight:800}.pyramid-box{border:1px solid var(--line);border-radius:22px;background:rgba(255,255,255,.045);padding:18px}.pyramid-box svg{width:100%;height:auto}.tri{fill:rgba(115,199,255,.08)}.edge{stroke:rgba(255,255,255,.35);stroke-width:2}.vertex{fill:#eaf4ff;font-weight:900;font-size:16px}.dot{fill:var(--green);stroke:white;stroke-width:2}.dot.alt{fill:var(--gold)}.dot.hot{fill:var(--red)}footer{padding:34px min(7vw,84px);color:var(--muted)}@media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}.task-head{display:block}section{padding:18px}}
    """


def build_html(final: dict[str, Any], search: dict[str, Any] | None) -> str:
    task1_li = find_run(final, "LI_3", "task1_width8_ooo")
    task1_vo = find_run(final, "VORTEX_2", "task1_width8_ooo")
    final_li = find_run(final, "LI_3", "task4_li3_robusto")
    final_vo = find_run(final, "VORTEX_2", "task4_vortex2_robusto")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jean Reinhold · LI_3 e VORTEX_2</title>
  <link rel="stylesheet" href="assets/style.css">
  <style>{css()}</style>
</head>
<body>
  <header>
    <small>UFPel · Arquitetura Avançada · sim-outorder</small>
    <h1>Jean Reinhold: LI_3 e VORTEX_2</h1>
    <p class="lead">Esta página isola os dois benchmarks atribuídos a mim e separa duas coisas: primeiro, a entrega exata pedida no PDF; depois, a busca mais ampla usada para escolher as três configurações da Tarefa 4.</p>
  </header>
  <main class="wrap">
    <nav class="nav" aria-label="Navegação"><a href="index.html">relatório geral</a><a href="#perfil">perfil</a><a href="#t1">tarefa 1</a><a href="#t2">tarefa 2</a><a href="#t3">tarefa 3</a><a href="#t4">tarefa 4</a><a href="#dados">dados</a></nav>
    <section id="perfil">
      <p class="eyebrow">benchmarks escolhidos</p>
      <h2>Dois programas, dois gargalos prováveis</h2>
      <div class="grid2">{benchmark_cards(final)}</div>
    </section>
    <section>
      <p class="eyebrow">leituras rápidas</p>
      <div class="grid3">
        <article class="mini"><h3>LI_3 em largura 8 OOO</h3><p>CPI {fmt(cpi(task1_li))}; ciclos {fmt(cycles(task1_li))}.</p></article>
        <article class="mini"><h3>VORTEX_2 em largura 8 OOO</h3><p>CPI {fmt(cpi(task1_vo))}; ciclos {fmt(cycles(task1_vo))}.</p></article>
        <article class="mini"><h3>Busca da Tarefa 4</h3><p>{h(task4_search_note(search))}</p></article>
      </div>
    </section>
    <section id="t1">
      <div class="task-head"><div><p class="eyebrow">Tarefa 1</p><h2>Em ordem contra fora de ordem</h2></div><p>A largura ajuda nos dois benchmarks, mas o ganho fica mais convincente quando o processador pode procurar trabalho fora de ordem.</p></div>
      <div class="grid2"><div><h3>LI_3</h3><div class="table-wrap">{task1_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task1_table(final, 'VORTEX_2')}</div></div></div>
      <p class="callout">No LI_3, trocar in-order por out-of-order em largura 8 reduziu o CPI em 26,37%. No VORTEX_2, a mesma troca reduziu 20,03%. A largura sem reordenação ainda melhora, mas deixa desempenho preso por dependências, memória e desvios.</p>
    </section>
    <section id="t2">
      <div class="task-head"><div><p class="eyebrow">Tarefa 2</p><h2>Janela maior: ganho real, mas não gratuito</h2></div><p>A janela foi medida com execução fora de ordem e largura fixa. RUU e LSQ crescem juntas, então o ganho não é só de uma estrutura isolada.</p></div>
      <div class="grid2"><div><h3>LI_3</h3><div class="table-wrap">{task2_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task2_table(final, 'VORTEX_2')}</div></div></div>
      <p class="callout">A maior janela testada na Tarefa 2 foi a melhor nos dois casos: ganho de 26,34% no LI_3 e 28,57% no VORTEX_2 contra RUU 4. O resultado justifica testar janela/LSQ com mais cuidado na Tarefa 4.</p>
    </section>
    <section id="t3">
      <div class="task-head"><div><p class="eyebrow">Tarefa 3</p><h2>Previsão de desvios</h2></div><p>O bimodal foi comparado com preditores estáticos e com o perfect. A leitura principal é a distância entre errar muitos desvios e aprender o comportamento local de cada branch.</p></div>
      <div class="grid2"><div><h3>LI_3</h3><div class="table-wrap">{task3_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task3_table(final, 'VORTEX_2')}</div></div></div>
      <p class="callout">Um previsor bimodal usa uma tabela indexada pelo endereço do desvio. Cada entrada guarda um contador saturante de 2 bits, que demora a trocar de opinião e por isso filtra oscilações ocasionais. No LI_3, ele ficou muito perto do perfect e bem à frente dos preditores estáticos. No VORTEX_2, o bimod medido ficou ligeiramente melhor que o perfect nesta configuração; tratei isso como efeito de interação da simulação, não como prova de que o perfect seja inferior.</p>
    </section>
    <section id="t4">
      <div class="task-head"><div><p class="eyebrow">Tarefa 4</p><h2>Escolher dois, abrir mão de um</h2></div><p>A pirâmide usada aqui tem três vértices: desempenho, baixo custo e folga arquitetural. Cada projeto escolhe dois lados e aceita perder no terceiro.</p></div>
      <div class="grid2"><div>{pyramid_svg('LI_3')}</div><div>{pyramid_svg('VORTEX_2')}</div></div>
      <h3>Configurações finais</h3>
      <div class="grid2"><div><h3>LI_3</h3><div class="table-wrap">{task4_table(final, 'LI_3')}</div></div><div><h3>VORTEX_2</h3><div class="table-wrap">{task4_table(final, 'VORTEX_2')}</div></div></div>
      <p class="callout">No LI_3, o robusto vence em CPI, mas o equilibrado mostra o ponto de compromisso: largura 4, RUU 64, LSQ 32 e duas portas de memória já capturam boa parte do ganho sem dobrar todo o processador. No VORTEX_2, a versão robusta ganha pouco contra a robusta de LSQ 64 vista na busca, mas ela representa bem o extremo de folga para uma carga com 53,72% de instruções load/store.</p>
      <h3>Nuvem da busca ampla</h3>
      <div class="grid2"><div><h3>LI_3</h3>{search_cloud_svg(search, final, 'LI_3')}</div><div><h3>VORTEX_2</h3>{search_cloud_svg(search, final, 'VORTEX_2')}</div></div>
    </section>
    <section id="dados">
      <p class="eyebrow">reprodutibilidade</p>
      <h2>Dados usados</h2>
      <p>Os números desta página vêm dos arquivos versionáveis da execução local: <a href="data/jean-final-results.json"><code>site/data/jean-final-results.json</code></a> para a entrega oficial, e dos arquivos auxiliares da busca da Tarefa 4 quando presentes.</p>
      <p class="muted">Além de CPI, o custo de um processador deveria considerar área, energia, complexidade de wakeup/select da RUU, tamanho da LSQ, portas da L1, rede de bypass, pressão sobre frequência de clock e esforço de verificação. O CPI escolhe desempenho; o projeto precisa pagar a conta.</p>
    </section>
  </main>
  <footer>Gerado por <code>scripts/generate_jean_page.py</code> a partir dos resultados medidos. O HTML foi escrito para esta dupla de benchmarks, não como página genérica.</footer>
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
