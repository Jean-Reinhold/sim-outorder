IMAGE ?= sim-outorder:local
RESULTS ?= results/latest
BENCHMARKS ?= quick
EXPERIMENTS ?= smoke
MAX_INST ?= 100000
TIMEOUT_SEC ?= 0
JOBS ?= 1
FULL_JOBS ?= $(shell sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 1)
TASK4_SEARCH_RESULTS ?= results/jean-task4-search
TASK4_SEARCH_MAX_INST ?= 0
TASK4_SEARCH_TIMEOUT_SEC ?= 0
PROGRESS_INTERVAL_SEC ?= 15
JEAN_PAGE ?= site/jean-li3-vortex2.html
JEAN_SEARCH_RESULTS ?= $(TASK4_SEARCH_RESULTS)

.PHONY: docker-build docker-shell run task4-search report jean-page validate-site validate-metadata test pages smoke clean-results

docker-build:
	docker build -t $(IMAGE) .

docker-shell:
	docker run --rm -it -v "$(PWD):/workspace" -w /workspace $(IMAGE) bash

run:
	docker run --rm -v "$(PWD):/workspace" -w /workspace $(IMAGE) python3 scripts/run_experiments.py --benchmarks "$(BENCHMARKS)" --experiment-set "$(EXPERIMENTS)" --max-instructions "$(MAX_INST)" --timeout-sec "$(TIMEOUT_SEC)" --jobs "$(JOBS)" --output "$(RESULTS)"

task4-search: docker-build
	docker run --rm -v "$(PWD):/workspace" -w /workspace $(IMAGE) python3 scripts/run_experiments.py --benchmarks "li3_vortex2" --experiment-set "task4_search" --max-instructions "$(TASK4_SEARCH_MAX_INST)" --timeout-sec "$(TASK4_SEARCH_TIMEOUT_SEC)" --jobs "$(FULL_JOBS)" --schedule "interleaved" --progress-interval-sec "$(PROGRESS_INTERVAL_SEC)" --output "$(TASK4_SEARCH_RESULTS)"
	python3 scripts/analyze_task4_search.py --results "$(TASK4_SEARCH_RESULTS)" --html-output "$(TASK4_SEARCH_RESULTS)/task4-search.html"

report:
	python3 scripts/generate_report.py --results "$(RESULTS)" --output site
	python3 scripts/generate_jean_page.py --results "$(RESULTS)" --search-results "$(JEAN_SEARCH_RESULTS)" --output "$(JEAN_PAGE)"

jean-page:
	python3 scripts/generate_jean_page.py --results "$(RESULTS)" --search-results "$(JEAN_SEARCH_RESULTS)" --output "$(JEAN_PAGE)"

validate-site:
	python3 scripts/validate_site.py --site site --results "$(RESULTS)"

validate-metadata:
	python3 scripts/validate_experiments.py

test:
	python3 -m unittest discover -s tests

pages: report validate-site

smoke: docker-build
	docker run --rm -v "$(PWD):/workspace" -w /workspace $(IMAGE) python3 scripts/run_experiments.py --benchmarks quick --experiment-set smoke --max-instructions 100000 --timeout-sec 300 --output results/smoke
	python3 scripts/generate_report.py --results results/smoke --output site

clean-results:
	rm -rf results site
