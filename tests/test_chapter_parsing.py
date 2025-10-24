import pytest
from audiobook_p.chapters import parse_chapter_spec, parse_time_to_seconds


def test_parse_time_various_formats():
    assert parse_time_to_seconds('00:00:00') == 0.0
    assert parse_time_to_seconds('00:01:30') == 90.0
    assert parse_time_to_seconds('1:30') == 90.0
    assert parse_time_to_seconds('65.5') == 65.5
    assert parse_time_to_seconds('') is None
    assert parse_time_to_seconds(None) is None


def test_parse_chapter_range_with_title():
    out = parse_chapter_spec('00:00:00-00:05:00:Chapter 1')
    assert out['start_s'] == 0.0
    assert out['end_s'] == 300.0
    assert out['title'] == 'Chapter 1'


def test_parse_chapter_seconds_range():
    out = parse_chapter_spec('0-300:Intro')
    assert out['start_s'] == 0.0
    assert out['end_s'] == 300.0
    assert out['title'] == 'Intro'


def test_parse_json_object_string():
    out = parse_chapter_spec('{"start":"00:05:00","title":"Part 1"}')
    assert out['start_s'] == 300.0
    assert out['end_s'] is None
    assert out['title'] == 'Part 1'


def test_parse_shorthand_ch():
    out = parse_chapter_spec('ch2')
    assert out['title'] == 'Chapter 2'
    assert out['start_s'] is None


def test_parse_single_time_with_title():
    out = parse_chapter_spec('65.5:Quick')
    assert out['start_s'] == 65.5
    assert out['title'] == 'Quick'


def test_parse_kv_form():
    out = parse_chapter_spec('start=00:00:00,end=00:05:00,title=Chapter 1')
    assert out['start_s'] == 0.0
    assert out['end_s'] == 300.0
    assert out['title'] == 'Chapter 1'
