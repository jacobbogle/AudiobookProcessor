# Final Todo List: Failing Tests

The following tests are currently failing and need to be fixed:

1. **tests/test_chapter_rendering.py::test_chapter_titles_appear_in_m4b_chapters**
   - Error: Exception: Output file was not created or is empty

2. **tests/test_integration_m4b_chapters.py::test_real_m4b_chapter_update**
   - Error: AttributeError: 'function' object has no attribute 'score'

3. **tests/test_integration_series_tags.py::test_write_and_read_series_tags**
   - Error: TypeError: super() argument 1 must be type, not function

4. **tests/test_mutate_convert_tags.py::test_mutate_convert_produces_expected_tags**
   - Error: Exception: Output file was not created or is empty

5. **tests/test_mutate_metadata_full_fields_extra2.py::test_mutate_metadata_derives_album_sort_and_title_sort**
   - Error: ValueError: No audio files found in: C:\Users\Bogle\AppData\Local\Temp\pytest-of-Bogl...

6. **tests/test_mutate_metadata_full_fields_extra2.py::test_mutate_metadata_prefers_original_trkn_per_chapter**
   - Error: ValueError: No audio files found in: C:\Users\Bogle\AppData\Local\Temp\pytest-of-Bogl...

7. **tests/test_mutate_metadata_full_fields_extra2.py::test_mutate_metadata_title_from_folder_when_no_title**
   - Error: ValueError: No audio files found in: C:\Users\Bogle\AppData\Local\Temp\pytest-of-Bogl...

8. **tests/test_mutate_metadata_full_fields_extra3.py::test_album_sort_prefix_and_series_name**
   - Error: UnboundLocalError: local variable 'metadata' referenced before assignment

9. **tests/test_mutate_metadata_full_fields_extra3.py::test_part_titles_grouping_and_filenames**
   - Error: ValueError: No audio files found in: C:\Users\Bogle\AppData\Local\Temp\pytest-of-Bogl...

10. **tests/test_mutate_metadata_full_fields_extra3.py::test_series_index_inference_from_parent**
    - Error: ValueError: No audio files found in: C:\Users\Bogle\AppData\Local\Temp\pytest-of-Bogl...

11. **tests/test_mutate_metadata_sample.py::test_mutate_metadata_basic**
    - Error: AssertionError: assert 'test.mp3' in {'test_folder\\test.mp3': {'album': 'Test Album'...

12. **tests/test_part_title_option.py::test_part_title_groups_and_filenames**
    - Error: AssertionError: Missing expected renamed files: ['Source Book 01 Part 2 - 011.m4a', '...

13. **tests/test_part_titles_noffmpeg.py::test_part_titles_no_ffmpeg**
    - Error: AssertionError: No mutated files found

Total: 13 failing tests out of 129 total tests (114 passed, 1 skipped).