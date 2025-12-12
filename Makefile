STATIC_ANALYSER_IMAGE := "docker.onedata.org/python_static_analyser:v10"
SRC_FILES := ecudo registrar

UID := $(shell id -u)
GID := $(shell id -g)

.PHONY: format black-check static-analysis type-check lint test

define docker_run
	docker run --rm -i -v $(CURDIR):$(CURDIR) -w $(CURDIR) -u $(UID):$(GID) $(STATIC_ANALYSER_IMAGE) $1
endef

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
	$(call docker_run, isort $(SRC_FILES))
	$(call docker_run, black --fast $(SRC_FILES))

black-check:
	$(call print_target)
	$(call docker_run, black $(SRC_FILES) --check) || (echo "Code failed Black format checking. Please run 'make format' before committing your changes."; exit 1)

##
## Static analysis
##

static-analysis:
	$(call print_target)
	$(call docker_run, sh -c "pip install -qq --break-system-packages -r requirements.txt && pylint $(SRC_FILES) --recursive=y")

##
## Type checking
##

type-check:
	$(call print_target)
	$(call docker_run, sh -c "pip install -qq --break-system-packages -r requirements.txt && mypy --install-types --non-interactive $(SRC_FILES)")

lint: black-check static-analysis type-check
	@:

##
## Tests
##

test:
	$(call print_target)
	$(call docker_run, sh -c "pip install -qq --break-system-packages -r requirements.txt && pytest tests")
