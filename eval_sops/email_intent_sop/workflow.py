from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Extract product_id from email_body using simple token inspection
        email_body = input_data["email_body"]
        tokens = email_body.replace("\n", " ").split()
        extracted_product_id = None
        for token in tokens:
            # Strip common punctuation
            clean_token = token.strip(".,;:!?)('\"")
            if len(clean_token) == 6 and clean_token.startswith("P") and clean_token.isalnum():
                extracted_product_id = clean_token
                break
        # Fallback to the provided product_id if extraction failed
        if not extracted_product_id:
            extracted_product_id = input_data["product_id"]

        # Step 2: Determine seller intent based on email content
        lower_body = email_body.lower()

        # Pricing concern detection
        if "price" in lower_body:
            seller_intent = "concern about incorrect pricing"
            action = "update price"
        # Description concern detection
        elif "description" in lower_body:
            seller_intent = "concern about incorrect description"
            action = "update description"
        # Listing not listed detection (various phrasing cues)
        elif any(phrase in lower_body for phrase in [
            "not listed", "not showing", "not appearing",
            "can't find", "cannot find", "product not visible",
            "product not showing", "why isnt", "why is", "why isn't", "why is"
        ]):
            seller_intent = "concern about their product not being listed"
            action = "share listing status"
        # Generic question fallback (email mentions the product but none of the above)
        elif extracted_product_id and extracted_product_id in email_body:
            seller_intent = "generic question about a listing"
            action = "no action"
        # Unable to decide fallback
        else:
            seller_intent = "unable to decide"
            action = "further clarification required"

        # Step 3: Fetch additional data based on intent when required
        price_info = None
        description_info = None
        listing_status_info = None
        inventory_info = None

        if seller_intent == "concern about incorrect pricing":
            price_info = manager.get_product_price(
                product_id=extracted_product_id,
                marketplace_id=input_data["marketplace_id"]
            )
        elif seller_intent == "concern about incorrect description":
            description_info = manager.get_product_description(
                product_id=extracted_product_id
            )
        elif seller_intent == "concern about their product not being listed":
            listing_status_info = manager.get_product_listing_status(
                product_id=extracted_product_id,
                marketplace_id=input_data["marketplace_id"],
                include_history=False
            )
            inventory_info = manager.get_inventory_status(
                product_id=extracted_product_id,
                marketplace_id=input_data["marketplace_id"],
                include_forecasts=False
            )
        # No external calls needed for generic or unable intents

        # Combine every step's result the SOP's Output section names as fields
        return {
            "email_id": input_data["email_id"],
            "product_id": extracted_product_id,
            "seller_intent": seller_intent,
            "action": action,
            # Optional inclusion of fetched data for completeness
            "price_info": price_info,
            "description_info": description_info,
            "listing_status_info": listing_status_info,
            "inventory_info": inventory_info
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}