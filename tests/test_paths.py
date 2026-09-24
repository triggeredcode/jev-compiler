from jevcompiler.paths import DEFAULT_CACHE_PATH, artifact_directory


def test_generated_paths_share_one_local_workspace() -> None:
    assert artifact_directory("support-router", "dataset").as_posix() == (
        ".jevcompiler/artifacts/support-router/dataset"
    )
    assert DEFAULT_CACHE_PATH.as_posix() == ".jevcompiler/cache/jev-responses.sqlite3"
