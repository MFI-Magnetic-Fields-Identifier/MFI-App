from argparse import ArgumentParser


def main() -> None:
    """Confirma que o pacote pode ser executado."""
    parser = ArgumentParser(prog="python -m mfi_cv")
    parser.parse_args()
    print("MFI CV: ambiente Python pronto.")


if __name__ == "__main__":
    main()
