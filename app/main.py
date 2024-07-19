import sys
from dataclasses import dataclass
from enum import IntEnum
from mmap import ACCESS_READ, mmap

from app import _read_integer
from app.cells import TableLeafCell

DOT_DBINFO = ".dbinfo"

PAGE_SIZE_OFFSET = 16

# import sqlparse - available if you need it!

CELL_POINTER_SIZE = 2
MIN_PAGE_SIZE = 512


class PageType(IntEnum):
    INDEX_INTERIOR = 2
    TABLE_INTERIOR = 5
    INDEX_LEAF = 10
    TABLE_LEAF = 13

    def is_interior(self):
        return self in (PageType.TABLE_INTERIOR, PageType.INDEX_INTERIOR)

    def is_table(self):
        return self in (PageType.TABLE_LEAF, PageType.TABLE_INTERIOR)

    def is_leaf(self):
        return not self.is_interior()

    def is_index(self):
        return not self.is_table()

    def cell_pointer_array_offset(self):
        return 12 if self.is_interior() else 8


@dataclass
class DbInfo:
    page_size: int = 0

    def __init__(self, database_file_path):
        with open(database_file_path, "rb") as database_file:
            database_mmap = mmap(database_file.fileno(), 0, access=ACCESS_READ)
            self.page_size = _read_integer(database_mmap, PAGE_SIZE_OFFSET, 2)
            self.page_size = 65536 if self.page_size == 1 else self.page_size
            sqlite_schema_tree_root = DbPage(
                database_mmap, page_number=1, page_size=self.page_size
            )
            self.table_names = sqlite_schema_tree_root.child_rows


@dataclass
class DbPage:
    number_of_cells: int = 0
    page_size: int = -1

    RIGHT_MOST_POINTER_OFFSET = 8

    def __init__(self, database_file, page_number=1, page_size=4096, usable_size=4096):
        self.child_rows = []
        self.page_size = page_size
        self.usable_size = usable_size
        self.database_file = database_file
        self.page_content_cells_offset = self.page_size * (page_number - 1)
        self.page_offset = 100 if page_number == 1 else self.page_content_cells_offset
        self.page = database_file[self.page_offset: self.page_content_cells_offset + self.page_size]

        self.page_type = PageType(self._read_integer(0, 1))
        assert self.page_type.is_table()
        first_freeblock = self._read_integer(1, 2)
        # assert first_freeblock == 0
        self.number_of_cells = self._read_integer(3, 2)
        cell_content_area_start = self._read_integer(5, 2)
        self.cell_content_area_start = (
            65536 if cell_content_area_start == 0 else cell_content_area_start
        )

        self.children = []
        if self.page_type.is_leaf():
            for cell in range(self.number_of_cells):
                self.child_rows.append(self.get_table_name(cell))
        elif self.page_type.is_interior():
            for cell in range(self.number_of_cells):
                cell_content_pointer = self.get_cell_content_pointer(cell)
                self._add_child_at(cell_content_pointer)

            self._add_child_at(DbPage.RIGHT_MOST_POINTER_OFFSET)

    def get_table_name(self, cell_number):
        cell = self.get_cell(cell_number)
        # cell_slice, payload_size_length = cell

        return cell.columns

    def get_cell(self, cell_number):
        return TableLeafCell(self.page, self.get_cell_content_pointer(cell_number), self.usable_size)

    def get_cell_content_pointer(self, cell):
        cell_pointer_location = (
                cell * CELL_POINTER_SIZE
                + self.page_type.cell_pointer_array_offset()
        )
        cell_offset = self._read_integer(cell_pointer_location, CELL_POINTER_SIZE)
        return cell_offset + self.page_content_cells_offset - self.page_offset

    def _read_integer(self, location_in_page, size):
        return _read_integer(self.page, location_in_page, size)

    def _add_child_at(self, child_page_number_location):
        child_page_number = self._read_integer(child_page_number_location, 4)
        child_page = DbPage(self.database_file, child_page_number, self.page_size)
        self.children.append(child_page)
        self.child_rows += child_page.child_rows


def main():
    database_file_path = "sample.db"
    if len(sys.argv) > 1:
        database_file_path = sys.argv[1]
    command = DOT_DBINFO
    if len(sys.argv) > 2:
        command = sys.argv[2]

    if command == DOT_DBINFO:
        db_info = DbInfo(database_file_path)
        print(f"database page size: {db_info.page_size}")
        print(f"number of tables: {db_info.number_of_tables}")
    else:
        print(f"Invalid command: {command}")


if __name__ == "__main__":
    main()
