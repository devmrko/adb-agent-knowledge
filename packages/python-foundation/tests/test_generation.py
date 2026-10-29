import pytest

from python_foundation.cli import generate


@pytest.mark.parametrize("database", ["sqlite", "oracle"])
@pytest.mark.parametrize("auth", ["session", "token", "mixed"])
def test_generator_has_six_variants_and_never_overwrites(tmp_path, database, auth):
    destination = tmp_path / f"sample-{database}-{auth}"
    generate(destination, "sample", database, auth)
    source = (destination / "src/sample/app.py").read_text()
    compile(source, "app.py", "exec")
    assert "__AUTH__" not in source and "__DATABASE_FIELD__" not in source
    with pytest.raises(FileExistsError):
        generate(destination, "sample", database, auth)
    assert (destination / "src/sample/app.py").read_text() == source


def test_generator_rejects_invalid_package_without_creating_directory(tmp_path):
    destination = tmp_path / "sample"
    with pytest.raises(ValueError):
        generate(destination, "../unsafe", "sqlite", "session")
    assert not destination.exists()
