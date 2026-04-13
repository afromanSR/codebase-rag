from pathlib import Path

from codebase_rag.indexer.detector import RepoProfile, detect_stack


def touch_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_detect_laravel(tmp_path: Path) -> None:
    touch_file(tmp_path / "composer.json")
    touch_file(tmp_path / "artisan")

    profile = detect_stack(tmp_path)

    assert isinstance(profile, RepoProfile)
    assert profile.stack == "laravel"
    assert profile.language == "php"
    assert profile.framework == "Laravel"
    assert "routes" in profile.key_paths
    assert "migrations" in profile.key_paths
    assert "models" in profile.key_paths
    assert "controllers" in profile.key_paths


def test_detect_php_generic(tmp_path: Path) -> None:
    touch_file(tmp_path / "composer.json")

    profile = detect_stack(tmp_path)

    assert profile.stack == "php"
    assert profile.language == "php"
    assert profile.framework == "Generic PHP"


def test_detect_go_generic(tmp_path: Path) -> None:
    touch_file(tmp_path / "go.mod")

    profile = detect_stack(tmp_path)

    assert profile.stack == "go"
    assert profile.language == "go"


def test_detect_go_chi(tmp_path: Path) -> None:
    touch_file(tmp_path / "go.mod")
    (tmp_path / "internal" / "server").mkdir(parents=True)

    profile = detect_stack(tmp_path)

    assert profile.stack == "go-chi"
    assert profile.framework == "Chi"


def test_detect_vue(tmp_path: Path) -> None:
    touch_file(tmp_path / "package.json")
    touch_file(tmp_path / "src" / "App.vue")

    profile = detect_stack(tmp_path)

    assert profile.stack == "vue"
    assert profile.language == "typescript"
    assert profile.framework == "Vue 3"


def test_detect_nextjs(tmp_path: Path) -> None:
    touch_file(tmp_path / "package.json")
    touch_file(tmp_path / "next.config.js")

    profile = detect_stack(tmp_path)

    assert profile.stack == "nextjs"


def test_detect_nuxt(tmp_path: Path) -> None:
    touch_file(tmp_path / "package.json")
    touch_file(tmp_path / "nuxt.config.ts")

    profile = detect_stack(tmp_path)

    assert profile.stack == "nuxt"


def test_detect_node_generic(tmp_path: Path) -> None:
    touch_file(tmp_path / "package.json")

    profile = detect_stack(tmp_path)

    assert profile.stack == "node"


def test_detect_rust(tmp_path: Path) -> None:
    touch_file(tmp_path / "Cargo.toml")

    profile = detect_stack(tmp_path)

    assert profile.stack == "rust"


def test_detect_dotnet(tmp_path: Path) -> None:
    touch_file(tmp_path / "app.csproj")

    profile = detect_stack(tmp_path)

    assert profile.stack == "dotnet"


def test_detect_java_gradle(tmp_path: Path) -> None:
    touch_file(tmp_path / "build.gradle")

    profile = detect_stack(tmp_path)

    assert profile.stack == "java"


def test_detect_java_maven(tmp_path: Path) -> None:
    touch_file(tmp_path / "pom.xml")

    profile = detect_stack(tmp_path)

    assert profile.stack == "java"


def test_detect_unknown(tmp_path: Path) -> None:
    profile = detect_stack(tmp_path)

    assert profile.stack == "unknown"


def test_repo_name_from_directory(tmp_path: Path) -> None:
    profile = detect_stack(tmp_path)

    assert profile.name == tmp_path.name


def test_repo_path_is_absolute(tmp_path: Path) -> None:
    profile = detect_stack(tmp_path)

    assert Path(profile.path).is_absolute()


def test_key_paths_env_when_exists(tmp_path: Path) -> None:
    touch_file(tmp_path / ".env.example")

    profile = detect_stack(tmp_path)

    assert "env" in profile.key_paths


def test_key_paths_docker_when_exists(tmp_path: Path) -> None:
    touch_file(tmp_path / "docker-compose.yml")

    profile = detect_stack(tmp_path)

    assert "docker" in profile.key_paths
