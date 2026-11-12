#!/usr/bin/env python3
"""Compute an optimal strategy for a tree guessing game and write it to a CSV file.

The game is played on a tree in which some nodes can be the answer. The answer is
picked uniformly at random from those nodes, and the player guesses one of them at
a time. After each wrong guess, the player is told the lowest common ancestor (LCA)
of the guess and the answer. The strategy minimizes the expected number of guesses,
and whenever several guesses are equally good, it picks the one whose name is first
alphabetically. The proof that it's optimal is in math/proof.tex.

The game tree is read from a CSV file with `id,name,canBeAnswer,parent` columns, where
`canBeAnswer` is `true` or `false` and `parent` is the id of the node's parent, or
empty for the root.

The strategy is written as one `Size,Group,Guesses` row per group, where the group is
the last LCA the player was told (the root before any guess):
    Size     number of answers still possible when the player first gets to the group
    Group    name of the group
    Guesses  names of the guesses to make in the group, in order, until the player is
             told a different group or guesses the answer
Rows are sorted by Size, largest first, then alphabetically by Group. The first row is
always the root, since it's the only group with every answer still possible.

Usage:
    python3 compute_optimal_guesses.py --input tree.csv --output strategy.csv
"""

import argparse
import csv
import sys


class Node:
    def __init__(self, name, can_be_answer):
        self.name = name
        self.can_be_answer = can_be_answer
        self.children = []
        self.size = 0  # number of answers in the subtree, set by count_answers
        self.options = []  # set by sort_options
        self.guess = None  # set by sort_options


class Group:
    def __init__(self, node, options):
        self.node = node  # the last LCA the player was told
        self.size = sum(option_size(node, option) for option in options)
        self.guesses = [option_guess(node, option) for option in options]


def read_tree(path):
    """Read the game tree from a CSV file and return its root."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    nodes = {}
    for row in rows:
        can_be_answer = row["canBeAnswer"].lower()
        if can_be_answer not in ("true", "false"):
            sys.exit(f"canBeAnswer of node {row['id']} is {row['canBeAnswer']!r}, not true or false")
        nodes[row["id"]] = Node(row["name"], can_be_answer == "true")

    roots = []
    for row in rows:
        if row["parent"]:
            nodes[row["parent"]].children.append(nodes[row["id"]])
        else:
            roots.append(nodes[row["id"]])
    if len(roots) != 1:
        sys.exit(f"Expected one node without a parent in {path}, found {len(roots)}")
    return roots[0]


def count_answers(node):
    """Set the size of `node` and every node under it, and return the size of `node`."""
    node.size = (1 if node.can_be_answer else 0) + sum(count_answers(child) for child in node.children)
    return node.size


def option_size(node, option):
    return 1 if option is node else option.size


def option_guess(node, option):
    """Return the node to guess to check `option` of `node`.

    If `option` is a child, its guess must already be set by sort_options.
    """
    return node if option is node else option.guess


def sort_options(node):
    """Set the options and the guess of `node` and every node under it.

    The options of a node are the places an answer under it can be: each child with answers under
    it, plus the node itself if it can be the answer. They're sorted largest first, and options of
    the same size by the name of the guess that checks them, so that whenever several guesses are
    equally good, the strategy picks the one that's first alphabetically.

    The guess of a node is the guess that checks its first option. It's the first guess to make
    when the answer is known to be under the node.
    """
    for child in node.children:
        sort_options(child)
    node.options = [child for child in node.children if child.size > 0]
    if node.can_be_answer:
        node.options.append(node)
    node.options.sort(key=lambda option: (-option_size(node, option), option_guess(node, option).name.casefold()))
    if node.options:
        node.guess = option_guess(node, node.options[0])


def strategy_groups(node, options):
    """Yield the Group in which the player checks `options` of `node`, unless there are none, then
    every Group under `node`.

    The player checks every option of the root. She's only told another node after a guess in its
    first option, so in any other group, she checks the options after the first.
    """
    if options:
        yield Group(node, options)
    for child in node.children:
        yield from strategy_groups(child, child.options[1:])


def build_strategy(root):
    """Return the Groups of an optimal strategy, which are empty if no node can be the answer."""
    count_answers(root)
    sort_options(root)
    return list(strategy_groups(root, root.options))


def write_csv(path, groups):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Size", "Group", "Guesses"])
        for group in groups:
            writer.writerow([group.size, group.node.name, ", ".join(guess.name for guess in group.guesses)])


def main():
    parser = argparse.ArgumentParser(description="Compute an optimal strategy for a tree guessing game and write it to a CSV file.")
    parser.add_argument("-i", "--input", required=True, help="path of the game tree CSV file to read")
    parser.add_argument("-o", "--output", required=True, help="path of the CSV file to write the strategy to")
    args = parser.parse_args()

    groups = build_strategy(read_tree(args.input))
    if not groups:
        sys.exit(f"No nodes in {args.input} can be the answer")

    groups.sort(key=lambda group: (-group.size, group.node.name.casefold()))
    write_csv(args.output, groups)
    print(f"Wrote {len(groups)} groups to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
