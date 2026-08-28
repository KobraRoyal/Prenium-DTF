"""Contrat studio : un groupe mémorisé s’aligne et se répartit comme un seul objet.

Miroir volontaire de `gang-sheet-editor.js` (`layoutUnits`, `alignSelectedItems`,
`distributeSelectedItems`). Toute évolution de ce comportement doit mettre à jour
le JS et ce fichier.
"""

from __future__ import annotations

from collections import defaultdict


def _round(value, digits=2):
    return float(f"{float(value):.{digits}f}")


def _size(item):
    if int(item.get("rotation") or 0) in (90, 270):
        return item["height_mm"], item["width_mm"]
    return item["width_mm"], item["height_mm"]


def _bounds(items):
    left = top = float("inf")
    right = bottom = float("-inf")
    for item in items:
        width, height = _size(item)
        left = min(left, item["x_mm"])
        top = min(top, item["y_mm"])
        right = max(right, item["x_mm"] + width)
        bottom = max(bottom, item["y_mm"] + height)
    return left, top, right, bottom


def layout_units(items):
    grouped = defaultdict(list)
    units = []
    for item in items:
        group_id = item.get("layout_group_id") or ""
        if not group_id:
            units.append([item])
        else:
            grouped[group_id].append(item)
    units.extend(grouped.values())
    return [{"items": members, "bounds": _bounds(members)} for members in units]


def _translate(items, delta_x, delta_y):
    for item in items:
        item["x_mm"] = _round(item["x_mm"] + delta_x)
        item["y_mm"] = _round(item["y_mm"] + delta_y)


def _item(public_id, x_mm, y_mm, width_mm, height_mm, group=None):
    return {
        "public_id": public_id,
        "x_mm": x_mm,
        "y_mm": y_mm,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "layout_group_id": group,
    }


def _axis_size(unit, *, horizontal):
    start = unit["bounds"][0] if horizontal else unit["bounds"][1]
    end = unit["bounds"][2] if horizontal else unit["bounds"][3]
    return end - start


def align_on_selection(items, direction):
    left, top, right, bottom = _bounds(items)
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    for unit in layout_units(items):
        if len(unit["items"]) == 1:
            item = unit["items"][0]
            width, height = _size(item)
            if direction == "left":
                item["x_mm"] = _round(left)
            elif direction == "center-x":
                item["x_mm"] = _round(center_x - width / 2)
            elif direction == "right":
                item["x_mm"] = _round(right - width)
            elif direction == "top":
                item["y_mm"] = _round(top)
            elif direction == "center-y":
                item["y_mm"] = _round(center_y - height / 2)
            elif direction == "bottom":
                item["y_mm"] = _round(bottom)
            continue
        unit_left, unit_top, unit_right, unit_bottom = unit["bounds"]
        delta_x = delta_y = 0
        if direction == "left":
            delta_x = left - unit_left
        elif direction == "center-x":
            delta_x = center_x - (unit_left + unit_right) / 2
        elif direction == "right":
            delta_x = right - unit_right
        elif direction == "top":
            delta_y = top - unit_top
        elif direction == "center-y":
            delta_y = center_y - (unit_top + unit_bottom) / 2
        elif direction == "bottom":
            delta_y = bottom - unit_bottom
        _translate(unit["items"], delta_x, delta_y)


def distribute_axis(items, *, horizontal):
    units = layout_units(items)
    if len(units) < 3:
        return False
    sorted_units = sorted(
        units,
        key=lambda unit: unit["bounds"][0] if horizontal else unit["bounds"][1],
    )
    first, last = sorted_units[0], sorted_units[-1]
    first_start = first["bounds"][0] if horizontal else first["bounds"][1]
    last_end = last["bounds"][2] if horizontal else last["bounds"][3]
    total_size = sum(_axis_size(unit, horizontal=horizontal) for unit in sorted_units)
    gap = (last_end - first_start - total_size) / (len(sorted_units) - 1)
    if gap < 0:
        return False
    cursor = first_start
    for unit in sorted_units:
        origin = unit["bounds"][0] if horizontal else unit["bounds"][1]
        delta = cursor - origin
        _translate(unit["items"], delta if horizontal else 0, 0 if horizontal else delta)
        size = _axis_size(unit, horizontal=horizontal)
        cursor += size + gap
    return True


def test_ungrouped_align_left_still_stacks_individuals():
    items = [
        _item("a", 10, 0, 20, 10),
        _item("b", 40, 5, 20, 10),
    ]
    align_on_selection(items, "left")
    assert [item["x_mm"] for item in items] == [10, 10]


def test_grouped_pair_align_left_keeps_internal_gap():
    items = [
        _item("a", 10, 0, 20, 10, "g1"),
        _item("b", 40, 5, 20, 10, "g1"),
        _item("c", 80, 0, 10, 10),
    ]
    align_on_selection(items, "left")
    grouped = [item for item in items if item["layout_group_id"] == "g1"]
    assert grouped[0]["x_mm"] == 10
    assert grouped[1]["x_mm"] == 40
    assert grouped[1]["x_mm"] - grouped[0]["x_mm"] == 30
    assert items[2]["x_mm"] == 10


def test_grouped_pair_align_right_translates_as_one_object():
    items = [
        _item("a", 10, 0, 20, 10, "g1"),
        _item("b", 40, 5, 20, 10, "g1"),
        _item("c", 80, 0, 10, 10),
    ]
    align_on_selection(items, "right")
    assert items[0]["x_mm"] == 40
    assert items[1]["x_mm"] == 70
    assert items[1]["x_mm"] - items[0]["x_mm"] == 30
    assert items[2]["x_mm"] == 80


def test_layout_units_count_grouped_members_as_one():
    items = [
        _item("a", 0, 0, 10, 10, "g1"),
        _item("b", 20, 0, 10, 10, "g1"),
        _item("c", 50, 0, 10, 10),
        _item("d", 80, 0, 10, 10),
    ]
    assert len(layout_units(items)) == 3


def test_distribute_horizontal_moves_group_as_block():
    items = [
        _item("a", 0, 0, 20, 10, "g1"),
        _item("b", 10, 12, 15, 8, "g1"),
        _item("c", 40, 0, 10, 10),
        _item("d", 90, 0, 10, 10),
    ]
    assert distribute_axis(items, horizontal=True) is True
    assert items[1]["x_mm"] - items[0]["x_mm"] == 10
    assert items[1]["y_mm"] - items[0]["y_mm"] == 12
    assert items[0]["x_mm"] == 0
    assert items[3]["x_mm"] == 90
    assert items[2]["x_mm"] == 52.5


def test_one_group_of_three_is_a_single_distribute_unit():
    items = [
        _item("a", 0, 0, 10, 10, "g1"),
        _item("b", 20, 0, 10, 10, "g1"),
        _item("c", 40, 0, 10, 10, "g1"),
    ]
    assert len(layout_units(items)) == 1
    assert distribute_axis(items, horizontal=True) is False
    assert [item["x_mm"] for item in items] == [0, 20, 40]
