"""Turning a SharePoint link the user pasted into the drive item behind it.

A browser URL says nothing about drive ids, so Graph's /shares endpoint does the
translation. That is why the UI can ask for a copied link rather than making
anyone hunt down a site id.
"""
import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class DriveItemRef:
    """Everything needed to address one file in Graph's workbook API."""

    drive_id: str
    item_id: str
    name: str
    web_url: str = ""

    @property
    def path(self) -> str:
        """The `/drives/{id}/items/{id}` prefix every workbook call hangs off."""
        return f"/drives/{self.drive_id}/items/{self.item_id}"


def encode_share_url(url: str) -> str:
    """Encode a sharing URL the way /shares wants it: "u!" + unpadded base64url."""
    token = base64.urlsafe_b64encode(url.strip().encode("utf-8")).decode("ascii")
    return "u!" + token.rstrip("=")


def share_url_to_item(client, url: str) -> DriveItemRef:
    """Resolve a pasted SharePoint / OneDrive URL to the file it points at.

    Raises:
        ValueError: If `url` is not a link, or the item Graph returns is not in
            a drive (a page or list item rather than a file).
        GraphError: If the link is unknown or the signed-in user cannot see it.
    """
    url = (url or "").strip()
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError(
            f"Expected an https link copied from SharePoint, got {url!r}"
        )

    item = client.get(
        f"/shares/{encode_share_url(url)}/driveItem"
        "?$select=id,name,webUrl,parentReference"
    )

    drive_id = (item.get("parentReference") or {}).get("driveId")
    if not drive_id:
        raise ValueError(
            f"{item.get('name') or url!r} is not a file in a document library, "
            "so it has no drive to write to"
        )

    return DriveItemRef(
        drive_id=drive_id,
        item_id=item["id"],
        name=item.get("name", ""),
        web_url=item.get("webUrl", ""),
    )
