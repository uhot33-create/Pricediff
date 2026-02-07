from dataclasses import dataclass
from typing import Optional


@dataclass
class Item:
    name: str
    image_url: str
    price: Optional[int]
    shipping: Optional[int]
    url: str
