"""SearchController: the control object of the three search sequence diagrams (keyword, voice, image).
Each method follows its diagram's steps in order; the step numbers are in the comments."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...errors import ValidationError
from . import images
from .dao import ProductDAO, ProductImageDAO, SearchHistoryDAO
from .query import SearchQuery, SearchRegion

MAX_KEYWORD = 100
# Emoji blocks plus the joiners that build them (ZWJ, variation selector, keycap); Vietnamese letters sit outside these.
EMOJI_RE = re.compile("[%s-%s%s-%s%s-%s%s-%s%s%s%s]" % tuple(map(chr, (
    0x1F000, 0x1FAFF, 0x2300, 0x23FF, 0x2600, 0x27BF, 0x2B00, 0x2BFF, 0x200D, 0xFE0F, 0x20E3))))
LETTER_RE = re.compile(r"[^\W_]")  # any letter or digit, accented ones included


class InvalidKeyword(ValidationError):
    """The diagram's error("Invalid Keyword"); the message says what to fix."""
    code = "invalid_keyword"


@dataclass
class ImageSearchResult:
    products: list = field(default_factory=list)
    label: str | None = None   # what Gemini saw in the photo, shown in the search box
    note: str | None = None    # why the results are colour matches, when they are


class SearchController:
    # --- Keyword search: steps 2-5 and 8-16 ------------------------------------------------------
    @staticmethod
    def show_search_box(customer) -> list:
        """2: showSearchBox(customerId) -> 3: SearchHistoryDAO.findRecent -> 5: return listHistory."""
        if customer is None:
            return []
        return SearchHistoryDAO.find_recent_keywords(customer.id)

    @staticmethod
    def validate_keyword(keyword: str | None) -> str:
        """9: validateKeyword(). Returns the trimmed keyword or raises InvalidKeyword (10)."""
        keyword = (keyword or "").strip()
        if not keyword:
            raise InvalidKeyword("Type a product name or brand to search.")
        if len(keyword) > MAX_KEYWORD:
            raise InvalidKeyword(f"Keep your search under {MAX_KEYWORD} characters.")
        if EMOJI_RE.search(keyword):
            raise InvalidKeyword("Search can't contain emojis. Please use letters and numbers only.")
        if not LETTER_RE.search(keyword):
            raise InvalidKeyword("Use letters or numbers to search.")
        return keyword

    @staticmethod
    def search_by_keyword(customer, keyword: str, search_type: str = "text") -> list:
        """8: searchByKeyword(keyword) -> 9 validate -> 12 new SearchQuery -> 13 save -> 14 findByKeyword."""
        keyword = SearchController.validate_keyword(keyword)
        query = SearchQuery.new(search_type, keyword)
        if customer is not None:  # visitors search too, but only customers have a history
            SearchHistoryDAO.save(query.to_history(customer))
        return ProductDAO.find_by_keyword(query.raw)

    # --- Voice search: steps 14-18 (steps 1-13, recording and recognising speech, run in the browser) ----
    @staticmethod
    def confirm_voice_text(customer, final_text: str) -> list:
        """14: confirmVoiceText(finalText) -> 15 new SearchQuery("VOICE") -> 16 save -> 17 findByKeyword."""
        return SearchController.search_by_keyword(customer, final_text, "voice")

    # --- Image search: steps 5-11 and 14-22 -----------------------------------------------------------
    @staticmethod
    def validate_image(image: bytes | None) -> tuple[int, int]:
        """5: imageFile -> 6: SearchQuery.validateImage() -> 7 invalid (raises "File error") / 10 valid."""
        return SearchQuery.validate_image(image)

    @staticmethod
    def search_by_image(customer, image: bytes | None, region: SearchRegion | None, filename: str,
                        categories: list[str]) -> ImageSearchResult:
        """14: searchByImage(image, region) -> 15 SearchRegion -> 16 new SearchQuery("IMAGE") -> 17 save
        -> 18 ProductImageDAO.findSimilar(featureVector) -> 20 ProductDAO.findById for each match.
        Before the colour match, Gemini names the product in the cropped photo and that name is searched
        like a keyword, because a name finds the right product far more often than colours do."""
        SearchController.validate_image(image)
        query = SearchQuery.new("image", filename or "photo", image=image, region=region)
        if customer is not None:
            SearchHistoryDAO.save(query.to_history(customer))
        label = images.describe(query.image, categories)
        products = ProductDAO.find_by_keyword(label) if label else []
        if products:
            return ImageSearchResult(products, label)
        matches = ProductImageDAO.find_similar(query.vector)
        note = (f"No products match “{label}”, so these are matched by colour." if label else
                "The AI couldn't read this photo right now (busy or offline), so these are matched by colour. "
                "Try again in a minute.")
        return ImageSearchResult([ProductDAO.find_by_id(m.product_id) for m in matches], label, note)

    @staticmethod
    def find_similar(product) -> list:
        """The product page's "Find similar": the image search steps 18-21, starting from a product photo."""
        vec = product.image_vector
        if not vec:
            return []
        return [ProductDAO.find_by_id(m.product_id) for m in ProductImageDAO.find_similar(vec, product.id)]
