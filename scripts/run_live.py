"""
Live trading entry point (future use).
Requires IBKR account credentials in environment variables or config.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    print("Live trading not yet implemented.")
    print("Set IBKR_CONFIG in environment and uncomment the section below.")


if __name__ == "__main__":
    main()