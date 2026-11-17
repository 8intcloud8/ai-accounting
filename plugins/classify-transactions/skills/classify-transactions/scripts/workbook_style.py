"""Shared look for the Excel files people open: real Excel tables with banded rows and
filters, dollar formats, colour-coded statuses and an overview sheet first."""

from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

MONEY = '$#,##0.00;[Red]-$#,##0.00'
INK = "101A24"
ACCENT = "0F7A63"
STATUS_FILLS = {  # status text -> (fill, font colour)
    "Classified": ("E5F4EF", "0F5A49"),
    "Proposed": ("FFF4E0", "8A5300"),
    "Not classified": ("FDECEA", "9B1C13"),
}


def as_table(sheet, name, money=(), widths=None, wrap=()):
    """Turn row 1 headers plus data into a banded, filterable Excel table."""
    headers = [c.value for c in sheet[1]]
    letter = {h: get_column_letter(i + 1) for i, h in enumerate(headers)}
    if sheet.max_row >= 2:
        table = Table(displayName=name, ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sheet.add_table(table)
    else:
        for box in sheet[1]:
            box.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 22
    for box in sheet[1]:
        box.alignment = Alignment(vertical="center")
    for header in money:
        for box in sheet[letter[header]][1:]:
            box.number_format = MONEY
    for header in wrap:
        for box in sheet[letter[header]][1:]:
            box.alignment = Alignment(wrap_text=True, vertical="top")
    for header, width in (widths or {}).items():
        sheet.column_dimensions[letter[header]].width = width
    return letter


def colour_status(sheet, column, rows):
    """Colour each status cell by its value, so the state reads at a glance."""
    if rows < 2:
        return
    area = f"{column}2:{column}{rows}"
    for status, (fill, font) in STATUS_FILLS.items():
        sheet.conditional_formatting.add(area, CellIsRule(
            operator="equal", formula=[f'"{status}"'],
            fill=PatternFill("solid", fgColor=fill), font=Font(color=font, bold=True)))


def overview(book, title, subtitle, rows):
    """A first sheet with the headline numbers. `rows` are (label, value, is_money)."""
    sheet = book.create_sheet("Overview", 0)
    sheet["A1"] = title
    sheet["A1"].font = Font(size=16, bold=True, color=INK)
    sheet["A2"] = subtitle
    sheet["A2"].font = Font(color="5D6B78")
    for i, (label, value, is_money) in enumerate(rows, start=4):
        sheet.cell(i, 1, label).font = Font(color="5D6B78")
        box = sheet.cell(i, 2, value)
        box.font = Font(bold=True, size=12, color=STATUS_FILLS.get(label, (None, INK))[1])
        if is_money:
            box.number_format = MONEY
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 18
    sheet.sheet_view.showGridLines = False
    book.active = 0
    return sheet
