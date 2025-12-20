# Add this to the get_file_changes error handling:

    except json.JSONDecodeError as e:
        # Check if the error suggests a truncated response
        error_msg = str(e)
        if "Unterminated" in error_msg or "Expecting" in error_msg:
            logger.error(f"Possible truncated response from Claude: {e}")
            logger.error(f"Response was: {response_text[:500]}")
            return None
        else:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.error(f"Response was: {response_text[:500]}")
            return None
