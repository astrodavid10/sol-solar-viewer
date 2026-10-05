"""A validator check that raises fails its own product, never the whole run.

The defect (found by fuzzing, 2026-10-04): nulling a single manifest leaf made
24 different pfss checks raise -- `float(None)` and friends -- and the
exception escaped validate_products into cmd_all's outer handler, which prints
NOTHING PROMOTED and exits 1. CI then skips the publish and all six products
go stale over one bad number. io_utils._round_floats writes any NaN as a JSON
null, so the trigger is one NaN anywhere upstream.
"""

import functools
import json
from pathlib import Path

import pytest

from ..validate import PRODUCT_MANIFESTS, Tree, tree_from_root, validate_products

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"

live = pytest.mark.skipif(not (ROOT / "index.json").is_file(),
                          reason="no published tree in public/data")

# Leaves nulled per product. Enough to cover every top-level key and the first
# entries of each array; the full cross product would take minutes because the
# texture checks decode JPEGs.
MAX_LEAVES = 15


def _leaves(doc, path=()):
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(doc, list):
        for i, v in enumerate(doc[:2]):
            yield from _leaves(v, path + (i,))
    else:
        yield path


def _with_null(doc, path):
    doc = json.loads(json.dumps(doc))
    cur = doc
    for key in path[:-1]:
        cur = cur[key]
    cur[path[-1]] = None
    return doc


def _spread(items, n):
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def test_a_raising_check_becomes_a_failed_check_of_that_product():
    """Unit-level: no tree needed, the manifest itself is not JSON."""
    def get(rel):
        if rel == PRODUCT_MANIFESTS["ephemeris"]:
            return b'{"schema": "sol.ephem/1", "bodies": [1, 2, 3]}'
        return None

    tree = Tree(get, lambda rel: None, None, "synthetic")
    reports = validate_products(tree, products=["ephemeris"])
    assert "ephemeris" in reports           # it reported rather than raised


@live
@pytest.mark.parametrize("product", sorted(PRODUCT_MANIFESTS))
def test_nulling_any_leaf_never_raises(product):
    base = tree_from_root(str(ROOT))
    get = functools.lru_cache(maxsize=None)(base.get)
    rel = PRODUCT_MANIFESTS[product]
    doc = json.loads(get(rel))
    for path in _spread(list(_leaves(doc)), MAX_LEAVES):
        mutated = json.dumps(_with_null(doc, path)).encode()

        def patched(r, _m=mutated):
            return _m if r == rel else get(r)

        tree = Tree(patched, base.probe, base.root, base.label)
        try:
            validate_products(tree, products=[product])
        except Exception as exc:            # noqa: BLE001
            pytest.fail("{0}: nulling {1} raised {2!r}".format(
                product, "/".join(map(str, path)), exc))
