# quivr

Quivr is a Python library which provides great containers for Arrow data.

Quivr's `Table`s are like DataFrames, but with strict schemas to
enforce types and expectations. They are backed by the
high-performance Arrow memory model, making them well-suited for
streaming IO, RPCs, and serialization/deserialization to Parquet.

## why?

Data engineering involves taking analysis code and algorithms which
were prototyped, often on pandas DataFrames, and shoring them up for
production use.

While DataFrames are great for ad-hoc exploration, visualization, and
prototyping, they aren't as great for building sturdy applications:

 - Loose and dynamic typing makes it difficult to be sure that code is
   correct without lots of explicit checks of the dataframe's state.
 - Performance of Pandas operations can be unpredictable and have
   surprising characteristics, which makes it harder to provision
   resources.
 - DataFrames can use an extremely large amount of memory (typical
   numbers cited are between 2x and 10x the "raw" data's size), and
   often are forced to copy data in intermediate computations, which
   poses unnecessarily heavy requirements.
 - The mutability of DataFrames can make debugging difficult and lead
   to confusing state.

We don't want to throw everything out, here. Vectorized computations
are often absolutely necessary for data work. But what if we could
have those vectorized computations, but with:
 - Types enforced at runtime, with no dynamically column information.
 - Relatively uniform performance due to a no-copy orientation
 - Immutable data, allowing multiple views at very fast speed

This is what Quivr's Tables try to provide.

## Installation

Check out this repo, and `pip install` it.

## Usage

Your main entrypoint to Quivr is through defining classes which
represent your tables. You write a subclass of quivr.Table, annotating
it with Columns that describe the data you're working with, and quivr
will handle the rest.

```python
from quivr import Table, Float64Column
import pyarrow as pa


class Coordinates(Table):
	x = Float64Column()
	y = Float64Column()
	z = Float64Column()
	vx = Float64Column()
	vy = Float64Column()
	vz = Float64Column()
```

Then, you can construct tables from data:

```python

coords = Coordinates.from_data(
    x=np.array([ 1.00760887, -2.06203093,  1.24360546, -1.00131722]),
    y=np.array([-2.7227298 ,  0.70239707,  2.23125432,  0.37269832]),
    z=np.array([-0.27148738, -0.31768623, -0.2180482 , -0.02528401]),
    vx=np.array([ 0.00920172, -0.00570486, -0.00877929, -0.00809866]),
    vy=np.array([ 0.00297888, -0.00914301,  0.00525891, -0.01119134]),
    vz=np.array([-0.00160217,  0.00677584,  0.00091095, -0.00140548])
)

# Sort the table by the z column. This returns a copy.
coords_z_sorted = coords.sort_by("z")

print(len(coords))
# prints 4

# Access any of the columns as a numpy array with zero copy:
xs = coords.x.to_numpy()

# Present the table as a pandas DataFrame, with zero copy if possible:
df = coords.to_dataframe()
```

### Embedded definitions and nullable columns

You can embed one table's definition within another, and you can make columns nullable:

```python

class AsteroidOrbit(Table):
	designation = StringColumn()
	mass = Float64Column(nullable=True)
	radius = Float64Column(nullable=True)
	coords = Coordinates.as_column()

# You can construct embedded columns from Arrow StructArrays, which you can get from
# other Quivr tables using the to_structarray() method with zero copy.
orbits = AsteroidOrbit.from_data(
    designation=np.array(["Ceres", "Pallas", "Vesta", "2023 DW"]),
    mass=np.array([9.393e20, 2.06e21, 2.59e20, None]),
    radius=np.array([4.6e6, 2.7e6, 2.6e6, None]),
    coords=coords.to_structarray(),
)
```

### Computing

#### Using Numpy
When you reference columns, you'll get numpy arrays which you can use to do computations:

```python
import numpy as np

print(np.quantile(orbits.mass + 10, 0.5)
```


#### Using pyarrow.compute

You can also use access columns of the data as Arrow Arrays to do
computations using the Pyarrow compute kernels:

```python
import pyarrow.compute as pc

median_mass = pc.quantile(pc.add(orbits.column(mass, as_numpy=False), 10), q=0.5)
# median_mass is a pyarrow.Scalar, which you can get the value of with .as_py()
print(median_mass.as_py())
```

There is a very extensive set of functions available in the
`pyarrow.compute` package, which you can see
[here](https://arrow.apache.org/docs/python/compute.html). These
computations will, in general, use all cores available and do
vectorized computations which are very fast.

### Customizing behavior with methods

Because Quivr tables are just Python classes, you can customize the
behavior of your tables by adding or overriding methods. For example, if you want to add a
method to compute the total mass of the asteroids in the table, you
can do so like this:

```python

class AsteroidOrbit(Table):
	designation = StringColumn()
	mass = Float64Column(nullable=True)
	radius = Float64Column(nullable=True)
	coords = Coordinates.as_column()

    def total_mass(self):
        return pc.sum(self.mass)

```

You can also use this to add "meta-columns" which are combinations of other columns. For example:

```python
class CoordinateCovariance(Table):
	matrix_values = ListColumn(pa.float64(), 36)

    @property
    def matrix(self):
        # This is a numpy array of shape (n, 6, 6)
        return self.matrix_values.to_numpy().reshape(-1, 6, 6)


class AsteroidOrbit(Table):
	designation = StringColumn()
	mass = Float64Column(nullable=True)
	radius = Float64Column(nullable=True)
	coords = Coordinates.as_column()
	covariance = CoordinateCovariance.as_column()

orbits = load_orbits() # Analogous to the example above

# Compute the determinant of the covariance matrix for each asteroid
determinants = np.linalg.det(orbits.covariance.matrix)
```

### Adding instance attributes

You can also add more attributes (that is, non-Column ones) to your
class and its instances, but doing so requires a bit more attention.

You can override `__init__` to add instance-level attributes. However,
if you do this, there are a few rules:

 1. Your `__init__` method must have an attribute called `table`, with
    type `pyarrow.Table`, and you must pass this to Table's `__init__`
    (via `super().__init__(table)`).
 2. You must implement a `with_table(self, table: pa.Table) -> Self`
    method which returns a **new** instance with the provided table,
    bringing along the current values of all instance attributes.

For example:

```python
from typing import Self

class AsteroidOrbit(Table):
    designation = StringColumn()
	mass = Float64Column(nullable=True)
	
	def __init__(self, table: pa.Table, mu: float):
	    super().__init__(table)
		self.mu = mu
		
	def with_table(self, table: pa.Table) -> Self:
        return AsteroidOrbit(table, self.mu)
```

The `with_table` method will be used in iteration, slicing and
indexing operations, so try to make it pretty quick.

In addition, note that serialization methods (`to_csv`, `to_feather`,
and `to_parquet`) will not, by default, bring along your instance
attributes. If you would like to serialize the instance attributes,
either override those methods or add additional serialization methods
of your own, and similarly implement deserializers.


### Data Validation

You can validate that the data inside a Table matches constraints you
define. Only a small number of validators are currently implemented,
mostly for numeric checks, but as use cases emerge, more will be
added.

To add data validation, use the `validator=` keyword inside
columns. For example:

```python
from quivr import Table, Int64Column, Float64Column, StringColumn
from quivr.validators import gt, ge, le, and_, is_in

class Observation(Table):
    id = Int64Column(validator=gt(0))
    ra = Float64Column(validator=and_(ge(0), le(360))
    dataset_id = StringColumn(validator=is_in(["ztf", "nsc", "skymapper"])))
    unvalidated = Int64Column()
```

This `Observation` table has validators that
- the `id` column's values are greater than 0
- the `ra` column's values are between 0 and 360, inclusive
- the `dataset_id` column only has strings in the set `{"ztf", "nsc", "skymapper"}`

When an `Observation` instance is created using the `from_data`
method, these validation checks will be run, by default. This can be
disabled by calling `Observation.from_data(..., validate=False)`.

In addition, an instance can be explicitly validated by calling the
`.validate()` method, which will raise a `quivr.ValidationError` if
there are any failures.

Also, tables have a `.is_valid()` method which returns a boolean to
indicate whether they pass validation.


### Filtering
You can also filter by expressions on the data. See [Arrow
documentation](https://arrow.apache.org/docs/python/compute.html) for
more details. You can use this to construct a quivr Table using an
appropriately-schemaed Arrow Table:

```python

big_orbits = AsteroidOrbit(orbits.table.filter(orbits.table["mass"] > 1e21))
```

If you're plucking out rows that match a single value, you can use the
"select" method on the Table:

```python
# Get the orbit of Ceres
ceres_orbit = orbits.select("designation", "Ceres")
```

#### Indexes for Fast Lookups

If you're going to be doing a lot of lookups on a particular column,
it can be useful to create an index for that column. You can do using
the `quivr.StringIndex` class to build an index for string values:

```python
# Build an index for the designation column
designation_index = quivr.StringIndex(orbits, "designation")

# Get the orbit of Ceres
ceres_orbit = designation_index.lookup("Ceres")
```

The `lookup` method on the StringIndex returns Quivr Tables, or None
if there is no match. Keep in mind that the returned tables might have
multiple rows if there are multiple matches.

_TODO: Add numeric and time-based indexes._

### Serialization

#### Feather
Feather is a fast, zero-copy serialization format for Arrow tables. It
can be used for interprocess communication, or for working with data
on disk via memory mapping.

```python
orbits.to_feather("orbits.feather")

orbits_roundtripped = AsteroidOrbit.from_feather("orbits.feather")

# use memory mapping to work with a large file without copying it into memory
orbits_mmap = AsteroidOrbit.from_feather("orbits.feather", memory_map=True)
```


#### Parquet

You can serialize your tables to Parquet files, and read them back:

```python
orbits.to_parquet("orbits.parquet")

orbits_roundtripped = AsteroidOrbit.from_parquet("orbits.parquet")
```

See the [Arrow
documentation](https://arrow.apache.org/docs/python/parquet.html) for
more details on the Parquet format used.
