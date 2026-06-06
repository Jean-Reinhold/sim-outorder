"""Generated Task 4 search space for Jean Reinhold's benchmark exploration."""

from __future__ import annotations

from typing import Any


TASK4_SEARCH_SET = "task4_search"


def base_options(
    *,
    fetch: int,
    decode: int,
    issue: int,
    commit: int,
    ruu: int,
    lsq: int,
    ialu: int,
    imult: int,
    fpalu: int,
    fpmult: int,
    memport: int,
) -> dict[str, Any]:
    return {
        "fetch:ifqsize": fetch,
        "decode:width": decode,
        "issue:width": issue,
        "issue:inorder": False,
        "ruu:size": ruu,
        "commit:width": commit,
        "lsq:size": lsq,
        "res:ialu": ialu,
        "res:imult": imult,
        "res:fpalu": fpalu,
        "res:fpmult": fpmult,
        "res:memport": memport,
        "bpred": "bimod",
    }


def make_experiment(exp_id: str, title: str, summary: str, options: dict[str, Any], profile: str) -> dict[str, Any]:
    return {
        "task": "Tarefa 4",
        "title": title,
        "summary": summary,
        "profile": profile,
        "options": options,
    }


def build_task4_search_experiments() -> dict[str, dict[str, Any]]:
    experiments: dict[str, dict[str, Any]] = {}

    def add(exp_id: str, title: str, summary: str, options: dict[str, Any], profile: str) -> None:
        if exp_id in experiments:
            return
        experiments[exp_id] = make_experiment(exp_id, title, summary, options, profile)

    width_windows = {
        1: [8, 16, 32],
        2: [8, 16, 32, 64],
        4: [16, 32, 64, 128],
        8: [32, 64, 128],
    }
    memports_by_width = {
        1: [1, 2],
        2: [1, 2, 4],
        4: [1, 2, 4],
        8: [2, 4],
    }

    # Coherent core lattice: width, RUU/LSQ, and memory ports scale together.
    for width, windows in width_windows.items():
        for ruu in windows:
            lsq = max(4, ruu // 2)
            for memport in memports_by_width[width]:
                imult = 1 if width <= 4 else 2
                options = base_options(
                    fetch=width,
                    decode=width,
                    issue=width,
                    commit=width,
                    ruu=ruu,
                    lsq=lsq,
                    ialu=width,
                    imult=imult,
                    fpalu=1,
                    fpmult=1,
                    memport=memport,
                )
                add(
                    f"task4_search_core_w{width}_r{ruu}_l{lsq}_m{memport}",
                    f"Busca core W{width} RUU{ruu} LSQ{lsq} MEM{memport}",
                    "Ponto coerente da grade principal, mantendo FP minimo para cargas inteiras.",
                    options,
                    "core",
                )

    # Memory-pressure variants: isolate LSQ and memory ports for pointer-heavy behavior.
    for width in [2, 4, 8]:
        for ruu in [32, 64, 128]:
            if width == 2 and ruu == 128:
                continue
            for lsq in sorted({ruu // 2, ruu}):
                for memport in [2, 4]:
                    options = base_options(
                        fetch=width,
                        decode=width,
                        issue=width,
                        commit=width,
                        ruu=ruu,
                        lsq=lsq,
                        ialu=width,
                        imult=1 if width <= 4 else 2,
                        fpalu=1,
                        fpmult=1,
                        memport=memport,
                    )
                    add(
                        f"task4_search_mem_w{width}_r{ruu}_l{lsq}_m{memport}",
                        f"Busca memoria W{width} RUU{ruu} LSQ{lsq} MEM{memport}",
                        "Variante focada em folga de memoria para comparar LSQ e portas da L1.",
                        options,
                        "memory",
                    )

    # Front-end and commit bottleneck probes.
    front_end_variants = [
        (8, 8, 4, 4, 64, 32, 4, 1, 1, 1, 2, "front_w8_issue4"),
        (8, 8, 8, 4, 64, 32, 8, 2, 1, 1, 4, "issue8_commit4"),
        (4, 8, 8, 8, 64, 32, 8, 2, 1, 1, 4, "fetch4_decode8_issue8"),
        (8, 4, 4, 4, 64, 32, 4, 1, 1, 1, 4, "fetch8_decode4"),
        (8, 8, 4, 8, 64, 32, 4, 1, 1, 1, 4, "commit8_issue4"),
    ]
    for fetch, decode, issue, commit, ruu, lsq, ialu, imult, fpalu, fpmult, memport, slug in front_end_variants:
        options = base_options(
            fetch=fetch,
            decode=decode,
            issue=issue,
            commit=commit,
            ruu=ruu,
            lsq=lsq,
            ialu=ialu,
            imult=imult,
            fpalu=fpalu,
            fpmult=fpmult,
            memport=memport,
        )
        add(
            f"task4_search_pipe_{slug}",
            f"Busca gargalo de pipeline {slug.replace('_', ' ')}",
            "Variante assimetrica para separar gargalos de busca, decodificacao, despacho e commit.",
            options,
            "pipeline",
        )

    # Functional-unit sensitivity around balanced and robust baselines.
    baselines = [
        (4, 32, 16, 2, "balanced"),
        (4, 64, 32, 4, "memory_balanced"),
        (8, 64, 32, 4, "robust"),
    ]
    for width, ruu, lsq, memport, base_slug in baselines:
        for ialu in sorted({max(1, width // 2), width, min(8, width * 2)}):
            options = base_options(
                fetch=width,
                decode=width,
                issue=width,
                commit=width,
                ruu=ruu,
                lsq=lsq,
                ialu=ialu,
                imult=1 if width <= 4 else 2,
                fpalu=1,
                fpmult=1,
                memport=memport,
            )
            add(
                f"task4_search_fu_{base_slug}_ialu{ialu}",
                f"Busca unidades inteiras {base_slug} IALU{ialu}",
                "Varia apenas ALUs inteiras ao redor de um ponto candidato.",
                options,
                "functional-unit",
            )
        for imult in [1, 2, 4]:
            options = base_options(
                fetch=width,
                decode=width,
                issue=width,
                commit=width,
                ruu=ruu,
                lsq=lsq,
                ialu=width,
                imult=imult,
                fpalu=1,
                fpmult=1,
                memport=memport,
            )
            add(
                f"task4_search_fu_{base_slug}_imult{imult}",
                f"Busca multiplicadores inteiros {base_slug} IMULT{imult}",
                "Varia multiplicadores inteiros para medir retorno de uma unidade mais cara.",
                options,
                "functional-unit",
            )
        for fpalu, fpmult, fp_slug in [(1, 1, "fpmin"), (4, 1, "fpdefault"), (4, 2, "fpwide")]:
            options = base_options(
                fetch=width,
                decode=width,
                issue=width,
                commit=width,
                ruu=ruu,
                lsq=lsq,
                ialu=width,
                imult=1 if width <= 4 else 2,
                fpalu=fpalu,
                fpmult=fpmult,
                memport=memport,
            )
            add(
                f"task4_search_fu_{base_slug}_{fp_slug}",
                f"Busca ponto flutuante {base_slug} {fp_slug}",
                "Varia recursos de ponto flutuante para confirmar se sao custo dispensavel nestas cargas.",
                options,
                "functional-unit",
            )

    return experiments


def add_task4_search_space(experiment_doc: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "schema_version": experiment_doc.get("schema_version", 1),
        "sets": {name: list(members) for name, members in experiment_doc.get("sets", {}).items()},
        "experiments": {name: dict(experiment) for name, experiment in experiment_doc.get("experiments", {}).items()},
    }
    generated = build_task4_search_experiments()
    merged["experiments"].update(generated)
    merged["sets"][TASK4_SEARCH_SET] = list(generated)
    return merged
