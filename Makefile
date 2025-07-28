.PHONY: clean build upload-test upload test

clean:
	rm -rf dist/

build:
	uv build

upload-test: clean build
	uv publish --repository testpypi --token ${TWINE_TEST_PYPI_TOKEN} dist/*

upload: clean build
	uv publish --token ${TWINE_PYPI_TOKEN} dist/*

test:
	pip install -r requirements.txt; rm -rf refs; ./ref_fetch.py pip