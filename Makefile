.PHONY: init-db ingest ingest-dry-run help

help:
	@echo "Support AI Assistant - Commands"
	@echo "  make init-db      - Create database and run migrations"
	@echo "  make ingest       - Ingest docs from source/ into database"
	@echo "  make ingest-dry   - Dry run: load docs without ingesting"

init-db:
	@python scripts/init_db.py

ingest:
	@python scripts/ingest_from_source.py

ingest-dry:
	@python scripts/ingest_from_source.py --dry-run
