from app.models.schemas import (
    HomePlannerInput,
    PartyPlannerInput,
    JewelryPlannerInput,
)
from app.services.gemini_service import generate_json


def _links(query: str):
    from urllib.parse import quote_plus

    q = quote_plus(query)

    return [
        {
            "platform": "Amazon",
            "url": f"https://www.amazon.in/s?k={q}",
        },
        {
            "platform": "Flipkart",
            "url": f"https://www.flipkart.com/search?q={q}",
        },
        {
            "platform": "IKEA",
            "url": f"https://www.ikea.com/in/en/search/?q={q}",
        },
    ]


# ============================================================
# NORMALIZATION
# ============================================================

def _safe_float(value, default=0):
    """
    Convert Gemini numeric output into a safe float.
    Handles values such as:
        25000
        "25000"
        "₹25,000"
        "25,000"
    """
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        cleaned = (
            value.replace("₹", "")
            .replace(",", "")
            .replace("INR", "")
            .strip()
        )

        try:
            return float(cleaned)
        except ValueError:
            return default

    return default


def _normalize_allocation(allocation, total_budget):
    """
    Convert Gemini allocation output into:

    [
        {
            "category": "...",
            "amount": 10000
        }
    ]
    """

    if not isinstance(allocation, list):
        return [
            {
                "category": "Budget",
                "amount": float(total_budget),
            }
        ]

    normalized = []

    for item in allocation:

        # Gemini returned a proper object
        if isinstance(item, dict):

            category = (
                item.get("category")
                or item.get("name")
                or item.get("type")
                or "Other"
            )

            amount = (
                item.get("amount")
                if item.get("amount") is not None
                else item.get("budget")
            )

            if amount is None:
                amount = item.get("allocated_amount", 0)

            normalized.append(
                {
                    "category": str(category),
                    "amount": _safe_float(amount),
                }
            )

        # Gemini returned a string
        elif isinstance(item, str):

            normalized.append(
                {
                    "category": item,
                    "amount": 0,
                }
            )

        # Gemini returned a number
        elif isinstance(item, (int, float)):

            normalized.append(
                {
                    "category": "Allocation",
                    "amount": _safe_float(item),
                }
            )

    if not normalized:
        normalized.append(
            {
                "category": "Budget",
                "amount": float(total_budget),
            }
        )

    return normalized


def _normalize_platforms(platforms):
    """
    Normalize shopping platform information.
    """

    if not isinstance(platforms, list):
        return []

    normalized = []

    for platform in platforms:

        if isinstance(platform, dict):

            name = (
                platform.get("platform")
                or platform.get("name")
                or "View"
            )

            url = platform.get("url") or "#"

            normalized.append(
                {
                    "platform": str(name),
                    "url": str(url),
                }
            )

        elif isinstance(platform, str):

            normalized.append(
                {
                    "platform": platform,
                }
            )

    return normalized


def _normalize_recommendations(recommendations):
    """
    Convert Gemini recommendation output into the standard
    PocketSmart AI recommendation structure.
    """

    if not isinstance(recommendations, list):
        return []

    normalized = []

    for item in recommendations:

        # --------------------------------------------
        # Proper Gemini object
        # --------------------------------------------

        if isinstance(item, dict):

            name = (
                item.get("name")
                or item.get("item")
                or item.get("product")
                or item.get("category")
                or "Recommended Item"
            )

            price = (
                item.get("estimated_price")
                if item.get("estimated_price") is not None
                else item.get("price")
            )

            if price is None:
                price = item.get("estimated_cost", 0)

            reason = (
                item.get("reason")
                or item.get("description")
                or item.get("why")
                or "Recommended based on your requirements and budget."
            )

            platforms = _normalize_platforms(
                item.get("platforms", [])
            )

            normalized.append(
                {
                    "name": str(name),
                    "estimated_price": _safe_float(price),
                    "reason": str(reason),
                    "platforms": platforms,
                }
            )

        # --------------------------------------------
        # Gemini returned plain text
        # --------------------------------------------

        elif isinstance(item, str):

            normalized.append(
                {
                    "name": item,
                    "estimated_price": 0,
                    "reason": (
                        "Recommended based on your requirements "
                        "and budget."
                    ),
                    "platforms": [],
                }
            )

    return normalized


