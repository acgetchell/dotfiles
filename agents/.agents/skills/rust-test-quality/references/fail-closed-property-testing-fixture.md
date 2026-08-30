# Fail-Closed Property-Testing Fixture

Use these paired cases to calibrate reviews of generated Rust tests. The first
case rejects only independently recognizable raw-input states. The second must
produce a finding because a production failure is converted into a discarded
case.

## Valid Raw-Domain Rejection

```rust
proptest! {
    #[test]
    fn admitted_triangles_have_nonnegative_area(raw in raw_triangles()) {
        prop_assume!(raw.iter().all(|point| point.iter().all(|value| value.is_finite())));
        prop_assume!(raw.windows(2).all(|pair| pair[0] != pair[1]));

        let triangle = Triangle::try_from(raw.clone()).map_err(|error| {
            TestCaseError::fail(format!("admitted raw triangle {raw:?} failed construction: {error:?}"))
        })?;
        prop_assert!(triangle.area() >= 0.0);
    }
}
```

Expected review: no fail-open finding. Admission uses only raw finite-value and
duplicate-point facts; an unexpected production construction error fails with
replay context.

## Invalid Production-Success Filter

```rust
proptest! {
    #[test]
    fn triangles_have_nonnegative_area(raw in raw_triangles()) {
        let result = Triangle::try_from(raw.clone());
        prop_assume!(result.is_ok());

        if let Ok(triangle) = result {
            prop_assert!(triangle.area() >= 0.0);
        }
    }
}
```

Expected review: report a finding. A broken `Triangle::try_from` can return
`Err` for every admitted input and the property will discard every case instead
of failing. The smallest correction is to define admission from independent raw
facts, unwrap the admitted construction through a property failure carrying
`raw` and the typed/debug error, and retain one deterministic successful input
in ordinary validation.
