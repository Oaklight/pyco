CONDA_PREFIX ?= $(HOME)/ml_lab/envs/snugpy
PYTHON ?= python3
VERSION ?= 3.14
TARGET ?= linux-x86_64
PROFILE ?= baseline
DISTRIBUTION ?=
RUNS ?= 10
JOBS ?= $(shell nproc 2>/dev/null || echo 1)
IMAGE_TAG ?=
NAMESPACE ?= oaklight

export PYTHONPATH := $(CURDIR)$(if $(PYTHONPATH),:$(PYTHONPATH))

.PHONY: all help conda lock check fetch build test test-full measure package report matrix clean images publish-images

all: check

help:
	@echo "Available targets:"
	@echo "  conda       - Create or update the conda toolchain at CONDA_PREFIX"
	@echo "  lock        - Regenerate conda-linux-64.lock from CONDA_PREFIX"
	@echo "  check       - Run unit tests, compileall, ShellCheck, and shfmt"
	@echo "  fetch       - Download and verify pinned CPython and zerodep sources"
	@echo "  build       - Build one PROFILE for VERSION and TARGET"
	@echo "  test        - Run smoke gates for one built PROFILE"
	@echo "  test-full   - Run full CPython and zerodep gates"
	@echo "  measure     - Measure size, dependencies, startup, and RSS"
	@echo "  package     - Create and verify distribution archives"
	@echo "  report      - Write results/summary.csv and results/report.md"
	@echo "  matrix      - Build, test, measure, and package all seven profiles"
	@echo "  images      - Build the runtime images locally"
	@echo "  publish-images - Build and push the runtime images to Docker Hub"
	@echo "  clean       - Remove work/, out/, and dist/"
	@echo ""
	@echo "Variables:"
	@echo "  CONDA_PREFIX=$(CONDA_PREFIX)"
	@echo "  PYTHON=$(PYTHON)"
	@echo "  VERSION=$(VERSION)  TARGET=$(TARGET)  PROFILE=$(PROFILE)"
	@echo "  DISTRIBUTION=$(DISTRIBUTION)  (empty packages headless, headed, and test)"
	@echo "  RUNS=$(RUNS)  JOBS=$(JOBS)"
	@echo "  IMAGE_TAG=$(IMAGE_TAG)  NAMESPACE=$(NAMESPACE)"

conda:
	./scripts/setup-conda.sh "$(CONDA_PREFIX)"

lock:
	./scripts/lock-conda.sh "$(CONDA_PREFIX)"

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m compileall -q snugpy_build tests benchmarks
	command -v shellcheck >/dev/null
	shellcheck scripts/*.sh
	command -v shfmt >/dev/null
	shfmt -d scripts/*.sh

fetch:
	./scripts/fetch.sh "$(VERSION)" --zerodep

build:
	./scripts/build.sh "$(VERSION)" "$(PROFILE)" "$(TARGET)" --jobs "$(JOBS)"

test:
	./scripts/test.sh "$(VERSION)" "$(PROFILE)" "$(TARGET)" --smoke

test-full:
	./scripts/test.sh "$(VERSION)" "$(PROFILE)" "$(TARGET)" --full --network

measure:
	./scripts/measure.sh "$(VERSION)" "$(PROFILE)" "$(TARGET)" --runs "$(RUNS)"

package:
	./scripts/package.sh "$(VERSION)" "$(PROFILE)" "$(TARGET)" $(if $(DISTRIBUTION),--distribution "$(DISTRIBUTION)")

report:
	./scripts/report.sh

matrix:
	./scripts/matrix.sh --version "$(VERSION)" --target "$(TARGET)" --runs "$(RUNS)"

images:
	./scripts/publish-images.sh "$(VERSION)" "$(PROFILE)" "$(TARGET)" \
		--namespace "$(NAMESPACE)" $(if $(IMAGE_TAG),--tag "$(IMAGE_TAG)")

publish-images:
	./scripts/publish-images.sh "$(VERSION)" "$(PROFILE)" "$(TARGET)" \
		--namespace "$(NAMESPACE)" $(if $(IMAGE_TAG),--tag "$(IMAGE_TAG)") \
		--push --latest

clean:
	./scripts/clean.sh
