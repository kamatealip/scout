from app import app, serve
from indexer import index_file


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python main.py [SUBCOMMAND] [ARGS]")
        usage()
        return

    subcommand = sys.argv[1].upper()
    if subcommand == "INDEX":
        if len(sys.argv) < 3:
            print("Usage: python main.py INDEX [folder path]")
            return
        index_file(sys.argv[2])
        return
    if subcommand == "SERVE":
        serve(app)
        return
    usage()


def usage():
    print("SUBCOMMANDS:")
    print("      INDEX:   [folder path]: Process HTML files and store word counts in SQLite")
    print("      SERVE: Start the Flask web server")


if __name__ == "__main__":
    main()
