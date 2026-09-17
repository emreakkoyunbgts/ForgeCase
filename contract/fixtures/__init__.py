"""Independent, reviewable contract fixtures.

These modules must never import ``generator.core``, ``verifier.semantic``,
``common.drafts`` or ``common.quantities`` to derive an expected answer. If a
fixture were computed by the code under test, every contract assertion built on
it would be a tautology. Expected values here are written out literally so a
reviewer can check them by eye.
"""