def _normalize_result(result, budget):
    """
    Normalize the complete Gemini response.
    """

    if not isinstance(result, dict):
        return None

    normalized = {
        "summary": str(
            result.get(
                "summary",
                "Here is your personalized PocketSmart AI plan.",
            )
        ),
        "budget": _safe_float(
            result.get("budget", budget),
            budget,
        ),
        "allocation": _normalize_allocation(
            result.get("allocation", []),
            budget,
        ),
        "recommendations": _normalize_recommendations(
            result.get("recommendations", [])
        ),
        "note": str(
            result.get(
                "note",
                "Prices are estimates and may change.",
            )
        ),
    }

    return normalized


# ============================================================
# FALLBACK — HOME
# ============================================================

def _fallback_home(data):

    per_item = round(
        data.budget / max(data.quantity, 1),
        2,
    )

    query = (
        f"{data.room_type} "
        f"{data.style} "
        f"{data.needs}"
    ).strip()

    return {
        "summary": (
            f"Plan for {data.room_type} "
            f"within ₹{data.budget:,.0f}."
        ),
        "budget": data.budget,
        "allocation": [
            {
                "category": data.room_type,
                "amount": data.budget,
            }
        ],
        "recommendations": [
            {
                "name": (
                    f"{data.style} "
                    f"{data.room_type} essentials"
                ),
                "estimated_price": per_item,
                "reason": (
                    "Search result links are generated "
                    "from your room, style and needs."
                ),
                "platforms": _links(query),
            }
        ],
        "note": (
            "Add GEMINI_API_KEY to enable "
            "AI-generated recommendations."
        ),
    }


# ============================================================
# FALLBACK — PARTY
# ============================================================

def _fallback_party(data):

    allocations = [
        (
            "Food & Catering",
            round(data.budget * 0.50, 2),
        ),
        (
            "Decoration",
            round(data.budget * 0.20, 2),
        ),
        (
            "Venue",
            round(data.budget * 0.20, 2),
        ),
        (
            "Entertainment",
            round(data.budget * 0.10, 2),
        ),
    ]

    return {
        "summary": (
            f"{data.event_type} plan for "
            f"{data.guest_count} guests within "
            f"₹{data.budget:,.0f}."
        ),
        "budget": data.budget,
        "allocation": [
            {
                "category": category,
                "amount": amount,
            }
            for category, amount in allocations
        ],
        "recommendations": [
            {
                "name": category,
                "estimated_price": amount,
                "reason": (
                    "Budget allocation based on "
                    "the event details."
                ),
                "platforms": _links(
                    f"{data.event_type} "
                    f"{category} "
                    f"{data.venue}"
                ),
            }
            for category, amount in allocations
        ],
        "note": (
            "Add GEMINI_API_KEY to enable "
            "AI-generated recommendations."
        ),
    }


# ============================================================
# FALLBACK — JEWELRY
# ============================================================

def _fallback_jewelry(data):

    return {
        "summary": (
            f"{data.style} jewelry ideas for "
            f"{data.occasion} within "
            f"₹{data.budget:,.0f}."
        ),
        "budget": data.budget,
        "allocation": [
            {
                "category": "Jewelry",
                "amount": data.budget,
            }
        ],
        "recommendations": [
            {
                "name": (
                    f"{data.style} jewelry "
                    f"for {data.occasion}"
                ),
                "estimated_price": data.budget,
                "reason": (
                    "Use the marketplace links to "
                    "compare current products and prices."
                ),
                "platforms": _links(
                    f"{data.occasion} "
                    f"{data.style} jewelry"
                ),
            }
        ],
        "note": (
            "Add GEMINI_API_KEY to enable "
            "multimodal outfit analysis."
        ),
    }


# ============================================================
# HOME PLANNER
# ============================================================

