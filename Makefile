SRC_FILES := apps/crawlers/src apps/crawlers/tests apps/registrar/src
TEST_PATHS := apps/crawlers/tests
UV_RUN := uv run --group dev

.PHONY: sync format black-check static-analysis type-check lint test

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
	$(UV_RUN) isort $(SRC_FILES)
	$(UV_RUN) black --fast $(SRC_FILES)

black-check:
	$(call print_target)
	$(UV_RUN) black $(SRC_FILES) --check || (echo "Code failed Black format checking. Please run 'make format' before committing your changes."; exit 1)

##
## Static analysis
##

static-analysis:
	$(call print_target)
	$(UV_RUN) pylint $(SRC_FILES) --recursive=y

##
## Type checking
##

type-check:
	$(call print_target)
	$(UV_RUN) mypy --install-types --non-interactive $(SRC_FILES)

lint: black-check static-analysis type-check
	@:

##
## Tests
##

test:
	$(call print_target)
	$(UV_RUN) pytest $(TEST_PATHS) -v --junitxml=repository-crawlers-tests-results.xml
