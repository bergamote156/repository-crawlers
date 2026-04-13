SRC_FILES := crawlers registrar tests

.PHONY: format black-check static-analysis type-check lint test

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

format:
	$(call print_target)
	uv run isort $(SRC_FILES)
	uv run black --fast $(SRC_FILES)

black-check:
	$(call print_target)
	uv run black $(SRC_FILES) --check || (echo "Code failed Black format checking. Please run 'make format' before committing your changes."; exit 1)

##
## Static analysis
##

static-analysis:
	$(call print_target)
	uv run pylint $(SRC_FILES) --recursive=y

##
## Type checking
##

type-check:
	$(call print_target)
	uv run mypy --install-types --non-interactive $(SRC_FILES)

lint: black-check static-analysis type-check
	@:

##
## Tests
##

test:
	$(call print_target)
	uv run pytest tests -v --junitxml=public-data-crawlers-tests-results.xml
