from crawlers.plugins.eodc.parser import parse_eodc_collection, parse_eodc_item


def test_parse_eodc_item_returns_parsed_record():
    item = {
        "id": "item-123",
        "title": "Sample EODC item",
        "collection": "test-collection",
        "properties": {
            "datetime": "2024-05-21T12:00:00Z",
            "eo:common_name": "example",
            "product:type": "test-product",
            "platform": "sentinel-1",
            "updated": "2024-05-22T12:00:00Z",
            "processing:datetime": "2024-05-23T12:00:00Z",
        },
        "assets": {
            "data": {
                "href": "https://example.com/data.tiff",
                "type": "image/tiff",
            }
        },
        "links": [{"rel": "self", "href": "https://example.com/item/123"}],
    }
    collection_meta = {
        "title": "Test collection",
        "providers": [
            {"name": "EODC Host", "roles": ["host"]},
            {"name": "EODC Producer", "roles": ["producer"]},
        ],
        "keywords": ["geospatial", "satellite"],
        "description": "A test collection",
    }

    parsed = parse_eodc_item(item, collection_meta)

    assert parsed is not None
    assert parsed.identifier == "item-123"
    assert parsed.title == "Sample EODC item"
    assert parsed.metadata.publisher == "EODC Host"
    assert parsed.metadata.publication_year == 2024
    assert any("example" == subject for subject in parsed.metadata.subjects)
    assert parsed.files[0].url == "https://example.com/data.tiff"


def test_parse_eodc_item_skips_items_without_id():
    assert parse_eodc_item({}) is None


def test_parse_eodc_collection_parses_bbox_and_dates():
    collection = {
        "id": "collection-123",
        "title": "Collection title",
        "description": "Collection description",
        "providers": [{"name": "EODC Producer", "roles": ["producer"]}],
        "assets": {
            "metadata": {
                "href": "https://example.com/collection.json",
                "type": "application/json",
            }
        },
        "extent": {
            "temporal": {"interval": [["2024-01-01T00:00:00Z", "2024-01-31T23:59:59Z"]]},
            "spatial": {"bbox": [[10.0, 20.0, 11.0, 21.0]]},
        },
        "links": [{"rel": "self", "href": "https://example.com/collection/123"}],
    }

    parsed = parse_eodc_collection(collection)

    assert parsed is not None
    assert parsed.identifier == "collection-123"
    assert parsed.title == "Collection title"
    assert parsed.metadata.publication_year == 2024
    assert parsed.files[0].url == "https://example.com/collection.json"
    assert parsed.metadata.geo_locations[0].points[0] == (10.0, 20.0)
