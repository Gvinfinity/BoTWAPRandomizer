"""Marker replacement for an already decoded shop slot list.

This helper does not decode native ShopData AAMP resources or discover shops;
shops are not part of the generated chest catalog yet.
"""
try:
    from .core import ROOT
except ImportError:
    from core import ROOT
from botw_static.checks import check_actor_name


def patch_shop_byml(byml_data: dict, shop_map: dict) -> bool:
    items = byml_data.get('Items', [])
    names = {}
    for index, location_id in shop_map.items():
        if type(index) is not int or not 0 <= index < len(items):
            raise ValueError(f'Mapped shop slot is absent: {index}')
        names[index] = check_actor_name(location_id)
    if len(set(names.values())) != len(names):
        raise ValueError('Duplicate shop check IDs')
    for index, name in names.items():
        items[index]['ItemName'] = name
        items[index].pop('AP_LocationID', None)
    return bool(names)


def process_bshop_file(filepath: str, shop_map: dict):
    raise NotImplementedError('Native ShopData decoding and catalog bindings are not implemented')
