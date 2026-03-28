.PHONY: version bump-patch bump-minor bump-major build-deb publish-apt release clean

VERSION_FILE := VERSION
VERSION := $(shell cat $(VERSION_FILE) | tr -d '[:space:]')

version:
	@echo $(VERSION)

bump-patch:
	@IFS='.' read -r major minor patch < $(VERSION_FILE); \
	patch=$$((patch + 1)); \
	echo "$$major.$$minor.$$patch" > $(VERSION_FILE); \
	echo "Bumped to $$(cat $(VERSION_FILE))"

bump-minor:
	@IFS='.' read -r major minor patch < $(VERSION_FILE); \
	minor=$$((minor + 1)); \
	echo "$$major.$$minor.0" > $(VERSION_FILE); \
	echo "Bumped to $$(cat $(VERSION_FILE))"

bump-major:
	@IFS='.' read -r major minor patch < $(VERSION_FILE); \
	major=$$((major + 1)); \
	echo "$$major.0.0" > $(VERSION_FILE); \
	echo "Bumped to $$(cat $(VERSION_FILE))"

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
	git add VERSION dist/ frontend/public/apt/ packaging/; \
	git commit -m "release: v$$NEW_VERSION"; \
	git tag "v$$NEW_VERSION"
	@echo ""
	@echo "Release v$$(cat $(VERSION_FILE)) created (not pushed)."
	@echo "  git push origin main --tags"

clean:
	rm -rf dist/ build/
	rm -rf frontend/public/apt/pool/
	rm -rf frontend/public/apt/dists/
