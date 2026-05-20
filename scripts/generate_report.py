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
.conclusions-body h3, .conclusions-body h4 { color: var(--ufpel-blue-dark); }
.conclusions-body ul { padding-left: 22px; }
.conclusions-body li { margin: 6px 0; }
footer { padding: 28px clamp(20px, 5vw, 72px); color: var(--muted); border-top: 1px solid var(--line); background: #fff; }
@media (max-width: 1100px) { .cards, .task-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 680px) {
  .hero { padding-top: 34px; }
  .cards, .task-grid { grid-template-columns: 1fr; }
  main { width: min(100% - 20px, 1480px); }
  th, td { padding: 10px; }
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
    <a href="#analysis">Analise</a>
    <a href="#conclusions">Conclusoes</a>
    <a href="#methodology">Reprodutibilidade</a>
  </nav>
  <main>
    <section id="overview" class="cards">{summary_cards(results)}</section>
    {task_intro_sections(report)}
    {benchmark_section(results)}
    {experiments_section(results)}
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
