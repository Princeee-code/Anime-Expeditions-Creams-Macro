.PHONY: help install run clean test build

help:
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Herm's Engine | Anime Expeditions"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "  Targets:"
	@echo "    make install   — Install Python dependencies"
	@echo "    make run       — Launch the GUI macro"
	@echo "    make test      — Run CLI diagnostics (no GUI)"
	@echo "    make build     — Build executable with PyInstaller"
	@echo "    make clean     — Remove build artifacts and caches"
	@echo "    make help      — Show this message"
	@echo ""

install:
	pip install -r requirements.txt
	@if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi

run:
	python main.py

test:
	python main.py --test

build:
	python build_pyinstaller.py

clean:
	rm -rf build/ dist/ __pycache__/ *.spec
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
