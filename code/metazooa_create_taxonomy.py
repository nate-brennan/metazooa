#!/usr/bin/env python3
"""Write the NCBI taxonomy tree of the Metazooa animals to a CSV file.

Downloads the Metazooa animal list and the NCBI taxonomy dump, then writes each
animal on the list plus its ancestors up to Metazoa as
`id,name,canBeAnswer,parent` rows. Ancestors that aren't on the list and have
only one child are left out, and that child is attached to their parent instead.
`id` is the NCBI taxonomy id and `parent` is the id of the parent taxon;
Metazoa's parent is left empty. Listed animals get their name from the list and
`canBeAnswer` set to `true`; every other taxon gets its NCBI scientific name and
`canBeAnswer` set to `false`. Rows are ordered so that each taxon appears after
its parent.

Usage:
    python3 metazooa_create_taxonomy.py --output metazoa.csv
"""

import argparse
import collections
import csv
import io
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request

ANIMALS_URL = "https://raw.githubusercontent.com/the-abe-train/metazooa-translations/refs/heads/main/Species%20Lists/animals.json"
TAXDUMP_URL = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"
METAZOA_TAXID = 33208


def download_animals():
    """Return a dict mapping the NCBI taxid of each animal on the Metazooa list to its name."""
    print(f"Downloading {ANIMALS_URL}", file=sys.stderr)
    with urllib.request.urlopen(ANIMALS_URL, timeout=60) as response:
        return {animal["nodeId"]: animal["name"] for animal in json.load(response)}


def read_dmp(tar, member_name):
    """Yield the fields of each row of a .dmp file in the taxdump archive."""
    with tar.extractfile(member_name) as raw:
        for line in io.TextIOWrapper(raw, encoding="utf-8"):
            yield line.rstrip("\t|\n").split("\t|\t")


def metazoa_subtree(tar):
    """Return (taxid, parent_taxid) pairs for Metazoa and all its descendants, in depth-first order."""
    children = {}
    for fields in read_dmp(tar, "nodes.dmp"):
        taxid, parent = int(fields[0]), int(fields[1])
        if taxid != parent:  # the root node is its own parent
            children.setdefault(parent, []).append(taxid)

    subtree = []
    stack = [(METAZOA_TAXID, None)]
    while stack:
        taxid, parent = stack.pop()
        subtree.append((taxid, parent))
        stack.extend((child, taxid) for child in reversed(children.get(taxid, [])))
    return subtree


def filter_tree(subtree, animals):
    """Keep only the animals and their ancestors from `subtree`, preserving its order."""
    parents = dict(subtree)
    missing = [f"{name} ({taxid})" for taxid, name in animals.items() if taxid not in parents]
    if missing:
        sys.exit(f"Animals not found under Metazoa in the NCBI taxonomy: {', '.join(missing)}")

    kept = set()
    for taxid in animals:
        while taxid is not None and taxid not in kept:
            kept.add(taxid)
            taxid = parents[taxid]
    return [(taxid, parent) for taxid, parent in subtree if taxid in kept]


def collapse_single_child_taxa(tree, animals):
    """Remove non-animal taxa that have exactly one child, attaching the child to the removed taxon's parent.

    `tree` must list each taxon after its parent.
    """
    child_counts = collections.Counter(parent for _, parent in tree)
    replacements = {}
    collapsed = []
    for taxid, parent in tree:
        parent = replacements.get(parent, parent)
        if taxid not in animals and child_counts[taxid] == 1:
            replacements[taxid] = parent
        else:
            collapsed.append((taxid, parent))
    return collapsed


def scientific_names(tar, taxids):
    names = {}
    for taxid, name, _unique_name, name_class in read_dmp(tar, "names.dmp"):
        if name_class == "scientific name" and int(taxid) in taxids:
            names[int(taxid)] = name
    return names


def main():
    parser = argparse.ArgumentParser(description="Write the NCBI taxonomy tree of the Metazooa animals to a CSV file.")
    parser.add_argument("-o", "--output", required=True, help="path of the CSV file to write")
    args = parser.parse_args()

    animals = download_animals()

    with tempfile.TemporaryFile() as archive:
        print(f"Downloading {TAXDUMP_URL}", file=sys.stderr)
        with urllib.request.urlopen(TAXDUMP_URL, timeout=60) as response:
            shutil.copyfileobj(response, archive)
        archive.seek(0)

        with tarfile.open(fileobj=archive, mode="r:gz") as tar:
            print("Building tree from nodes.dmp", file=sys.stderr)
            tree = collapse_single_child_taxa(filter_tree(metazoa_subtree(tar), animals), animals)
            print("Reading names from names.dmp", file=sys.stderr)
            names = scientific_names(tar, {taxid for taxid, _ in tree})
    names.update(animals)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "canBeAnswer", "parent"])
        for taxid, parent in tree:
            writer.writerow([taxid, names[taxid], "true" if taxid in animals else "false", parent])

    print(f"Wrote {len(tree):,} taxa ({len(animals)} animals) to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
