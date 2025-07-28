.PHONY: build upload-test upload

build:
	uv build

upload-test: build
	uv publish --repository testpypi --token ${TWINE_TEST_PYPI_TOKEN} dist/*

upload: build
	uv publish --token ${TWINE_PYPI_TOKEN} dist/*