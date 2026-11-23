"""argparse value types shared by the command modules."""

import argparse


def non_negative_int(text: str) -> int:
    value = int(text)

    if value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {value}")

    return value


def positive_int(text: str) -> int:
    value = int(text)

    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value}")

    return value
