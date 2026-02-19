DB_MSG ?= init schema

ifneq (,$(wildcard .env))
include .env
export $(shell sed 's/=.*//' .env)
endif

.PHONY: db-revision db-upgrade db-init seed-admin

db-revision:
	alembic revision --autogenerate -m "$(DB_MSG)"

db-upgrade:
	alembic upgrade head

db-init: db-revision db-upgrade

seed-admin:
	python scripts/seed_admin.py
