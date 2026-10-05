from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Extract product_id from email_body using simple token parsing
        raw_body = "" if (input_data.get("email_body") is None) else str(input_data["email_body"])
        tokens = raw_body.replace("\n", " ").replace("\r", " ").split()
        extracted_product_id = ""
        for tok in tokens:
            cleaned = tok.strip('.,;:!?"\'()[]{}')
            if len(cleaned) == 6 and cleaned.upper().startswith("P") and cleaned.isalnum():
                extracted_product_id = cleaned.upper()
                break

        # Use the extracted product_id; if none found, fall back to input product_id
        product_id = extracted_product_id if extracted_product_id else input_data["product_id"]

        # Step 2: Determine seller intent based on email content
        lower_body = raw_body.lower()

        # Helper flags
        has_price = "price" in lower_body
        has_description = "description" in lower_body
        # Listing‑not‑listed indicative phrases
        listing_phrases = [
            "not listed",
            "not showing",
            "not visible",
            "not appearing",
            "can't find",
            "cannot find",
            "cant find",
        ]
        has_listing_phrase = any(phrase in lower_body for phrase in listing_phrases)

        # Does the body mention the product id (any case)?
        mentions_product = product_id.lower() in lower_body

        if has_price:
            seller_intent = "concern about incorrect pricing"
        elif has_description:
            seller_intent = "concern about incorrect description"
        elif mentions_product and has_listing_phrase:
            seller_intent = "concern about their product not being listed"
        elif mentions_product:
            seller_intent = "generic question about a listing"
        else:
            seller_intent = "unable to decide"

        # Step 3: Map intent to action
        intent_action_map = {
            "concern about their product not being listed": "share listing status",
            "concern about incorrect pricing": "update price",
            "concern about incorrect description": "update description",
            "generic question about a listing": "no action",
            "unable to decide": "further clarification required",
        }
        action = intent_action_map.get(seller_intent, "further clarification required")

        # Step 4: Retrieve additional data based on intent
        price_info = None
        description_info = None
        listing_status_info = None
        inventory_status_info = None

        if seller_intent == "concern about incorrect pricing":
            price_info = manager.get_product_price(
                product_id=product_id,
                marketplace_id=input_data["marketplace_id"],
            )
        elif seller_intent == "concern about incorrect description":
            description_info = manager.get_product_description(
                product_id=product_id,
            )
        elif seller_intent == "concern about their product not being listed":
            listing_status_info = manager.get_product_listing_status(
                product_id=product_id,
                marketplace_id=input_data["marketplace_id"],
                include_history=False,
            )
            inventory_status_info = manager.get_inventory_status(
                product_id=product_id,
                marketplace_id=input_data["marketplace_id"],
                include_forecasts=False,
            )
        # No external calls needed for generic question or unable to decide

        # Combine results for final output
        return {
            "email_id": input_data["email_id"],
            "product_id": product_id,
            "seller_intent": seller_intent,
            "action": action,
            "price_info": price_info,
            "description_info": description_info,
            "listing_status_info": listing_status_info,
            "inventory_status_info": inventory_status_info,
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}