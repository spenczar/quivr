import numpy as np
import pyarrow as pa

from quivr.columns import Int64Column, StringColumn
from quivr.indexing import StringIndex
from quivr.tables import Table


class TableWithString(Table):
    id = Int64Column()
    name = StringColumn()
    value = Int64Column()


def test_indexing():
    table = TableWithString.from_arrays([pa.array([1, 2, 3]), pa.array(["a", "b", "c"]), pa.array([4, 5, 6])])
    index = StringIndex(table, "name")
    assert len(index.lookup("a")) == 1
    np.testing.assert_array_equal(index.lookup("a").id, [1])
    assert len(index.lookup("b")) == 1
    np.testing.assert_array_equal(index.lookup("b").id, [2])


def test_indexing_duplicate():
    table = TableWithString.from_arrays([pa.array([1, 2, 3]), pa.array(["a", "a", "c"]), pa.array([4, 5, 6])])
    index = StringIndex(table, "name")
    assert len(index.lookup("a")) == 2
    np.testing.assert_array_equal(index.lookup("a").id, [1, 2])
    assert index.lookup("b") is None
