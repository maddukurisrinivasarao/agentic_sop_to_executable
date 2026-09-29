from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Extract product_id from email_body (fallback to input product_id if not found)
        email_body = input_data["email_body"]
        extracted_product_id = None
        for token in email_body.split():
            if len(token) == 6 and token[0] == "P" and token.isalnum():
                extracted_product_id = token
                break
        # Use the extracted ID if found, otherwise trust the supplied product_id
        product_id = extracted_product_id if extracted_product_id else input_data["product_id"]

        # Step 2: Classify seller intent based on keywords and phrasing
        lower_body = email_body.lower()
        if "price" in lower_body:
            seller_intent = "concern about incorrect pricing"
        elif "description" in lower_body:
            seller_intent = "concern about incorrect description"
        elif any(phrase in lower_body for phrase in [
            "not listed", "not showing", "can't find", "cannot find",
            "not appearing", "not visible", "listed yet", "not listed yet",
            "not showing up", "not appearing"
        ]):
            seller_intent = "concern about their product not being listed"
        else:
            # Default to generic question when none of the above patterns match
            seller_intent = "generic question about a listing"

        # Step 3: Determine action based on classified intent
        if seller_intent == "concern about their product not being listed":
            action = "share listing status"
        elif seller_intent == "concern about incorrect pricing":
            action = "update price"
        elif seller_intent == "concern about incorrect description":
            action = "update description"
        elif seller_intent == "generic question about a listing":
            action = "no action"
        else:
            action = "further clarification required"

        # Step 4: Retrieve additional data only when required by the determined action
        # Price retrieval for pricing concerns
        price_info = None
        if action == "update price":
            price_info = manager.get_product_price(
                product_id=product_id,
                marketplace_id=input_data["marketplace_id"]
            )
        # Description retrieval for description concerns
        description_info = None
        if action == "update description":
            description_info = manager.get_product_description(
                product_id=product_id
            )
        # Listing status and inventory retrieval for listing status concerns
        listing_status_info = None
        inventory_info = None
        if action == "share listing status":
            listing_status_info = manager.get_product_listing_status(
                product_id=product_id,
                marketplace_id=input_data["marketplace_id"],
                include_history=False
            )
            inventory_info = manager.get_inventory_status(
                product_id=product_id,
                marketplace_id=input_data["marketplace_id"],
                include_forecasts=False
            )

        # Step 5: Assemble final output matching SOP's Output fields
        return {
            "email_id": input_data["email_id"],
            "product_id": product_id,
            "seller_intent": seller_intent,
            "action": action,
            # The following fields are included to ensure every step's result is represented,
            # even though they are not explicitly required in the SOP's XML output.
            "price_info": price_info,
            "description_info": description_info,
            "listing_status_info": listing_status_info,
            "inventory_info": inventory_info
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}