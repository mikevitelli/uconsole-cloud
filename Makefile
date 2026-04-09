.PHONY: version bump-patch bump-minor bump-major build-deb publish-apt release install dev-mode pkg-mode clean

VERSION_FILE := VERSION
VERSION := $(shell cat $(VERSION_FILE) | tr -d '[:space:]')

version:
	@echo $(VERSION)

bump-patch:
	@IFS='.' read -r major minor patch < $(VERSION_FILE); \
	patch=$$((patch + 1)); \
	echo "$$major.$$minor.$$patch" > $(VERSION_FILE); \
	cp $(VERSION_FILE) device/VERSION; \
	echo "Bumped to $$(cat $(VERSION_FILE))"

bump-minor:
	@IFS='.' read -r major minor patch < $(VERSION_FILE); \
	minor=$$((minor + 1)); \
	echo "$$major.$$minor.0" > $(VERSION_FILE); \
	cp $(VERSION_FILE) device/VERSION; \
	echo "Bumped to $$(cat $(VERSION_FILE))"

bump-major:
	@IFS='.' read -r major minor patch < $(VERSION_FILE); \
	major=$$((major + 1)); \
	echo "$$major.0.0" > $(VERSION_FILE); \
	cp $(VERSION_FILE) device/VERSION; \
	echo "Bumped to $$(cat $(VERSION_FILE))"

RSYNC_EXCLUDE := --exclude __pycache__ --exclude .pytest_cache --exclude tests \
	--exclude .flake8 --exclude Makefile --exclude .git

install:
	@echo "Deploying device/ → /opt/uconsole/"
	@sudo rsync -a --delete $(RSYNC_EXCLUDE) device/lib/ /opt/uconsole/lib/
	@sudo rsync -a --delete $(RSYNC_EXCLUDE) device/scripts/ /opt/uconsole/scripts/
	@sudo rsync -a --delete $(RSYNC_EXCLUDE) device/webdash/ /opt/uconsole/webdash/
	@sudo rsync -a --delete $(RSYNC_EXCLUDE) device/bin/ /opt/uconsole/bin/
	@sudo rsync -a --delete $(RSYNC_EXCLUDE) device/share/ /opt/uconsole/share/
	@sudo cp frontend/public/scripts/uconsole /opt/uconsole/bin/uconsole 2>/dev/null || true
	@sudo chmod +x /opt/uconsole/bin/* 2>/dev/null || true
	@echo "Syncing device/ → ~/pkg/ (no --delete, preserves backup-only files)"
	@rsync -a $(RSYNC_EXCLUDE) device/ $(HOME)/pkg/
	@if systemctl is-active --quiet uconsole-webdash 2>/dev/null; then \
		sudo systemctl restart uconsole-webdash; \
		echo "Done. Webdash restarted."; \
	else \
		echo "Done."; \
	fi

dev-mode:
	@REAL_USER=$$(logname 2>/dev/null || whoami); \
	REAL_HOME=$$(getent passwd "$$REAL_USER" | cut -d: -f6); \
	REPO_ROOT=$$(pwd); \
	sudo mkdir -p /etc/systemd/system/uconsole-webdash.service.d; \
	printf '[Service]\nExecStart=\nExecStart=/usr/bin/python3 %s/device/webdash/app.py\nWorkingDirectory=%s/device/webdash\n' \
		"$$REPO_ROOT" "$$REPO_ROOT" | sudo tee /etc/systemd/system/uconsole-webdash.service.d/dev.conf >/dev/null; \
	sudo systemctl daemon-reload; \
	sudo systemctl restart uconsole-webdash 2>/dev/null || true; \
	echo "Dev mode: webdash running from $$REPO_ROOT/device/webdash/"

pkg-mode:
	@sudo rm -f /etc/systemd/system/uconsole-webdash.service.d/dev.conf; \
	sudo systemctl daemon-reload; \
	sudo systemctl restart uconsole-webdash 2>/dev/null || true; \
	echo "Package mode: webdash running from /opt/uconsole/webdash/"

build-deb:
	bash packaging/build-deb.sh

publish-apt:
	@DEB=$$(ls -t dist/uconsole-cloud_*_arm64.deb 2>/dev/null | head -1); \
	if [ -z "$$DEB" ]; then \
		echo "ERROR: No .deb found in dist/. Run 'make build-deb' first." >&2; \
		exit 1; \
	fi; \
	bash packaging/scripts/generate-repo.sh "$$DEB"

release: bump-patch build-deb publish-apt
	@NEW_VERSION=$$(cat $(VERSION_FILE) | tr -d '[:space:]'); \
	git add VERSION frontend/public/apt/ packaging/ .gitignore; \
	git commit -m "release: v$$NEW_VERSION"; \
	git tag "v$$NEW_VERSION"
	@echo ""
	@echo "Release v$$(cat $(VERSION_FILE)) created (not pushed)."
	@echo "  git push origin main --tags"

clean:
	rm -rf dist/ build/
	rm -rf frontend/public/apt/pool/
	rm -rf frontend/public/apt/dists/
