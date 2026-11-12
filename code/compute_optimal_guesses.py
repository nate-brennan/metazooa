#!/usr/bin/env python3
"""Compute an optimal strategy for a tree guessing game and write it to a CSV file.

The game is played on a tree in which some nodes can be the answer. The answer is
picked uniformly at random from those nodes, and the player guesses one of them at
a time. After each wrong guess, the player is told the lowest common ancestor (LCA)
of the guess and the answer. The strategy is a decision tree that minimizes the
expected number of guesses: each decision is a guess, plus the decision to make next
for each LCA the player can be told. Whenever several guesses are equally good, the
strategy picks the one whose name is first alphabetically.

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


class Decision:
    def __init__(self, group, guess):
        self.group = group  # the answer is known to be under this node
        self.guess = guess
        self.if_lca = {}  # LCA of the guess and the answer, if the guess is wrong -> next Decision
        self.size = 0  # set by compute_sizes


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

    The options of every node under `option` must already be sorted.
    """
    return node if option is node else probe_path(option)[-1]


def sort_options(node):
    """Set the options of `node` and every node under it.

    The options of a node are the places an answer under it can be: each child with answers under
    it, plus the node itself if it can be the answer. They're sorted largest first, and options of
    the same size by the name of the guess that checks them, so that whenever several guesses are
    equally good, the strategy picks the one that's first alphabetically.
    """
    for child in node.children:
        sort_options(child)
    node.options = [child for child in node.children if child.size > 0]
    if node.can_be_answer:
        node.options.append(node)
    node.options.sort(key=lambda option: (-option_size(node, option), option_guess(node, option).name.casefold()))


def probe_path(option):
    """Return the path from `option` down through each node's largest option, until a node's
    largest option is itself. The last node on the path is the one to guess."""
    path = [option]
    while path[-1].options[0] is not path[-1]:
        path.append(path[-1].options[0])
    return path


def build_decision(group, i):
    """Return the Decision that checks group.options[i], or None if no options are left.

    The answer is known to be under `group`, but not in group.options[:i].
    """
    if i >= len(group.options):
        return None

    option = group.options[i]
    path = [] if option is group else probe_path(option)
    decision = Decision(group, path[-1] if path else group)

    # LCA = group: the answer isn't in this option, so check the next one.
    next_decision = build_decision(group, i + 1)
    if next_decision:
        decision.if_lca[group] = next_decision

    # LCA = a node on the path: the answer is under that node, but not in its first option.
    for node in path:
        deeper = build_decision(node, 1)
        if deeper:
            decision.if_lca[node] = deeper

    return decision


def build_strategy(root):
    """Return the first Decision of an optimal strategy, or None if no node can be the answer."""
    count_answers(root)
    sort_options(root)
    return build_decision(root, 0)


def compute_sizes(decision):
    """Set the size of `decision` and every Decision that can follow it, and return the size of `decision`.

    The answers still possible when a decision is reached are exactly the guesses of the decisions
    in its subtree, so its size is the number of decisions in the subtree.
    """
    decision.size = 1 + sum(compute_sizes(next_decision) for next_decision in decision.if_lca.values())
    return decision.size


def group_decisions(first):
    """Yield the list of Decisions made in each group, starting with the group of `first`.

    A group's list starts with the Decision made when the player first gets to the group, and goes
    on for as long as the player is told the same group again.
    """
    group = first.group
    decisions = [first]
    while group in decisions[-1].if_lca:
        decisions.append(decisions[-1].if_lca[group])
    yield decisions
    for decision in decisions:
        for lca, next_decision in decision.if_lca.items():
            if lca is not group:
                yield from group_decisions(next_decision)


def write_csv(path, groups):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Size", "Group", "Guesses"])
        for decisions in groups:
            guesses = ", ".join(decision.guess.name for decision in decisions)
            writer.writerow([decisions[0].size, decisions[0].group.name, guesses])


def main():
    parser = argparse.ArgumentParser(description="Compute an optimal strategy for a tree guessing game and write it to a CSV file.")
    parser.add_argument("-i", "--input", required=True, help="path of the game tree CSV file to read")
    parser.add_argument("-o", "--output", required=True, help="path of the CSV file to write the strategy to")
    args = parser.parse_args()

    first = build_strategy(read_tree(args.input))
    if first is None:
        sys.exit(f"No nodes in {args.input} can be the answer")
    compute_sizes(first)

    groups = sorted(group_decisions(first), key=lambda decisions: (-decisions[0].size, decisions[0].group.name.casefold()))
    write_csv(args.output, groups)
    print(f"Wrote {len(groups)} groups to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
