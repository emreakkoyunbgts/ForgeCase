"""
Exit codes — see the Project Specification, section 5.2.

    0  SUCCESS    the program did what was asked
    1  REJECTED   a legitimate negative result (e.g. the Verifier found an
                  invented fact). This is NOT a crash — it is the program
                  working correctly.
    2  BAD_INPUT  unreadable file, missing argument, malformed JSON

Programs MUST NOT crash with a stack trace. Catch it, say what happened,
exit with the right code.
"""
import sys

SUCCESS = 0
REJECTED = 1
BAD_INPUT = 2


def die(message, code=BAD_INPUT):
    """Print a clear error to stderr and exit. Never raise a raw traceback."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)
