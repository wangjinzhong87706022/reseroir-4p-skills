import sys; sys.path.insert(0, "..")
from vision_extract import build_payload, cross_check
import base64, json

def test_build_payload_structure():
    fake_bytes = b"\xff\xd8\xff\xe0fake image data"
    payload = build_payload(fake_bytes, "识别数值")
    content = payload["content"]
    img_part = next(p for p in content if p.get("type") == "image_url")
    b64_data = img_part["image_url"]["url"].split(",")[1]
    assert base64.b64decode(b64_data) == fake_bytes

def test_cross_check_found():
    text = "百年一遇泄量1454 m³/s，千年一遇泄量2218 m³/s，汛限水位788.5m"
    result = cross_check(text)
    assert result["found"]["1454"] is True
    assert result["found"]["2218"] is True
    assert result["found"]["788.5"] is True

def test_cross_check_missing():
    text = "汛限水位为788米"
    result = cross_check(text)
    assert result["found"]["1454"] is False
    assert result["found"]["788.5"] is False   # "788" alone doesn't match "788.5"

def test_cross_check_output_shape():
    text = "test"
    result = cross_check(text)
    assert "found" in result and "values" in result
    assert isinstance(result["found"], dict)
