.PHONY: test test-html

# Run pytest with a terminal coverage summary
test:
	cd backend && source venv/bin/activate && \
	GEMINI_API_KEY=test-fake-key-do-not-use \
	pytest tests/ \
	  --cov=main \
	  --cov-report=term-missing \
	  --cov-fail-under=80 \
	  -v

# Same but also produce an HTML coverage report
test-html:
	cd backend && source venv/bin/activate && \
	GEMINI_API_KEY=test-fake-key-do-not-use \
	pytest tests/ \
	  --cov=main \
	  --cov-report=term-missing \
	  --cov-report=html:../htmlcov \
	  --cov-fail-under=80 \
	  -v
	@echo "\nHTML report generated → learnr/htmlcov/index.html"
