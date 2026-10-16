"""Entry point shared by the desktop app and its console worker."""
import sys
from runtime_paths import initialize_runtime


def main():
    initialize_runtime()
    if len(sys.argv) > 1 and sys.argv[1] == "--run-tracker":
        del sys.argv[1]
        from tracker import cli_main
        return cli_main()
    if len(sys.argv) > 2 and sys.argv[1] == "--self-test":
        from packaging_smoke import run_self_test
        return run_self_test(sys.argv[2])
    from main import run_gui
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
