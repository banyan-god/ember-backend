from __future__ import annotations

from fido2 import cbor
from fido2.cose import CoseKey, ES256

from ember_backend.security.webauthn_service import _serialize_cose_public_key


def test_serialize_cose_public_key_from_map_round_trips() -> None:
    key_map = {
        1: 2,
        3: -7,
        -1: 1,
        -2: b"\x01" * 32,
        -3: b"\x02" * 32,
    }
    encoded = _serialize_cose_public_key(key_map)
    parsed = CoseKey.parse(cbor.decode(encoded))

    assert isinstance(encoded, bytes)
    assert parsed[1] == key_map[1]
    assert parsed[3] == key_map[3]
    assert parsed[-1] == key_map[-1]
    assert parsed[-2] == key_map[-2]
    assert parsed[-3] == key_map[-3]


def test_serialize_cose_public_key_bytes_passthrough() -> None:
    source = {
        1: 2,
        3: -7,
        -1: 1,
        -2: b"\x03" * 32,
        -3: b"\x04" * 32,
    }
    encoded = _serialize_cose_public_key(ES256(source))
    parsed = CoseKey.parse(cbor.decode(encoded))
    assert parsed[-2] == source[-2]
    assert parsed[-3] == source[-3]
