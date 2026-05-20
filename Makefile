IMAGE ?= sim-outorder:local
RESULTS ?= results/latest
BENCHMARKS ?= quick
EXPERIMENTS ?= smoke
MAX_INST ?= 100000
TIMEOUT_SEC ?= 0

.PHONY: docker-build docker-shell run report pages smoke clean-results

docker-build:
	docker build -t $(IMAGE) .

docker-shell:
	docker run --rm -it -v "$(PWD):/workspace" -w /workspace $(IMAGE) bash

run:
	docker run --rm -v "$(PWD):/workspace" -w /workspace $(IMAGE) python3 scripts/run_experiments.py --benchmarks "$(BENCHMARKS)" --experiment-set "$(EXPERIMENTS)" --max-instructions "$(MAX_INST)" --timeout-sec "$(TIMEOUT_SEC)" --output "$(RESULTS)"

report:
	python3 scripts/generate_report.py --results "$(RESULTS)" --output site

pages: report

smoke: docker-build
	docker run --rm -v "$(PWD):/workspace" -w /workspace $(IMAGE) python3 scripts/run_experiments.py --benchmarks quick --experiment-set smoke --max-instructions 100000 --timeout-sec 300 --output results/smoke
	python3 scripts/generate_report.py --results results/smoke --output site

clean-results:
	rm -rf results site
