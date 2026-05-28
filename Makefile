SRC_FILES  := $(shell find apps packages -type d \( -name src -o -name tests \) | grep -v '\.venv' | sort)
SRC_TYPED  := $(shell find apps packages -type d -name src | grep -v '\.venv' | sort)
TEST_PATHS := $(shell find apps packages -type d -name tests | grep -v '\.venv' | sort)
UV_RUN := uv run --group dev

.PHONY: sync format format-check static-analysis type-check lint test

bold := $(shell tput bold)
normal := $(shell tput sgr0)
blue := $(shell tput setaf 4)

define print_target
	@echo ""
	@echo "$(blue)$(bold)$@:$(normal)"
endef

##
## Formatting
##

sync:
	$(call print_target)
	uv sync --group dev

format:
	$(call print_target)
	$(UV_RUN) ruff check --fix $(SRC_FILES)
	$(UV_RUN) ruff format $(SRC_FILES)

format-check:
	$(call print_target)
	$(UV_RUN) ruff format $(SRC_FILES) --check || (echo "Code failed Ruff format checking. Please run 'make format' before committing your changes."; exit 1)

##
## Static analysis
##

static-analysis:
	$(call print_target)
	$(UV_RUN) ruff check $(SRC_FILES)

##
## Type checking
##

type-check:
	$(call print_target)
	$(UV_RUN) mypy --install-types --non-interactive $(SRC_TYPED)

lint: format-check static-analysis type-check
	@:

##
## Tests
##

test:
	$(call print_target)
	$(UV_RUN) pytest $(TEST_PATHS) -v --junitxml=repository-crawlers-tests-results.xml
