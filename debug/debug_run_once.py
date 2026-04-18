from pathlib import Path
import os

from shared.config import Settings
from crawler.crawling.pipeline import CrawlPipeline
from persistence_api.repository import build_repository


def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    debug_data_dir = workspace_root / "data" / "debug"
    export_dir = debug_data_dir / "exports"
    debug_db_path = debug_data_dir / "run-once.sqlite"

    debug_data_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Force the local debug flow onto SQLite instead of any Docker/Postgres DSN
    # that may be inherited from the shell or loaded from the project .env file.
    os.environ["HEYBLOG_DB_DSN"] = ""
    os.environ["HEYBLOG_DB_PATH"] = str(debug_db_path)
    os.environ["HEYBLOG_EXPORT_DIR"] = str(export_dir)

    settings = Settings.from_env()
    settings.db_dsn = None
    settings.db_path = debug_db_path
    settings.export_dir = export_dir

    print("debug db_path =", settings.db_path)
    print("debug db_dsn =", settings.db_dsn)
    print("debug seed_path =", settings.seed_path)
    print("debug export_dir =", settings.export_dir)

    repo = build_repository(db_path=settings.db_path, db_dsn=settings.db_dsn)
    pipeline = CrawlPipeline(settings, repo)

    print("bootstrap_result =", pipeline.bootstrap_seeds())

    result = pipeline.run_once(max_nodes=1)
    print("run_once_result =", result)


if __name__ == "__main__":
    main()
