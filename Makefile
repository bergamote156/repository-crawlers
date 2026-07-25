SRC_FILES  := $(shell find apps packages -type d \( -name src -o -name tests \) | grep -v '\.venv' | sort)
SRC_TYPED  := $(shell find apps packages -type d -name src | grep -v '\.venv' | sort)
TEST_PATHS := $(shell find apps packages -type d -name tests | grep -v '\.venv' | sort)
UV_RUN := uv run --group dev

.DEFAULT_GOAL := help
.PHONY: help sync format format-check static-analysis type-check lint test check

bold := $(shell tput bold)
normal := $(shell tput sgr0)
blue := $(shell tput setaf 4)

define print_target
	@echo ""
	@echo "$(blue)$(bold)$@:$(normal)"
endef

# `make help` groups targets by `##@ section` banners and lists each `target: ## description`.
help:
	@awk 'BEGIN{FS=":.*## "} /^##@ /{printf "\n%s:\n",substr($$0,5)} /^[a-z][a-zA-Z0-9_-]*:.*## /{printf "  %-20s %s\n",$$1,$$2}' $(MAKEFILE_LIST)

##@ dev

sync: ## install deps into .venv
	$(call print_target)
	uv sync --group dev

format: ## ruff autofix + format
	$(call print_target)
	$(UV_RUN) ruff check --fix $(SRC_FILES)
	$(UV_RUN) ruff format $(SRC_FILES)

format-check: ## ruff format --check
	$(call print_target)
	$(UV_RUN) ruff format $(SRC_FILES) --check || (echo "Code failed Ruff format checking. Please run 'make format' before committing your changes."; exit 1)

static-analysis: ## ruff check
	$(call print_target)
	$(UV_RUN) ruff check $(SRC_FILES)

type-check: ## mypy (src only)
	$(call print_target)
	$(UV_RUN) mypy --install-types --non-interactive $(SRC_TYPED)

lint: format-check static-analysis type-check ## format-check + static-analysis + type-check
	@:

test: ## pytest (+ junit for CI)
	$(call print_target)
	$(UV_RUN) pytest $(TEST_PATHS) -v --junitxml=repository-crawlers-tests-results.xml

check: lint test ## lint + test
	@:
