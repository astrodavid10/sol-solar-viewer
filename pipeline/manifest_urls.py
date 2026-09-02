"""One walker over a manifest's file references.

WHY THIS EXISTS.  Two places have to answer "which files does this manifest
name?", and both had grown their own hand-maintained answer:

* ``cli._prune_orphan_textures`` builds a keep-set and deletes everything else
  under ``texture/``.  Its comment history is a record of the same bug four
  times -- ``off_limb.url`` was forgotten, then ``off_limb.tiers[]``, then
  ``frames[].near_side.url``, then ``high_res.url``.  Each omission deletes
  files the SAME run just wrote, on the very publish that wrote them, and the
  only symptom is a missing image in the app.
* ``validate`` decodes a SAMPLE of the texture frames (three per channel of
  eighteen) and never looked at the rest at all.  Measured: deleting a
  non-sampled history frame from a copy of the published tree left
  ``validate --strict`` passing.  Footgun 35's production failure -- a
  ``texture.json`` naming fifteen history frames of which four were on disk --
  is exactly this hole, and it is still uncaught by the sampling.

Both are the same question, so it is asked once here.  The walker is GENERIC
on purpose: it does not know what an off-limb tier or a near-side window is,
so the next nested url is covered before anyone writes it.

WHAT COUNTS AS A URL.  Any string value under a key named ``url`` or ending in
``_url``.  That is the naming convention every product already follows --
``url``, ``topology_url``, ``source_url``, ``active_regions_url`` -- and it is
why a new nested block needs no change here.

WHAT IS DELIBERATELY SKIPPED, and why each would be wrong to include:

* **Absolute URLs.**  ``source_url`` is provenance: the sdo.gsfc.nasa.gov
  browse still a map was reprojected from.  It is not a file in our tree, it
  is not ours to keep or delete, and an existence check against it would put
  a third party's uptime in our publish path.
* **Cross-directory relative URLs.**  ``pfss/manifest.json`` carries
  ``active_regions_url: "../ar/regions.json"``.  Both users of this walker are
  per-directory (a keep-set for one glob, an existence pass for one product),
  and resolving that pointer would couple the pfss product's validation to the
  active-regions product's presence -- which is precisely the coupling footguns
  50 and 51 are about.  The consuming product validates its own dependency
  (see ``validate``'s ar_index checks).  ``is_sibling_file_url`` is exposed so
  a caller can see the rule rather than re-deriving it.
"""

from __future__ import annotations

from typing import Any, Iterator, List, Set

# A scheme (http:, https:, data:) or a protocol-relative // prefix means the
# reference leaves our tree.
_SCHEME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789+-.")


def _is_absolute(value: str) -> bool:
    if value.startswith("//"):
        return True
    head, _, _ = value.partition(":")
    return bool(_) and bool(head) and all(c in _SCHEME_CHARS
                                          for c in head.lower())


def is_url_key(key: str) -> bool:
    """``url`` or anything ending in ``_url`` -- the products' convention."""
    return key == "url" or key.endswith("_url")


def is_sibling_file_url(value: Any) -> bool:
    """True for a plain file name in the manifest's OWN directory.

    Sibling-only is the same rule ``validate._check_texture_jpeg`` already
    enforces on every texture url ("/" not in name); stating it once here is
    what lets the prune keep-set and the existence pass agree by construction.
    """
    if not isinstance(value, str) or not value:
        return False
    if _is_absolute(value):
        return False
    return "/" not in value and "\\" not in value


def iter_manifest_urls(doc: Any) -> Iterator[str]:
    """Every sibling file the manifest references: depth-first, deduped.

    Nesting depth is irrelevant, which is the entire point: a url added three
    blocks down is found without touching this function.  Deduped because the
    newest texture frame's url IS the layer's url (deliberately -- that slot is
    the full-resolution map) and the default off-limb rung also appears in its
    own tier ladder, so the raw walk repeats names.  Order is deterministic
    (each container's own keys before its children, children in declaration
    order) so a report reads the same way twice.
    """
    seen: Set[str] = set()
    stack: List[Any] = [doc]
    # An explicit stack rather than recursion: a manifest is arbitrary JSON
    # read off disk, and blowing the Python stack on a pathological one would
    # be a crash where a wrong answer is already handled.
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            children: List[Any] = []
            for key, value in node.items():
                if isinstance(value, str):
                    if is_url_key(str(key)) and is_sibling_file_url(value) \
                            and value not in seen:
                        seen.add(value)
                        yield value
                elif isinstance(value, (dict, list)):
                    children.append(value)
            stack.extend(reversed(children))
        elif isinstance(node, list):
            stack.extend(reversed([v for v in node
                                   if isinstance(v, (dict, list))]))


def manifest_url_set(doc: Any) -> Set[str]:
    """``set(iter_manifest_urls(doc))`` -- the keep-set / reference-set form."""
    return set(iter_manifest_urls(doc))


__all__ = ["iter_manifest_urls", "manifest_url_set", "is_sibling_file_url",
           "is_url_key"]
