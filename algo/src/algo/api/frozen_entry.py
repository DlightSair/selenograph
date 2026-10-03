"""Entry point of the packaged server: `selenograph-server.exe` serves the API; with `--run-pipeline`
(used by the server to start a run as a child process) it runs one registration instead."""
import multiprocessing
import sys


def main() -> None:
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--run-pipeline":
        sys.argv = ["pipeline"] + sys.argv[2:]
        from algo.pipeline import main as run_pipeline

        run_pipeline()
    else:
        from algo.api.server import main as serve

        serve()


if __name__ == "__main__":
    main()
