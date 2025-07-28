.PHONY: clean build patch minor major upload-test upload test

clean:
	rm -rf dist/

build:
	uv build

patch:
	uv version --bump patch

minor:
	uv version --bump minor

major:
	uv version --bump major

upload-test: clean build
	uv publish --repository testpypi --token ${TWINE_TEST_PYPI_TOKEN} dist/*

upload: clean build
	uv publish --token ${TWINE_PYPI_TOKEN} dist/*

test:
	uv sync; rm -rf refs; ref-fetch pip
