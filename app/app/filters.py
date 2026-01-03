# filters.py - Dynamic filters based on translation cache
"""
Language-agnostic filters that check against DB translations.
Adding new languages requires NO code changes - just DB updates.
"""
from telegram.ext import filters
from telegram import Update
from app.translations import get_cached_languages, get_text


# ============================================================================
# DYNAMIC TEXT MATCHING
# ============================================================================

def matches_translation_key(text: str, key: str) -> bool:
    """
    Check if text matches translation key in ANY language.
    
    Args:
        text: User's message text
        key: Translation key (e.g., "menu_consultation")
    
    Returns:
        True if text matches the translation in any language
    """
    if not text:
        return False
    
    # Check against all cached languages
    for lang in get_cached_languages():
        translation = get_text(lang, key)
        if translation and text == translation:
            return True
    
    return False


# ============================================================================
# CUSTOM FILTER CLASSES
# ============================================================================

class TranslationKeyFilter(filters.MessageFilter):
    """
    Filter that matches messages against a translation key in any language.
    
    Example:
        booking_filter = TranslationKeyFilter("menu_consultation")
        # Matches "Запись на консультацию" (ru) OR "Գրանցվել խորհրդատվության" (am)
    """
    
    def __init__(self, key: str):
        self.key = key
        super().__init__()
    
    def filter(self, message):
        if not message.text:
            return False
        return matches_translation_key(message.text, self.key)


class MultiKeyFilter(filters.MessageFilter):
    """
    Filter that matches messages against multiple translation keys.
    
    Example:
        admin_buttons = MultiKeyFilter([
            "admin_toggle", "admin_pending", "admin_slots"
        ])
    """
    
    def __init__(self, keys: list):
        self.keys = keys
        super().__init__()
    
    def filter(self, message):
        if not message.text:
            return False
        
        for key in self.keys:
            if matches_translation_key(message.text, self.key):
                return True
        
        return False


# ============================================================================
# PRE-BUILT FILTERS (using translation keys)
# ============================================================================

# Home button (works in any language)
home_button = TranslationKeyFilter("menu_home")

# Consultation booking button (works in any language)
booking_button = TranslationKeyFilter("menu_consultation")

# Menu navigation buttons
terms_button = TranslationKeyFilter("menu_terms")
qualification_button = TranslationKeyFilter("menu_qual")
about_button = TranslationKeyFilter("menu_about")


# ============================================================================
# ADMIN BUTTON FILTER (for conversation escaping)
# ============================================================================

# Note: These are English-only admin UI buttons, not translated
# If you want multilingual admin UI, add these to translations.py and use TranslationKeyFilter
admin_button_hardcoded = filters.Regex(
    "^(Toggle Availability|Upload Landing|Pending Requests|Edit Prices|Create Slot|View Slots)$"
)


# ============================================================================
# COMBINED FILTERS
# ============================================================================

# Landing page buttons (should trigger handle_menu_click)
landing_buttons = (
    terms_button | 
    qualification_button | 
    about_button
)

# Buttons that have dedicated handlers (exclude from generic handler)
excluded_from_generic = (
    booking_button |  # Has ConversationHandler
    home_button       # Has dedicated handler
)

# All menu buttons (for reference)
all_menu_buttons = (
    booking_button | 
    terms_button | 
    qualification_button | 
    about_button | 
    home_button
)


# ============================================================================
# HELPER FUNCTION FOR DEBUGGING
# ============================================================================

def get_translation_key_for_text(text: str) -> str:
    """
    Reverse lookup: find which translation key matches this text.
    Useful for debugging and logging.
    
    Args:
        text: User's message text
    
    Returns:
        Translation key or "unknown"
    """
    # Common keys to check
    common_keys = [
        "menu_consultation", "menu_terms", "menu_qual", "menu_about", "menu_home",
        "btn_online", "btn_onsite", "btn_individual", "btn_couple",
        "btn_agree", "btn_counter"
    ]
    
    for key in common_keys:
        if matches_translation_key(text, key):
            return key
    
    return "unknown"
