# Resources

`pilot.json` registers the local IFsBase/Working sources and reviewed analysis semantics. Paths resolve relative to that file, not the current working directory.

`countries-872.json` fixes the reviewed model membership. Other datasets must be checked against this membership rather than automatically trusting every Region bucket as a country.

Only reviewed SUM variables are enabled for standard aggregation. `sum_dimensions` and `summed_dimension_buckets` explicitly identify extra dimensions and their allowed members. This prevents summing both component categories and a total category. Variable dictionary metadata is informational and marked unverified against generating versions.

Store private datasets, extracted blobs, indexes, and execution artifacts under ignored `workspace/`, or register existing read-only locations. Never store credentials in the manifest.