async def generate_home_recommendations(
    data: HomePlannerInput,
):

    prompt = f"""
You are PocketSmart AI's home interior budget planner.

Return ONLY valid JSON.

The JSON MUST follow EXACTLY this structure:

{{
    "summary": "short summary",
    "budget": {data.budget},
    "allocation": [
        {{
            "category": "Furniture",
            "amount": 10000
        }}
    ],
    "recommendations": [
        {{
            "name": "product or item name",
            "estimated_price": 5000,
            "reason": "why this is recommended",
            "platforms": [
                {{
                    "platform": "Amazon",
                    "url": "https://www.amazon.in/"
                }}
            ]
        }}
    ],
    "note": "important note"
}}

RULES:

1. allocation MUST be a JSON array.
2. Every allocation item MUST contain:
   - category
   - amount

3. recommendations MUST be a JSON array.
4. Every recommendation MUST contain:
   - name
   - estimated_price
   - reason
   - platforms

5. platforms MUST be an array of objects containing:
   - platform
   - url

6. estimated_price and amount MUST be numbers.
7. Do NOT return recommendations as plain strings.
8. Do NOT return markdown.
9. Do NOT use code fences.
10. Keep the total allocation within the user's budget.
11. Do not claim live availability.
12. Do not claim exact current prices.

USER DETAILS:

Budget: INR {data.budget}
Room: {data.room_type}
Quantity: {data.quantity}
Style: {data.style}
Needs: {data.needs}
"""

    result = await generate_json(prompt)

    normalized = _normalize_result(
        result,
        data.budget,
    )

    return normalized or _fallback_home(data)


# ============================================================
# PARTY PLANNER
# ============================================================

async def generate_party_recommendations(
    data: PartyPlannerInput,
):

    prompt = f"""
You are PocketSmart AI's party budget planner.

Return ONLY valid JSON.

The JSON MUST follow EXACTLY this structure:

{{
    "summary": "short party plan summary",
    "budget": {data.budget},
    "allocation": [
        {{
            "category": "Food & Catering",
            "amount": 10000
        }}
    ],
    "recommendations": [
        {{
            "name": "recommended item or service",
            "estimated_price": 5000,
            "reason": "why it is suitable",
            "platforms": [
                {{
                    "platform": "Amazon",
                    "url": "https://www.amazon.in/"
                }}
            ]
        }}
    ],
    "note": "important note"
}}

RULES:

1. allocation MUST be an array of objects.
2. Each allocation object MUST contain category and amount.
3. recommendations MUST be an array of objects.
4. Each recommendation MUST contain name, estimated_price,
   reason and platforms.
5. platforms MUST contain platform and url.
6. amount and estimated_price MUST be numbers.
7. Do NOT return plain strings inside recommendations.
8. Do NOT return markdown or code fences.
9. Do not claim live vendor availability.
10. Do not claim exact current prices.
11. Keep the total allocation within the budget.

USER DETAILS:

Budget: INR {data.budget}
Guests: {data.guest_count}
Event type: {data.event_type}
Venue details: {data.venue}
Preferences: {data.preferences}
"""

    result = await generate_json(prompt)

    normalized = _normalize_result(
        result,
        data.budget,
    )

    return normalized or _fallback_party(data)


# ============================================================
# JEWELRY PLANNER
# ============================================================

async def generate_jewelry_recommendations(
    data: JewelryPlannerInput,
):

    prompt = f"""
You are PocketSmart AI's jewelry recommendation assistant.

Return ONLY valid JSON.

The JSON MUST follow EXACTLY this structure:

{{
    "summary": "short jewelry recommendation summary",
    "budget": {data.budget},
    "allocation": [
        {{
            "category": "Jewelry",
            "amount": 10000
        }}
    ],
    "recommendations": [
        {{
            "name": "recommended jewelry item",
            "estimated_price": 5000,
            "reason": "why it matches the occasion and style",
            "platforms": [
                {{
                    "platform": "Amazon",
                    "url": "https://www.amazon.in/"
                }}
            ]
        }}
    ],
    "note": "important note"
}}

RULES:

1. allocation MUST be an array of objects.
2. Every allocation object MUST contain category and amount.
3. recommendations MUST be an array of objects.
4. Every recommendation MUST contain:
   - name
   - estimated_price
   - reason
   - platforms

5. platforms MUST be an array of objects containing:
   - platform
   - url

6. amount and estimated_price MUST be numbers.
7. Do NOT return recommendations as plain strings.
8. Do NOT return markdown.
9. Do NOT use code fences.
10. Do not identify people in the uploaded image.
11. If an outfit image is supplied, use only its colors
    and visual style for coordination.
12. Do not claim live inventory.
13. Do not claim exact current prices.
14. Keep recommendations within the budget.

USER DETAILS:

Budget: INR {data.budget}
Occasion: {data.occasion}
Style: {data.style}
Outfit notes: {data.outfit_notes}
"""

    result = await generate_json(
        prompt,
        data.image_path,
    )

    normalized = _normalize_result(
        result,
        data.budget,
    )

    return normalized or _fallback_jewelry(data)