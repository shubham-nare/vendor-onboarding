"""Verify PDF digital signatures (e.g. GST certificates signed by GSTN).

Handles the legacy /adbe.pkcs7.sha1 format (what the GST portal used, and what pyHanko
rejects) and the common detached formats (/adbe.pkcs7.detached, /ETSI.CAdES.detached).

Checks two things:
  intact    - the hash of the signed bytes equals the hash inside the signature
              (any change to the signed content after signing makes this False)
  valid     - the signer's RSA signature over that hash verifies with the signer certificate
It does NOT check whether the signer certificate chains to a trusted Indian CA root at the
time of signing (that needs the CCA India roots and revocation data: a production add-on).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

_HASHES = {"sha1": hashes.SHA1, "sha256": hashes.SHA256, "sha384": hashes.SHA384, "sha512": hashes.SHA512}
_BYTERANGE = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")
_SUBFILTER = re.compile(rb"/SubFilter\s*/([A-Za-z0-9.]+)")


@dataclass
class SignatureCheck:
    present: bool
    sub_filter: str = ""
    signer: str = ""
    signer_org: str = ""
    chain: list[str] = field(default_factory=list)
    signed_at: str = ""
    intact: bool | None = None
    valid: bool | None = None
    covers_whole_file: bool | None = None
    error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def is_gstn(self) -> bool:
        return "GOODS AND SERVICES TAX NETWORK" in self.signer.upper()


def _cn(name: x509.Name) -> str:
    vals = name.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    return vals[0].value if vals else name.rfc4514_string()[:80]


def check_pdf_signature(raw: bytes) -> SignatureCheck:
    """Check the last signature in the file (the one that covers the most bytes)."""
    ranges = list(_BYTERANGE.finditer(raw))
    if not ranges:
        return SignatureCheck(present=False)
    m = ranges[-1]
    a, b, c, d = map(int, m.groups())
    sub = _SUBFILTER.findall(raw)
    sub_filter = sub[-1].decode() if sub else ""
    try:
        signed = raw[a:a + b] + raw[c:c + d]
        hex_blob = raw[a + b:c].strip().lstrip(b"<").rstrip(b">").strip()
        der = bytes.fromhex(hex_blob.decode("ascii"))
        content = cms.ContentInfo.load(der, strict=False)["content"]
        si = content["signer_infos"][0]
        algo = si["digest_algorithm"]["algorithm"].native
        hash_cls = _HASHES[algo]
        sid = si["sid"].chosen
        certs = [cc.chosen for cc in content["certificates"]]
        signer_asn = next(
            (cc for cc in certs if cc.serial_number == sid["serial_number"].native and cc.issuer == sid["issuer"]),
            certs[0],
        )
        cert = x509.load_der_x509_certificate(signer_asn.dump())

        signed_attrs = si["signed_attrs"]
        if sub_filter == "adbe.pkcs7.sha1":
            embedded = content["encap_content_info"]["content"].native  # SHA-1 of the byte ranges
            intact = hashlib.sha1(signed).digest() == embedded
            data_to_verify = signed_attrs.untag().dump() if signed_attrs.native else embedded
        else:
            md = next(x["values"][0].native for x in signed_attrs if x["type"].native == "message_digest")
            h = hashlib.new(algo)
            h.update(signed)
            intact = h.digest() == md
            data_to_verify = signed_attrs.untag().dump()

        pub = cert.public_key()
        try:
            if isinstance(pub, rsa.RSAPublicKey):
                pub.verify(si["signature"].native, data_to_verify, padding.PKCS1v15(), hash_cls())
            elif isinstance(pub, ec.EllipticCurvePublicKey):
                pub.verify(si["signature"].native, data_to_verify, ec.ECDSA(hash_cls()))
            valid = True
        except Exception:
            valid = False

        signed_at = ""
        for attr in signed_attrs or []:
            if attr["type"].native == "signing_time":
                signed_at = str(attr["values"][0].native)
        if not signed_at:
            mm = re.search(rb"/M\s*\(D:(\d{14})", raw)
            signed_at = mm.group(1).decode() if mm else ""

        org = cert.subject.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME)
        return SignatureCheck(
            present=True,
            sub_filter=sub_filter,
            signer=_cn(cert.subject),
            signer_org=org[0].value if org else "",
            chain=[c2.subject.native.get("common_name", "?") for c2 in certs],
            signed_at=signed_at,
            intact=intact,
            valid=valid,
            covers_whole_file=(c + d == len(raw)) or (c + d >= len(raw.rstrip())),
        )
    except Exception as e:  # malformed signature = treat as present but unverifiable
        return SignatureCheck(present=True, sub_filter=sub_filter, intact=False, valid=False, error=f"{type(e).__name__}: {e}"[:200])
