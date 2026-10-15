"""Compatibility entry for the browser acceptance fixture.

Run python -m tests.browser_fixture and open /qa/history?variant=current.
"""
from tests.browser_fixture import main


if __name__ == "__main__":
    main()
