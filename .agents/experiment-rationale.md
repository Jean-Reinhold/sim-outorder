# Experiment Rationale

Use this document to understand what each experiment is trying to isolate before interpreting results.

## Tarefa 1: In-Order vs Out-of-Order Width Sweep

Question: how much performance comes from issuing more instructions per cycle, and how much comes from out-of-order scheduling?

The controlled variable is pipeline width: `1`, `2`, `4`, and `8`. For each width, the runner creates an in-order and an out-of-order configuration. Fetch queue size, decode width, issue width, commit width, and execution resources scale together so each width represents a coherent processor class.

Expected reasoning pattern:

- If CPI falls as width increases, the benchmark exposes instruction-level parallelism or benefits from higher front-end/commit bandwidth.
- If CPI stops improving at wider configurations, the workload is likely limited by dependencies, branch prediction, memory/cache behavior, or the benchmark's available ILP.
- If out-of-order improves CPI strongly over in-order at the same width, the workload likely has stalls that can be hidden by scheduling independent instructions.
- If out-of-order gives little benefit, the workload may be dependency-bound, branch-bound, too narrow, or already limited by long-latency memory behavior that the available window cannot hide.

## Tarefa 2: Window Size Sweep

Question: does a larger instruction window improve out-of-order scheduling enough to reduce CPI?

The controlled variable is `ruu:size`, with the matching `lsq:size` scaled as powers of two. Width and functional units stay fixed, so the agent should attribute differences mainly to scheduler/window capacity.

Expected reasoning pattern:

- If larger windows reduce CPI, the benchmark has independent work available beyond the smaller RUU/LSQ capacity.
- If larger windows do not reduce CPI, the bottleneck is probably not the scheduler window; check branch misses, cache miss rates, issue width, and functional-unit pressure.
- If CPI improves and then saturates, the saturation point is the practical window size for that workload under these resource assumptions.

## Tarefa 3: Branch Predictor Analysis

Question: how much does branch prediction accuracy affect performance?

The experiments compare `nottaken`, `taken`, and `bimod`. The `perfect` predictor is included as a baseline, even though the PDF asks to report only three concrete predictor options, because it makes the cost of imperfect prediction easier to quantify.

Expected reasoning pattern:

- Compare CPI against `perfect` for the same benchmark.
- Use `bpred_*.bpred_dir_rate`, `bpred_*.misses`, and branch count stats to explain performance differences.
- A bimodal predictor uses a table indexed by branch address. Each entry is a saturating 2-bit counter that moves toward taken or not-taken based on recent outcomes. It filters noise better than a 1-bit predictor because one unusual outcome does not immediately flip a strong prediction.
- If `taken` beats `nottaken`, the workload's branches are more often taken; if `nottaken` wins, the opposite is likely true.

## Tarefa 4: Custom Processor Candidates

Question: what is the best performance/cost tradeoff for each benchmark?

The repository seeds three candidate configurations:

- `task4_balanced`: moderate width and resources, intended as a cost-conscious baseline.
- `task4_memory_window`: larger RUU/LSQ and memory ports, intended for load/store-heavy workloads.
- `task4_compute_wide`: wider pipeline and more functional units, intended to test available ILP.

Expected reasoning pattern:

- Do not choose solely by CPI if the CPI gain is tiny and resource cost is much larger.
- Consider RUU size, LSQ size, number of ALUs, FP units, multipliers, memory ports, branch predictor behavior, and cache miss rates.
- Use the benchmark's load/store fraction from `experiments/benchmarks.json` to explain why memory-oriented candidates may or may not help.
- Report the best CPI and whether the extra resources are justified.
