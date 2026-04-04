from typing import Any

# Roles worth surfacing to the agent — skip purely structural containers
_ACTIONABLE_ROLES = {
    "button",
    "link",
    "textbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "option",
    "menuitem",
    "tab",
    "heading",
    "img",
    "searchbox",
    "spinbutton",
    "slider",
    "switch",
    "treeitem",
}


def walk_tree(
    node: dict[str, Any],
) -> tuple[list[str], dict[str, tuple[str, str, int]]]:
    """
    Walk an accessibility tree dict (from page.accessibility.snapshot()).

    Returns:
        lines:   formatted text, e.g. ['heading "Hello" @e1', ...]
        ref_map: {"@e1": (role, name, occurrence_index), ...}
    """
    lines: list[str] = []
    ref_map: dict[str, tuple[str, str, int]] = {}
    occurrence_counter: dict[tuple[str, str], int] = {}
    counter = [1]

    def _visit(n: dict[str, Any]) -> None:
        role = (n.get("role") or "").lower()
        name = n.get("name") or ""

        if role in _ACTIONABLE_ROLES and name:
            key = (role, name)
            idx = occurrence_counter.get(key, 0)
            occurrence_counter[key] = idx + 1

            ref = f"@e{counter[0]}"
            counter[0] += 1
            ref_map[ref] = (role, name, idx)

            state_parts = []
            st = n.get("state") or {}
            if st.get("checked"):
                state_parts.append("checked")
            if st.get("selected"):
                state_parts.append("selected")
            if st.get("disabled"):
                state_parts.append("disabled")
            if "expanded" in st:
                state_parts.append("expanded" if st["expanded"] else "collapsed")
            state_str = f" [{', '.join(state_parts)}]" if state_parts else ""
            lines.append(f'{role} "{name}"{state_str} {ref}')

        for child in n.get("children") or []:
            _visit(child)

    _visit(node)
    return lines, ref_map


def build_ref_locator_args(role: str, name: str, nth: int) -> dict[str, Any]:
    """Return kwargs needed to resolve a ref: page.get_by_role(role, name=name).nth(nth)."""
    return {"role": role, "name": name, "nth": nth}


def format_snapshot(lines: list[str]) -> str:
    return "\n".join(f"[{i + 1}] {line}" for i, line in enumerate(lines))
