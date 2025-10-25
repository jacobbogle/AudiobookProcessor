# Dataflow-Ordered Detailed To-Do List

This file provides a step-by-step, mode/option-marked todo list for refactoring and test updates, based on the simplification plan.

---

## 1. CLI/Argparse Layer (all modes)
- Refactor CLI entrypoint and mode dispatch
- Normalize and validate all CLI args
- Update CLI tests for new config object
- Add tests for option combinations

## 2. Metadata Extraction (extract mode)
- Standardize output dicts for extraction functions
- Restore/export missing helpers
- Update extraction tests for dict outputs
- Add edge case tests

## 3. Mutation (mutate, mutate-convert modes)
- Refactor `mutate_metadata` to pure function
- Move file copying/renaming to utility
- Centralize option logic
- Update mutation tests for dict outputs
- Add/expand tag logic tests

## 4. Conversion (convert, mutate-convert modes)
- Refactor conversion to only handle concatenation/chapters
- Move mutation out of conversion
- Add error handling/diagnostics
- Update conversion tests for dict outputs
- Add/expand ffmpeg tests

## 5. Post-processing (convert, mutate-convert modes)
- Use `m4b_edit.py` for tag/cover edits
- Ensure tag/cover preservation
- Add/expand post-processing tests

## 6. Helper Functions (all modes)
- Restore/export helpers
- Document contracts/edge cases
- Add/expand helper tests

## 7. Test Suite (all modes/options)
- Update all tests for dict outputs
- Remove/update legacy tests
- Use fixtures for setup/teardown
- Add integration tests

## 8. Final Review (all modes/options)
- Compare outputs to legacy
- Document differences
- Update code/tests for compatibility

---

# Simple Reference Todo Lists (by test area)

## CLI/Argparse
- [ ] Refactor CLI entrypoint
- [ ] Normalize/validate args
- [ ] Update CLI tests
- [ ] Add option combination tests

## Extraction
- [x] Standardize output dicts
- [ ] Restore helpers
- [ ] Update extraction tests
- [ ] Add edge case tests

## Mutation
- [ ] Refactor to pure function
- [ ] Move file ops to utility
- [ ] Centralize options
- [ ] Update mutation tests
- [ ] Add tag logic tests

## Conversion
- [ ] Refactor for concatenation/chapters only
- [ ] Move mutation out
- [ ] Add error handling
- [ ] Update conversion tests
- [ ] Add ffmpeg tests

## Post-processing
- [ ] Use m4b_edit.py
- [ ] Ensure tag/cover preservation
- [ ] Add post-processing tests

## Helpers
- [ ] Restore/export helpers
- [ ] Document contracts
- [ ] Add helper tests

## Test Suite
- [ ] Update for dict outputs
- [ ] Remove legacy tests
- [ ] Use fixtures
- [ ] Add integration tests

## Final Review
- [ ] Compare outputs
- [ ] Document differences
- [ ] Update for compatibility
