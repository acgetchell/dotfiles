ci: python-tests notebook-check

python-tests:
    @echo python-tests

notebook-export:
    @echo notebook-export

notebook-lint: notebook-export
    @echo notebook-lint
    @test "${FAIL_LINT:-0}" != 1

notebook-check: notebook-lint
    @echo notebook-execute
